// Browser check of the verifier CSV upload and the SIMRS B screens.
// Usage: node demo-ui-batch.mjs [screenshot-dir] [csv-file]
import {mkdirSync} from "node:fs";
import {chromium} from "playwright";

const SHOTS = process.argv[2] ?? "demo-shots";
const CSV_BUTTON = process.argv[3] ?? "klaim_contoh_1000.csv";
mkdirSync(SHOTS, {recursive: true});
const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1280, height: 800}});
const problems = [];

const simrsB = await context.newPage();
simrsB.on("pageerror", (e) => problems.push(`simrs-b crash: ${e.message}`));
await simrsB.goto("http://localhost:5176");
await simrsB.getByText("Pasien hari ini").first().waitFor();
await simrsB.getByRole("button", {name: "Klaim BPJS"}).click();
await simrsB.getByText("Sudah diajukan").first().waitFor();
await simrsB.screenshot({path: `${SHOTS}/20-simrsb-klaim.png`});
console.log("- SIMRS B terbuka");

const page = await context.newPage();
page.on("pageerror", (e) => problems.push(`verifikator crash: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("favicon")) problems.push(m.text().slice(0, 200)); });
await page.goto("http://localhost:5175");
await page.getByRole("button", {name: "Masuk", exact: true}).click();
await page.getByRole("button", {name: "Unggah CSV"}).first().click();
await page.getByRole("button", {name: "klaim_november.csv"}).click();
await page.getByText("bermasalah").first().waitFor();
await page.screenshot({path: `${SHOTS}/21-unggah-masalah.png`});
console.log("- file bermasalah ditolak per baris");
await page.getByRole("button", {name: "Unggah CSV"}).first().click();
await page.getByRole("button", {name: new RegExp(CSV_BUTTON)}).click();
await page.getByRole("button", {name: /^Periksa [\d.]+ klaim/}).waitFor();
await page.screenshot({path: `${SHOTS}/22-unggah-pratinjau.png`});
const started = Date.now();
await page.getByRole("button", {name: /^Periksa [\d.]+ klaim/}).click();
await page.getByText("Sedang memeriksa").waitFor();
await page.waitForTimeout(8000);
await page.screenshot({path: `${SHOTS}/23-unggah-berjalan.png`});
await page.getByText("Ringkasan unggahan").first().waitFor({timeout: 480000});
console.log(`- unggahan selesai dalam ${Math.round((Date.now() - started) / 1000)} detik`);
await page.waitForTimeout(1000);
await page.screenshot({path: `${SHOTS}/24-unggah-hasil.png`, fullPage: false});
console.log((await page.locator("main").innerText()).split("\n").filter(Boolean).slice(0, 26).join(" | "));

console.log(problems.length ? `MASALAH:\n${[...new Set(problems)].join("\n")}` : "TANPA ERROR BROWSER");
await browser.close();
