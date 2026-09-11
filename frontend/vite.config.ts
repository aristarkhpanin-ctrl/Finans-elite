import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = `http://127.0.0.1:${process.env.E2E_API_PORT ?? 8000}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Прокси на backend в dev. Порт переопределяется `E2E_API_PORT`: сквозные тесты
      // поднимают свой бэкенд на свободном порту и со своей базой, чтобы не задеть
      // ни dev-базу разработчика, ни его же запущенный сервер.
      "/api": { target: apiTarget, changeOrigin: true },
      "/health": { target: apiTarget, changeOrigin: true },
    },
  },
});
