# Paket SQL API_LOGISTIK

Target: Oracle Database 19c Enterprise Edition. Delapan file source disiapkan untuk direview dan dijalankan sendiri oleh pengguna/DBA. Agent hanya menjalankan probe berizin yang read-only: pool TCPS, metadata, SELECT dan ekspresi JSON CLOB pada Oracle 19.26/AL32UTF8. Tidak ada DDL, seed, provisioning key atau CRUD tulis yang dijalankan; function belum dikompilasi live.

SQL autentikasi hanya menyediakan metadata, constraint dan baris kontrol; generasi, hash, validasi serta lifecycle key tetap Python. Tidak ada function/procedure auth, package kriptografi atau scheduler Oracle baru. Atas persetujuan pengguna, source tabel/function bisnis fresh-only juga tersedia untuk objek yang belum ada. Source tersebut tidak menimpa atau mengubah objek bisnis existing.

Acuan requirement dan nama objek: [PRD](<../docs/PRD.md>). Tahapan pengerjaan: [rencana implementasi](<../docs/IMPLEMENTATION_PLAN.md>).

## 1. Isi paket dan prefix

| Prefix | File | Dampak |
|---|---|---|
| `Q_` | [Q_VERIFY_EXISTING_OBJECTS.sql](<prechecks/Q_VERIFY_EXISTING_OBJECTS.sql>) | Read-only: konteks koneksi, versi, charset, objek, kolom, constraint, grants, trigger, dan job legacy yang terlihat. Tidak membaca nilai hash atau data karyawan. |
| `Q_` | [Q_VERIFY_API_KEY_STORAGE.sql](<prechecks/Q_VERIFY_API_KEY_STORAGE.sql>) | Read-only sesudah deployment: singleton, pointer/status, jumlah baris menurut status, dan constraint. Tidak membuktikan validasi waktu atau rotasi sudah berjalan. |
| `T_` | [T_KARYAWAN.sql](<schema/T_KARYAWAN.sql>) | Fresh CREATE TABLE bisnis sesuai registry; PK NUMBER(5), kolom teks BYTE. Tidak untuk existing. |
| `F_` | [F_CRUD_KARYAWAN_LOGISTIK.sql](<functions/F_CRUD_KARYAWAN_LOGISTIK.sql>) | Fresh CREATE FUNCTION sesudah tabel bisnis tersedia; signature tetap, helper lokal, tanpa commit/rollback internal. |
| `T_` | [T_API_KEY_AUTH.sql](<schema/T_API_KEY_AUTH.sql>) | Membuat tabel key canonical baru, hanya bila tabel belum ada. |
| `T_` | [T_API_KEY_ROTATION_STATE.sql](<schema/T_API_KEY_ROTATION_STATE.sql>) | Membuat tabel kontrol baru dengan foreign key ke KEY_ID NUMBER pada tabel key. |
| `C_` | [C_API_KEY_AUTH_STATUS.sql](<schema/C_API_KEY_AUTH_STATUS.sql>) | Patch bersyarat untuk constraint legacy bernama CK_API_KEY_AUTH_STATUS agar menerima GRACE. Bukan migrasi schema lengkap. |
| `D_` | [D_INIT_API_KEY_ROTATION_STATE.sql](<seed/D_INIT_API_KEY_ROTATION_STATE.sql>) | MERGE baris GLOBAL yang belum ada, lalu COMMIT. Tidak membuat key dan tidak menimpa state existing. |

Prefix `D_` menandai DML seed, supaya script yang mengubah data tidak disamarkan sebagai Q read-only. Prefix F/P/J tetap tersedia untuk jenis file lain dalam konvensi project, tetapi tidak ada file auth/rotasi jenis tersebut dalam paket baru ini. Direktori lama yang kosong bukan instruksi untuk membuat ulang objek legacy.

## 2. Source bisnis fresh-only

