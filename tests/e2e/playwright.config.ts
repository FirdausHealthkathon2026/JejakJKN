import {defineConfig} from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  timeout: 90_000,
  retries: 0,
  use: {headless: true, trace: "retain-on-failure", launchOptions: {executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"]}},
  reporter: "line",
});
