# Technical Breakdown Report

### Project Overview
**lmarena-client** is a Python-based interface for interacting with `lmarena.ai` (Large Model Arena). It functions as both a standalone asynchronous Python library and a local REST API server compatible with OpenAI's format (`/v1/chat/completions`).

### Key Architecture Components

1.  **Browser Automation (The "Driver"):**
    *   **Technology:** Uses `nodriver` (a Python wrapper for Chrome DevTools Protocol).
    *   **Purpose:** LMArena is heavily protected by Cloudflare Turnstile and reCAPTCHA. The client boots a real Chromium-based browser to establish a valid session, solve CAPTCHAs, and generate `grecaptcha` tokens.
    *   **Concurrency:** Browser operations run on a dedicated background thread with its own asyncio loop to prevent blocking the main application flow.

2.  **API Discovery & Reverse Engineering:**
    *   **Mechanism:** The client does not use a documented public API. Instead, it parses the server-rendered HTML and Next.js JavaScript chunks (`_next/static/...`) to discover:
        *   Available models (`initialModels`).
        *   Next.js Server Action IDs (`generateUploadUrl`, `getSignedUrl`) required for file uploads.
    *   **Data Transport:** Actual chat messages are sent via standard HTTP POST requests using `aiohttp`, utilizing cookies and tokens extracted from the browser session.

3.  **Server Layer:**
    *   **Technology:** FastAPI with Uvicorn.
    *   **Endpoints:** Exposes OpenAI-compatible endpoints (`GET /v1/models`, `POST /v1/chat/completions`).
    *   **State:** The server is largely stateless regarding chat history. It passes the `evaluationSessionId` to the client to maintain context on LMArena's side, but it processes only the *last* user message in a request.

4.  **Frontend (WebUI):**
    *   **Technology:** React, Vite, TypeScript, Tailwind CSS.
    *   **State Management:** `zustand` for in-memory state, `dexie` (IndexedDB) for persistent local storage of chat history.
    *   **Communication:** The frontend talks to the local Python FastAPI server, treating it as an OpenAI-compatible backend.

### Critical Workflows
*   **Bootstrapping:** On startup, the `BrowserManager` launches Chrome, navigates to the arena, attempts to click "Accept Cookies" and Turnstile widgets, and waits for specific authentication cookies (`arena-auth-prod`).
*   **Image Upload:** Images are processed in three steps: (1) Request upload URL via Next.js action, (2) PUT binary data to S3/GCS, (3) Confirm upload via Next.js action to get a signed URL, which is then attached to the chat message.

---

# File Summary Report

Use the following summaries to determine which files are relevant for specific development or debugging tasks.

## Backend (Python)

