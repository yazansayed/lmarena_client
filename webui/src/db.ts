import Dexie, { Table } from "dexie";
import type { Chat, Message, Settings } from "./types";

export interface SettingsRow {
  key: string;
  value: Settings;
}

export class LMArenaDB extends Dexie {
  chats!: Table<Chat, string>;
  messages!: Table<Message, string>;
  settings!: Table<SettingsRow, string>;

  constructor() {
    super("lmarena_client_webui");
    this.version(1).stores({
      chats: "id, createdAt, updatedAt",
      messages: "id, chatId, createdAt",
      settings: "key",
    });
  }
}

export const db = new LMArenaDB();
