from __future__ import annotations

import os
import sys

from .errors import MissingRequirementsError

try:
    import uvicorn
except ImportError as e:  # pragma: no cover
    raise MissingRequirementsError('Install server extras: pip install "lmarena-client[server]"') from e


def main() -> None:
    host = os.environ.get("LM_ARENA_HOST", "127.0.0.1")
    port = int(os.environ.get("LM_ARENA_PORT", "1337"))
    uvicorn.run("lmarena_client.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
