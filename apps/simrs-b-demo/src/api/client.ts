const API = import.meta.env.VITE_SIMRS_B_API_URL ?? "http://localhost:8102/api";
const CLAIM_API = import.meta.env.VITE_BPJS_CLAIM_API_URL ?? "http://localhost:8103/api";
export const FACILITY_CODE = "HOSP-DEMO-002";

const WIB = "Asia/Jakarta";
const CLAIM_ITEM_TYPE: Record<string, string> = {DIAGNOSIS: "DIAGNOSIS", PROCEDURE: "PROCEDURE", MEDICATION_DISPENSED: "MEDICATION_DISPENSE"};
const REF_PREFIX: Record<string, string> = {DIAGNOSIS: "DX", PROCEDURE: "PROC", MEDICATION_DISPENSED: "MED"};
const JENIS_BY_ITEM: Record<string, string> = {DIAGNOSIS: "DIAGNOSIS", PROCEDURE: "TINDAKAN", MEDICATION_DISPENSE: "OBAT"};

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(code);
  }
}

async function send<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {...init, headers: {"Content-Type": "application/json", ...init?.headers}});
  } catch {
    throw new ApiError(503, "DOWN");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, body.detail?.error_code ?? "DOWN");
  return body as T;
}

const request = <T,>(path: string, init?: RequestInit) => send<T>(`${API}${path}`, init);