Pemeriksaan owned/visible objects dan synonym terakhir belum menemukan objek project pada schema target. Bila objek tetap belum ada setelah preflight pengguna, terapkan [tabel bisnis](<schema/T_KARYAWAN.sql>) lalu [function CRUD](<functions/F_CRUD_KARYAWAN_LOGISTIK.sql>). CREATE, bukan CREATE OR REPLACE: existing object menyebabkan error dan harus direview, bukan di-drop agar script dapat lanjut.

ID harus bilangan bulat 0 sampai 99999; input API tetap string digit ASCII dan dikonversi ke NUMBER saat bind. Nama/cabang/status nonblank dibatasi 50/30/10 byte; phone 1 sampai 20 digit ASCII, nol depan dipertahankan. Tidak ada enum status baru. Duplicate KRY_001, missing KRY_404, validasi KRY_002 sampai KRY_013, internal KRY_999 tanpa SQLERRM. JSON CLOB menyimpan boolean asli, ID string canonical dan data null pada error. API memanggilnya melalui bound PL/SQL lalu commit/rollback; jangan menjalankan mode DML menggunakan SELECT function FROM DUAL.

Tes source dan probe ekspresi JSON read-only tidak membuktikan compile function, transaksi, concurrency atau hasil CRUD. Periksa ulang signature/compile errors melalui precheck setelah deployment. [Tes sandbox](<../tests/integration/test_oracle_isolated_writes.py>) belum dijalankan dan memerlukan izin terpisah.

## 3. Sebelum menjalankan file

1. Pastikan koneksi, session user, CURRENT_SCHEMA, serta PDB sesuai tujuan. File perubahan memakai nama tabel tanpa schema prefix; jangan mengandalkan tebakan owner atau synonym. Jalankan oleh pemilik schema yang sudah diverifikasi. Referensi lintas schema memerlukan review qualification dan privilege REFERENCES tersendiri.
2. Gunakan sesi admin/setup khusus tanpa transaksi lain yang belum selesai. Oracle DDL melakukan implicit commit, dan file seed mempunyai COMMIT eksplisit. ROLLBACK tidak menjamin mengembalikan perubahan DDL.
3. Aktifkan stop-on-first-error pada client SQL. Tabel/query memakai semicolon; source function berisi PL/SQL dengan terminator slash, sehingga jalankan dalam mode script yang sesuai client. Jangan mengirim slash sebagai bagian statement driver. Oracle DDL dapat meninggalkan function berstatus INVALID: periksa object status dan compile errors.
4. Jalankan [preflight](<prechecks/Q_VERIFY_EXISTING_OBJECTS.sql>) dan review setiap hasil sebelum memilih file perubahan. File Q mengeluarkan result set untuk pemeriksaan operator; tidak memblokir deployment secara otomatis.
5. Jangan menjalankan seluruh folder sekaligus. Tidak ada DROP TABLE, TRUNCATE, pembuatan user/grant otomatis, migrasi data massal, atau pemanggilan bisnis di paket ini.
6. Pastikan writer/job/procedure legacy tidak dapat mengubah key global di luar protokol baru. Query hanya melihat metadata sesuai hak akun; hasil kosong bukan bukti tidak ada writer lain. Pengguna/DBA harus mengonfirmasi kondisi lintas schema dan scheduler eksternal.

Bila salah satu view metadata tidak dapat dibaca, laporkan view yang ditolak dan minta DBA menyediakan hasilnya. Jangan meminta privilege ANY/DBA hanya untuk membuat semua query berhasil. Filter ALL_* sengaja memperlihatkan owner; objek bernama sama pada schema lain tidak boleh disangka target.

## 3. Pilih jalur yang cocok

### A. Schema baru: kedua tabel belum ada

Jalankan hanya langkah yang sudah diizinkan, satu per satu:

