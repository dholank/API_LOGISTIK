# Status penerimaan API_LOGISTIK

Project belum siap production. Dokumen ini memisahkan bukti source, tes offline, operasi Oracle live berizin, dan pekerjaan yang belum selesai. Requirement mengacu pada [PRD](<PRD.md>) bagian 4, 10, 11, dan 12.

`PASS` berlaku hanya pada pemeriksaan dan lingkungan yang disebutkan. `SOURCE` berarti implementasi tersedia tanpa bukti eksekusi pada gate tersebut; `NOT RUN` berarti belum diuji; `BLOCKED` berarti prasyarat belum tersedia. Build atau tes offline yang lulus tidak menutup acceptance Oracle live maupun production.

## Ringkasan terkini

Snapshot 2 November 2026 mencakup pembaruan pin operator dan verifikasi autentikasi/READ Oracle pada image API baru, zona waktu Asia/Jakarta. CRUD tulis terakhir diuji pada 27 Oktober, cutover tanpa grace pada 29 Oktober, restart/recreate image existing pada 30 Oktober, dan deployment image baru pada 1 November. Bukti setiap tahap dibatasi pada pemeriksaan yang dicatat:

| Area | Bukti terakhir | Batas |
|---|---|---|
| Suite offline Linux Docker | 475 passed, 2 Windows-only skips, 5 integration deselected, 9 subtests passed; coverage Python 88% | Source lokal dengan dependency image tes existing; satu warning TestClient/httpx; bukan suite integrasi Oracle |
| Lint dan format | Ruff check lulus; 50 file sesuai format | Bukan build image rilis atau bukti cutover Oracle |
| Mypy | Linux dan target statis `win32` lulus pada 27 source files | Tidak menggantikan tes ACL Windows asli |
| API dan Oracle | Bootstrap key serta 24 pemeriksaan HTTP setelah aktivasi lulus pada Oracle 19.26/AL32UTF8 | Fixture dan client lokal yang disetujui, bukan production |
| Data fixture | 10 dummy awal tetap cocok; fixture CRUD sementara 91991 sudah dihapus | Tidak mengizinkan mutasi data lain |
| Rotasi manual tanpa grace | KEY_ID 21 ACTIVE, ID 1 REVOKED, GLOBAL VERSION 6; HTTP key baru 200 dan key lama 401 sebelum/sesudah restart | Bukan pengujian normal grace, expiry boundary, atau concurrency/failure |
| Restart API dengan key aktif | Proses berubah pada container/image existing yang sama; metadata Oracle dan material privat tetap, tanpa mint ulang; API kembali berhenti | Bukan recreate container, restart host, atau backup/restore |
| Recreate API dengan key aktif | Container ID baru, image/env/security tetap; 8 pemeriksaan HTTP lulus dan metadata/material key tidak berubah | Bukan upgrade image, restart host, atau restore material |
| Koneksi DB gagal pada sandbox | 10 HTTP checks: enam 503 DB_UNAVAILABLE, dua 401, dua health 200; enam upaya koneksi, nol koneksi/lookup/callback bisnis | Endpoint TCPS loopback tidak terjangkau, bukan pemutusan Oracle aktif atau transaksi berjalan |
| Update image API development, 1 November | Build runtime baru, kecocokan dua modul perbaikan, smoke sandbox, serta 10 HTTP checks pada container baru lulus; API dibiarkan running/healthy | Pada tahap deployment ini belum ada key valid/Oracle atau perubahan pin operator; verifikasi lanjutan dicatat di bawah |
| Pin operator dan auth image baru, 2 November | Launcher memakai image baru; status tetap VERSION 6/key aktif 21; GET dummy memakai key 21 menghasilkan 200 dan key revoked 1 menghasilkan 401; metadata/material tetap | Read-only, tanpa rotasi, CRUD tulis, restart API, atau gate recovery lainnya |
| Operasi lanjutan | Rotasi normal/grace, sesi/query DB putus setelah terhubung, concurrency, TLS client, host recovery/restore, dan p95 belum lengkap | Scheduler/distribusi otomatis belum dipasang atau dibuktikan |

## Pin operator dan autentikasi image baru, 2 November 2026

Pengguna mengizinkan dua langkah: memperbarui pin launcher operator dan memeriksa key aktif/revoked melalui GET read-only. Run `6721f2bf-2c9d-4582-a77a-ee65a6368a3c` selesai **09:23:34 WIB**. API tetap container `0ea6f790b0ca`, image dan waktu start tidak berubah, running/healthy.

Pin privat `operator-image.id` berubah dari `sha256:41925437208e0d49db6179584940c7537ba4390ddf55cb251fcee15675a4d551` ke `sha256:6dea12e211ac05babaf1a1dde7983a2ac870adfe641f09c3cb4b64784bfae403`. File tetap milik operator dengan permission 0600 dan bukan symlink/hardlink. Image lama tetap tersedia sebagai opsi pemulihan pin. Tidak ada build/pull, perubahan profil, atau restart API.

