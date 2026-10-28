import { defineConfig, devices } from "@playwright/test";

// The app built with relative API URLs, served by `vite preview`, talking to
// e2e/mock-server.mjs through the preview proxy. No real backend or model.
const MOCK = 8765;
const PREVIEW = 4173;

export default defineConfig({
  testDir: "e2e",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${PREVIEW}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } } },
  ],
  webServer: [
    { command: `node e2e/mock-server.mjs`, port: MOCK, reuseExistingServer: !process.env.CI, env: { MOCK_PORT: String(MOCK) } },
    {
      command: `npm run build:e2e && npx vite preview --outDir dist-e2e --port ${PREVIEW} --strictPort`,
      port: PREVIEW,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: { MIZAN_API_TARGET: `http://localhost:${MOCK}` },
    },
  ],
});
