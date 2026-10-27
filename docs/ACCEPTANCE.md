# Status penerimaan API_LOGISTIK

Project belum siap production. Dokumen ini memisahkan bukti source, tes offline, operasi Oracle live berizin, dan pekerjaan yang belum selesai. Requirement mengacu pada [PRD](<PRD.md>) bagian 4, 10, 11, dan 12.

`PASS` berlaku hanya pada pemeriksaan dan lingkungan yang disebutkan. `SOURCE` berarti implementasi tersedia tanpa bukti eksekusi pada gate tersebut; `NOT RUN` berarti belum diuji; `BLOCKED` berarti prasyarat belum tersedia. Build atau tes offline yang lulus tidak menutup acceptance Oracle live maupun production.

## Ringkasan terkini

Snapshot 27 Oktober 2026, zona waktu Asia/Jakarta:

| Area | Bukti terakhir | Batas |
|---|---|---|
| Suite offline Linux Docker | 343 passed, 2 Windows-only skips, 5 integration deselected, 9 subtests passed; coverage 85% | Satu warning TestClient/httpx; bukan suite integrasi Oracle |
| Lint dan format | Ruff check lulus; 48 file sesuai format | Bukan bukti runtime |
| Mypy | Linux dan target statis `win32` lulus pada 27 source files | Tidak menggantikan tes ACL Windows asli |
| API dan Oracle | Bootstrap key serta 24 pemeriksaan HTTP setelah aktivasi lulus pada Oracle 19.26/AL32UTF8 | Fixture dan client lokal yang disetujui, bukan production |
| Data fixture | 10 dummy awal tetap cocok; fixture CRUD sementara 91991 sudah dihapus | Tidak mengizinkan mutasi data lain |
| Operasi lanjutan | Rotasi, outage, concurrency, restart dengan key aktif, TLS client, recovery, dan p95 belum lengkap | Scheduler/distribusi otomatis belum dipasang atau dibuktikan |

## Bootstrap API Key dan CRUD HTTP live, 27 Oktober 2026 (Asia/Jakarta)

Target yang disetujui pengguna adalah koneksi FreeSQL pada profil lokal terbaru, bukan asumsi database training lama. Oracle terverifikasi 19.26/AL32UTF8 dengan fingerprint schema/PDB `3984146c9c7537a5`. Pengguna mengonfirmasi kesiapan client lokal setelah menerima file privat, lalu mengizinkan fixture CRUD ID 91991 beserta cleanup. Tidak ada DDL, perubahan routine, auth bypass, atau rotasi darurat.

### Provisioning dan readiness

Kedua tabel key canonical berstatus VALID, constraint enabled/validated, dan row GLOBAL berjumlah satu. Bootstrap dimulai tanpa key pada VERSION 0.

| Operasi CLI | Hasil |
|---|---|
| Init master key | File privat dibuat di luar repository |
| Prepare | Kandidat KEY_ID 1, PENDING, VERSION 1 |
| Export | Raw key tersimpan pada file privat; tidak dicetak |
| Tes key PENDING | GET bisnis menghasilkan 401 AUTH_001 sebelum aktivasi |
| Konfirmasi readiness | Kandidat ID 1/VERSION 1 cocok; state menjadi VERSION 2 |
| Activate | KEY_ID 1 ACTIVE, VERSION 3 |

Engine/repository yang sudah ada menangani perubahan dengan lock GLOBAL, bukan SQL autentikasi alternatif. Tidak ada retry mutasi atau commit outcome unknown pada operasi ini.

Master key, encrypted store, export, dan audit berada di luar repository, dengan direktori 0700 dan file 0600 milik UID operator host. Profil operator terpisah memuat acknowledgment dan path privat; koneksi DB berasal dari konfigurasi lokal yang disetujui. Ini belum membuktikan pemisahan privilege akun DB atau integrasi secret manager production.

### Hasil HTTP setelah aktivasi

Run ID audit tersanitasi: `494fc26e-1a4a-4252-aae4-93247d7d4ed2`. Seluruh 24 response mempunyai request ID.

