from __future__ import annotations


class LMArenaClientError(Exception):
    """Base error for lmarena-client."""


class MissingRequirementsError(LMArenaClientError):
    """A required optional dependency is missing."""


class HTTPError(LMArenaClientError):
    """
    HTTP-shaped error (status/reason/detail) used for surfacing useful upstream messages
    and for server status-code passthrough.
    """

    def __init__(
        self,
        message: str | None = None,
        *,
        status: int | None = None,
        reason: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.status = status
        self.reason = reason
        self.detail = detail

        if message is None:
            base = ""
            if status is not None and reason:
                base = f"{status} {reason}"
            elif status is not None:
                base = str(status)
            elif reason:
                base = reason

            if detail:
                message = f"{base}: {detail}" if base else detail
            else:
                message = base or "HTTP error"

        super().__init__(message)


class AuthError(HTTPError):
    """Authentication/anti-bot related failure."""


class CloudflareError(AuthError):
    """Blocked by anti-bot / Cloudflare / Turnstile."""


class RateLimitError(HTTPError):
    """Rate limit or quota exceeded."""


class HTTPStatusError(HTTPError):
    """Non-2xx HTTP response from LMArena."""


class ModelNotFoundError(LMArenaClientError):
    """Requested model is not available on LMArena."""


class StreamError(LMArenaClientError):
    """LMArena streaming protocol error."""

