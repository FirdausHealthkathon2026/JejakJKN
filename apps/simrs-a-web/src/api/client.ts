const API = import.meta.env.VITE_SIMRS_A_API_URL ?? "http://localhost:8101/api";
const CLAIM_API = import.meta.env.VITE_BPJS_CLAIM_API_URL ?? "http://localhost:8103/api";
export const FACILITY_CODE = "HOSP-DEMO-001";

// The form speaks hospital terms; JejakJKN only accepts mapped catalogs.
const CATALOG_BY_TYPE: Record<string, string> = {
  DIAGNOSIS: "DEMO-DIAGNOSIS-CATALOG",
  PROCEDURE: "DEMO-PROCEDURE-CATALOG",
  MEDICATION_PRESCRIBED: "DEMO-MEDICATION-CATALOG",
  MEDICATION_DISPENSED: "DEMO-MEDICATION-CATALOG",
  STAGE_COMPLETION: "DEMO-STAGE-CATALOG",
};
const CLAIM_ITEM_TYPE: Record<string, string> = {
  DIAGNOSIS: "DIAGNOSIS",
  PROCEDURE: "PROCEDURE",
  MEDICATION_PRESCRIBED: "MEDICATION",
  MEDICATION_DISPENSED: "MEDICATION_DISPENSE",
};
const REF_PREFIX: Record<string, string> = {DIAGNOSIS: "DX", PROCEDURE: "PROC", MEDICATION_PRESCRIBED: "MED", MEDICATION_DISPENSED: "MED"};
const WIB = "Asia/Jakarta";

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
    throw new ApiError(503, "HTTP 503");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, body.detail?.error_code ?? `HTTP ${response.status}`);
  return body as T;
}

const request = <T,>(path: string, init?: RequestInit) => send<T>(`${API}${path}`, init);

export const fmtDate = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, day: "numeric", month: "short", year: "numeric"}).format(new Date(iso));
export const fmtLongDate = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, weekday: "long", day: "numeric", month: "short", year: "numeric"}).format(new Date(iso));
export const fmtTime = (iso: string) => new Intl.DateTimeFormat("id-ID", {timeZone: WIB, hour: "2-digit", minute: "2-digit", hour12: false}).format(new Date(iso)).replace(":", ".");
export const fmtStamp = (iso: string | null) => (iso ? `${fmtDate(iso)}, ${fmtTime(iso)}` : "");

const plainQty = (quantity: unknown) => (quantity === null || quantity === undefined || quantity === "" ? "" : String(Number(quantity)));
const formCodeSystem = (type: string) => (type === "DIAGNOSIS" ? "ICD-10" : "LOCAL");

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapRecord(row: any) {
  const latest = [...row.history].reverse().find((h) => h.content) ?? {content: {}};
  return {
    rid: row.record_id,
    type: row.event_type,
    cs: formCodeSystem(row.event_type),
    code: latest.content.code ?? "",
    display: latest.content.display ?? "",
    qty: plainQty(latest.content.quantity),
    unit: latest.content.unit ?? "",
    ver: row.version,
    status: row.status,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    hist: row.history.map((h: any) => ({
      v: h.version,
      action: h.action,
      time: fmtTime(h.created_at),
      desc: [h.content?.display ?? latest.content.display, h.content?.quantity ? `${plainQty(h.content.quantity)} ${h.content.unit ?? ""}` : ""].filter(Boolean).join(" · "),
      note: h.note ?? "",
    })),
  };
}

