# Kontrak HTTP API_LOGISTIK

API memakai opaque Global API Key melalui header `X-API-Key`, bukan JWT. Pembuatan, ekspor, dan rotasi key dilakukan lewat CLI operator, bukan endpoint HTTP. Requirement mengacu pada [PRD](<PRD.md>) bagian 5, 7, 9, dan 15; hasil pengujian aktual ada di [acceptance](<ACCEPTANCE.md>).

## Endpoint

| Method | Path | `X-API-Key` | Hasil sukses |
|---|---|---|---|
| POST | `/api/v1/karyawan` | Wajib | 201, CREATE |
| GET | `/api/v1/karyawan/{id}` | Wajib | 200, READ |
| PUT | `/api/v1/karyawan/{id}` | Wajib | 200, UPDATE |
| DELETE | `/api/v1/karyawan/{id}` | Wajib | 200, DELETE; bukan 204 |
| GET | `/api/v1/health/live` | Tidak | 200, proses hidup |

Lima operasi ini memakai tiga path. Tidak ada endpoint list, PATCH, login, atau readiness database. Liveness tidak mengakses Oracle, key, atau secret store. Pool dibuat saat koneksi pertama dibutuhkan, sehingga liveness tetap dapat merespons 200 ketika Oracle tidak tersedia. Status ini bukan tanda CRUD siap.

Development/test menyediakan `/docs` dan `/openapi.json`; production menonaktifkannya secara default. `DOCS_ENABLED` dapat mengubah pilihan tersebut. Jangan memasukkan key nyata ke Swagger bersama atau jaringan yang tidak dipercaya. Production memerlukan TLS client sesuai [panduan operasi](<OPERATIONS.md>).

## Input karyawan

POST mewajibkan seluruh field berikut. Contoh ini sintetis, bukan data pegawai nyata atau izin menulis Oracle.

```json
{
  "id_karyawan": "1001",
  "nama": "CONTOH TRAINING",
  "cabang": "TRAINING",
  "no_telp": "0000000000",
  "status": "AKTIF"
}
```

| Field | Bentuk HTTP | Validasi aplikasi |
|---|---|---|
| `id_karyawan` | String pada POST; path pada operasi lain | 1 sampai 5 digit ASCII `[0-9]`, tanpa tanda, spasi, atau desimal |
| `nama` | String wajib | Trim tepi; tidak kosong; maksimal 50 karakter dan 50 byte UTF-8 |
| `cabang` | String wajib | Trim tepi; tidak kosong; maksimal 30 karakter dan 30 byte UTF-8 |
| `no_telp` | String wajib | 1 sampai 20 digit ASCII; tidak di-trim; nol awal dipertahankan |
| `status` | String wajib | Trim tepi; tidak kosong; maksimal 10 karakter dan 10 byte UTF-8; tanpa enum tambahan |

PUT mengganti penuh `nama`, `cabang`, `no_telp`, dan `status`. Semua field wajib; ID hanya berada di path dan dilarang di body PUT. POST/PUT menolak field tambahan dan angka JSON sebagai pengganti string. GET/DELETE tidak memerlukan body.

Python menyaring bentuk request dan ukuran byte UTF-8 agar sesuai target Oracle AL32UTF8. Function `F_CRUD_KARYAWAN_LOGISTIK` tetap memvalidasi bisnis, termasuk field wajib, batas kolom BYTE, digit telepon, duplikat, serta keberadaan data. Validasi aplikasi tidak menggantikan function atau constraint tabel.

ID string dikonversi ke integer untuk bind `P_ID_KARYAWAN IN NUMBER`, dengan batas tabel training `NUMBER(5)`, yaitu 0 sampai 99999. Nilai `"00101"` dan `"101"` menunjuk ID yang sama. Response menormalkan ID menjadi string desimal tanpa nol awal. Target/schema lain tetap memerlukan preflight DBA.

## Response dan error

Envelope aplikasi berisi `success`, `code`, `message`, dan `data`. Sukses CRUD memakai `code="SUCCESS"` dengan objek data yang memuat `id_karyawan`; field lain dapat null sesuai operasi. Kegagalan memakai `data=null`. Gunakan `code`, bukan teks `message`, sebagai identifier untuk logika client.

```json
{
  "success": false,
  "code": "AUTH_001",
  "message": "API Key tidak valid atau sudah kedaluwarsa",
  "data": null
}
```

