# API_LOGISTIK: Product Requirements Document (PRD)
## REST API Integration: FastAPI, Oracle Database & Docker

**Versi:** 1.2, implementasi Global API Key Python dan source bisnis fresh-only  
**Tanggal:** 26 Oktober 2026  
**Status:** Source implementasi tersedia; acceptance Oracle tulis dan production belum selesai  
**Environment awal:** Development / Training  
**Target Python:** Rilis stabil terbaru, diverifikasi dan dikunci sebelum setup implementasi.  
**Target database:** Oracle Database 19c Enterprise Edition.

---

## 1. Project Overview

### 1.1 Background

Project ini bertujuan membangun REST API menggunakan FastAPI sebagai penghubung antara client application dan Oracle Database.

Business logic, validasi data bisnis, dan CRUD dijalankan menggunakan Oracle PL/SQL Function. FastAPI menerima request, menjalankan autentikasi Global API Key di Python, memanggil function CRUD Oracle, dan mengembalikan JSON. Generasi, hashing, validasi, serta rotasi key seluruhnya di Python; Oracle hanya menyimpan metadata/hash dan menyediakan transaksi SQL biasa untuk autentikasi.

Aplikasi FastAPI dijalankan di dalam Docker Container untuk mempermudah deployment dan pengelolaan environment.

Pada tahap development, sistem menggunakan tabel `KARYAWAN` sebagai data training.

### 1.2 Objectives

1. Membangun REST API yang terintegrasi dengan Oracle Database.
2. Mengimplementasikan CRUD melalui Oracle Function.
3. Mengamankan seluruh endpoint bisnis menggunakan API Key.
4. Mengimplementasikan rotasi Global API Key di Python setiap 7 hari dari aktivasi aktual, dengan konfirmasi kesiapan distribusi.
5. Menjalankan FastAPI menggunakan Docker.
6. Menyediakan standardisasi response JSON, error handling, dan logging.
7. Menyiapkan arsitektur yang dapat dikembangkan untuk integrasi database production.

## 2. Scope

### 2.1 In Scope — MVP

- FastAPI REST API.
- Integrasi Oracle Database menggunakan Python driver.
- CRUD terhadap tabel training `KARYAWAN`.
- Oracle Function untuk business logic dan validasi.
- API Key authentication melalui request header.
- Penyimpanan metadata dan hash API Key di Oracle.
- Rotasi Global API Key oleh Python; pemicu manual pada M2 dan scheduler eksternal pada M3, tanpa job Oracle.
- Docker deployment.
- Swagger/OpenAPI untuk testing development.
- Logging, error handling, dan pengujian API.

### 2.2 Out of Scope — MVP

- Integrasi langsung ke tabel production operasional.
- Aplikasi frontend khusus.
- Login pengguna berbasis username/password.
- JWT dan OAuth2.
- Migrasi procedure atau function dari project lama.
- Operasi massal/bulk CRUD.
- Sistem manajemen hak akses pengguna yang kompleks.

## 3. System Architecture

```text
CLIENT APPLICATION
       |
       | HTTPS Request
       | X-API-Key
       v
FASTAPI (DOCKER)
       |
       | Python: generate/hash/validate/rotate Global API Key
       | Bind SQL metadata + call business function
       v
ORACLE DATABASE 19c EE
       +-- F_CRUD_KARYAWAN_LOGISTIK -> KARYAWAN (TRAINING)
       +-- API_KEY_AUTH (hash + metadata)
       +-- API_KEY_ROTATION_STATE (GLOBAL singleton + row lock)
```

**Prinsip arsitektur:** FastAPI tidak menjalankan query CRUD secara langsung. Semua operasi terhadap data bisnis dijalankan melalui Oracle Function.

## 4. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-001 | API menerima request melalui HTTP REST | Must |
| FR-002 | Semua endpoint bisnis wajib menggunakan API Key | Must |
| FR-003 | Python memvalidasi SHA-256 key terhadap metadata Oracle; invalid 401, kegagalan database 503, fail-closed | Must |
| FR-004 | Python merotasi Global API Key 7 hari dari aktivasi aktual; readiness terkonfirmasi, grace maksimal 24 jam tanpa memperpanjang expiry | Must |
| FR-005 | API memanggil Oracle Function untuk operasi CRUD | Must |
| FR-006 | Mendukung CREATE, READ, UPDATE, DELETE | Must |
| FR-007 | Business validation berada pada Oracle Function | Must |
| FR-008 | Response menggunakan format JSON konsisten | Must |
| FR-009 | Menyediakan error handling dan HTTP status yang sesuai | Must |
| FR-010 | Aplikasi dijalankan menggunakan Docker | Must |
| FR-011 | Menyediakan logging dan request ID | Must |
| FR-012 | Menyediakan dokumentasi API untuk development | Should |

## 5. API Specification

Base path: `/api/v1`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/karyawan` | Menambahkan data karyawan |
| GET | `/karyawan/{id}` | Mencari data berdasarkan ID |
| PUT | `/karyawan/{id}` | Memperbarui data karyawan |
| DELETE | `/karyawan/{id}` | Menghapus data karyawan |
| GET | `/health/live` | Memeriksa proses API berjalan |

Empat endpoint CRUD menggunakan satu Oracle Function dengan parameter mode berbeda. Endpoint health check tidak memproses data bisnis.

### 5.1 Contoh CREATE Request

**Endpoint:** `POST /api/v1/karyawan`

Header:

```http
X-API-Key: <active_api_key>
Content-Type: application/json
```

Request body:

```json
{
  "id_karyawan": "1001",
  "nama": "HAZZA",
  "cabang": "JAKARTA",
  "no_telp": "081234567890",
  "status": "AKTIF"
}
```

Contoh response sukses:

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Data karyawan berhasil ditambahkan",
  "data": {
    "id_karyawan": "1001"
  }
}
```

