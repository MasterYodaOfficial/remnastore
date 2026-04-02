import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: true,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:4175",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4175",
    port: 4175,
    reuseExistingServer: true,
    stdout: "ignore",
    stderr: "pipe",
    env: {
      VITE_API_BASE_URL: "http://127.0.0.1:8000",
      VITE_SUPABASE_URL: "https://example.supabase.co",
      VITE_SUPABASE_ANON_KEY: "playwright-anon-key",
      VITE_TELEGRAM_BOT_URL: "https://t.me/remnastore_test_bot",
      VITE_SUPPORT_TELEGRAM_URL: "https://t.me/remnastore_support",
    },
  },
  projects: [
    {
      name: "mobile-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
});
