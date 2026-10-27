# Status penerimaan API_LOGISTIK

Acuan: [PRD](<PRD.md>) bagian 4, 10, 11 dan 12. Snapshot 26 Oktober 2026 ini mencatat bukti parent dan pemeriksaan dokumentasi secara terpisah. Project belum seluruhnya PASS. `SOURCE` berarti tersedia tanpa bukti runtime; `NOT RUN` berarti belum diuji pada tingkat gate tersebut; `BLOCKED` berarti prasyarat konkret belum tersedia. PASS offline/build tidak menjadi PASS Oracle live atau production.

## Bukti aktual dan batas

| Pemeriksaan | Hasil | Batas |
|---|---|---|
| Suite Linux Docker final, Python 3.15.2 | 334 passed, 2 Windows-only skips, 5 integration deselected, 9 subtests passed; coverage 85% | UID10001, filesystem read-only, network none; bukan bukti Oracle live |
| Suite Windows final | 318 passed, 18 skips, 5 integration deselected, 9 subtests passed | 16 kasus lokasi private memerlukan temp di luar checkout; dua skip platform/privilege. Kasus lokasi tersebut berjalan di suite Linux, bukan di-mock agar lolos |
| Lint parent atas src/scripts/tests; mypy | PASS; mypy 27 source files | Bukan deployment atau pengujian DB |
| Exporter melalui interpreter terinstal `-I` | PASS offline, lima operasi/tiga path, default/custom output | dotenv/load_settings/Settings init/pool acquire dipatch menolak akses; output ditangkap di memori |
| Compose dan isolasi environment | PASS parsing; nilai DB runtime cocok dengan profil privat, operator/writer/master/store tidak diteruskan | Perbandingan dilakukan di memori, hanya boolean dilaporkan; credential runtime tetap sensitif |
| Official `python:3.15.2-slim` | Manifest tidak tersedia saat lookup | Jalur default tetap tidak tersedia; tidak downgrade |
| [Source-runtime Python](<../Dockerfile.python-runtime>) | PASS build Linux amd64, checksum source dan import modul, dilaporkan parent | Versi tepat 3.15.2; bukan tes API |
| Image aplikasi final | PASS build, user `api` UID/GID10001, filesystem read-only, publish 127.0.0.1:8000 | Profil privat dan source checkout tidak ada pada filesystem image; bukan bukti production TLS |
| HTTP image rilis dan stop/start | PASS: liveness/docs/OpenAPI 200, empat method bisnis tanpa key 401, 404/405 envelope, storage belum tersedia 503; sesudah restart liveness/docs/schema kembali 200 | Swagger HTML/schema diperiksa lewat HTTP, bukan klik browser; key persistence/live CRUD belum diuji |
| Log runtime dan hooks exception | PASS sentinel/profile-value scan di memori; thread/unraisable nyata di container tidak mencetak canary/traceback; raw Uvicorn access logger dimatikan | Bug close background driver teramati pada run awal; hook sanitasi ditambahkan dan diregresi, bukan klaim upstream bug sudah diperbaiki |
| SDK/probe pool Oracle parent | TCPS Oracle 19.26, AL32UTF8; cold wait 2000 ms gagal DPY-4005, probe wait 10000 ms PASS dalam 2,758 detik | Default kini 5000 ms; bukan benchmark p95, auth/CRUD atau bukti profil runtime diubah |
| USER/ALL objects dan synonym target | Target KARYAWAN, tabel key dan function tidak ditemukan, dilaporkan parent | Auth/CRUD live terhalang objek belum tersedia |
| Delapan file SQL termasuk fresh-only bisnis baru yang disetujui | SOURCE; pengguna menerapkan manual | Tidak ada DDL/DML/provisioning key live yang diizinkan/dijalankan |
| Client TLS, p95, distribusi otomatis, restore production | NOT RUN | Provider/proxy/beban/izin/sign-off belum tersedia |

Angka di atas berasal dari eksekusi command aktual pada snapshot ini, bukan hasil lima tes integrasi live. Rerun lint/format/mypy dan suite setelah perubahan source; jangan menjumlahkan hasil Windows dan Linux yang menguji kasus beririsan.

