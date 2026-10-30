import {defineConfig} from "@playwright/test";
import {existsSync} from "node:fs";
import {resolve} from "node:path";

const envPath = resolve(__dirname, "../../.env");
if (existsSync(envPath) && typeof process.loadEnvFile === "function") {
  process.loadEnvFile(envPath);
}

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  timeout: 90_000,
  retries: 0,
  use: {headless: true, trace: "retain-on-failure", launchOptions: {executablePath: "/usr/bin/google-chrome", args: ["--no-sandbox"]}},
  reporter: "line",
});
