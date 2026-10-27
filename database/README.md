# Paket SQL API_LOGISTIK

Paket ini menargetkan Oracle Database 19c Enterprise Edition. Sembilan file SQL mencakup precheck, schema fresh-only, function bisnis, patch legacy, seed state, dan fixture dummy opsional. [PRD](<../docs/PRD.md>) bagian 15/16 tetap menjadi registry tunggal nama, signature, dan path; tabel berikut hanya panduan pemilihan file.

Pada target FreeSQL pengguna, objek project sudah terlihat VALID. Penambahan 10 dummy, bootstrap key, dan satu siklus CRUD HTTP berizin telah diverifikasi sesuai [acceptance](<../docs/ACCEPTANCE.md>). Hasil itu tidak mengizinkan penerapan ulang DDL atau mutasi lain. Untuk target baru, lakukan preflight lagi.

Oracle menyimpan hash/metadata key dan state transaksi. Python menangani generasi, hashing, validasi, dan lifecycle key; operator menyalurkan key melalui kanal privat. Paket ini tidak membuat routine autentikasi, package kriptografi, atau scheduler Oracle baru. Tahapan pekerjaan ada di [rencana implementasi](<../docs/IMPLEMENTATION_PLAN.md>).

## Isi paket

| Prefix | File | Kapan digunakan |
|---|---|---|
| `Q_` | [Q_VERIFY_EXISTING_OBJECTS.sql](<prechecks/Q_VERIFY_EXISTING_OBJECTS.sql>) | Preflight read-only: koneksi, versi, charset, objek, kolom, constraint, grants, trigger, dan job legacy yang terlihat; tanpa nilai hash atau data karyawan. |
| `Q_` | [Q_VERIFY_API_KEY_STORAGE.sql](<prechecks/Q_VERIFY_API_KEY_STORAGE.sql>) | Verifikasi read-only schema/state, pointer/status, jumlah baris, dan constraint; bukan bukti validasi waktu atau rotasi. |
| `T_` | [T_KARYAWAN.sql](<schema/T_KARYAWAN.sql>) | Fresh CREATE TABLE bisnis dengan PK NUMBER(5) dan kolom teks BYTE; hanya bila tabel belum ada. |
| `F_` | [F_CRUD_KARYAWAN_LOGISTIK.sql](<functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) | Fresh CREATE FUNCTION setelah tabel tersedia; signature tetap, helper lokal, tanpa commit/rollback internal. |
| `T_` | [T_API_KEY_AUTH.sql](<schema/T_API_KEY_AUTH.sql>) | Fresh table hash/metadata key kanonis, hanya bila belum ada. |
| `T_` | [T_API_KEY_ROTATION_STATE.sql](<schema/T_API_KEY_ROTATION_STATE.sql>) | Fresh table kontrol GLOBAL dengan foreign key ke KEY_ID NUMBER. |
| `C_` | [C_API_KEY_AUTH_STATUS.sql](<schema/C_API_KEY_AUTH_STATUS.sql>) | Patch constraint legacy dikenal untuk menambahkan GRACE; bukan migrasi schema lengkap. |
| `D_` | [D_INIT_API_KEY_ROTATION_STATE.sql](<seed/D_INIT_API_KEY_ROTATION_STATE.sql>) | MERGE row GLOBAL yang belum ada, lalu COMMIT; tanpa mint key atau perubahan row existing. |
| `D_` | [D_DUMMY_KARYAWAN.sql](<seed/D_DUMMY_KARYAWAN.sql>) | Fixture opsional: 10 data sintetis melalui function CRUD, tanpa overwrite atau COMMIT otomatis; rollback ke savepoint saat gagal. |

D_ menandai file yang dapat mengubah data, bukan query Q_ read-only. Prefix F/P/J tersedia dalam konvensi PRD, tetapi paket ini tidak menambahkan routine atau job key jenis tersebut. Direktori kosong bukan instruksi untuk membuat ulang objek legacy.

## Source bisnis fresh-only

Jika preflight membuktikan objek bisnis belum ada, terapkan [tabel karyawan](<schema/T_KARYAWAN.sql>) lalu [function CRUD](<functions/F_CRUD_KARYAWAN_LOGISTIK.sql>). Keduanya memakai CREATE, bukan CREATE OR REPLACE. Jika objek sudah ada, hentikan dan review; jangan melakukan DROP agar script dapat lanjut.

Kontrak bisnis:

