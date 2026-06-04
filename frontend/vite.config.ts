import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built SPA is served by FastAPI from /static/app/. In dev, Vite serves the
// app and proxies /api to the running FastAPI process (matchbox web, :8765).
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../src/matchbox/web/static/app",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});
