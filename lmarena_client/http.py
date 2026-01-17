from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

from aiohttp import BaseConnector, ClientResponse, ClientSession, ClientTimeout

from .errors import CloudflareError, HTTPStatusError, RateLimitError, AuthError
from .utils import (
    is_cloudflare_html,
    looks_like_recaptcha_failure,
    read_response_text_safe,
    log,
)


class StreamResponse(ClientResponse):
    async def iter_lines(self) -> AsyncIterator[bytes]:
        async for line in self.content:
            yield line.rstrip(b"\r\n")


class StreamSession:
    """
    Small aiohttp wrapper similar to g4f's StreamSession, but kept local.
    """

    def __init__(
        self,
        *,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        timeout: Optional[int] = None,
        connector: Optional[BaseConnector] = None,
    ) -> None:
        if timeout is not None:
            timeout_obj = ClientTimeout(total=timeout)
        else:
            timeout_obj = None

        self._session = ClientSession(
            headers=headers or {},
            cookies=cookies or {},
            timeout=timeout_obj,
            connector=connector,
            response_class=StreamResponse,
        )

    async def __aenter__(self) -> ClientSession:
        return self._session

    async def __aexit__(self, *args, **kwargs) -> None:
        await self._session.close()


async def ensure_ok(response: ClientResponse, *, context: str = "") -> None:
    ok = getattr(response, "ok", None)
    if ok is None:
        ok = 200 <= int(getattr(response, "status", 0)) < 300
    if ok:
        return

    status = int(getattr(response, "status", 0))
    reason = getattr(response, "reason", "")
    url = str(getattr(response, "url", ""))

    body = await read_response_text_safe(response)

    log("[lmarena-client] HTTP ERROR")
    log("  context:", context)
    log("  url:", url)
    log("  status:", status, reason)
    log("  body:\n", body)

    if status in (429, 402):
        raise RateLimitError(f"HTTP {status}: {reason}")
    if status == 401:
        raise AuthError(f"HTTP {status}: {reason}")
    if status == 403 and (is_cloudflare_html(body) or looks_like_recaptcha_failure(body)):
        raise CloudflareError("HTTP 403: blocked by anti-bot / recaptcha failure")
    if status == 403:
        raise AuthError(f"HTTP {status}: Forbidden")
    raise HTTPStatusError(f"HTTP {status}: {reason or 'HTTP error'}")
