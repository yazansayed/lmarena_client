export type Role = "user" | "assistant";

export interface MessagePartText {
  type: "text";
  text: string;
}

export interface MessagePartImageUrl {
  type: "image_url";
  image_url: {
    url: string;
  };
}

export type MessageContent = string | (MessagePartText | MessagePartImageUrl)[];

export interface Message {
  id: string;
  chatId: string;
  role: Role;
  content: MessageContent;
  createdAt: number;
}

export interface Chat {
  id: string;
  title: string;
  model: string | null;
  evaluationSessionId: string | null;
  createdAt: number;
  updatedAt: number;
}

export type Theme = "dark" | "light" | "system";

export interface Settings {
  maxChats: number;
  streaming: boolean;
  theme: Theme;
}
