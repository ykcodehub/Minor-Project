import process from "node:process";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": {
          target:
            process.env.VITE_API_TARGET ||
            env.VITE_API_TARGET ||
            "http://127.0.0.1:8000",
          changeOrigin: false,
        },
      },
    },
  };
});