1. [T_API_KEY_AUTH.sql](<schema/T_API_KEY_AUTH.sql>).
2. [T_API_KEY_ROTATION_STATE.sql](<schema/T_API_KEY_ROTATION_STATE.sql>).
3. [D_INIT_API_KEY_ROTATION_STATE.sql](<seed/D_INIT_API_KEY_ROTATION_STATE.sql>) pada sesi setup khusus.
4. [Q_VERIFY_API_KEY_STORAGE.sql](<prechecks/Q_VERIFY_API_KEY_STORAGE.sql>) dan ulangi preflight metadata.

Jangan jalankan patch C pada schema canonical baru: constraint tersebut sudah menerima GRACE. Bila CREATE TABLE tidak tersedia, minta DBA menyediakan objek yang sama; jangan menggantinya dengan function, procedure, job, atau storage plaintext.

### B. API_KEY_AUTH sudah ada

Jangan menjalankan file T untuk membuat ulang tabel key. Cocokkan KEY_ID, identity/strategi ID, tipe hash, status, kolom waktu, nullability, serta constraint melalui preflight.

- Canonical baru memakai ACTIVATES_AT dan EXPIRES_AT. Schema legacy mungkin memakai ACTIVE_AT, EXPIRED_AT, dan CLIENT_ID yang wajib terisi. Paket tidak rename kolom atau memindahkan data secara otomatis. Adapter Python legacy harus dipilih dari hasil verifikasi dan membatasi scope global; keberadaannya belum diimplementasikan pada tahap SQL ini.
- Tabel state membutuhkan referensi ke KEY_ID bertipe NUMBER dengan primary/unique key yang sesuai. Bila tipe/layout berbeda, hentikan langkah dan minta keputusan, bukan mengubah tipe tabel bisnis/auth secara otomatis.
- Bila tabel state belum ada dan struktur key sesuai, jalankan definisi tabel state dan seed saja. Bila state sudah ada, jangan membuat atau meresetnya; cocokkan struktur terlebih dahulu.
- [Patch GRACE](<schema/C_API_KEY_AUTH_STATUS.sql>) hanya boleh dipilih bila preflight membuktikan nama/definisi constraint lama cocok dan memang belum menerima GRACE. Semua writer harus berhenti selama maintenance.

Patch C berisi DROP CONSTRAINT lalu ADD dengan nama yang sama dan ENABLE VALIDATE. Keduanya DDL terpisah, bukan transaksi atomik: bila DROP berhasil tetapi ADD gagal, tabel dapat tertinggal tanpa constraint tersebut. Hentikan penulisan, perbaiki penyebabnya, dan terapkan kembali ADD yang sudah direview sebelum membuka akses. Jangan rerun seluruh patch secara buta. Constraint STATUS lain yang masih berlaku juga perlu diperiksa; patch ini tidak menghapusnya.

Perubahan C tidak mengubah raw key, hash existing, waktu, atau status baris. Patch tersebut juga tidak membuktikan schema legacy sepenuhnya siap untuk aplikasi baru.

### C. Tabel kontrol sudah dipakai

Seed aman untuk diulang secara berurutan: MERGE tidak mempunyai WHEN MATCHED UPDATE, sehingga pointer, jadwal, readiness, dan VERSION existing tetap utuh. Seed bukan pengganti protokol runtime row locking dan bukan perintah reset.

Jalankan seed hanya oleh satu operator setup. Dua seed bersamaan dapat bersaing pada primary key; jika salah satunya gagal dengan duplicate key, jangan hapus baris. Setelah transaksi lain selesai, verifikasi singleton dan ulangi seed bila masih diperlukan.

## 4. Schema dan invariant

[Tabel key canonical](<schema/T_API_KEY_AUTH.sql>) berisi KEY_ID identity NUMBER, hash lowercase hex 64 karakter, lima status, dan timestamp dengan timezone. Tidak ada kolom raw key, API key default, atau dummy key bootstrap. PENDING/REVOKED yang belum diaktifkan boleh tidak memiliki waktu aktivasi/expiry; ACTIVE/GRACE wajib memiliki keduanya. Bila kedua waktu tersedia, expiry harus lebih besar dari activation.

