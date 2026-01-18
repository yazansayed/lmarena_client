import React from "react";
import { useChatStore } from "../store/chats";
import { useSettingsStore } from "../store/settings";
import { cn } from "../lib/cn";
import { Plus, Settings, Trash2 } from "lucide-react";

interface SidebarProps {
  onOpenSettings: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ onOpenSettings }) => {
  const { chats, activeChatId, setActiveChat, createChat, deleteChat, clearAll } =
    useChatStore();
  const { settings } = useSettingsStore();

  async function handleNewChat() {
    const defaultModel = chats.length > 0 ? chats[chats.length - 1].model : null;
    const chat = await createChat({ model: defaultModel });
    setActiveChat(chat.id);
  }

  async function handleClearAll() {
    if (!window.confirm("Clear all chats? This cannot be undone.")) return;
    await clearAll();
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
        <button
          type="button"
          onClick={handleClearAll}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800"
          title="Clear all chats"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {chats.length === 0 ? (
          <div className="px-4 py-2 text-xs text-slate-500">
            No chats yet. Click &quot;New chat&quot; to start.
          </div>
        ) : (
          <ul className="space-y-1 px-2">
            {chats
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
