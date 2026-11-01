import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Component and module specs (*.spec.ts[x]). The older src/utils/*.test.ts
// files are plain node scripts and keep running with `npm run test:utils`.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    environment: "jsdom",
    include: ["src/**/*.spec.{ts,tsx}"],
    css: false,
  },
});
