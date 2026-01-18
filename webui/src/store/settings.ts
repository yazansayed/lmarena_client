import { create } from "zustand";
import { db } from "../db";
import type { Settings, Theme } from "../types";

const SETTINGS_KEY = "main";

const DEFAULT_SETTINGS: Settings = {
  maxChats: 50,
  streaming: true,
  theme: "dark",
};

interface SettingsState {
  settings: Settings;
  loaded: boolean;
  load: () => Promise<void>;
  setTheme: (theme: Theme) => Promise<void>;
  setStreaming: (streaming: boolean) => Promise<void>;
  setMaxChats: (maxChats: number) => Promise<void>;
  reset: () => Promise<void>;
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.classList.toggle("dark", prefersDark);
  } else {
    root.classList.toggle("dark", theme === "dark");
  }
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  settings: DEFAULT_SETTINGS,
  loaded: false,

  async load() {
    if (get().loaded) return;
    const row = await db.settings.get(SETTINGS_KEY);
    const next = row?.value ?? DEFAULT_SETTINGS;
    set({ settings: next, loaded: true });
    applyTheme(next.theme);
  },

  async setTheme(theme: Theme) {
    const current = get().settings;
    const next: Settings = { ...current, theme };
    await db.settings.put({ key: SETTINGS_KEY, value: next });
    set({ settings: next });
    applyTheme(theme);
  },

  async setStreaming(streaming: boolean) {
    const current = get().settings;
    const next: Settings = { ...current, streaming };
    await db.settings.put({ key: SETTINGS_KEY, value: next });
    set({ settings: next });
  },

  async setMaxChats(maxChats: number) {
    const current = get().settings;
    const next: Settings = { ...current, maxChats };
    await db.settings.put({ key: SETTINGS_KEY, value: next });
    set({ settings: next });
  },

  async reset() {
    await db.settings.delete(SETTINGS_KEY);
    set({ settings: DEFAULT_SETTINGS });
    applyTheme(DEFAULT_SETTINGS.theme);
  },
}));
