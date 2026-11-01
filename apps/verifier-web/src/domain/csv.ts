// Reads the claim CSV (one row per service) into claims, keeping row-level problems for the preview.
import names from "./code_names.json";

const ITEM_TYPE: Record<string, [string, string]> = {diagnosis: ["DIAGNOSIS", "DX"], tindakan: ["PROCEDURE", "PROC"], obat: ["MEDICATION_DISPENSE", "MED"]};
const REQUIRED = ["nomor_klaim", "kode_faskes", "tanggal_mulai", "tanggal_selesai", "jenis_layanan", "sistem_kode", "kode"];
const FACILITIES: Record<string, string> = {"HOSP-DEMO-001": "RS Demo Satu", "HOSP-DEMO-002": "RS Demo Dua"};
const CATALOG = names as Record<string, string>;

export type Issue = {line: string; claim: string; what: string; text: string};
export type ParsedCsv = {fileName: string; rowCount: number; claims: any[]; issues: Issue[]; skipped: string[]; missingColumns: string[]};

function splitLine(line: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { cells.push(cell); cell = ""; }
    else cell += c;
  }
  cells.push(cell);
  return cells.map((v) => v.trim());
}

const dateText = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: "UTC", day: "numeric", month: "short", year: "numeric"}).format(new Date(`${iso}T00:00:00Z`));

export function parseClaimsCsv(fileName: string, text: string): ParsedCsv {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
  const header = splitLine(lines[0] ?? "").map((h) => h.toLowerCase());
  const missingColumns = REQUIRED.filter((c) => !header.includes(c));
  const issues: Issue[] = [];
  if (missingColumns.length) return {fileName, rowCount: 0, claims: [], issues, skipped: [], missingColumns};

  const byClaim = new Map<string, any>();
  const skipped = new Set<string>();
  lines.slice(1).forEach((line, index) => {
    const lineNo = index + 2;
    const cells = splitLine(line);
    const row = Object.fromEntries(header.map((h, i) => [h, cells[i] ?? ""]));
    const id = row.nomor_klaim;
    const fail = (what: string, detail: string) => {
      issues.push({line: `Baris ${lineNo}`, claim: id, what, text: detail});
      skipped.add(id);
    };
    if (!id) { issues.push({line: `Baris ${lineNo}`, claim: "—", what: "Nomor klaim kosong.", text: "Kolom nomor_klaim wajib diisi."}); return; }
    if (!FACILITIES[row.kode_faskes]) fail("Kode faskes tidak dikenali.", `Kode ${row.kode_faskes || "kosong"} tidak ada di daftar faskes.`);
    if (!row.nomor_peserta && !row.nama_pasien) fail("Identitas pasien kosong.", "Isi nomor_peserta atau nama_pasien.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.tanggal_mulai) || !/^\d{4}-\d{2}-\d{2}$/.test(row.tanggal_selesai)) fail("Format tanggal salah.", "Gunakan format TTTT-BB-HH.");
    else if (row.tanggal_selesai < row.tanggal_mulai) fail("Tanggal terbalik.", `Tanggal selesai (${dateText(row.tanggal_selesai)}) lebih awal dari tanggal mulai (${dateText(row.tanggal_mulai)}).`);
    const type = ITEM_TYPE[row.jenis_layanan.toLowerCase()];
    if (!type) fail("Jenis layanan tidak dikenali.", "Isi Diagnosis, Tindakan, atau Obat.");
    const quantity = row.jumlah === "" || row.jumlah === undefined ? 1 : Number(row.jumlah);
    if (!(quantity > 0)) fail("Jumlah tidak valid.", `Kolom jumlah berisi ${row.jumlah}. Jumlah harus lebih dari 0.`);

    let claim = byClaim.get(id);
    if (!claim) {
      claim = {
        id, revision: row.revisi_klaim || "1", participant_number: row.nomor_peserta || null, patient_name: row.nama_pasien || null,
        facility_code: row.kode_faskes, service_start: `${row.tanggal_mulai}T00:00:00+07:00`, service_end: `${row.tanggal_selesai}T23:59:59+07:00`,
        care_type: row.tanggal_mulai === row.tanggal_selesai ? "RJ" : "RI", amount: 0, items: [], firstLine: lineNo,
      };
      byClaim.set(id, claim);
    } else if ((row.nomor_peserta || null) !== claim.participant_number) {
      fail("Data pasien berbeda.", `Nomor peserta di baris ini berbeda dengan baris ${claim.firstLine}, padahal nomor klaimnya sama.`);
    }
    if (row.nominal_klaim) claim.amount = Number(row.nominal_klaim);
    if (type) {
      const count = claim.items.filter((it: any) => it.item_type === type[0]).length + 1;
      claim.items.push({
        item_ref: `${type[1]}-${count}`, item_type: type[0], code_system: row.sistem_kode, code: row.kode,
        display: CATALOG[`${row.sistem_kode}:${row.kode}`] || CATALOG[row.kode] || "Layanan pada klaim",
        quantity, unit: type[0] === "MEDICATION_DISPENSE" ? row.satuan || "1" : "1",
      });
    }
  });

  const claims: any[] = [];
  for (const claim of byClaim.values()) {
    const {firstLine, ...input} = claim;
    if (!(input.amount > 0)) {
      issues.push({line: `Baris ${firstLine}`, claim: input.id, what: "Nominal kosong.", text: "Isi kolom nominal_klaim pada salah satu baris klaim."});
      skipped.add(input.id);
    }
    if (!skipped.has(input.id)) claims.push(input);
  }
  return {fileName, rowCount: lines.length - 1, claims, issues, skipped: [...skipped], missingColumns};
}
