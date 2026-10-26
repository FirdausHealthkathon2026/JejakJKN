import {expect, test} from "@playwright/test";

async function login(page: import("@playwright/test").Page, username: string, password: string) {
  await page.getByLabel("Username or email").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {name: "Sign In"}).click();
}

test("patient, SIMRS, verifier, and review interfaces complete one synthetic journey", async ({browser}) => {
  const patientContext = await browser.newContext();
  const simrsContext = await browser.newContext();
  const verifierContext = await browser.newContext();
  const patient = await patientContext.newPage();
  const simrs = await simrsContext.newPage();
  const verifier = await verifierContext.newPage();

  await patient.goto("http://localhost:5173");
  await login(patient, "patient01", "synthetic-patient-01");
  await expect(patient.getByRole("heading", {name: "JejakJKN Pasien"})).toBeVisible();
  await patient.getByRole("button", {name: "Tampilkan QR Masuk"}).click();
  const checkInQr = await patient.getByLabel("Token QR untuk simulator").inputValue();

  await simrs.goto("http://localhost:5174");
  await simrs.getByLabel("Token QR").fill(checkInQr);
  await simrs.getByRole("button", {name: "Scan Masuk"}).click();
  await expect(simrs.getByText("Scan check-in berhasil.")).toBeVisible();
  const encounterId = await simrs.getByLabel("ID kunjungan").inputValue();
  await simrs.getByLabel("Sistem kode").fill("DEMO-PROCEDURE-CATALOG");
  await simrs.getByLabel("Kode", {exact: true}).fill("PROC-001");
  await simrs.getByRole("button", {name: "Simpan"}).click();
  await expect(simrs.getByText(/Catatan tersimpan lokal/)).toBeVisible();

  await patient.getByRole("button", {name: "Muat ulang status"}).click();
  await expect(patient.getByText(/OPEN/)).toBeVisible();
  await patient.getByRole("button", {name: "Tampilkan QR Keluar"}).click();
  const checkOutQr = await patient.getByLabel("Token QR untuk simulator").inputValue();
  await simrs.getByLabel("Token QR").fill(checkOutQr);
  await simrs.getByRole("button", {name: "Scan Keluar"}).click();
  await expect(simrs.getByText("Scan check-out berhasil.")).toBeVisible();
  await simrs.getByRole("button", {name: "Tandai sinkronisasi lengkap"}).click();
  await expect(simrs.getByText(/Watermark sinkronisasi lengkap/)).toBeVisible();

  await patient.getByRole("button", {name: "Muat ulang status"}).click();
  await expect(patient.getByText(/CHECKED_OUT/)).toBeVisible();
  await patient.getByRole("button", {name: "Lihat ringkasan"}).click();
  await expect(patient.getByRole("heading", {name: "Ringkasan layanan"})).toBeVisible({timeout: 15_000});
  await patient.getByRole("button", {name: "Kirim konfirmasi"}).click();
  await expect(patient.getByText(/Respons CONFIRMED tersimpan/)).toBeVisible();

  await verifier.goto("http://localhost:5175");
  await login(verifier, "verifier01", "synthetic-verifier-01");
  const claimId = `E2E-${Date.now()}`;
  await verifier.getByLabel("ID klaim").fill(claimId);
  await verifier.getByLabel("Kode prosedur").fill("PROC-NOT-RECORDED");
  await verifier.getByRole("button", {name: "Verifikasi klaim"}).click();
  await expect(verifier.getByText(/ID verifikasi:/)).toBeVisible();
  await verifier.getByRole("button", {name: "Muat hasil"}).click();
  await expect(verifier.getByRole("heading", {name: "Empat dimensi"})).toBeVisible({timeout: 15_000});
  await expect(verifier.getByText(/keputusan fraud: null/)).toBeVisible();

  for (let attempt = 0; attempt < 20; attempt++) {
    await verifier.getByRole("button", {name: "Muat antrian"}).click();
    if (await verifier.getByRole("button", {name: new RegExp(claimId)}).count()) break;
    await verifier.waitForTimeout(500);
  }
  await verifier.getByRole("button", {name: new RegExp(claimId)}).click();
  await verifier.getByRole("button", {name: "ESCALATE"}).click();
  await expect(verifier.getByText("Status: IN_REVIEW")).toBeVisible();

  await Promise.all([patientContext.close(), simrsContext.close(), verifierContext.close()]);
  expect(encounterId).toMatch(/[0-9a-f-]{36}/);
});
