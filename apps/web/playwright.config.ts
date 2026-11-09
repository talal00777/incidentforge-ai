import { defineConfig, devices } from "@playwright/test";

/**
 * M5.3 browser tests run against an already running local web service.
 * No automatic production-data mutation or screenshot/trace capture.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  outputDir: "./test-results/m53-browser",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.IF_M53_BASE_URL ?? "http://localhost:3000",
    headless: true,
    acceptDownloads: true,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
