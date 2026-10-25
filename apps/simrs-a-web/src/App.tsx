import {useState} from "react";

export default function App() {
  const [token, setToken] = useState("");
  const [result, setResult] = useState("");

  const scan = async (kind: "check-in" | "check-out") => {
    setResult("Memproses…");
    try {
      const response = await fetch(`http://localhost:8101/api/scan/${kind}`, {
        method: "POST",
        headers: {"Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID()},
        body: JSON.stringify({qr_token: token, scanner_external_id: "SIMRS-A-SCANNER-01", external_visit_reference: kind === "check-in" ? `VISIT-${Date.now()}` : null}),
      });
      const body = await response.json();
      setResult(response.ok ? JSON.stringify(body, null, 2) : JSON.stringify(body.detail ?? body, null, 2));
    } catch {
      setResult("Scanner tidak dapat menghubungi backend SIMRS A.");
    }
  };

  return <main style={{fontFamily: "system-ui", maxWidth: 720, margin: "2rem auto", padding: "1rem"}}>
    <h1>SIMRS A — Scanner Gate 1</h1>
    <p>Tempel token QR untuk simulasi pemindai. Input klinis baru tersedia pada Gate 2.</p>
    <textarea aria-label="Token QR" value={token} onChange={(e) => setToken(e.target.value)} rows={7} style={{width: "100%"}}/>
    <p><button onClick={() => scan("check-in")} disabled={!token}>Scan Masuk</button>{" "}<button onClick={() => scan("check-out")} disabled={!token}>Scan Keluar</button></p>
    <pre aria-live="polite">{result}</pre>
  </main>;
}
