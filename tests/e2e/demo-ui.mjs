// Drives the four web apps in a real browser through the main demo journey.
// Usage: node demo-ui.mjs [screenshot-dir] (needs playwright with Chromium)
import {mkdirSync} from "node:fs";
import {chromium} from "playwright";

const SHOTS = process.argv[2] ?? "demo-shots";
mkdirSync(SHOTS, {recursive: true});
const PATIENT = "http://localhost:5173";
const SIMRS_A = "http://localhost:5174";
const VERIFIER = "http://localhost:5175";

const browser = await chromium.launch({headless: true});
const context = await browser.newContext({viewport: {width: 1280, height: 800}, permissions: ["clipboard-read", "clipboard-write"]});
const problems = [];

async function open(url, name) {
  const page = await context.newPage();
  page.on("pageerror", (error) => problems.push(`${name} crash: ${error.message}`));
  // Polling a summary that is not ready yet answers 409/404 by design.
  page.on("console", (m) => { if (m.type() === "error" && !/favicon|status of 40[49]/.test(m.text())) problems.push(`${name} console: ${m.text().slice(0, 200)}`); });
  page.on("requestfailed", (r) => { if (!r.url().includes("fonts.g")) problems.push(`${name} request failed: ${r.url()}`); });
  await page.goto(url);
  return page;
}

// Reports text squeezed to nothing or pushed past a clipping ancestor.
const findClipped = () => {
  const out = [];
  for (const el of document.querySelectorAll("button, span, p, h1, h2, h3, a, label, dd, dt")) {
    const text = (el.textContent ?? "").trim();
    if (!text || el.children.length > 2) continue;
    const box = el.getBoundingClientRect();
    if (!box.height) continue;
    if (box.width < 2 && getComputedStyle(el).position !== "absolute") { out.push(`gepeng: ${text.slice(0, 40)}`); continue; }
    for (let a = el.parentElement; a; a = a.parentElement) {
      const style = getComputedStyle(a);
      if (style.overflowX === "visible") continue;
      if (box.right > a.getBoundingClientRect().right + 1 && style.overflowX === "hidden") out.push(`terpotong: ${text.slice(0, 40)}`);
      break;
    }
  }
  return [...new Set(out)].slice(0, 8);
};
const shot = async (page, name) => {
  await page.screenshot({path: `${SHOTS}/${name}.png`, fullPage: false});
  for (const item of await page.evaluate(findClipped)) problems.push(`${name} ${item}`);
};
const step = (text) => console.log(`- ${text}`);

// Patient: sign in through Keycloak and scan in
const patient = await open(PATIENT, "pasien");
await patient.getByRole("button", {name: /Masuk/}).first().click();
await patient.fill("#username", "patient01");
await patient.fill("#password", "synthetic-patient-01");
await patient.click("#kc-login");
await patient.waitForURL(`${PATIENT}/**`);
await patient.getByText("Riwayat").first().waitFor();
await shot(patient, "01-pasien-beranda");
step("pasien masuk");
await patient.getByRole("button", {name: /QR Masuk|Tampilkan QR/}).first().click();
await patient.getByText("Simulasikan pindai petugas").waitFor();
await shot(patient, "02-pasien-qr");
await patient.getByText("Simulasikan pindai petugas").click();
await patient.getByText(/sudah tercatat/).waitFor({timeout: 15000});
await shot(patient, "03-pasien-masuk-berhasil");
step("QR masuk diproses");

// SIMRS A: record services
const simrs = await open(SIMRS_A, "simrs-a");
await simrs.getByRole("button", {name: "Buka"}).first().click();
await simrs.getByRole("form", {name: "Tambah catatan"}).waitFor();
await shot(simrs, "04-simrs-kunjungan");
const addRecord = async (type, code, display, qty, unit) => {
  const form = simrs.getByRole("form", {name: "Tambah catatan"});
  await form.getByLabel("Jenis").selectOption(type);
  await form.getByLabel("Kode", {exact: true}).fill(code);
  await form.getByLabel("Deskripsi").fill(display);
  if (qty) {
    await form.getByLabel("Jumlah").fill(qty);
    await form.getByLabel("Satuan").fill(unit);
  }
  await form.getByRole("button", {name: "Simpan ke SIMRS"}).click();
  await simrs.getByText(display).first().waitFor();
};
await addRecord("DIAGNOSIS", "H10.9", "Konjungtivitis");
await addRecord("PROCEDURE", "PROC-EYE-01", "Pemeriksaan mata");
await addRecord("MEDICATION_DISPENSED", "MED-PCT-500", "Paracetamol 500 mg", "10", "tablet");
await shot(simrs, "05-simrs-catatan");
step("SIMRS A mencatat 3 layanan");

