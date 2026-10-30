const GATEWAY = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:18080";
const KEYCLOAK = import.meta.env.VITE_KEYCLOAK_URL ?? "http://localhost:8081";
const CLAIM_API = import.meta.env.VITE_BPJS_CLAIM_API_URL ?? "http://localhost:8103/api";
const TOKEN_URL = `${KEYCLOAK}/realms/jejakjkn-dev/protocol/openid-connect/token`;
const VERIFY_API = `${GATEWAY}/api/v1/verifications`;
const REVIEW_API = `${GATEWAY}/api/v1/review-cases`;
const CLAIM_SOURCE = "BPJS_FKRTL_PROD";
const DEMO_PASSWORDS: Record<string, string> = {verifier01: "synthetic-verifier-01", supervisor01: "synthetic-supervisor-01"};

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
  }
}

type Session = {accessToken: string; refreshToken: string; expiresAt: number};
let session: Session | null = null;

async function grant(body: Record<string, string>): Promise<void> {
  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: new URLSearchParams({client_id: "verifier-web", ...body}),
  });
  if (!response.ok) throw new ApiError(response.status, "LOGIN_FAILED", "Login failed");
  const token = await response.json();
  session = {accessToken: token.access_token, refreshToken: token.refresh_token, expiresAt: Date.now() + (token.expires_in - 20) * 1000};
}

export const login = (username: string) => grant({grant_type: "password", username, password: DEMO_PASSWORDS[username]});
export const logout = () => { session = null; };

async function accessToken(): Promise<string> {
  if (!session) throw new ApiError(401, "NOT_LOGGED_IN", "Not logged in");
  if (Date.now() > session.expiresAt) await grant({grant_type: "refresh_token", refresh_token: session.refreshToken});
  return session.accessToken;
}

async function authed<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {"Content-Type": "application/json", Authorization: `Bearer ${await accessToken()}`, ...init?.headers},
  });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new ApiError(response.status, problem.error_code ?? "REQUEST_FAILED", problem.detail ?? "Request failed");
  }
  return response.json() as Promise<T>;
}

async function plain<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {...init, headers: {"Content-Type": "application/json"}});
  if (!response.ok) throw new ApiError(response.status, "CLAIM_SYSTEM_ERROR", "Claim system error");
  return response.json() as Promise<T>;
}

// BPJS claim system simulator
export const listClaims = () => plain<any[]>(`${CLAIM_API}/claims?limit=3000`);
export const setClaimStatus = (id: string, status: "VERIFYING" | "DONE") =>
  plain(`${CLAIM_API}/claims/${encodeURIComponent(id)}/status`, {method: "POST", body: JSON.stringify({status})});
export const importClaims = (fileName: string, claims: any[]) =>
  plain<{imported: number}>(`${CLAIM_API}/claims/import`, {method: "POST", body: JSON.stringify({file_name: fileName, claims})});

function verificationBody(claim: any) {
  return {
    claim_source: CLAIM_SOURCE,
    claim_id: claim.id,
    claim_revision: claim.revision,
    relationship: {type: claim.relationship, related_claim_id: claim.related_claim_id},
    patient: claim.participant_number ? {participant_number: claim.participant_number} : {full_name: claim.patient_name},
    facility: {namespace: "DEMO-FASKES", code: claim.facility_code},
    service_period: {start: claim.service_start, end: claim.service_end},
    items: claim.items.map(({item_ref, item_type, code_system, code, display, quantity, unit}: any) => ({item_ref, item_type, code_system, code, display, quantity, unit})),
  };
}

// Verification service
export const listAssessments = () => authed<any[]>(`${VERIFY_API}?limit=3000`);
export const getAssessment = (id: string) => authed<any>(`${VERIFY_API}/${id}`);
export const submitVerification = (claim: any) =>
  authed<{verification_id: string}>(VERIFY_API, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify(verificationBody(claim))});
export const recheckVerification = (id: string) =>
  authed<{verification_id: string}>(`${VERIFY_API}/${id}/re-evaluate`, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}});

export async function verificationDetail(claimId: string, verificationId: string) {
  const [findings, items, candidates, history] = await Promise.all([
    authed<any[]>(`${VERIFY_API}/${verificationId}/findings`),
    authed<any[]>(`${VERIFY_API}/${verificationId}/items`),
    authed<any[]>(`${VERIFY_API}/${verificationId}/candidates`),
    authed<any[]>(`${VERIFY_API}/history?claim_source=${CLAIM_SOURCE}&claim_id=${encodeURIComponent(claimId)}`),
  ]);
  return {findings, items, candidates, history};
}

export async function waitForAssessment(id: string, timeoutMs = 60000, intervalMs = 400): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const assessment = await getAssessment(id);
    if (assessment.status !== "QUEUED" && assessment.status !== "RUNNING") return assessment;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new ApiError(504, "VERIFICATION_TIMEOUT", "Verification timed out");
}

// Review service
export const listCases = () => authed<any[]>(REVIEW_API);
export const getCase = (id: string) => authed<any>(`${REVIEW_API}/${id}`, {headers: {"X-Access-Purpose": "FRAUD_REVIEW"}});
export const assignCase = (id: string, assignee: string) =>
  authed<any>(`${REVIEW_API}/${id}/assign`, {method: "POST", body: JSON.stringify({assignee})});
export const decideCase = (id: string, decision: string, reason: string) =>
  authed<any>(`${REVIEW_API}/${id}/decisions`, {method: "POST", headers: {"Idempotency-Key": crypto.randomUUID()}, body: JSON.stringify({decision, reason})});