### 5.2 Contoh Error Response

```json
{
  "success": false,
  "code": "KRY_001",
  "message": "ID Karyawan sudah terdaftar",
  "data": null
}
```

Kode error digunakan untuk identifikasi teknis. Client dapat menampilkan `message` saja kepada pengguna.

### 5.3 HTTP Response Standards

| HTTP Status | Penggunaan |
|---|---|
| 200 | READ, UPDATE, atau DELETE berhasil |
| 201 | CREATE berhasil |
| 400 | Request tidak valid secara umum |
| 401 | API Key tidak valid, kosong, atau expired |
| 404 | Data karyawan tidak ditemukan |
| 409 | Konflik data, misalnya ID duplikat |
| 422 | Input tidak memenuhi aturan validasi |
| 429 | Request melebihi rate limit jika fitur diaktifkan |
| 500 | Internal server error |
| 503 | Koneksi atau layanan database tidak tersedia |

## 6. Oracle Database Requirements

### 6.1 Development Table

**Table:** `KARYAWAN`

| Column | Data Type Rencana | Description |
|---|---|---|
| ID_KARYAWAN | NUMBER(5) | Primary Key dan NOT NULL |
| NAMA | VARCHAR2(50 BYTE) | Nama karyawan |
| CABANG | VARCHAR2(30 BYTE) | Lokasi cabang |
| NO_TELP | VARCHAR2(20 BYTE) | Nomor telepon |
| STATUS | VARCHAR2(10 BYTE) | Status karyawan, tanpa enum tambahan |

Ini target fresh schema sesuai registry dan [source tabel](<../database/schema/T_KARYAWAN.sql>) yang disetujui pengguna pada 26 Oktober 2026. Metadata live terakhir belum menemukan tabel tersebut; tabel existing tidak boleh diubah otomatis. Transport ID API berupa string digit ASCII, bind function berupa NUMBER, dan response dinormalisasi tanpa nol depan. `NO_TELP` tetap teks agar nol depan tidak hilang. Charset target byte-validation adalah AL32UTF8, terkonfirmasi pada koneksi read-only.

### 6.2 CRUD Function

Nama function yang diusulkan:

`F_CRUD_KARYAWAN_LOGISTIK`

Input:

- `P_MODE` — CREATE, READ, UPDATE, DELETE.
- `P_ID_KARYAWAN`.
- `P_NAMA`.
- `P_CABANG`.
- `P_NO_TELP`.
- `P_STATUS`.

Output berupa JSON terstruktur yang memuat status, kode hasil, pesan, dan data bila diperlukan.

Untuk READ, parameter selain ID boleh kosong. Untuk DELETE, cukup menggunakan ID. Untuk CREATE dan UPDATE, field wajib divalidasi sesuai aturan bisnis.

### 6.3 Transaction Management

- Function CRUD menjalankan perubahan data tanpa melakukan `COMMIT` internal.
- FastAPI mengontrol `COMMIT` setelah operasi berhasil.
- Jika proses gagal, FastAPI menjalankan `ROLLBACK`.
- Function DML dipanggil melalui konteks PL/SQL, bukan menggunakan `SELECT function(...) FROM DUAL`.
- Akses database menggunakan bind parameters dan database user dengan privilege terbatas.

## 7. API Key Authentication

### 7.1 Authentication Method

Sistem menggunakan API Key biasa (*opaque API key*), bukan JWT.

API Key dikirim melalui HTTP header:

```http
X-API-Key: <api_key>
```

Setiap request CRUD harus melewati autentikasi sebelum memanggil function bisnis.

### 7.2 Global key dan lifecycle Python

Satu scope `GLOBAL` dipakai bersama seluruh client, bukan key per client. Python menghasilkan raw key melalui `secrets.token_urlsafe(32)` dan menghitung SHA-256 UTF-8 melalui `hashlib.sha256`; Oracle menyimpan digest heksadesimal lowercase 64 karakter, bukan raw key. Jangan trim atau ubah case raw key. Raw key tidak masuk source, log, query output, atau endpoint CRUD.

- Status: `PENDING`, `ACTIVE`, `GRACE`, `EXPIRED`, `REVOKED`. PENDING tidak dapat mengautentikasi; EXPIRED/REVOKED tidak boleh dihidupkan kembali.
- Aktivasi aktual pada A menetapkan due rotasi A+7 hari dan expiry asli A+8 hari. Ini menggantikan jadwal Senin/jam tetap lama.
- Pada rotasi normal pada B, key lama yang masih live menjadi GRACE dengan expiry `min(expiry_asli, B+24 jam)`. Keterlambatan tidak memperpanjang umur key. Key yang sudah expired tidak diberi grace.
- Python memeriksa status, pointer state, dan jendela waktu pada setiap autentikasi: `ACTIVATES_AT <= now < EXPIRES_AT`. Hanya ACTIVE/GRACE yang konsisten dengan state dan masih berlaku diterima. Key kosong, salah, pending, expired, atau revoked menghasilkan 401; kegagalan database menghasilkan 503 tanpa bypass.
- Seluruh generasi, hashing, validasi, dan keputusan rotasi berada di Python. Tidak ada dependensi `DBMS_CRYPTO`, `STANDARD_HASH`, `DBMS_SCHEDULER`, function/procedure autentikasi Oracle, atau job Oracle.

