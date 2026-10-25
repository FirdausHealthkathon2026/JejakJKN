export type Encounter = {
  encounter_id: string;
  facility_display_name: string;
  status: string;
  started_at: string;
  check_in_successful: boolean;
  check_out_successful: boolean;
  confirmation_status: "NOT_AVAILABLE";
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

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

const API = `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18080"}/api/v1`;

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init?.headers},
  });
  if (!response.ok) {
    const problem = await response.json();
    throw new ApiError(response.status, problem.error_code ?? "REQUEST_FAILED", problem.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export function listEncounters(token: string): Promise<{items: Encounter[]}> {
  return request("/patient/encounters", token);
}

export function issueQr(token: string, purpose: "CHECK_IN" | "CHECK_OUT", encounterId?: string): Promise<{token: string; expires_at: string; ttl_seconds: number}> {
  return request("/patient/qr-tokens", token, {method: "POST", body: JSON.stringify({purpose, encounter_id: encounterId ?? null, facility_hint: "HOSP-DEMO-001"})});
}

export function getCheckoutSummary(token: string, encounterId: string): Promise<CheckoutSummary> {
  return request(`/patient/encounters/${encounterId}/checkout-summary`, token);
}

export function submitPatientResponse(token: string, snapshotId: string, overallResponse: string, items: ItemResponse[]): Promise<PatientResponse> {
  return request(`/patient/checkout-summaries/${snapshotId}/responses`, token, {
    method: "POST",
    headers: {"Idempotency-Key": crypto.randomUUID()},
    body: JSON.stringify({overall_response: overallResponse, items}),
  });
}
