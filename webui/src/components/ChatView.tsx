import React, { useMemo, useState } from "react";
import { useChatStore } from "../store/chats";
import { useSettingsStore } from "../store/settings";
import type { Message, MessageContent, MessagePartImageUrl, MessagePartText } from "../types";
import { sendChatCompletion, sendChatCompletionStream } from "../api/client";
import { MarkdownMessage } from "./MarkdownMessage";
import { cn } from "../lib/cn";
import { Copy, Image as ImageIcon, Loader2 } from "lucide-react";
import { newId } from "../lib/id";

interface ChatViewProps {
  models: string[];
  modelsLoading: boolean;
  modelsError: string | null;
}

interface PendingImage {
  id: string;
  dataUrl: string;
}

function extractText(content: MessageContent): string {
  if (typeof content === "string") return content;
  const parts: string[] = [];
  for (const p of content) {
    if ((p as MessagePartText).type === "text") {
      parts.push((p as MessagePartText).text);
    }
  }
  return parts.join("\n\n");
}

export const ChatView: React.FC<ChatViewProps> = ({
  models,
  modelsLoading,
  modelsError,
}) => {
  const {
    chats,
    activeChatId,
    getMessagesForChat,
    addMessage,
    createChat,
    updateChat,
  } = useChatStore();
  const { settings } = useSettingsStore();

  const [input, setInput] = useState("");
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [sending, setSending] = useState(false);
  const [streamingText, setStreamingText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const activeChat = useMemo(
    () => chats.find((c) => c.id === activeChatId) ?? null,
    [chats, activeChatId]
  );

  const messages = getMessagesForChat(activeChatId);

  const selectedModel: string | null = useMemo(() => {
    if (activeChat?.model) return activeChat.model;
    if (models.length > 0) return models[0];
    return null;
  }, [activeChat?.model, models]);

  function handleModelChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (!activeChat) return;
    updateChat(activeChat.id, { model: e.target.value });
  }

  async function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const newImgs: PendingImage[] = [];
    for (const file of Array.from(files)) {
      const id = newId();
      const dataUrl = await readFileAsDataUrl(file);
      newImgs.push({ id, dataUrl });
    }
    setPendingImages((prev) => [...prev, ...newImgs]);
    e.target.value = "";
  }

  function handleRemoveImage(id: string) {
    setPendingImages((prev) => prev.filter((img) => img.id !== id));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (sending) return;
    if (!selectedModel) {
      setError("No model available.");
      return;
    }
    const trimmed = input.trim();
    if (!trimmed && pendingImages.length === 0) {
      return;
    }

    setError(null);
    setSending(true);
    setStreamingText("");

    try {
      let chat = activeChat;
      if (!chat) {
        chat = await createChat({ model: selectedModel });
      } else if (!chat.model) {
        await updateChat(chat.id, { model: selectedModel });
        chat = { ...chat, model: selectedModel };
      }

      const userContent: MessageContent =
        pendingImages.length === 0
          ? trimmed
          : buildContentWithImages(trimmed, pendingImages.map((p) => p.dataUrl));

      // message list for API: existing messages + new user message
      const existingMessages = getMessagesForChat(chat.id);
      const payloadMessages = [
        ...existingMessages.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        {
          role: "user" as const,
          content: userContent,
        },
      ];

      // Persist user message immediately
      await addMessage({
        chatId: chat.id,
        role: "user",
        content: userContent,
      });

      // Update title on first message
      if (!chat.title || chat.title === "New chat") {
        const preview = trimmed || "Image chat";
        const title =
          preview.length > 60 ? preview.slice(0, 57).trimEnd() + "..." : preview;
        await updateChat(chat.id, { title });
      }

      const useStream = settings.streaming;

      if (!useStream) {
        const result = await sendChatCompletion(
          selectedModel,
          payloadMessages,
          chat.evaluationSessionId
        );

        const assistantContent = buildAssistantContent(
          result.text,
          result.images
        );

        await addMessage({
          chatId: chat.id,
          role: "assistant",
          content: assistantContent,
        });

        if (result.evaluationSessionId && result.evaluationSessionId !== chat.evaluationSessionId) {
          await updateChat(chat.id, {
            evaluationSessionId: result.evaluationSessionId,
          });
        }
      } else {
        const controller = new AbortController();
        setStreamingText("");

        const resultPromise = sendChatCompletionStream(
          selectedModel,
          payloadMessages,
          chat.evaluationSessionId,
          (delta) => {
            setStreamingText((prev) => prev + delta);
          },
          controller.signal
        );

        const result = await resultPromise;

        const assistantContent = buildAssistantContent(
          result.text,
          result.images
        );

        await addMessage({
          chatId: chat.id,
          role: "assistant",
          content: assistantContent,
        });

        if (result.evaluationSessionId && result.evaluationSessionId !== chat.evaluationSessionId) {
          await updateChat(chat.id, {
            evaluationSessionId: result.evaluationSessionId,
          });
        }
      }

      setInput("");
      setPendingImages([]);
      setStreamingText("");
    } catch (e: any) {
      console.error("Chat error", e);
      setError(e instanceof Error ? e.message : "Failed to send message.");
      setStreamingText("");
    } finally {
      setSending(false);
    }
  }

  async function handleCopyEvalId() {
    if (!activeChat?.evaluationSessionId) return;
    try {
      await navigator.clipboard.writeText(activeChat.evaluationSessionId);
    } catch (e) {
      console.error("Failed to copy evaluationSessionId", e);
    }
  }

  function renderMessage(msg: Message) {
    const isUser = msg.role === "user";
    const textOnly = extractText(msg.content);

    async function handleCopyRaw() {
      try {
        await navigator.clipboard.writeText(textOnly);
      } catch (e) {
        console.error("Failed to copy message", e);
      }
    }

    return (
      <div
        key={msg.id}
        className={cn("flex", isUser ? "justify-end" : "justify-start")}
      >
        <div
          className={cn(
            "max-w-[80%] rounded-lg border px-3 py-2 text-sm shadow-sm",
            isUser
              ? "bg-slate-900 border-slate-700 text-slate-50"
              : "bg-slate-900/70 border-slate-700 text-slate-100"
          )}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-[10px] uppercase tracking-wide text-slate-400">
              {isUser ? "You" : "Assistant"}
            </span>
            <button
              type="button"
              onClick={handleCopyRaw}
              className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
            >
              <Copy className="h-3 w-3" />
              Copy
            </button>
          </div>
          <MarkdownMessage content={msg.content} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <div className="flex items-center gap-3">
          <div className="text-xs text-slate-400">Model</div>
          <select
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
            value={selectedModel ?? ""}
            onChange={handleModelChange}
            disabled={!activeChat || models.length === 0}
          >
            {modelsLoading && <option value="">Loading models...</option>}
            {!modelsLoading && models.length === 0 && (
              <option value="">No models</option>
            )}
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          {modelsError && (
            <span className="text-[10px] text-red-400">{modelsError}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeChat?.evaluationSessionId && (
            <button
              type="button"
              onClick={handleCopyEvalId}
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] text-slate-200 hover:bg-slate-800"
              title="Copy evaluationSessionId"
            >
              <Copy className="h-3 w-3" />
              <span className="max-w-[200px] truncate">
                {activeChat.evaluationSessionId}
              </span>
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !streamingText && (
          <div className="mt-10 text-center text-sm text-slate-500">
            Start a new chat from the sidebar and type your message below.
          </div>
        )}
        {messages.map((m) => renderMessage(m))}
        {streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 shadow-sm">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[10px] uppercase tracking-wide text-slate-400">
                  Assistant
                </span>
                <Loader2 className="h-3 w-3 animate-spin text-slate-400" />
              </div>
              <MarkdownMessage content={streamingText} />
            </div>
          </div>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-slate-800 px-4 py-3 space-y-2"
      >
        {error && (
          <div className="text-xs text-red-400 mb-1">
            {error}
          </div>
        )}

        {pendingImages.length > 0 && (
          <div className="mb-1 flex flex-wrap gap-2">
            {pendingImages.map((img) => (
              <div
                key={img.id}
                className="relative h-16 w-16 overflow-hidden rounded-md border border-slate-700"
              >
                <img
                  src={img.dataUrl}
                  alt="pending"
                  className="h-full w-full object-cover"
                />
                <button
                  type="button"
                  className="absolute right-0 top-0 rounded-bl-md bg-black/70 px-1 text-[10px] text-slate-100"
                  onClick={() => handleRemoveImage(img.id)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
            onClick={() => {
              const input = document.getElementById(
                "file-input"
              ) as HTMLInputElement | null;
              input?.click();
            }}
            title="Attach images"
          >
            <ImageIcon className="h-4 w-4" />
          </button>
          <input
            id="file-input"
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={handleFileInput}
          />
          <textarea
            className="min-h-[52px] max-h-40 flex-1 resize-none rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-400"
            placeholder={
              selectedModel
                ? "Send a message..."
                : modelsLoading
                ? "Loading models..."
                : "No models available"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending || !selectedModel}
          />
          <button
            type="submit"
            disabled={
              sending ||
              !selectedModel ||
              (input.trim().length === 0 && pendingImages.length === 0)
            }
            className={cn(
              "inline-flex h-9 items-center justify-center rounded-lg px-4 text-sm font-medium",
              sending || !selectedModel || (input.trim().length === 0 && pendingImages.length === 0)
                ? "bg-slate-800 text-slate-500"
                : "bg-slate-100 text-slate-900 hover:bg-slate-200"
            )}
          >
            {sending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Send"
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

function buildContentWithImages(
  text: string,
  dataUrls: string[]
): MessageContent {
  const parts: (MessagePartText | MessagePartImageUrl)[] = [];
  if (text.trim()) {
    parts.push({ type: "text", text });
  }
  for (const url of dataUrls) {
    parts.push({ type: "image_url", image_url: { url } });
  }
  return parts;
}

function buildAssistantContent(
  text: string,
  images: string[]
): MessageContent {
  const parts: (MessagePartText | MessagePartImageUrl)[] = [];
  if (text) {
    parts.push({ type: "text", text });
  }
  for (const url of images) {
    parts.push({ type: "image_url", image_url: { url } });
  }
  if (parts.length === 0) {
    return "";
  }
  if (parts.length === 1 && parts[0].type === "text") {
    return parts[0].text;
  }
  return parts;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === "string") {
        resolve(result);
      } else {
        reject(new Error("Unexpected file reader result"));
      }
    };
    reader.readAsDataURL(file);
  });
}