### 7.3 Storage kanonis

Gunakan kembali nama `API_KEY_AUTH`; jangan membuat tabel key alternatif. Definisi fresh-only:

| Kolom | Kontrak |
|---|---|
| `KEY_ID` | `NUMBER GENERATED ALWAYS AS IDENTITY` |
| `KEY_HASH` | SHA-256 lowerhex64, unik |
| `STATUS` | PENDING, ACTIVE, GRACE, EXPIRED, REVOKED |
| `CREATED_AT` | TIMESTAMP WITH TIME ZONE, waktu pembuatan |
| `ACTIVATES_AT` | TIMESTAMP WITH TIME ZONE, jadwal/aktivasi; aktivasi final memakai A aktual |
| `EXPIRES_AT` | TIMESTAMP WITH TIME ZONE, batas eksklusif |

Tabel baru yang disetujui `API_KEY_ROTATION_STATE` menyimpan satu row `SCOPE_ID='GLOBAL'`: `ACTIVE_KEY_ID`, `GRACE_KEY_ID`, `PENDING_KEY_ID`, `NEXT_ROTATION_AT`, `PENDING_READY_AT`, `VERSION`, `LAST_OPERATION_ID`, `LAST_OPERATION_AT`. Pointer mengacu pada key yang sesuai status; waktu memakai TSTZ. Row ini adalah titik serialisasi transaksi, bukan penyimpanan secret.

Skema legacy memakai `CLIENT_ID`, `ACTIVE_AT`, `EXPIRED_AT`, dan opsional `LAST_USED_AT`. Definisi fresh tidak boleh diterapkan di atas tabel existing. Patch status hanya menangani constraint dikenal `CK_API_KEY_AUTH_STATUS`; patch itu tidak me-rename kolom lama atau melakukan migrasi penuh. Ketidakcocokan legacy memerlukan keputusan/migrasi tersendiri sebelum runtime kanonis dipakai.

### 7.4 Distribusi, readiness, dan transaksi

Python menyiapkan kandidat PENDING; operator menyalurkan raw key melalui kanal rahasia terpisah dan mengonfirmasi kesiapan sebelum aktivasi. Kanal distribusi/ack seluruh client masih harus dipilih. Scheduler tetap semi-otomatis sampai distribusi dan konfirmasi juga otomatis; pemicu waktu saja bukan rotasi otomatis end-to-end.

Setiap prepare, konfirmasi readiness, aktivasi, dan revoke mengunci row GLOBAL menggunakan `SELECT ... FOR UPDATE`, memeriksa candidate ID tepat serta `VERSION` yang diharapkan, dan memperbarui key/state dalam satu transaksi SQL biasa milik Python. Konfirmasi readiness harus terikat kandidat dan versi yang sama; kandidat diganti atau versi stale berarti konfirmasi ulang, bukan aktivasi berdasarkan boolean generik. Gunakan operation ID untuk rekonsiliasi retry; rollback saat gagal, dan jangan mengulang mutasi secara buta ketika hasil commit tidak diketahui.

Operator dapat mencabut key kompromi segera, meskipun replacement belum siap, dengan risiko outage yang dinyatakan. Aktivasi darurat memerlukan replacement baru yang telah dikonfirmasi siap. Dalam satu transaksi, Python mencabut seluruh key lama yang live, termasuk GRACE, lalu mengaktifkan replacement dan memperbarui GLOBAL. Tidak ada overlap darurat, revival key lama, atau bypass autentikasi. Jika distribusi/rotasi gagal, expiry tetap berlaku; monitoring dan pemulihan tidak boleh memperpanjang key secara diam-diam.

## 8. Docker Requirements

FastAPI dijalankan sebagai Docker Container.

Struktur target pembangunan ulang yang disetujui:

```text
API_logistik/
├── src/
│   └── api_logistik/
│       ├── main.py
│       ├── config.py
│       ├── logging_config.py
│       ├── errors.py
│       ├── api/
│       ├── schemas/
│       ├── db/
│       └── middleware/
├── database/
│   ├── prechecks/
│   ├── schema/
│   ├── functions/
│   ├── procedures/
│   └── jobs/
├── tests/
│   ├── unit/
│   ├── api/
│   ├── contracts/
│   └── integration/
├── docs/
├── scripts/
├── pyproject.toml
├── Dockerfile
├── compose.yaml
├── .env.example
└── README.md
```

Diagram di atas adalah struktur target, bukan daftar implementasi yang sudah selesai. Detail tanggung jawab modul berada di [ARCHITECTURE.md](<ARCHITECTURE.md>), dan tahapan pengerjaan di [IMPLEMENTATION_PLAN.md](<IMPLEMENTATION_PLAN.md>). Setiap package Python menggunakan `__init__.py` saat mulai diimplementasikan. Dependency dikelola melalui `pyproject.toml` dan satu lockfile dari tool yang disepakati, bukan beberapa daftar versi yang dirawat manual.

Konfigurasi koneksi Oracle dibaca dari environment variables atau Docker Secrets, bukan hardcoded dalam image.

Persyaratan Docker:

