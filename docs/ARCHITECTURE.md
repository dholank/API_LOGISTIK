# Arsitektur API_LOGISTIK

FastAPI menghubungkan client dengan Oracle Database 19c Enterprise Edition. Python menangani HTTP, autentikasi, lifecycle Global API Key, dan batas transaksi. Validasi bisnis serta CRUD karyawan tetap di `F_CRUD_KARYAWAN_LOGISTIK`.

[PRD](<PRD.md>) menjadi acuan requirement, nama/signature objek, dan registry SQL bagian 15/16. [Rencana implementasi](<IMPLEMENTATION_PLAN.md>) membagi pekerjaan menjadi tiga milestone. Hasil offline, bootstrap key, dan CRUD HTTP live pada fixture berizin dicatat terpisah di [acceptance](<ACCEPTANCE.md>); project belum siap production.

## Struktur dan packaging

Project memakai src layout. Development dapat memakai instalasi editable; image rilis memasang package normal, tanpa menyisipkan `sys.path`. Struktur berikut menunjukkan pembagian source, bukan daftar gate yang sudah lulus:

```text
src/api_logistik/
  api/          route dan dependency HTTP
  schemas/      kontrak request/response
  security/     key, lifecycle, dan private store
  db/           pool, transaksi, dan akses Oracle
  middleware/   request context

database/       precheck, schema, function, dan seed/fixture manual
tests/          unit, API, source-contract, dan integrasi opt-in
scripts/        pemeriksaan environment dan ekspor OpenAPI
docs/           requirement, kontrak, operasi, dan bukti
```

Versi runtime dan dependency dikunci melalui [manifest](<../pyproject.toml>), [pin Python](<../.python-version>), dan satu [lockfile](<../uv.lock>). Perubahan versi memerlukan pengujian ulang. Virtualenv, cache, log, hasil ekspor lokal, dan secret bukan source repository.

Sembilan file SQL tersedia sesuai registry PRD, termasuk fixture dummy opsional. Pilihan file dan prasyarat penerapannya dijelaskan di [panduan database](<../database/README.md>), bukan diturunkan dari keberadaan direktori.

## Batas modul

| Modul | Tanggung jawab dan batas |
|---|---|
| [main.py](<../src/api_logistik/main.py>) | Merakit app, router, middleware, handler, dan lifecycle resource; tanpa SQL bisnis. |
| [config.py](<../src/api_logistik/config.py>) | Memvalidasi konfigurasi; tanpa koneksi saat import atau credential dalam output. |
| [logging_config.py](<../src/api_logistik/logging_config.py>) | Log tersanitasi ke stdout/stderr; tanpa body sensitif, raw key, atau traceback mentah. |
| [errors.py](<../src/api_logistik/errors.py>) | Kategori error dan pemetaan response terpusat. |
| [router.py](<../src/api_logistik/api/router.py>) | Menggabungkan route di `/api/v1`. |
| [dependencies.py](<../src/api_logistik/api/dependencies.py>) | Autentikasi Python dan koneksi request; tanpa provisioning, rotasi, atau DDL. |
| [health.py](<../src/api_logistik/api/health.py>) | Liveness proses tanpa query Oracle; bukan readiness database. |
| [Handler karyawan](<../src/api_logistik/api/karyawan.py>) | Menerima input, memilih mode CRUD, dan status HTTP; tanpa query tabel bisnis langsung. |
| [Schemas](<../src/api_logistik/schemas/>) | Bentuk request/response dan batas input, termasuk byte UTF-8 untuk target AL32UTF8; tidak menggantikan validasi bisnis Oracle. |
| [api_keys.py](<../src/api_logistik/security/api_keys.py>) | Generasi `secrets.token_urlsafe(32)`, SHA-256 UTF-8, serta validasi status, waktu, dan pointer GLOBAL. |
| [key_rotation.py](<../src/api_logistik/security/key_rotation.py>) | Keputusan readiness, normal/emergency rotation, revoke, expiry, dan retry; tanpa import DB/HTTP. |
| [secret_store.py](<../src/api_logistik/security/secret_store.py>) | Material rahasia persisten di luar Oracle/repository, permission privat, dan ekspor tanpa raw key di stdout/log. |
| [pool.py](<../src/api_logistik/db/pool.py>) | Pool per proses, acquire/release, dan shutdown; bukan commit per cursor. |
| [transactions.py](<../src/api_logistik/db/transactions.py>) | Batas eksplisit commit/rollback; hasil bisnis gagal juga rollback. |
| [Repository key](<../src/api_logistik/db/api_key_repository.py>) | Bind SQL hash/metadata, lock GLOBAL, dan penyimpanan perubahan state/key; tidak membuat raw key atau memutuskan lifecycle. |
| [Repository karyawan](<../src/api_logistik/db/karyawan_repository.py>) | Memanggil function bisnis melalui PL/SQL bind, membaca CLOB JSON, dan menutup cursor; tanpa commit sendiri. |
| [request_context.py](<../src/api_logistik/middleware/request_context.py>) | Request ID, durasi, dan metadata log; bukan keputusan bisnis/transaksi. |
| [cli.py](<../src/api_logistik/cli.py>) | Jalur operator untuk provisioning dan lifecycle key; bukan endpoint publik atau task startup API. |

