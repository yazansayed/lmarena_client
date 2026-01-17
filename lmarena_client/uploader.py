from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Optional

from .browser import BrowserManager
from .config import ClientConfig
from .discovery import Discovery
from .http import StreamSession, ensure_ok
from .images import to_bytes_async, detect_file_type, ensure_filename
from .utils import log, log_exc


class ImageUploader:
    """
    Handles LMArena image upload (generateUploadUrl -> PUT -> getSignedUrl).

    Keeps an optional in-memory cache: md5(image_bytes) -> uploaded descriptor
    """

    def __init__(self, *, config: ClientConfig, browser: BrowserManager, discovery: Discovery) -> None:
        self._config = config
        self._browser = browser
        self._discovery = discovery
        self._cache: dict[str, dict[str, str]] = {}

    async def upload(self, media: list[tuple[Any, Optional[str]]] | None) -> list[dict[str, str]]:
        if not media:
            return []

        await self._browser.ensure_ready()
        await self._discovery.ensure_loaded()

        state = self._discovery.state
        if not state.next_actions.get("generateUploadUrl") or not state.next_actions.get("getSignedUrl"):
            raise RuntimeError("Next.js action IDs not loaded (generateUploadUrl/getSignedUrl).")

        uploaded: list[dict[str, str]] = []
        image_url = self._config.origin.rstrip("/") + self._config.image_path

        for idx, (obj, name) in enumerate(media):
            data = await to_bytes_async(obj)
            h = hashlib.md5(data).hexdigest()

            if self._config.image_cache and h in self._cache:
                uploaded.append(self._cache[h])
                continue

            ext, mime = detect_file_type(data)
            filename = ensure_filename(name, default_stem=f"file-{idx}{ext}")
            # if caller passed "cat.png", keep it; otherwise ensure extension exists
            if "." not in filename and ext:
                filename = filename + ext

            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    http_args = await self._browser.get_http_args()
                    async with StreamSession(
                        headers=http_args.headers,
                        cookies=http_args.cookies,
                        timeout=self._config.upload_timeout_seconds,
                    ) as session:

                        # Step 1: generate upload URL
                        async with session.post(
                            image_url,
                            json=[filename, mime],
                            headers={
                                "accept": "text/x-component",
                                "content-type": "text/plain;charset=UTF-8",
                                "next-action": state.next_actions["generateUploadUrl"],
                                "referer": image_url,
                            },
                        ) as resp:
                            await ensure_ok(resp, context="generateUploadUrl")
                            text = await resp.text()

                        line = next((x for x in text.split("\n") if x.startswith("1:")), "")
                        if not line:
                            raise RuntimeError("Failed to parse generateUploadUrl response (no '1:' line).")
                        chunk = json.loads(line[2:])
                        if not chunk.get("success"):
                            raise RuntimeError(f"generateUploadUrl failed: {chunk}")

                        upload_url = chunk.get("data", {}).get("uploadUrl")
                        key = chunk.get("data", {}).get("key")
                        if not upload_url or not key:
                            raise RuntimeError(f"generateUploadUrl missing fields: {chunk}")

                        # Step 2: PUT bytes
                        async with session.put(
                            upload_url,
                            headers={"content-type": mime},
                            data=data,
                        ) as resp:
                            await ensure_ok(resp, context="upload_put")

                        # Step 3: getSignedUrl
                        async with session.post(
                            image_url,
                            json=[key],
                            headers={
                                "accept": "text/x-component",
                                "content-type": "text/plain;charset=UTF-8",
                                "next-action": state.next_actions["getSignedUrl"],
                                "referer": image_url,
                            },
                        ) as resp:
                            await ensure_ok(resp, context="getSignedUrl")
                            text = await resp.text()

                        line = next((x for x in text.split("\n") if x.startswith("1:")), "")
                        if not line:
                            raise RuntimeError("Failed to parse getSignedUrl response (no '1:' line).")
                        chunk = json.loads(line[2:])
                        if not chunk.get("success"):
                            raise RuntimeError(f"getSignedUrl failed: {chunk}")

                        signed_url = chunk.get("data", {}).get("url")
                        if not signed_url:
                            raise RuntimeError(f"getSignedUrl missing url: {chunk}")

                    descriptor = {"name": key, "contentType": mime, "url": signed_url}
                    self._cache[h] = descriptor
                    uploaded.append(descriptor)
                    log(f"[lmarena-client] Uploaded image: {signed_url}")
                    break

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log_exc("uploader:upload", e)
                    if attempt + 1 < max_attempts:
                        try:
                            await self._browser.reload_tab()
                        except Exception as re:
                            log_exc("uploader:reload_tab", re)
                        log(f"[lmarena-client] Image upload retrying (attempt {attempt + 2}/{max_attempts})")
                    else:
                        raise

        return uploaded
