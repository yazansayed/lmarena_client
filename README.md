# lmarena-client

Standalone Python package extracted from `g4f`'s LMArena provider.

Goals:
- Async client library for `lmarena.ai`
- Optional FastAPI server with OpenAI-ish endpoints:
  - `GET /v1/models`
  - `POST /v1/chat/completions`
- Uses **nodriver** for auth + reCAPTCHA
- Uses **aiohttp** for HTTP



# lmarena-client — Usage

`lmarena-client` is a standalone Python 3.11+ package that:
- boots a real Chromium-based browser via **nodriver** to pass anti-bot + generate reCAPTCHA tokens,
- uses **aiohttp** for the actual API calls to `lmarena.ai`,
- exposes:
  1) a **Python async client library**, and
  2) an optional **FastAPI server** with OpenAI-ish endpoints:
     - `GET /v1/models`
     - `POST /v1/chat/completions` (supports streaming)

Key limitation:
- We **ignore multi-turn roles/history** from the request and only send **the last user message** (LMArena keeps history server-side per `evaluationSessionId`).

---

## 1) Install

From your repo folder:

### Library only
```bash
pip install -e .
```

### With server extras
```bash
pip install -e ".[server]"
```

---

## 2) Configure the browser (nodriver)

By default, the package runs **headful** (GUI browser) for better reliability with Turnstile/reCAPTCHA. You can override settings using env vars:

### Environment variables

| Variable | Meaning |
|---|---|
| `LM_ARENA_BROWSER_EXECUTABLE_PATH` | Path to Chrome/Brave/Chromium executable |
| `LM_ARENA_BROWSER_USER_DATA_DIR` | User data dir (persistent profile) |
| `LM_ARENA_BROWSER_PROFILE_DIRECTORY` | Profile directory name (e.g. `"Default"`) |
| `LM_ARENA_BROWSER_INCOGNITO` | `1/true/yes` to run incognito |
| `LM_ARENA_BROWSER_HEADLESS` | `1/true/yes` to run headless (`--headless=new`) |
| `LM_ARENA_HOST` | Server host (when running server) |
| `LM_ARENA_PORT` | Server port (when running server) |

Example (Windows PowerShell):
```powershell
$env:LM_ARENA_BROWSER_EXECUTABLE_PATH="C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
$env:LM_ARENA_BROWSER_USER_DATA_DIR="C:\Users\<you>\AppData\Local\BraveSoftware\Brave-Browser\User Data"
$env:LM_ARENA_BROWSER_PROFILE_DIRECTORY="Default"
$env:LM_ARENA_BROWSER_HEADLESS="0"
```

---

## 3) Run the FastAPI server

### Option A: run via module
```bash
python -m lmarena_client
```

### Option B: run via console script
```bash
lmarena-server
```

By default it binds to:
- `127.0.0.1:1337`

Override:
```bash
LM_ARENA_HOST=0.0.0.0 LM_ARENA_PORT=8000 lmarena-server
```

### Startup behavior
On server startup it:
1) boots the browser and performs the “bootstrap” flow (cookies + turnstile assist + grecaptcha readiness),
2) loads live models and Next.js action IDs needed for image upload.

---

## 4) Server API usage

### 4.1 `GET /v1/models`
Returns a list of models (OpenAI-ish shape):
```bash
curl http://127.0.0.1:1337/v1/models
```

### 4.2 `POST /v1/chat/completions` (non-stream)
Minimal request:
```bash
curl -X POST http://127.0.0.1:1337/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-3-pro\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}"
```

Response includes a vendor extension:
- `conversation.evaluationSessionId` (this is the **real resume key**)

Example response:
``` json
{
    "id": "chatcmpl-f0ea528f7853432d80e2ff2c9b718b9d",
    "object": "chat.completion",
    "created": 1768644722,
    "model": "gemini-3-pro",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello! How can I help you today?"
            },
            "finish_reason": "stop"
        }
    ],
    "conversation": {
        "evaluationSessionId": "019bcb70-a714-7d9b-bb79-e2ae55270f67"
    }
}
```


### 4.3 Conversation continuation (resume)
To continue a chat, pass:
```json
"conversation": { "evaluationSessionId": "..." }
```

Example:
```bash
curl -X POST http://127.0.0.1:1337/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-3-pro\",\"conversation\":{\"evaluationSessionId\":\"<ID>\"},\"messages\":[{\"role\":\"user\",\"content\":\"continue\"}]}"
```

### 4.4 Streaming (`stream: true`)
This endpoint returns `text/event-stream` with OpenAI-style `data: ...` chunks and a final `data: [DONE]`.

Example:
```bash
curl -N -X POST http://127.0.0.1:1337/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"gemini-3-pro\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}"
```

---

## 5) Sending images (vision input)

The server accepts OpenAI-style content parts in the **last user** message:

```json
{
  "model": "gemini-3-pro",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "text", "text": "What is in this image?"},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,...."}}
    ]
  }]
}
```

Notes:
- The image must be a valid `data:` URI, or an `http(s)` URL.
- Images are uploaded to LMArena using Next.js actions (`generateUploadUrl` / `getSignedUrl`) and then included as `experimental_attachments`.

---

## 6) Python client library usage

### Basic usage
```python
import asyncio
from lmarena_client import Client

async def main():
    client = Client()
    await client.bootstrap()

    models = await client.list_models()
    print("Models:", models)

    chat = await client.chats.create(model='gemini-3-pro')

    # non-stream
    r1 = await chat.send("1+1=", stream=False)
    print("Reply:", r1.text)
    print("Chat ID (evaluationSessionId):", r1.evaluation_session_id)

    # resume (explicitly)
    chat2 = await client.chats.resume(model='gemini-3-pro', chat_id=r1.evaluation_session_id)
    r2 = await chat2.send("add 5 to the result", stream=False)
    print("Reply2:", r2.text)

asyncio.run(main())
```

### Streaming usage
```python
import asyncio
from lmarena_client import Client

async def stream_example():
    client = Client()
    await client.bootstrap()
    models = await client.list_models()
    chat = await client.chats.create(model='gemini-3-pro')

    stream = await chat.send("write a short article about global warming", stream=True)
    async for delta in stream:
        print(delta, end="", flush=True) #not delta.content, delta is str

    # We can get the id after stream completes, this is the id to persist/use for resume
    print("\nChat eval id (post):", chat.conversation.evaluation_session_id)
asyncio.run(stream_example())
```

### Sending images from Python
`ChatSession.send(..., images=...)` expects:
```python
images=[(image_data, filename_or_none), ...]
```
Where `image_data` can be:
- bytes
- `data:image/...;base64,...`
- path (`"C:/path/to/image.png"`)
- file-like object
- `http(s)://...` URL (fetched with aiohttp)

Example:
```python
r = await chat.send(
    "What's in this image?",
    images=[("data:image/png;base64,....", "img.png")],
    stream=False,
)
print(r.text)
```

---

## 7) Operational notes / limitations

- **Single-user / low-QPS design**: nodriver operations are serialized behind a lock. This is intentional for simplicity.
- **History handling**: We do *not* send full message history to LMArena. LMArena maintains history server-side per `evaluationSessionId`.
- **Reliability**: headful mode is default because Turnstile/reCAPTCHA is often more reliable than headless. You can enable headless via `LM_ARENA_BROWSER_HEADLESS=1`.
- **Persistence**: the library does not store chats. If you want persistence, store the returned `evaluationSessionId` yourself and resume later.

