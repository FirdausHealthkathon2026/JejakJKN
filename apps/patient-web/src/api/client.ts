export type Encounter = {
  encounter_id: string;
  facility_display_name: string;
  service_type: string;
  status: string;
  presence_status: string;
  started_at: string;
  ended_at: string | null;
  check_in_successful: boolean;
  check_out_successful: boolean;
};

export type SummaryItem = {
  evidence_id: string;
  evidence_version_id: string;
  version: number;
  kind: "DIAGNOSIS" | "PROCEDURE" | "MEDICATION_DISPENSE";
  description: string;
  quantity: string | null;
  unit: string | null;
  recorded_status: string;
};

export type CheckoutSummary = {
  snapshot_id: string;
  encounter_id: string;
  status: "READY";
  evidence_revision: number;
  presented_at: string | null;
  items: SummaryItem[];
};

export type ItemResponse = {
  evidence_id: string;
  response: "CONFIRMED" | "DISPUTED";
  reason?: "SERVICE_NOT_RECEIVED" | "MEDICATION_NOT_RECEIVED" | "QUANTITY_DIFFERENT" | "OTHER";
  note?: string;
};

export type PatientResponse = {
  response_id: string;
  snapshot_id: string;
  overall_response: string;
  submitted_at: string;
  snapshot_status: string;
};

export type Visit = {
  id: string;
  isOpen: boolean;
  fac: string;
  date: string;
  inT: string;
  outT: string;
  ref: string;
  presence: "QR" | "EXC" | "UNV";
  care?: string;
  conf: string;
  sent?: string;
  month: string;
  rev: number;
  deadline: string;
  snapshotId: string;
  items: {id: string; kind: SummaryItem["kind"]; name: string; qty: string}[];
};

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

const API = `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18080"}/api/v1`;
const SIMRS_A_API = import.meta.env.VITE_SIMRS_A_API_URL ?? "http://localhost:8101/api";
const RESPONSE_WINDOW_HOURS = 72;
const UNIT_LABELS: Record<string, string> = {bottle: "botol", service: "layanan"};
const KIND_ORDER = ["DIAGNOSIS", "PROCEDURE", "MEDICATION_DISPENSE"];
const WIB = "Asia/Jakarta";
const TERMINAL = new Set(["CONFIRMED", "PARTIALLY_DISPUTED", "DISPUTED", "NO_RESPONSE"]);

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init?.headers},
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new ApiError(response.status, problem.error_code ?? "REQUEST_FAILED", problem.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export function listEncounters(token: string): Promise<{items: Encounter[]}> {
  return request("/patient/encounters?limit=50", token);
}

export function issueQr(token: string, purpose: "CHECK_IN" | "CHECK_OUT", encounterId?: string): Promise<{token: string; expires_at: string; ttl_seconds: number}> {
  return request("/patient/qr-tokens", token, {method: "POST", body: JSON.stringify({purpose, encounter_id: encounterId ?? null})});
}

export function getCheckoutSummary(token: string, encounterId: string): Promise<CheckoutSummary> {
  return request(`/patient/encounters/${encounterId}/checkout-summary`, token);
}

export function getPatientResponse(token: string, snapshotId: string): Promise<PatientResponse> {
  return request(`/patient/checkout-summaries/${snapshotId}/response`, token);
}

export function submitPatientResponse(token: string, snapshotId: string, overallResponse: string, items: ItemResponse[]): Promise<PatientResponse> {
  return request(`/patient/checkout-summaries/${snapshotId}/responses`, token, {
    method: "POST",
    headers: {"Idempotency-Key": crypto.randomUUID()},
    body: JSON.stringify({overall_response: overallResponse, items}),
  });
}

// Demo shortcut behind the "Simulasikan pindai petugas" button: the real SIMRS A scan endpoint.
export async function staffScan(purpose: "CHECK_IN" | "CHECK_OUT", qrToken: string): Promise<void> {
  const kind = purpose === "CHECK_IN" ? "check-in" : "check-out";
  const response = await fetch(`${SIMRS_A_API}/scan/${kind}`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID()},
    body: JSON.stringify({qr_token: qrToken}),
  });
  if (!response.ok) throw new ApiError(response.status, "SCAN_FAILED", "Scan failed");
}

const part = (iso: string, options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("id-ID", {timeZone: WIB, ...options}).format(new Date(iso));

export const formatDate = (iso: string) => part(iso, {day: "numeric", month: "short", year: "numeric"});
export const formatTime = (iso: string) => part(iso, {hour: "2-digit", minute: "2-digit", hour12: false}).replace(":", ".");
export const formatDateTime = (iso: string) => `${formatDate(iso)}, ${formatTime(iso)} WIB`;

export function formatQuantity(quantity: string | null, unit: string | null): string {
  if (quantity === null || !unit || unit === "service" || unit === "code") return "";
  return `${Number(quantity)} ${UNIT_LABELS[unit] ?? unit}`;
}

function shell(encounter: Encounter): Visit {
  const ended = encounter.ended_at;
  return {
    id: encounter.encounter_id,
    isOpen: encounter.status === "OPEN",
    fac: encounter.facility_display_name,
    date: formatDate(encounter.started_at),
    inT: formatTime(encounter.started_at),
    outT: ended ? formatTime(ended) : "",
    ref: `JJK-${encounter.encounter_id.slice(0, 4).toUpperCase()}-${encounter.encounter_id.slice(4, 8).toUpperCase()}`,
    presence: encounter.presence_status === "QR_VERIFIED" ? "QR" : encounter.presence_status.includes("EXCEPTION") ? "EXC" : "UNV",
    care: encounter.service_type === "INPATIENT" ? "Rawat inap" : undefined,
    conf: "INCOMPLETE",
    month: part(encounter.started_at, {month: "long", year: "numeric"}),
    rev: 1,
    deadline: ended ? formatDate(new Date(new Date(ended).getTime() + RESPONSE_WINDOW_HOURS * 3600e3).toISOString()) + ", " + formatTime(ended) : "",
    snapshotId: "",
    items: [],
  };
}

export async function loadVisit(token: string, encounter: Encounter, known?: Visit): Promise<Visit> {
  if (known && TERMINAL.has(known.conf)) return known;
  const visit = shell(encounter);
  if (!encounter.ended_at) return visit;
  try {
    const summary = await getCheckoutSummary(token, encounter.encounter_id);
    visit.snapshotId = summary.snapshot_id;
    visit.rev = summary.evidence_revision;
    visit.items = [...summary.items]
      .sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
      .map((item) => ({id: item.evidence_id, kind: item.kind, name: item.description, qty: formatQuantity(item.quantity, item.unit)}));
    visit.conf = "READY";
  } catch (error) {
    if (!(error instanceof ApiError) || error.status === 401) throw error;
    visit.conf = error.code.includes("NO_RESPONSE") ? "NO_RESPONSE" : "INCOMPLETE";
    return visit;
  }
  try {
    const answer = await getPatientResponse(token, visit.snapshotId);
    visit.conf = answer.overall_response;
    visit.sent = formatDateTime(answer.submitted_at);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
  }
  return visit;
}