Sebelum perubahan, target/credential API dan profil operator dibandingkan hanya di memori. Path store/master, permission direktori 0700/file 0600, serta hash file package terpasang `cli.py` dan `preflight.py` sesuai. Launcher asli menjalankan `status` memakai image lama, kemudian image baru, dan sekali lagi setelah HTTP: ketiganya lulus, dengan active ID 21, VERSION 6, tanpa PENDING/GRACE/issues. Audit launcher merekam image yang digunakan tanpa nilai key.

| GET | Hasil |
|---|---|
| Health sebelum autentikasi | 200 SUCCESS |
| Fixture dummy 90001 memakai key ACTIVE ID 21 | 200 SUCCESS; seluruh field cocok dengan fixture sintetis |
| Fixture yang sama memakai key REVOKED ID 1 | 401 AUTH_001, data null |
| Health sesudah autentikasi | 200 SUCCESS |

Snapshot dari pool Oracle baru sebelum/sesudah HTTP sama persis untuk seluruh row key dan GLOBAL: dua row key, VERSION 6, status, hash, timestamp, pointer, dan operation metadata tetap. Context schema/PDB sama dan target Oracle 19c/AL32UTF8 terkonfirmasi tanpa menampilkan identitas login atau nilai key. Profil, master, ciphertext, dan delivery identik byte/owner/group/permission; hanya pin serta audit yang berubah.

Metode: container pemeriksaan memakai image runtime yang sama, user operator non-root, filesystem read-only, tmpfs, cap-drop ALL, no-new-privileges, dan root privat di-mount read-only. GET memakai loopback pada network namespace API, tanpa proxy; material key existing didekripsi hanya di memori dan tidak dikirim melalui argv/stdout. Pool snapshot hanya melakukan SELECT dengan autocommit false dan rollback eksplisit. Pemeriksaan log terpisah tanpa jaringan mencocokkan raw key, master, digest, dan credential existing secara privat; tidak ditemukan kebocoran atau traceback. Empat request ID unik ditemukan pada log API. Audit verifikasi tersanitasi disimpan di luar repository dengan permission 0600.