| Pemeriksaan | Hasil |
|---|---|
| Health tanpa key | 200 |
| Key missing, malformed, dan salah dengan format valid | Masing-masing 401 AUTH_001 |
| READ 10 dummy awal | Masing-masing 200; seluruh field cocok |
| ID sementara belum ada | 404 KRY_404 |
| Path invalid | 422 REQUEST_422 |
| POST fixture, lalu POST duplikat | 201 SUCCESS, lalu 409 KRY_001 |
| GET hasil CREATE | 200; duplikat tidak mengubah data |
| PUT penuh, lalu PUT tidak lengkap | 200, lalu 422 tanpa mengubah hasil update |
| GET hasil UPDATE | 200; seluruh field cocok |
| DELETE fixture, lalu GET | 200, lalu 404 |

### Kondisi akhir dan privasi

Pool Oracle baru memastikan fixture 91991 tidak tersisa, 10 dummy awal tetap cocok, dan tepat satu key ACTIVE. GLOBAL berada pada VERSION 3 tanpa pointer PENDING/GRACE.

| Metadata key pada snapshot | Waktu WIB |
|---|---|
| Aktivasi aktual | 27 Oktober 2026, 20:19:52 |
| Due rotasi A+7 hari | 3 November 2026, 20:19:52 |
| Expiry A+8 hari | 4 November 2026, 20:19:52 |

Scan 75 calon file publikasi dan log API tidak menemukan raw key, master key, atau digest key. Client membaca header key dari file privat ke memori. Container API tidak menerima setting operator/master/store atau mount privat. Dokumen ini tidak memuat key, hash key, atau credential. Hasil scan terbatas pada artefak yang diperiksa, bukan sertifikasi keamanan.

Bootstrap dan satu siklus CRUD tidak membuktikan concurrency, stale VERSION race, grace/rotation/revoke/emergency, expiry boundary, outage 503, unknown commit, failure injection rollback, restart dengan key aktif, distribusi otomatis, backup/restore, TLS client, atau p95. Tidak ada klik browser Swagger atau eksekusi suite integrasi opt-in.

Pada akhir pengujian, key dibiarkan ACTIVE untuk development yang disetujui. Scheduler belum dipasang; operator harus menyiapkan successor dan distribusi sebelum due. Expiry tidak diperpanjang otomatis. Jangan menghapus material privat tanpa backup/recovery. Operasi ini tidak mencakup commit atau push Git.

## Eksekusi fixture Oracle live berizin, 27 Oktober 2026 (Asia/Jakarta)

Sebelum bootstrap key, pengguna memberi izin terpisah untuk menambahkan 10 dummy dan COMMIT pada target dengan fingerprint yang sama. Credential dan nama login tidak dicatat.

- Preflight menemukan tabel dan function CRUD VALID, schema sama dengan session user, struktur/signature sesuai, primary key enabled/validated, tanpa trigger aktif, dan ID 90001 sampai 90010 kosong. Source function deployed cocok dengan source lokal setelah normalisasi komentar/whitespace, tanpa kontrol transaksi internal.
- [D_DUMMY_KARYAWAN.sql](<../database/seed/D_DUMMY_KARYAWAN.sql>) dieksekusi sebagai blok PL/SQL pada sesi khusus dengan autocommit False. Wrapper memeriksa sepuluh respons function serta seluruh nilai fixture sebelum COMMIT eksplisit. File fixture tetap tanpa COMMIT otomatis.
- Pool/koneksi baru menemukan tepat 10 ID terisi dan 10 baris cocok seluruh field. Tidak ada overwrite, perubahan schema/function, provisioning key, atau retry mutasi pada tahap ini.
- Perbandingan di memori memastikan environment API cocok dengan profil Compose terbaru. Nilainya tidak dicetak dan API tidak direstart.

Tahap ini hanya membuktikan CREATE fixture dan pembacaan SQL agregat. Bukti CRUD HTTP berikutnya berada di bagian bootstrap di atas. Failure injection rollback, concurrency, dan acceptance production tetap terbuka. Penghapusan 10 dummy setelah COMMIT memerlukan izin terpisah.

