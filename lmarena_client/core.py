from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from .browser import BrowserManager
from .config import ClientConfig
from .discovery import Discovery
from .errors import ModelNotFoundError, StreamError
from .http import StreamSession, ensure_ok
from .stream import StreamFinal, StreamImages, Usage
from .uploader import ImageUploader
from .utils import log, log_exc, uuid7


@dataclass
class ChatResult:
    text: str
    evaluation_session_id: str
    finish_reason: Optional[str] = None
    usage: Optional[Usage] = None
    images: Optional[list[str]] = None


class LMArenaCore:
    """
    Core engine that talks to LMArena:
    - ensures browser bootstrap
    - loads models/actions via discovery
    - uploads images (if any)
    - posts create-evaluation / post-to-evaluation
    - parses LMArena streaming protocol
    """

    def __init__(self, config: ClientConfig, browser: BrowserManager, discovery: Discovery) -> None:
        self._config = config
        self._browser = browser
        self._discovery = discovery
        self._uploader = ImageUploader(config=config, browser=browser, discovery=discovery)

    @property
    def discovery(self) -> Discovery:
        return self._discovery

    async def bootstrap(self) -> None:
        await self._browser.ensure_ready()
        await self._discovery.ensure_loaded()

    async def list_models(self) -> list[str]:
        await self.bootstrap()
        return list(self._discovery.state.models or [])

    async def stream_message(
        self,
        *,
        model: str,
        prompt: str,
        evaluation_session_id: Optional[str] = None,
        create_new: bool = False,
        media: list[tuple[Any, Optional[str]]] | None = None,
        timeout: Optional[int] = None,
    ) -> AsyncIterator[str | StreamImages | StreamFinal]:
        """
        Stream a single user message. Yields:
        - text deltas (str)
        - StreamImages when image URLs are produced
        - StreamFinal at the end

        NOTE: This is low-level; the higher-level ChatSession wraps it.
        """
        await self.bootstrap()

        state = self._discovery.state
        if not model:
            model = state.default_model or ""
        model_id = self._discovery.resolve_model_id(model)
        if not model_id:
            raise ModelNotFoundError(f"Unknown model: {model!r}")

        if media and not self._discovery.supports_vision_input(model):
            raise ValueError(f"Model {model!r} does not support image input, but images were provided.")

        is_image_output_model = self._discovery.is_image_output_model(model)

        # conversation routing
        # - create_new=True forces create-evaluation endpoint, even if a client pre-generated an id.
        #   This enables "client.chats.create()" to hand out a chat_id immediately.
        if create_new:
            url = f"{self._config.origin.rstrip('/')}/nextjs-api/stream/create-evaluation"
            eval_id = evaluation_session_id or str(uuid7())
        elif evaluation_session_id:
            url = f"{self._config.origin.rstrip('/')}/nextjs-api/stream/post-to-evaluation/{evaluation_session_id}"
            eval_id = evaluation_session_id
        else:
            url = f"{self._config.origin.rstrip('/')}/nextjs-api/stream/create-evaluation"
            eval_id = str(uuid7())

        user_message_id = str(uuid7())
        model_a_message_id = str(uuid7())

        files = await self._uploader.upload(media)

        max_attempts = 2
        emitted_anything = False

        for attempt in range(max_attempts):
            grecaptcha = None
            try:
                http_args = await self._browser.get_http_args()
                grecaptcha = await self._browser.get_grecaptcha_token()

                payload = {
                    "id": eval_id,
                    "mode": "direct",
                    "modelAId": model_id,
                    "userMessageId": user_message_id,
                    "modelAMessageId": model_a_message_id,
                    "userMessage": {
                        "content": prompt or "",
                        "experimental_attachments": files,
                        "metadata": {},
                    },
                    "modality": "image" if is_image_output_model else "chat",
                    "recaptchaV3Token": grecaptcha,
                }

                async with StreamSession(
                    headers=http_args.headers,
                    cookies=http_args.cookies,
                    timeout=timeout or self._config.timeout_seconds,
                ) as session:
                    async with session.post(url, json=payload) as response:
                        await ensure_ok(response, context="chat stream")

                        async for raw in response.iter_lines():
                            line = raw.decode(errors="ignore")

                            if line.startswith("a0:"):
                                chunk = json.loads(line[3:])
                                if chunk == "hasArenaError":
                                    raise ModelNotFoundError("LMArena stream encountered an error: hasArenaError")
                                if isinstance(chunk, str) and chunk:
                                    yield chunk

                            elif line.startswith("a2:") and line == 'a2:[{"type":"heartbeat"}]':
                                continue

                            elif line.startswith("a2:"):
                                obj = json.loads(line[3:])
                                images = [
                                    x.get("image")
                                    for x in obj
                                    if isinstance(x, dict) and x.get("image")
                                ]
                                if images:
                                    emitted_anything = True
                                    yield StreamImages(images)

                            elif line.startswith("ad:"):
                                finish = json.loads(line[3:])
                                finish_reason = None
                                usage = None
                                if isinstance(finish, dict):
                                    finish_reason = finish.get("finishReason")
                                    if isinstance(finish.get("usage"), dict):
                                        usage = Usage.from_lmarena(finish["usage"])
                                emitted_anything = True
                                yield StreamFinal(
                                    evaluation_session_id=eval_id,
                                    finish_reason=finish_reason,
                                    usage=usage,
                                )

                            elif line.startswith("a3:"):
                                raise StreamError(f"LMArena stream error: {json.loads(line[3:])}")

                            else:
                                # ignore unknown prefixes (debug only)
                                continue

                break  # success

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log_exc("core:stream_message", e)
                log("[lmarena-client] Context snapshot:")
                log("  model:", model)
                log("  url:", url)
                log("  evaluation_session_id:", eval_id)
                log("  grecaptcha_present:", bool(grecaptcha))

                if emitted_anything:
                    raise

                if attempt + 1 < max_attempts:
                    try:
                        await self._browser.reload_tab()
                    except Exception as re:
                        log_exc("core:reload_tab", re)
                    log(f"[lmarena-client] Retrying stream (attempt {attempt + 2}/{max_attempts})")
                else:
                    raise

    async def send_message(
        self,
        *,
        model: str,
        prompt: str,
        evaluation_session_id: Optional[str] = None,
        create_new: bool = False,
        media: list[tuple[Any, Optional[str]]] | None = None,
        timeout: Optional[int] = None,
    ) -> ChatResult:
        """
        Non-streaming helper: consumes the stream and returns a ChatResult.
        """
        text_parts: list[str] = []
        images: list[str] = []
        final: Optional[StreamFinal] = None

        async for event in self.stream_message(
            model=model,
            prompt=prompt,
            evaluation_session_id=evaluation_session_id,
            create_new=create_new,
            media=media,
            timeout=timeout,
        ):

            if isinstance(event, str):
                text_parts.append(event)
            elif isinstance(event, StreamImages):
                images.extend(event.urls)
            elif isinstance(event, StreamFinal):
                final = event

        eval_id = final.evaluation_session_id if final else (evaluation_session_id or "")
        return ChatResult(
            text="".join(text_parts),
            evaluation_session_id=eval_id,
            finish_reason=final.finish_reason if final else None,
            usage=final.usage if final else None,
            images=images or None,
        )
