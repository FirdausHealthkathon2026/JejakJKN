// Turns a real verification result into the view model the design screens render.

const WIB = "Asia/Jakarta";
const FORMAT = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, ...options});

export const fmtDate = (iso: string) => FORMAT({day: "numeric", month: "short", year: "numeric"}).format(new Date(iso));
export const fmtDay = (iso: string) => FORMAT({weekday: "long", day: "numeric", month: "short", year: "numeric"}).format(new Date(iso));
export const fmtTime = (iso: string) => FORMAT({hour: "2-digit", minute: "2-digit", hour12: false}).format(new Date(iso)).replace(":", ".");
export const fmtStamp = (iso: string | null | undefined) => (iso ? `${fmtDate(iso)}, ${fmtTime(iso)}` : "—");

const A = (tone: string, title: string, text: string) => ({tone, title, text});
const C = (q: string, tone: string, a: string, note = "") => ({q, tone, a, note});
const P = (label: string, tone: string, text: string) => ({label, tone, text});
const R = (fk: boolean, fkText: string, pt: boolean | null, why = "") => ({fk, fkText, pt, why});
const Q = ["Apakah pasien datang?", "Apakah layanan tercatat?", "Sudah dipakai klaim lain?", "Apa tanggapan pasien?"];
const NOT_IN_HISTORY = "Tidak ada klaim lain di riwayat pemeriksaan JejakJKN yang memakai kunjungan atau layanan ini.";
const INFO_CODES = new Set(["CLAIM_REVERIFIED"]);
const ITEM_FINDINGS: Record<string, string> = {
  MISSING_OR_PRESCRIBED_ONLY: "tidak ada di catatan faskes",
  QUANTITY_MISMATCH: "jumlahnya berbeda",
  UNSUPPORTED_MAPPING: "kodenya belum dapat dipetakan",
};

const SHORT: Record<string, string> = {
  NO_ENCOUNTER: "Kunjungan tidak ditemukan",
  WEAK_IDENTITY: "Identitas pasien belum pasti",
  MISSING_OR_PRESCRIBED_ONLY: "Layanan yang diklaim tidak tercatat",
  QUANTITY_MISMATCH: "Jumlah berbeda",
  PATIENT_DISPUTED: "Pasien menyanggah layanan",
  TIME_INCONSISTENCY: "Waktu layanan di luar rentang klaim",
  ENCOUNTER_REUSED: "Kunjungan juga dipakai klaim lain",
  EVIDENCE_REUSED: "Catatan layanan juga dipakai klaim lain",
  STALE_OR_LATE_EVIDENCE: "Data kunjungan berubah",
  DOCUMENT_CROSS_PATIENT: "Dokumen sama muncul pada pasien lain",
  CHECKOUT_EXCEPTION: "Kehadiran pasien belum terverifikasi",
  PATIENT_NO_RESPONSE: "Pasien belum menanggapi",
  UNSUPPORTED_MAPPING: "Kode layanan belum dapat dipetakan",
};

export const shortOf = (codes: string[], matchStatus?: string) => {
  const labels = [...new Set(codes.filter((c) => !INFO_CODES.has(c)).map((c) => SHORT[c]).filter(Boolean))];
  if (matchStatus === "AMBIGUOUS_MATCH") labels.unshift("Lebih dari satu kunjungan cocok");
  return labels.join(" · ");
};

const qty = (n: unknown) => String(Number(n));