export const fmtDate = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, day: "numeric", month: "short", year: "numeric"}).format(new Date(iso));
export const fmtLongDate = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, weekday: "long", day: "numeric", month: "short", year: "numeric"}).format(new Date(iso));
export const fmtTime = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, hour: "2-digit", minute: "2-digit", hour12: false}).format(new Date(iso)).replace(":", ".");
const fmtStamp = (iso: string | null) => (iso ? `${fmtDate(iso)}, ${fmtTime(iso)}` : "");

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapDelivery(row: any, visitId: string) {
  const isMark = row.target_path.endsWith("/sync-complete");
  const time = fmtTime(row.delivered_at ?? row.created_at);
  const st = row.status === "PENDING" && row.attempts > 0 ? "RETRYING" : row.status;
  const note = st === "DELIVERED" ? `Diterima pukul ${time}.`
    : st === "FAILED" ? "Ditolak: isinya tidak memenuhi format yang diterima JejakJKN. Periksa jumlah dan kemasan obat."
    : st === "RETRYING" ? `JejakJKN belum dapat dihubungi. Dicoba lagi otomatis (percobaan ke-${row.attempts}).`
    : "Menunggu diterima JejakJKN.";
  return {
    id: row.id, time, vid: visitId, st, note,
    what: isMark ? "Pelayanan selesai" : row.content?.display ?? "Catatan layanan",
    kind: isMark ? "Tanda semua catatan sudah dikirim" : "Catatan baru",
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapRecord(row: any, desc: (r: any) => string) {
  const record = {
    rid: row.record_id,
    jenis: row.local.jenis,
    kode: row.local.kode,
    jumlah: row.local.jumlah,
    ver: 1,
    status: row.status,
    canonical: row.canonical,
    hist: [] as unknown[],
  };
  record.hist = [{v: 1, action: "RECORDED", time: fmtTime(row.created_at), desc: desc(record), note: "", who: row.local.petugas ?? "Petugas Demo B"}];
  return record;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapVisit(row: any, desc: (r: any) => string) {
  return {
    id: row.encounter_id,
    pn: row.participant_number ?? "",
    ref: row.external_visit_reference ?? `RJ-${row.encounter_id.slice(0, 8)}`,
    startedAt: row.checked_in_at,
    endedAt: row.checked_out_at,
    inT: row.checked_in_at ? fmtTime(row.checked_in_at) : "",
    outT: row.checked_out_at ? fmtTime(row.checked_out_at) : "",
    status: row.status,
    presence: row.presence_status === "QR_VERIFIED" ? "QR" : "EXC",
    sync: row.sync_status,
    pending: row.pending,
    failed: row.failed,
    delivered: row.delivered,
    marking: false,
    records: row.records.map((r: unknown) => mapRecord(r, desc)),
    deliveries: row.deliveries.map((d: unknown) => mapDelivery(d, row.encounter_id)),
    claimId: null as string | null,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapClaim(row: any) {
  return {
    id: row.id,
    vid: row.encounter_id,
    ref: row.visit_reference ?? "—",
    visitDate: `${fmtDate(row.service_start)} · ${fmtTime(row.service_start)} – ${fmtTime(row.service_end)}`,
    pn: row.participant_number ?? row.patient_name ?? "—",
    care: row.care_type,
    amount: row.amount,
    st: row.status,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    items: row.items.map((it: any) => ({jenis: JENIS_BY_ITEM[it.item_type] ?? "TINDAKAN", kode: it.local_code ?? it.code, jumlah: it.local_quantity ?? null})),
    at: [fmtStamp(row.submitted_at), fmtStamp(row.submitted_at), fmtStamp(row.verifying_at), fmtStamp(row.done_at)],
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function loadAll(desc: (r: any) => string) {
  const [visits, claims] = await Promise.all([
    request<unknown[]>("/kunjungan"),
    send<unknown[]>(`${CLAIM_API}/claims?facility_code=${FACILITY_CODE}`).catch(() => []),
  ]);
  const bclaims = claims.map(mapClaim);
  const mapped = visits.map((v) => mapVisit(v, desc));
  for (const visit of mapped) visit.claimId = bclaims.find((claim) => claim.vid === visit.id)?.id ?? null;
  return {visits: mapped, bclaims, deliveries: mapped.flatMap((v) => v.deliveries)};
}

export function scan(mode: "IN" | "OUT", token: string, reference: string) {
  const path = mode === "IN" ? "/pindai/masuk" : "/pindai/keluar";
  return request<{encounter_id: string}>(path, {
    method: "POST",
    headers: {"Idempotency-Key": crypto.randomUUID()},
    body: JSON.stringify({token_qr: token, referensi_kunjungan: reference || null}),
  });
}

export function addRecord(encounterId: string, jenis: string, kode: string, jumlah: string | null) {
  return request(`/kunjungan/${encounterId}/catatan`, {
    method: "POST",
    headers: {"Idempotency-Key": crypto.randomUUID()},
    body: JSON.stringify({jenis, kode, jumlah, urutan: 1, id_rekam: `SIMRS-B-${crypto.randomUUID()}`}),
  });
}

export const completeSync = (encounterId: string) => request(`/kunjungan/${encounterId}/sinkronisasi-selesai`, {method: "POST"});
export const retryDelivery = (deliveryId: string) => request(`/deliveries/${deliveryId}/retry`, {method: "POST"});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function submitClaim(visit: any, draft: any, records: any[], amount: number) {
  const counters: Record<string, number> = {};
  const items = records.map((r) => {
    const {event_type: type, content} = r.canonical;
    const prefix = REF_PREFIX[type];
    counters[prefix] = (counters[prefix] ?? 0) + 1;
    const isMedication = type === "MEDICATION_DISPENSED";
    return {
      item_ref: `${prefix}-${counters[prefix]}`,
      item_type: CLAIM_ITEM_TYPE[type],
      code_system: content.code_system,
      code: content.code,
      display: content.display,
      quantity: isMedication ? content.quantity : 1,
      unit: isMedication ? content.unit : "1",
      local_code: r.kode,
      local_quantity: r.jumlah,
    };
  });
  return send<{id: string}>(`${CLAIM_API}/claims`, {
    method: "POST",
    body: JSON.stringify({
      participant_number: String(draft.pn).trim(),
      facility_code: FACILITY_CODE,
      visit_reference: visit.ref,
      encounter_id: visit.id,
      service_start: visit.startedAt,
      service_end: visit.endedAt ?? new Date().toISOString(),
      care_type: draft.care,
      amount,
      items,
    }),
  });
}
