import {expect, test} from "@playwright/test";

test("the four current web interfaces load without browser errors", async ({browser}) => {
  const context = await browser.newContext();
  const errors: string[] = [];
  const pages = await Promise.all([
    ["http://localhost:5173", "Catat kunjungan Anda dengan QR"],
    ["http://localhost:5174", "Pasien hari ini"],
    ["http://localhost:5175", "Masuk sebagai verifikator"],
    ["http://localhost:5176", "Pasien hari ini"],
  ].map(async ([url, text]) => {
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(`${url}: ${error.message}`));
    await page.goto(url);
    await expect(page.getByText(text).first()).toBeVisible();
    return page;
  }));

  await pages[1].getByRole("button", {name: "Pindai QR", exact: true}).click();
  await expect(pages[1].getByRole("button", {name: "Buka kamera"})).toBeVisible();
  await pages[3].getByRole("button", {name: "Pindai QR", exact: true}).click();
  await expect(pages[3].getByRole("button", {name: "Pilih dari galeri"})).toBeVisible();
  expect(errors).toEqual([]);
  await context.close();
});
