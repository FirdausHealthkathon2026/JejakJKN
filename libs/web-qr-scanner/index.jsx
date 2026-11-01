import React, {useCallback, useEffect, useRef, useState} from "react";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_PIXELS = 20_000_000;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export function validateQrImage(file, width, height) {
  if (!IMAGE_TYPES.has(file.type)) return "Gunakan gambar JPEG, PNG, atau WebP.";
  if (file.size > MAX_BYTES) return "Ukuran gambar maksimal 10 MiB.";
  if (width * height > MAX_PIXELS) return "Resolusi gambar maksimal 20 megapiksel.";
  return null;
}

function cameraMessage(error) {
  if (!window.isSecureContext) return "Kamera memerlukan localhost atau koneksi HTTPS tepercaya.";
  if (error?.name === "NotAllowedError") return "Izin kamera ditolak. Aktifkan izin kamera, atau gunakan galeri.";
  if (error?.name === "NotFoundError") return "Kamera tidak ditemukan. Gunakan galeri atau tempel token.";
  if (error?.name === "NotReadableError") return "Kamera sedang digunakan aplikasi lain.";
  return "Kamera tidak dapat dibuka. Gunakan galeri atau tempel token.";
}

export function QrScannerPanel({
  disabled = false,
  resetKey,
  modeName = "QR Masuk",
  onDecoded,
  onError,
  viewfinderHeight = 220,
  borderRadius = 14,
}) {
  const videoRef = useRef(null);
  const fileRef = useRef(null);
  const scannerRef = useRef(null);
  const sessionRef = useRef(0);
  const acceptedRef = useRef(false);
  const [state, setState] = useState("idle");
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [status, setStatus] = useState("Pilih kamera atau galeri untuk membaca QR.");

  const stop = useCallback(() => {
    sessionRef.current += 1;
    scannerRef.current?.destroy();
    scannerRef.current = null;
    setState("idle");
  }, []);

  useEffect(() => stop, [stop, resetKey]);
  useEffect(() => {
    if (disabled && scannerRef.current) stop();
  }, [disabled, stop]);
  useEffect(() => {
    const hidden = () => {
      if (document.hidden && scannerRef.current) {
        stop();
        setStatus("Kamera dihentikan karena tab tidak aktif.");
      }
    };
    document.addEventListener("visibilitychange", hidden);
    return () => document.removeEventListener("visibilitychange", hidden);
  }, [stop]);

  const accept = useCallback((value) => {
    const token = value?.trim();
    if (!token || token.length > 8192 || acceptedRef.current) return;
    acceptedRef.current = true;
    stop();
    setStatus("QR terbaca. Memproses…");
    onDecoded?.(token);
  }, [onDecoded, stop]);

  const startCamera = useCallback(async (nextDeviceId = "") => {
    if (disabled) return;
    stop();
    acceptedRef.current = false;
    const session = sessionRef.current;
    setState("starting");
    setStatus("Membuka kamera…");
    try {
      const {default: QrScanner} = await import("qr-scanner");
      if (session !== sessionRef.current || !videoRef.current) return;
      const scanner = new QrScanner(videoRef.current, (result) => accept(result.data), {
        preferredCamera: nextDeviceId || "environment",
        highlightScanRegion: true,
        highlightCodeOutline: true,
        returnDetailedScanResult: true,
      });
      scannerRef.current = scanner;
      await scanner.start();
      if (session !== sessionRef.current) {
        scanner.destroy();
        return;
      }
      setState("camera");
      setStatus("Arahkan kamera ke satu QR pasien.");
      const cameras = await QrScanner.listCameras(true);
      if (session === sessionRef.current) {
        setDevices(cameras);
        const activeId = videoRef.current?.srcObject?.getVideoTracks?.()[0]?.getSettings?.().deviceId;
        setDeviceId(activeId || nextDeviceId || cameras[0]?.id || "");
      }
    } catch (error) {
      if (session !== sessionRef.current) return;
      stop();
      const message = cameraMessage(error);
      setStatus(message);
      onError?.(message);
    }
  }, [accept, disabled, onError, stop]);

  const chooseImage = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    stop();
    acceptedRef.current = false;
    const session = sessionRef.current;
    setState("image");
    setStatus("Membaca gambar…");
    try {
      const fileIssue = validateQrImage(file, 0, 0);
      if (fileIssue) throw new Error(fileIssue);
      let dimensions;
      try {
        dimensions = await createImageBitmap(file);
        const issue = validateQrImage(file, dimensions.width, dimensions.height);
        dimensions.close();
        if (issue) throw new Error(issue);
      } catch (error) {
        dimensions?.close?.();
        if (error instanceof Error && (error.message.includes("Gunakan") || error.message.includes("maksimal") || error.message.includes("Resolusi") || error.message.includes("Ukuran"))) throw error;
        throw new Error("Gambar tidak dapat dibuka. Gunakan JPEG, PNG, atau WebP.");
      }
      const {default: QrScanner} = await import("qr-scanner");
      const result = await QrScanner.scanImage(file, {returnDetailedScanResult: true});
      if (session === sessionRef.current) accept(result.data);
    } catch (error) {
      if (session !== sessionRef.current) return;
      setState("idle");
      const message = error instanceof Error && error.message !== "No QR code found"
        ? error.message
        : "QR tidak terbaca. Pilih gambar tajam berisi satu QR lengkap dengan tepi putih.";
      setStatus(message);
      onError?.(message);
    }
  }, [accept, onError, stop]);

  const isErr = status && (status.includes("ditolak") || status.includes("tidak") || status.includes("gagal") || status.includes("Gunakan") || status.includes("maksimal") || status.includes("sedang digunakan"));

  const btnStyle = {
    minHeight: 38,
    padding: "0 14px",
    borderRadius: 8,
    border: "1px solid #CBD3CF",
    background: "#FFFFFF",
    color: "#1F2A22",
    fontWeight: 600,
    fontSize: 13,
    cursor: disabled ? "not-allowed" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  };

  return (
    <div
      aria-label="Pemindai QR kamera dan galeri"
      style={{display: "flex", flexDirection: "column", gap: 10, width: "100%"}}
    >
      <div
        style={{
          position: "relative",
          height: typeof viewfinderHeight === "number" ? `${viewfinderHeight}px` : viewfinderHeight,
          borderRadius,
          background: "#1F2A22",
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <video
          ref={videoRef}
          muted
          playsInline
          aria-label="Pratinjau kamera pemindai QR"
          style={{
            display: (state === "camera" || state === "starting") ? "block" : "none",
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
        <div
          style={{
            position: "relative",
            zIndex: 1,
            width: "150px",
            height: "150px",
            border: "2px dashed rgba(255,255,255,0.45)",
            borderRadius: "12px",
            pointerEvents: "none",
          }}
        />
        <span
          style={{
            position: "absolute",
            bottom: "12px",
            left: 0,
            right: 0,
            textAlign: "center",
            fontSize: "12px",
            color: "rgba(255,255,255,0.75)",
            textShadow: "0 1px 3px rgba(0,0,0,0.8)",
            zIndex: 1,
            pointerEvents: "none",
          }}
        >
          {state === "starting"
            ? "Membuka kamera…"
            : state === "camera"
            ? `Arahkan kamera ke ${modeName} pasien`
            : state === "image"
            ? "Membaca gambar…"
            : `Arahkan kamera ke ${modeName} pasien`}
        </span>
      </div>

      <div style={{display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap"}}>
        {state === "camera" || state === "starting" ? (
          <button type="button" onClick={stop} style={btnStyle}>
            Tutup kamera
          </button>
        ) : (
          <button type="button" disabled={disabled} onClick={() => startCamera()} style={btnStyle}>
            Buka kamera
          </button>
        )}

        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            stop();
            fileRef.current?.click();
          }}
          style={btnStyle}
        >
          Pilih dari galeri
        </button>

        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={chooseImage}
          hidden
          aria-label="Pilih gambar QR dari galeri"
        />

        {devices.length > 1 && (state === "camera" || state === "starting") ? (
          <label style={{display: "inline-flex", alignItems: "center", gap: 6, fontSize: "12.5px", color: "#3E4A45"}}>
            <span>Kamera</span>
            <select
              value={deviceId}
              onChange={(e) => startCamera(e.target.value)}
              disabled={disabled}
              style={{padding: "4px 8px", borderRadius: 6, border: "1px solid #CBD3CF", fontSize: "12.5px"}}
            >
              {devices.map((cam) => (
                <option key={cam.id} value={cam.id}>
                  {cam.label || `Kamera ${cam.id}`}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <p
        aria-live="polite"
        style={{
          margin: 0,
          fontSize: "12px",
          lineHeight: 1.4,
          color: isErr ? "#A1271B" : "#56625D",
        }}
      >
        {disabled ? "Memproses QR…" : status}
      </p>
    </div>
  );
}
