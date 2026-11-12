# Deploy online — AGEN AI VIDEO STUDIO PRO

## Pilihan hosting
Paket ini disiapkan untuk Render menggunakan Docker. Render memberikan URL publik `*.onrender.com`.
Dokumentasi resmi:
- https://render.com/docs/docker
- https://render.com/docs/web-services
- https://render.com/docs/configure-environment-variables

## Langkah publikasi
1. Buat akun GitHub dan Render.
2. Buat repository baru di GitHub, misalnya `agen-ai-video-studio`.
3. Unggah semua isi folder proyek ini ke repository (bukan file ZIP-nya).
4. Di Render pilih **New +** → **Blueprint**.
5. Hubungkan repository GitHub tersebut. Render akan membaca `render.yaml`.
6. Saat diminta, isi `OPENAI_API_KEY` dengan API key milik Anda. Jangan masukkan API key ke file frontend atau membagikannya.
7. Deploy dan tunggu sampai status menjadi Live.
8. Buka alamat `https://nama-service.onrender.com` dari HP atau laptop.

## Catatan biaya dan penyimpanan
- Hosting, pemakaian API AI, dan text-to-speech dapat memiliki batas atau biaya sesuai paket/penyedia.
- Render Free dapat tidur setelah tidak aktif dan perlu waktu untuk bangun kembali.
- Sistem ini menyimpan hasil sementara di filesystem server. Pada paket hosting dengan filesystem ephemeral, file dapat hilang ketika service restart atau deploy. Untuk penyimpanan hasil yang permanen, sambungkan object storage (misalnya S3-compatible) atau persistent disk berbayar.
- Video dibuat dari rangkaian gambar adegan, voice-over, dan subtitle. Generator klip gerak text-to-video (misalnya model video pihak ketiga) belum diaktifkan; perlu API provider video dan integrasi tambahan.
- Untuk penggunaan publik banyak pengguna, tambahkan autentikasi, pembatasan penggunaan, antrean pekerjaan, dan penyimpanan permanen sebelum diluncurkan luas.

## Pengujian lokal opsional
```bash
docker build -t agen-ai-video-studio .
docker run --rm -p 5000:10000 -e OPENAI_API_KEY='ISI_API_KEY' agen-ai-video-studio
```
Lalu buka http://localhost:5000