## Penyiapan source fixture dummy, 27 Oktober 2026 (Asia/Jakarta)

Pengguna menyetujui [fixture dummy](<../database/seed/D_DUMMY_KARYAWAN.sql>) dan pengecualian [registry PRD bagian 16.4](<PRD.md#164-fixture-dummy-karyawan-persetujuan-27-oktober-2026>): 10 data sintetis lewat function CRUD, tanpa overwrite atau COMMIT otomatis, dengan rollback ke savepoint saat gagal.

Tujuh [source-contract fixture](<../tests/contracts/test_dummy_seed_contracts.py>) ditambahkan. Suite final menghasilkan 343 passed, 2 Windows-only skips, 5 integration deselected, 9 subtests passed, coverage 85%, dan satu warning TestClient/httpx. Ruff check serta format check 48 file lulus. Tes berjalan sebagai UID10001 dengan network none, filesystem read-only, dan tmpfs, tanpa credential atau koneksi Oracle.

Run awal terhenti karena dua file source baru berpermission 0600, sehingga pengguna container non-root tidak bisa membacanya. Permission source nonrahasia diubah menjadi 0644; permission secret tetap. Satu mismatch format tes juga diperbaiki sebelum run final lulus.

Tahap penyiapan source tidak menjalankan SQL live. Eksekusi berikutnya memerlukan preflight dan izin terpisah seperti catatan di atas serta [panduan fixture](<../database/README.md#d-mengisi-dummy-karyawan-opsional>). Source-contract bukan bukti kompilasi atau rollback Oracle live.

## Deployment WSL2, 27 Oktober 2026 (Asia/Jakarta)

Lingkungan: Ubuntu 24.04.5 WSL2, Linux amd64, Docker Engine 29.9.2, Compose v5.6.1, dan Buildx v0.38.1 pada distro yang sama. Perubahan mencakup pin image resmi, petunjuk deployment, dan guard platform secret store. Versi Python/dependency, SQL bisnis, serta kebijakan permission/ACL tidak berubah.

| Pemeriksaan | Hasil dan batas |
|---|---|
| Image resmi Python | Tersedia; [Dockerfile](<../Dockerfile>) memakai OCI index `sha256:197f6622a70b727a4e61bdac13a73b4e2b914b896aa5a729ceb1f45a09bde5fa`; bukan audit supply chain lengkap |
| Compose dan build | Validasi memakai `/dev/null`; build `uv sync --locked --no-dev --no-editable --no-python-downloads`; Python runtime 3.15.2 |
| Isolasi container | Healthy, UID/GID10001, filesystem read-only, cap-drop ALL, no-new-privileges, loopback 8000, tanpa bind mount |
| HTTP dan stop/start | Health/docs/OpenAPI 200, empat method bisnis tanpa key 401, malformed header 401, unknown route 404; endpoint publik kembali 200 setelah stop/start |
| Suite setelah perbaikan mypy | 336 passed, 2 Windows-only skips, 5 integration deselected, 9 subtests passed; coverage 85%, satu warning TestClient/httpx |
| Lint/format | Ruff check lulus; 47 file sesuai format pada tahap ini |
| Mypy Linux dan target Windows | Mypy 2.4.0 lulus pada 27 source files untuk kedua target; enam error awal ditutup dengan guard `sys.platform`, bukan suppression |
| Environment dan log | Whitelist cocok dengan profil privat; setting operator/master/store tidak diteruskan; scan tidak menemukan nilai profil atau sentinel malformed header |

Image dibangun ulang setelah perbaikan. SHA-256 source secret store terpasang cocok dengan source lokal; log tidak memuat nilai profil atau traceback. Pengujian pada tahap deployment ini belum memakai key valid atau koneksi Oracle. Stop/start mendahului provisioning, sehingga belum membuktikan persistensi key setelah restart. Swagger hanya diperiksa sebagai HTML/schema HTTP, bukan lewat klik browser.

## Bukti historis 26 Oktober 2026 dan batas

Catatan ini mempertahankan hasil sebelum migrasi WSL2. Kondisi lama, seperti image belum tersedia atau objek Oracle belum ditemukan, bukan status target terkini.

| Pemeriksaan historis | Hasil | Batas |
|---|---|---|
| Suite Linux Docker, Python 3.15.2 | 334 passed, 2 Windows-only skips, 5 integration deselected; coverage 85% | Network none, non-root, read-only; bukan Oracle live |
| Suite Windows | 318 passed, 18 skips | 16 kasus lokasi privat memerlukan temp di luar checkout; kasus itu berjalan di Linux, bukan di-mock agar lolos |
| Lint/format dan mypy | Lulus; mypy 27 source files | Bukan deployment atau pengujian DB |
| Exporter terinstal dengan `-I` | Offline lulus; lima operasi/tiga path, output default/custom | Dotenv/settings/pool dipatch menolak akses; output ditangkap di memori |
| Compose/environment | Parsing lulus; nilai DB cocok dengan profil; setting operator tidak diteruskan | Nilai dibandingkan di memori, tidak dicetak |
| Image resmi Python | Manifest 3.15.2-slim belum tersedia saat lookup | Kini sudah tersedia; tidak ada downgrade |
| [Source-runtime Python](<../Dockerfile.python-runtime>) | Build Linux amd64, checksum, versi 3.15.2, dan import modul lulus | Bukan tes API |
| Image aplikasi | Build non-root/read-only, loopback 8000; profil privat dan checkout tidak ada di runtime | Bukan bukti TLS production |
| HTTP dan stop/start | Health/docs/schema 200; bisnis tanpa key 401; 404/405 envelope; storage auth 503 | Belum menguji persistensi key atau CRUD saat itu |
| Log dan runtime hooks | Canary/profile-value scan lulus; thread/unraisable nyata tidak mencetak traceback; access logger mati | Bug background close teramati, sanitasi diregresi; bukan perbaikan upstream |
| Pool Oracle | TCPS Oracle 19.26/AL32UTF8; wait 2000 ms gagal DPY-4005, probe wait 10000 ms lulus dalam 2,758 detik | Default kemudian 5000 ms; bukan p95 atau bukti auth/CRUD |
| Metadata objek | Objek project belum terlihat melalui USER/ALL objects atau synonym | Kondisi sebelum pengguna memasang objek |
| Delapan source SQL awal | Tersedia untuk penerapan manual | Tidak ada DDL/DML/provisioning live pada tahap itu |
| TLS client, p95, distribusi otomatis, restore production | Belum dijalankan | Target/provider/beban/izin/sign-off belum tersedia |

Jangan menjumlahkan hasil Windows dan Linux yang menguji kasus beririsan. Ulangi pemeriksaan yang relevan setelah source berubah; jangan mewarisi kelulusan snapshot lama.

## Delivery gate backend

- Verifikasi: bukti offline, build, bootstrap, dan HTTP live dicatat per tahap. Tidak ada klaim Oracle live dari mock atau source saja.
- Privasi: canary, nilai profil, raw key, master key, dan digest dipindai sesuai scope. Tidak ada DDL oleh agent; provisioning serta mutasi fixture hanya memakai izin yang dikonfirmasi. Scan bukan sertifikasi keamanan.
- UI: pemeriksaan visual, dials, dan klik browser tidak berlaku untuk pekerjaan backend ini. Swagger hanya diperiksa lewat HTML/schema HTTP.

## Matriks 12 functional requirements

| ID | Gate | Bukti saat ini | Sisa gate |
|---|---|---|---|
| FR-001 | HTTP REST | Offline dan smoke HTTP image lulus | Sign-off production |
| FR-002 | Key pada semua endpoint bisnis | Offline dan CRUD HTTP live lulus pada fixture | Expired/revoked live dan gate production |
| FR-003 | SHA-256, 401/503, fail-closed | Lookup/auth live lulus; missing/wrong/PENDING 401; 503 lulus offline | Outage database live dan penolakan expired/revoked |
| FR-004 | A+7/A+8, readiness/grace | Offline lifecycle dan metadata bootstrap/readiness live lulus | Concurrency, cutover/grace/retry, scheduler/distribusi otomatis |
| FR-005 | CRUD lewat function | Source-contract dan empat mode HTTP Oracle live lulus | Privilege minimum dan target production |
| FR-006 | Empat operasi CRUD | Satu siklus HTTP committed lulus; fixture dibersihkan | Concurrency/failure dan sign-off target |
| FR-007 | Validasi bisnis Oracle | Duplikat 409, missing 404, serta source-contract lulus | Seluruh validasi bisnis Oracle dan failure injection |
| FR-008 | JSON konsisten | Offline dan 24 pemeriksaan HTTP live lulus | Sign-off production |
| FR-009 | Error/status | 200/201/401/404/409/422 HTTP live lulus | 500/503, outage/unknown commit, rollback setelah kegagalan teknis |
| FR-010 | Docker | Build/non-root/HTTP/liveness/stop-start lulus | Persistensi setelah restart dengan key aktif dan production |
| FR-011 | Log/request ID | Offline, runtime hooks, serta scan log container lulus dalam scope | Proxy/operator production dan audit artefak lengkap |
| FR-012 | Dokumentasi development | Export/schema dan HTTP docs lulus; default production-off diuji unit | Interaksi browser dan target deployment |

## Seluruh 16 acceptance items asli

Urutan mengikuti PRD bagian 11. Hasil parsial tidak menutup requirement secara keseluruhan.

| No. | Acceptance | Bukti | Sisa evidence |
|---|---|---|---|
| 1 | FastAPI stabil melalui Docker | Build/HTTP/liveness/stop-start lulus | Soak/load target yang disepakati |
| 2 | Koneksi Oracle Development | TCPS, metadata auth/state, dan CRUD HTTP pada target pengguna lulus | Privilege/separasi akun dan production |
| 3 | CREATE lewat function | Fixture 91991 dan 10 dummy berizin lulus | Concurrency/failure dan production |
| 4 | READ berdasarkan ID | 10 dummy dan fixture CRUD dengan ID canonical lulus | Target production |
| 5 | UPDATE | PUT penuh dan pembacaan hasil lulus; fixture kemudian dihapus | Concurrency/failure |
| 6 | DELETE training | Fixture 91991 terhapus; pool baru memastikan tidak tersisa | Tidak memberi izin menghapus data lain |
| 7 | Error validasi bisnis | Duplikat/missing live dan shape 422 lulus | Seluruh validasi bisnis Oracle, bukan hanya Python |
| 8 | Missing/wrong/PENDING 401; DB failure 503; tanpa CRUD | Penolakan key live lulus; 503 lulus offline | Outage/503 live dan observasi callback saat outage |
| 9 | Expired/revoked ditolak tanpa revival | Offline lulus; live belum diuji | Boundary expiry dan state saat scheduler berhenti |
| 10 | A+7/A+8/grace, concurrency/retry, automation | Offline lulus parsial; metadata bootstrap live cocok | Cutover/grace/concurrency/retry dan otomasi aktual |
| 11 | Kanal aman dan readiness ID+VERSION/GLOBAL lock | CLI bootstrap serta file privat/client lokal siap lulus; race diuji offline | Kanal production, ack semua penerima, stale candidate/version concurrent live |
| 12 | Grace terbatas, revoke, emergency seluruh old live | Offline lulus; live belum diuji | Transaksi atomik termasuk GRACE dan replacement siap |
| 13 | Rollback saat DB gagal | Offline lulus; live belum diuji | Failure injection, partial write, unknown commit/reconcile |
| 14 | Restart mempertahankan state key | Belum diuji dengan key aktif | Restart, store/metadata persisten, tanpa mint ulang |
| 15 | Swagger/dokumentasi development | Offline/schema dan HTTP container lulus | Interaksi browser; default production-off sudah diuji unit |
| 16 | Credential/key tidak muncul di log/repository | Canary serta scan source/log live lulus dalam scope | Audit artefak/log rilis/proxy lengkap, tanpa mencetak secret |

## Tepat tiga milestone subsystem key

| Milestone | Bukti saat ini | Gate terbuka |
|---|---|---|
| M1 Auth MVP | Fondasi/offline, storage/read/auth Oracle, bootstrap CLI, private store Linux, dan CRUD HTTP live | Bootstrap concurrent, permission failure injection live, outage auth/503, privilege minimum, dan sign-off production |
| M2 Rotation Engine/manual/emergency | Offline waktu terkontrol, readiness/race/version, grace/emergency, dan rekonsiliasi | Concurrency/rollback/unknown commit Oracle serta distribusi nyata; LAST_OPERATION_ID yang tertimpa memerlukan review manual |
| M3 External Automation/distribution/monitoring/recovery | Tick staging 24 jam sebelum due dan runbook tersedia | Scheduler menit aktual, kanal/provider/ack, alert pending-unready, restore/restart; tetap semi-otomatis sebelum distribusi/ack otomatis terbukti |

CRUD, Docker, TLS, pool/worker, privilege minimum, audit dependency/image, backup/restore, dan p95 tetap bagian penerimaan project. Build yang lulus tidak menutup gate tersebut.

## Integrasi opt-in dan verifikasi berikutnya

Lima tes pada [direktori integrasi](<../tests/integration/>) hanya dikoleksi/skip offline, belum dijalankan live. Read-only memerlukan `RUN_ORACLE_READONLY_INTEGRATION=1` dan `ORACLE_TEST_ENV_FILE` absolut di luar project. Writes juga memerlukan `RUN_ORACLE_WRITE_INTEGRATION=I_ACKNOWLEDGE_ISOLATED_EMPTY_SCHEMA`, profil test terpisah, schema/tabel fixture kosong terisolasi, dan izin. Profil runtime project dilarang untuk suite ini. Izin bootstrap/manual HTTP fixture tidak mengaktifkan suite atau memberi izin mutasi lain.

1. Verifikasi target/schema/PDB, privilege, schema canonical, dan sembilan source SQL. Fixture dummy bersifat opsional. [Tabel bisnis](<../database/schema/T_KARYAWAN.sql>) dan [function](<../database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) terlihat VALID pada target pengguna tanpa DDL oleh agent; target baru tetap memerlukan preflight/penerapan manual. Mismatch legacy menghentikan deployment.
2. Ulangi stop/start secara berizin dengan key aktif. Pengujian restart terdahulu mendahului provisioning. Image resmi Python kini tersedia dan dipin digest.
3. Uji integrasi Oracle dengan fixture/cleanup dan izin terpisah. Historical key bukan bukti commit operasi asli; reconcile memakai pool baru dan lock GLOBAL, lalu review manual jika LAST_OPERATION_ID berubah.
4. Uji TLS client/firewall, TCPS, distribusi/readiness/scheduler/alert, dan restore. Ukur p95 pada beban yang disepakati; durasi unit test atau probe koneksi bukan benchmark.
5. Catat waktu/timezone, artefak/digest, command aman, lingkungan, hasil, batas, pemilik, dan sign-off untuk setiap gate. Jangan menandai lulus sebelum bukti tersedia.

## Audit dokumentasi, 27 Oktober 2026

Perapian mencakup sembilan Markdown milik project, termasuk instruksi agent lokal yang tetap diabaikan Git. Pemeriksaan meliputi 151 tautan/anchor lokal, sintaks enam blok Bash dan enam contoh JSON, serta keseimbangan code fence dan whitespace. Signature/contoh SQL PRD, 12 FR, 16 kriteria acceptance, registry path, tiga milestone, contoh JSON API, dan perintah operasional tetap terjaga.

Hash 67 file non-Markdown cocok dengan baseline sebelum penyuntingan. Source-contract terhadap dokumen terbaru menghasilkan 37 passed dalam container non-root/read-only dengan network none. Ini bukan rerun suite penuh atau tes Oracle live. Tidak ada perubahan database, key, kode aplikasi, container API, staging, commit, atau push. URL eksternal tidak diperiksa ulang secara online; pemeriksaan tautan hanya mencakup path dan anchor lokal.
