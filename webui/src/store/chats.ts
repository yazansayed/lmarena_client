import { create } from "zustand";
import { db } from "../db";
import type { Chat, Message, MessageContent } from "../types";
import { newId } from "../lib/id";
import { useSettingsStore } from "./settings";

interface ChatState {
  chats: Chat[];
  messagesByChatId: Record<string, Message[]>;
  activeChatId: string | null;
  loading: boolean;

  init: () => Promise<void>;
  createChat: (opts?: { model?: string | null; title?: string }) => Promise<Chat>;
  setActiveChat: (id: string | null) => void;
  addMessage: (message: Omit<Message, "id" | "createdAt"> & { id?: string }) => Promise<Message>;
  updateChat: (id: string, patch: Partial<Chat>) => Promise<void>;
  deleteChat: (id: string) => Promise<void>;
  clearAll: () => Promise<void>;
  getMessagesForChat: (chatId: string | null) => Message[];
}

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  messagesByChatId: {},
  activeChatId: null,
  loading: false,

  async init() {
    if (get().loading || get().chats.length > 0) return;
    set({ loading: true });
    try {
      const chats = await db.chats.orderBy("createdAt").toArray();
      const messagesByChatId: Record<string, Message[]> = {};

      if (chats.length > 0) {
        const allMessages = await db.messages.orderBy("createdAt").toArray();
        for (const msg of allMessages) {
          if (!messagesByChatId[msg.chatId]) {
            messagesByChatId[msg.chatId] = [];
          }
          messagesByChatId[msg.chatId].push(msg);
        }
      }

      const activeChatId = chats.length > 0 ? chats[chats.length - 1].id : null;

      set({ chats, messagesByChatId, activeChatId, loading: false });
    } catch (e) {
      console.error("Failed to init chat store", e);
      set({ loading: false });
    }
  },

  async createChat(opts?: { model?: string | null; title?: string }) {
    const id = newId();
    const now = Date.now();
    const chat: Chat = {
      id,
      title: opts?.title ?? "New chat",
      model: opts?.model ?? null,
      evaluationSessionId: null,
      createdAt: now,
      updatedAt: now,
    };

    await db.chats.add(chat);

    // enforce maxChats from settings
    const maxChats = useSettingsStore.getState().settings.maxChats;
    let chats = [...get().chats, chat];
    if (chats.length > maxChats) {
      const toDelete = chats
        .slice()
        .sort((a, b) => a.createdAt - b.createdAt)
        .slice(0, chats.length - maxChats);
      const toDeleteIds = new Set(toDelete.map((c) => c.id));

      await db.transaction("rw", db.chats, db.messages, async () => {
        for (const c of toDelete) {
          await db.chats.delete(c.id);
          await db.messages.where("chatId").equals(c.id).delete();
        }
      });

      chats = chats.filter((c) => !toDeleteIds.has(c.id));
      const messagesByChatId = { ...get().messagesByChatId };
      for (const id of toDeleteIds) {
        delete messagesByChatId[id];
      }
      set({ messagesByChatId });
    }

    set({ chats, activeChatId: id });
    return chat;
  },

  setActiveChat(id: string | null) {
    set({ activeChatId: id });
  },

  async addMessage(
    message: Omit<Message, "id" | "createdAt"> & { id?: string; createdAt?: number }
  ) {
    const id = message.id ?? newId();
    const createdAt = message.createdAt ?? Date.now();
    const full: Message = {
      id,
      createdAt,
      chatId: message.chatId,
      role: message.role,
      content: message.content as MessageContent,
    };

    await db.messages.add(full);

    set((state) => {
      const existing = state.messagesByChatId[full.chatId] ?? [];
      return {
        messagesByChatId: {
          ...state.messagesByChatId,
          [full.chatId]: [...existing, full],
        },
      };
    });

    await db.chats.update(full.chatId, { updatedAt: createdAt });

    set((state) => {
      const chats = state.chats.map((c) =>
        c.id === full.chatId ? { ...c, updatedAt: createdAt } : c
      );
      return { chats };
    });

    return full;
  },

  async updateChat(id: string, patch: Partial<Chat>) {
    await db.chats.update(id, patch);
    set((state) => ({
      chats: state.chats.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    }));
  },

  async deleteChat(id: string) {
    await db.transaction("rw", db.chats, db.messages, async () => {
      await db.chats.delete(id);
      await db.messages.where("chatId").equals(id).delete();
    });

    set((state) => {
      const chats = state.chats.filter((c) => c.id !== id);
      const messagesByChatId = { ...state.messagesByChatId };
      delete messagesByChatId[id];

      let activeChatId = state.activeChatId;
      if (activeChatId === id) {
        activeChatId = chats.length > 0 ? chats[chats.length - 1].id : null;
      }

      return { chats, messagesByChatId, activeChatId };
    });
  },

  async clearAll() {
    await db.transaction("rw", db.chats, db.messages, db.settings, async () => {
      await db.chats.clear();
      await db.messages.clear();
    });

    set({ chats: [], messagesByChatId: {}, activeChatId: null });
  },

  getMessagesForChat(chatId: string | null) {
    if (!chatId) return [];
    const state = get();
    return state.messagesByChatId[chatId] ?? [];
  },
}));

export async function reloadChatsFromDB() {
  const chats = await db.chats.orderBy("createdAt").toArray();
  const messagesByChatId: Record<string, Message[]> = {};

  if (chats.length > 0) {
    const allMessages = await db.messages.orderBy("createdAt").toArray();
    for (const msg of allMessages) {
      if (!messagesByChatId[msg.chatId]) {
        messagesByChatId[msg.chatId] = [];
      }
      messagesByChatId[msg.chatId].push(msg);
    }
  }

  const activeChatId = chats.length > 0 ? chats[chats.length - 1].id : null;

  useChatStore.setState({
    chats,
    messagesByChatId,
    activeChatId,
    loading: false,
  });
}

