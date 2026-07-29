import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    exclude: ["e2e/**", "node_modules/**", "dist/**"]
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8013",
      "/auth": "http://127.0.0.1:8013",
      "/ws": { target: "ws://127.0.0.1:8013", ws: true }
    }
  }
});