API/CLI mengorkestrasi repository dan security. Engine lifecycle menggunakan immutable `KeyRecord` dan `RotationState`; repository memetakan keduanya ke persistence. Jangan mengimpor app utama untuk memperoleh settings atau koneksi. MVP tidak menambah ORM, generic repository, service layer, atau domain layer tanpa alasan rancangan yang dicatat.

## Request dan transaksi

```text
Client X-API-Key -> request context -> dependency autentikasi Python
  -> SHA-256 + bind lookup metadata/state Oracle
  -> valid ACTIVE/GRACE dan ACTIVATES_AT <= now < EXPIRES_AT
  -> handler -> batas transaksi -> F_CRUD_KARYAWAN_LOGISTIK
  -> periksa hasil bisnis -> commit/rollback -> HTTP JSON
```

Handler bisnis hanya berjalan setelah autentikasi dan validasi input lulus. Key kosong, salah, PENDING, expired, atau revoked menghasilkan 401. Kegagalan pool, koneksi, atau query autentikasi menghasilkan 503, tanpa cache fallback, validator Oracle, atau auth bypass. Raw key tidak di-trim, diubah case, atau dikirim ke Oracle.

Repository memanggil function lewat blok PL/SQL dengan bind, bukan `SELECT function(...) FROM DUAL`. ID API berupa string digit ASCII maksimal lima digit, dikonversi ke NUMBER sesuai tabel training `NUMBER(5)`. Function mengembalikan CLOB JSON; aplikasi memvalidasi hasil sebelum commit. Exception teknis, `success=false`, dan kegagalan parsing memicu rollback. Repository dan function tidak memiliki commit sendiri.

Commit write selesai sebelum response HTTP sukses. Jika commit tidak pasti, koneksi di-drop; rekonsiliasi memakai manager/session baru dan mengambil lock GLOBAL sebelum membaca state lifecycle. Respons gagal setelah commit tidak menjamin mutasi belum terjadi. Jangan mengulang mutasi secara buta. Request ID tersedia sebelum handler dan pada response yang dapat ditangani aplikasi.

## Pool, timeout, dan TLS

Koneksi auth/CRUD berada dalam scope request. Pool dibuat lazy per proses/worker, bukan per request atau saat import. Kapasitas total harus menghitung jumlah worker dan proses operator.

| Pengaturan | Default |
|---|---|
| Pool API min/max | 1 / 5 |
| Pool writer CLI | 1 / 1 |
| Acquire wait | 5000 ms |
| TCP connect timeout | 5 detik |
| Call timeout | 5000 ms per panggilan driver |

