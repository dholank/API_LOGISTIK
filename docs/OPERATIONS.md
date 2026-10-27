# Operasi API_LOGISTIK

Status: panduan konfigurasi dan prosedur operator, bukan bukti deployment. Tidak ada perintah di dokumen ini yang telah diberi izin untuk mengubah Oracle. Pengguna menerapkan SQL secara manual setelah memverifikasi target, privilege, fixture dan pemulihan. Lihat [panduan database](<../database/README.md>), [PRD](<PRD.md>) dan [acceptance](<ACCEPTANCE.md>).

## Artefak dan batas deployment

[Dockerfile](<../Dockerfile>) mengunci Python `3.15.2-slim` dengan digest OCI index `sha256:197f6622a70b727a4e61bdac13a73b4e2b914b896aa5a729ceb1f45a09bde5fa` dan uv `0.13.5`, menginstal package normal melalui wheel dengan `uv sync --locked --no-dev --no-editable --no-python-downloads`, lalu menyalin virtualenv saja ke runtime. Hatchling `1.32.4` serta dependency runtime berasal dari [manifest](<../pyproject.toml>) dan [lockfile](<../uv.lock>): FastAPI 0.162.0, Pydantic 2.14.1, python-oracledb 26.0.1, Uvicorn 0.54.0. Tidak ada editable install atau source bind mount pada image rilis. Runtime UID/GID 10001:10001; source, uv, dev tools dan SQL tidak disalin ke stage akhir.

Pemeriksaan registry read-only pada 26 Oktober 2026 menemukan:

- `ghcr.io/astral-sh/uv:0.13.5` tersedia; digest OCI index terverifikasi `sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff`, mencakup Linux amd64/arm64. Dockerfile memakai tag+digest ini.
- `docker.io/library/python:3.15.2-slim` mengembalikan `not found` melalui `docker manifest inspect` dan `docker buildx imagetools inspect`. Default tag tetap dipertahankan sesuai versi terkunci; jalur official image belum tersedia. Tidak ada digest Python yang dikarang atau downgrade otomatis.
- Base alternatif `debian:bookworm-slim` tersedia; digest OCI index terverifikasi `sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8` dipakai pada kedua stage [runtime source-build](<../Dockerfile.python-runtime>).

### Jalur default WSL2, pemeriksaan 27 Oktober 2026

