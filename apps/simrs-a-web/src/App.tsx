import {FormEvent, useState} from "react";
import {ClinicalInput, SyncStatus, cancelRecord, completeSync, correctRecord, createClinicalEvent, getSyncStatus, scan} from "./api/client";

const initialInput: ClinicalInput = {event_type: "PROCEDURE", code_system: "LOCAL", code: "PROC-001", display: "Konsultasi dokter"};

export default function App() {
  const [qrToken, setQrToken] = useState("");
  const [encounterId, setEncounterId] = useState("");
  const [input, setInput] = useState(initialInput);
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [message, setMessage] = useState("");

  const run = async (action: () => Promise<unknown>, success: string) => {
    setMessage("Memproses…");
    try { await action(); setMessage(success); if (encounterId) setStatus(await getSyncStatus(encounterId)); }
    catch (error) { setMessage((error as Error).message); }
  };

  const doScan = async (kind: "check-in" | "check-out") => run(async () => {
    const result = await scan(kind, qrToken);
    setEncounterId(result.encounter_id);
  }, `Scan ${kind} berhasil.`);

  const addEvent = (event: FormEvent) => {
    event.preventDefault();
    void run(() => createClinicalEvent(encounterId, {...input, quantity: input.quantity || undefined, unit: input.unit || undefined}), "Catatan tersimpan lokal dan masuk antrean sinkronisasi.");
  };

  const correct = (recordId: string) => {
    const reason = window.prompt("Alasan koreksi");
    if (reason) void run(() => correctRecord(recordId, input, reason), "Versi koreksi tersimpan dan diantrikan.");
  };

  const cancel = (recordId: string) => {
    const reason = window.prompt("Alasan pembatalan");
    if (reason) void run(() => cancelRecord(recordId, reason), "Versi pembatalan tersimpan dan diantrikan.");
  };

  return <main style={{fontFamily: "system-ui", maxWidth: 820, margin: "2rem auto", padding: "1rem"}}>
    <h1>SIMRS A — Kunjungan & Sinkronisasi</h1>
    <p>Catatan klinis disimpan dahulu di SIMRS A, lalu dikirim ulang secara durable sampai diterima JejakJKN.</p>
    <label>Token QR<textarea value={qrToken} onChange={(event) => setQrToken(event.target.value)} rows={5} style={{display: "block", width: "100%"}}/></label>
    <p><button onClick={() => doScan("check-in")} disabled={!qrToken}>Scan Masuk</button>{" "}<button onClick={() => doScan("check-out")} disabled={!qrToken}>Scan Keluar</button></p>
    <label>ID kunjungan<input value={encounterId} onChange={(event) => setEncounterId(event.target.value)} style={{display: "block", width: "100%"}}/></label>

    <h2>Input klinis/farmasi</h2>
    <form onSubmit={addEvent}>
      <label>Jenis<select value={input.event_type} onChange={(event) => setInput({...input, event_type: event.target.value})}>
        <option value="DIAGNOSIS">Diagnosis</option><option value="PROCEDURE">Tindakan</option><option value="MEDICATION_PRESCRIBED">Resep obat</option><option value="MEDICATION_DISPENSED">Obat diserahkan</option><option value="STAGE_COMPLETION">Tahap internal selesai</option>
      </select></label>{" "}
      <label>Sistem kode <input value={input.code_system} onChange={(event) => setInput({...input, code_system: event.target.value})}/></label>{" "}
      <label>Kode <input value={input.code} onChange={(event) => setInput({...input, code: event.target.value})}/></label><br/>
      <label>Deskripsi <input value={input.display} onChange={(event) => setInput({...input, display: event.target.value})}/></label>{" "}
      <label>Jumlah <input type="number" min="0" step="any" value={input.quantity ?? ""} onChange={(event) => setInput({...input, quantity: event.target.value})}/></label>{" "}
      <label>Satuan <input value={input.unit ?? ""} onChange={(event) => setInput({...input, unit: event.target.value})}/></label>{" "}
      <button disabled={!encounterId}>Simpan</button>
    </form>

    <h2>Status adapter</h2>
    <button onClick={() => run(async () => setStatus(await getSyncStatus(encounterId)), "Status dimuat.")} disabled={!encounterId}>Muat status</button>{" "}
    <button onClick={() => run(() => completeSync(encounterId), "Watermark sinkronisasi lengkap diantrikan.")} disabled={!encounterId}>Tandai sinkronisasi lengkap</button>
    {status && <section><p>Status: <strong>{status.sync_status}</strong> · antre {status.pending} · gagal {status.failed} · terkirim {status.delivered}</p>
      <ul>{status.records.map((record) => <li key={record.record_id}>{record.event_type} — {record.external_record_id} — v{record.version} {record.status}{" "}
        {record.status !== "CANCELLED" && <><button onClick={() => correct(record.record_id)}>Koreksi memakai form</button>{" "}<button onClick={() => cancel(record.record_id)}>Batalkan</button></>}
      </li>)}</ul>
    </section>}
    <pre aria-live="polite">{message}</pre>
  </main>;
}
