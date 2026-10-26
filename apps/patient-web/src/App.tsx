import {useEffect, useState} from "react";
import {QRCodeSVG} from "qrcode.react";
import {ApiError, CheckoutSummary, Encounter, ItemResponse, getCheckoutSummary, issueQr, listEncounters, submitPatientResponse} from "./api/client";

type Props = {accessToken: () => string; logout: () => void};

export default function App({accessToken, logout}: Props) {
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [qr, setQr] = useState<{token: string; expires_at: string} | null>(null);
  const [error, setError] = useState("");
  const [summary, setSummary] = useState<CheckoutSummary | null>(null);
  const [summaryMessage, setSummaryMessage] = useState("");
  const [answers, setAnswers] = useState<Record<string, ItemResponse>>({});
  const [responseMessage, setResponseMessage] = useState("");

  const refresh = () => listEncounters(accessToken()).then((data) => setEncounters(data.items)).catch((e: Error) => setError(e.message));
  useEffect(() => { void refresh(); }, []);

  const showQr = async (purpose: "CHECK_IN" | "CHECK_OUT", encounterId?: string) => {
    setError("");
    try { setQr(await issueQr(accessToken(), purpose, encounterId)); }
    catch (e) { setError((e as Error).message); }
  };

  const showSummary = async (encounterId: string) => {
    setError(""); setSummary(null); setResponseMessage(""); setSummaryMessage("Memuat ringkasan…");
    try {
      const value = await getCheckoutSummary(accessToken(), encounterId);
      setSummary(value);
      setAnswers(Object.fromEntries(value.items.map((item) => [item.evidence_id, {evidence_id: item.evidence_id, response: "CONFIRMED"}])));
      setSummaryMessage("");
    } catch (e) {
      setSummaryMessage(e instanceof ApiError && e.status === 409 ? "Ringkasan belum siap. Menunggu watermark sinkronisasi lengkap dari SIMRS." : (e as Error).message);
    }
  };

  const submit = async (declined = false) => {
    if (!summary) return;
    const items = declined ? [] : Object.values(answers);
    const disputed = items.filter((item) => item.response === "DISPUTED").length;
    const overall = declined ? "DECLINED" : disputed === 0 ? "CONFIRMED" : disputed === items.length ? "DISPUTED" : "PARTIALLY_DISPUTED";
    try {
      const result = await submitPatientResponse(accessToken(), summary.snapshot_id, overall, items);
      setResponseMessage(`Respons ${result.overall_response} tersimpan.`);
    } catch (e) { setError((e as Error).message); }
  };

  const active = encounters.find((item) => item.status === "OPEN");
  return <main style={{fontFamily: "system-ui", maxWidth: 720, margin: "2rem auto", padding: "1rem"}}>
    <header style={{display: "flex", justifyContent: "space-between", alignItems: "center"}}>
      <h1>JejakJKN Pasien</h1><button onClick={logout}>Keluar</button>
    </header>
    <p>QR masuk/keluar dan status kunjungan. Informasi tahap pelayanan tidak ditampilkan selama kunjungan.</p>
    {error && <p role="alert" style={{color: "#a00"}}>{error}</p>}
    <button onClick={() => showQr("CHECK_IN")} disabled={Boolean(active)}>Tampilkan QR Masuk</button>{" "}
    <button onClick={() => active && showQr("CHECK_OUT", active.encounter_id)} disabled={!active}>Tampilkan QR Keluar</button>
    {qr && <section aria-label="QR aktif" style={{marginTop: 24}}>
      <QRCodeSVG value={qr.token} size={240}/>
      <label>Token QR untuk simulator<textarea readOnly value={qr.token} rows={3} style={{display: "block", width: "100%"}}/></label>
      <p>Berlaku sampai {new Date(qr.expires_at).toLocaleTimeString("id-ID")}</p>
    </section>}
    <h2>Riwayat kunjungan</h2><button onClick={refresh}>Muat ulang status</button>
    {encounters.length === 0 ? <p>Belum ada kunjungan.</p> : <ul>{encounters.map((item) => <li key={item.encounter_id}>
      {item.facility_display_name} — {item.status} — {new Date(item.started_at).toLocaleString("id-ID")} {item.status !== "OPEN" && <button onClick={() => showSummary(item.encounter_id)}>Lihat ringkasan</button>}
    </li>)}</ul>}
    {summaryMessage && <p role="status">{summaryMessage}</p>}
    {summary && <section aria-label="Ringkasan layanan setelah keluar">
      <h2>Ringkasan layanan</h2>
      <p>Versi bukti {summary.evidence_revision}. Ringkasan ini dibekukan setelah SIMRS menyatakan sinkronisasi lengkap.</p>
      {summary.items.length === 0 ? <p>Tidak ada item layanan pada ringkasan ini.</p> : <ul>{summary.items.map((item) => {
        const answer = answers[item.evidence_id];
        return <li key={item.evidence_id} style={{marginBottom: 16}}>
          <strong>{item.description}</strong> ({item.kind}) {item.quantity && `— ${item.quantity} ${item.unit ?? ""}`}
          <div>
            <label><input type="radio" checked={answer?.response === "CONFIRMED"} onChange={() => setAnswers({...answers, [item.evidence_id]: {evidence_id: item.evidence_id, response: "CONFIRMED"}})}/> Sesuai</label>{" "}
            <label><input type="radio" checked={answer?.response === "DISPUTED"} onChange={() => setAnswers({...answers, [item.evidence_id]: {evidence_id: item.evidence_id, response: "DISPUTED", reason: item.kind === "MEDICATION_DISPENSE" ? "MEDICATION_NOT_RECEIVED" : "SERVICE_NOT_RECEIVED"}})}/> Tidak sesuai</label>
          </div>
        </li>;
      })}</ul>}
      <button onClick={() => submit()}>Kirim konfirmasi</button>{" "}<button onClick={() => submit(true)}>Tolak memberi konfirmasi</button>
      {responseMessage && <p role="status">{responseMessage}</p>}
    </section>}
  </main>;
}
