import {FormEvent, useState} from "react";
import {addRecord, checkIn, completeSync, getStatus} from "./api/client";
import {LocalClinicalInput, SyncStatus} from "./types";

export default function App() {
  const [qr, setQr] = useState("");
  const [encounterId, setEncounterId] = useState("");
  const [input, setInput] = useState<LocalClinicalInput>({jenis: "OBAT", kode: "OB-PCT500", id_rekam: `RX-${Date.now()}`, jumlah: 10, satuan: "tab"});
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [message, setMessage] = useState("");

  const run = async (action: () => Promise<unknown>, success: string) => {
    setMessage("Memproses…");
    try { await action(); setMessage(success); if (encounterId) setStatus(await getStatus(encounterId)); }
    catch (error) { setMessage((error as Error).message); }
  };
  const scan = () => run(async () => { const result = await checkIn(qr); setEncounterId(result.encounter_id); }, "Kunjungan SIMRS-B dibuat.");
  const submit = (event: FormEvent) => { event.preventDefault(); void run(() => addRecord(encounterId, input), "Catatan lokal diantrikan secara durable."); };

  return <main style={{fontFamily: "system-ui", maxWidth: 800, margin: "2rem auto", padding: 16}}>
    <h1>SIMRS B — Skema Alternatif</h1>
    <p>Field dan kode lokal diterjemahkan adapter sebelum masuk ke katalog canonical JejakJKN.</p>
    <label>Token QR<textarea value={qr} onChange={event => setQr(event.target.value)} rows={5} style={{display: "block", width: "100%"}}/></label>
    <button onClick={scan} disabled={!qr}>Pindai masuk</button>
    <label>ID kunjungan<input value={encounterId} onChange={event => setEncounterId(event.target.value)} style={{display: "block", width: "100%"}}/></label>
    <h2>Catatan lokal</h2>
    <form onSubmit={submit} style={{display: "grid", gap: 8}}>
      <label>Jenis<select value={input.jenis} onChange={event => setInput({...input, jenis: event.target.value})}><option>OBAT</option><option>TINDAKAN</option><option>DIAGNOSIS</option></select></label>
      <label>Kode<input value={input.kode} onChange={event => setInput({...input, kode: event.target.value})}/></label>
      <label>ID rekam<input value={input.id_rekam} onChange={event => setInput({...input, id_rekam: event.target.value})}/></label>
      <label>Jumlah<input type="number" min="0" value={input.jumlah ?? ""} onChange={event => setInput({...input, jumlah: Number(event.target.value)})}/></label>
      <label>Satuan<input value={input.satuan ?? ""} onChange={event => setInput({...input, satuan: event.target.value})}/></label>
      <button disabled={!encounterId}>Simpan dan antrekan</button>
    </form>
    <h2>Status sinkronisasi</h2>
    <button onClick={() => void run(async () => setStatus(await getStatus(encounterId)), "Status dimuat.")} disabled={!encounterId}>Muat status</button>{" "}
    <button onClick={() => void run(() => completeSync(encounterId), "Watermark final diantrikan.")} disabled={!encounterId}>Sinkronisasi selesai</button>
    {status && <><p>{status.sync_status}: {status.delivered} terkirim, {status.pending} antre, {status.failed} gagal.</p><ul>{status.records.map(record => <li key={record.record_id}>{record.jenis}/{record.kode} — {record.status}</li>)}</ul></>}
    <p role="status">{message}</p>
  </main>;
}