- ID adalah bilangan bulat 0 sampai 99999. API menerima string digit ASCII maksimal lima digit dan melakukan bind NUMBER untuk tabel `NUMBER(5)`; response menormalkan ID tanpa nol awal.
- Nama/cabang/status wajib tidak kosong dan dibatasi 50/30/10 byte. Target byte-validation adalah AL32UTF8. Python menyaring bentuk dan byte UTF-8; Oracle tetap memvalidasi bisnis.
- Telepon berupa teks 1 sampai 20 digit ASCII agar nol awal tidak hilang. Tidak ada enum status tambahan.
- Duplikat menghasilkan `KRY_001`, data tidak ditemukan `KRY_404`, validasi `KRY_002` sampai `KRY_013`, dan kegagalan internal `KRY_999` tanpa SQLERRM.
- Function mengembalikan JSON CLOB dengan boolean asli, ID string kanonis, dan `data=null` pada error. Pemanggil memakai blok PL/SQL dengan bind, bukan `SELECT function(...) FROM DUAL`, lalu mengelola commit/rollback.

Periksa status objek dan compile errors setelah penerapan. Tes source tidak membuktikan kompilasi, transaksi, atau concurrency. [Suite integrasi sandbox](<../tests/integration/test_oracle_isolated_writes.py>) memerlukan opt-in dan izin terpisah; hasil manual yang sudah tersedia tidak berarti suite tersebut telah dijalankan.

## Prasyarat penerapan

1. Verifikasi target koneksi, session user, CURRENT_SCHEMA, dan PDB. File perubahan memakai nama objek tanpa schema prefix; jalankan sebagai pemilik schema yang sudah dipastikan, bukan lewat asumsi owner atau synonym. Referensi lintas schema memerlukan review qualification dan privilege REFERENCES.
2. Gunakan sesi setup khusus tanpa transaksi lain. Oracle DDL melakukan implicit commit; ROLLBACK tidak mengembalikannya. Seed state GLOBAL mempunyai COMMIT eksplisit, sedangkan fixture dummy harus dijalankan dengan autocommit OFF.
3. Aktifkan stop-on-first-error. Jalankan source PL/SQL dalam mode script dengan terminator slash; jangan mengirim slash sebagai statement driver. DDL dapat meninggalkan function INVALID, sehingga status dan compile errors tetap harus diperiksa.
4. Jalankan [preflight metadata](<prechecks/Q_VERIFY_EXISTING_OBJECTS.sql>) dan review hasilnya sebelum memilih perubahan. Query ini memberi hasil untuk operator, bukan gate yang otomatis menghentikan deployment.
5. Jangan menjalankan seluruh folder. Paket tidak menyediakan DROP TABLE, TRUNCATE, pembuatan user/grant otomatis, atau migrasi massal. Fixture dummy bukan langkah deployment otomatis.
6. Pastikan writer, procedure, atau job legacy tidak mengubah key di luar protokol GLOBAL. Metadata yang terlihat hanya mencakup hak akun; hasil kosong bukan bukti tidak ada writer pada schema lain atau scheduler eksternal.

Jika suatu view tidak dapat dibaca, laporkan nama view dan minta DBA memeriksa. Jangan meminta privilege ANY/DBA hanya agar semua query berhasil. Filter ALL_* memperlihatkan owner agar objek pada schema berbeda tidak disangka target yang sama.

## Jalur penerapan

### A. Schema baru: kedua tabel key belum ada

Setelah izin dan prasyarat terpenuhi, jalankan satu per satu:

1. [T_API_KEY_AUTH.sql](<schema/T_API_KEY_AUTH.sql>)
2. [T_API_KEY_ROTATION_STATE.sql](<schema/T_API_KEY_ROTATION_STATE.sql>)
3. [D_INIT_API_KEY_ROTATION_STATE.sql](<seed/D_INIT_API_KEY_ROTATION_STATE.sql>) pada sesi setup khusus
4. [Q_VERIFY_API_KEY_STORAGE.sql](<prechecks/Q_VERIFY_API_KEY_STORAGE.sql>) dan preflight metadata ulang

Fresh schema sudah menerima GRACE, sehingga tidak membutuhkan patch status legacy. Jika hak CREATE TABLE tidak tersedia, minta DBA menyiapkan objek yang sama; jangan menggantinya dengan routine, job, atau storage plaintext.

### B. API_KEY_AUTH sudah ada

Jangan menjalankan ulang CREATE TABLE. Cocokkan KEY_ID, identity/strategi ID, hash, status, waktu, nullability, dan constraint melalui preflight.

