/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the React app runs on :5173 and forwards API calls to FastAPI on :8000,
// so the browser sees a single origin (no CORS setup, and the login cookie just works).
// 127.0.0.1 rather than "localhost": on Windows, localhost can resolve to the IPv6 address first, where
// uvicorn isn't listening, and every API call would fail.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "node",
  },
});