- Image menjalankan FastAPI tanpa hak root.
- Database Oracle berada di luar container aplikasi.
- Connection pooling diaktifkan dan ukurannya dapat dikonfigurasi.
- Container memiliki health check.
- Log dikirim ke standard output/error.
- Secret tidak disimpan dalam Dockerfile atau repository.
- Versi dependency ditetapkan dan dipindai sebelum deployment.

## 9. Validation Requirements

Oracle Function wajib melakukan validasi bisnis berikut:

| Validation | CREATE | READ | UPDATE | DELETE |
|---|---|---|---|---|
| ID wajib diisi | Ya | Ya | Ya | Ya |
| ID hanya digit | Ya | Ya | Ya | Ya |
| Nama wajib diisi | Ya | Tidak | Ya | Tidak |
| Cabang wajib diisi | Ya | Tidak | Ya | Tidak |
| No. telepon wajib diisi | Ya | Tidak | Ya | Tidak |
| No. telepon hanya digit | Ya | Tidak | Ya | Tidak |
| Status wajib diisi | Ya | Tidak | Ya | Tidak |
| Cek ID duplikat | Ya | Tidak | Tidak | Tidak |
| Cek ID sudah ada | Tidak | Ya | Ya | Ya |

Validasi panjang kolom dan pilihan status disesuaikan dengan skema database. Constraint database tetap menjadi pelindung terakhir terhadap data tidak valid.

## 10. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Security | HTTPS/TLS wajib untuk koneksi client |
| Authentication | Seluruh endpoint CRUD terlindungi API Key |
| Availability | Kegagalan rotasi key harus terdeteksi dan dilaporkan |
| Performance | Target awal p95 response time di bawah 1 detik pada beban development yang disepakati |
| Reliability | Tidak terjadi partial commit pada operasi gagal |
| Logging | Request ID, endpoint, status HTTP, durasi, dan kategori error |
| Privacy | API Key, password, serta data sensitif tidak dicatat secara mentah |
| Scalability | Connection pool dan jumlah worker dapat dikonfigurasi |
| Deployment | Docker image dapat dijalankan ulang tanpa mengubah data bisnis |
| Compatibility | Driver Oracle harus sesuai dengan versi Oracle Database target |

Target performance merupakan target awal yang perlu diuji melalui benchmarking, bukan jaminan sebelum pengujian.

## 11. Acceptance Criteria

Project MVP dianggap selesai apabila:

- [ ] FastAPI berjalan stabil melalui Docker.
- [ ] FastAPI berhasil terhubung ke Oracle Development Database.
- [ ] CREATE berhasil menambahkan data melalui Oracle Function.
- [ ] READ berhasil mengambil data berdasarkan ID.
- [ ] UPDATE berhasil memperbarui data.
- [ ] DELETE berhasil menghapus data training.
- [ ] Business validation gagal dengan error yang sesuai.
- [ ] Python menolak API Key kosong/salah/pending dengan 401; kegagalan database menghasilkan 503, tanpa memanggil CRUD.
- [ ] Python menolak key expired/revoked tanpa revival, termasuk saat scheduler terlambat atau berhenti.
- [ ] Rotasi Python A+7 hari, expiry A+8 hari, grace min(expiry asli, B+24 jam), konkurensi/retry dan automation eksternal diuji dengan waktu terkontrol; scheduler saja tetap semi-otomatis.
- [ ] Client menerima key melalui kanal aman dan readiness kandidat ID+VERSION dikonfirmasi di bawah lock GLOBAL sebelum aktivasi.
- [ ] Cutover normal membatasi grace tanpa extension; revoke operator segera dan aktivasi darurat replacement siap mencabut semua key live lama termasuk grace secara atomik.
- [ ] Rollback berhasil jika operasi database gagal.
- [ ] Container dapat restart tanpa kehilangan status API Key.
- [ ] Swagger dan dokumentasi endpoint tersedia di development.
- [ ] Kredensial dan API Key tidak muncul di log maupun repository.

## 12. Development Milestones

| Milestone | Deliverable dan batas selesai |
|---|---|
| M1 Auth MVP | Fondasi minimum app/config/pool, generate/hash/storage, bootstrap aman, reusable dependency X-API-Key, serta tes auth fail-closed. Tidak membangun ulang CRUD atau mewajibkan Docker/TLS selesai pada milestone auth ini. |
| M2 Rotation Engine/manual/emergency | Engine Python, readiness kandidat+VERSION di bawah lock GLOBAL, rotasi manual normal/darurat, revoke segera, expiry/grace serta retry teruji. |
| M3 External Automation/distribution/monitoring/recovery | Scheduler eksternal, distribusi/konfirmasi, alert, rekonsiliasi dan pemulihan; tetap semi-otomatis sampai distribusi otomatis terbukti. |

Tiga milestone ini membagi subsystem Global API Key. Requirement CRUD, Docker, TLS, dan penerimaan project keseluruhan tetap berlaku, tetapi tidak disamakan dengan gate M1 autentikasi. Paket source SQL saat ini bukan penyelesaian milestone Python mana pun.

## 13. Risks and Dependencies

**Risiko utama:**

- Rotasi API Key menyebabkan request gagal apabila key baru belum diterima client.
- Oracle Function melakukan commit internal sehingga rollback API tidak efektif.
- Versi driver tidak kompatibel dengan Oracle Database.
- Database user mempunyai privilege terlalu luas.
- Kegagalan koneksi Oracle membuat endpoint tidak tersedia.
- Pemanggilan berulang CREATE/DELETE akibat retry menyebabkan perubahan tidak diinginkan.

