import React, { useState } from "react";
import { useSettingsStore } from "../store/settings";
import type { Theme } from "../types";
import { cn } from "../lib/cn";
import { Download, Upload, X } from "lucide-react";
import { db } from "../db";
import { reloadChatsFromDB } from "../store/chats";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

interface ExportFileV1 {
  version: 1;
  exportedAt: string;
  chats: any[];
  messages: any[];
}

export const SettingsDrawer: React.FC<SettingsDrawerProps> = ({
  open,
  onClose,
}) => {
  const { settings, setTheme, setStreaming, setMaxChats } = useSettingsStore();
  const [maxChatsDraft, setMaxChatsDraft] = useState(settings.maxChats);
  const [importError, setImportError] = useState<string | null>(null);

  if (!open) return null;

  function handleThemeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setTheme(e.target.value as Theme).catch((err) =>
      console.error("Failed to set theme", err)
    );
  }

  function handleStreamingChange(e: React.ChangeEvent<HTMLInputElement>) {
    setStreaming(e.target.checked).catch((err) =>
      console.error("Failed to set streaming", err)
    );
  }

  function handleMaxChatsBlur() {
    const n = Number(maxChatsDraft);
    if (!Number.isFinite(n) || n <= 0) {
      setMaxChatsDraft(settings.maxChats);
      return;
    }
    setMaxChats(n).catch((err) =>
      console.error("Failed to set maxChats", err)
    );
  }

  async function handleExport() {
    try {
      const chats = await db.chats.orderBy("createdAt").toArray();
      const messages = await db.messages.orderBy("createdAt").toArray();
      const payload: ExportFileV1 = {
        version: 1,
        exportedAt: new Date().toISOString(),
        chats,
        messages,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `lmarena_chats_${new Date()
        .toISOString()
        .replace(/[:.]/g, "-")}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to export chats", err);
    }
  }

  async function handleImportFile(
    e: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    if (
      !window.confirm(
        "Importing will replace all existing local chats. Continue?"
      )
    ) {
      return;
    }

    try {
      const text = await file.text();
      const data = JSON.parse(text) as ExportFileV1;

      if (
        !data ||
        !Array.isArray((data as any).chats) ||
        !Array.isArray((data as any).messages)
      ) {
        throw new Error("Invalid export format");
      }

      await db.transaction("rw", db.chats, db.messages, async () => {
        await db.chats.clear();
        await db.messages.clear();
        await db.chats.bulkAdd((data as any).chats);
        await db.messages.bulkAdd((data as any).messages);
      });

      await reloadChatsFromDB();
      setImportError(null);
      onClose();
    } catch (err: any) {
      console.error("Failed to import chats", err);
      setImportError(
        err instanceof Error ? err.message : "Failed to import file"
      );
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40">
      <div className="h-full w-80 border-l border-slate-800 bg-slate-950 text-slate-100 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <div>
            <div className="text-sm font-semibold">Settings</div>
            <div className="text-xs text-slate-400">
              lmarena-client WebUI
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-slate-900 text-slate-300 hover:bg-slate-800"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 px-4 py-4 text-sm">
          <div>
            <div className="mb-1 text-xs font-semibold text-slate-300">
              Theme
            </div>
            <select
              value={settings.theme}
              onChange={handleThemeChange}
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
            >
              <option value="dark">Dark</option>
              <option value="light">Light</option>
              <option value="system">System</option>
            </select>
          </div>

          <div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={settings.streaming}
                onChange={handleStreamingChange}
                className="h-3 w-3 rounded border-slate-600 bg-slate-900 text-slate-100"
              />
              <span>Stream responses (token-by-token)</span>
            </label>
            <div className="mt-1 text-xs text-slate-400">
              When disabled, responses are returned only after completion.
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold text-slate-300">
              Max chats to keep
            </div>
            <input
              type="number"
              min={1}
              value={maxChatsDraft}
              onChange={(e) => setMaxChatsDraft(Number(e.target.value))}
              onBlur={handleMaxChatsBlur}
              className={cn(
                "w-24 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
              )}
            />
            <div className="mt-1 text-xs text-slate-400">
              Oldest chats beyond this limit will be removed.
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold text-slate-300">
              Export / Import
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleExport}
                className="inline-flex flex-1 items-center justify-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 hover:bg-slate-800"
              >
                <Download className="h-3 w-3" />
                Export JSON
              </button>
              <button
                type="button"
                onClick={() => {
                  const input = document.getElementById(
                    "import-file-input"
                  ) as HTMLInputElement | null;
                  input?.click();
                }}
                className="inline-flex flex-1 items-center justify-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 hover:bg-slate-800"
              >
                <Upload className="h-3 w-3" />
                Import
              </button>
              <input
                id="import-file-input"
                type="file"
                accept="application/json"
                className="hidden"
                onChange={handleImportFile}
              />
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              Import will replace all existing local chats and messages.
            </div>
            {importError && (
              <div className="mt-1 text-[11px] text-red-400">
                {importError}
              </div>
            )}
          </div>

          <div className="mt-4 text-[11px] text-slate-500">
            API base URL is automatically set to{" "}
            <code className="rounded bg-slate-900 px-1">
              {window.location.origin}
            </code>
            .
          </div>
        </div>
      </div>
    </div>
  );
};