Response liveness:

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "Proses API berjalan",
  "data": {"status": "alive"}
}
```

| HTTP | Code aplikasi | Arti |
|---|---|---|
| 200/201 | `SUCCESS` | Operasi berhasil |
| 401 | `AUTH_001` | Key hilang, kosong, salah, PENDING, expired, revoked, atau tidak konsisten dengan GLOBAL |
| 404 | `KRY_404` | Karyawan tidak ditemukan |
| 409 | `KRY_001` | ID duplikat |
| 422 | `REQUEST_422` | Bentuk input, path, atau body tidak valid |
| 422 | `KRY_002` sampai `KRY_020` | Error bisnis yang dipetakan aplikasi; makna spesifik mengikuti function |
| 404/405 | `HTTP_404` / `HTTP_405` | Route tidak ada atau method tidak didukung |
| 500 | `INTERNAL_ERROR` | Exception internal atau kontrak JSON/function tidak cocok |
| 503 | `DB_UNAVAILABLE` | Pool, koneksi, atau query autentikasi tidak tersedia; tanpa bypass |
| 503 | `COMMIT_OUTCOME_UNKNOWN` | Hasil commit belum pasti; rekonsiliasi sebelum retry |

Aplikasi tidak menyediakan rate limiter bawaan. Error reverse proxy, TLS, penolakan sebelum ASGI, dan proses mati berada di luar jaminan envelope aplikasi.

## Autentikasi, transaksi, dan log

Python menghitung SHA-256 lalu memeriksa metadata Oracle: status ACTIVE/GRACE, pointer GLOBAL, dan jendela `ACTIVATES_AT <= now < EXPIRES_AT`. Raw key tidak di-trim, diubah case, atau dikirim ke Oracle. Key tidak valid menghasilkan 401; kegagalan database menghasilkan 503. Tidak ada cache fallback atau auth bypass.

CRUD memanggil function melalui blok PL/SQL dengan bind, lalu membaca CLOB JSON. Jangan memanggil function DML melalui `SELECT function(...) FROM DUAL`. Python memvalidasi hasil sebelum commit; error bisnis, parsing, atau operasi memicu rollback. Function tidak melakukan commit/rollback internal.

Write di-commit sebelum response HTTP sukses. Timeout atau response gagal setelah commit tidak membuktikan mutasi gagal. Jangan mengulang CREATE/UPDATE/DELETE secara buta, terutama ketika menerima `COMMIT_OUTCOME_UNKNOWN`.

Server membuat `X-Request-ID` untuk setiap request tanpa mempercayai nilai client. Gunakan ID response untuk korelasi. Log JSON hanya memuat metadata yang diizinkan, bukan header, body, query string, credential, atau exception mentah. Access log Uvicorn dimatikan; debug log driver/proxy juga tidak boleh membocorkan key.

## Ekspor OpenAPI offline

[Exporter](<../scripts/export_openapi.py>) memakai package terinstal, tanpa `PYTHONPATH` atau penyisipan source path. Untuk environment WSL2/Docker, ikuti [panduan operasi](<OPERATIONS.md>) dan [README](<../README.md>); jangan memakai interpreter virtualenv Windows sebagai runtime Linux.

Argumen output opsional. Default relatif terhadap working directory adalah [OpenAPI JSON](<openapi.json>). Exporter memanggil `app.openapi()` tanpa menjalankan server, lifespan, atau acquire pool. Settings memakai konstanta test melalui `model_construct`, bukan `load_settings`, sehingga tidak membaca file runtime atau credential host. Pola ini khusus ekspor offline, bukan konfigurasi runtime.

Schema adalah snapshot source saat ekspor, bukan bukti deployment. Router bisnis mendeklarasikan `ErrorResponse` untuk 400/401/404/405/409/422/500/503, termasuk envelope `REQUEST_422`, bukan schema default HTTPValidationError. Liveness memakai `HealthResponse` dengan `data.status="alive"`.

Bootstrap key dan 24 pemeriksaan HTTP CRUD live pada fixture berizin sudah dicatat di [acceptance](<ACCEPTANCE.md>). Bukti tersebut tidak menutup gate rotasi, outage, concurrency, atau production.

## Referensi

- [FastAPI OpenAPI](<https://fastapi.tiangolo.com/how-to/extending-openapi/>)
- [Konfigurasi FastAPI](<https://fastapi.tiangolo.com/reference/fastapi/>)
- [Pydantic 2.14.1 model_construct](<https://github.com/pydantic/pydantic/blob/v2.14.1/docs/concepts/models.md>)
