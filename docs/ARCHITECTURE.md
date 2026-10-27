# Arsitektur API_LOGISTIK

Status: arsitektur implementasi source API/CLI yang tersedia; hasil pengujian dan gate live dicatat terpisah pada [acceptance](<ACCEPTANCE.md>). [PRD](<PRD.md>) menjadi sumber tunggal requirement, nama/signature objek, dan registry path SQL (bagian 15/16). [Rencana implementasi](<IMPLEMENTATION_PLAN.md>) menetapkan tiga milestone; [panduan database](<../database/README.md>) menjelaskan penerapan SQL oleh pengguna.

Target: Python stabil terbaru yang diverifikasi/dikunci sebelum setup, Oracle Database 19c Enterprise Edition. Verifikasi dukungan dependency/platform, mode Thin/Thick dan Oracle Client bila diperlukan sesuai [standar kerja project](<PRD.md#17-standar-kerja-dan-target-teknologi>); dukungan tertulis bukan bukti koneksi live.

## 1. Struktur target

Gunakan src layout, instalasi editable untuk development dan instalasi package normal untuk pengujian rilis. Jangan menyisipkan `sys.path`. Setiap package Python mendapat `__init__.py` saat diimplementasikan. Tree berikut adalah target, bukan file atau fitur yang semuanya sudah tersedia.

```text
API_logistik/
├── src/api_logistik/
│   ├── main.py
│   ├── config.py
│   ├── logging_config.py
│   ├── errors.py
│   ├── api/
│   │   ├── router.py
│   │   ├── dependencies.py
│   │   ├── health.py
│   │   └── karyawan.py
│   ├── schemas/
│   │   ├── karyawan.py
│   │   └── responses.py
│   ├── security/
│   │   ├── api_keys.py
│   │   ├── key_rotation.py
│   │   └── secret_store.py
│   ├── db/
│   │   ├── pool.py
│   │   ├── transactions.py
│   │   ├── api_key_repository.py
│   │   └── karyawan_repository.py
│   └── middleware/request_context.py
├── database/
│   ├── README.md
│   ├── prechecks/
│   │   ├── Q_VERIFY_EXISTING_OBJECTS.sql
│   │   └── Q_VERIFY_API_KEY_STORAGE.sql
│   ├── schema/
│   │   ├── T_API_KEY_AUTH.sql
│   │   ├── T_API_KEY_ROTATION_STATE.sql
│   │   ├── C_API_KEY_AUTH_STATUS.sql
│   │   ├── C_KARYAWAN_ID_NOT_NULL.sql
│   │   └── C_PK_KARYAWAN.sql
│   ├── seed/D_INIT_API_KEY_ROTATION_STATE.sql
│   └── functions/F_CRUD_KARYAWAN_LOGISTIK.sql
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── api/
│   ├── contracts/
│   └── integration/
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── API.md
│   ├── OPERATIONS.md
│   ├── ACCEPTANCE.md
│   └── decisions/
├── scripts/
│   ├── check_environment.py
│   └── export_openapi.py
├── pyproject.toml
├── Dockerfile
├── compose.yaml
├── .env.example
├── .gitignore
├── .dockerignore
└── README.md
```

Lewati skeleton tanpa isi nyata. Delapan SQL pada registry PRD kini tersedia: enam storage/precheck/seed dan dua bisnis fresh-only yang disetujui pengguna. Source Python sudah tersedia; tree di atas tetap panduan ownership, bukan bukti setiap nama target harus dibuat bila tidak diperlukan. Manifest dependency memakai satu lockfile hasil tool yang dipilih, bukan daftar versi manual kedua. Virtualenv, cache, log, hasil ekspor, dan secret bukan source.

## 2. Batas modul

| Modul target | Tanggung jawab dan batas |
|---|---|
| `main.py` | Merakit app/router/middleware/handler dan lifecycle resource, bukan SQL bisnis. |
| `config.py` | Memvalidasi environment; tanpa koneksi saat import atau credential di output. |
| `logging_config.py` | Log stdout/stderr tersanitasi, bukan body sensitif/raw key. |
| `errors.py` | Kategori error dan response mapping terpusat; jangan menelan kegagalan tanpa diagnostik aman. |
| `api/router.py` | Menggabungkan route `/api/v1`. |
| `api/dependencies.py` | Memanggil autentikasi Python dan menyediakan koneksi request; tanpa provisioning/rotasi/DDL. |
| `api/health.py` | Liveness proses tanpa query bisnis; bukan readiness Oracle. |
| `api/karyawan.py` | Input, mode CRUD, status HTTP; tidak query tabel bisnis langsung. |
| `schemas/` | Validasi bentuk request/response, bukan mengganti validasi bisnis Oracle. |
| `security/api_keys.py` | Generasi `secrets.token_urlsafe(32)`, digest `hashlib.sha256` UTF-8 dan validasi status/waktu/state Global. |
| `security/key_rotation.py` | Keputusan lifecycle, readiness, normal/emergency rotation, revoke dan retry; transaksi SQL biasa melalui repository. |
| `security/secret_store.py` | Material rahasia durable di luar Oracle/repository; pengamanan permission dan distribusi, tanpa raw key di stdout/log. |
| `db/pool.py` | Pool per proses, acquire/release/shutdown, bukan commit per cursor. |
| `db/transactions.py` | Pemilik eksplisit commit/rollback; hasil bisnis gagal juga rollback. |
| `db/api_key_repository.py` | Bind SQL metadata/hash, lock GLOBAL dan update state/key; tidak membuat/hash raw key atau memutuskan lifecycle. |
| `db/karyawan_repository.py` | Memanggil hanya F_CRUD_KARYAWAN_LOGISTIK melalui PL/SQL bind, membaca CLOB/JSON, menutup cursor; tanpa commit sendiri. |
| `middleware/request_context.py` | Request ID, durasi dan log tersanitasi; bukan keputusan bisnis/transaksi. |

API/CLI mengorkestrasi repository dan security. Engine lifecycle tidak mengimpor DB/HTTP; repository menggunakan immutable KeyRecord/RotationState dari engine untuk mapping persistence. Jangan import main untuk memperoleh settings/koneksi. Tidak ada ORM, generic repository, layer services atau domain tambahan pada MVP awal; tambahan layer memerlukan alasan tercatat. Business logic karyawan tetap Oracle; autentikasi/lifecycle key seluruhnya Python.

## 3. Request dan transaksi

```text
Client X-API-Key -> request context -> dependency autentikasi Python
  -> SHA-256 + bind lookup metadata/state Oracle
  -> valid ACTIVE/GRACE dan ACTIVATES_AT <= now < EXPIRES_AT
  -> handler -> batas transaksi -> F_CRUD_KARYAWAN_LOGISTIK
  -> periksa hasil bisnis -> commit/rollback -> HTTP JSON
```

Handler bisnis hanya berjalan setelah autentikasi dan validasi bentuk input lulus. Key invalid/kosong/pending/expired/revoked menghasilkan 401; kegagalan database 503, fail-closed. Tidak ada fallback ke validator Oracle atau bypass. Raw key tidak di-trim/diubah case dan tidak dikirim ke Oracle. Request ID tersedia sebelum handler dan pada response yang dapat ditangani aplikasi.

Koneksi auth/CRUD dikelola dalam scope request. Pool per proses/worker, bukan per request/import; kapasitas total memperhitungkan jumlah worker. Pool dibuat lazy per proses, default min/max 1/5, acquire wait 5000 ms, TCP connect 5 detik dan call timeout 5000 ms; writer CLI memakai pool 1/1. Koneksi baru yang commit-nya tidak diketahui di-drop, dan rekonsiliasi memakai manager/session baru lalu lock GLOBAL sebelum inspeksi. Default wait dinaikkan dari 2 ke 5 detik setelah cold-pool probe 2,758 detik. Repository tidak commit; CRUD function tidak commit/rollback internal. Tangani exception teknis, success=false, kegagalan parsing sebelum commit dan cleanup. Respons gagal setelah commit tidak menjamin mutasi belum terjadi; retry membutuhkan rekonsiliasi.

## 4. Global lifecycle dan administrasi

Reuse API_KEY_AUTH untuk hash/metadata; API_KEY_ROTATION_STATE baru menyimpan singleton GLOBAL, pointer ACTIVE/GRACE/PENDING, due, readiness, VERSION dan operation metadata sesuai PRD. Tidak ada DBMS_CRYPTO, STANDARD_HASH, DBMS_SCHEDULER, auth function/procedure, atau job Oracle sebagai dependency.

Python mengunci row GLOBAL dengan SELECT FOR UPDATE sebelum mutasi lifecycle. Konfirmasi readiness harus cocok dengan kandidat ID dan VERSION yang diharapkan di bawah lock yang sama, sebelum aktivasi; stale confirmation ditolak. Update row key dan state atomik, dengan operation ID untuk rekonsiliasi retry/commit tidak diketahui.

Aktivasi aktual A menetapkan due A+7 hari dan expiry asli A+8 hari. Cutover normal B memberi key lama yang masih live GRACE sampai min(expiry asli, B+24 jam), tanpa extension saat telat. Jangan revive EXPIRED/REVOKED. Scheduler eksternal hanya pemicu engine Python; sebelum distribusi dan ack otomatis, operasi tetap semi-otomatis dan expiry tetap berlaku saat pemicu gagal.

Operator boleh revoke kompromi segera tanpa menunggu replacement, dengan risiko outage. Aktivasi darurat memerlukan replacement baru yang readiness-nya terkonfirmasi; transaksi yang sama mencabut semua key lama live termasuk GRACE. Tidak ada auth bypass atau grace darurat.

F_VALIDATE_API_KEY_LOGISTIK, P_PREPARE_API_KEY, P_ROTATE_API_KEYS dan JOB_ROTATE_API_KEYS hanya historis, tidak dipanggil/dibuat ulang/di-drop oleh pekerjaan ini. Startup API tidak menjalankan DDL, compile function, seed atau rotasi. SQL disiapkan offline; pengguna melakukan manual privilege/target preflight dan menerapkannya sendiri. Ini bukan izin DB connect/push.

Fresh schema memakai ACTIVATES_AT/EXPIRES_AT. Patch status legacy hanya constraint CK_API_KEY_AUTH_STATUS, tidak rename ACTIVE_AT/EXPIRED_AT atau menyelesaikan migrasi; mismatch menghentikan penerapan runtime kanonis sampai ada keputusan. Seed D_ hanya mengisi GLOBAL jika hilang, tanpa mint key, dengan COMMIT eksplisit pada sesi admin khusus. Q_ read-only tidak menampilkan hash/raw key.

## 5. Tes dan bukti

| Folder target | Bukti yang dituju |
|---|---|
| `tests/unit/` | Bentuk input, mapping, parser, transaksi fake, hash/validasi/lifecycle Python dengan waktu terkontrol. |
| `tests/api/` | HTTP/dependency override: invalid 401, DB failure 503, CRUD tidak dipanggil saat auth gagal. |
| `tests/contracts/` | Nama/signature bisnis, prefix/path SQL, lowerhex64, schema/state; statis bukan bukti compile/live. |
| `tests/integration/` | Oracle sandbox opt-in berizin: CRUD/rollback, locking, concurrent readiness, stale VERSION, lifecycle/expiry, emergency, retry/recovery. |

Tes default tanpa mutasi/jaringan Oracle. Integrasi memerlukan fixture, target, izin dan rencana pemulihan. Bedakan bukti source, mock, compile, live dan acceptance deployment; tidak ada klaim runtime dari dokumen/source saja.

## 6. Dokumentasi dan referensi

Dokumen API/operasi/acceptance dibuat saat dibutuhkan, tanpa placeholder kelulusan. Bukti acceptance mencatat requirement ID, lingkungan, waktu, metode, hasil dan batas tanpa secret/data pribadi. Catat keputusan pool, driver, lockfile, TLS, distribusi dan recovery di `docs/decisions/`; jadwal A+7 dan grace sudah diputuskan, bukan opsi terbuka.

Referensi desain historis berikut bukan verifikasi versi/dependency saat ini:

- [FastAPI multi-file](<https://fastapi.tiangolo.com/tutorial/bigger-applications/>) dan [lifecycle](<https://fastapi.tiangolo.com/advanced/events/>).
- [PyPA src layout](<https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/>).
- [pytest good practices](<https://pytest.org/en/stable/explanation/goodpractices.html>).
- [python-oracledb transactions](<https://python-oracledb.readthedocs.io/en/stable/user_guide/txn_management.html>) dan [interoperabilitas](<https://github.com/oracle/python-oracledb/blob/main/doc/src/user_guide/installation.rst>).
- [Docker build practices](<https://docs.docker.com/build/building/best-practices/>).