[Tabel kontrol](<schema/T_API_KEY_ROTATION_STATE.sql>) berisi satu scope GLOBAL, pointer ACTIVE/GRACE/PENDING, NEXT_ROTATION_AT, PENDING_READY_AT, VERSION, LAST_OPERATION_ID, serta LAST_OPERATION_AT. Constraint mencegah scope lain, versi negatif, readiness tanpa pending, active tanpa jadwal, pasangan operation metadata yang tidak lengkap, pointer identik, dan referensi key yang tidak ada.

DDL tidak dapat membuktikan bahwa status key cocok dengan jenis pointer atau bahwa seluruh writer memperoleh lock. Python wajib membaca ulang state sesudah mengunci singleton, memverifikasi invariant lintas baris, dan mengubah key/pointer/jadwal dalam satu transaksi. Query postcheck memberi tanda BROKEN_REFERENCE atau STATUS_MISMATCH; jangan menafsirkannya sebagai perbaikan otomatis. STATUS_MATCH_ONLY bukan bukti key belum expired.

Batas waktu tetap dihitung Python dari acuan waktu database:

```text
rotation_due    = actual_activation + 7 hari
original_expiry = actual_activation + 8 hari
grace_expiry    = min(original_expiry_lama, activation_baru + 24 jam)
```

Status EXPIRED/REVOKED tidak diaktifkan kembali. File SQL ini tidak mengaktifkan PENDING, mengonfirmasi distribusi, memperpanjang expiry, atau menjadwalkan rotasi. Setelah seed, semua pointer dan jadwal masih kosong; API tidak boleh menganggap sudah ada key valid.

## 5. Matriks akses untuk pemeriksaan pengguna/DBA

| Aktor | Kebutuhan |
|---|---|
| API | CREATE SESSION dan SELECT tabel key/state; privilege bisnis existing sesuai kebutuhan endpoint. |
| Operator Python | SELECT/INSERT/UPDATE tabel key dan SELECT/UPDATE tabel kontrol. |
| Setup/DBA | Hak untuk DDL pada schema tujuan, kebutuhan identity/storage/quota, dan INSERT/UPDATE untuk seed MERGE sesuai privilege Oracle. |

Ownership dan role yang aktif harus diperhitungkan. Tidak terlihatnya grant eksplisit bukan bukti akun pemilik tabel tidak punya akses. Privilege SELECT, bukan hanya READ yang melarang locking, dibutuhkan oleh operator yang memakai SELECT FOR UPDATE. Akses schema lain/FK memerlukan pemeriksaan tambahan; paket tidak memberi GRANT secara otomatis.

Jika schema/privilege belum tersedia, source SQL tetap dapat direview offline, tetapi verifikasi privilege, eksekusi DDL, seed, dan lock/concurrency tetap belum lulus. Tidak perlu mengirim credential atau nilai hash untuk melaporkan hasil precheck.

## 6. Bukti yang perlu dikembalikan

Laporkan secara tersanitasi: owner/schema/PDB yang dituju, versi/RU/charset, grants relevan, bentuk kolom/constraint, script yang dipilih, hasil eksekusi atau kode error, hasil postcheck, serta konfirmasi writer legacy tidak aktif. Jangan kirim password, raw key, hash key, atau data pegawai.

Review statis source bukan bukti Oracle telah mengompilasi atau menjalankan script. Tidak ada pengujian live dalam penyusunan paket ini. DDL/seed yang berhasil juga belum membuktikan auth, locking, expiry, emergency rotation, atau milestone aplikasi selesai.

## 7. Referensi yang diperiksa

- [Oracle 19c: integrity constraints dan ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html), diperiksa melalui Context7.
- [Oracle 19c: MERGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html), diperiksa bersama referensi DML melalui Context7.
- [Oracle 19c: object grants yang diterima](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TAB_PRIVS_RECD.html).
- [Oracle 19c: column grants yang diterima](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_COL_PRIVS_RECD.html).
