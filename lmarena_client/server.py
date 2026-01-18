from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from .client import Client
from .config import ClientConfig
from .errors import MissingRequirementsError
from .stream import StreamFinal, StreamImages, Usage
from .utils import log

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as e:  # pragma: no cover
    raise MissingRequirementsError('Install server extras: pip install "lmarena-client[server]"') from e

from .openai_types import (
    ChatCompletionsRequest,
    ChatCompletionsResponse,
    ChatCompletionsStreamChunk,
    ChatChoice,
    ChatMessage,
    ListModelsResponse,
    ModelCard,
    StreamChoice,
    Delta,
)


def _extract_last_user_text_and_images(messages: list[dict[str, Any]]) -> tuple[str, list[tuple[Any, Optional[str]]]]:
    """
    Extract:
    - last user text (concatenate text parts if content is list)
    - last user images (from image_url parts)
    Ignores all roles except user.
    """
    last_user: Optional[dict[str, Any]] = None
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            last_user = m
            break

    if not last_user:
        return "", []

    content = last_user.get("content", "")
    text_parts: list[str] = []
    images: list[tuple[Any, Optional[str]]] = []

    if isinstance(content, str):
        return content, images

    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text" and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
            elif ptype == "image_url":
                image_url = part.get("image_url") or {}
                url = image_url.get("url")
                if isinstance(url, str) and url:
                    images.append((url, None))

    return "".join(text_parts).strip(), images


def _usage_to_dict(usage: Optional[Usage]) -> Optional[dict[str, Any]]:
    if not usage:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def create_app(config: Optional[ClientConfig] = None) -> FastAPI:
    """
    OpenAI-ish FastAPI server.

    Endpoints:
    - GET /v1/models
    - POST /v1/chat/completions

    Notes:
    - conversation continuation via vendor extension (stateless):
        request.conversation = {"evaluationSessionId": "..."}
    - if no evaluationSessionId is provided, a new conversation is created.
    - ignores non-user roles; only uses last user message content + images.
    """
    app = FastAPI(title="lmarena-client", version="0.1.0")
    cfg = config or ClientConfig.from_env()

    # Static WebUI (built frontend) served from /ui
    static_dir = Path(__file__).resolve().parent / "webui_dist"

    if static_dir.exists():
        # Serve built assets (Vite-style) under /ui/assets
        app.mount(
            "/ui/assets",
            StaticFiles(directory=static_dir / "assets", check_dir=False),
            name="ui_assets",
        )

        # SPA entry + fallback for any /ui/* path
        @app.get("/ui", response_class=HTMLResponse)
        @app.get("/ui/{path:path}", response_class=HTMLResponse)
        async def serve_ui(path: str = "") -> HTMLResponse:  # type: ignore[unused-argument]
            index_file = static_dir / "index.html"
            if not index_file.is_file():
                return HTMLResponse(
                    "<h1>WebUI assets not found</h1><p>Expected index.html under webui_dist.</p>",
                    status_code=500,
                )
            return HTMLResponse(index_file.read_text(encoding="utf-8"))
    else:
        # Graceful message when assets are missing
        @app.get("/ui", response_class=HTMLResponse)
        async def ui_missing() -> HTMLResponse:
            return HTMLResponse(
                "<h1>WebUI assets not found</h1>"
                "<p>No webui_dist directory detected. "
                "Run the frontend build to generate the WebUI assets.</p>",
                status_code=500,
            )


    @app.on_event("startup")
    async def _startup() -> None:
        app.state.client = Client(cfg)
        try:
            await app.state.client.bootstrap()
            log("[lmarena-client] Server bootstrap complete.")
        except Exception as e:
            log("[lmarena-client] Server bootstrap failed:", type(e).__name__, str(e))
            if cfg.fail_fast_bootstrap:
                raise

    @app.get("/v1/models")
    async def list_models() -> JSONResponse:
        client: Client = app.state.client
        try:
            models = await client.list_models()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        payload = ListModelsResponse(data=[ModelCard(id=m) for m in models])
        return JSONResponse(payload.model_dump())

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionsRequest) -> Any:
        client: Client = app.state.client

        # Determine evaluationSessionId (stateless)
        eval_id: Optional[str] = None
        if req.conversation and req.conversation.evaluationSessionId:
            eval_id = req.conversation.evaluationSessionId

        prompt, images = _extract_last_user_text_and_images([m.model_dump() for m in req.messages])

        if not req.stream:
            try:
                result = await client._core.send_message(
                    model=req.model,
                    prompt=prompt,
                    evaluation_session_id=eval_id,
                    create_new=(eval_id is None),
                    media=images,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

            payload = ChatCompletionsResponse(
                id=f"chatcmpl-{uuid.uuid4().hex}",
                created=int(time.time()),
                model=req.model or client._core.discovery.state.default_model,
                choices=[
                    ChatChoice(
                        index=0,
                        message=ChatMessage(role="assistant", content=result.text),
                        finish_reason=result.finish_reason,
                    )
                ],
                conversation={"evaluationSessionId": result.evaluation_session_id},
                images=result.images,
                usage=_usage_to_dict(result.usage),
            )
            return JSONResponse(payload.model_dump(exclude_none=True))

        # streaming
        async def sse() -> AsyncIterator[bytes]:
            chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
            created = int(time.time())
            model = req.model or client._core.discovery.state.default_model

            # Initial role chunk (common OpenAI pattern)
            first = ChatCompletionsStreamChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[StreamChoice(index=0, delta=Delta(role="assistant"))],
            )
            yield f"data: {json.dumps(first.model_dump(exclude_none=True))}\n\n".encode()

            images_out: list[str] = []

            try:
                async for event in client._core.stream_message(
                    model=req.model,
                    prompt=prompt,
                    evaluation_session_id=eval_id,
                    create_new=(eval_id is None),
                    media=images,
                ):
                    if isinstance(event, str) and event:
                        delta_chunk = ChatCompletionsStreamChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(index=0, delta=Delta(content=event))],
                        )
                        yield f"data: {json.dumps(delta_chunk.model_dump(exclude_none=True))}\n\n".encode()

                    elif isinstance(event, StreamImages):
                        images_out.extend(event.urls)

                    elif isinstance(event, StreamFinal):
                        final_chunk = ChatCompletionsStreamChunk(
                            id=chunk_id,
                            created=created,
                            model=model,
                            choices=[StreamChoice(index=0, delta=Delta(), finish_reason=event.finish_reason)],
                            conversation={"evaluationSessionId": event.evaluation_session_id},
                            images=images_out or None,
                            usage=_usage_to_dict(event.usage),
                        )
                        yield f"data: {json.dumps(final_chunk.model_dump(exclude_none=True))}\n\n".encode()
                        break

            except Exception as e:
                err = {"error": {"message": str(e), "type": type(e).__name__}}
                yield f"data: {json.dumps(err)}\n\n".encode()

            yield b"data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    return app


# Convenience for: `uvicorn lmarena_client.server:app`
app = create_app()


