import React, { useMemo, useState } from "react";
import { useChatStore } from "../store/chats";
import { useSettingsStore } from "../store/settings";
import type { MessageContent, MessagePartText } from "../types";
import { cn } from "../lib/cn";
import { Plus, Search, Settings, Trash2, X } from "lucide-react";

interface SidebarProps {
  onOpenSettings: () => void;
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

export const Sidebar: React.FC<SidebarProps> = ({ onOpenSettings }) => {
  const { chats, activeChatId, setActiveChat, createChat, deleteChat, getMessagesForChat } =
    useChatStore();
  const { settings } = useSettingsStore();

  const [searchQuery, setSearchQuery] = useState("");

  const filteredChats = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return chats;

    return chats.filter((chat) => {
      // Search in title
      const title = (chat.title || "").toLowerCase();
      if (title.includes(q)) return true;

      // Search in model name
      const model = (chat.model || "").toLowerCase();
      if (model.includes(q)) return true;

      // Search in messages
      const messages = getMessagesForChat(chat.id);
      for (const msg of messages) {
        const text = extractText(msg.content).toLowerCase();
        if (text.includes(q)) return true;
      }

      return false;
    });
  }, [chats, searchQuery, getMessagesForChat]);

  async function handleNewChat() {
    const defaultModel = chats.length > 0 ? chats[chats.length - 1].model : null;
    const chat = await createChat({ model: defaultModel });
    setActiveChat(chat.id);
    setSearchQuery("");
  }

  return (
    <aside className="w-72 bg-slate-950 border-r border-slate-800 flex flex-col">
      <div className="px-4 py-3 flex items-center justify-between border-b border-slate-800">
        <div>
          <div className="text-sm font-semibold">lmarena-client</div>
          <div className="text-xs text-slate-400">Max chats: {settings.maxChats}</div>
        </div>
        <button
          type="button"
          onClick={onOpenSettings}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800"
          title="Settings"
        >
          <Settings className="h-4 w-4" />
        </button>
      </div>

      <div className="px-3 py-2 border-b border-slate-800 flex gap-2">
        <button
          type="button"
          onClick={handleNewChat}
          className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-slate-800 text-slate-100 text-sm py-1.5 hover:bg-slate-700"
        >
          <Plus className="h-4 w-4" />
          New chat
        </button>
      </div>

      <div className="px-3 py-2 border-b border-slate-800">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search chats..."
            className="w-full rounded-md border border-slate-700 bg-slate-900 py-1.5 pl-7 pr-7 text-xs text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-400"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              title="Clear search"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {chats.length === 0 ? (
          <div className="px-4 py-2 text-xs text-slate-500">
            No chats yet. Click &quot;New chat&quot; to start.
          </div>
        ) : filteredChats.length === 0 ? (
          <div className="px-4 py-2 text-xs text-slate-500">
            No chats match your search.
          </div>
        ) : (
          <ul className="space-y-1 px-2">
            {filteredChats
              .slice()
              .sort((a, b) => a.createdAt - b.createdAt)
              .map((chat) => (
                <li key={chat.id}>
                  <button
                    type="button"
                    onClick={() => setActiveChat(chat.id)}
                    className={cn(
                      "w-full flex items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-xs",
                      activeChatId === chat.id
                        ? "bg-slate-800 text-slate-50"
                        : "text-slate-300 hover:bg-slate-900"
                    )}
                  >
                    <div className="flex-1 truncate">
                      <div className="truncate">
                        {chat.title && chat.title !== "New chat"
                          ? chat.title
                          : "Untitled chat"}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate mt-0.5">
                        {chat.model ?? "model: auto"}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteChat(chat.id);
                      }}
                      className="inline-flex h-6 w-6 items-center justify-center rounded-md text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                      title="Delete chat"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>
    </aside>
  );
};


