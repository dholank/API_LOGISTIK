# API_LOGISTIK

REST API untuk CRUD data karyawan training, menggunakan FastAPI dan Oracle Database 19c Enterprise Edition. API berjalan di Docker; database berada di luar container.

Python menangani HTTP, validasi bentuk input, autentikasi Global API Key, dan transaksi. Function Oracle `F_CRUD_KARYAWAN_LOGISTIK` menangani validasi bisnis serta CRUD. Pembuatan, hashing SHA-256, dan rotasi API Key berlangsung di Python; Oracle menyimpan hash dan metadata key.

## Status project

API sudah berjalan dan lolos smoke test Docker di WSL2. Health check, dokumentasi HTTP, penolakan request tanpa key, serta stop/start container sudah diuji.

Project belum siap production. Autentikasi, CRUD, dan rotasi Oracle live masih memerlukan verifikasi; TLS client, distribusi key, scheduler, recovery, dan pengukuran p95 juga belum selesai. Lihat [bukti pengujian dan batasnya](<docs/ACCEPTANCE.md>).

## Menjalankan API di WSL2

Gunakan Docker Engine dan Compose pada distro WSL2 yang sama. Python berjalan di image, sehingga host tidak memerlukan instalasi Python atau virtualenv Windows.

### Konfigurasi

Bila belum punya profil runtime, salin [template environment](<.env.example>) tanpa menimpa konfigurasi yang sudah ada:

```bash
cp --no-clobber .env.example .env
```

Isi konfigurasi tersebut secara lokal sebelum menjalankan API.

Untuk koneksi Oracle, isi `ORACLE_DSN`, `ORACLE_USER`, dan `ORACLE_PASSWORD` bersama-sama. DSN harus memakai TCPS. Jangan memasukkan credential atau API Key ke source, log, maupun perintah shell. [Aturan Git](<.gitignore>) dan [aturan konteks build](<.dockerignore>) mengecualikan konfigurasi privat, wallet, key, cache, serta tooling lokal.

### Build dan jalankan

Jalankan dari root project:

```bash
docker compose build api
docker compose up --no-build --pull never --wait --wait-timeout 90
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/health/live
```

- Swagger development: <http://127.0.0.1:8000/docs>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>
- Health check: <http://127.0.0.1:8000/api/v1/health/live>

Hentikan API dengan `docker compose stop`. Untuk menjalankannya kembali, ulangi perintah `up`. Setelah perubahan source, ulangi `build` lalu `up`.

[Dockerfile](<Dockerfile>) memakai Python 3.15.2 dengan digest image terkunci. Versi dependency ada di [manifest](<pyproject.toml>) dan [lockfile](<uv.lock>). [Compose](<compose.yaml>) menjalankan container non-root dengan filesystem read-only dan port host terbatas pada `127.0.0.1:8000`.

Status `healthy` hanya menandakan proses API hidup, bukan kesiapan Oracle atau CRUD. Startup tidak membuat tabel, menjalankan seed, atau menerbitkan API Key. Jangan menampilkan hasil `docker compose config` yang sudah diinterpolasi karena dapat memuat credential. Detail jaringan, TLS, dan alternatif build tersedia di [panduan operasi](<docs/OPERATIONS.md>).

## Endpoint

| Method | Path | Fungsi | API Key |
|---|---|---|---|
| POST | `/api/v1/karyawan` | Tambah karyawan | Wajib |
| GET | `/api/v1/karyawan/{id}` | Ambil satu karyawan | Wajib |
| PUT | `/api/v1/karyawan/{id}` | Ganti seluruh field karyawan | Wajib |
| DELETE | `/api/v1/karyawan/{id}` | Hapus karyawan | Wajib |
| GET | `/api/v1/health/live` | Periksa proses API | Tidak |

