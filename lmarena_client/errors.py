from __future__ import annotations


class LMArenaClientError(Exception):
    """Base error for lmarena-client."""


class MissingRequirementsError(LMArenaClientError):
    """A required optional dependency is missing."""


class AuthError(LMArenaClientError):
    """Authentication/anti-bot related failure."""


class CloudflareError(AuthError):
    """Blocked by anti-bot / Cloudflare / Turnstile."""


class RateLimitError(LMArenaClientError):
    """Rate limit or quota exceeded."""


class HTTPStatusError(LMArenaClientError):
    """Non-2xx HTTP response from LMArena."""


class ModelNotFoundError(LMArenaClientError):
    """Requested model is not available on LMArena."""


class StreamError(LMArenaClientError):
    """LMArena streaming protocol error."""
