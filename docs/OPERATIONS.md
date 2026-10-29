# Operasi API_LOGISTIK

Panduan ini mencakup deployment, konfigurasi, dan pekerjaan operator. Perintah di sini bukan izin untuk mengubah Oracle. Setiap perubahan tetap memerlukan target, privilege, fixture, scope izin, dan rencana pemulihan. Penerapan SQL mengikuti [panduan database](<../database/README.md>); hasil pengujian dicatat pada [acceptance](<ACCEPTANCE.md>).

## Artefak dan batas deployment

[Dockerfile](<../Dockerfile>) memakai image resmi Python 3.15.2 dan uv 0.13.5 dengan tag+digest terkunci. Build memasang package non-editable melalui wheel menggunakan `uv sync --locked --no-dev --no-editable --no-python-downloads`. Hatchling 1.32.4 dan dependency runtime mengikuti [manifest](<../pyproject.toml>) serta [lockfile](<../uv.lock>).

Stage akhir hanya menerima virtualenv, bukan source checkout, SQL, uv, atau dev tools. Container memakai UID/GID 10001:10001. Jangan memasukkan credential ke build argument, layer image, atau source bind mount.

Arsip image lokal dengan pola `api-logistik*.tar`, `api-logistik*.tar.gz`, dan `api-logistik*.tar.zst` dikecualikan oleh [Git ignore](<../.gitignore>) dan [Docker ignore](<../.dockerignore>), termasuk di subfolder. Metadata `:Zone.Identifier` tetap dikecualikan agar salinan dari Windows tidak ikut commit/build. File privat, cache, dan tooling pada subfolder juga dikecualikan dari konteks Docker; template environment di luar direktori privat tetap disertakan.

