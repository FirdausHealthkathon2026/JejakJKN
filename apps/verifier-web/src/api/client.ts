export type Assessment = {
  verification_id: string; run_id: string; status: string; claim_id: string;
  encounter_match_status: string; selected_encounter_id: string | null; identity_assurance: string;
  evidence_reconciliation_status: string; duplicate_assessment_status: string;
  patient_confirmation_status: string; review_required: boolean; final_fraud_decision: null; data_freshness: string;
};
export type Candidate = {encounter_id: string; match_state: string; identity_assurance: string; presence_status: string; patient_confirmation_status: string; reasons: string[]};
export type Finding = {rule_id: string; severity: string; finding_code: string; claim_item_ref: string | null; limitations: string};

const API = `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18080"}/api/v1/verifications`;
async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {...init, headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init?.headers}});
  if (!response.ok) { const problem = await response.json(); throw new Error(problem.detail ?? "Request failed"); }
  return response.json() as Promise<T>;
}
export const submitVerification = (token: string, body: object) => request<{verification_id: string}>("", token, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify(body)});
export const getAssessment = (token: string, id: string) => request<Assessment>(`/${id}`, token);
export const getCandidates = (token: string, id: string) => request<Candidate[]>(`/${id}/candidates`, token);
export const getFindings = (token: string, id: string) => request<Finding[]>(`/${id}/findings`, token);
export const recheck = (token: string, id: string) => request(`/${id}/re-evaluate`, token, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: "{}"});
