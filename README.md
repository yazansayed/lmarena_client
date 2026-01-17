# lmarena-client

Standalone Python package extracted from `g4f`'s LMArena provider.

Goals:
- Async client library for `lmarena.ai`
- Optional FastAPI server with OpenAI-ish endpoints:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- Uses **nodriver** for auth + reCAPTCHA
- Uses **aiohttp** for HTTP (no curl_cffi)

## Install

Library only:
```bash
pip install -e .
