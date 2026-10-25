export type Encounter = {
  encounter_id: string;
  facility_display_name: string;
  status: string;
  started_at: string;
  check_in_successful: boolean;
  check_out_successful: boolean;
  confirmation_status: "NOT_AVAILABLE";
};

const API = `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18080"}/api/v1`;

async function request<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init?.headers},
  });
  if (!response.ok) {
    const problem = await response.json();
    throw new Error(problem.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

export function listEncounters(token: string): Promise<{items: Encounter[]}> {
  return request("/patient/encounters", token);
}

export function issueQr(token: string, purpose: "CHECK_IN" | "CHECK_OUT", encounterId?: string): Promise<{token: string; expires_at: string; ttl_seconds: number}> {
  return request("/patient/qr-tokens", token, {method: "POST", body: JSON.stringify({purpose, encounter_id: encounterId ?? null, facility_hint: "HOSP-DEMO-001"})});
}
