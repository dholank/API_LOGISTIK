# Rencana Pembangunan Ulang API_LOGISTIK

Acuan: [PRD](<PRD.md>) dan [arsitektur](<ARCHITECTURE.md>). PRD bagian 15/16 adalah registry tunggal nama/signature objek dan path SQL. Source API/CLI, delapan SQL, tes dan Docker tersedia. Runtime memakai Python 3.15.2, python-oracledb 26.0.1, uv 0.13.5 dan satu lockfile. Build dan tes offline bukan deployment Oracle; hasil aktual serta gate yang masih terbuka dicatat pada [acceptance](<ACCEPTANCE.md>). Direktori atau source bukan bukti acceptance.

## 1. Aturan dan pekerjaan saat ini

- Muat antislop dan skill relevan; sebelum kode/konfigurasi teknologi gunakan Context7 sesuai [standar kerja project](<PRD.md#17-standar-kerja-dan-target-teknologi>). Dokumentasi ini tidak menginstal dependency atau menulis aplikasi Python.
- Target Oracle Database 19c Enterprise Edition. Verifikasi Python stabil terbaru dan dukungan FastAPI/Pydantic/python-oracledb/platform sebelum setup, lalu kunci versi development/CI/Docker serta satu tool/lockfile. Konflik dukungan memerlukan keputusan pengguna, bukan downgrade diam-diam.
- Pertahankan nama/signature bisnis dan validasi CRUD Oracle. Generasi, hashing, validasi dan rotasi Global API Key seluruhnya di Python; Oracle hanya storage/metadata serta transaksi SQL biasa untuk key. Tidak ada dependency crypto/scheduler/auth routine Oracle.
- SQL boleh disiapkan offline sekarang tanpa menunggu privilege check live. Pengguna melakukan preflight manual target/schema/PDB/privilege sebelum menerapkan sendiri. Jangan DB connect/push, menjalankan DDL/DML, mint key, atau mengklaim live pass pada pekerjaan source.
- Delapan file SQL sesuai registry PRD: dua Q_ read-only, tiga T_ fresh-only termasuk KARYAWAN, satu F_ CRUD fresh-only yang disetujui pengguna, satu C_ patch status legacy dikenal, satu D_ seed GLOBAL. D_ diperlukan karena seed adalah DML, bukan query read-only. Panduan penerapan ada di [panduan database](<../database/README.md>).
- Precheck tidak menampilkan raw key/nilai hash. Verifikasi pascadeploy mencakup schema kanonis, count/status/waktu/state. Seed MERGE hanya row GLOBAL yang hilang, tanpa mengubah existing/mint key; COMMIT eksplisit memerlukan sesi admin khusus.
- Patch CK_API_KEY_AUTH_STATUS tidak rename ACTIVE_AT/EXPIRED_AT dan bukan migrasi penuh. Jika legacy tidak cocok dengan ACTIVATES_AT/EXPIRES_AT kanonis, hentikan deployment/runtime kanonis sampai ada keputusan migrasi.
- Validator/procedure/job key lama pada PRD hanya historis, tidak dieksekusi, dibuat ulang atau di-drop. Jangan membuat function/procedure/job key baru atau mengisi skeleton di luar scope.
- Hubungkan perubahan dengan FR/acceptance. Pisahkan pemeriksaan source, fake/mock, compile, Oracle live dan deployment. Secret/data karyawan nyata tidak masuk source, contoh, log atau laporan.

## 2. Tiga milestone

### M1 Auth MVP

Requirement utama: FR-001, FR-002, FR-003 serta bagian response/error/logging/dokumentasi FR-008, FR-009, FR-011, FR-012. Ini fondasi dan subsystem auth, bukan pembangunan ulang CRUD atau deployment Docker/TLS.

Ruang lingkup milestone (implementasi source tersedia, bukti live terpisah):

- Pengguna memverifikasi sandbox, schema/PDB, privilege dan layout sebelum integrasi live. Preflight manual bukan gate pembuatan source SQL offline.
- Tambahkan fondasi minimum pada src layout yang ada: app/settings/pool, liveness, error mapping, request ID, log tersanitasi, dan dependency auth reusable. Jangan koneksi saat import atau membuat ulang project.
- Python memakai secrets.token_urlsafe(32), hashlib.sha256 UTF-8, lowerhex64 di storage, dan validasi status/waktu/pointer GLOBAL; tidak trim atau ubah case raw key.
- Simpan material secara aman di luar Oracle/repository sebelum bootstrap, dengan konfirmasi distribusi operator sebelum aktivasi awal. Lock singleton mencegah bootstrap ganda. Aktivasi A menetapkan due A+7 hari dan expiry asli A+8 hari.
- Dependency auth kini terpasang pada keempat handler bisnis; tes API memakai fake repository yang diberi label terisolasi, bukan respons produksi palsu. Handler memanggil function Oracle melalui repository saat runtime. Source function fresh-only tersedia atas persetujuan pengguna; tidak menimpa function existing.

Gate:

- [ ] Package/settings/pool dan import smoke test lulus; liveness berjalan tanpa Oracle dan tanpa side effect import.
- [ ] Generator dan test vector hash benar; raw key tidak pernah menjadi bind Oracle, output/log/exception, contoh atau credential template.
- [ ] Key ACTIVE valid diterima; key kosong/salah/pending/expired/revoked menghasilkan 401; tepat pada expiry key ditolak.
- [ ] Kegagalan koneksi/pool/query auth menghasilkan 503 dan callback bisnis tidak berjalan; tidak ada cache fallback atau auth bypass.
- [ ] Bootstrap bersamaan hanya menghasilkan satu state canonical dan tidak mengaktifkan key sebelum distribusi dikonfirmasi.
- [ ] Secure-store gagal/permission tidak aman menghentikan bootstrap; material canonical tidak hilang akibat cleanup/retry.
- [ ] Storage/read dan privilege Oracle dibuktikan melalui pengujian berizin, terpisah dari tes fake/source-contract. Belum ada klaim live pada paket SQL ini.

M1 belum menjanjikan rotasi atau production readiness. Requirement bisnis, Docker, TLS dan penerimaan project keseluruhan tetap dijadwalkan/dibuktikan terpisah, tanpa memasukkannya sebagai implementasi auth atau pekerjaan SQL-only saat ini.

### M2 Rotation Engine/manual/emergency

Requirement: FR-004, FR-002, FR-003, FR-009, FR-011.

Implementasikan engine Python dan jalur operator terotorisasi, bukan endpoint CRUD atau startup task. Prepare, konfirmasi readiness, aktivasi, revoke dan rekonsiliasi menggunakan transaksi SQL biasa dengan lock row GLOBAL. Candidate ID tepat dan VERSION harus cocok saat konfirmasi readiness sebelum aktivasi; kandidat/versi stale ditolak. State/key berubah atomik; operation ID membantu retry tanpa double activation.

Aktivasi aktual A menetapkan due A+7 hari dan expiry asli A+8 hari. Cutover normal B memberi key lama live GRACE sampai min(expiry asli, B+24 jam). Tidak memperpanjang key ketika terlambat atau revive EXPIRED/REVOKED. Operator dapat revoke kompromi segera tanpa replacement dan menerima risiko outage. Aktivasi darurat hanya replacement baru yang readiness-nya terkonfirmasi, serta mencabut semua key lama live termasuk GRACE dalam transaksi yang sama, tanpa bypass.

Gate:

- [ ] Waktu terkontrol mencakup due/expiry boundary, grace, cutover terlambat melewati expiry, scheduler berhenti dan penolakan revival.
- [ ] Concurrent worker, readiness candidate salah, VERSION stale, rollback, retry dan commit tidak diketahui mempunyai bukti rekonsiliasi.
- [ ] Kanal aman dan konfirmasi penerimaan mendahului aktivasi; raw key tidak masuk SQL/source/log.
- [ ] Revoke segera dan emergency replacement siap teruji, tanpa overlap darurat atau auth bypass.
- [ ] Tes model/fake dibedakan dari transaksi/locking Oracle live opt-in.

### M3 External Automation/distribution/monitoring/recovery

Requirement: FR-004 serta availability/reliability/privacy PRD; seluruh 16 acceptance items tetap berlaku untuk penerimaan akhir.

Scheduler eksternal memicu engine Python. Tidak memakai DBMS_SCHEDULER atau routine autentikasi/rotasi Oracle. Tick bukan jadwal Senin tetap: due mengikuti A+7 hari. Distribusi raw key lewat kanal rahasia dan ack readiness juga harus diotomatisasi sebelum mengklaim end-to-end otomatis; sementara itu scheduler tetap semi-otomatis.

Gate:

- [ ] Pemicu aktual, distribusi/ack, aktivasi dan hasil/no-op tercatat tersanitasi; script saja bukan bukti automation berjalan.
- [ ] No-successor, distribusi gagal, readiness belum ada, expiry dekat, worker down dan DB failure menghasilkan alert/escalation; expiry tidak diperpanjang sebagai recovery diam-diam.
- [ ] Restart container mempertahankan state; recovery, retry pascacommit tidak diketahui dan emergency mempunyai runbook serta bukti uji.
- [ ] Ukur p95 pada beban development yang disepakati, bukan durasi unit test; target awal bukan klaim performance.
- [ ] Dokumen operasi/API/acceptance memuat target, waktu, metode, hasil dan batas tanpa secret; seluruh acceptance wajib lulus dan pengguna memberi sign-off. Unit/source-contract tidak dilabeli live pass.

## 3. Dokumen bertahap

[README](<../README.md>) mencatat status dan petunjuk yang benar-benar tersedia. `docs/API.md`, `docs/OPERATIONS.md`, `docs/ACCEPTANCE.md` serta `docs/decisions/` dibuat ketika punya isi nyata: kontrak API/OpenAPI, distribusi/operator/scheduler/TLS/recovery, bukti requirement, dan keputusan driver/pool/lockfile. Jangan membuat placeholder kelulusan atau perintah runtime yang belum tersedia. Ekspor OpenAPI, laporan tes dan bundle distribusi dipisahkan dari source.