Batas: tidak ada prepare, export, confirm-distributed, activate, revoke, tick, DDL/DML, provisioning, atau tes tulis. Bukti ini menutup pin operator lama dan penolakan/penerimaan key existing pada image baru dalam scope GET; bukan bukti rotasi live pada image baru, normal grace, expiry boundary, concurrency, rollback/unknown commit, outage, TLS, p95, atau host recovery/restore. Suite offline 475 tes dan lima tes integrasi opt-in tidak dijalankan ulang. Acuan transaksi dibaca melalui Context7 untuk [python-oracledb 26.0.1](<https://github.com/oracle/python-oracledb/blob/v26.0.1/doc/src/user_guide/txn_management.rst>).

## Deployment image API development, 1 November 2026

Pengguna mengizinkan update container development. Run `7068ad24-ba48-4b44-b7be-b93570d39362` selesai **17:30:13 WIB**. Container awal `7c4cd3f91018` berstatus Exited (0); container baru `0ea6f790b0ca` bernama `api_logistik-api-1` dibiarkan running/healthy pada `127.0.0.1:8000`.

- Image runtime lama: `sha256:41925437208e0d49db6179584940c7537ba4390ddf55cb251fcee15675a4d551`. Tag lokal rollback: `api-logistik:rollback-api-20261101-7068ad24`; tidak dihapus atau dipakai untuk rollback pada run ini.
- Image runtime baru: `sha256:6dea12e211ac05babaf1a1dde7983a2ac870adfe641f09c3cb4b64784bfae403`, ditag `api-logistik:0.1.0-dev`. `docker --context default compose build api` lulus dengan base digest dan dependency terkunci, instalasi non-editable/nodev.
- Sebelum penerapan, sandbox image baru tanpa mount/credential dan network none meluluskan smoke CLI prepare, preflight dengan cursor/metadata sintetis, serta 10 HTTP checks. Python 3.15.2, FastAPI 0.162.0, Pydantic 2.14.1, dan python-oracledb 26.0.1 cocok dengan manifest. Hash file package terpasang `cli.py` dan `preflight.py` cocok dengan source lokal, baik pada sandbox maupun container hasil deployment. Runtime tidak memuat pytest atau `/app/src`.
- Penerapan memakai `docker --context default compose up --force-recreate --no-build --pull never --no-deps --wait --wait-timeout 90 api`. Konfigurasi Compose dibandingkan dengan environment container lama hanya di memori, tanpa dump nilai privat. Environment, user 10001:10001, root read-only, tmpfs, cap-drop ALL, no-new-privileges, restart policy, healthcheck, port loopback, dan kondisi tanpa mount tetap.
- Sepuluh pemeriksaan HTTP pada container hasil deployment lulus: health/docs/OpenAPI 200; empat method CRUD tanpa key dan malformed key 401; route tidak dikenal 404; method tidak didukung 405. Request ID unik, envelope yang relevan benar, dan seluruh request ID ditemukan pada log container baru. Scan log tidak menemukan nilai credential runtime, canary malformed header, atau traceback.

Batas: tidak ada request dengan key berformat valid pada container berprofil existing, koneksi/probe Oracle oleh agent, DDL/DML, mint/rotasi/revoke key, atau pemasangan scheduler. Penggantian image ini belum membuktikan autentikasi/CRUD Oracle setelah upgrade, persistensi metadata/material key pada image baru, normal grace, recovery host/restore, TLS, atau p95. Suite 475 tes berasal dari tahap perbaikan offline, tidak dijalankan ulang pada tahap deployment ini.

Pin `operator-image.id` dan profil/material operator tidak dibaca atau diubah. Walaupun package dalam image API baru memuat perbaikan prepare/preflight, launcher operator tetap memakai image yang dipin sebelumnya; update pin merupakan operasi terpisah. Acuan build/recreate dibaca melalui Context7: [Compose build](<https://github.com/docker/compose/blob/main/docs/reference/compose_build.md>) dan [Compose up](<https://github.com/docker/compose/blob/main/docs/reference/compose_up.md>).

## Perbaikan prepare dan preflight, 1 November 2026

Perbaikan source menutup dua temuan yang direproduksi offline: prepare menerima VERSION stale saat PENDING sudah ada, dan preflight memberi readiness positif meski metadata kolom/constraint/signature tidak cocok.

- Prepare membaca ulang kandidat existing/retry di bawah lock GLOBAL. Operasi baru memeriksa VERSION sebelum menerima kandidat existing; jalur registrasi concurrent juga memeriksa VERSION sebelum no-op. Retry UUID operasi yang sama tidak menerbitkan kandidat lain. Tes race opt-in kini mensyaratkan satu pemenang dan satu penolakan STALE_VERSION, tetapi belum dijalankan terhadap Oracle.
- Preflight membandingkan metadata dengan kontrak schema kanonis dan melaporkan `schema_issues`. Kolom legacy, constraint disabled/not validated, salah kolom atau referensi key, dan signature tidak cocok menahan readiness serta menghasilkan exit code 2. Cakupan dan pemeriksaan manual yang tetap wajib dijelaskan di [panduan database](<../database/README.md#preflight-python-read-only>).
- Suite offline: 475 passed, 2 skips khusus Windows, 5 integration deselected, 9 subtests passed, coverage Python 88%, satu warning deprecation TestClient/httpx. Ruff check, format 50 file, serta mypy Linux dan target statis win32 pada 27 source files lulus.
- Smoke entrypoint CLI memakai KeyOperator/repository asli dengan cursor sintetis: VERSION stale ditolak exit 2 setelah lock; kandidat existing dengan VERSION cocok dan retry UUID yang sama menghasilkan exit 0 tanpa commit atau perubahan state/material. Preflight CLI menolak gabungan kolom legacy, constraint disabled, dan signature salah dengan exit 2 serta readiness false.
- Proses Uvicorn asli meluluskan 10 pemeriksaan HTTP: health/docs/OpenAPI 200, empat method CRUD tanpa key dan malformed key 401, token sintetis berformat valid tanpa konfigurasi DB 503, serta route tidak dikenal 404. Semua response memiliki request ID; token sintetis dan traceback tidak ditemukan di log smoke.

Metode: image offline-tests existing menyediakan dependency terkunci; source/tests/scripts/database/docs lokal di-mount eksplisit, tanpa profil privat. Tes dan smoke berjalan non-root, filesystem read-only, tmpfs, network none, drop ALL capabilities, dan no-new-privileges. Tidak ada build/pull atau penerapan image API baru.

Batas: cursor/metadata sintetis bukan Oracle live atau bukti locking dua sesi. Tidak ada koneksi Oracle, DDL/DML, provisioning, rotasi, restart container API existing, pemasangan scheduler, atau perubahan privilege. Gate normal grace/concurrency/rollback/unknown commit Oracle, TLS client, restore, p95, dan M3 tetap terbuka. Predicate CHECK, generation identity/default, dan privilege minimum tetap memerlukan review DBA; flag preflight bukan sign-off production.


## Kegagalan koneksi DB pada sandbox, 30 Oktober 2026 (Asia/Jakarta)

Pengguna mengizinkan tes fail-closed berikutnya pada target terisolasi. Run `4b763556-44ce-49e6-aaa2-e33213161da9` selesai **12:39:36 WIB**. Container sementara memakai image API existing, non-root/read-only, `--network none`, tmpfs, drop ALL capabilities, no-new-privileges, tanpa mount atau port publish. HTTP client berjalan melalui docker exec dan loopback langsung tanpa proxy. Sandbox tidak menerima profil, wallet, master key, store, atau credential Oracle asli.

Endpoint TCPS uji menunjuk loopback sandbox port 1; probe socket mengonfirmasi connection refused. Factory `create_app` dan PoolManager/driver python-oracledb asli dipakai dengan identitas dummy berlabel test, pool min/max 1, wait 500 ms, dan connect timeout 1 detik. Tidak ada mock koneksi atau dependency override autentikasi. Harness menambahkan penghitung pass-through pada batas koneksi/factory auth dan guard pada `_execute` bisnis yang akan menaikkan counter serta gagal bila terpanggil. Guard bukan pengganti pembuktian: seluruh counter bisnis wajib nol.

| Pemeriksaan HTTP | Hasil |
|---|---|
| Health sebelum dan sesudah kegagalan | Dua 200 SUCCESS |
| GET tanpa key atau dengan format salah | Dua 401 AUTH_001; sebelum upaya koneksi pertama |
| GET dengan key aktif existing, key revoked existing, atau token acak berformat valid | Tiga 503 DB_UNAVAILABLE |
| POST/PUT/DELETE dengan key berformat valid dan payload sintetis | Tiga 503 DB_UNAVAILABLE |

Sepuluh pemeriksaan menghasilkan request ID unik, envelope konsisten, serta data null pada error. Setelah dua 401, semua counter tetap nol. Setelah enam request berformat valid, counter koneksi = 6, koneksi berhasil = 0, factory repository autentikasi = 0, dan `_execute` bisnis = 0. Jadi function CRUD tidak terpanggil, termasuk untuk tiga HTTP verb tulis pada sandbox. Seluruh request ditemukan pada log sandbox, tanpa raw key, master key, digest key, credential DB asli, atau echo key pada body/header.

Key revoked berformat valid juga menghasilkan 503 pada sandbox karena status Oracle tidak dapat dibaca. Ini bukan key diterima atau dihidupkan kembali. Missing/malformed tetap 401 melalui validasi lokal; saat backend tersedia, penolakan revoked 401 sudah dibuktikan pada tes sebelumnya.

Snapshot Oracle asli dari pool baru sebelum/sesudah sama: dua row key, ID 21 ACTIVE, ID 1 REVOKED, GLOBAL VERSION 6, tanpa PENDING/GRACE; waktu serta LAST_OPERATION_ID tetap. Hash cocok dengan delivery existing tanpa ditampilkan. Material privat identik byte/permission/owner/group. ID, image, konfigurasi, dan seluruh state container API utama tidak berubah; API utama tetap berhenti dan tidak dimulai untuk tes ini. Sandbox berlabel run ID sudah dihapus; audit tersanitasi 0600 tetap di luar repository.

Batas: transport/connect failure sebelum sesi atau query, bukan mematikan Oracle asli, memutus sesi established, gagal query auth setelah acquire berhasil, pool exhaustion, recovery DB, rollback, partial write, atau unknown commit. Belum ada benchmark atau tes opt-in Oracle terisolasi. Tidak ada perubahan source/config/SQL, mint/rotasi key, DDL, function CRUD pada Oracle asli, commit/push Git, atau rerun suite penuh 445 tes.

Acuan: [python-oracledb 26.0.1 connection handling](<https://github.com/oracle/python-oracledb/blob/v26.0.1/doc/src/user_guide/connection_handling.rst>) dan [FastAPI dependency yield](<https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/>). Context7 memiliki driver versi tepat; FastAPI 0.162.0 belum terindeks, sehingga referensi web FastAPI bersifat umum, bukan verifikasi versi. Harness mengikuti factory/dependency existing dan runtime terkunci yang diuji, tanpa mengganti dependency.

## Recreate API dengan key aktif, 30 Oktober 2026 (Asia/Jakarta)

Pengguna mengizinkan penggantian container sebagai kelanjutan tes restart. Run `a2436625-0de9-4fee-ae34-ca97bb979b99` selesai **11:38:21 WIB**. Sebelum perubahan, konfigurasi Compose dirender hanya di memori dan dibandingkan dengan environment container existing serta target operator; tag lokal menunjuk image existing yang sama. Tidak ada dump credential ke terminal atau audit.

API awalnya berhenti. Tes memulai container existing, memeriksa HTTP, lalu memakai `docker compose up --force-recreate --no-build --pull never --wait --wait-timeout 90 api`. Container ID setelah up berbeda; image, environment, port, read-only root, capability/security options, dan tmpfs tetap. Container API tidak menerima mount atau setting operator. Metode mengikuti [referensi Compose up](<https://github.com/docker/docs/blob/main/_vendor/github.com/docker/compose/v5/docs/reference/docker_compose_up.yaml>).

| GET | Sebelum recreate | Sesudah recreate |
|---|---|---|
| Health tanpa key | 200 SUCCESS | 200 SUCCESS |
| READ dummy 90001 dengan key ID 21 | 200 SUCCESS | 200 SUCCESS |
| READ yang sama dengan revoked ID 1 | 401 AUTH_001 | 401 AUTH_001 |
| READ yang sama tanpa key | 401 AUTH_001 | 401 AUTH_001 |

Delapan pemeriksaan lulus dengan request ID unik dan envelope sesuai; hasil READ dummy identik, tanpa mencetak data karyawan. Request memakai loopback langsung tanpa proxy. Log container lama diperiksa sebelum dihapus oleh recreate, lalu log container baru diperiksa setelah tes: seluruh request terkonfirmasi pada container fasenya dan tidak ada raw key lama/baru, master key, digest key, atau credential DB pada body/header/log.

Snapshot dari pool Oracle baru sebelum/sesudah identik: dua row key, ID 21 ACTIVE, ID 1 REVOKED, GLOBAL VERSION 6, LAST_OPERATION_ID/waktu/pointer tetap, tanpa PENDING/GRACE. Hash dua key cocok dengan delivery existing tanpa menampilkan nilainya. Byte, owner, group, dan permission master/profile/pin/store/delivery tetap; tidak ada ciphertext atau key baru. Audit tersanitasi disimpan di luar repository dengan permission 0600.

Setelah tes, container **baru** dihentikan: status akhir Exited (0), sama-sama berhenti seperti kondisi awal. Container lama tidak dipulihkan karena penggantian ID memang tujuan tes. Tidak ada perubahan source/config/SQL, rotasi, DDL, request tulis bisnis, build/pull image, atau commit/push Git.

Batas: image yang sama pada host/daemon yang sama, bukan upgrade image, restart WSL/host, volume/store hilang, backup/restore, outage database, concurrency, expiry boundary, atau p95. Suite offline 445 tes dan lima tes integrasi opt-in tidak dijalankan pada tahap ini. Kelulusan recreate tidak menutup recovery production.

## HTTP key dan restart API, 30 Oktober 2026 (Asia/Jakarta)

Pengguna mengizinkan pengujian prioritas: key baru/lama lewat HTTP dan persistensi setelah restart. API awalnya berhenti. Tes memulai container existing, menjalankan GET read-only, melakukan restart terkontrol, lalu mengembalikan API ke kondisi berhenti. Tidak ada prepare, konfirmasi readiness, aktivasi, revoke, DDL, atau request tulis bisnis.

Run final `b48bafdb-30f8-42b1-a500-bb9ddf94f5fa` selesai **11:15:51 WIB**. Audit tersanitasi disimpan di luar project dengan permission 0600.

| GET | Sebelum restart | Sesudah restart |
|---|---|---|
| `/api/v1/health/live`, tanpa key | 200 SUCCESS | 200 SUCCESS |
| `/api/v1/karyawan/90001`, key aktif ID 21 | 200 SUCCESS | 200 SUCCESS |
| Path yang sama, key revoked ID 1 | 401 AUTH_001, data null | 401 AUTH_001, data null |
| Path yang sama, tanpa key | 401 AUTH_001, data null | 401 AUTH_001, data null |

Delapan pemeriksaan HTTP lulus dengan request ID unik, tanpa echo key pada body/header. Data READ dummy cocok sebelum/sesudah restart dan tidak dicetak ke audit. PID serta StartedAt berubah, sedangkan container ID, image, environment, dan mount tetap. API tetap non-root/read-only tanpa material/setting operator.

Pool Oracle baru sebelum/sesudah memastikan seluruh metadata key/state sama: dua row key, ID 1 REVOKED, ID 21 ACTIVE, GLOBAL VERSION 6, LAST_OPERATION_ID tetap, tanpa PENDING/GRACE. Hash dua row cocok dengan file delivery yang tidak berubah, tanpa menampilkan nilainya. Due tetap 5 November 2026 14:19:28 WIB dan expiry 6 November 2026 14:19:28 WIB. Byte, owner, group, serta permission master/profile/pin/store/delivery tetap; tidak ada key atau ciphertext baru. Scan log API tidak menemukan raw key lama/baru, master key, digest key, atau credential DB.

Metode: `compose start --wait`, `compose restart --timeout 15`, lalu `up --no-recreate --no-build --pull never --wait` untuk menunggu health tanpa mengganti container. Healthcheck tidak dipakai sebagai pengganti tes autentikasi. Acuan: [Compose start](<https://github.com/docker/docs/blob/main/_vendor/github.com/docker/compose/v5/docs/reference/docker_compose_start.yaml>).

Run awal `f7b7ff28-01b0-4f7a-beaa-d729d9244bcc` dihentikan oleh assertion harness yang keliru meminta request ID 36 karakter. [Middleware](<../src/api_logistik/middleware/request_context.py>) memakai `uuid.uuid4().hex`, yaitu 32 karakter. API dikembalikan berhenti setelah run awal, assertion diperbaiki tanpa perubahan aplikasi, kemudian run final di atas lulus. Hasil awal tidak disamarkan sebagai bug API atau kelulusan.

Batas: ini restart proses pada container existing, bukan uji recreating image/container, restart WSL/host, volume hilang, backup/restore, outage DB, concurrency, expiry boundary, atau performa. Tidak ada CRUD tulis atau rotasi baru. Suite offline 445 tes tidak dijalankan ulang pada tahap ini; lima tes integrasi opt-in tetap belum dijalankan. Tidak ada commit/push Git.

## Cutover manual tanpa grace, 29 Oktober 2026 (Asia/Jakarta)

Pengguna meminta key baru serta pemadaman key lama, lalu mengonfirmasi seluruh client siap memakai kandidat ID 21/VERSION 4 setelah menerima file delivery privat. Cutover memakai flag emergency karena tidak boleh ada grace, dengan reason `manual_rotation`; tidak ada klaim insiden kompromi.

- Preflight: GLOBAL VERSION 3, ACTIVE ID 1, tanpa PENDING/GRACE. Prepare melalui launcher menghasilkan kandidat ID 21 dan VERSION 4; export privat 0600 tanpa overwrite, tanpa menampilkan raw key. ID identity tidak diasumsikan berurutan.
- Confirm-distributed mengikat ID 21/VERSION 4 dan menghasilkan VERSION 5. Activate `--emergency` dengan expected VERSION 5 mencabut old live dan mengaktifkan replacement dalam satu transaksi engine/repository existing di bawah lock GLOBAL. Tidak ada SQL autentikasi alternatif atau retry mutasi.
- Commit terkonfirmasi pada VERSION 6, ACTIVE ID 21, tanpa pointer PENDING/GRACE. UUID aktivasi: `c9196157-bd8c-45ad-b142-72fcc526ce3b`.
- Pool Oracle baru memastikan ID 1 berstatus REVOKED dan ID 21 ACTIVE. Lookup hash key lama tidak menemukan record autentikasi yang memenuhi pointer GLOBAL; dependency `require_api_key` menolak key lama dan menerima key baru. Raw key hanya dibaca ke memori dari file privat, bukan dikirim ke Oracle.
- Aktivasi aktual: 29 Oktober 2026 **14:19:28 WIB**. Due berikutnya: **5 November 2026 14:19:28 WIB**; expiry: **6 November 2026 14:19:28 WIB**, sesuai A+7/A+8. Key lama tidak mempunyai grace dan tidak boleh diaktifkan kembali.
- Master key, bootstrap profile, ciphertext existing, serta file delivery lama/baru dipertahankan. Scan calon file publikasi dan audit operator tidak menemukan raw key lama/baru, master key, digest key, atau credential DB. Tidak ada pembacaan/perubahan data karyawan, DDL, perubahan source engine, atau commit/push Git.

Bukti ini adalah satu cutover tanpa grace serta verifikasi dependency autentikasi terhadap Oracle, bukan HTTP 200/401 baru. API tetap berhenti; tidak ada restart, scheduler, atau pengujian outage/rollback/concurrency. Normal grace dan emergency dengan old GRACE masih memerlukan bukti terpisah. File key lama disimpan privat untuk audit, tetapi tidak lagi valid; client harus memakai replacement yang sudah diterima.

## Rotasi manual operator, 29 Oktober 2026 (Asia/Jakarta)

Bagian ini mencatat fase penyiapan launcher sebelum cutover di atas. Pengguna memilih manual terlebih dahulu. [Launcher Bash](<../scripts/api_key_operator.sh>) memanggil CLI existing dalam satu container operator per command, menggunakan image ID immutable dan daemon lokal, tanpa menyalakan API. Tidak ada scheduler, auto-confirm, chaining, retry otomatis, atau perubahan engine/schema. Root privat read-only dengan overlay store/delivery writable; intent/UUID disinkronkan ke audit owner-only sebelum command. Stderr engine dibuang, bukan dicatat mentah.

| Pemeriksaan | Hasil dan batas |
|---|---|
| [Tes launcher](<../tests/unit/test_key_operator_launcher.py>) | 102 kasus lulus: opsi/flag/reason/UUID, audit sebelum Docker, exit code, interrupt INT/TERM, pin immutable, mount, symlink/hardlink/permission, audit gagal, path berspasi, export tanpa overwrite, dan penolakan remote context. Docker dipalsukan melalui executable Python yang dipanggil fungsi Bash agar fixture berjalan pada `/tmp` noexec; ini bukan 102 rotasi live. |
| Build dan suite penuh | Image offline-tests dibangun dengan dependency terkunci. Run non-root/read-only/network none: 445 passed, 2 Windows-only skips, 5 integration deselected, 9 subtests passed, coverage Python 85%, satu warning TestClient/httpx. Coverage tersebut mengukur package Python, bukan branch Bash. |
| Pemeriksaan statis | `bash -n`, Ruff check, Ruff format 49 file, serta mypy Linux dan target statis win32 pada 27 source files lulus. |
| Profil privat | Profil manual baru cocok dengan target koneksi runtime yang disetujui, tanpa shell-source/interpolasi credential. Round-trip quote/backslash/dollar/whitespace/Unicode/newline lulus. Pin image dan profil baru 0600; bootstrap profile lama tidak ditimpa. |
| Smoke Oracle read-only | `status` melalui launcher asli lulus: KEY_ID 1 ACTIVE, VERSION 3, tanpa PENDING/GRACE/issues. Due tetap 3 November 2026 20:19:52 WIB dan expiry 4 November 2026 20:19:52 WIB. Tidak ada prepare/confirm/activate/revoke, pembacaan karyawan, atau penulisan metadata key. |
| Privasi dan preservasi | Scan 77 calon file publikasi, log API, dan audit status tidak menemukan raw key, master key, digest key, atau credential DB. Byte master/ciphertext/delivery dan bootstrap profile lama tetap sama. Source aplikasi, SQL, dependency/lockfile, serta konfigurasi runtime API tidak berubah; container API tetap berhenti. |

Pemeriksaan akhir juga meluluskan 161 tautan/anchor lokal, sintaks contoh Bash/JSON, `git diff --check`, serta 37 source-contract pada dokumen final. Signature/code fence PRD, 12 FR, 16 acceptance requirements, dan tiga milestone tetap terjaga. Jumlah source-contract adalah subset suite, bukan tambahan untuk dijumlahkan.

Gate backend/copy: Hard Gate PASS berdasarkan scan privasi dan preservasi material; Purpose Gate PASS karena launcher memakai CLI/engine existing tanpa service atau schema tambahan; Quality Locks PASS berdasarkan tes/statis/tautan di atas. Liveliness dan pemeriksaan UI tidak berlaku: tidak ada antarmuka atau aset visual yang dibuat, dan tidak ada klaim klik browser.

Batas: setup ini tidak membuktikan cutover normal/darurat Oracle live, concurrency, rollback/unknown commit live, atau kesiapan production. Read-only status bukan tes autentikasi HTTP setelah restart. Tidak ada timer/alert eksternal yang dipasang dan tidak ada staging/commit/push Git. Operator tetap harus menyiapkan distribusi dan menjalankan rotasi sebelum expiry; jadwal tidak diperpanjang oleh mode manual. M3 memerlukan scheduler, pengamanan composite tick setelah hasil tidak pasti, distribusi/ack, monitoring, dan recovery teruji.

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
| FR-002 | Key pada semua endpoint bisnis | CRUD HTTP fixture lulus; GET key 21 diterima dan revoked 1 ditolak sebelum/sesudah restart serta pada image baru 2 November | Expired live dan gate production |
| FR-003 | SHA-256, 401/503, fail-closed | Lookup/auth live; missing/wrong/PENDING/revoked 401; connect-failure sandbox menghasilkan 503 sebelum lookup/bisnis | Sesi/query auth putus setelah koneksi berhasil dan expiry boundary |
| FR-004 | A+7/A+8, readiness/grace | Offline lifecycle, bootstrap, dan cutover tanpa grace/readiness live lulus | Concurrency, normal grace/retry, scheduler/distribusi otomatis |
| FR-005 | CRUD lewat function | Source-contract dan empat mode HTTP Oracle live lulus | Privilege minimum dan target production |
| FR-006 | Empat operasi CRUD | Satu siklus HTTP committed lulus; fixture dibersihkan | Concurrency/failure dan sign-off target |
| FR-007 | Validasi bisnis Oracle | Duplikat 409, missing 404, serta source-contract lulus | Seluruh validasi bisnis Oracle dan failure injection |
| FR-008 | JSON konsisten | Offline, 24 pemeriksaan CRUD HTTP, dan 8 pemeriksaan auth/restart lulus pada tahap terpisah | Sign-off production |
| FR-009 | Error/status | 200/201/401/404/409/422 live dan 503 connect-failure sandbox lulus | 500, putus sesi/query, unknown commit, rollback setelah kegagalan teknis |
| FR-010 | Docker | Build/non-root/HTTP lulus; restart/recreate image existing mempertahankan autentikasi serta metadata/material key; deployment image baru, pin operator, serta auth/READ existing lulus pada 1 dan 2 November | CRUD tulis pada image baru, host recovery/restore, dan production |
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
| 8 | Missing/wrong/PENDING 401; DB failure 503; tanpa CRUD | Penolakan key live; sandbox cold-connect: 503 pada GET/POST/PUT/DELETE, enam upaya koneksi dan nol callback bisnis | Putus sesi/query setelah terhubung, pool exhaustion, serta recovery belum diuji |
| 9 | Expired/revoked ditolak tanpa revival | Offline lulus; revoked ID 1 tetap 401 sebelum/sesudah restart live | Expiry boundary dan state saat scheduler berhenti |
| 10 | A+7/A+8/grace, concurrency/retry, automation | Offline parsial; bootstrap/cutover tanpa grace live; metadata waktu tetap setelah restart | Normal grace/concurrency/retry dan otomasi aktual |
| 11 | Kanal aman dan readiness ID+VERSION/GLOBAL lock | CLI bootstrap serta file privat/client lokal siap lulus; race diuji offline | Kanal production, ack semua penerima, stale candidate/version concurrent live |
| 12 | Grace terbatas, revoke, emergency seluruh old live | Offline lulus; satu cutover tanpa grace live mencabut ACTIVE lama setelah replacement siap | Normal grace dan emergency dengan old GRACE live |
| 13 | Rollback saat DB gagal | Offline lulus; live belum diuji | Failure injection, partial write, unknown commit/reconcile |
| 14 | Restart mempertahankan state key | Restart/recreate image existing lulus. Pada image baru, key 21 tetap 200 dan key 1 tetap 401; snapshot metadata/material selama verifikasi 2 November tetap | Restart host, backup/restore, serta recovery/failure setelah upgrade belum diuji |
| 15 | Swagger/dokumentasi development | Offline/schema dan HTTP container lulus | Interaksi browser; default production-off sudah diuji unit |
| 16 | Credential/key tidak muncul di log/repository | Canary serta scan source/log live lulus dalam scope | Audit artefak/log rilis/proxy lengkap, tanpa mencetak secret |

## Tepat tiga milestone subsystem key

| Milestone | Bukti saat ini | Gate terbuka |
|---|---|---|
| M1 Auth MVP | Fondasi/offline, auth/bootstrap/CRUD live, serta HTTP503 sandbox connect-failure tanpa callback bisnis | Bootstrap concurrent, permission failure, sesi/query auth putus, privilege minimum, dan production |
| M2 Rotation Engine/manual/emergency | Offline lifecycle/rekonsiliasi, 102 kasus launcher, smoke read-only, dan satu cutover tanpa grace beserta penolakan key lama pada Oracle | Concurrency/rollback/unknown commit Oracle serta distribusi nyata; LAST_OPERATION_ID yang tertimpa memerlukan review manual |
| M3 External Automation/distribution/monitoring/recovery | Tick/runbook tersedia; restart/recreate image existing lulus; update image, pin operator, serta auth/READ existing pada image baru lulus | Scheduler aktual, kanal/provider/ack, alert, CRUD tulis pada image baru, host recovery dan restore; automation ditunda |

CRUD, Docker, TLS, pool/worker, privilege minimum, audit dependency/image, backup/restore, dan p95 tetap bagian penerimaan project. Build yang lulus tidak menutup gate tersebut.

## Integrasi opt-in dan verifikasi berikutnya

Lima tes pada [direktori integrasi](<../tests/integration/>) hanya dikoleksi/skip offline, belum dijalankan live. Read-only memerlukan `RUN_ORACLE_READONLY_INTEGRATION=1` dan `ORACLE_TEST_ENV_FILE` absolut di luar project. Writes juga memerlukan `RUN_ORACLE_WRITE_INTEGRATION=I_ACKNOWLEDGE_ISOLATED_EMPTY_SCHEMA`, profil test terpisah, schema/tabel fixture kosong terisolasi, dan izin. Profil runtime project dilarang untuk suite ini. Izin bootstrap/manual HTTP fixture tidak mengaktifkan suite atau memberi izin mutasi lain.

1. Verifikasi target/schema/PDB, privilege, schema canonical, dan sembilan source SQL. Fixture dummy bersifat opsional. [Tabel bisnis](<../database/schema/T_KARYAWAN.sql>) dan [function](<../database/functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) terlihat VALID pada target pengguna tanpa DDL oleh agent; target baru tetap memerlukan preflight/penerapan manual. Mismatch legacy menghentikan deployment.
2. Restart/recreate image existing diuji pada 30 Oktober; deployment image baru pada 1 November serta pin operator dan auth/READ existing pada 2 November juga lulus. CRUD tulis pada image baru, restart host, serta pemulihan/restore tetap memerlukan izin dan bukti terpisah; hasil tersebut tidak menutup seluruh recovery. Image resmi Python tersedia dan dipin digest.
3. Uji integrasi Oracle dengan fixture/cleanup dan izin terpisah. Historical key bukan bukti commit operasi asli; reconcile memakai pool baru dan lock GLOBAL, lalu review manual jika LAST_OPERATION_ID berubah.
4. Uji TLS client/firewall, TCPS, distribusi/readiness/scheduler/alert, dan restore. Ukur p95 pada beban yang disepakati; durasi unit test atau probe koneksi bukan benchmark.
5. Catat waktu/timezone, artefak/digest, command aman, lingkungan, hasil, batas, pemilik, dan sign-off untuk setiap gate. Jangan menandai lulus sebelum bukti tersedia.

## Audit dokumentasi, 27 Oktober 2026

Perapian mencakup sembilan Markdown milik project, termasuk instruksi agent lokal yang tetap diabaikan Git. Pemeriksaan meliputi 151 tautan/anchor lokal, sintaks enam blok Bash dan enam contoh JSON, serta keseimbangan code fence dan whitespace. Signature/contoh SQL PRD, 12 FR, 16 kriteria acceptance, registry path, tiga milestone, contoh JSON API, dan perintah operasional tetap terjaga.

Hash 67 file non-Markdown cocok dengan baseline sebelum penyuntingan. Source-contract terhadap dokumen terbaru menghasilkan 37 passed dalam container non-root/read-only dengan network none. Ini bukan rerun suite penuh atau tes Oracle live. Tidak ada perubahan database, key, kode aplikasi, container API, staging, commit, atau push. URL eksternal tidak diperiksa ulang secara online; pemeriksaan tautan hanya mencakup path dan anchor lokal.
