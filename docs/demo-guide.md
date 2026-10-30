# Panduan Demo JejakJKN

Butuh Docker Desktop yang sedang berjalan dan Git Bash.

## Menyalakan

```bash
bash scripts/demo-up.sh          # menyalakan semua layanan, migrasi, dan seed
python scripts/demo-smoke.py     # opsional: cek alur utama lewat API
```

| Aplikasi | Alamat | Akun |
|---|---|---|
| Pasien | http://localhost:5173 | `patient01` / `synthetic-patient-01` |
| SIMRS A | http://localhost:5174 | tanpa login |
| Verifikator | http://localhost:5175 | tombol di halaman masuk |
| SIMRS B | http://localhost:5176 | tanpa login |

Reset data demo: `docker compose down -v`, lalu jalankan `scripts/demo-up.sh` lagi.

## Alur utama

1. **Pasien:** masuk, tampilkan QR Masuk, tekan "Simulasikan pindai petugas".
2. **SIMRS A:** buka kunjungan, tambahkan diagnosis, tindakan, dan obat. Jenis tindakan dan obat memakai "Kode internal RS".
3. **Pasien:** tampilkan QR Keluar, tekan "Simulasikan pindai petugas".
4. **SIMRS A:** tekan "Tandai lengkap".
5. **Pasien:** periksa ringkasan, tandai satu obat "Tidak sesuai", kirim respons.
6. **SIMRS A:** menu Klaim BPJS, ajukan klaim. Naikkan jumlah obat agar berbeda dari catatan.
7. **Verifikator:** masuk, tekan "Periksa" pada klaim, lalu "Mulai pemeriksaan". Halaman Tinjau terbuka dengan Ringkasan AI.
8. **Verifikator:** ambil kasus, pilih tindak lanjut, tulis alasan, simpan.

## Unggah CSV

Di Verifikator, buka Unggah CSV, pilih `klaim_contoh_1000.csv`, lalu periksa. Selesai sekitar 2 menit dengan hasil 900 sesuai dan 100 perlu ditinjau.

## SIMRS B

Klik QR di aplikasi pasien untuk menyalin token, lalu tempel di halaman Pindai QR SIMRS B. Tombol "Simulasikan pindai petugas" hanya mengarah ke SIMRS A.