Koneksi Oracle wajib TCPS dengan pemeriksaan server DN; tidak ada fallback TCP atau penonaktifan verifikasi. Thin/Thick dan kebutuhan Oracle Client harus cocok dengan versi driver, Oracle 19c, OS, serta arsitektur target sesuai [standar teknologi](<PRD.md#17-standar-kerja-dan-target-teknologi>). Dokumentasi dukungan bukan bukti koneksi live.

Client production wajib memakai TLS melalui reverse proxy eksternal. Publish loopback Docker untuk development bukan pengganti TLS, firewall, atau review proxy. Konfigurasi runtime dan batas deployment ada di [panduan operasi](<OPERATIONS.md>).

## Global API Key dan administrasi

`API_KEY_AUTH` menyimpan hash dan metadata. `API_KEY_ROTATION_STATE` menyimpan singleton GLOBAL, pointer ACTIVE/GRACE/PENDING, due, readiness, VERSION, dan operation metadata. Tidak ada dependency `DBMS_CRYPTO`, `STANDARD_HASH`, `DBMS_SCHEDULER`, atau routine autentikasi/job Oracle.

Setiap prepare, konfirmasi readiness, aktivasi, dan revoke mengunci row GLOBAL melalui `SELECT FOR UPDATE`. Konfirmasi harus cocok dengan kandidat ID dan VERSION yang diharapkan di bawah lock yang sama, sebelum aktivasi. Konfirmasi stale ditolak. Perubahan key/state atomik; operation ID membantu rekonsiliasi retry atau commit yang tidak pasti. Jika `LAST_OPERATION_ID` sudah tertimpa, hasil historis saja tidak cukup untuk mengonfirmasi operasi asli.

Aktivasi aktual A menetapkan due A+7 hari dan expiry asli A+8 hari. Cutover normal pada B memberi key lama yang masih live status GRACE sampai `min(expiry_asli, B+24 jam)`. Cutover terlambat tidak memperpanjang umur key. Key EXPIRED/REVOKED tidak diaktifkan kembali.

Operator boleh mencabut key kompromi tanpa replacement, dengan risiko outage. Aktivasi darurat memerlukan replacement baru yang sudah siap; transaksi yang sama mencabut seluruh key lama yang live, termasuk GRACE. Tidak ada overlap darurat, grace darurat, atau auth bypass.

Tahap aktif adalah rotasi manual melalui [launcher Docker](<../scripts/api_key_operator.sh>): satu command CLI per pemanggilan, profil dan pin image privat, tanpa menyalakan API atau memasang scheduler. Root operator di-mount read-only; hanya store dan delivery yang diperlukan CLI bersifat writable. Host mencatat audit privat dengan UUID sebelum command, mempertahankan exit code, dan tidak mengulang mutasi otomatis. Launcher tidak mengubah engine, repository, settings, atau kontrak HTTP.

Scheduler eksternal ditunda ke M3 dan nantinya hanya memicu engine Python. Sampai distribusi dan acknowledgment client juga otomatis, pemicu terjadwal masih semi-otomatis. Pengamanan composite tick yang terputus/commit unknown harus disiapkan sebelum mengaktifkan scheduler. Expiry tetap berlaku ketika operator terlambat, WSL mati, atau distribusi gagal.

`F_VALIDATE_API_KEY_LOGISTIK`, `P_PREPARE_API_KEY`, `P_ROTATE_API_KEYS`, dan `JOB_ROTATE_API_KEYS` hanya catatan historis: tidak dipanggil, dibuat ulang, atau di-drop. Startup API tidak menjalankan DDL, compile function, seed, atau rotasi.

## Penerapan SQL

Pengguna/DBA memilih dan menerapkan SQL setelah preflight target, schema/PDB, privilege, fixture, dan pemulihan. Menyiapkan source bukan izin koneksi atau mutasi database.

Fresh schema memakai `ACTIVATES_AT`/`EXPIRES_AT`. Patch status legacy hanya mengubah constraint `CK_API_KEY_AUTH_STATUS`, bukan mengganti nama `ACTIVE_AT`/`EXPIRED_AT` atau memigrasikan schema. Mismatch menghentikan runtime kanonis sampai ada keputusan migrasi.

Seed state mengisi GLOBAL hanya jika belum ada, tanpa membuat key, dengan COMMIT eksplisit pada sesi setup khusus. Fixture dummy opsional mengikuti PRD bagian 16.4: penambahan hanya melalui function CRUD, tanpa overwrite atau COMMIT otomatis, dan rollback ke savepoint jika gagal. Query Q_ tetap read-only tanpa menampilkan nilai hash/raw key.

## Pengujian dan bukti

| Kelompok tes | Cakupan dan batas |
|---|---|
| [Unit](<../tests/unit/>) | Input, mapping, parsing, transaksi fake, hash, dan lifecycle dengan waktu terkontrol. |
| [API](<../tests/api/>) | HTTP/dependency override, 401/503 fail-closed, dan penolakan callback bisnis saat auth gagal. |
| [Source-contract](<../tests/contracts/>) | Nama/signature, registry SQL, schema, dan fixture; bukan bukti compile atau transaksi live. |
| [Integrasi](<../tests/integration/>) | Oracle sandbox opt-in untuk CRUD/rollback, locking, concurrency, stale VERSION, lifecycle, dan recovery. |

Tes default tidak membutuhkan jaringan atau mutasi Oracle. Integrasi memerlukan target, izin, fixture, dan rencana pemulihan terpisah. Bedakan bukti source, fake/mock, compile, live, dan deployment; hasil suatu tingkat tidak otomatis menutup tingkat lain.

[Acceptance](<ACCEPTANCE.md>) mencatat requirement ID, lingkungan, waktu, metode, hasil, dan batas tanpa secret atau data pegawai nyata. Keputusan pool, driver, lockfile, TLS, distribusi, dan recovery harus memiliki alasan serta referensi yang dapat ditelusuri.

## Referensi

Referensi rancangan berikut bukan pengganti verifikasi dependency terkunci atau pengujian target:

- [FastAPI multi-file](<https://fastapi.tiangolo.com/tutorial/bigger-applications/>) dan [lifecycle](<https://fastapi.tiangolo.com/advanced/events/>)
- [PyPA src layout](<https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/>)
- [pytest good practices](<https://pytest.org/en/stable/explanation/goodpractices.html>)
- [python-oracledb transactions](<https://python-oracledb.readthedocs.io/en/stable/user_guide/txn_management.html>) dan [interoperabilitas](<https://github.com/oracle/python-oracledb/blob/main/doc/src/user_guide/installation.rst>)
- [Docker build practices](<https://docs.docker.com/build/building/best-practices/>)