Image resmi Python 3.15.2 kini tersedia. Pemeriksaan `docker buildx imagetools inspect python:3.15.2-slim` mengembalikan digest OCI index di atas. Default Dockerfile beralih ke tag+digest tersebut, tanpa mengubah versi Python atau lockfile. Pin digest mengikuti [panduan Docker](<https://docs.docker.com/build/building/best-practices/#pin-base-image-versions>); pembaruan digest berikutnya memerlukan review dan pengujian ulang.

Docker Engine berjalan pada distro Ubuntu WSL2 yang sama, melalui context `default` dan socket Unix lokal. Perintah dari root project:

```bash
docker compose --env-file /dev/null config --no-interpolate --no-env-resolution --quiet
docker compose build api
docker compose up --no-build --pull never --wait --wait-timeout 90
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/health/live
```

Validasi config memakai profil kosong Linux dan tidak merender credential. Build/start memakai whitelist profil privat Compose yang sudah tersedia, bukan menyalinnya ke image. `--wait` menunggu healthcheck, sedangkan `--no-build --pull never` menjalankan image lokal yang baru dibangun, sesuai [referensi Compose up](<https://docs.docker.com/reference/cli/docker/compose/up/>). Virtualenv Windows hasil pemindahan tidak dipakai pada jalur ini. Gunakan `docker compose stop` untuk menghentikan API; ulangi `up` untuk memulai, atau `build` lalu `up` setelah source berubah. Restart policy tetap `unless-stopped`.

Perubahan ini hanya setup API lokal. Liveness, HTTP development dan tes offline tidak membuktikan auth/CRUD Oracle, persistensi key, TLS client, scheduler atau readiness production. Bukti WSL2 dicatat terpisah pada [acceptance](<ACCEPTANCE.md>).

### Alternatif eksplisit: compile Python versi yang sama di Docker

[Dockerfile.python-runtime](<../Dockerfile.python-runtime>) menyediakan jalur yang disetujui untuk mengompilasi source resmi Python 3.15.2 di builder Debian, bukan mengompilasi pada host atau mengganti patch version. [Halaman rilis resmi](<https://www.python.org/downloads/release/python-3152/>) memuat SHA-256 XZ `8b5536d280142ecf6cdfe15d12a21ba1c65e300bbf7b28a8d0cdb849575797de`, dicocokkan dengan checksum yang diberikan parent. Download HTTPS diverifikasi checksum sebelum ekstraksi. Configure memakai `--enable-shared`, build `make -j2`, tanpa PGO/LTO dan tanpa bootstrap pip; uv mengelola instalasi package pada image aplikasi.

Compiler/header/source tetap di stage builder. Stage runtime menyalin instalasi Python dan memasang library runtime SSL, ctypes/FFI, SQLite, zlib/bzip2/lzma/zstd, readline, UUID dan gdbm beserta CA. Parent melaporkan build runtime Linux amd64 PASS, termasuk checksum, versi tepat dan import modul tersebut. Build image aplikasi juga PASS dengan user `api`, UID/GID10001. Smoke HTTP dan stop/start telah lulus; preflight TCPS/metadata dari container mencapai Oracle 19.26. Auth/CRUD sukses belum diuji karena objek project belum diterapkan.

Dua perintah berikut untuk dijalankan parent/operator setelah persetujuan build, pada daemon/platform Linux yang sama:

```powershell
docker build -f Dockerfile.python-runtime -t api-logistik/python:3.15.2 .
docker build --build-arg PYTHON_IMAGE=api-logistik/python:3.15.2 -t api-logistik:0.1.0-dev .
```

`PYTHON_IMAGE` hanya override eksplisit base builder/runtime, bukan versi dependency. Dockerfile aplikasi memeriksa `sys.version_info[:3] == (3, 15, 2)` pada stage dasar bersama; salah versi gagal sebelum sync. Compose tetap memakai default build; jangan menjalankan Compose rebuild default setelah memilih fallback. Gunakan image aplikasi yang baru dibangun dan opsi Compose `--no-build` saat operator kemudian menjalankannya. Untuk builder terpisah, parent harus membuat image base tersedia pada builder tersebut; tag lokal tidak otomatis tersedia pada daemon/registry lain.

Digest Debian dan checksum source terkunci, tetapi paket apt repository belum memakai snapshot/version pin. Jalur ini belum menjanjikan reproduksibilitas bit-for-bit; simpan provenance, daftar paket, SBOM/hasil scan dan digest image hasil build sebelum rilis. Perubahan base/dependency memerlukan pengujian ulang.

Verifikasi 26 Oktober 2026: build Linux versi tepat, liveness/docs/OpenAPI HTTP 200, empat method bisnis tanpa key 401, 404/405 envelope dan storage auth belum tersedia 503. Stop/start mengembalikan liveness/docs/schema 200. UID10001, read-only filesystem dan loopback publish diperiksa. Ini tidak membuktikan persistensi key, CRUD, TLS eksternal atau benchmark production; audit dependency/image tetap gate rilis.

## Konfigurasi runtime dan jaringan

[Template environment](<../.env.example>) hanya memuat nilai kosong/default, tanpa credential atau key contoh. Siapkan profil runtime privat melalui proses operator; jangan menampilkan isinya atau merender `docker compose config` dengan interpolasi credential. `--no-env-resolution` saja tidak menghentikan interpolasi. Validasi tanpa profil nyata memakai `--env-file NUL --no-interpolate --no-env-resolution --quiet`.

[Compose](<../compose.yaml>) memakai whitelist `environment` yang diinterpolasi dari environment host/profil Compose, bukan meneruskan seluruh file melalui `env_file`. Hanya setting API/Oracle runtime yang terdaftar diteruskan. Writer credential, acknowledgment operator, direktori store dan encryption/master key tidak diteruskan walaupun tersedia pada profil host. Jangan memperluas whitelist dengan setting operator. File runtime dikecualikan dari build melalui [dockerignore](<../.dockerignore>), dan Dockerfile memakai COPY allowlist, bukan seluruh direktori. Secret bukan build argument/layer image. Environment container tetap dapat dibaca administrator Docker; akses daemon adalah privilege sensitif.

Nilai utama:

| Variable | Kontrak/default |
|---|---|
| `ENVIRONMENT` | development, production atau test; production memerlukan trio Oracle lengkap |
| `ORACLE_DSN`, `ORACLE_USER`, `ORACLE_PASSWORD` | Semua diisi bersama atau semua kosong di development/test; DSN wajib TCPS saat koneksi |
| `ORACLE_MODE` | thin; thick dipilih eksplisit tanpa fallback dan wajib `ORACLE_CLIENT_LIB_DIR` |
| `ORACLE_WALLET_DIR`, `ORACLE_WALLET_PASSWORD` | Opsional sesuai kebijakan trust DBA; mount privat read-only, tidak dibake |
| `ORACLE_POOL_MIN/MAX/INCREMENT` | 1 / 5 / 1 per proses worker; pool baru dibuat saat acquire pertama |
| `ORACLE_POOL_WAIT_MS` | 5000 ms; default dinaikkan agar cold pool tidak gagal terlalu cepat |
| `ORACLE_CONNECT_TIMEOUT` | 5 detik; retry koneksi driver 0 |
| `ORACLE_CALL_TIMEOUT_MS` | 5000 ms per panggilan driver, bukan deadline total HTTP |
| `BIND_HOST`, `PORT` | Host lokal default 127.0.0.1:8000; Compose memaksa internal 0.0.0.0:8000 |
| `DOCS_ENABLED` | Tidak diisi: aktif development/test, mati production |

Compose memublikasikan hanya `127.0.0.1:8000:8000`, menjalankan filesystem read-only, tmpfs terbatas, drop semua capability dan no-new-privileges. Entrypoint adalah `python -m api_logistik`; access log Uvicorn mati dan proxy headers tidak dipercaya secara otomatis. Satu proses pada konfigurasi ini. Untuk beberapa worker/replica, hitung batas pool total terhadap kapasitas Oracle, termasuk proses operator terpisah.

Healthcheck memakai urllib standard library untuk GET `/api/v1/health/live` tanpa key/query database. Status healthy bukan readiness auth/CRUD. Startup API tidak menjalankan DDL, seed, compile function atau rotasi. Probe cold pool parent dengan wait 2000 ms gagal `DPY-4005`; probe terbatas dengan wait 10000 ms berhasil dalam 2,758 detik. Default kini 5000 ms, bukan klaim p95 atau pembuktian CRUD. Profil runtime nyata tidak diubah.

Production memerlukan reverse proxy eksternal yang benar-benar memasang sertifikat TLS, renewal, pembatasan akses dan redaksi log. Backend harus privat/firewall; loopback host bukan perlindungan dari container lain pada jaringan Docker yang sama. Jangan mengekspos port HTTP langsung ke client dan jangan membuat default TLS palsu. Profil ini tidak memasang reverse proxy, CA atau sertifikat. Validasi trusted CA/hostname, penolakan sertifikat tidak valid, akses backend dan log proxy sebelum sign-off.

Oracle juga wajib TCPS dengan pemeriksaan server DN aktif. Jangan mematikan verifikasi server atau memakai TCP sebagai fallback. Thin default dipilih eksplisit; kebutuhan verifier/network encryption/client untuk Oracle 19c harus dibuktikan pada target sebenarnya. Thick memerlukan Oracle Client yang cocok dengan Linux/arsitektur dan 19c, library eksplisit serta image turunan yang ditinjau. Image dasar ini tidak menyertakan Instant Client; jangan menganggap path Windows dapat dipakai di container.

## Secret store dan hak operator

API hanya memerlukan privilege baca metadata key serta EXECUTE function bisnis sesuai persetujuan DBA. Jangan berikan writer credential atau material Fernet pada container API. Simpan profil operator terpisah dari profil API. `ORACLE_WRITER_USER/PASSWORD` opsional berpasangan untuk proses operator; tanpa keduanya CLI memakai credential utama sehingga privilege akun tersebut harus ditinjau.

`OPERATOR_AUTHORIZED=True` adalah acknowledgment CLI, bukan autentikasi atau batas keamanan. Otoritas sebenarnya berasal dari identitas OS, ACL, hak DB dan kontrol akses scheduler. Orang yang dapat membaca profil operator dan encryption key dapat bertindak sebagai operator.

Local encrypted Fernet file store hanya untuk development. `KEY_SECRET_STORE_DIR` wajib di luar project dan persisten, dengan owner/permission privat. Pilih tepat satu sumber: `KEY_ENCRYPTION_KEY` SecretStr melalui mekanisme injeksi privat, atau `KEY_ENCRYPTION_KEY_FILE` path file privat. Jangan menaruh nilai key pada command line, stdout, source, contoh atau Oracle. Utamakan file privat yang dibuat CLI; jangan memasukkannya pada shell history. Encryption key, store, hasil export dan backup semuanya material sensitif, walau store terenkripsi.

Windows memeriksa ancestor dan DACL secara ketat; direktori Work/Documents saat ini dapat ditolak. Jangan melonggarkan ACL host atau menonaktifkan pemeriksaan. Minta administrator menyediakan lokasi privat di luar project dengan ancestor yang memenuhi kebijakan. Linux memerlukan owner/permission yang sesuai. Production secret manager belum mempunyai provider nyata yang disepakati; implementasi lokal ini bukan integrasi secret manager production dan tidak memenuhi gate produksi.

## Prosedur CLI development

Perintah di bawah menjelaskan interface; bukan instruksi menjalankannya sekarang. Jalankan `api-logistik-keys --help` dan subcommand `--help` dari package terinstal untuk memeriksa versi sebelum perubahan berizin. Setiap subcommand menerima `--env-file PRIVATE_PROFILE` (default `.env`). Gunakan path privat yang disetujui, bukan path contoh sebagai credential.

```text
api-logistik-keys init-secret-key --output PRIVATE_ENCRYPTION_KEY_FILE --env-file PRIVATE_PROFILE
api-logistik-keys status --env-file PRIVATE_PROFILE
api-logistik-keys prepare --expected-version N --reason bootstrap --env-file PRIVATE_PROFILE
api-logistik-keys export --key-id N --output PRIVATE_DELIVERY_FILE --env-file PRIVATE_PROFILE
api-logistik-keys confirm-distributed --key-id N --expected-version N --reason distribution_confirmed --env-file PRIVATE_PROFILE
api-logistik-keys activate --expected-version N --reason scheduled --env-file PRIVATE_PROFILE
api-logistik-keys revoke --key-id N --expected-version N --reason suspected_compromise --env-file PRIVATE_PROFILE
api-logistik-keys tick --env-file PRIVATE_PROFILE
api-logistik-keys reconcile --operation-id ORIGINAL_UUID --key-id N --env-file PRIVATE_PROFILE
```

1. Administrator menyiapkan profil privat, lokasi store/encryption key dan target Oracle kanonis. `init-secret-key` membuat encryption key ke file privat, bukan key autentikasi di stdout. Jangan overwrite material lama atau menjalankan bootstrap pada target yang belum disetujui.
2. Baca status/VERSION. `prepare` membuat kandidat PENDING, bukan langsung ACTIVE. Untuk mengganti kandidat yang belum siap gunakan `--replace-pending --reason REASON --expected-version N` hanya setelah menilai distribusi kandidat sebelumnya. Kunci baru tidak boleh dicetak.
3. `export` menulis raw key ke output privat. Salurkan melalui kanal secret yang disetujui, cek seluruh penerima/client siap, dan cabut akses file delivery setelah distribusi sesuai kebijakan. Kanal/ack otomatis belum dipilih; jangan kirim melalui chat, email biasa atau tiket.
4. Baca versi terbaru lalu `confirm-distributed` untuk ID kandidat tepat dan VERSION yang diharapkan. CLI memeriksa material store lalu memeriksa ulang hash kandidat di bawah lock GLOBAL untuk menolak race pergantian kandidat. Readiness terikat kandidat+versi, bukan boolean umum. Mutasi lain dapat membuat versi stale, sehingga operator harus membaca ulang dan tidak menebak versi berikutnya.
5. Aktivasi awal/normal memerlukan readiness. `activate --manual` dapat meminta cutover lebih awal sesuai kebijakan engine; early manual ditolak ketika GRACE lama masih live. Jangan memakai manual untuk melewati readiness atau memperpanjang expiry.

Aktivasi aktual A menetapkan due A+7 hari dan expiry asli A+8 hari. Cutover normal B memberi GRACE sampai `min(expiry_asli, B+24 jam)`. PENDING tidak dapat dipakai untuk autentikasi, dan EXPIRED/REVOKED tidak dapat dihidupkan kembali. Waktu disimpan timezone-aware; due tidak mengikuti jadwal Senin tetap.

Jika key kompromi, operator dapat `revoke` segera dengan alasan dan versi tepat, walau replacement belum siap. Nyatakan risiko outage terlebih dahulu. Emergency replacement memakai `prepare --emergency --expected-version N --reason suspected_compromise`; flag emergency otomatis mengizinkan penggantian PENDING. Distribusi/konfirmasi kandidat yang sama tetap wajib, lalu gunakan `activate --emergency --expected-version N --reason suspected_compromise` dengan versi terbaru. Aktivasi emergency mencabut seluruh key lama yang masih live, termasuk GRACE, atomik dengan aktivasi replacement siap. Tidak ada grace emergency, revival atau auth bypass.

`--reason` wajib pada prepare, confirm-distributed, activate dan revoke, dengan pilihan tepat: `bootstrap`, `scheduled`, `manual_rotation`, `suspected_compromise`, `distribution_confirmed`, `key_retired`, `recovery`. Bukan teks bebas. Semua subcommand menerima `--operation-id UUID`; bila tidak diisi CLI membuat UUID baru. Simpan ID operasi asli dari output aman, bukan raw key/hash. Exit 0 sukses, 1 error aplikasi/store, 2 ditolak/blocked, 3 lock busy, 4 hasil commit tidak diketahui.

Jika commit tidak diketahui, hentikan retry mutasi. `reconcile --operation-id ORIGINAL_UUID` wajib memakai ID asli; `--key-id N` opsional membantu pemeriksaan kandidat. Rekonsiliasi membuat PoolManager/fisik pool baru, mengambil lock GLOBAL lebih dahulu, lalu membaca state/key. Hanya kecocokan `LAST_OPERATION_ID` mengonfirmasi operasi asli pada hasil ini. `historical_key_found=true` sendiri bukan bukti commit operasi tersebut. Bila LAST_OPERATION_ID sudah tertimpa operasi lain, `manual_review_required=true`; cocokkan metadata dan lakukan review manual, jangan menyimpulkan sukses/gagal atau retry buta. Rekonsiliasi bukan izin memperpanjang key atau meregenerasi material.

## Scheduler eksternal, alert dan pemulihan

Jalankan `tick` setiap satu menit sebagai proses operator terpisah lewat cron atau Windows Task Scheduler, bukan loop startup/worker HTTP dan bukan job Oracle. Scheduler harus memakai executable environment terinstal, working directory terkontrol, profil privat, hak minimum dan pencatatan exit code yang tersanitasi. Jangan menaruh credential/raw key pada definisi job atau redirect debug trace. Definisi job host belum dipasang atau diuji oleh paket ini.

Target staging kandidat adalah 24 jam sebelum due. Tick berulang harus idempotent melalui lock GLOBAL, pemeriksaan VERSION dan state. Sebelum distribusi/ack otomatis terbukti, proses ini tetap semi-otomatis. Saat due tetapi kandidat belum ready, alert dan eskalasi; jangan aktivasi paksa, menambah grace, atau memperpanjang expiry.

Pantau tick terakhir/exit, due/expiry, umur PENDING, readiness belum terkonfirmasi, lock busy, kegagalan DB, kegagalan store, tidak adanya successor, dan commit outcome unknown. Tetapkan penerima/eskalasi sebelum mengaktifkan jadwal; threshold warning minimal memberi waktu distribusi sebelum due dan hard expiry. Pantau juga 401/503 dan jangan menganggap liveness menggantikan indikator itu. Belum ada integrasi alert/provider yang terbukti di production.

Backup store terenkripsi dan encryption key melalui akses terpisah/terkontrol; uji restore di sandbox berizin. Kehilangan keduanya dapat membuat raw key tidak dapat dipulihkan meski metadata Oracle masih ada. Restart API tidak boleh mint key atau menghapus state. Setelah outage scheduler/DB, baca status dan rekonsiliasi hasil; expiry tetap berjalan dan key expired tidak dipulihkan. Persetujuan perubahan baru, kandidat siap dan prosedur emergency diperlukan bila layanan sudah kehilangan key live.

Sebelum restart/deploy: verifikasi target Oracle, privilege, schema, distribusi, backup dan rollback aplikasi. Parent melaporkan TCPS Oracle 19.26, charset AL32UTF8; USER/ALL objects serta synonym tidak menemukan target KARYAWAN/tabel key/function. Koneksi/probe pool bukan bukti auth/CRUD tersedia. Paket kini delapan source SQL, termasuk fresh-only [T_KARYAWAN](<../database/schema/T_KARYAWAN.sql>) dan [F_CRUD_KARYAWAN_LOGISTIK](<../database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) yang disetujui pengguna; penerapan tetap manual oleh pengguna, tanpa izin DDL/DML live pada pekerjaan ini. Jangan otomatis menjalankan direktori SQL, seed atau routine/job historis.

Lima tes integrasi baru hanya dikoleksi/skip offline, belum dijalankan live. Jalur read-only memerlukan `RUN_ORACLE_READONLY_INTEGRATION=1` dan `ORACLE_TEST_ENV_FILE` berupa path absolut di luar project. Jalur tulis memerlukan `RUN_ORACLE_WRITE_INTEGRATION=I_ACKNOWLEDGE_ISOLATED_EMPTY_SCHEMA`, profil test eksplisit melalui variable yang sama, schema/tabel fixture kosong terisolasi dan izin terpisah. Profil runtime project saat ini dilarang untuk tes tersebut. Flag opt-in bukan izin menulis dan tidak melakukan provisioning/DDL otomatis.

## Logging runtime dan shutdown

Log request hanya memuat metadata allowlist dan route pattern, bukan header/body/query atau ID mentah. Raw Uvicorn access logger dimatikan. Formatter menolak nama event bebas; exception/trace/object tidak dirender. Hook thread dan unraisable dipasang saat konfigurasi logging, bukan saat import, dan hanya menghasilkan event konstan. Uji thread/unraisable nyata dalam container membuktikan canary tidak tercetak.

Run awal menemukan error background close python-oracledb 26.0.1 ketika koneksi/network ditutup, diikuti StopIteration. Sanitasi hook mencegah raw traceback; ini bukan patch driver atau bukti penyebab jaringan sudah hilang. Pantau event background_thread_failed, periksa backend/pool dan restart terkontrol bila terjadi saat operasi. Jangan menggunakan cache/bypass atau mengulang mutasi dengan commit outcome unknown. Dokumentasi hook: [threading](<https://docs.python.org/3.15/library/threading.html#threading.excepthook>) dan [unraisable](<https://docs.python.org/3.15/library/sys.html#sys.unraisablehook>).

## Pemeriksaan platform secret store

Pada WSL2 dan container Linux, [secret store](<../src/api_logistik/security/secret_store.py>) memakai permission POSIX: direktori privat 0700, material key/export 0600, serta pemeriksaan owner, ancestor dan symlink. Guard platform menggunakan `sys.platform == "win32"` untuk membatasi API Windows, bukan mencoba menjalankan utilitas Windows yang mungkin tersedia lewat WSL interop. Pemanggilan helper ACL Windows pada POSIX ditolak dengan error terkontrol sebelum library Windows dimuat.

Guard ini mengikuti [dukungan platform checks mypy](<https://mypy.readthedocs.io/en/stable/common_issues.html#python-version-and-system-platform-checks>), dengan mypy 2.4.0 dan Python 3.15.2 sesuai lockfile. [ctypes.WinDLL](<https://docs.python.org/3.15/library/ctypes.html#ctypes.WinDLL>) dan [os.path.isreserved](<https://docs.python.org/3.15/library/os.path.html#os.path.isreserved>) hanya tersedia pada Windows; [sys.platform](<https://docs.python.org/3.15/library/sys.html#sys.platform>) pada Linux adalah `linux`, termasuk proses Python Linux di WSL2. Tidak ada `type: ignore`, penonaktifan error `attr-defined`, atau perubahan kebijakan ACL/permission untuk meloloskan type-check.

Jalankan mypy default di image tes Linux. Pemeriksaan tambahan `mypy --platform win32` memeriksa cabang Windows secara statis, bukan menggantikan tes ACL pada host Windows asli. Tes fixture Linux tetap offline dan tidak memakai secret store operator atau Oracle nyata.

## Referensi keputusan

Dokumentasi dibaca melalui Context7 sebelum konfigurasi: [Docker multi-stage](<https://docs.docker.com/build/building/multi-stage/>), [Dockerfile reference](<https://docs.docker.com/reference/dockerfile/>), [Compose services](<https://docs.docker.com/reference/compose-file/services/>), [uv 0.13.5 Docker integration](<https://github.com/astral-sh/uv/blob/0.13.5/docs/guides/integration/docker.md>) dan [FastAPI configuration](<https://fastapi.tiangolo.com/reference/fastapi/>). Multi-stage/non-editable menghilangkan ketergantungan runtime pada source checkout; allowlist COPY mencegah profil runtime masuk image; loopback publish menghindari eksposur HTTP host secara default. Ini keputusan konfigurasi, bukan klaim hardening atau deployment sudah lulus.