Endpoint bisnis menerima key melalui header `X-API-Key`. Key tidak valid menghasilkan 401; kegagalan backend autentikasi menghasilkan 503, tanpa melewati autentikasi. Swagger dan OpenAPI aktif di development/test, tetapi nonaktif secara default di production.

Bentuk input, contoh response, kode error, dan batas retry dijelaskan dalam [kontrak API](<docs/API.md>). Snapshot schema tersedia di [OpenAPI JSON](<docs/openapi.json>).

## Menyiapkan Oracle dan API Key

Pengguna menerapkan SQL secara manual setelah memeriksa target schema/PDB, objek existing, privilege, dan rencana pemulihan. Ikuti [panduan database](<database/README.md>); jangan menjalankan seluruh folder SQL otomatis. Source fresh-only bukan migrasi legacy atau izin menimpa objek existing.

CRUD baru dapat digunakan setelah tabel, function, dan key siap. Function bisnis tidak melakukan commit internal; Python mengelola commit atau rollback.

Global API Key digunakan bersama seluruh client. Key baru hanya boleh aktif setelah distribusinya dikonfirmasi untuk kandidat dan versi state yang tepat. Rotasi jatuh tempo 7 hari setelah aktivasi, dengan hard expiry pada hari ke-8. Grace key lama maksimal 24 jam dan tidak boleh melewati expiry aslinya. Key expired atau revoked tidak diaktifkan kembali.

Provisioning, distribusi, revoke, dan rotasi memakai CLI operator dengan profil privat terpisah, bukan endpoint HTTP. Simpan master key, store terenkripsi, serta hasil ekspor key di luar project dengan permission privat. Scheduler tetap semi-otomatis selama distribusi dan konfirmasi client masih manual. Prosedurnya ada di [runbook operator](<docs/OPERATIONS.md#prosedur-cli-development>).

## Pengujian

Jalankan suite offline di Docker, tanpa jaringan atau credential Oracle:

```bash
docker build --target offline-tests -t api-logistik:offline-tests .
docker run --rm --network none \
  --user 10001:10001 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  api-logistik:offline-tests
```

Untuk lint, format, dan type-check, gunakan image tes yang sama:

```bash
docker run --rm --network none \
  --user 10001:10001 --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  --env RUFF_CACHE_DIR=/tmp/ruff \
  api-logistik:offline-tests sh -c \
  'ruff check src scripts tests && ruff format --check src scripts tests && mypy --cache-dir=/tmp/mypy src/api_logistik'
```

Hasil WSL2 pada 27 Oktober 2026: 336 tes lulus, 2 tes khusus Windows dilewati, 5 tes integrasi tidak dijalankan, dan coverage 85%. Lint, format, serta mypy Linux lulus; target mypy `win32` juga lulus secara statis dari Linux. Suite masih menampilkan satu warning deprecation TestClient/httpx.

Tes integrasi Oracle memerlukan opt-in, target sandbox, profil privat eksternal, fixture, dan izin terpisah. Hasil offline tidak membuktikan koneksi, CRUD, transaksi, atau rotasi Oracle live. Rincian ada di [acceptance](<docs/ACCEPTANCE.md>).

## Dokumentasi

| Dokumen | Isi |
|---|---|
| [PRD](<docs/PRD.md>) | Requirement, batas scope, dan registry objek SQL |
| [Arsitektur](<docs/ARCHITECTURE.md>) | Tanggung jawab modul dan alur transaksi |
| [Rencana implementasi](<docs/IMPLEMENTATION_PLAN.md>) | Milestone dan gate penerimaan |
| [Kontrak API](<docs/API.md>) | Endpoint, input, response, dan error |
| [Panduan database](<database/README.md>) | Preflight dan penerapan SQL manual |
| [Operasi](<docs/OPERATIONS.md>) | Konfigurasi, CLI operator, rotasi, dan recovery |
| [Acceptance](<docs/ACCEPTANCE.md>) | Bukti pengujian dan pekerjaan yang belum selesai |