| File Path | Description | Relevance Keywords |
| :--- | :--- | :--- |
| `README.md` | General documentation, installation steps, usage examples for both library and server modes, and environment variable configuration. | Documentation, Installation, Usage, Env Vars |
| `config.yaml` | Default configuration file defining browser paths, profiles, timeouts, and headless modes. | Configuration, Settings, Defaults |
| `lmarena_client/__init__.py` | Package initialization. Exports `Client`, `ClientConfig`, and optionally `create_app` if server extras are installed. | Exports, Package Init |
| `lmarena_client/__main__.py` | Entry point for the console script. Launches the Uvicorn/FastAPI server based on environment variables. | Entry Point, Startup, CLI |
| `lmarena_client/browser.py` | **Core Component.** Manages the `nodriver` browser instance. Handles thread/loop management, navigation, cookie extraction, Turnstile clicking, and `grecaptcha` token generation. | Browser, Nodriver, Cookies, CAPTZXCHA, Threading |
| `lmarena_client/client.py` | High-level library interface. Defines the `Client`, `ChatsAPI`, and `ChatSession` classes used by Python scripts to interact with the arena. | Public API, Library Interface, Session Management |
| `lmarena_client/config.py` | Logic for loading configuration. Merges defaults, `config.yaml`, and environment variables. Defines `ClientConfig` and `BrowserConfig` data classes. | Config Parsing, Environment Variables |
| `lmarena_client/core.py` | **Business Logic Orchestrator.** Connects the browser, discovery module, and HTTP layer. Handles message sending, streaming response parsing, and error handling. | Logic, Orchestration, Streaming, Messaging |
| `lmarena_client/discovery.py` | **Scraping Logic.** Parses HTML and fetched JS files to extract dynamic Next.js Server Action IDs and the list of available models. | Scraping, Parsing, Next.js, Action IDs, Models |
| `lmarena_client/errors.py` | Custom exception classes for the project (e.g., `AuthError`, `ModelNotFoundError`, `CloudflareError`). | Exceptions, Error Handling |
| `lmarena_client/http.py` | Wrapper around `aiohttp`. Handles session creation and standardizes HTTP error raising (e.g., converting 403s to `CloudflareError`). | HTTP, Requests, Aiohttp, Network |
| `lmarena_client/images.py` | Utilities for handling image inputs. Detects MIME types, validates file headers, and converts various inputs (URLs, paths, base64) into bytes. | Images, Base64, MIME Types, File Handling |
| `lmarena_client/openai_types.py` | Pydantic models defining the schema for OpenAI-compatible requests and responses. | OpenAI API, Schema, Pydantic, Types |
| `lmarena_client/server.py` | **FastAPI Server.** Imjhplements the `/v1/` endpoints. Maps HTTP requests to the `Client` logic and serves the static WebUI assets. | Server, API, FastAPI, Routes, WebUI Serving |
| `lmarena_client/stream.py` | Data classes representing the internal streaming events (text deltas, images, final usage stats). | Streaming, Data Classes |
| `lmarena_client/uploader.py` | Logic for uploading images to LMArena. Executes the 3-step Next.js upload protocol (Generate URL -> PUT -> Sign URL). | Upload, Images, Next.js Actions |
| `lmarena_client/utils.py` | Helper functions including UUIDv7 generation, logging hooks, and helper functions to detect Cloudflare block pages. | Helpers, Utilities, UUID, Logging |
| `pyproject.toml` | Build configuration, dependency listing, and project metadata. | Dependencies, Build, Metadata |

## Frontend (React/TypeScript)

| File Path | Description | Relevance Keywords |
| :--- | :--- | :--- |
| `webui/src/App.tsx` | Main React component. Handles initial data loading (models, settings) and high-level layout structure. | Frontend Entry, Layout, Initialization |
| `webui/src/api/client.ts` | Frontend API client. Functions to fetch models and send chat requests (streaming and non-streaming) to the Python backend. | Frontend API, Fetch, Networking |
| `webui/src/components/ChatView.tsx` | **Main UI Component.** Renders the chat interface, handles user input, file attachments, and displays the message stream. | Chat UI, Input, rendering, Message List |
| `webui/src/components/MarkdownMessage.tsx` | Component for rendering Markdown content, including code blocks with syntax highlighting and image attachments. | Markdown, Rendering, Code Blocks |
| `webui/src/components/SettingsDrawer.tsx` | UI for the settings menu. Handles theme switching, export/import of chat history, and max chat limits. | Settings, UI, Export/Import |
| `webui/src/components/Sidebar.tsx` | Sidebar component listing chat history. Handles creating new chats, deleting chats, and clearing history. | Sidebar, History, Navigation |
| `webui/src/db.ts` | Database configuration using `Dexie` (IndexedDB wrapper).DSA Defines schemas for storing chats and messages locally in the browser. | Database, IndexedDB, Storage, Schema |
| `webui/src/store/chats.ts` | Zustand store for managing chat state (current chat, message history, CRUD operations on local DB). | State Management, Chats, Zustand |
| `webui/src/store/settings.ts` | Zustand store for managing application settings (theme, streaming preference). | State Management, Settings, Zustand |
| `webui/vite.config.ts` | Vite configuration. Sets up the proxy to the Python backend (`/v1`) during dev and defines build output paths. | Build, Configuration, Proxy |