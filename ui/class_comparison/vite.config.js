import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        entryFileNames: "assets/dashboard.js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
