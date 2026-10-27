# Kontrak HTTP API_LOGISTIK

Acuan requirement: [PRD](<PRD.md>) bagian 5, 7, 9 dan 15. Dokumen ini menjelaskan kontrak source aplikasi, bukan bukti CRUD atau autentikasi Oracle live lulus. API menggunakan opaque Global API Key, bukan JWT. Tidak ada endpoint HTTP untuk membuat, mengekspor, atau merotasi key.

## Endpoint

| Method | Path | Header `X-API-Key` | Hasil sukses |
|---|---|---|---|
| POST | `/api/v1/karyawan` | Wajib | 201, hasil CREATE |
| GET | `/api/v1/karyawan/{id}` | Wajib | 200, hasil READ |
| PUT | `/api/v1/karyawan/{id}` | Wajib | 200, hasil UPDATE |
| DELETE | `/api/v1/karyawan/{id}` | Wajib | 200, hasil DELETE, bukan 204 |
| GET | `/api/v1/health/live` | Tidak | 200, proses hidup |

Tidak ada endpoint list, PATCH, login atau readiness database. Liveness tidak mengakses Oracle, key atau secret store. Karena pool dibuat lazy, liveness dapat tetap 200 ketika Oracle tidak tersedia atau objek bisnis belum dipasang. Ini bukan tanda layanan CRUD siap.

Development/test menyediakan `/docs` dan `/openapi.json`; production menonaktifkannya secara default. `DOCS_ENABLED` dapat mengubah pilihan tersebut secara eksplisit. Jangan memasukkan key nyata pada Swagger bersama atau jaringan yang tidak dipercaya. TLS client wajib di production; lihat [operasi](<OPERATIONS.md>).

## Input karyawan

POST memakai semua field berikut. Contoh ini data sintetis, bukan fixture live atau izin menulis Oracle.

```json
{
  "id_karyawan": "1001",
  "nama": "CONTOH TRAINING",
  "cabang": "TRAINING",
  "no_telp": "0000000000",
  "status": "AKTIF"
}
```

| Field | Bentuk HTTP | Batas aplikasi |
|---|---|---|
| `id_karyawan` | String wajib pada POST, path pada operasi lain | 1 sampai 5 digit ASCII `[0-9]`, tanpa tanda, spasi atau desimal |
| `nama` | String wajib | Trim tepi, 1 sampai 50 karakter |
| `cabang` | String wajib | Trim tepi, 1 sampai 30 karakter |
| `no_telp` | String wajib | 1 sampai 20 digit ASCII, tidak di-trim; nol awal dipertahankan |
| `status` | String wajib | Trim tepi, 1 sampai 10 karakter; nilai bisnis ditentukan function Oracle |

PUT adalah penggantian penuh `nama`, `cabang`, `no_telp`, `status`. Semua wajib; `id_karyawan` hanya di path dan dilarang di body PUT. Field tambahan ditolak pada POST/PUT. Tipe angka JSON tidak diterima sebagai pengganti string. GET/DELETE tidak memerlukan body.

ID di-bind sebagai integer ke `P_ID_KARYAWAN IN NUMBER`; `"00101"` dan `"101"` menunjuk ID numerik yang sama. ID hasil dinormalisasi menjadi string desimal tanpa nol awal. Batas kompatibilitas training adalah `NUMBER(5)`; bentuk aktual tetap perlu preflight DBA. Panjang string API menghitung karakter, sedangkan catatan kolom Oracle memakai BYTE. Validasi ukuran byte, pilihan status, duplikat dan keberadaan data tetap kewenangan `F_CRUD_KARYAWAN_LOGISTIK`.

## Response dan error

Semua hasil aplikasi memakai `success`, `code`, `message`, `data`. Sukses CRUD memakai `code="SUCCESS"` dan objek data dengan `id_karyawan`; field data lainnya dapat null tergantung hasil function. Kegagalan memakai `data=null`. `message` bukan identifier stabil untuk logika client.

```json
{
  "success": false,
  "code": "AUTH_001",
  "message": "API Key tidak valid atau sudah kedaluwarsa",
  "data": null
}
```

