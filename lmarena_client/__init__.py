from __future__ import annotations

__all__ = [
    "ClientConfig",
    "BrowserConfig",
    "Client",
    "LMArenaClientError",
]

from .config import ClientConfig, BrowserConfig
from .client import Client
from .errors import LMArenaClientError

# Optional server export (only available when `lmarena-client[server]` is installed)
try:  # pragma: no cover
    from .server import create_app  # type: ignore

    __all__.append("create_app")
except Exception:
    pass