Mitigasi meliputi pengujian staging, transactional control, pemantauan rotasi, secret management, dan mekanisme idempotency untuk operasi yang memerlukan proteksi retry.

## 14. Open Decisions

Sebelum implementasi final, perlu konfirmasi:

1. Target versi dan edisi sudah ditetapkan: Oracle Database 19c Enterprise Edition. Detail patch/RU, schema/PDB, dan platform target tetap perlu diverifikasi bersama DBA.
2. Kanal distribusi Global key, daftar penerima, dan bukti konfirmasi readiness seluruh client.
3. Frekuensi tick, host scheduler eksternal, otorisasi operator, dan monitoring M3; due tetap A+7 hari.
4. Runbook migrasi legacy ke kolom kanonis bila hasil preflight tidak cocok.
5. Detail operational recovery, rekonsiliasi commit tidak diketahui, dan penanggung jawab escalation; grace/expiry mengikuti bagian 7, bukan keputusan terbuka.
6. Apakah production akan menggunakan tabel lain dengan struktur dan aturan CRUD yang berbeda.
7. Apakah akses API dibatasi hanya pada jaringan internal/VPN.

---

**Target MVP:** sebuah REST API dalam Docker yang menerima request terautentikasi, menjalankan operasi CRUD melalui Oracle Function terhadap tabel training `KARYAWAN`, menggunakan Global API Key yang dikelola dan dirotasi di Python setiap 7 hari dari aktivasi aktual, serta menghasilkan response JSON yang konsisten dan dapat diaudit.

## 15. Registry Objek SQL untuk Pembangunan Ulang

### 15.1 Tujuan dan batas reset

Pemilik project meminta pembangunan ulang dari nol pada 26 Oktober 2026. Reset hanya menghapus file implementasi lokal; PRD ini tetap menjadi acuan requirement dan nama objek SQL. Reset file tidak menghapus, menonaktifkan, atau mengubah objek, data, maupun job pada Oracle. Reset ini juga tidak menghentikan container Docker yang sudah berjalan.

Daftar berikut berasal dari definisi SQL dan catatan skema pada implementasi sebelum reset. Daftar ini bukan hasil pemeriksaan database live. Sebelum menjalankan DDL, pengembang bersama DBA harus memverifikasi schema/PDB, keberadaan objek, signature, constraint, dan status kompilasinya.

### 15.2 Aturan penamaan tetap

1. Gunakan kembali nama function, procedure, tabel, job, dan constraint dalam registry ini. Jangan membuat objek alternatif dengan suffix versi, nama lain, atau package pembungkus hanya untuk menghindari perubahan objek yang sudah ada.
2. Function CRUD tetap satu objek dengan empat mode. Jangan membuat function atau procedure standalone baru untuk masing-masing operasi CREATE, READ, UPDATE, dan DELETE.
3. Runtime hanya memanggil `F_CRUD_KARYAWAN_LOGISTIK` untuk bisnis. Autentikasi dan lifecycle key memakai Python serta bind SQL biasa terhadap dua tabel key. Validator, procedure key, dan job lama hanya registry historis: tidak dipanggil, dibuat ulang, dieksekusi, atau di-drop oleh pekerjaan ini.
4. Perbaiki implementasi di dalam objek yang sama. Setiap perubahan signature, penambahan objek schema, atau pergantian nama memerlukan persetujuan pemilik project dan pembaruan PRD terlebih dahulu, termasuk tabel audit, index, sequence, trigger, package, atau job tambahan.
5. Periksa objek yang sudah ada sebelum deployment. Jangan menjalankan ulang CREATE TABLE, ADD CONSTRAINT, atau CREATE JOB jika objek tersebut sudah terpasang. Jangan memakai DROP, TRUNCATE, penghapusan data, atau regenerasi key sebagai bagian otomatis dari setup ulang.
6. SQL source boleh disiapkan offline sekarang, tanpa menunggu live privilege check. Pengguna menerapkan SQL sendiri setelah preflight manual atas target/privilege dan persetujuan perubahan. Menyiapkan source tidak mengklaim preflight, kompilasi, atau deployment live lulus.
7. Bila requirement tidak dapat dipenuhi dengan objek yang tercatat, dokumentasikan kebutuhan dan minta persetujuan sebelum menambahkan objek. Jangan menghilangkan requirement untuk mempertahankan jumlah objek.

### 15.3 Function standalone yang dipertahankan

| Nama objek | Peran | Kontrak |
|---|---|---|
| `F_CRUD_KARYAWAN_LOGISTIK` | Validasi bisnis dan CRUD tabel `KARYAWAN` | Menerima mode dan data karyawan; mengembalikan CLOB berisi JSON `success`, `code`, `message`, dan `data`. |
| `F_VALIDATE_API_KEY_LOGISTIK` | Historis, tidak dipakai desain Global | Signature lama disimpan sebagai catatan, bukan dependency runtime atau target SQL baru. |

Signature yang digunakan sebelum reset dan menjadi acuan pembangunan ulang:

```sql
FUNCTION F_CRUD_KARYAWAN_LOGISTIK (
    P_MODE IN VARCHAR2,
    P_ID_KARYAWAN IN NUMBER,
    P_NAMA IN VARCHAR2 DEFAULT NULL,
    P_CABANG IN VARCHAR2 DEFAULT NULL,
    P_NO_TELP IN VARCHAR2 DEFAULT NULL,
    P_STATUS IN VARCHAR2 DEFAULT NULL
) RETURN CLOB;

FUNCTION F_VALIDATE_API_KEY_LOGISTIK (
    P_API_KEY IN VARCHAR2
) RETURN NUMBER;
```

