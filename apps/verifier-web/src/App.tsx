import {FormEvent, useState} from "react";
import {Assessment, Candidate, Finding, getAssessment, getCandidates, getFindings, recheck, submitVerification} from "./api/client";

type Props = {accessToken: () => string; logout: () => void};
export default function App({accessToken, logout}: Props) {
  const [claimId, setClaimId] = useState(`CLAIM-${Date.now()}`);
  const [participant, setParticipant] = useState("SYNTHETIC-10001");
  const [code, setCode] = useState("PROC-001");
  const [verificationId, setVerificationId] = useState("");
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState("");
  const refresh = async (id = verificationId) => {
    if (!id) return;
    try { setAssessment(await getAssessment(accessToken(), id)); setCandidates(await getCandidates(accessToken(), id)); setFindings(await getFindings(accessToken(), id)); }
    catch (value) { setError((value as Error).message); }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    const now = new Date(), start = new Date(now.getTime() - 7 * 86400000), end = new Date(now.getTime() + 86400000);
    try {
      const result = await submitVerification(accessToken(), {claim_source: "VERIFIER-DEMO", claim_id: claimId, claim_revision: "1", patient: {participant_number: participant}, facility: {namespace: "DEMO-FASKES", code: "HOSP-DEMO-001"}, service_period: {start: start.toISOString(), end: end.toISOString()}, items: [{item_ref: "ITEM-1", item_type: "PROCEDURE", code_system: "LOCAL", code, quantity: 1, unit: "1"}]});
      setVerificationId(result.verification_id); setTimeout(() => void refresh(result.verification_id), 1200);
    } catch (value) { setError((value as Error).message); }
  };
  return <main style={{fontFamily: "system-ui", maxWidth: 900, margin: "2rem auto", padding: 16}}>
    <header style={{display: "flex", justifyContent: "space-between"}}><h1>JejakJKN Verifier</h1><button onClick={logout}>Keluar</button></header>
    <p>Hasil ini adalah sinyal verifikasi dan tidak pernah menjadi keputusan fraud otomatis.</p>
    <form onSubmit={submit} style={{display: "grid", gap: 12, maxWidth: 520}}>
      <label>ID klaim <input value={claimId} onChange={e => setClaimId(e.target.value)} required/></label>
      <label>Nomor peserta <input value={participant} onChange={e => setParticipant(e.target.value)} required/></label>
      <label>Kode prosedur <input value={code} onChange={e => setCode(e.target.value)} required/></label>
      <button type="submit">Verifikasi klaim</button>
    </form>
    {error && <p role="alert" style={{color: "#a00"}}>{error}</p>}
    {verificationId && <p>ID verifikasi: <code>{verificationId}</code> <button onClick={() => refresh()}>Muat hasil</button> <button onClick={async () => { await recheck(accessToken(), verificationId); setTimeout(() => void refresh(), 1200); }}>Evaluasi ulang</button></p>}
    {assessment && <section><h2>Empat dimensi</h2><dl>
      <dt>Pencocokan encounter</dt><dd>{assessment.encounter_match_status}</dd><dt>Rekonsiliasi bukti</dt><dd>{assessment.evidence_reconciliation_status}</dd>
      <dt>Duplikasi</dt><dd>{assessment.duplicate_assessment_status}</dd><dt>Konfirmasi pasien</dt><dd>{assessment.patient_confirmation_status}</dd>
    </dl><p>Status: {assessment.status}; freshness: {assessment.data_freshness}; keputusan fraud: {String(assessment.final_fraud_decision)}</p></section>}
    {candidates.length > 0 && <section><h2>Semua kandidat</h2><ul>{candidates.map(row => <li key={row.encounter_id}>{row.encounter_id}: {row.match_state} ({row.reasons.join(", ") || "semua item cocok"})</li>)}</ul></section>}
    <section><h2>Temuan aturan</h2>{findings.length ? <ul>{findings.map((row, index) => <li key={`${row.rule_id}-${index}`}><strong>{row.rule_id}</strong> [{row.severity}] {row.finding_code} — {row.limitations}</li>)}</ul> : <p>Belum ada temuan.</p>}</section>
  </main>;
}
