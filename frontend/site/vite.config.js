import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/site/",
  plugins: [react()],
  build: {
    outDir: "../../app/static/web/site",
    emptyOutDir: true,
    assetsDir: "assets",
  },
});
