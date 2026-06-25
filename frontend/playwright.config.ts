import { defineConfig, devices } from "@playwright/test"

/**
 * Oskar E2E — Playwright config
 *
 * Assumes both services are already running:
 *   Backend  http://localhost:8000  (uvicorn, AUTH_PROVIDER=dev)
 *   Frontend http://localhost:5173  (vite dev) OR http://localhost:4173 (vite preview)
 *
 * Override with env vars:
 *   BASE_URL      — frontend base (default http://localhost:5173)
 *   API_URL       — backend base  (default http://localhost:8000)
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,   // workflow tests share DB state — run serially by default
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,             // single worker keeps DB state predictable
  reporter: [
    ["list"],
    ["html", { outputFolder: "e2e-report", open: "never" }],
  ],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // All requests that the page makes pass through here so we can intercept
    extraHTTPHeaders: {},
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // No webServer block — tests assume both services are already running.
  // Use `npm run e2e:serve` to start both before running tests.
})
