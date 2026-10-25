const API = "http://localhost:8101/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {...init, headers: {"Content-Type": "application/json", ...init?.headers}});
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body));
  return body as T;
}

export type ClinicalRecord = {record_id: string; event_type: string; external_record_id: string; version: number; status: string};
export type SyncStatus = {encounter_id: string; sync_status: string; last_error: string | null; pending: number; failed: number; delivered: number; records: ClinicalRecord[]};
export type ClinicalInput = {event_type: string; code_system: string; code: string; display: string; quantity?: string; unit?: string};

export function scan(kind: "check-in" | "check-out", qrToken: string) {
  return request<{encounter_id: string}>(`/scan/${kind}`, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify({qr_token: qrToken, scanner_external_id: "SIMRS-A-SCANNER-01", external_visit_reference: kind === "check-in" ? `VISIT-${Date.now()}` : null})});
}

export function createClinicalEvent(encounterId: string, input: ClinicalInput) {
  return request<{record_id: string}>(`/visits/${encounterId}/clinical-events`, {method: "POST", body: JSON.stringify(input)});
}

export function getSyncStatus(encounterId: string) { return request<SyncStatus>(`/visits/${encounterId}/sync-status`); }
export function completeSync(encounterId: string) { return request(`/visits/${encounterId}/sync-complete`, {method: "POST"}); }

export function cancelRecord(recordId: string, reason: string) {
  return request(`/clinical-records/${recordId}/cancellations`, {method: "POST", body: JSON.stringify({cancel_reason: reason})});
}

export function correctRecord(recordId: string, input: ClinicalInput, reason: string) {
  return request(`/clinical-records/${recordId}/corrections`, {method: "POST", body: JSON.stringify({code_system: input.code_system, code: input.code, display: input.display, quantity: input.quantity || null, unit: input.unit || null, change_reason: reason})});
}
