import React, { useEffect, useState } from "react";
import { listModels } from "./api/client";
import { useSettingsStore } from "./store/settings";
import { useChatStore } from "./store/chats";
import { Sidebar } from "./components/Sidebar";
import { ChatView } from "./components/ChatView";
import { SettingsDrawer } from "./components/SettingsDrawer";

const App: React.FC = () => {
  const { load: loadSettings, loaded: settingsLoaded } = useSettingsStore();
  const { init: initChats } = useChatStore();
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState<boolean>(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    // Load settings and chats on startup
    loadSettings().catch((e) => console.error("Failed to load settings", e));
    initChats().catch((e) => console.error("Failed to init chats", e));
  }, [loadSettings, initChats]);

  useEffect(() => {
    let cancelled = false;
    async function loadModels() {
      setModelsLoading(true);
      setModelsError(null);
      try {
        const ms = await listModels();
        if (!cancelled) {
          setModels(ms);
        }
      } catch (e: any) {
        console.error("Failed to load models", e);
        if (!cancelled) {
          setModelsError(
            e instanceof Error ? e.message : "Failed to load models from /v1/models"
          );
        }
      } finally {
        if (!cancelled) {
          setModelsLoading(false);
        }
      }
    }
    loadModels();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!settingsLoaded) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <div className="text-sm text-slate-300">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex">
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} />
      <main className="flex-1 flex flex-col border-l border-slate-800 bg-slate-950/80">
        <ChatView
          models={models}
          modelsLoading={modelsLoading}
          modelsError={modelsError}
        />
      </main>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
};

export default App;