const KIND_TEXT: Record<string, string> = {
  DIAGNOSIS: "diagnosis", PROCEDURE: "tindakan", MEDICATION_PRESCRIBED: "resep obat", MEDICATION_DISPENSED: "obat diserahkan", STAGE_COMPLETION: "tahap selesai",
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapDelivery(row: any, visitId: string) {
  const isMark = row.target_path.endsWith("/sync-complete");
  const isCorrection = row.target_path.endsWith("/corrections");
  const isCancel = row.target_path.endsWith("/cancellations");
  const time = fmtTime(row.delivered_at ?? row.created_at);
  const st = row.status === "PENDING" && row.attempts > 0 ? "RETRYING" : row.status;
  const note = st === "DELIVERED" ? `Diterima pukul ${time}.`
    : st === "FAILED" ? "Ditolak: isinya tidak memenuhi format yang diterima JejakJKN."
    : st === "RETRYING" ? `JejakJKN belum dapat dihubungi. Dicoba lagi otomatis (percobaan ke-${row.attempts}).`
    : "Menunggu jawaban JejakJKN.";
  return {
    id: row.id,
    time,
    vid: visitId,
    what: isMark ? "Pelayanan selesai" : row.content?.display ?? "Catatan layanan",
    kind: isMark ? "Tanda semua catatan sudah dikirim" : isCorrection ? `Koreksi · versi ${row.record_version}` : isCancel ? `Pembatalan · versi ${row.record_version}` : `Catatan baru · ${KIND_TEXT[row.event_type] ?? "layanan"}`,
    st,
    note,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapVisit(row: any) {
  return {
    id: row.encounter_id,
    pn: row.participant_number ?? "",
    ref: row.external_visit_reference ?? `VISIT-${row.encounter_id.slice(0, 8)}`,
    enc: row.encounter_id,
    startedAt: row.checked_in_at,
    endedAt: row.checked_out_at,
    inT: row.checked_in_at ? fmtTime(row.checked_in_at) : "",
    outT: row.checked_out_at ? fmtTime(row.checked_out_at) : "",
    status: row.status,
    presence: row.presence_status,
    sync: row.sync_status,
    err: row.last_error,
    pending: row.pending,
    failed: row.failed,
    delivered: row.delivered,
    marking: false,
    records: row.records.map(mapRecord),
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
    items: row.items.map((it: any) => ({
      type: it.item_type === "MEDICATION_DISPENSE" ? "MEDICATION_DISPENSED" : it.item_type === "MEDICATION" ? "MEDICATION_PRESCRIBED" : it.item_type,
      cs: formCodeSystem(it.item_type), code: it.code, display: it.display, qty: it.unit === "1" ? "" : plainQty(it.quantity), unit: it.unit === "1" ? "" : it.unit,
    })),
    at: [fmtStamp(row.submitted_at), fmtStamp(row.submitted_at), fmtStamp(row.verifying_at), fmtStamp(row.done_at)],
  };
}

export async function loadAll() {
  const [visits, claims] = await Promise.all([
    request<unknown[]>("/visits"),
    send<unknown[]>(`${CLAIM_API}/claims?facility_code=${FACILITY_CODE}`).catch(() => []),
  ]);
  const bclaims = claims.map(mapClaim);
  const mapped = visits.map(mapVisit);
  for (const visit of mapped) visit.claimId = bclaims.find((claim) => claim.vid === visit.id)?.id ?? null;
  return {visits: mapped, bclaims, deliveries: mapped.flatMap((v) => v.deliveries)};
}

export function scan(kind: "check-in" | "check-out", qrToken: string) {
  const reference = kind === "check-in" ? `VISIT-${Date.now()}` : undefined;
  return request<{encounter_id: string}>(`/scan/${kind}`, {
    method: "POST",
    headers: {"Idempotency-Key": crypto.randomUUID()},
    body: JSON.stringify({qr_token: qrToken, scanner_external_id: "SIMRS-A-SCANNER-01", external_visit_reference: reference}),
  });
}

export function createClinicalEvent(encounterId: string, form: {type: string; code: string; display: string; qty: string; unit: string; stage: string}) {
  return request(`/visits/${encounterId}/clinical-events`, {
    method: "POST",
    body: JSON.stringify({
      event_type: form.type,
      code_system: CATALOG_BY_TYPE[form.type],
      code: form.code.trim(),
      display: form.display.trim(),
      quantity: form.qty || null,
      unit: form.unit || null,
      stage_completion: form.type === "STAGE_COMPLETION" ? form.stage : null,
    }),
  });
}

export function correctRecord(recordId: string, type: string, dialog: {code: string; display: string; qty: string; unit: string; reason: string}) {
  return request(`/clinical-records/${recordId}/corrections`, {
    method: "POST",
    body: JSON.stringify({code_system: CATALOG_BY_TYPE[type], code: dialog.code.trim(), display: dialog.display.trim(), quantity: dialog.qty || null, unit: dialog.unit || null, change_reason: dialog.reason.trim()}),
  });
}

export function cancelRecord(recordId: string, reason: string) {
  return request(`/clinical-records/${recordId}/cancellations`, {method: "POST", body: JSON.stringify({cancel_reason: reason.trim()})});
}

export const completeSync = (encounterId: string) => request(`/visits/${encounterId}/sync-complete`, {method: "POST"});
export const retryDelivery = (deliveryId: string) => request(`/deliveries/${deliveryId}/retry`, {method: "POST"});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function submitClaim(visit: any, draft: any, records: any[], amount: number) {
  const counters: Record<string, number> = {};
  const items = records.map((r) => {
    const prefix = REF_PREFIX[r.type];
    counters[prefix] = (counters[prefix] ?? 0) + 1;
    const qty = draft.sel[r.rid].qty;
    return {
      item_ref: `${prefix}-${counters[prefix]}`,
      item_type: CLAIM_ITEM_TYPE[r.type],
      code_system: CATALOG_BY_TYPE[r.type],
      code: r.code,
      display: r.display,
      quantity: qty || 1,
      unit: qty ? r.unit : "1",
    };
  });
  return send<{id: string}>(`${CLAIM_API}/claims`, {
    method: "POST",
    body: JSON.stringify({
      participant_number: String(draft.pn).trim(),
      facility_code: FACILITY_CODE,
      visit_reference: visit.ref,
      encounter_id: visit.enc,
      service_start: visit.startedAt,
      service_end: visit.endedAt ?? new Date().toISOString(),
      care_type: draft.care,
      amount,
      items,
    }),
  });
}