- `P_MODE` hanya menerima `CREATE`, `READ`, `UPDATE`, atau `DELETE`. READ dan DELETE cukup membawa ID; CREATE dan UPDATE mengikuti validasi pada bagian 9.
- Function CRUD tidak melakukan COMMIT atau ROLLBACK internal. Pemanggil API mengelola transaksi sesuai bagian 6.3 dan menggunakan bind parameter dalam blok PL/SQL.
- Signature validator di atas hanya historis. Validasi aktif dilakukan Python sesuai bagian 7, menerima ACTIVE/GRACE yang masih berlaku dan sesuai state GLOBAL.

### 15.4 Procedure administratif historis, tidak digunakan

| Nama objek | Status |
|---|---|
| `P_PREPARE_API_KEY` | Signature lama dipertahankan sebagai catatan; jangan compile, panggil, atau drop dalam scope ini. |
| `P_ROTATE_API_KEYS` | Historis, bukan engine rotasi Global. |

```sql
PROCEDURE P_PREPARE_API_KEY (
    P_CLIENT_ID IN VARCHAR2,
    P_ACTIVE_AT IN TIMESTAMP WITH TIME ZONE,
    P_API_KEY IN VARCHAR2
);

PROCEDURE P_ROTATE_API_KEYS;
```

Kontrak ini hanya mendokumentasikan implementasi sebelum reset. Format hex raw key dan transaksi procedure lama bukan kontrak Global baru. Python menghasilkan token URL-safe dan mengelola transaksi lifecycle; tidak mengirim raw key ke procedure Oracle. Seed DML dijalankan pengguna di sesi admin khusus tanpa transaksi lain karena mempunyai COMMIT eksplisit.

### 15.5 Registry tabel dan constraint kanonis

| Jenis | Nama | Catatan |
|---|---|---|
| Tabel bisnis | `KARYAWAN` | Tabel training existing; jangan membuat pengganti. |
| Tabel metadata key reuse | `API_KEY_AUTH` | Definisi kanonis fresh-only pada bagian 7.3. |
| Tabel kontrol baru disetujui | `API_KEY_ROTATION_STATE` | Singleton GLOBAL, pointer key, readiness, versi dan operation metadata pada bagian 7.3. |
| Primary key bisnis | `PK_KARYAWAN` | Pada `KARYAWAN(ID_KARYAWAN)`. |
| Primary key key | `PK_API_KEY_AUTH` | Pada `API_KEY_AUTH(KEY_ID)`. |
| Unique constraint | `UK_API_KEY_AUTH_HASH` | Pada `API_KEY_AUTH(KEY_HASH)`. |
| Check constraint | `CK_API_KEY_AUTH_STATUS` | PENDING, ACTIVE, GRACE, EXPIRED, REVOKED; patch legacy hanya nama constraint ini. |
| Check constraint | `CK_API_KEY_AUTH_WINDOW` | Definisi fresh memakai EXPIRES_AT lebih besar dari ACTIVATES_AT; legacy tidak otomatis dimigrasi. |
| Job historis | `JOB_ROTATE_API_KEYS` | Tidak digunakan, tidak dibuat/dijalankan/di-drop; bukan dependency desain baru. |

Constraint struktural untuk tabel kontrol ditetapkan dalam definisi tabel yang disetujui; tidak menambahkan function, procedure, sequence manual, atau job. Nama dan path kanonis berada hanya pada registry bagian 15/16 ini; dokumen lain merujuknya.

Catatan skema training sebelum reset:

| Kolom `KARYAWAN` | Tipe |
|---|---|
| `ID_KARYAWAN` | `NUMBER(5)`, primary key dan NOT NULL |
| `NAMA` | `VARCHAR2(50 BYTE)` |
| `CABANG` | `VARCHAR2(30 BYTE)` |
| `NO_TELP` | `VARCHAR2(20 BYTE)` |
| `STATUS` | `VARCHAR2(10 BYTE)` |

Tipe ID pada bagian 6.1 masih berupa rencana; bagian 6.1 sendiri menyerahkan tipe final kepada tabel training yang tersedia. Catatan NUMBER(5) di atas mendokumentasikan skema sebelumnya, bukan izin mengubah tipe tabel existing tanpa verifikasi DBA. Telepon tetap teks agar nol awal tidak hilang.

Skema lama `API_KEY_AUTH` mempunyai CLIENT_ID, ACTIVE_AT, EXPIRED_AT dan LAST_USED_AT. Catatan itu bukan kontrak fresh dan bukan bukti keadaan live. Preflight manual harus membedakan legacy dari kanonis; patch status tidak menyelesaikan perbedaan tersebut.

Jadwal lama Senin 00:05 Asia/Jakarta telah digantikan oleh A+7 hari dari aktivasi aktual. Registry historis tidak menyatakan job terpasang, dihentikan, atau aman; pengguna/DBA perlu menilai objek lama agar tidak mengganggu deployment baru. Jangan menjalankannya sebagai bagian setup.

### 15.6 Helper lokal dan objek bawaan Oracle

