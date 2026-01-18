import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  // App is served from /ui when built by the Python server.
  base: "/ui/",
  server: {
    port: 5173,
    proxy: {
      "/v1": {
        target: "http://127.0.0.1:1337",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Emit directly into the Python package so FastAPI can serve from webui_dist.
    outDir: "../lmarena_client/webui_dist",
    // Avoid Vite trying to empty directories outside the project root.
    emptyOutDir: false,
  },
});


