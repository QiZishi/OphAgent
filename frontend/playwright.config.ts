import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8013",
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: {
    command: "cd .. && ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8013",
    url: "http://127.0.0.1:8013",
    reuseExistingServer: true,
    timeout: 30_000
  },
  projects: [
    {
      name: "desktop",
      grep: /@desktop/,
      use: { ...devices["Desktop Chrome"], browserName: "chromium", viewport: { width: 1440, height: 900 } }
    },
    {
      name: "mobile",
      grep: /@mobile/,
      use: { ...devices["iPhone 13"], browserName: "chromium" }
    }
  ]
});