## Delivery gate backend

- PASS verifikasi: lint/format, mypy, suite Linux/Windows dan smoke HTTP image dicatat di atas; tidak ada klaim compile/CRUD Oracle dari mock.
- PASS evidence/privacy: log dan runtime hooks diuji dengan canary; nilai profil dibandingkan di memori, tidak dicetak; tidak ada DDL/provisioning/tes tulis live. Scope scan bukan sertifikasi keamanan.
- UI/dials/klik-browser: tidak berlaku pada perubahan backend ini; Swagger hanya diverifikasi melalui HTML/schema HTTP, bukan diaku telah diklik.

## Matriks 12 functional requirements

| ID | Gate | Status/bukti | Sisa gate |
|---|---|---|---|
| FR-001 | HTTP REST | Offline dan smoke HTTP image PASS | Sign-off target production |
| FR-002 | API Key pada semua endpoint bisnis | Offline PASS | Empat route dengan auth Oracle nyata |
| FR-003 | Python SHA-256, 401/503 fail-closed | Offline PASS | Lookup metadata/state Oracle dan outage nyata |
| FR-004 | Due 7 hari, expiry 8 hari, readiness/grace | Offline lifecycle PASS | Concurrency/transaksi Oracle, distribusi dan scheduler aktual |
| FR-005 | CRUD lewat function | Source/contract PASS; live BLOCKED | Objek/signature/grants dan panggilan PL/SQL live |
| FR-006 | CREATE/READ/UPDATE/DELETE | Offline adapter/HTTP PASS | Fixture berizin dan hasil committed |
| FR-007 | Validasi bisnis Oracle | Source/contract PASS | Eksekusi function existing/deploy baru berizin |
| FR-008 | JSON konsisten | Offline HTTP PASS | Verifikasi target deploy; schema error eksplisit tersedia |
| FR-009 | Error/status | Offline PASS | Failure injection/transaksi Oracle berizin |
| FR-010 | Docker | Build/nonroot/HTTP/liveness/stop-start PASS | Persistensi key/state live dan target production |
| FR-011 | Log aman/request ID | Offline dan capture log container PASS; hook runtime diregresi | Proxy/operator production dan audit artefak lengkap |
| FR-012 | Dokumentasi development | Export/schema dan HTTP docs image PASS; production-off diuji unit | Pengujian interaksi browser dan target deployment |

## Seluruh 16 acceptance items asli

Urutan sama dengan PRD bagian 11. PASS offline parsial tidak menutup item live/deployment.

| No. | Acceptance | Status | Sisa evidence |
|---|---|---|---|
| 1 | FastAPI stabil melalui Docker | Build/HTTP/liveness/stop-start PASS | Soak/load target yang disepakati, bukan hanya smoke |
| 2 | FastAPI terhubung Oracle Development | Pool/metadata TCPS dari host dan container PASS terbatas | Tabel/function/state belum tersedia; tidak membuktikan autentikasi/CRUD sukses |
| 3 | CREATE melalui function | NOT RUN live | Izin tulis, fixture, commit dan cleanup |
| 4 | READ berdasarkan ID | NOT RUN live | Fixture berizin dan ID canonical |
| 5 | UPDATE | NOT RUN live | PUT penuh, commit dan pemulihan fixture |
| 6 | DELETE training | NOT RUN live | Fixture terisolasi dan recovery disetujui |
| 7 | Validasi bisnis error sesuai | Offline contract PASS; live NOT RUN | Duplikat/missing/invalid melalui function |
| 8 | Kosong/salah/PENDING 401; DB gagal 503; tanpa CRUD | Offline PASS; live NOT RUN | Auth Oracle nyata dan callback bisnis tidak dipanggil |
| 9 | Expired/revoked ditolak tanpa revival | Offline PASS; live NOT RUN | Boundary expiry dan state Oracle saat scheduler berhenti |
| 10 | A+7/A+8/grace, concurrency/retry, automation | Offline PASS parsial | Lock/transaksi live, scheduler/distribusi aktual; tetap semi-otomatis |
| 11 | Kanal aman dan readiness ID+VERSION/GLOBAL lock | Offline race check PASS; live NOT RUN | Kanal/ack seluruh penerima dan stale candidate/version live |
| 12 | Grace terbatas, revoke, emergency semua old live | Offline PASS; live NOT RUN | Transaksi atomik termasuk old GRACE dan replacement ready |
| 13 | Rollback saat DB gagal | Offline PASS; live NOT RUN | Failure injection, tidak ada partial write, unknown commit direkonsiliasi |
| 14 | Restart mempertahankan key state | NOT RUN | Restart container dan store/metadata persisten, tanpa mint ulang |
| 15 | Swagger/dokumentasi development | Offline/schema dan HTTP container PASS | Interaksi browser; production default off sudah diuji unit |
| 16 | Credential/API Key tidak muncul di log/repository | Offline sentinel/review PASS parsial | Audit artefak/log rilis/proxy; tanpa mencetak secret nyata |

