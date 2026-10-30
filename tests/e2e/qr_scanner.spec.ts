import {expect, test, chromium, type APIRequestContext, type Browser, type Page} from "@playwright/test";
import {mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {spawnSync} from "node:child_process";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {QRCodeSVG} from "qrcode.react";

const TOKEN_URL = "http://localhost:8081/realms/jejakjkn-dev/protocol/openid-connect/token";
const ISSUE_URL = "http://localhost:18080/api/v1/patient/qr-tokens";
const APPS = {
  A: {url: "http://localhost:5174", facility: "HOSP-DEMO-001", inPath: "/api/scan/check-in", outPath: "/api/scan/check-out"},
  B: {url: "http://localhost:5176", facility: "HOSP-DEMO-002", inPath: "/api/pindai/masuk", outPath: "/api/pindai/keluar"},
} as const;

async function accessToken(request: APIRequestContext) {
  const response = await request.post(TOKEN_URL, {form: {
    grant_type: "client_credentials",
    client_id: "test-patient-client",
    client_secret: process.env.TEST_PATIENT_CLIENT_SECRET ?? "",
  }});
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).access_token as string;
}

async function issueQr(request: APIRequestContext, token: string, purpose: "CHECK_IN" | "CHECK_OUT", facility: string, encounterId?: string) {
  const response = await request.post(ISSUE_URL, {
    headers: {Authorization: `Bearer ${token}`},
    data: {purpose, facility_hint: facility, encounter_id: encounterId},
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()).token as string;
}

async function qrPng(browser: Browser, value: string) {
  const page = await browser.newPage({viewport: {width: 360, height: 360}});
  const svg = renderToStaticMarkup(createElement(QRCodeSVG, {value, size: 300, marginSize: 4, level: "L"}));
  await page.setContent(`<body style="margin:30px;background:white">${svg}</body>`);
  const png = await page.locator("svg").screenshot({type: "png"});
  await page.close();
  return png;
}

async function openScanner(page: Page, url: string, outgoing: boolean) {
  await page.goto(url);
  await page.getByRole("button", {name: "Pindai QR"}).first().click();
  if (outgoing) await page.getByRole("button", {name: "QR Keluar", exact: true}).click();
}

async function galleryScan(browser: Browser, app: typeof APPS.A | typeof APPS.B, png: Buffer, outgoing = false) {
  const page = await browser.newPage();
  await openScanner(page, app.url, outgoing);
  const path = outgoing ? app.outPath : app.inPath;
  const responsePromise = page.waitForResponse((response) => response.url().includes(path) && response.request().method() === "POST");
  await page.locator('input[type="file"]').setInputFiles({name: "patient-qr.png", mimeType: "image/png", buffer: png});
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBeTruthy();
  await expect(page.getByText(outgoing ? "Keluar berhasil" : "Masuk berhasil").first()).toBeVisible();
  const result = await response.json();
  await page.close();
  return result.encounter_id as string;
}

function fakeCameraVideo(png: Buffer) {
  const directory = mkdtempSync(join(tmpdir(), "jejakjkn-camera-"));
  const input = join(directory, "qr.png");
  const output = join(directory, "qr.y4m");
  writeFileSync(input, png);
  const conversion = spawnSync("ffmpeg", [
    "-loglevel", "error", "-y", "-loop", "1", "-i", input,
    "-vf", "scale=480:480:force_original_aspect_ratio=decrease,pad=640:480:(ow-iw)/2:(oh-ih)/2:white,format=yuv420p",
    "-t", "8", "-r", "8", output,
  ]);
  expect(conversion.status, conversion.stderr.toString()).toBe(0);
  return {directory, output};
}

async function cameraScan(app: typeof APPS.A | typeof APPS.B, png: Buffer, outgoing = false) {
  const video = fakeCameraVideo(png);
  const browser = await chromium.launch({
    headless: true,
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", `--use-file-for-fake-video-capture=${video.output}`],
  });
  try {
    const context = await browser.newContext({permissions: ["camera"]});
    const page = await context.newPage();
    await openScanner(page, app.url, outgoing);
    const path = outgoing ? app.outPath : app.inPath;
    let requests = 0;
    page.on("request", (request) => { if (request.url().includes(path) && request.method() === "POST") requests += 1; });
    const responsePromise = page.waitForResponse((response) => response.url().includes(path) && response.request().method() === "POST", {timeout: 20_000});
    await page.getByRole("button", {name: "Buka kamera"}).click();
    const response = await responsePromise;
    expect(response.ok(), await response.text()).toBeTruthy();
    await expect(page.getByText(outgoing ? "Keluar berhasil" : "Masuk berhasil").first()).toBeVisible();
    expect(requests).toBe(1);
    return (await response.json()).encounter_id as string;
  } finally {
    await browser.close();
    rmSync(video.directory, {recursive: true, force: true});
  }
}

test("gallery processes signed QR IN and OUT in SIMRS A and B", async ({browser, request}) => {
  const auth = await accessToken(request);
  for (const app of [APPS.A, APPS.B]) {
    const checkIn = await issueQr(request, auth, "CHECK_IN", app.facility);
    const encounterId = await galleryScan(browser, app, await qrPng(browser, checkIn));
    const checkOut = await issueQr(request, auth, "CHECK_OUT", app.facility, encounterId);
    expect(await galleryScan(browser, app, await qrPng(browser, checkOut), true)).toBe(encounterId);
  }
});

test("fake camera processes signed QR IN and OUT once in SIMRS A and B", async ({browser, request}) => {
  const auth = await accessToken(request);
  for (const app of [APPS.A, APPS.B]) {
    const checkIn = await issueQr(request, auth, "CHECK_IN", app.facility);
    const encounterId = await cameraScan(app, await qrPng(browser, checkIn));
    const checkOut = await issueQr(request, auth, "CHECK_OUT", app.facility, encounterId);
    expect(await cameraScan(app, await qrPng(browser, checkOut), true)).toBe(encounterId);
  }
});

test("scanner validates images, reports permission errors, and reuses retry identity", async ({browser}) => {
  const token = "scanner-retry-token-123456789012345678901234567890";
  const png = await qrPng(browser, token);
  const context = await browser.newContext();
  const page = await context.newPage();
  const keys: string[] = [];
  const bodies: string[] = [];
  let attempts = 0;
  await page.route("**/api/visits", (route) => route.fulfill({json: []}));
  await page.route("**/api/claims?**", (route) => route.fulfill({json: []}));
  await page.route("**/api/scan/check-in", async (route) => {
    attempts += 1;
    keys.push(await route.request().headerValue("Idempotency-Key") ?? "");
    bodies.push(route.request().postData() ?? "");
    if (attempts === 1) await route.abort("connectionreset");
    else await route.fulfill({json: {encounter_id: "11111111-1111-4111-8111-111111111111"}});
  });
  await openScanner(page, APPS.A.url, false);
  await page.locator('input[type="file"]').setInputFiles({name: "retry.png", mimeType: "image/png", buffer: png});
  await expect(page.getByText("JejakJKN tidak dapat dihubungi")).toBeVisible();
  await page.getByRole("button", {name: "Proses QR Masuk"}).click();
  await expect(page.getByText("Masuk berhasil").first()).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  expect(bodies[0]).toBe(bodies[1]);

  await page.locator('input[type="file"]').setInputFiles({name: "too-large.png", mimeType: "image/png", buffer: Buffer.alloc(10 * 1024 * 1024 + 1)});
  await expect(page.getByText("Ukuran gambar maksimal 10 MiB.")).toBeVisible();
  await page.getByRole("button", {name: "Buka kamera"}).click();
  await expect(page.getByText(/Izin kamera ditolak|Kamera tidak ditemukan|Kamera sedang digunakan/)).toBeVisible({timeout: 10_000});
  expect(attempts).toBe(2);
  await context.close();
});