- Schema kanonis memakai `ACTIVATES_AT`/`EXPIRES_AT`. Legacy dapat memakai `ACTIVE_AT`, `EXPIRED_AT`, dan `CLIENT_ID` wajib. Paket tidak mengganti nama atau memindahkan kolom tersebut; adapter/migrasi legacy belum tersedia. Mismatch memerlukan keputusan sebelum runtime kanonis dipakai.
- Tabel state membutuhkan KEY_ID bertipe NUMBER dengan primary/unique key yang sesuai. Jika layout berbeda, hentikan langkah, bukan mengubah tabel bisnis/auth otomatis.
- Jika tabel state belum ada dan struktur key sudah cocok, pilih definisi state dan seed saja. Jika sudah ada, periksa tanpa membuat ulang atau meresetnya.
- [Patch GRACE](<schema/C_API_KEY_AUTH_STATUS.sql>) hanya berlaku bila preflight membuktikan constraint `CK_API_KEY_AUTH_STATUS` cocok dan belum menerima GRACE. Hentikan seluruh writer selama maintenance.

Patch melakukan DROP CONSTRAINT lalu ADD dengan nama sama dan ENABLE VALIDATE. Dua DDL ini tidak atomik. Jika ADD gagal sesudah DROP berhasil, tabel dapat tertinggal tanpa constraint. Hentikan penulisan, perbaiki penyebabnya, dan review ADD sebelum membuka akses kembali. Jangan rerun seluruh patch secara buta atau menghapus constraint STATUS lain yang masih berlaku.

Patch tidak mengubah raw key, hash, waktu, status row, atau nama kolom legacy. Keberhasilannya bukan bukti migrasi lengkap.

### C. Tabel kontrol sudah dipakai

Seed state hanya menambahkan GLOBAL jika hilang. MERGE tidak memiliki WHEN MATCHED UPDATE, sehingga pointer, jadwal, readiness, dan VERSION existing tetap utuh. Ini bukan perintah reset atau pengganti lock runtime.

Gunakan satu operator setup. Dua seed bersamaan dapat bersaing pada primary key. Jika terjadi duplikat, jangan menghapus row; tunggu transaksi lain selesai, verifikasi singleton, lalu ulangi hanya jika masih diperlukan.

### D. Mengisi dummy karyawan (opsional)

[D_DUMMY_KARYAWAN.sql](<seed/D_DUMMY_KARYAWAN.sql>) menyiapkan 10 data sintetis: ID 90001 sampai 90010, nama DUMMY KARYAWAN 01 sampai 10, cabang TRAINING, telepon `0000000001` sampai `0000000010`, dan status AKTIF. Fixture ini bukan data pegawai nyata atau langkah wajib deployment.

Pastikan target schema/PDB, privilege, struktur tabel, serta function VALID dan signature-nya sesuai. Function deployed tidak boleh melakukan commit/rollback internal. ID fixture harus kosong. Gunakan sesi khusus, autocommit OFF, dan stop-on-first-error; hasil metadata tidak otomatis memberi izin tulis.

Dari root project di SQL*Plus/SQLcl:

```sql
@database/seed/D_DUMMY_KARYAWAN.sql
```

Di SQL Developer, buka file yang sama dan gunakan Run Script. Blok PL/SQL diakhiri slash; jangan menjalankan slash sebagai statement driver. Penambahan hanya memakai mode CREATE pada function CRUD. Konflik ID atau kegagalan apa pun menghentikan blok dan me-rollback seluruh penambahan eksekusi itu ke savepoint, tanpa overwrite atau melewati konflik. Rerun setelah COMMIT akan gagal karena duplikat; fixture tidak idempotent.

Jika blok selesai tanpa error, periksa pada sesi yang sama sebelum menyimpan:

```sql
SELECT COUNT(*) AS JUMLAH_DUMMY
FROM KARYAWAN
WHERE ID_KARYAWAN BETWEEN 90001 AND 90010
  AND NAMA = 'DUMMY KARYAWAN ' || TO_CHAR(ID_KARYAWAN - 90000, 'FM00')
  AND CABANG = 'TRAINING'
  AND NO_TELP = '00000000' || TO_CHAR(ID_KARYAWAN - 90000, 'FM00')
  AND STATUS = 'AKTIF';
```

Hasil yang diharapkan adalah 10. Pilih salah satu keputusan setelah review, bukan menjalankan keduanya berurutan.

Simpan:

```sql
COMMIT;
```

Atau batalkan sebelum commit:

```sql
ROLLBACK;
```

File tidak melakukan COMMIT sendiri, tetapi autocommit atau exit client dapat menyimpan transaksi. Setelah commit, ROLLBACK tidak menghapus fixture. Tidak ada cleanup otomatis; pemulihan memerlukan review kepemilikan fixture dan izin terpisah, bukan DELETE berdasarkan rentang ID saja.

Parsing CLOB dan `ON_ERROR(1)` mengikuti [JSON types Oracle 19c](<https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/json-types.html>). SAVEPOINT/ROLLBACK memakai statement PL/SQL langsung, bukan dependency package DBMS_TRANSACTION; semantiknya dijelaskan pada [referensi transaksi Oracle 19c](<https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_TRANSACTION.html>). Source-contract tidak membuktikan rollback live. Eksekusi fixture yang sudah diizinkan beserta batasnya tercatat di [acceptance](<../docs/ACCEPTANCE.md>).

