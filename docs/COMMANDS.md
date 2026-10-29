# Command API_LOGISTIK

Panduan harian untuk Bash di WSL2/Linux. Jalankan dari root project, bukan dari folder dokumentasi. Tidak perlu Python host; aplikasi dan CLI operator memakai Python di image Docker.

Command di dokumen ini adalah referensi, bukan batch untuk dijalankan sekaligus. Bagian key mengubah state Oracle. Pastikan target dan izin benar; ganti placeholder ID/VERSION berdasarkan `status` terbaru, bukan menyalin angka dari contoh atau riwayat.

- [Docker](<#1-docker>)
- [Menjalankan dan menghentikan API](<#2-menjalankan-dan-menghentikan-api>)
- [Log dan konfigurasi](<#3-log-dan-konfigurasi>)
- [Status dan persiapan operator](<#4-status-dan-persiapan-operator>)
- [Membuat key baru dan rotasi normal](<#5-membuat-key-baru-dan-rotasi-normal>)
- [Cutover tanpa grace dan revoke](<#6-cutover-tanpa-grace-dan-revoke>)
- [Rekonsiliasi](<#7-rekonsiliasi>)
- [Tes offline](<#8-tes-offline>)
- [Transfer image](<#9-transfer-image>)

## 1. Docker

Periksa client, Compose, dan daemon lokal:

```bash
docker --version
docker compose version
docker --context default info --format '{{.ServerVersion}}'
```

Untuk Docker Engine native pada WSL2 yang memakai systemd:

```bash
sudo systemctl start docker
systemctl status docker --no-pager
```

Jika memakai Docker Desktop, buka aplikasinya dan aktifkan Linux containers serta integrasi distro WSL2. Jangan menyalakan Engine kedua dalam distro hanya untuk mengikuti contoh di atas. Command operator fase ini memerlukan context `default` pada socket lokal `/var/run/docker.sock`; remote context, custom socket, dan rootless Docker belum didukung launcher.

Jika akses daemon ditolak, minta administrator mengatur akses. Jangan menjalankan launcher operator dengan `sudo`: UID dan kepemilikan material privat harus cocok.

## 2. Menjalankan dan menghentikan API

Sebelum start pertama, siapkan konfigurasi dari [template environment](<../.env.example>) tanpa menimpa profil yang sudah ada:

```bash
cp --no-clobber .env.example .env
```

Isi koneksi Oracle secara privat. Gunakan TCPS dan trio konfigurasi koneksi lengkap. Untuk schema baru, ikuti [panduan database](<../database/README.md>); startup API tidak membuat tabel, menjalankan seed, atau menerbitkan key.

Build setelah perubahan source atau saat image belum tersedia:

```bash
docker compose build api
```

Jalankan image lokal dan tunggu healthcheck:

```bash
docker compose up --no-build --pull never --wait --wait-timeout 90 api
docker compose ps -a api
curl --fail http://127.0.0.1:8000/api/v1/health/live
```

Health 200 hanya berarti proses hidup, bukan koneksi Oracle atau autentikasi siap. Buka Swagger di <http://127.0.0.1:8000/docs>. Untuk endpoint bisnis, masukkan key melalui Authorize pada Swagger privat; jangan menaruh raw key pada argumen `curl`, chat, atau log. Kontrak request ada di [API](<API.md>).

Hentikan API tanpa menghapus container:

```bash
docker compose stop api
docker compose ps -a api
```

Restart proses tanpa menerapkan perubahan image/config:

```bash
docker compose restart api
```

Jika source berubah, ulangi build lalu up. Jika konfigurasi runtime berubah, gunakan up agar Compose dapat menerapkan perubahan; restart saja tidak memuat konfigurasi container baru. Profil koneksi operator terpisah juga perlu direview bila target Oracle berubah.

## 3. Log dan konfigurasi

Lihat log API terakhir atau ikuti log baru; Ctrl+C menghentikan tampilan follow, bukan API:

```bash
docker compose logs --tail 100 api
docker compose logs --follow --tail 100 api
```

Jangan membagikan log utuh tanpa pemeriksaan privasi. Jangan memakai debug trace atau access log proxy yang merekam header key.

Validasi struktur Compose tanpa merender credential, dari WSL2/Linux:

```bash
docker compose --env-file /dev/null config --no-interpolate --no-env-resolution --quiet
```

Jangan menampilkan hasil `docker compose config` biasa atau dump environment/inspect container; nilainya dapat memuat credential.

## 4. Status dan persiapan operator

[Launcher operator](<../scripts/api_key_operator.sh>) berjalan terpisah dari API. API boleh tetap berhenti selama administrasi key.

```bash
scripts/api_key_operator.sh --help
scripts/api_key_operator.sh status
```

Status menampilkan ID, VERSION, readiness, due, expiry, dan issues, bukan raw key. Catat hasilnya sebelum setiap mutasi. Semua client memakai satu key GLOBAL; rotasi harus dikoordinasikan dengan seluruh penerima.

Direktori privat default adalah `${XDG_DATA_HOME:-$HOME/.local/share}/api-logistik`. Profil koneksi lengkap, pin image immutable, master key, store terenkripsi, delivery, dan audit harus sudah disiapkan sesuai [runbook operator](<OPERATIONS.md#alur-utama-rotasi-manual>). Gunakan filesystem Linux dan permission privat; jangan mengatasi penolakan dengan melonggarkan guard.

Untuk contoh export berikut, siapkan variabel path pada terminal yang sama:

```bash
OP_ROOT="${API_LOGISTIK_OPERATOR_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/api-logistik}"
```

Variabel itu hanya path, bukan key. Rebuild/tag API tidak otomatis memperbarui pin image operator. Jangan mengganti master key atau memakai `init-secret-key` untuk merotasi API Key; launcher sengaja tidak menyediakan command tersebut atau `tick`.

## 5. Membuat key baru dan rotasi normal

Blok `text` di bagian ini adalah template. Isi VERSION dan ID dari hasil tiap langkah. Jangan jalankan seluruh urutan sebelum memeriksa hasil dan kesiapan client.

### A. Buat kandidat

```text
scripts/api_key_operator.sh prepare --expected-version VERSION_STATUS --reason manual_rotation
```

Prepare membuat API Key baru berstatus PENDING dan menyimpan materialnya terenkripsi. Key lama belum dimatikan. Jika kandidat sudah ada, review ID dan distribusinya sebelum mengganti kandidat. Jangan menganggap ID identity selalu berurutan.

```bash
scripts/api_key_operator.sh status
```

### B. Export dan distribusikan

```text
scripts/api_key_operator.sh export --key-id ID_PENDING --output "$OP_ROOT/delivery/successor-UNIQUE.txt"
```

Ganti `UNIQUE` dengan nama baru untuk operasi tersebut. Output wajib file baru langsung di delivery; file existing/symlink ditolak. Buka atau salurkan file secara privat melalui kanal yang disetujui, bukan mencetak raw key di terminal. Jangan mengirim master key atau seluruh store kepada client.

### C. Konfirmasikan kesiapan

Setelah seluruh client penerima siap memakai kandidat yang sama, baca status lagi. Keberadaan file export bukan konfirmasi penerimaan client.

```text
scripts/api_key_operator.sh confirm-distributed --key-id ID_PENDING --expected-version VERSION_PENDING --reason distribution_confirmed
```

Konfirmasi mengubah VERSION. Jika kandidat atau VERSION berbeda dari yang diperiksa, hentikan dan konfirmasikan ulang; jangan sekadar mengganti angka agar command lolos.

### D. Aktifkan pada/setelah due

```text
scripts/api_key_operator.sh activate --expected-version VERSION_SETELAH_CONFIRM --reason manual_rotation
```

Normal cutover mengaktifkan kandidat dan memberi key lama yang masih live GRACE sampai `min(expiry_asli, waktu_cutover + 24 jam)`. Reason `manual_rotation` tidak melewati pemeriksaan due. Untuk normal cutover lebih awal, gunakan `--manual` hanya setelah keputusan operator yang jelas; readiness tetap wajib dan key lama masih dapat mendapat grace.

```bash
scripts/api_key_operator.sh status
```

Periksa ACTIVE/GRACE dan waktu, lalu uji client bila API berjalan. Pastikan client berpindah sebelum grace habis. Due key baru adalah aktivasi aktual +7 hari dan expiry +8 hari, walaupun rotasi dijalankan manual atau WSL sedang mati. Tidak ada scheduler yang melakukan langkah ini untuk Anda.

## 6. Cutover tanpa grace dan revoke

### Ganti key dan langsung matikan key lama

Gunakan alternatif ini, bukan aktivasi normal pada langkah D, jika key lama harus langsung tidak berlaku. Selesaikan prepare, distribusi, dan confirm-distributed terlebih dahulu.

```text
scripts/api_key_operator.sh activate --expected-version VERSION_SETELAH_CONFIRM --emergency --reason manual_rotation
```

Mode emergency mencabut seluruh old live yang dikelola state GLOBAL, termasuk GRACE, dan mengaktifkan replacement dalam satu transaksi. Tidak ada overlap atau grace. Untuk insiden kompromi nyata, reason `suspected_compromise` tersedia; jangan mencatat insiden fiktif hanya karena ingin cutover tanpa grace.

Jangan revoke key lama terlebih dahulu lalu baru menyiapkan replacement jika ingin menghindari jeda layanan.

### Cabut satu key tanpa replacement

```text
scripts/api_key_operator.sh revoke --key-id ID_YANG_DICABUT --expected-version VERSION_STATUS --reason key_retired
```

Periksa ID sebelum menjalankan. Revoke ACTIVE tanpa pengganti dapat menyebabkan outage; command ini tidak otomatis mengaktifkan PENDING. EXPIRED/REVOKED tidak boleh dihidupkan kembali.

```bash
scripts/api_key_operator.sh status
```

## 7. Rekonsiliasi

Jika exit 4, proses terputus, atau hasil tidak lengkap, hentikan mutasi. Jangan mengulang prepare/activate untuk menebak hasil. Ambil UUID asli dari output/audit privat:

```text
scripts/api_key_operator.sh reconcile --operation-id UUID_OPERASI_ASLI
```

Jika ID kandidat diketahui, boleh tambahkan `--key-id ID_KANDIDAT`. Jangan membuat UUID baru pengganti. Rekonsiliasi memakai pool baru dan lock GLOBAL; bila LAST_OPERATION_ID sudah tertimpa atau hasil meminta manual review, keberadaan historical key saja tidak membuktikan commit.

| Exit | Arti/tindakan |
|---|---|
| 0 | Command selesai; tetap baca hasil/status |
| 1 | Error aplikasi/store atau preflight launcher; perbaiki penyebab sebelum mutasi |
| 2 | Argumen ditolak, VERSION stale, kandidat tidak cocok, atau operasi belum diizinkan |
| 3 | Lock busy; periksa state dan pekerjaan operator lain |
| 4 | Commit outcome unknown; reconcile sebelum mutasi lain |
| 125/126/127 | Docker gagal menjalankan command; cek daemon/image dan audit |
| 130/143 | Proses terputus; periksa UUID dan reconcile sebelum mencoba mutasi lagi |

Jangan menghapus audit, export, ciphertext, atau master key untuk membersihkan error. Detail recovery ada di [operasi](<OPERATIONS.md#alasan-operasi-exit-code-dan-rekonsiliasi>).

## 8. Tes offline

Bangun image tes, lalu jalankan tanpa jaringan atau credential Oracle:

```bash
docker build --target offline-tests -t api-logistik:offline-tests .
docker run --rm --network none \
  --user 10001:10001 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  api-logistik:offline-tests
```

Lint, format, serta mypy Linux dan target statis Windows:

```bash
docker run --rm --network none \
  --user 10001:10001 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --env RUFF_CACHE_DIR=/tmp/ruff \
  api-logistik:offline-tests sh -c \
  'ruff check src scripts tests && ruff format --check src scripts tests && mypy --cache-dir=/tmp/mypy-linux src/api_logistik && mypy --platform win32 --cache-dir=/tmp/mypy-win32 src/api_logistik'
```

Mypy win32 bukan pengujian runtime Windows. Tes integrasi Oracle memerlukan izin dan target terisolasi; jangan menyalin flag opt-in ke profil runtime untuk mencoba suite tulis.

## 9. Transfer image

Di pengirim, simpan image aplikasi lokal:

```bash
docker image save -o api-logistik.tar api-logistik:0.1.0-dev
```

Di penerima, load arsip yang sudah diterima:

```bash
docker image load -i api-logistik.tar
```

Penerima juga memerlukan [Compose](<../compose.yaml>), [template environment](<../.env.example>), dan koneksi Oracle yang disetujui sebelum menjalankan up. Image tidak membawa database, data karyawan, profil privat, atau key. Distribusi raw API Key dilakukan terpisah melalui kanal aman. Image yang dibangun pada setup ini adalah Linux amd64; platform lain memerlukan emulasi atau build yang diverifikasi.

Gunakan save/load, bukan export/import container. Ignore mencegah arsip lokal ikut commit/build context, bukan menyaring isi image yang sudah dibangun. Review image sebelum dibagikan; jangan membagikan direktori operator.

## Acuan

- [Runbook operasi](<OPERATIONS.md>) untuk konfigurasi, distribusi, dan recovery.
- [Acceptance](<ACCEPTANCE.md>) untuk bukti pengujian; ID/VERSION di riwayat bukan input mutasi berikutnya.
- [Docker Compose up](<https://github.com/docker/docs/blob/main/_vendor/github.com/docker/compose/v5/docs/reference/docker_compose_up.yaml>), [stop](<https://github.com/docker/docs/blob/main/_vendor/github.com/docker/compose/v5/docs/reference/compose_stop.md>), dan [save/load](<https://github.com/docker/docs/blob/main/content/manuals/desktop/settings-and-maintenance/backup-and-restore.md>).