function attentionOf(claim: any, a: any, findings: any[], itemName: (ref: string) => string) {
  const out: any[] = [];
  const unitOf = (ref: string) => {
    const unit = claim.items.find((it: any) => it.ref === ref)?.unit;
    return unit ? ` ${unit}` : "";
  };
  const seen = new Set<string>();
  if (a.encounter_match_status === "AMBIGUOUS_MATCH") {
    out.push(A("warn", `Ada ${a.candidate_count} kunjungan yang sama-sama cocok`, `Klaim ini mencakup rentang waktu yang memuat ${a.candidate_count} kunjungan pasien di ${claim.facName}. Sistem tidak memilih salah satunya, jadi kunjungan yang dimaksud perlu dipastikan lewat peninjauan.`));
  }
  for (const f of findings) {
    const name = f.claim_item_ref ? itemName(f.claim_item_ref) : "";
    const facts = f.explanation_facts ?? {};
    const code = f.finding_code;
    const key = `${code}:${f.claim_item_ref ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    if (code === "NO_ENCOUNTER") out.push(A("bad", "Kunjungan tidak ditemukan", `Tidak ada catatan kunjungan peserta ini di ${claim.facName} pada ${claim.date}. Ini belum tentu berarti layanan tidak diberikan: data faskes mungkin belum terkirim, atau tanggal pada klaim berbeda dengan tanggal kunjungan.`));
    else if (code === "WEAK_IDENTITY") out.push(A("warn", "Klaim tidak memuat nomor peserta", "Klaim hanya memuat nama pasien. Nama bisa sama untuk orang berbeda, jadi tidak cukup untuk memastikan kunjungan milik siapa."));
    else if (code === "MISSING_OR_PRESCRIBED_ONLY") out.push(A("bad", `${name} tidak tercatat`, `Klaim mencantumkan ${name}, tetapi catatan ${claim.facName} untuk kunjungan ini tidak memuatnya. Ini belum tentu berarti layanan tidak diberikan: bisa jadi belum dicatat atau belum dikirim.`));
    else if (code === "QUANTITY_MISMATCH") out.push(A("bad", `Jumlah ${name} berbeda`, `Klaim mencantumkan ${qty(facts.claimed)}${unitOf(f.claim_item_ref)}, sedangkan faskes mencatat ${qty(facts.allocated)}${unitOf(f.claim_item_ref)} diserahkan.`));
    else if (code === "PATIENT_DISPUTED") out.push(A("bad", `Pasien menyanggah ${name}`, "Pasien menyatakan layanan ini tidak sesuai dengan yang diterima. Sanggahan pasien perlu ditinjau, bukan bukti otomatis bahwa layanan tidak diberikan."));
    else if (code === "TIME_INCONSISTENCY") out.push(A("warn", "Waktu layanan di luar rentang klaim", "Ada catatan layanan yang waktunya berada di luar tanggal pada klaim."));
    else if (code === "ENCOUNTER_REUSED") out.push(A("bad", `Kunjungan ini juga dipakai klaim ${(facts.conflicting_claims ?? []).join(", ")}`, "Kedua klaim menunjuk kunjungan yang sama. Tanda ini muncul di kedua klaim, termasuk klaim yang mungkin sah. Bandingkan keduanya sebelum memberi tindak lanjut."));
    else if (code === "EVIDENCE_REUSED") out.push(A("bad", "Catatan layanan juga dipakai klaim lain", "Catatan layanan yang sama sudah dipakai klaim lain."));
    else if (code === "STALE_OR_LATE_EVIDENCE") out.push(A("warn", "Data kunjungan berubah", "Faskes mengirim data setelah pemeriksaan ini. Periksa ulang untuk hasil terbaru."));
    else if (code === "DOCUMENT_CROSS_PATIENT") out.push(A("bad", "Dokumen sama muncul pada pasien lain", "Dokumen pada kunjungan ini juga tercatat pada pasien lain."));
    else if (code === "CHECKOUT_EXCEPTION") out.push(A("warn", "Kehadiran pasien tidak terverifikasi", `Kunjungan ini tercatat di ${claim.facName}, tetapi tanpa pindai QR pasien. Yang belum terbukti adalah kehadiran pasien.`));
    else if (code === "PATIENT_NO_RESPONSE") out.push(A("info", "Pasien belum menanggapi", "Pasien belum memberi tanggapan atas ringkasan layanan."));
    else if (code === "UNSUPPORTED_MAPPING") out.push(A("warn", `Kode ${name} belum dapat dipetakan`, "Kode pada catatan faskes belum ada di katalog pemetaan JejakJKN, jadi layanan ini belum bisa dibandingkan."));
    else if (code === "CLAIM_REVERIFIED") out.push(A("info", "Klaim ini sudah pernah diperiksa", "Hasil pemeriksaan sebelumnya tetap tersimpan di riwayat."));
  }
  return out;
}

const PRESENCE: Record<string, [string, string]> = {
  QR_VERIFIED: ["ok", "Masuk dan keluar tercatat dengan QR"],
  EXCEPTION_DOCUMENTED: ["warn", "Dicatat petugas lewat jalur pengecualian"],
};

function confirmationCheck(a: any, disputed: string[]) {
  if (disputed.length) return C(Q[3], "bad", `Menyanggah ${disputed.length} layanan`, `Pasien menyatakan ${disputed.join(", ")} tidak sesuai.`);
  const status = a.patient_confirmation_status;
  if (status === "CONFIRMED") return C(Q[3], "ok", "Mengonfirmasi", "Pasien mengonfirmasi semua layanan yang tercatat.");
  if (status === "NO_RESPONSE" || status === "PENDING") return C(Q[3], "neutral", "Belum menanggapi", "Pasien belum memberi tanggapan atas ringkasan layanan.");
  return C(Q[3], "neutral", "Belum dapat dipakai", "Menunggu kunjungan dipastikan.");
}

function candidateCard(claim: any, a: any, c: any, index: number, total: number) {
  const selected = c.encounter_id === a.selected_encounter_id;
  const presence = PRESENCE[c.presence_status] ?? ["warn", "Tidak terverifikasi: tanpa QR pasien"];
  const matched = c.match_state === "ELIGIBLE_COMPLETE_MATCH";
  const when = c.started_at
    ? `${fmtDay(c.started_at)} · masuk ${fmtTime(c.started_at)}${c.ended_at ? ", keluar " + fmtTime(c.ended_at) : ""}`
    : claim.date;
  const unmatched = (c.reasons ?? []).length;
  const fit = matched ? "Semua layanan cocok" : `${unmatched} layanan belum cocok`;
  const rows = [
    P("Bukti kehadiran", presence[0], presence[1]),
    P("Kecocokan layanan", matched ? "ok" : "bad", fit),
  ];
  return {
    kicker: total > 1 ? `Kunjungan ${index + 1} dari ${total}` : "Kunjungan yang dipakai",
    fac: claim.facName,
    when,
    tone: selected ? "ok" : "warn",
    status: selected ? "Dipakai untuk pemeriksaan" : total > 1 ? "Cocok, belum dipilih" : "Tidak dipakai",
    rows,
  };
}

const VERDICT = (a: any, clear: boolean, claim: any, findings: any[]): [string, string, string] => {
  if (clear) return ["ok", "Tidak ada yang perlu ditinjau", a.patient_confirmation_status === "CONFIRMED"
    ? "Kunjungan pasien ditemukan, dan semua layanan yang diklaim sesuai catatan faskes serta dikonfirmasi pasien."
    : "Kunjungan pasien ditemukan, dan semua layanan yang diklaim sesuai catatan faskes."];
  const codes = findings.map((f) => f.finding_code);
  if (a.encounter_match_status === "NO_ENCOUNTER_FOUND") return ["warn", "Perlu ditinjau", "Tidak ada catatan kunjungan pasien ini di faskes dan tanggal yang diklaim."];
  if (a.encounter_match_status === "AMBIGUOUS_MATCH") return ["warn", "Perlu ditinjau", "Ada lebih dari satu kunjungan yang sama-sama cocok. Sistem tidak memilih salah satunya."];
  if (a.encounter_match_status === "IDENTITY_INSUFFICIENT") return ["warn", "Perlu ditinjau", "Identitas pasien belum pasti, sehingga sistem tidak mengaitkan klaim ini dengan kunjungan mana pun."];
  if (codes.includes("ENCOUNTER_REUSED")) return ["warn", "Perlu ditinjau", "Kunjungan dan catatan layanannya juga dipakai oleh klaim lain."];
  if (codes.includes("CHECKOUT_EXCEPTION")) return ["warn", "Perlu ditinjau", "Layanan sesuai catatan faskes, tetapi kehadiran pasien tidak terverifikasi."];
  const issues = codes.filter((c) => ITEM_FINDINGS[c] || c === "PATIENT_DISPUTED").length;
  if (issues) return ["warn", "Perlu ditinjau", `Kunjungan pasien ditemukan, tetapi ada ${issues} hal yang tidak sesuai dengan klaim.`];
  return ["warn", "Perlu ditinjau", `Pemeriksaan menemukan hal yang perlu dilihat pada klaim di ${claim.facName}.`];
};

export function buildScenario(claim: any, a: any, detail: any) {
  if (!a) return emptyScenario();
  const findings = detail?.findings ?? (a.finding_codes ?? []).map((finding_code: string) => ({finding_code}));
  const codes: string[] = findings.map((f: any) => f.finding_code);
  const clear = !a.review_required;
  const itemName = (ref: string) => claim.items.find((it: any) => it.ref === ref)?.label ?? "Layanan";
  const selected = !!a.selected_encounter_id;
  const disputedRefs = new Set(findings.filter((f: any) => f.finding_code === "PATIENT_DISPUTED").map((f: any) => f.claim_item_ref));
  const results: any[] = detail?.items ?? [];

  let rows: any = null;
  if (selected && results.length) {
    rows = {};
    for (const item of results) {
      const unit = item.unit && item.unit !== "1" ? ` ${item.unit}` : "";
      const isDrug = String(item.item_type).startsWith("MEDICATION");
      const matched = item.match_result === "MATCHED";
      const fkText = item.match_result === "QUANTITY_MISMATCH" ? `${qty(item.allocated_evidence_quantity)}${unit} diserahkan`
        : !matched ? "Tidak tercatat"
        : isDrug ? `${qty(item.allocated_evidence_quantity)}${unit} diserahkan`
        : item.item_type === "DIAGNOSIS" ? "Tercatat" : "Tercatat dilakukan";
      const disputed = disputedRefs.has(item.claim_item_ref);
      const why = !matched ? (item.match_result === "QUANTITY_MISMATCH" ? "Jumlah berbeda" : "Tidak ada di catatan faskes") + (disputed ? " dan disanggah pasien" : "") : disputed ? "Disanggah pasien" : "";
      rows[item.claim_item_ref] = R(matched, fkText, !matched ? null : disputed ? false : true, why);
    }
  }

  const total = claim.items.length;
  const okCount = a.matched_items_count;
  const reused = codes.filter((c) => c === "ENCOUNTER_REUSED" || c === "EVIDENCE_REUSED").length > 0;
  const conflicts: string[] = a.conflicting_claims ?? [];
  const candidates = detail?.candidates ?? [];
  const presenceBad = codes.includes("CHECKOUT_EXCEPTION");

  const checks = [
    a.encounter_match_status === "NO_ENCOUNTER_FOUND" || a.encounter_match_status === "NO_SUITABLE_ENCOUNTER"
      ? C(Q[0], "bad", "Tidak ditemukan", `Tidak ada catatan kunjungan di ${claim.facName} pada ${claim.date}.`)
      : a.encounter_match_status === "AMBIGUOUS_MATCH" ? C(Q[0], "warn", `Ya, tetapi ${a.candidate_count} kali`, "Pasien tercatat datang lebih dari sekali. Belum pasti kunjungan mana yang diklaim.")
      : a.encounter_match_status === "IDENTITY_INSUFFICIENT" ? C(Q[0], "warn", "Belum pasti", "Ada kunjungan yang mirip, tetapi identitas pasien belum pasti.")
      : presenceBad ? C(Q[0], "warn", "Belum terverifikasi", "Kunjungan tercatat, tetapi tanpa QR masuk dan keluar dari pasien.")
      : C(Q[0], "ok", "Ya, datang", "Masuk dan keluar tercatat dengan QR."),
    !selected ? C(Q[1], "neutral", "Belum dinilai", "Menunggu kunjungan dipastikan.")
      : okCount === total ? C(Q[1], "ok", "Semua sesuai", `${total} dari ${total} layanan cocok dengan catatan faskes.`)
      : C(Q[1], "bad", `${okCount} dari ${total} sesuai`, results.filter((r) => r.match_result !== "MATCHED").map((r) => itemName(r.claim_item_ref)).join(", ") + " tidak sesuai."),
    reused ? C(Q[2], "bad", `Ya, ${Math.max(conflicts.length, 1)} klaim`, `${conflicts.join(", ")} memakai kunjungan atau catatan layanan yang sama.`)
      : C(Q[2], "ok", "Tidak", NOT_IN_HISTORY),
    confirmationCheck(a, [...disputedRefs].map((ref) => itemName(String(ref)))),
  ];

  const visits = candidates.map((c: any, i: number) => candidateCard(claim, a, c, i, candidates.length));
  const attention = attentionOf(claim, a, findings, itemName);
  return {
    clear,
    verdict: VERDICT(a, clear, claim, findings),
    short: clear ? "Semua sesuai" : shortOf(codes, a.encounter_match_status) || "Perlu ditinjau",
    attention,
    checks,
    rows,
    vt: candidates.length > 1
      ? [`Kunjungan yang cocok (${candidates.length})`, "Semua kunjungan ini cocok dengan klaim. Sistem tidak memilih salah satunya."]
      : candidates.length ? ["Kunjungan yang dipakai", "Catatan kunjungan ini dipakai untuk membandingkan layanan."]
      : ["Kunjungan pasien", "Tidak ada catatan kunjungan yang cocok dengan pasien, faskes, dan tanggal pada klaim ini."],
    visits,
  };
}

export function emptyScenario() {
  return {
    clear: false, verdict: ["neutral", "Belum diperiksa", "Klaim ini belum diperiksa."] as [string, string, string], short: "", attention: [] as any[],
    checks: Q.map((q) => C(q, "neutral", "Belum dinilai")), rows: null, vt: ["Kunjungan pasien", ""], visits: [] as any[],
  };
}

const SESUAI = "YANG SESUAI:";
const TIDAK = "YANG TIDAK SESUAI:";

export function narrativeOf(narrative: any) {
  if (!narrative) return null;
  const summary: string[] = narrative.summary ?? [];
  const strip = (line: string, prefix: string) => line.slice(prefix.length).trim();
  const bad = summary.filter((l) => l.startsWith(TIDAK)).map((l) => strip(l, TIDAK));
  const ok = summary.filter((l) => l.startsWith(SESUAI)).map((l) => strip(l, SESUAI));
  const plainLines = summary.filter((l) => !l.startsWith(TIDAK) && !l.startsWith(SESUAI));
  return {ok: ok.length ? ok : plainLines, bad, q: narrative.questions ?? [], l: narrative.limitations ?? []};
}

const DECISION_TITLE: Record<string, string> = {NO_ACTION: "Klaim wajar", REQUEST_CLARIFICATION: "Minta klarifikasi", ESCALATE: "Teruskan ke supervisor", CLOSE_REVIEW: "Tutup peninjauan"};

export function caseHistory(row: any) {
  const opened = {at: fmtStamp(row.opened_at), who: "Sistem", kind: "open", title: "Kasus dibuka otomatis", text: "Pemeriksaan menemukan hal yang perlu ditinjau.", code: ""};
  const events = (row.events ?? []).map((e: any) => {
    const at = fmtStamp(e.created_at);
    if (e.kind === "ASSIGN") return {at, who: e.actor_name, kind: "assign", title: e.detail === e.actor_name ? "Mengambil kasus ini" : `Menugaskan ke ${e.detail}`, text: "", code: ""};
    if (e.kind === "ACCESS") return {at, who: e.actor_name, kind: "access", title: "Membuka paket bukti", text: "Tujuan: pemeriksaan integritas klaim.", code: ""};
    return {at, who: e.actor_name, kind: "decision", title: DECISION_TITLE[e.code] ?? "Tindak lanjut", text: e.detail ?? "", code: e.code};
  });
  return [opened, ...events];
}

export function mapCase(row: any) {
  return {
    id: row.id,
    claimId: row.claim_id,
    verificationId: row.verification_id,
    opened: fmtStamp(row.opened_at),
    state: row.state,
    stale: row.is_stale,
    owner: row.assigned_name,
    findingCodes: row.finding_codes ?? [],
    ai: {method: row.narrative_method ?? "LLM", at: fmtStamp(row.narrative_generated_at ?? row.opened_at), ready: !!row.narrative, text: narrativeOf(row.narrative)},
    history: caseHistory(row),
  };
}

const KIND: Record<string, string> = {DIAGNOSIS: "Diagnosis", PROCEDURE: "Tindakan", MEDICATION: "Obat", MEDICATION_DISPENSE: "Obat"};

export function mapClaim(row: any) {
  const start = row.service_start;
  const end = row.service_end;
  const days = Math.max(1, Math.round((new Date(fmtIsoDay(end)).getTime() - new Date(fmtIsoDay(start)).getTime()) / 86400000) + 1);
  return {
    id: row.id,
    rel: row.relationship,
    relId: row.related_claim_id ?? "",
    pn: row.participant_number ?? "",
    name: row.patient_name ?? "",
    facName: row.facility_name,
    date: days > 1 ? `${fmtDate(start)} – ${fmtDate(end)}` : fmtDate(start),
    days,
    amount: row.amount,
    src: row.source,
    file: row.file_name,
    submittedAt: row.submitted_at,
    items: row.items.map((it: any) => ({ref: it.item_ref, kind: KIND[it.item_type] ?? "Layanan", label: it.display, qty: it.unit === "1" ? "" : String(Number(it.quantity)), unit: it.unit === "1" ? "" : it.unit})),
    raw: row,
  };
}

const fmtIsoDay = (iso: string) => new Intl.DateTimeFormat("en-CA", {timeZone: WIB}).format(new Date(iso));