Aturan mengikuti [semantik gitignore](<https://github.com/git/htmldocs/blob/gh-pages/gitignore.adoc>) dan [Docker build context](<https://github.com/docker/docs/blob/main/content/manuals/build/concepts/context.md>). Ignore tidak menghapus file yang sudah tracked atau menyaring hasil `docker image save`; arsip menyimpan image yang sudah dibangun, sehingga isinya tetap perlu direview sebelum dibagikan.

Pemeriksaan 29 Oktober 2026 meluluskan 68 kasus path Git dan 70 assertion build context Docker dengan fixture sintetis `FROM scratch`. Seluruh 75 path source tracked tetap disertakan. Tes tidak memakai credential asli atau Oracle; container API tetap berhenti. Ini pengujian aturan ignore, bukan build ulang image API atau audit seluruh layer image.

### Jalur default WSL2, pemeriksaan 27 Oktober 2026

Docker Engine berjalan pada distro Ubuntu WSL2 yang sama, melalui context `default` dan socket Unix lokal. Image resmi Python 3.15.2 kini tersedia; Dockerfile mengunci digest OCI index `sha256:197f6622a70b727a4e61bdac13a73b4e2b914b896aa5a729ceb1f45a09bde5fa`. Pembaruan digest memerlukan review dan pengujian ulang, sesuai [panduan pin base image Docker](<https://docs.docker.com/build/building/best-practices/#pin-base-image-versions>).

Jalankan dari root project:

```bash
docker compose --env-file /dev/null config --no-interpolate --no-env-resolution --quiet
docker compose build api
docker compose up --no-build --pull never --wait --wait-timeout 90
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/health/live
```

Validasi config memakai profil kosong Linux dan tidak mencetak credential. Build/start memakai whitelist konfigurasi runtime Compose, bukan menyalin profil privat ke image. Opsi `--wait` menunggu healthcheck; `--no-build --pull never` menjalankan image lokal yang baru dibangun. Lihat [referensi Compose up](<https://docs.docker.com/reference/cli/docker/compose/up/>).

Gunakan `docker compose stop` untuk menghentikan API. Ulangi `up` untuk memulai, atau `build` lalu `up` setelah source berubah. Restart policy adalah `unless-stopped`. Jalur ini tidak memakai virtualenv Windows dari workspace lama.

Status `healthy` hanya membuktikan liveness. Bootstrap key dan CRUD HTTP pada Oracle sudah diuji secara terpisah; hasil tersebut belum menutup gate TLS, rotasi, restart dengan key aktif, atau production pada [acceptance](<ACCEPTANCE.md>).

### Alternatif eksplisit: compile Python versi yang sama di Docker

Pada 26 Oktober 2026, tag image resmi belum tersedia. [Dockerfile.python-runtime](<../Dockerfile.python-runtime>) menyediakan fallback Python 3.15.2 dari source resmi, tanpa mengganti patch version atau memasang compiler pada host. Jalur ini tetap tersedia, tetapi bukan default WSL2 saat ini.

Fallback memakai Debian ber-digest `sha256:7ff6ba31527b9e336162fa061746c366c4b2032f4d2cff2078bea43f78efe3f8`. Download HTTPS diverifikasi sebelum ekstraksi dengan SHA-256 XZ `8b5536d280142ecf6cdfe15d12a21ba1c65e300bbf7b28a8d0cdb849575797de` dari [rilis resmi Python 3.15.2](<https://www.python.org/downloads/release/python-3152/>). Configure memakai `--enable-shared`, build `make -j2`, tanpa PGO/LTO atau bootstrap pip; uv memasang package aplikasi.

Compiler, header, dan source tetap di builder. Stage runtime memuat instalasi Python, CA, serta library SSL, ctypes/FFI, SQLite, zlib/bzip2/lzma/zstd, readline, UUID, dan gdbm. Build serta import modul fallback Linux amd64 lulus pada snapshot 26 Oktober; ini bukti historis, bukan pengujian ulang saat ini.

Gunakan daemon/builder Linux yang sama untuk kedua image:

```bash
docker build -f Dockerfile.python-runtime -t api-logistik/python:3.15.2 .
docker build --build-arg PYTHON_IMAGE=api-logistik/python:3.15.2 -t api-logistik:0.1.0-dev .
```

`PYTHON_IMAGE` hanya mengganti base image secara eksplisit, bukan versi dependency. Dockerfile menolak versi selain 3.15.2 sebelum sync. Sesudah memilih fallback, jalankan image hasil build dengan Compose `--no-build`; rebuild default akan kembali memakai image resmi. Tag lokal tidak otomatis tersedia pada builder atau daemon lain.

Digest Debian dan checksum source terkunci, tetapi paket apt belum memakai snapshot/version pin. Build ini belum menjanjikan reproduksibilitas bit-for-bit. Simpan provenance, daftar paket, SBOM/hasil scan, dan digest image sebelum rilis; uji ulang setelah perubahan base atau dependency.

## Konfigurasi runtime dan jaringan

[Template environment](<../.env.example>) berisi nilai kosong/default tanpa credential atau key contoh. Isi profil privat secara lokal. Jangan mencetak isinya atau hasil `docker compose config` yang sudah diinterpolasi. Opsi `--no-env-resolution` saja tidak menghentikan interpolasi; gunakan validasi `/dev/null` pada contoh WSL2 di atas.

[Compose](<../compose.yaml>) meneruskan whitelist `environment` dari environment host/profil Compose, bukan seluruh file lewat `env_file`. Writer credential, acknowledgment operator, direktori store, dan encryption/master key tidak diteruskan ke API. Jangan memperluas whitelist API dengan setting operator.

[Docker ignore](<../.dockerignore>) mengecualikan profil privat; Dockerfile memakai COPY allowlist. Administrator Docker tetap dapat membaca environment container, sehingga akses daemon harus dibatasi.

| Variable | Kontrak/default |
|---|---|
| `ENVIRONMENT` | development, production, atau test; production memerlukan trio Oracle lengkap |
| `ORACLE_DSN`, `ORACLE_USER`, `ORACLE_PASSWORD` | Diisi bersama, atau semuanya kosong di development/test; koneksi wajib TCPS |
| `ORACLE_MODE` | thin; Thick dipilih eksplisit, tanpa fallback, dengan `ORACLE_CLIENT_LIB_DIR` |
| `ORACLE_WALLET_DIR`, `ORACLE_WALLET_PASSWORD` | Opsional sesuai kebijakan DBA; mount privat read-only, bukan bagian image |
| `ORACLE_POOL_MIN`, `ORACLE_POOL_MAX`, `ORACLE_POOL_INCREMENT` | 1 / 5 / 1 per proses API; pool dibuat saat acquire pertama |
| `ORACLE_POOL_WAIT_MS` | 5000 ms |
| `ORACLE_CONNECT_TIMEOUT` | 5 detik; retry koneksi driver 0 |
| `ORACLE_CALL_TIMEOUT_MS` | 5000 ms per panggilan driver, bukan deadline HTTP keseluruhan |
| `BIND_HOST`, `PORT` | Lokal 127.0.0.1:8000; Compose memaksa internal 0.0.0.0:8000 |
| `DOCS_ENABLED` | Default aktif di development/test, nonaktif di production |

Compose memublikasikan hanya `127.0.0.1:8000:8000`, dengan filesystem read-only, tmpfs terbatas, cap-drop ALL, dan no-new-privileges. Entrypoint `python -m api_logistik` menjalankan satu proses; access log Uvicorn mati dan proxy headers tidak dipercaya otomatis. Untuk beberapa worker/replica, hitung kapasitas pool total terhadap Oracle, termasuk proses operator. Operasi writer CLI memakai pool 1/1.

Healthcheck memanggil `/api/v1/health/live` tanpa key atau query database. Startup tidak menjalankan DDL, seed, compile function, atau rotasi. Default acquire wait naik dari 2000 ke 5000 ms setelah cold-pool probe awal gagal `DPY-4005`; probe dengan wait 10000 ms berhasil dalam 2,758 detik. Angka itu bukan benchmark p95.

Production memerlukan reverse proxy TLS dengan sertifikat, renewal, kontrol akses, dan redaksi log yang teruji. Backend harus privat/firewall; loopback host tidak melindungi dari container lain pada jaringan Docker yang sama. Profil ini tidak memasang proxy, CA, atau sertifikat. Verifikasi trusted CA/hostname, penolakan sertifikat invalid, pembatasan backend, dan log proxy sebelum sign-off.

Oracle wajib TCPS dengan server DN verification aktif. Jangan mematikan verifikasi atau memakai TCP sebagai fallback. Thin adalah default eksplisit; kebutuhan verifier/network encryption/client tetap harus cocok dengan target Oracle 19c. Thick memerlukan Oracle Client yang sesuai Linux/arsitektur dan 19c, path library eksplisit, serta image turunan yang direview. Image dasar tidak berisi Instant Client; path Windows tidak dapat dipakai di container Linux.

## Secret store dan hak operator

API memerlukan SELECT metadata key serta EXECUTE function bisnis sesuai review DBA, bukan writer credential atau material Fernet. Pisahkan profil operator dari profil API. `ORACLE_WRITER_USER` dan `ORACLE_WRITER_PASSWORD` bersifat opsional, tetapi wajib berpasangan; tanpa keduanya CLI memakai credential utama. Tinjau privilege akun tersebut sebelum provisioning.

`OPERATOR_AUTHORIZED=True` hanya acknowledgment CLI. Batas keamanan berasal dari identitas OS, permission/ACL, hak DB, dan akses scheduler. Pembaca profil operator serta encryption key dapat bertindak sebagai operator.

Local encrypted Fernet store hanya untuk development. `KEY_SECRET_STORE_DIR` harus persisten dan berada di luar project. Pilih satu sumber master key: `KEY_ENCRYPTION_KEY` melalui injeksi privat atau `KEY_ENCRYPTION_KEY_FILE` berupa file privat. Utamakan file yang dibuat CLI. Jangan menaruh raw key pada argumen command line, stdout, shell history, source, contoh, atau Oracle. Store terenkripsi, master key, export, dan backup tetap material sensitif.

Linux memerlukan owner dan permission yang sesuai. Windows memeriksa ancestor/DACL; folder shared atau Work/Documents dapat ditolak. Jangan melonggarkan ACL host secara global atau mematikan guard agar provisioning lolos. Minta administrator menyediakan lokasi privat yang sesuai. Provider secret manager production belum dipilih atau diuji.

## Prosedur CLI development

### Alur utama: rotasi manual

Operator menjalankan setiap langkah sendiri. Tidak ada cron, timer, loop tick, auto-confirm, atau auto-retry pada tahap ini. Manual tidak menonaktifkan expiry: siapkan dan distribusikan successor sebelum due, lalu aktifkan pada/setelah due. Semua client berbagi satu key GLOBAL; perubahan harus dikoordinasikan dengan seluruh penerima.

[Launcher manual](<../scripts/api_key_operator.sh>) memakai Bash di WSL2/Linux dan menjalankan satu CLI pada satu container operator. API boleh tetap berhenti. Launcher tidak memakai Python host, Docker Compose, port HTTP, source bind mount, atau Docker socket dalam container. Image harus sudah tersedia lokal dan dipin ID `sha256:...`; tidak ada pull atau pergantian image otomatis. Launcher memaksa context `default` pada socket lokal `/var/run/docker.sock` dan menolak override endpoint/context remote. Custom socket, rootless Docker, atau context `desktop-linux` belum menjadi target launcher ini; jangan mengubah context agar mount privat diam-diam berpindah host.

Default direktori privat adalah `${XDG_DATA_HOME:-$HOME/.local/share}/api-logistik`; `API_LOGISTIK_OPERATOR_ROOT` boleh menunjuk lokasi absolut lain di luar checkout. Di WSL, gunakan filesystem Linux seperti home operator, bukan folder Windows bersama. Launcher fase ini menargetkan WSL2/Linux, bukan shell Windows/macOS native. Struktur yang diperlukan:

```text
ROOT/                       owner operator, 0700
  operator-manual.env       koneksi Oracle lengkap dan setting operator, 0600
  operator-image.id         satu image ID immutable, 0600
  master.key                master existing, 0600
  ciphertext/               encrypted store existing, 0700
  delivery/                 file export privat, 0700
  audit/                    intent dan hasil command, 0700
```

Profil privat memuat trio Oracle yang disetujui, `OPERATOR_AUTHORIZED=true`, `KEY_SECRET_STORE_DIR=ROOT/ciphertext`, dan `KEY_ENCRYPTION_KEY_FILE=ROOT/master.key`, dengan path absolut yang sama di host/container. Jangan memakai contoh `ROOT` secara literal, mengirim credential lewat argv, atau shell-source profil. Jangan overwrite bootstrap profile atau master key existing. Simpan profil, pin, dan material privat melalui akses operator, bukan Git. Permission direktori/file yang tidak aman, symlink, atau pin yang bukan image ID ditolak.

```bash
scripts/api_key_operator.sh --help
scripts/api_key_operator.sh status
```

Contoh berikut adalah interface, bukan batch siap jalan. Ganti setiap ID dan VERSION dari hasil pembacaan terbaru; `VERSION_SETELAH_CONFIRM` berbeda dari VERSION sebelum konfirmasi.

```text
scripts/api_key_operator.sh prepare --expected-version VERSION_STATUS --reason manual_rotation
scripts/api_key_operator.sh export --key-id ID_PENDING --output ABSOLUTE_ROOT/delivery/successor.txt
scripts/api_key_operator.sh confirm-distributed --key-id ID_PENDING --expected-version VERSION_PENDING --reason distribution_confirmed
scripts/api_key_operator.sh activate --expected-version VERSION_SETELAH_CONFIRM --reason manual_rotation
scripts/api_key_operator.sh status
```

1. Baca status dan due/expiry. Jika PENDING sudah ada, review kandidat tersebut; jangan menggantinya tanpa menilai dampak distribusi.
2. Jalankan prepare dengan VERSION tepat. PENDING belum valid untuk autentikasi. UUID operasi tersimpan pada audit privat sebelum command dijalankan.
3. Export ke file baru langsung di delivery, tanpa overwrite. Salurkan melalui kanal rahasia yang disetujui; pastikan seluruh penerima siap. Keberadaan file tidak berarti readiness.
4. Baca status lagi, lalu confirm-distributed untuk ID_PENDING dan VERSION yang benar. Kandidat/VERSION yang berubah memerlukan pemeriksaan ulang.
5. Activate normal pada/setelah due dengan VERSION hasil konfirmasi. Reason `manual_rotation` tidak melewati pemeriksaan due; flag `--manual` untuk cutover lebih awal hanya jika operator memintanya secara eksplisit. Launcher tidak menambahkan flag itu.
6. Baca status dari koneksi baru. Periksa ACTIVE/GRACE dan waktu; tes HTTP membutuhkan API aktif serta izin scope terpisah. Jangan menyatakan client siap hanya dari health check.
7. Pastikan seluruh client memakai key baru sebelum grace selesai. Key expired tetap ditolak walaupun tidak ada scheduler yang membersihkan status metadata.

Output export terbatas pada direct child delivery, tanpa file existing/symlink. Launcher menolak tick, init-secret-key, override env-file, dan argumen tidak dikenal. Untuk bootstrap target lain atau operasi lanjut, gunakan CLI terinstal setelah izin terpisah, bukan mengakali guard launcher.

Setiap pemanggilan memiliki audit unik berpermission 0600, berisi intent/UUID, image ID, stdout CLI tersanitasi, dan exit code; bukan dump argv atau credential. Stderr Docker tidak disalin ke terminal/audit; kegagalan engine ditandai dengan pesan konstan dan exit code aslinya. Jika hasil tidak lengkap atau sinkronisasi audit gagal, review UUID sebelum mutasi berikutnya. Tidak ada chaining langkah berikutnya. Jika exit 4 atau proses terputus, hentikan mutasi dan gunakan UUID asli:

```text
scripts/api_key_operator.sh reconcile --operation-id UUID_OPERASI_ASLI --key-id ID_JIKA_DIKETAHUI
```

Reconcile tidak mendapat UUID baru pengganti. Jika `LAST_OPERATION_ID` sudah berubah, review manual tetap diperlukan. Jangan membuang ciphertext/export/audit ketika hasil operasi belum jelas.

### Interface CLI terinstal

Contoh berikut menjelaskan interface lanjutan, bukan urutan siap salin. Bootstrap atau tick di bawah ini bukan bagian alur manual aktif. Jalankan `api-logistik-keys --help` dan subcommand `--help` dari package terinstal sebelum perubahan berizin. Setiap command menerima `--env-file PRIVATE_PROFILE`; tanpa argumen itu CLI memakai profil default lokal. Placeholder `N` menandai ID atau VERSION sesuai argumennya. Gunakan hasil `status` terbaru, bukan angka tebakan.

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

1. Siapkan target canonical, profil privat, store persisten, dan file encryption key. `init-secret-key` membuat file privat, bukan key autentikasi di stdout. Jangan overwrite material lama atau bootstrap pada target yang belum disetujui.
2. Baca `status` dan VERSION sebelum `prepare`. Kandidat berstatus PENDING, belum bisa mengautentikasi. Penggantian kandidat memakai `--replace-pending --reason REASON --expected-version N` hanya setelah dampak distribusinya dinilai.
3. Gunakan `export` ke file privat dan salurkan lewat kanal secret yang disetujui. Konfirmasikan seluruh penerima siap. Jangan kirim melalui chat, email biasa, atau tiket; cabut akses file delivery sesuai kebijakan setelah distribusi.
4. Jalankan `confirm-distributed` untuk kandidat ID dan VERSION tepat. CLI memeriksa material store, lalu memeriksa ulang kandidat di bawah lock GLOBAL. Perubahan kandidat atau VERSION membuat konfirmasi stale; baca state lagi, jangan mengganti angka secara buta.
5. Aktifkan hanya setelah readiness terkonfirmasi. `activate --manual` mengizinkan cutover lebih awal sesuai engine, tetapi menolak GRACE lama yang masih live. Flag ini tidak melewati readiness atau memperpanjang expiry.

Aktivasi aktual A menetapkan due A+7 hari dan expiry asli A+8 hari. Cutover normal B membatasi GRACE lama sampai `min(expiry_asli, B+24 jam)`. PENDING tidak valid untuk auth; EXPIRED/REVOKED tidak boleh dihidupkan kembali. Timestamp timezone-aware mengikuti aktivasi aktual, bukan jadwal Senin tetap.

### Revoke dan aktivasi darurat

Operator boleh revoke key kompromi segera tanpa replacement, dengan risiko outage yang dinyatakan. Untuk replacement darurat, gunakan `prepare --emergency --expected-version N --reason suspected_compromise`; flag ini mengizinkan penggantian PENDING. Distribusi dan konfirmasi kandidat yang sama tetap wajib. Setelah membaca VERSION terbaru, `activate --emergency --expected-version N --reason suspected_compromise` mencabut seluruh key lama yang live, termasuk GRACE, lalu mengaktifkan replacement dalam satu transaksi. Tidak ada overlap darurat, revival, atau auth bypass.

### Alasan operasi, exit code, dan rekonsiliasi

`--reason` wajib pada prepare, confirm-distributed, activate, dan revoke. Nilainya terbatas pada `bootstrap`, `scheduled`, `manual_rotation`, `suspected_compromise`, `distribution_confirmed`, `key_retired`, atau `recovery`; bukan teks bebas.

Semua command menerima `--operation-id UUID`; CLI membuat UUID jika tidak diberikan. Simpan ID operasi asli dari output tersanitasi, bukan raw key atau hash. Exit code: 0 sukses, 1 error aplikasi/store, 2 ditolak/blocked, 3 lock busy, dan 4 hasil commit tidak diketahui.

Jika hasil commit tidak diketahui, hentikan retry mutasi. Jalankan `reconcile --operation-id ORIGINAL_UUID` dengan ID asli; `--key-id N` opsional. Rekonsiliasi memakai pool/session baru, mengambil lock GLOBAL, lalu membaca state/key. Hanya kecocokan `LAST_OPERATION_ID` yang mengonfirmasi operasi asli. `historical_key_found=true` sendiri tidak membuktikan commit.

Jika `LAST_OPERATION_ID` sudah tertimpa, hasil `manual_review_required=true` memerlukan pencocokan metadata dan review operator. Jangan menyimpulkan sukses/gagal, retry buta, memperpanjang expiry, atau meregenerasi material sebagai jalan pintas.

## Scheduler eksternal, alert dan pemulihan

Scheduler host belum dipasang atau diuji. Rancangan memakai `tick` setiap satu menit melalui cron atau Windows Task Scheduler sebagai proses operator terpisah, bukan loop startup/worker API atau job Oracle. Scheduler harus memakai executable terinstal, working directory terkontrol, profil privat, privilege minimum, dan exit code tersanitasi. Jangan menyimpan credential/raw key pada definisi job atau debug trace.

Engine menyiapkan kandidat 24 jam sebelum due. Tick harus idempotent melalui lock GLOBAL, pemeriksaan VERSION, dan state. Rotasi tetap semi-otomatis sampai distribusi/ack ikut otomatis. Jika due tercapai tetapi kandidat belum siap, kirim alert dan eskalasi; jangan mengaktifkan paksa, menambah grace, atau memperpanjang expiry.

Pantau tick terakhir, exit code, due/expiry, umur PENDING, readiness, lock busy, DB/store failure, successor yang hilang, commit outcome unknown, serta 401/503. Tetapkan penerima dan eskalasi sebelum scheduler diaktifkan. Warning harus memberi waktu distribusi sebelum due dan hard expiry. Liveness tidak menggantikan indikator tersebut; provider alert production belum terbukti.

Backup store terenkripsi dan encryption key melalui akses terpisah. Uji restore pada sandbox berizin. Kehilangan keduanya dapat membuat raw key tidak dapat dipulihkan meski metadata Oracle masih ada. Restart API tidak boleh mint key atau menghapus state. Setelah outage, baca status dan rekonsiliasi; expiry tetap berjalan dan key expired tidak dipulihkan. Penggantian darurat memerlukan persetujuan, kandidat baru yang siap, dan prosedur yang sama.

Sebelum restart/deploy, periksa target, privilege, schema, distribusi, backup, dan rollback aplikasi. Snapshot awal belum menemukan objek project; preflight berikutnya menemukan keempat objek VALID. Bootstrap serta CRUD fixture live kemudian lulus dengan izin terpisah pada [acceptance](<ACCEPTANCE.md>). Bukti itu tidak mengizinkan DDL atau mutasi lain. Ikuti [registry PRD](<PRD.md#16-konvensi-nama-file-sql>) dan jangan mengeksekusi seluruh direktori SQL, seed, atau routine/job historis otomatis.

Lima tes integrasi opt-in belum dijalankan live. Read-only memerlukan `RUN_ORACLE_READONLY_INTEGRATION=1` dan `ORACLE_TEST_ENV_FILE` absolut di luar project. Writes juga memerlukan `RUN_ORACLE_WRITE_INTEGRATION=I_ACKNOWLEDGE_ISOLATED_EMPTY_SCHEMA`, profil test terpisah, schema/tabel fixture kosong terisolasi, dan izin. Profil runtime project dilarang untuk suite ini; flag bukan izin tulis atau provisioning/DDL otomatis.

## Logging runtime dan shutdown

Log hanya memuat metadata allowlist dan route pattern, bukan header, body, query, credential, atau ID karyawan mentah. Access log Uvicorn mati; formatter tidak merender nama event bebas, traceback, atau object exception. Hook thread/unraisable dipasang saat konfigurasi logging, bukan saat import, dan hanya mencatat event konstan. Uji nyata dalam container memastikan canary tidak tercetak.

Run awal menemukan error background close python-oracledb 26.0.1 saat koneksi/network ditutup, disusul StopIteration. Sanitasi hook mencegah traceback mentah, bukan memperbaiki driver atau membuktikan akar masalah jaringan hilang. Pantau `background_thread_failed`, periksa backend/pool, dan lakukan restart terkontrol bila diperlukan. Jangan memakai cache/bypass atau mengulang mutasi dengan commit outcome unknown. Acuan: [threading.excepthook](<https://docs.python.org/3.15/library/threading.html#threading.excepthook>) dan [sys.unraisablehook](<https://docs.python.org/3.15/library/sys.html#sys.unraisablehook>).

## Pemeriksaan platform secret store

[Secret store](<../src/api_logistik/security/secret_store.py>) memakai aturan POSIX pada WSL2/container Linux: direktori privat 0700, material key/export 0600, serta pemeriksaan owner, ancestor, dan symlink. Guard `sys.platform == "win32"` membatasi API Windows; utilitas Windows yang tersedia lewat WSL interop tidak dipanggil. Helper ACL menolak panggilan POSIX sebelum memuat DLL.

Mypy 2.4.0 mengenali [platform checks](<https://mypy.readthedocs.io/en/stable/common_issues.html#python-version-and-system-platform-checks>). [ctypes.WinDLL](<https://docs.python.org/3.15/library/ctypes.html#ctypes.WinDLL>) dan [os.path.isreserved](<https://docs.python.org/3.15/library/os.path.html#os.path.isreserved>) hanya tersedia pada Windows; [sys.platform](<https://docs.python.org/3.15/library/sys.html#sys.platform>) untuk Python Linux di WSL2 adalah `linux`. Perbaikan tidak memakai `type: ignore`, menonaktifkan `attr-defined`, atau melonggarkan ACL/permission.

Jalankan mypy default dalam image tes Linux. Target tambahan `mypy --platform win32` hanya memeriksa cabang Windows secara statis, bukan menggantikan uji ACL Windows asli. Fixture Linux tetap offline, tanpa store operator atau Oracle nyata.

## Referensi keputusan

Pembatasan daemon mengikuti [Docker contexts](<https://github.com/docker/docs/blob/main/content/manuals/engine/manage-resources/contexts.md>); bind mount mengacu filesystem daemon, sehingga context remote tidak boleh dipakai untuk profil lokal. Launcher manual memakai [opsi hardening Docker](<https://github.com/docker/docs/blob/main/data/cli/engine/docker_container_create.yaml>) dan [bind mount read-only](<https://github.com/docker/docs/blob/main/content/manuals/engine/storage/bind-mounts.md>) agar operator tidak memerlukan service API. Profil mengikuti [python-dotenv](<https://github.com/theskumar/python-dotenv/blob/main/_autodocs/api-reference/main.md>) dengan interpolasi nonaktif sesuai loader project; serializer diuji round-trip untuk quote, backslash, dollar, whitespace, Unicode, dan newline. Tidak ada credential di contoh command.

Acuan konfigurasi yang dibaca melalui Context7: [Docker multi-stage](<https://docs.docker.com/build/building/multi-stage/>), [Dockerfile](<https://docs.docker.com/reference/dockerfile/>), [Compose services](<https://docs.docker.com/reference/compose-file/services/>), [uv 0.13.5 Docker integration](<https://github.com/astral-sh/uv/blob/0.13.5/docs/guides/integration/docker.md>), dan [FastAPI configuration](<https://fastapi.tiangolo.com/reference/fastapi/>). Multi-stage/non-editable memisahkan runtime dari checkout; COPY allowlist mengecualikan profil privat; loopback publish membatasi eksposur host. Keputusan itu bukan sertifikasi keamanan atau acceptance production.
