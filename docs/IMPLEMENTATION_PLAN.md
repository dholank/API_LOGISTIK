# Rencana Pembangunan Ulang API_LOGISTIK

[PRD](<PRD.md>) menetapkan requirement serta registry tunggal nama, signature, dan path SQL pada bagian 15/16. [Arsitektur](<ARCHITECTURE.md>) menetapkan batas modul. Rencana ini membagi subsystem Global API Key menjadi tepat tiga milestone; requirement CRUD, Docker, TLS, dan penerimaan project tetap berlaku di luar pembagian tersebut.

Source API/CLI, sembilan SQL termasuk fixture dummy opsional, tes, dan Docker tersedia. Runtime terkunci pada Python 3.15.2, python-oracledb 26.0.1, dan uv 0.13.5 dengan satu lockfile. [Acceptance](<ACCEPTANCE.md>) mencatat 445 tes offline lulus, bootstrap key ID 1 dari VERSION 0 ke 3, serta 24 pemeriksaan HTTP live. Fixture sementara 91991 sudah dihapus dan 10 dummy 90001 sampai 90010 tetap utuh. Bukti ini tidak menutup seluruh gate milestone atau membuktikan kesiapan production.

Tahap aktif yang disetujui pada 29 Oktober 2026 adalah M2 manual terlebih dahulu. [Launcher operator](<../scripts/api_key_operator.sh>) menjalankan `status → prepare → export → confirm-distributed → activate → status` sebagai langkah terpisah dengan profil, pin image, material key, dan audit privat di luar project. Operator tetap wajib memenuhi due A+7/expiry A+8 serta readiness ID+VERSION. Setup launcher tidak mengaktifkan API, menerbitkan kandidat, merotasi key live, atau memasang timer. Rincian operasional ada di [runbook manual](<OPERATIONS.md#alur-utama-rotasi-manual>).

M3 ditunda tanpa menghapus requirement automation. Scheduler, guard composite tick setelah proses terputus/commit unknown, kanal distribusi/ack, dan alert/recovery perlu ditambahkan serta diuji sebelum sistem disebut otomatis. Engine dan schema tidak diganti untuk perpindahan tahap ini.

## 1. Aturan dan pekerjaan saat ini

- Muat antislop dan skill yang sesuai. Sebelum mengubah kode atau konfigurasi teknologi, baca dokumentasi versi terkait melalui Context7 sesuai [standar kerja project](<PRD.md#17-standar-kerja-dan-target-teknologi>).
- Target database tetap Oracle Database 19c Enterprise Edition. Saat setup, verifikasi Python stabil terbaru beserta dukungan FastAPI, Pydantic, python-oracledb, dependency transitif, dan platform. Kunci versi development/CI/Docker serta satu tool/lockfile; konflik dukungan memerlukan keputusan pengguna, bukan downgrade diam-diam.
- Pertahankan nama/signature function bisnis dan validasi CRUD Oracle. Python menangani pembuatan, hashing, validasi, dan rotasi Global API Key. Oracle hanya menyimpan hash/metadata dan menjalankan transaksi SQL biasa untuk key, tanpa dependency crypto, scheduler, atau routine autentikasi Oracle.
- Source SQL boleh disiapkan offline sebelum preflight privilege live. Penerapan DDL tetap manual oleh pengguna/DBA. Source bukan izin DB connect/push, DDL/DML, mint key, atau klaim live lulus; setiap operasi memerlukan target/schema/PDB, fixture, scope izin, dan rencana pemulihan yang jelas.
- Paket SQL mengikuti registry PRD: dua Q_ read-only, tiga T_ fresh-only, satu F_ CRUD fresh-only, satu C_ patch status legacy, satu D_ seed GLOBAL, dan satu D_ fixture dummy opsional. Fixture hanya menambah 10 data sintetis lewat function CRUD, tanpa overwrite/COMMIT otomatis; kegagalan membatalkan seluruh penambahan blok ke savepoint. Ini bukan endpoint bulk API. Ikuti [panduan database](<../database/README.md>).
- Precheck tidak menampilkan raw key atau nilai hash. Verifikasi sesudah deployment mencakup schema kanonis, count, status, waktu, dan state. Seed GLOBAL hanya MERGE row yang hilang, tanpa mengubah existing atau mint key; COMMIT eksplisit memerlukan sesi admin khusus.
- Patch CK_API_KEY_AUTH_STATUS tidak mengganti nama ACTIVE_AT/EXPIRED_AT atau menyelesaikan migrasi. Mismatch dengan ACTIVATES_AT/EXPIRES_AT kanonis menghentikan deployment/runtime sampai ada keputusan migrasi.
- Validator, procedure, dan job key lama hanya historis: tidak dieksekusi, dibuat ulang, atau di-drop. Jangan menambah function/procedure/job key atau skeleton di luar scope.
- Hubungkan perubahan dengan FR dan acceptance. Pisahkan bukti source, fake/mock, kompilasi, Oracle live, dan deployment. Secret, credential, raw key, dan data karyawan nyata tidak masuk source, contoh, log, atau laporan.

## 2. Tiga milestone

### M1 Auth MVP

Requirement utama: FR-001, FR-002, FR-003, serta bagian response/error/logging/dokumentasi FR-008, FR-009, FR-011, FR-012.

Fondasinya mencakup app/settings/pool, liveness tanpa Oracle, error mapping, request ID, log tersanitasi, dan dependency X-API-Key pada keempat handler bisnis. Import tidak membuka koneksi atau menjalankan provisioning. Handler runtime memanggil function Oracle; fake repository pada tes harus jelas sebagai fixture terisolasi, bukan respons produksi. Source function tetap fresh-only dan tidak menimpa objek existing.

Python membuat key dengan `secrets.token_urlsafe(32)`, menghitung SHA-256 UTF-8 melalui `hashlib.sha256`, dan memvalidasi lowerhex64, status, waktu, serta pointer GLOBAL. Raw key tidak di-trim atau diubah case. Material disimpan secara aman di luar Oracle/repository sebelum bootstrap; konfirmasi distribusi mendahului aktivasi. Lock singleton mencegah bootstrap ganda. Aktivasi A menetapkan due A+7 hari dan expiry asli A+8 hari.

Bukti saat ini: fondasi dan tes offline tersedia; storage/read/auth Oracle, bootstrap CLI, private store Linux, dan CRUD HTTP live sudah diuji pada scope berizin. Bootstrap concurrent, outage auth, failure injection permission, serta privilege minimum masih memerlukan bukti live.

Kriteria penerimaan M1 tetap mencakup:

- Package, settings, pool, import smoke test, dan liveness berjalan tanpa Oracle atau side effect import.
- Generator dan test vector hash benar. Raw key tidak menjadi bind Oracle atau muncul pada output, log, exception, source, contoh, dan template credential.
- Key ACTIVE valid diterima; key kosong, salah, PENDING, EXPIRED, atau REVOKED ditolak 401, termasuk tepat pada expiry. Key terminal tidak diaktifkan kembali.
- Kegagalan koneksi, pool, atau query auth menghasilkan 503 sebelum callback bisnis, tanpa cache fallback atau auth bypass.
- Bootstrap bersamaan hanya menghasilkan satu state kanonis dan tidak mengaktifkan key sebelum distribusi dikonfirmasi.
- Kegagalan secure store atau permission tidak aman menghentikan bootstrap. Cleanup/retry tidak menghilangkan material kanonis.
- Storage/read dan privilege Oracle memiliki bukti berizin yang terpisah dari tes fake/source-contract. Preflight harus diulang untuk setiap target; keberhasilan target saat ini tidak berlaku otomatis untuk target lain.

M1 tidak mensyaratkan pembangunan ulang CRUD atau seluruh deployment Docker/TLS sebagai pekerjaan autentikasi. Requirement tersebut tetap menjadi gate project. Keberhasilan M1 juga tidak menjanjikan rotasi atau kesiapan production.

### M2 Rotation Engine/manual/emergency

Requirement: FR-004, FR-002, FR-003, FR-009, FR-011.

Engine Python dan jalur operator terotorisasi menangani prepare, readiness, aktivasi, revoke, serta rekonsiliasi. Operasi ini bukan endpoint CRUD atau startup task. Setiap mutasi memakai transaksi SQL biasa dan lock row GLOBAL. Readiness harus cocok dengan candidate ID dan VERSION yang diharapkan; kandidat atau versi stale ditolak, bukan diganti boolean generik. Key dan state berubah atomik. Operation ID membantu rekonsiliasi retry tanpa double activation; hasil commit yang tidak diketahui tidak boleh diikuti retry buta.

Aktivasi A menetapkan due A+7 hari dan expiry asli A+8 hari. Cutover normal B memberi key lama yang masih live status GRACE sampai `min(expiry_asli, B+24 jam)`, tanpa memperpanjang expiry saat terlambat atau mengaktifkan kembali EXPIRED/REVOKED. Operator boleh revoke segera tanpa replacement, dengan risiko outage. Aktivasi darurat memerlukan replacement baru yang sudah dikonfirmasi siap dan mencabut seluruh old live, termasuk GRACE, dalam transaksi yang sama. Tidak ada overlap darurat atau bypass.

Bukti saat ini: tes waktu terkontrol, readiness/race/version, grace/emergency, dan rekonsiliasi offline tersedia. Launcher manual memiliki 102 kasus terisolasi. Setelah setup read-only, satu cutover live tanpa grace yang diizinkan mengaktifkan ID 21, mencabut ID 1, dan mencapai VERSION 6 setelah readiness terkonfirmasi. Pool Oracle baru serta dependency autentikasi menolak key lama dan menerima key baru, tanpa HTTP/API start. Bukti ini belum menutup normal grace, emergency dengan old GRACE, concurrency, rollback, atau unknown commit live; rincian waktu dan batas ada di [acceptance](<ACCEPTANCE.md>).

Kriteria penerimaan M2:

- Tes waktu terkontrol mencakup due/expiry boundary, grace, cutover terlambat melewati expiry, scheduler berhenti, dan penolakan revival.
- Concurrent worker, candidate ID salah, VERSION stale, rollback, retry, dan commit tidak diketahui memiliki bukti rekonsiliasi.
- Kanal aman dan konfirmasi penerimaan mendahului aktivasi. Raw key tidak masuk SQL, source, atau log.
- Revoke segera serta aktivasi emergency replacement siap teruji tanpa overlap, revival, atau auth bypass.
- Bukti model/fake dibedakan dari transaksi dan locking Oracle live opt-in.

### M3 External Automation/distribution/monitoring/recovery

Requirement: FR-004 serta availability, reliability, dan privacy PRD. Seluruh 16 acceptance items tetap berlaku untuk penerimaan akhir.

Scheduler eksternal memicu engine Python, bukan DBMS_SCHEDULER atau routine autentikasi/rotasi Oracle. Due mengikuti A+7 hari, bukan jadwal Senin tetap. Distribusi raw key melalui kanal rahasia dan acknowledgment readiness juga harus otomatis sebelum sistem disebut otomatis end-to-end. Selama distribusi/konfirmasi masih manual, operasi tetap semi-otomatis.

Bukti saat ini terbatas pada jalur tick dan runbook. Scheduler aktual, provider distribusi/ack, alert, restart dengan key aktif, dan recovery production belum terverifikasi.

Kriteria penerimaan M3:

- Pemicu aktual, distribusi/ack, aktivasi, dan hasil/no-op tercatat tersanitasi. Kehadiran script saja bukan bukti automation berjalan.
- No-successor, distribusi gagal, readiness belum ada, expiry dekat, worker down, dan DB failure menghasilkan alert serta escalation. Recovery tidak memperpanjang expiry diam-diam.
- Restart container mempertahankan state. Recovery, retry setelah commit tidak diketahui, dan emergency memiliki runbook serta bukti uji.
- p95 diukur pada beban development yang disepakati terhadap target PRD, bukan dari durasi unit test atau probe koneksi.
- Dokumen API, operasi, dan acceptance mencatat target, waktu, metode, hasil, serta batas tanpa secret. Semua acceptance wajib terpenuhi dan pengguna memberi sign-off; unit/source-contract tidak dilabeli live PASS.

## 3. Dokumen bertahap

[README](<../README.md>) menjadi pintu masuk penggunaan. [Kontrak API](<API.md>) menjelaskan HTTP/OpenAPI, [operasi](<OPERATIONS.md>) menjelaskan distribusi/operator/scheduler/TLS/recovery, dan [acceptance](<ACCEPTANCE.md>) menyimpan bukti serta gate terbuka. Catat keputusan driver, pool, lockfile, privilege, distribusi, dan recovery saat ada keputusan nyata, bukan placeholder kelulusan. Pisahkan hasil ekspor OpenAPI, laporan tes, bundle distribusi, dan material privat dari source.