## Schema dan invariant key

[Tabel hash/metadata](<schema/T_API_KEY_AUTH.sql>) memakai KEY_ID identity NUMBER, hash unik lowercase hex 64 karakter, lima status, dan timestamp dengan timezone. Tidak ada raw key, default API Key, atau dummy key bootstrap. PENDING/REVOKED yang belum pernah aktif boleh tidak memiliki waktu aktivasi/expiry; ACTIVE/GRACE wajib memiliki keduanya. Jika kedua waktu terisi, expiry harus sesudah aktivasi.

[Tabel kontrol](<schema/T_API_KEY_ROTATION_STATE.sql>) menyimpan singleton GLOBAL, pointer ACTIVE/GRACE/PENDING, NEXT_ROTATION_AT, PENDING_READY_AT, VERSION, LAST_OPERATION_ID, dan LAST_OPERATION_AT. Constraint menjaga scope, versi nonnegatif, readiness yang terikat pending, jadwal saat active ada, pasangan operation metadata, pointer berbeda, dan referensi key.

Constraint tidak membuktikan status key cocok dengan pointer atau semua writer memakai lock. Python harus mengambil lock GLOBAL, memeriksa invariant lintas row, lalu menyimpan key/state dalam satu transaksi. Konfirmasi readiness wajib cocok dengan kandidat ID dan VERSION di bawah lock yang sama, sebelum aktivasi. Hasil `BROKEN_REFERENCE` atau `STATUS_MISMATCH` dari postcheck adalah temuan, bukan perbaikan otomatis; `STATUS_MATCH_ONLY` bukan bukti key belum expired.

Batas waktu memakai acuan waktu database:

```text
rotation_due    = actual_activation + 7 hari
original_expiry = actual_activation + 8 hari
grace_expiry    = min(original_expiry_lama, activation_baru + 24 jam)
```

Key EXPIRED/REVOKED tidak diaktifkan kembali. Revoke kompromi dapat dilakukan tanpa replacement dengan risiko outage. Aktivasi darurat tetap memerlukan replacement siap dan mencabut seluruh key lama yang live, termasuk GRACE, dalam satu transaksi tanpa bypass.

File SQL tidak mengaktifkan PENDING, mengonfirmasi distribusi, memperpanjang expiry, atau memasang scheduler. Pada schema baru, seed GLOBAL sendiri meninggalkan pointer dan jadwal kosong; bootstrap Python adalah langkah terpisah. Scheduler eksternal tetap semi-otomatis sampai distribusi dan acknowledgment client juga otomatis.

## Hak akses

| Aktor | Kebutuhan |
|---|---|
| API | CREATE SESSION, SELECT metadata key/state, dan privilege bisnis sesuai endpoint/function. |
| Operator Python | SELECT/INSERT/UPDATE tabel key serta SELECT/UPDATE tabel kontrol. |
| Setup/DBA | Hak DDL, kebutuhan identity/storage/quota, dan privilege seed MERGE yang sesuai. |

Perhitungkan ownership dan role aktif. Tidak terlihatnya grant eksplisit bukan bukti pemilik tabel tidak punya akses. Operator yang menjalankan `SELECT FOR UPDATE` membutuhkan SELECT; privilege READ saja melarang locking. Akses lintas schema dan foreign key memerlukan pemeriksaan tambahan. Paket tidak memberikan GRANT otomatis.

## Verifikasi dan pelaporan

Catat target owner/schema/PDB, versi/RU/charset, privilege relevan, bentuk kolom/constraint, file yang dipilih, hasil atau kode error, postcheck, dan konfirmasi writer legacy tidak aktif. Jangan menyertakan password, raw key, hash key, atau data pegawai nyata.

Pisahkan bukti source, kompilasi, transaksi live, dan deployment. DDL atau seed yang berhasil tidak otomatis membuktikan auth, locking, expiry, emergency rotation, atau milestone selesai. Jika privilege/schema belum siap, source tetap dapat direview offline tanpa klaim live lulus. Status terbaru dan gate yang belum selesai ada di [acceptance](<../docs/ACCEPTANCE.md>).

## Referensi

- [Oracle 19c: integrity constraints dan ALTER TABLE](<https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html>)
- [Oracle 19c: MERGE](<https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html>)
- [Oracle 19c: object grants yang diterima](<https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TAB_PRIVS_RECD.html>)
- [Oracle 19c: column grants yang diterima](<https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_COL_PRIVS_RECD.html>)
