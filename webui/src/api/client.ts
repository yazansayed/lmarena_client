import type { MessageContent } from "../types";

const BASE_URL = window.location.origin;

function extractErrorMessage(obj: any): string | null {
  if (!obj) return null;

  if (typeof obj === "string") return obj;

  // FastAPI shape
  if (typeof obj.detail === "string") return obj.detail;

  // Server/SSE shape
  if (typeof obj.error === "string") return obj.error;
  if (obj.error && typeof obj.error.message === "string") return obj.error.message;

  // Fallbacks
  if (typeof obj.message === "string") return obj.message;
  if (obj.error && typeof obj.error.type === "string") return obj.error.type;

  return null;
}

export interface OpenAIChatMessage {
  role: "user" | "assistant";
  content: MessageContent;
}

export interface ChatCompletionResult {
  text: string;
  evaluationSessionId: string | null;
  images: string[];
}

interface ChatCompletionsRequestBody {
  model: string;
  messages: OpenAIChatMessage[];
  stream?: boolean;
  conversation?: {
    evaluationSessionId: string;
  };
}

/**
 * Fetch available models from /v1/models.
 */
export async function listModels(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/v1/models`, {
    method: "GET",
  });
  if (!res.ok) {
    throw new Error(`Failed to list models: ${res.status} ${res.statusText}`);
  }
  const data = await res.json();
  const models = Array.isArray(data?.data) ? data.data : [];
  return models
    .map((m: any) => (m && typeof m.id === "string" ? m.id : null))
    .filter((id: string | null): id is string => !!id);
}

/**
 * Non-streaming chat completion.
 */
export async function sendChatCompletion(
  model: string,
  messages: OpenAIChatMessage[],
  evaluationSessionId: string | null
): Promise<ChatCompletionResult> {
  const body: ChatCompletionsRequestBody = {
    model,
    messages,
    stream: false,
  };
  if (evaluationSessionId) {
    body.conversation = { evaluationSessionId };
  }

  const res = await fetch(`${BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const raw = await res.text().catch(() => "");
    let parsed: any = null;
    try {
      parsed = raw ? JSON.parse(raw) : null;
    } catch {
      parsed = null;
    }

    const extracted = extractErrorMessage(parsed) || raw.trim();
    const base = `${res.status} ${res.statusText}`.trim();
    const msg = extracted ? `${base}: ${extracted}` : base;

    throw new Error(msg);
  }

  const data = await res.json();

  const errMsg = extractErrorMessage(data);
  if (errMsg) {
    throw new Error(errMsg);
  }

  const choice = Array.isArray(data?.choices) ? data.choices[0] : null;
  const content =
    choice && choice.message && typeof choice.message.content === "string"
      ? choice.message.content
      : "";

  const evalId =
    data?.conversation && typeof data.conversation.evaluationSessionId === "string"
      ? data.conversation.evaluationSessionId
      : evaluationSessionId;

  const images: string[] = Array.isArray(data?.images) ? (data.images as string[]) : [];

  return {
    text: content,
    evaluationSessionId: evalId ?? null,
    images,
  };
}

/**
 * Streaming chat completion via OpenAI-style SSE.
 * Calls onDelta for each text chunk and resolves with the full text + final evaluationSessionId.
 */
export async function sendChatCompletionStream(
  model: string,
  messages: OpenAIChatMessage[],
  evaluationSessionId: string | null,
  onDelta: (delta: string) => void,
  signal?: AbortSignal
): Promise<ChatCompletionResult> {
  const body: ChatCompletionsRequestBody = {
    model,
    messages,
    stream: true,
  };
  if (evaluationSessionId) {
    body.conversation = { evaluationSessionId };
  }

  const res = await fetch(`${BASE_URL}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    const raw = await res.text().catch(() => "");
    let parsed: any = null;
    try {
      parsed = raw ? JSON.parse(raw) : null;
    } catch {
      parsed = null;
    }

    const extracted = extractErrorMessage(parsed) || raw.trim();
    const base = `${res.status} ${res.statusText}`.trim();
    const msg = extracted ? `${base}: ${extracted}` : base;

    throw new Error(msg);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");

  let buffer = "";
  let done = false;
  let fullText = "";
  let finalEvalId: string | null = evaluationSessionId ?? null;
  let images: string[] = [];

  while (!done) {
    const { value, done: readerDone } = await reader.read();
    done = readerDone;

    if (value) {
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, idx).trimEnd();
        buffer = buffer.slice(idx + 1);

        if (!line.startsWith("data:")) {
          continue;
        }

        const payload = line.slice(5).trim();
        if (!payload || payload === "[DONE]") {
          continue;
        }

        let parsed: any;
        try {
          parsed = JSON.parse(payload);
        } catch {
          continue;
        }

        // Check for error in streamed chunk
        if (parsed?.error) {
          const errMsg = extractErrorMessage(parsed) || "Unknown error from server";
          throw new Error(errMsg);
        }


        const choice =

          Array.isArray(parsed?.choices) && parsed.choices.length > 0
            ? parsed.choices[0]
            : null;
        const deltaContent =
          choice && choice.delta && typeof choice.delta.content === "string"
            ? choice.delta.content
            : "";

        if (deltaContent) {
          fullText += deltaContent;
          onDelta(deltaContent);
        }

        if (
          parsed?.conversation &&
          typeof parsed.conversation.evaluationSessionId === "string"
        ) {
          finalEvalId = parsed.conversation.evaluationSessionId;
        }

        if (Array.isArray(parsed?.images)) {
          images = parsed.images as string[];
        }
      }
    }
  }

  return {
    text: fullText,
    evaluationSessionId: finalEvalId,
    images,
  };
}