`MAKE_RESPONSE` dan `MAKE_KARYAWAN_DATA` adalah function lokal di dalam `F_CRUD_KARYAWAN_LOGISTIK`, bukan objek standalone. Pertahankan sebagai helper lokal bila diperlukan; jangan membuat dua function schema tambahan untuk nama tersebut.

JSON bisnis dapat memakai fasilitas Oracle 19c yang sesuai kontrak CRUD. Fasilitas hashing, scheduler, dan autentikasi Oracle lama tidak menjadi dependency lifecycle Global; tidak ada prosedur/function/job key baru.

### 15.7 Syarat sebelum implementasi baru dinyatakan selesai

- Pengembang memeriksa dan mencatat objek existing tanpa mengambil atau mencetak raw key maupun data karyawan ke dokumen.
- Pemilik project menyetujui perubahan registry sebelum pengembang menambahkan objek di luar daftar ini.
- Pengembang membuktikan CRUD, validasi, autentikasi, transaksi, rotasi, dan pemulihan terhadap acceptance criteria pada bagian 11 menggunakan fixture dan izin yang sesuai.
- Catatan nama objek ini tidak berarti seluruh objek pernah dideploy atau seluruh acceptance criteria sudah lulus. Pembangunan ulang tidak mewarisi klaim kelulusan implementasi sebelumnya.

## 16. Konvensi Nama File SQL

Pemilik project menyetujui struktur pembangunan ulang dan meminta penanda jenis pada nama file SQL pada 26 Oktober 2026. Konvensi ini mengatur file source, bukan menambahkan atau mengganti nama objek Oracle pada bagian 15.

### 16.1 Prefix dan batas isi

Gunakan pola `<PREFIX>_<NAMA_DESKRIPTIF>.sql`, dengan nama dasar huruf kapital dan pemisah underscore. Prefix yang sudah menjadi bagian nama objek tidak ditambahkan dua kali: `F_CRUD_KARYAWAN_LOGISTIK.sql`, bukan `F_F_CRUD_KARYAWAN_LOGISTIK.sql`.

| Prefix | Jenis file | Isi yang diizinkan |
|---|---|---|
| `F_` | Function | Satu definisi function standalone yang tercatat di registry. Helper lokal tetap di dalam definisi tersebut. |
| `P_` | Procedure | Satu definisi procedure administratif yang tercatat di registry; compile tidak sekaligus memanggilnya. |
| `Q_` | Query | Read-only metadata/grants atau verifikasi storage agregat; tanpa nilai hash/raw key, DML, DDL, provisioning, job, atau perubahan session/database. |
| `D_` | DML seed | MERGE idempotent hanya untuk row GLOBAL yang belum ada, tanpa mint key; COMMIT eksplisit di sesi admin khusus. |
| `T_` | Table | Satu definisi tabel yang sudah tercatat di registry, hanya diterapkan jika tabel belum ada dan deployment disetujui. |
| `C_` | Constraint | Satu perubahan constraint atau nullability pada tabel existing yang sudah tercatat di registry. |
| `J_` | Job | Satu unit pendaftaran atau perubahan scheduler job existing sesuai registry; eksekusinya adalah perubahan database. |

`Q_` bukan penanda untuk semua file SQL. Definisi function, procedure, tabel, constraint, dan scheduler harus memakai prefix sesuai jenisnya. Nomor urutan deployment tidak perlu menjadi prefix tambahan; urutan dan prasyarat ditulis dalam panduan database agar penanda jenis tetap terlihat di awal nama file.

### 16.2 Pemetaan file target

Delapan file source tersedia setelah persetujuan pengguna untuk menyiapkan tabel/function bisnis fresh-only pada 26 Oktober 2026. Dua patch constraint bisnis tetap prospektif dan belum dibuat. Ketersediaan file bukan bukti SQL sudah diterapkan atau dikompilasi di Oracle.

| Path relatif dari root project | Target atau tujuan |
|---|---|
| `database/prechecks/Q_VERIFY_EXISTING_OBJECTS.sql` | Preflight manual read-only: metadata, signature, constraint, grants; tanpa nilai hash atau secret. |
| `database/prechecks/Q_VERIFY_API_KEY_STORAGE.sql` | Verifikasi read-only setelah deployment: skema kanonis, state/pointer, row count, status dan integritas waktu; tanpa nilai hash. |
| `database/schema/T_API_KEY_AUTH.sql` | Fresh-only API_KEY_AUTH kanonis; identity ALWAYS, lowerhex64, lima status dan waktu TSTZ. Bukan migrasi legacy. |
| `database/schema/T_API_KEY_ROTATION_STATE.sql` | Tabel kontrol GLOBAL baru pada bagian 7.3. |
| `database/schema/C_API_KEY_AUTH_STATUS.sql` | Patch kondisional hanya constraint legacy dikenal CK_API_KEY_AUTH_STATUS; tidak rename ACTIVE_AT/EXPIRED_AT, bukan migrasi penuh. |
| `database/seed/D_INIT_API_KEY_ROTATION_STATE.sql` | MERGE hanya row GLOBAL yang hilang; tidak mengubah row existing atau membuat key; COMMIT eksplisit, sesi admin khusus. |
| [T_KARYAWAN.sql](<../database/schema/T_KARYAWAN.sql>) | Fresh-only tabel bisnis sesuai tipe bagian 6.1 dan PK_KARYAWAN; tidak mengubah tabel existing. |
| `database/schema/C_KARYAWAN_ID_NOT_NULL.sql` | Prospektif jika diperlukan pada existing; tidak dibuat atau dijalankan. |
| `database/schema/C_PK_KARYAWAN.sql` | Target bisnis mendatang bila constraint existing belum terpasang. |
| [F_CRUD_KARYAWAN_LOGISTIK.sql](<../database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) | Fresh CREATE FUNCTION, nama/signature tetap, nested helpers saja, tanpa transaksi internal atau penggantian objek existing. |

