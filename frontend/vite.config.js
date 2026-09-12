import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Calls to /api/* are forwarded to FastAPI, so the browser sees one origin
      // in development and we avoid CORS entirely.
      "/api": { target: "http://localhost:8000", changeOrigin: true,
                rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
});