// @vitest-environment node
import {renderToString} from "react-dom/server";
import {describe, expect, it} from "vitest";
import App from "./App";
import {parseClaimsCsv} from "./domain/csv";
import {buildScenario, mapCase, mapClaim, narrativeOf} from "./domain/scenario";
import {View} from "./design/View";

const RAW_CLAIM = {
  id: "100011026V000001", source: "FASKES", file_name: null, revision: "1", relationship: "ORIGINAL", related_claim_id: null,
  participant_number: "SYNTHETIC-10001", patient_name: null, facility_code: "HOSP-DEMO-001", facility_name: "RS Demo Satu",
  service_start: "2026-10-30T02:00:00Z", service_end: "2026-10-30T03:00:00Z", care_type: "RJ", amount: 215000, status: "RECEIVED",
  submitted_at: "2026-10-30T04:00:00Z",
  items: [
    {item_ref: "DX-1", item_type: "DIAGNOSIS", code_system: "DEMO-DIAGNOSIS-CATALOG", code: "H10.9", display: "Konjungtivitis", quantity: "1", unit: "1"},
    {item_ref: "MED-1", item_type: "MEDICATION_DISPENSE", code_system: "DEMO-MEDICATION-CATALOG", code: "MED-1", display: "Paracetamol 500 mg", quantity: "20", unit: "tablet"},
  ],
};
const ASSESSMENT = {
  verification_id: "v1", claim_id: RAW_CLAIM.id, status: "COMPLETED", encounter_match_status: "UNIQUE_MATCH", selected_encounter_id: "e1", candidate_count: 1,
  matched_items_count: 1, patient_confirmation_status: "PARTIALLY_DISPUTED", review_required: true, data_freshness: "CURRENT", conflicting_claims: [],
  finding_codes: ["QUANTITY_MISMATCH", "PATIENT_DISPUTED"], created_at: "2026-10-30T04:10:00Z", completed_at: "2026-10-30T04:10:05Z",
};
const DETAIL = {
  findings: [
    {finding_code: "QUANTITY_MISMATCH", claim_item_ref: "MED-1", explanation_facts: {claimed: "20.0000", allocated: "10.0000"}},
    {finding_code: "PATIENT_DISPUTED", claim_item_ref: "MED-1", explanation_facts: {}},
  ],
  items: [
    {claim_item_ref: "DX-1", match_result: "MATCHED", item_type: "DIAGNOSIS", unit: "1", allocated_evidence_quantity: "1"},
    {claim_item_ref: "MED-1", match_result: "QUANTITY_MISMATCH", item_type: "MEDICATION_DISPENSE", unit: "tablet", allocated_evidence_quantity: "10.0000"},
  ],
  candidates: [{encounter_id: "e1", presence_status: "QR_VERIFIED", match_state: "ELIGIBLE_PARTIAL_MATCH", reasons: ["QUANTITY_MISMATCH"], started_at: "2026-10-30T02:00:00Z", ended_at: "2026-10-30T03:00:00Z"}],
  history: [ASSESSMENT],
};
const RAW_CASE = {
  id: "c1", claim_id: RAW_CLAIM.id, verification_id: "v1", state: "OPEN", is_stale: false, opened_at: "2026-10-30T04:10:06Z", assigned_name: null,
  finding_codes: ASSESSMENT.finding_codes, narrative_method: "LLM", narrative_generated_at: "2026-10-30T04:10:20Z",
  narrative: {summary: ["YANG SESUAI: Diagnosis Konjungtivitis sesuai catatan faskes.", "YANG TIDAK SESUAI: Paracetamol 500 mg berbeda jumlahnya."], questions: ["Apakah ada penyerahan tambahan?"], limitations: ["Bukan keputusan fraud."]},
  events: [{kind: "DECISION", actor_name: "verifier01", code: "ESCALATE", detail: "Perlu keputusan supervisor.", created_at: "2026-10-30T04:12:00Z"}],
};

