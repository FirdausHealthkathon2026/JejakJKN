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

| No. | Nama Lengkap | 
| --- | --- | 
| 1 | Fikrifalah Muslich | 
| 2 | Nicholas Putra Halim | 
| 3 | Leonardus Brain Fatolosja | 

## Cara Menjalankan Aplikasi

### Prasyarat

- Docker Engine atau Docker Desktop sudah terpasang dan berjalan.
- Docker Compose v2 tersedia melalui perintah `docker compose`.
- Bash tersedia. Untuk Windows, gunakan Git Bash atau WSL.
- Koneksi internet tersedia untuk mengunduh image dan dependency pada build pertama.

### Menjalankan Pertama Kali

1. Download dan ekstrak ZIP repositori, lalu buka terminal di folder yang berisi `scripts.sh` dan `compose.yaml`.
2. Jalankan:

   ```bash
   bash scripts.sh
   ```

   Tidak perlu mengedit `.env`, memasang Node/Python/OpenSSL, atau mengisi API key.
   Script menyiapkan konfigurasi dan kunci melalui Docker, membangun image,
   menerapkan migrasi, serta mengisi data demo termasuk fixture 1.000 klaim.
   Sebelum menampilkan alamat aplikasi, script memeriksa koneksi database, login,
   API, dan keempat portal. Tunggu sampai muncul `JejakJKN siap dipakai.`

   Konfigurasi dan kunci dicadangkan otomatis di volume Docker
   `jejakjkn_bootstrap-data`. Jika ZIP diekstrak ulang tanpa `.env` dan `.secrets/`,
   script memulihkannya dari volume tersebut agar tetap cocok dengan database lama.
   Menjalankan perintah yang sama lagi akan memakai konfigurasi dan data yang ada.

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

Jika Keycloak berhenti dengan `password authentication failed for user "kc_user"`,
periksa log berikut:

```bash
docker compose logs --tail=100 keycloak postgres
```

Pesan `Skipping initialization` berarti PostgreSQL memakai data lama. Jalankan
`bash scripts.sh` agar konfigurasi yang tersimpan dipakai kembali. Untuk instalasi
lama sebelum backup otomatis tersedia, `.env` asli tetap diperlukan; script akan
berhenti jika database lama ditemukan tanpa konfigurasi yang dapat dipulihkan.
Data tidak dihapus otomatis. Simpan `.env` dan `.secrets/` bersama backup database
jika memindahkan instalasi ke komputer lain.

### Menghentikan dan Menjalankan Kembali

Hentikan layanan dengan tetap menyimpan data lokal:

```bash
docker compose down
```

Setelah setup pertama selesai, jalankan kembali layanan dengan:

```bash
bash scripts.sh
```

Perintah `docker compose down -v` menghapus volume database dan data lokal. Gunakan hanya jika ingin mereset seluruh data demo.

Spesifikasi dan arsitektur lebih lanjut tersedia di [Spesifikasi Teknis](JejakJKN_Technical_Implementation_Specification_v1.0.md) dan [Dokumentasi Arsitektur](docs/architecture/technical-spec.md).