Liveness:

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
| 401 | `AUTH_001` | Key hilang, kosong, salah, PENDING, expired, revoked atau tidak konsisten dengan GLOBAL |
| 404 | `KRY_404` | Karyawan tidak ditemukan |
| 409 | `KRY_001` | ID duplikat |
| 422 | `REQUEST_422` | Bentuk input/path/body tidak valid |
| 422 | `KRY_002` sampai `KRY_020` | Error bisnis yang dipetakan aplikasi; makna spesifik mengikuti function existing |
| 404/405 | `HTTP_404` / `HTTP_405` | Route tidak ada / method tidak didukung |
| 500 | `INTERNAL_ERROR` | Exception internal atau kontrak JSON/function tidak cocok |
| 503 | `DB_UNAVAILABLE` | Pool, koneksi atau query autentikasi tidak tersedia; tanpa bypass |
| 503 | `COMMIT_OUTCOME_UNKNOWN` | Hasil commit belum pasti; rekonsiliasi sebelum retry |

Aplikasi tidak menyediakan rate limiter bawaan; 429 bukan fitur yang sudah terbukti. Error reverse proxy, TLS, body yang ditolak sebelum ASGI, atau proses mati berada di luar jaminan envelope aplikasi.

`X-Request-ID` dibuat server untuk setiap request, bukan mempercayai nilai dari client. Gunakan ID hasil untuk korelasi. Log JSON menyimpan metadata request yang aman, bukan header, body, query string, credential atau exception mentah. Access log Uvicorn dimatikan. Jangan menambahkan debug logging driver/proxy yang membocorkan `X-API-Key`.

Autentikasi memeriksa digest SHA-256, status ACTIVE/GRACE, pointer GLOBAL dan `ACTIVATES_AT <= now < EXPIRES_AT`. Raw key tidak di-trim/diubah case dan tidak dikirim ke Oracle. CRUD hanya memanggil function existing lewat blok PL/SQL dengan bind. Hasil write di-commit sebelum HTTP sukses; error bisnis/parsing/operasi memicu rollback. Timeout client setelah commit tidak membuktikan mutasi gagal. Jangan retry CREATE/UPDATE/DELETE secara buta.

## Ekspor OpenAPI offline

Jalankan interpreter environment yang sudah menginstal package `api_logistik`, tanpa `PYTHONPATH` atau penyisipan src path:

```powershell
.venv\Scripts\python.exe -I scripts/export_openapi.py C:\PrivateExports\api-logistik-openapi.json
```

Argumen output opsional, default relatif working directory adalah `docs/openapi.json`. [Exporter](<../scripts/export_openapi.py>) mengimpor factory dari package terinstal lalu memanggil `app.openapi()`, tanpa server/lifespan/acquire pool. Settings memakai konstanta test melalui `model_construct`, bukan `load_settings` atau sumber environment; file runtime dan credential host tidak dibaca. Jangan memakai pola ini untuk konfigurasi runtime karena sengaja melewati validasi settings.

Schema yang dihasilkan adalah snapshot source saat ekspor, bukan bukti deploy atau koneksi Oracle. Router CRUD mendeklarasikan `ErrorResponse` untuk 400/401/404/405/409/422/500/503, termasuk envelope `REQUEST_422`, bukan schema default HTTPValidationError. Liveness memakai `HealthResponse` dengan `data.status="alive"`. Bukti HTTP offline tercatat pada [acceptance](<ACCEPTANCE.md>); CRUD/auth Oracle live belum diuji.

Referensi teknis dibaca melalui Context7: [FastAPI OpenAPI](<https://fastapi.tiangolo.com/how-to/extending-openapi/>), [konfigurasi FastAPI](<https://fastapi.tiangolo.com/reference/fastapi/>), dan [Pydantic 2.14.1 model_construct](<https://github.com/pydantic/pydantic/blob/v2.14.1/docs/concepts/models.md>). Konstanta offline mencegah BaseSettings menggabungkan credential environment pada ekspor.
