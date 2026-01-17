# lmarena-client — Usage Report

`lmarena-client` is a standalone Python 3.11+ package that:
- boots a real Chromium-based browser via **nodriver** to pass anti-bot + generate reCAPTCHA tokens,
- uses **aiohttp** for the actual API calls to `lmarena.ai`,
- exposes:
  1) a **Python async client library**, and
  2) an optional **FastAPI server** with OpenAI-ish endpoints:
     - `GET /v1/models`
     - `POST /v1/chat/completions` (supports streaming)

Key limitation (by design, matching LMArena behavior):
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
curl -X POST http://127.0.0.1:1337/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"gemini-3-pro\",\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}"
```

Response includes a vendor extension:
- `conversation.evaluationSessionId` (this is the **real resume key**)

Example response:
``` json
{
    "id": "chatcmpl-6ef5ec3a0ee24f3492c42bd51e5ee100",
    "object": "chat.completion",
    "created": 1768643732,
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
        "evaluationSessionId": "019bcb61-8cf4-7457-99b9-17de827bbd63"
    },
    "conversation_id": "cbd2e590-d5fb-46f1-aaac-52c93fff603e"
}
```


### 4.3 Conversation continuation (resume)
To continue a chat, pass:
```json
"conversation": { "evaluationSessionId": "..." }
```

Example:
```bash
curl -X POST http://127.0.0.1:1337/v1/chat/completions ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"gemini-3-pro\",\"conversation\":{\"evaluationSessionId\":\"<ID>\"},\"messages\":[{\"role\":\"user\",\"content\":\"continue\"}]}"
```

### 4.4 Server-side convenience: `conversation_id`
The server also maintains an **in-memory** mapping:
- `conversation_id -> evaluationSessionId`

So you can pass `conversation_id` instead of `conversation`:
```json
"conversation_id": "..."
```

Note:
- This mapping is **not persisted** and will reset on server restart.


### 4.5 Streaming (`stream: true`)
This endpoint returns `text/event-stream` with OpenAI-style `data: ...` chunks and a final `data: [DONE]`.

Example:
```bash
curl -N -X POST http://127.0.0.1:1337/v1/chat/completions ^
  -H "Content-Type: application/json" ^
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

    chat = await client.chats.create(model=models[0])

    # non-stream
    r1 = await chat.send("hello", stream=False)
    print("Reply:", r1.text)
    print("Chat ID (evaluationSessionId):", r1.evaluation_session_id)

    # resume (explicitly)
    chat2 = await client.chats.resume(model=models[0], chat_id=r1.evaluation_session_id)
    r2 = await chat2.send("continue please", stream=False)
    print("Reply2:", r2.text)

asyncio.run(main())
```

### Streaming usage
```python
async def stream_example():
    client = Client()
    await client.bootstrap()
    models = await client.list_models()
    chat = await client.chats.create(model=models[0])

    stream = await chat.send("hello", stream=True)
    async for delta in stream:
        print(delta, end="", flush=True)
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

If you want, I can add a short “Troubleshooting” section (common bootstrap failures, missing cookies, nodriver setup issues) tailored to your environment.