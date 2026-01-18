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


def _extract_error_detail_from_body(body: str) -> Optional[str]:
    b = (body or "").strip()
    if not b:
        return None

    try:
        data: Any = json.loads(b)
    except Exception:
        return None

    # Common shapes:
    # - {"error": "Message ..."}
    # - {"error": {"message": "..."}}
    # - {"detail": "..."}  (FastAPI)
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
        if isinstance(err, dict):
            for k in ("message", "detail", "error"):
                v = err.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()

        for k in ("detail", "message"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    if isinstance(data, str) and data.strip():
        return data.strip()

    return None


async def ensure_ok(response: ClientResponse, *, context: str = "") -> None:
    ok = getattr(response, "ok", None)
    if ok is None:
        ok = 200 <= int(getattr(response, "status", 0)) < 300
    if ok:
        return

    status = int(getattr(response, "status", 0))
    reason = getattr(response, "reason", "") or ""
    url = str(getattr(response, "url", ""))

    body = await read_response_text_safe(response)
    detail = _extract_error_detail_from_body(body)

    log("[lmarena-client] HTTP ERROR")
    log("  context:", context)
    log("  url:", url)
    log("  status:", status, reason)
    log("  body:\n", body)

    if status in (429, 402):
        raise RateLimitError(status=status, reason=reason, detail=detail)
    if status == 401:
        raise AuthError(status=status, reason=reason, detail=detail)
    if status == 403 and (is_cloudflare_html(body) or looks_like_recaptcha_failure(body)):
        raise CloudflareError(status=403, reason=reason or "Forbidden", detail="blocked by anti-bot / recaptcha failure")
    if status == 403:
        raise AuthError(status=403, reason=reason or "Forbidden", detail=detail)
    raise HTTPStatusError(status=status, reason=reason or "HTTP error", detail=detail)

