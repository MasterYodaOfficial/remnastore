import path from "path";
import { defineConfig, searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";

const extraAllowedHosts = (process.env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS ?? "")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5174,
    allowedHosts: ["unhurriedly-honeyed-binturong.cloudpub.ru", ...extraAllowedHosts],
    fs: {
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        path.resolve(__dirname),
        path.resolve(__dirname, "../../packages"),
      ],
    },
  },
  resolve: {
    alias: {
      "@locales": path.resolve(__dirname, "../../packages/locales"),
    },
  },
});
