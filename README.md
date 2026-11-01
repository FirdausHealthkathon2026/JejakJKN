# JejakJKN

## Deskripsi Aplikasi

JejakJKN adalah prototipe platform pemeriksaan klaim Jaminan Kesehatan Nasional (JKN) yang dikembangkan untuk Healthkathon BPJS Kesehatan 2026. Aplikasi ini menghubungkan bukti kehadiran pasien, catatan pelayanan dari Sistem Informasi Manajemen Rumah Sakit (SIMRS), dan konfirmasi pasien untuk membantu verifikator menelusuri indikasi ketidaksesuaian klaim.

Alur utama aplikasi:

1. Pasien menampilkan QR masuk yang dipindai petugas SIMRS untuk mencatat kunjungan. QR berlaku sekitar 60 detik dan hanya dapat digunakan sekali.
2. SIMRS menyimpan diagnosis, tindakan, serta catatan obat di database sendiri, kemudian mengirimkannya ke JejakJKN melalui API.
3. Setelah QR keluar dipindai dan seluruh data layanan selesai disinkronkan, pasien melihat ringkasan layanan dan mengonfirmasi atau menyanggah setiap item.
4. Verifikator meminta pemeriksaan klaim melalui portal, baik satu per satu maupun melalui unggahan CSV.
5. Sistem mencocokkan klaim dengan seluruh kandidat kunjungan yang relevan, membandingkan bukti layanan, dan menandai potensi penggunaan ulang kunjungan atau bukti oleh klaim lain.
6. Verifikator meninjau temuan dan mencatat tindak lanjut. Narasi AI atau templat membantu menjelaskan hasil pemeriksaan; keputusan fraud dan pembayaran tidak ditentukan otomatis oleh JejakJKN.

Proyek menyediakan empat antarmuka web: **Portal Pasien**, **SIMRS A**, **SIMRS B**, dan **Portal Verifikator**. Frontend menggunakan React dan TypeScript, sedangkan backend menggunakan FastAPI dengan PostgreSQL, Redis, RabbitMQ, Keycloak, dan Nginx. Lingkungan lokal juga dilengkapi monitoring Prometheus, Grafana, dan Tempo.

## Anggota Pengembang

Nama lengkap, NIM, dan pembagian peran anggota belum dicantumkan dalam dokumentasi proyek. Lengkapi tabel berikut dengan data tim.

| No. | Nama Lengkap | 
| --- | --- | 
| 1 | Fikrifalah Muslich | 
| 2 | Nicholas Putra Halim | 
| 3 | Leonardus Brain Fatolosja | 

## Cara Menjalankan Aplikasi

### Prasyarat

- Docker Engine atau Docker Desktop sudah terpasang dan berjalan.
- Docker Compose v2 tersedia melalui perintah `docker compose`.
- Bash dan OpenSSL tersedia. Untuk Windows, gunakan Git Bash atau WSL.
- Koneksi internet tersedia untuk mengunduh image dan dependency pada build pertama.

### Menjalankan Pertama Kali

1. Buka terminal di folder utama repositori `JejakJKN`, yaitu folder yang berisi `compose.yaml`.
2. Jalankan:

   ```bash
   bash scripts/demo-up.sh
   ```

   Script ini menyiapkan `.env` dan kunci lokal di `.secrets/`, membangun image, menjalankan layanan, menerapkan migrasi database, serta mengisi data demo termasuk fixture benchmark 1.000 klaim. Tunggu hingga script selesai dan menampilkan alamat aplikasi.

3. Buka aplikasi melalui browser:

   | Aplikasi | Alamat | Cara Masuk |
   | --- | --- | --- |
   | Portal Pasien | http://localhost:5173 | Username `patient01`, password `synthetic-patient-01` |
   | SIMRS A | http://localhost:5174 | Langsung dibuka tanpa login manual |
   | Portal Verifikator | http://localhost:5175 | Pilih tombol masuk sebagai verifikator atau supervisor |
   | SIMRS B | http://localhost:5176 | Langsung dibuka tanpa login manual |

   API Gateway tersedia secara default di http://localhost:18080. Panduan mencoba alur pasien, SIMRS, dan verifikator tersedia di [Panduan Demo](docs/demo-guide.md).

### Mengecek Status dan Log

Jalankan dari folder utama repositori:

```bash
docker compose ps
docker compose logs --tail=100
```

### Menghentikan dan Menjalankan Kembali

Hentikan layanan dengan tetap menyimpan data lokal:

```bash
docker compose down
```

Setelah setup pertama selesai, jalankan kembali layanan dengan:

```bash
docker compose up -d --wait
```

Perintah `docker compose down -v` menghapus volume database dan data lokal. Gunakan hanya jika ingin mereset seluruh data demo.

Spesifikasi dan arsitektur lebih lanjut tersedia di [Spesifikasi Teknis](JejakJKN_Technical_Implementation_Specification_v1.0.md) dan [Dokumentasi Arsitektur](docs/architecture/technical-spec.md).