Enam file storage/precheck/seed ditambah dua source bisnis fresh-only tersedia untuk deployment manual pengguna. Tidak ada target F/P/J untuk autentikasi/rotasi baru; objek lama pada bagian 15.3/15.4/15.5 hanya historis.

### 16.3 Aturan pengembangan dan deployment

- Pengembang memakai pemetaan bagian 16.2 sebagai acuan file SQL. File tambahan memerlukan alasan dan pembaruan rencana; objek Oracle tambahan tetap memerlukan persetujuan sesuai bagian 15.2.
- Setiap file berisi satu unit perubahan yang jelas. File F/P tidak berisi invocation administratif atau pendaftaran scheduler sebagai efek samping.
- Penyiapan SQL offline boleh berjalan sebelum preflight live; pengguna menerapkan SQL sendiri sesudah pemeriksaan target/privilege manual. Jangan mengeksekusi seluruh direktori otomatis atau mengklaim hasil live dari pemeriksaan statis.
- Paket SQL tidak menjalankan deployment, mint key atau scheduler. Runtime/admin Python kini tersedia sebagai implementasi terpisah; SQL key menerima hash melalui bind, bukan raw key. Tes/probe Oracle read-only berizin telah dilakukan, tetapi DDL, provisioning, rotasi dan tes tulis live tetap memerlukan izin target/fixture terpisah.
- Pengembang memeriksa status kompilasi dan hasil query verifikasi sesudah perubahan yang berizin. Precheck yang menemukan perbedaan schema, data tidak valid, atau objek existing yang tidak cocok harus menghentikan deployment sampai DBA memberi keputusan.
- Penamaan file tidak memberi izin untuk membuat ulang tabel, mengganti constraint, atau mengubah job yang sudah terpasang.

## 17. Standar Kerja dan Target Teknologi

Pemilik project menetapkan aturan berikut sebelum penulisan kode pembangunan ulang:

1. Pengembang/agent wajib memuat skill `antislop` sebelum menulis atau mengubah kode, disertai skill turunannya yang relevan dengan pekerjaan. Skill antislop adalah filter kualitas; dokumentasi teknis dan pengujian tetap menjadi dasar implementasi backend.
2. Pengembang/agent wajib memeriksa dokumentasi teknis yang relevan melalui Context7 sebelum setiap unit pekerjaan kode, termasuk FastAPI, Pydantic, driver Oracle, konfigurasi dependency, dan Docker bila terkait. Gunakan dokumentasi yang cocok dengan versi dependency dan target Oracle 19c, bukan menyalin contoh dari versi terbaru yang tidak kompatibel. Catat sumber dan keputusan yang berpengaruh pada rancangan.
3. Bila skill atau Context7 tidak tersedia, pengembang/agent melaporkan keterbatasannya dan meminta arahan sebelum melanjutkan penulisan kode. Jangan mengklaim referensi atau skill sudah dipakai bila belum.
4. Python memakai rilis stabil terbaru yang sudah diterbitkan resmi pada saat setup implementasi, bukan alpha, beta, release candidate, build development, atau pilihan otomatis dari versi yang kebetulan terpasang di mesin.
5. Nomor versi Python dan dependency yang terpilih harus dicatat dan dikunci agar development, CI, serta Docker konsisten. Setelah versi dikunci, pembaruan rilis dilakukan sebagai perubahan terencana dengan pengujian ulang, bukan mengikuti tag latest secara diam-diam.
6. Target database adalah Oracle Database 19c Enterprise Edition. Fitur SQL/PLSQL dan konfigurasi driver harus kompatibel dengan target ini; fitur khusus database yang lebih baru tidak boleh digunakan hanya karena ada pada dokumentasi driver terbaru.
7. Pengembang memverifikasi dukungan Python terbaru pada FastAPI, Pydantic, python-oracledb, dependency transitif, serta OS/arsitektur target. Dukungan tertulis dan tersedianya package bukan bukti koneksi Oracle live sudah berhasil. Pemilihan Thin/Thick tetap mengikuti kebutuhan akun/database dan keputusan arsitektur.
8. Jika rilis stabil Python terbaru belum didukung komponen yang dibutuhkan, pengembang melaporkan konflik dan meminta keputusan pemilik project. Jangan menurunkan versi Python, mengganti database, atau menonaktifkan pemeriksaan kompatibilitas tanpa persetujuan.

Standar kerja publik tercantum pada bagian ini; instruksi agent lokal tidak disertakan dalam repository. Runtime mengunci Python 3.15.2, python-oracledb 26.0.1, uv 0.13.5, FastAPI 0.162.0 dan Pydantic 2.14.1 melalui manifest/pin/lockfile. Source API/CLI, tes dan Docker tersedia. Probe pool TCPS/SELECT/ekspresi JSON CLOB Oracle 19.26 read-only lulus; objek project belum ditemukan pada pemeriksaan terakhir. [Acceptance](<ACCEPTANCE.md>) memisahkan bukti tersebut dari compile function, auth/CRUD/rotasi live dan penerimaan production.
