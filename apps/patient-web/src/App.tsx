import {useEffect, useState} from "react";
import {QRCodeSVG} from "qrcode.react";
import {Encounter, issueQr, listEncounters} from "./api/client";

type Props = {accessToken: () => string; logout: () => void};

export default function App({accessToken, logout}: Props) {
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [qr, setQr] = useState<{token: string; expires_at: string} | null>(null);
  const [error, setError] = useState("");

  const refresh = () => listEncounters(accessToken()).then((data) => setEncounters(data.items)).catch((e: Error) => setError(e.message));
  useEffect(() => { void refresh(); }, []);

  const showQr = async (purpose: "CHECK_IN" | "CHECK_OUT", encounterId?: string) => {
    setError("");
    try { setQr(await issueQr(accessToken(), purpose, encounterId)); }
    catch (e) { setError((e as Error).message); }
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
      <p>Berlaku sampai {new Date(qr.expires_at).toLocaleTimeString("id-ID")}</p>
    </section>}
    <h2>Riwayat kunjungan</h2><button onClick={refresh}>Muat ulang status</button>
    {encounters.length === 0 ? <p>Belum ada kunjungan.</p> : <ul>{encounters.map((item) => <li key={item.encounter_id}>
      {item.facility_display_name} — {item.status} — {new Date(item.started_at).toLocaleString("id-ID")}
    </li>)}</ul>}
  </main>;
}
