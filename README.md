# API_LOGISTIK

FastAPI untuk CRUD Oracle dan Global API Key yang dikelola Python. Source API, operator CLI, rotasi, SQL fresh-only, Docker, serta tes tersedia. Penerimaan production belum selesai: pengguna masih perlu menerapkan SQL, mengizinkan tes tulis sandbox, serta memverifikasi TLS eksternal, distribusi/scheduler, recovery dan p95. Status rinci ada di [acceptance](<docs/ACCEPTANCE.md>).

## Menjalankan API lokal

Environment Windows pada workspace ini sudah terpasang. Konfigurasi privat yang sudah diisi tidak perlu ditimpa template. Untuk checkout baru, siapkan dependency terlebih dahulu seperti bagian setup di bawah; bila belum punya konfigurasi, gunakan [template tanpa credential](<.env.example>) dan isi secara lokal.

```powershell
.\.venv\Scripts\python.exe -m api_logistik
```

- Liveness publik: <http://127.0.0.1:8000/api/v1/health/live>.
- Swagger development: <http://127.0.0.1:8000/docs>.
- POST `/api/v1/karyawan` dan GET/PUT/DELETE `/api/v1/karyawan/{id}` memerlukan `X-API-Key`.
- Liveness tidak mengakses Oracle. Key tidak valid menghasilkan 401; backend auth tidak tersedia menghasilkan 503, tanpa melewati autentikasi.
- Jangan mengharapkan CRUD berhasil sebelum schema, function, dan key siap. Startup tidak membuat tabel, memasang job, atau menerbitkan key.

Kontrak lengkap: [API](<docs/API.md>). Produksi memerlukan reverse proxy TLS dan backend yang tidak dipublikasikan secara langsung; HTTP loopback development bukan deployment TLS production.

## SQL: pengguna menerapkan sendiri

Lihat [panduan SQL](<database/README.md>) sebelum memilih file. Jangan menjalankan seluruh folder otomatis. Pada schema kosong, source yang dibutuhkan mencakup:

1. [T_KARYAWAN.sql](<database/schema/T_KARYAWAN.sql>) dan [F_CRUD_KARYAWAN_LOGISTIK.sql](<database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql>), hanya jika objek bisnis belum ada.
2. [T_API_KEY_AUTH.sql](<database/schema/T_API_KEY_AUTH.sql>) dan [T_API_KEY_ROTATION_STATE.sql](<database/schema/T_API_KEY_ROTATION_STATE.sql>), hanya jika belum ada.
3. [D_INIT_API_KEY_ROTATION_STATE.sql](<database/seed/D_INIT_API_KEY_ROTATION_STATE.sql>) pada sesi setup khusus; hanya menambah GLOBAL yang hilang, bukan key.
4. Precheck/verifikasi sesuai panduan. Patch GRACE legacy tidak dibutuhkan pada fresh schema.

Function bisnis fresh memakai nama/signature tetap dan tidak mempunyai commit internal. File tersebut tidak memakai CREATE OR REPLACE, sehingga tidak menimpa function existing. DDL/seed belum dijalankan oleh agent. Pemeriksaan read-only terakhir pada Oracle 19.26/AL32UTF8 tidak menemukan keempat objek project melalui owned/visible objects maupun synonym. Jalankan kembali preflight setelah deployment:

```powershell
.\.venv\Scripts\api-logistik-preflight.exe
```

Exit 2 berarti prasyarat schema belum lengkap, bukan koneksi otomatis di-bypass. Bukti SELECT/JSON Oracle read-only bukan bukti function telah dikompilasi atau CRUD/rollback live sudah lulus.

## Provisioning dan rotasi

[Runbook operator](<docs/OPERATIONS.md>) menjelaskan private encrypted store, bootstrap prepare/confirm/activate, export ke file privat, immediate revoke, emergency replacement, tick dan rekonsiliasi. Jalankan operator dengan profil privat terpisah dan otorisasi OS/database yang sesuai:

```powershell
.\.venv\Scripts\api-logistik-keys.exe --help
```

Key digenerate menggunakan secrets.token_urlsafe(32), hash SHA-256 hanya di Python, dan Oracle menyimpan hash/metadata. Key baru tidak aktif sebelum distribusi dikonfirmasi untuk kandidat+VERSION yang tepat. Masa nominal 7 hari, hard expiry hari ke-8; grace lama min(expiry asli, aktivasi baru+24 jam). Tidak ada revival key expired/revoked atau endpoint publik untuk mengembalikan key baru.

Scheduler eksternal memanggil CLI setiap menit, bukan setiap worker API. Rotasi tetap semi-otomatis selama delivery/konfirmasi client masih manual. Error dan blocking menghasilkan audit/exit code untuk dipantau; delivery alert dan scheduler aktual tetap perlu disiapkan serta diuji oleh operator.

Master key, ciphertext store dan export plaintext harus berada di luar project dengan permission privat. CLI menolak lokasi di dalam project; pemeriksaan ACL/ancestor Windows juga dapat menolak folder shared. Jangan melonggarkan ACL host secara global untuk memaksa provisioning berhasil. Profil API tidak memerlukan writer credential atau master key. Compose meneruskan whitelist environment API saja.