// Patient: scan out; SIMRS A: mark complete
await patient.bringToFront();
await patient.getByRole("button", {name: "Kembali ke beranda"}).click();
await patient.getByRole("button", {name: /QR Keluar/}).first().click();
await patient.getByText("Simulasikan pindai petugas").click();
await patient.getByText(/telah selesai/).waitFor({timeout: 15000});
await shot(patient, "06-pasien-keluar");
step("QR keluar diproses");
await simrs.bringToFront();
await simrs.getByRole("button", {name: "Tandai lengkap"}).click();
await simrs.getByText("Lengkap", {exact: true}).first().waitFor({timeout: 30000});
step("data kunjungan lengkap");

// Patient: dispute one item
await patient.bringToFront();
await patient.getByRole("button", {name: "Periksa ringkasan layanan"}).click({timeout: 30000});
await patient.getByText("Paracetamol 500 mg").first().waitFor();
await shot(patient, "07-pasien-ringkasan");
const yes = patient.getByRole("button", {name: "Sesuai", exact: true});
const no = patient.getByRole("button", {name: "Tidak sesuai", exact: true});
const total = await yes.count();
for (let i = 0; i < total - 1; i++) await yes.nth(i).click();
await no.nth(total - 1).click();
await patient.getByText("Jumlahnya berbeda").click();
await patient.getByRole("button", {name: "Tinjau respons"}).click();
await shot(patient, "08-pasien-tinjau");
await patient.getByRole("button", {name: "Kirim respons"}).click();
await patient.getByText("Respons terkirim").first().waitFor();
await shot(patient, "09-pasien-terkirim");
step("pasien mengirim tanggapan");

// SIMRS A: submit a claim with an inflated quantity
await simrs.bringToFront();
await simrs.getByRole("button", {name: /Klaim BPJS/}).first().click();
await simrs.getByRole("button", {name: /Ajukan/}).first().click();
await simrs.getByLabel("Jumlah Paracetamol 500 mg").fill("20");
await simrs.getByLabel("Nominal tagihan (Rp)").fill("215000");
await simrs.getByRole("checkbox").last().check();
await shot(simrs, "10-simrs-form-klaim");
await simrs.getByRole("button", {name: "Ajukan ke BPJS"}).click();
await simrs.getByText("Diterima BPJS").first().waitFor();
await shot(simrs, "11-simrs-klaim-terkirim");
const claimId = (await simrs.locator("h1").first().innerText()).trim();
step(`klaim diajukan: ${claimId}`);

// Verifier: check, review, decide
const verifier = await open(VERIFIER, "verifikator");
await verifier.getByRole("button", {name: "Masuk", exact: true}).click();
await verifier.getByText(claimId).first().waitFor({timeout: 15000});
await shot(verifier, "12-verifikator-klaim");
await verifier.locator("div").filter({hasText: claimId}).filter({has: verifier.getByRole("button", {name: "Periksa"})}).last().getByRole("button", {name: "Periksa"}).click();
await verifier.getByRole("button", {name: "Mulai pemeriksaan"}).click();
await verifier.getByRole("heading", {name: "Yang tidak sesuai"}).waitFor({timeout: 60000});
await verifier.getByText("Ditulis AI").waitFor({timeout: 60000});
const page = await verifier.locator("main").innerText();
if (/kunjungan yang sama-sama cocok/.test(page)) problems.push("klaim satu kunjungan dianggap ambigu");
for (const raw of ["QUANTITY_MISMATCH", "UNIQUE_MATCH", "R004", "PROC-1", "MED-1", "DX-1"]) if (page.includes(raw)) problems.push(`kode mentah di layar: ${raw}`);
await shot(verifier, "13-verifikator-tinjau");
await verifier.screenshot({path: `${SHOTS}/14-verifikator-tinjau-penuh.png`, fullPage: true});
step("verifikator melihat Ringkasan AI");
await verifier.getByRole("button", {name: "Ambil kasus ini"}).click();
await verifier.getByText("Minta klarifikasi").first().click();
await verifier.getByPlaceholder(/dasar tindak lanjut/).fill("Minta penjelasan faskes soal selisih jumlah obat.");
await verifier.getByRole("button", {name: "Simpan tindak lanjut"}).click();
await verifier.getByText(/Tindak lanjut tersimpan/).waitFor({timeout: 15000});
await shot(verifier, "15-verifikator-tersimpan");
step("tindak lanjut tersimpan");

console.log(problems.length ? `MASALAH:\n${problems.join("\n")}` : "TANPA ERROR BROWSER");
await browser.close();
process.exit(problems.length ? 1 : 0);