## Tepat tiga milestone subsystem key

| Milestone | Bukti saat ini | Gate belum ditutup |
|---|---|---|
| M1 Auth MVP | Fondasi/settings/pool/hash/store/dependency dan offline tests tersedia | Privilege/storage/auth Oracle, bootstrap concurrent live, secure store pada host operator; bukan gate CRUD/Docker/TLS lengkap |
| M2 Rotation Engine/manual/emergency | Offline waktu terkontrol, readiness/race/version, grace/emergency dan rekonsiliasi | Concurrency/rollback/unknown commit Oracle, distribusi nyata; LAST_OPERATION_ID tertimpa memerlukan review manual |
| M3 External Automation/distribution/monitoring/recovery | Tick staging 24 jam sebelum due dan runbook tersedia | Scheduler menit aktual, kanal/provider/ack, alert pending-unready, restore/restart; semi-otomatis sampai distribusi/ack otomatis terbukti |

CRUD, Docker runtime, TLS, kapasitas pool/worker, privilege minimum, audit dependency/image, backup/restore dan p95 tetap gate PRD keseluruhan. Build PASS tidak menutup gate tersebut.

## Integrasi opt-in dan verifikasi berikutnya

Lima tes integrasi baru pada [direktori integrasi](<../tests/integration/>) hanya dikoleksi/skip offline. Read-only memerlukan `RUN_ORACLE_READONLY_INTEGRATION=1` dan `ORACLE_TEST_ENV_FILE` path absolut di luar project. Writes memerlukan `RUN_ORACLE_WRITE_INTEGRATION=I_ACKNOWLEDGE_ISOLATED_EMPTY_SCHEMA`, profil test eksplisit yang sama, schema/tabel kosong terisolasi, fixture dan izin terpisah. Profil runtime project saat ini dilarang. Variable acknowledgment bukan izin tulis atau provisioning/DDL otomatis; tidak ada izin DB writes pada pekerjaan ini.

1. Pengguna memverifikasi target/schema/PDB, privilege, schema kanonis dan delapan source SQL. [T_KARYAWAN](<../database/schema/T_KARYAWAN.sql>) fresh-only dan [function bisnis](<../database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) disetujui sebagai source; penerapan manual belum dijalankan. Mismatch legacy tetap menghentikan deployment.
2. HTTP/liveness/stop-start dan whitelist runtime sudah diverifikasi. Jangan rebuild default official base yang belum tersedia setelah memilih source-runtime. Stop/start proses belum membuktikan persistensi key karena schema/key belum diprovision.
3. Setelah izin terpisah, uji integration Oracle dengan fixture/cleanup dan catat hasil aktual. Kehadiran historical key saja bukan bukti commit operasi asli; reconcile memakai pool baru/lock GLOBAL dan manual review bila LAST_OPERATION_ID sudah berubah.
4. Uji client TLS/backend firewall, TCPS aplikasi, distribusi/readiness/scheduler/alert/restore. Ukur p95 pada beban yang disepakati; durasi unit test/probe koneksi bukan benchmark.
5. Catat waktu/timezone, artefak/digest, command aman, lingkungan, hasil, batas, pemilik dan sign-off untuk setiap gate. Parent menambahkan evidence runtime berikutnya; jangan menandai PASS sebelum bukti tersedia.