## Tes dan kualitas

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=api_logistik --cov-report=term-missing
.\.venv\Scripts\ruff.exe check src scripts tests
.\.venv\Scripts\ruff.exe format --check src scripts tests
.\.venv\Scripts\mypy.exe src\api_logistik
.\.venv\Scripts\python.exe scripts\export_openapi.py
```

Default pytest mengecualikan integration dan tidak membutuhkan credential/network Oracle. [Tes integrasi](<tests/integration/test_oracle_readonly.py>) memerlukan opt-in dan profil privat eksternal eksplisit; [tes tulis](<tests/integration/test_oracle_isolated_writes.py>) menambahkan acknowledgement sandbox terisolasi kosong dan cleanup hanya fixture. Jangan mengaktifkan flag tersebut pada schema operasional. Collection/skip bukan live PASS.

[OpenAPI export](<scripts/export_openapi.py>) memakai konfigurasi test eksplisit tanpa dotenv atau acquire pool. Hasil ekspor tersedia sebagai [openapi.json](<docs/openapi.json>). Installed TestClient saat ini masih memberi satu deprecation warning tentang httpx; warning tidak disembunyikan dan bukan kegagalan runtime.

Pada runner Windows ini, TEMP diarahkan ke checkout: 16 kasus kebijakan lokasi private dilewati karena precondition lokasi eksternal tidak tersedia. Jangan mematikan guard agar lolos. Suite Linux Docker final menjalankan kasus tersebut: **334 passed, 2 Windows-only skips, 5 integration deselected**, coverage 85%. Suite Windows final: 318 passed dan 18 skips. Lint/format dan mypy 27 source files lulus.

Jalankan suite Linux tanpa jaringan/database, memakai runtime source-build di bagian berikut:

```powershell
docker build --target offline-tests --build-arg PYTHON_IMAGE=api-logistik/python:3.15.2 -t api-logistik:offline-tests .
docker run --rm --network none --user 10001:10001 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=128m --cap-drop ALL --security-opt no-new-privileges api-logistik:offline-tests
```

## Docker

Jalur image resmi `python:3.15.2-slim` belum tersedia pada pemeriksaan registry. Build alternatif yang tetap memakai Python 3.15.2:

```powershell
docker build -f Dockerfile.python-runtime -t api-logistik/python:3.15.2 .
docker build --build-arg PYTHON_IMAGE=api-logistik/python:3.15.2 -t api-logistik:0.1.0-dev .
docker compose up --no-build
```

[Runtime source-build](<Dockerfile.python-runtime>) memakai source Python resmi ber-checksum dan Debian ber-digest; compiler hanya di builder, bukan host. [Dockerfile aplikasi](<Dockerfile>) memasang wheel non-editable, memeriksa versi tepat, dan memakai UID/GID 10001. [Compose](<compose.yaml>) mempublikasikan loopback 8000, root filesystem read-only, tmpfs, cap-drop dan no-new-privileges. Jangan memakai default Compose rebuild setelah memilih runtime lokal; gunakan `--no-build`. Detail dan batas reproducibility/TLS ada di [operasi](<docs/OPERATIONS.md>).

## Setup dependency dari checkout baru (Windows)

Pin runtime/tool: Python 3.15.2 dan uv 0.13.5. [Manifest](<pyproject.toml>), [pin Python](<.python-version>) dan [lockfile](<uv.lock>) mengunci runtime/dependency termasuk FastAPI 0.162.0, Pydantic 2.14.1, oracledb 26.0.1. Gunakan Python Install Manager yang mendukung target extraction; Python bootstrap hanya dipakai untuk memasang uv terisolasi.

```powershell
py -3 -m venv .tools\uv
.\.tools\uv\Scripts\python.exe -m pip --isolated --disable-pip-version-check install --index-url https://pypi.org/simple --no-cache-dir --only-binary=:all: uv==0.13.5
py install --yes --target=.\.tools\python-3.15.2 3.15.2
.\.tools\uv\Scripts\uv.exe --cache-dir .cache\uv sync --locked --python .\.tools\python-3.15.2\python.exe --no-python-downloads --default-index https://pypi.org/simple
.\.venv\Scripts\python.exe scripts\check_environment.py
```

Untuk workspace yang sudah terpasang cukup sync terakhir bila diperlukan; jangan bootstrap ulang di atas folder terpakai. Runtime target extraction tidak mengganti Python global; jangan memindahkannya selama virtualenv masih menggunakannya. Cache lokal menghindari cache uv global yang menolak akses pada mesin ini; tidak ada ACL global yang diubah. [Git ignore](<.gitignore>) dan [Docker ignore](<.dockerignore>) mengecualikan env privat, wallet, tooling/cache dan virtualenv.

## Isi repository publik

Repository menyertakan source API/CLI, SQL, tes, dokumentasi, template environment tanpa credential, serta manifest dan lockfile. Instruksi agent lokal, output Graphify, environment Python, cache, hasil tes, konfigurasi privat, wallet/key, metadata editor dan `:Zone.Identifier` tidak dipublikasikan. File lokal yang masih diperlukan tetap disimpan, tetapi diabaikan Git dan konteks build Docker.

Aturan pengecualian mengikuti [dokumentasi Git](<https://git-scm.com/docs/gitignore>). Target `offline-tests` tidak bergantung pada instruksi agent lokal agar checkout publik dapat menyediakan semua sumber `COPY`, sesuai [aturan Docker CopyIgnoredFile](<https://docs.docker.com/reference/build-checks/copy-ignored-file/>). Pengecualian file bukan pengganti audit secret sebelum commit atau push.

## Acuan

[PRD](<docs/PRD.md>) · [Arsitektur](<docs/ARCHITECTURE.md>) · [Rencana tiga milestone](<docs/IMPLEMENTATION_PLAN.md>) · [API](<docs/API.md>) · [Operasi](<docs/OPERATIONS.md>) · [Acceptance](<docs/ACCEPTANCE.md>).

Kesesuaian teknologi diperiksa melalui Context7 dan sumber resmi: [Python 3.15.2](https://www.python.org/downloads/release/python-3152/), [python-oracledb](https://github.com/oracle/python-oracledb/blob/main/README.md), [FastAPI](https://fastapi.tiangolo.com/), [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
