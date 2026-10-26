import {LocalClinicalInput, SyncStatus} from "../types";

const API = "http://localhost:8102/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {...init, headers: {"Content-Type": "application/json", ...init?.headers}});
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body));
  return body as T;
}

export const checkIn = (token: string) => request<{encounter_id: string}>("/pindai/masuk", {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify({token_qr: token, referensi_kunjungan: `RSB-${Date.now()}`})});
export const addRecord = (encounterId: string, input: LocalClinicalInput) => request(`/kunjungan/${encounterId}/catatan`, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify({...input, urutan: 1})});
export const completeSync = (encounterId: string) => request(`/kunjungan/${encounterId}/sinkronisasi-selesai`, {method: "POST"});
export const getStatus = (encounterId: string) => request<SyncStatus>(`/kunjungan/${encounterId}/status-sinkronisasi`);