const CSV = `nomor_klaim,revisi_klaim,nomor_peserta,nama_pasien,kode_faskes,tanggal_mulai,tanggal_selesai,jenis_layanan,sistem_kode,kode,jumlah,satuan,nominal_klaim
A1,1,111,,HOSP-DEMO-001,2024-05-07,2024-05-07,Diagnosis,ICD-10,K30,1,,173900
A1,1,111,,HOSP-DEMO-001,2024-05-07,2024-05-07,Tindakan,ICD-9-CM,3995,1,,
B2,1,222,,HOSP-DEMO-002,2024-05-09,2024-05-02,Diagnosis,ICD-10,K30,1,,100
C3,1,333,,HOSP-DEMO-002,2024-05-09,2024-05-09,Tindakan,ICD-9-CM,3995,0,,100`;

function render(state: Record<string, unknown>) {
  const app = new App({});
  const claim = mapClaim(RAW_CLAIM);
  Object.assign(app.state, {
    username: "verifier01", claims: [claim], assess: {[claim.id]: ASSESSMENT}, details: {[claim.id]: DETAIL}, cases: [mapCase(RAW_CASE)],
    claimId: claim.id, caseId: "c1", ...state,
  });
  app.setState = () => undefined;
  return renderToString(<View v={app.renderVals()} />);
}

describe("verifier screens render with live-shaped data", () => {
  const parsed = parseClaimsCsv("x.csv", CSV);
  it.each([
    ["login", {screen: "login"}], ["claims", {screen: "claims"}], ["confirm", {screen: "confirm"}], ["job", {screen: "job", job: {status: "RUNNING"}}],
    ["result", {screen: "result"}], ["cases", {screen: "cases"}], ["case", {screen: "case"}],
    ["upload", {screen: "upload", up: {phase: "pick"}}], ["preview", {screen: "upload", up: {phase: "preview", parsed}}],
    ["run", {screen: "upload", up: {phase: "run", parsed, done: 1, clear: 1}}], ["done", {screen: "upload", up: {phase: "done", parsed, done: 1}}],
    ["empty case page", {screen: "case", cases: [], claims: []}], ["empty claims", {screen: "claims", claims: [], assess: {}, cases: []}],
  ])("%s", (_, state) => {
    expect(render(state)).toContain("<");
  });

  it("shows the real case with its AI split and no raw codes", () => {
    const html = render({screen: "case"});
    expect(html).toContain("Yang tidak sesuai");
    expect(html).toContain("Paracetamol 500 mg berbeda jumlahnya.");
    expect(html).not.toMatch(/QUANTITY_MISMATCH|UNIQUE_MATCH|R00\d/);
  });
});

describe("domain", () => {
  it("groups CSV rows and reports problem rows", () => {
    const parsed = parseClaimsCsv("x.csv", CSV);
    expect(parsed.rowCount).toBe(4);
    expect(parsed.claims.map((c) => c.id)).toEqual(["A1"]);
    expect(parsed.claims[0].items).toHaveLength(2);
    expect(parsed.claims[0].amount).toBe(173900);
    expect(parsed.skipped).toEqual(["B2", "C3"]);
    expect(parsed.issues.map((i) => i.what)).toEqual(["Tanggal terbalik.", "Jumlah tidak valid."]);
  });

  it("reports missing columns", () => {
    expect(parseClaimsCsv("x.csv", "a,b\n1,2").missingColumns).toContain("nomor_klaim");
  });

  it("splits the narrative into sesuai and tidak sesuai", () => {
    const split = narrativeOf(RAW_CASE.narrative)!;
    expect(split.ok).toEqual(["Diagnosis Konjungtivitis sesuai catatan faskes."]);
    expect(split.bad).toEqual(["Paracetamol 500 mg berbeda jumlahnya."]);
  });

  it("derives comparison rows from item results", () => {
    const scenario = buildScenario(mapClaim(RAW_CLAIM), ASSESSMENT, DETAIL);
    expect(scenario.rows["MED-1"].fkText).toBe("10 tablet diserahkan");
    expect(scenario.attention[0].title).toBe("Jumlah Paracetamol 500 mg berbeda");
    expect(scenario.short).toContain("Jumlah berbeda");
  });

  it("explains an ambiguous match even without a rule finding", () => {
    const scenario = buildScenario(mapClaim(RAW_CLAIM), {...ASSESSMENT, encounter_match_status: "AMBIGUOUS_MATCH", selected_encounter_id: null, candidate_count: 2, finding_codes: []}, {findings: [], items: [], candidates: [], history: []});
    expect(scenario.attention[0].title).toBe("Ada 2 kunjungan yang sama-sama cocok");
    expect(scenario.rows).toBeNull();
  });
});
