import os
import stat
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from api_logistik.security.api_keys import hash_api_key
from api_logistik.security.secret_store import (
    EncryptedFileSecretStore,
    SecretStoreError,
    init_encryption_key,
    read_encryption_key,
)


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        from api_logistik.security import secret_store

        secret_store._restrict(self.base)
        real_check = secret_store._check_directory

        def check_test_directory(path, **kwargs):
            # Host sandbox ancestors are not part of the temporary storage fixture.
            if path == self.base or self.base in path.parents:
                return real_check(path, **kwargs)

        checker = patch.object(secret_store, "_check_directory", side_effect=check_test_directory)
        checker.start()
        self.addCleanup(checker.stop)
        self.master = Fernet.generate_key()
        self.store = EncryptedFileSecretStore(self.base / "ciphertext", self.master)
        self.raw = "a" * 43

    def test_encrypted_roundtrip_and_no_overwrite(self):
        digest = self.store.put(self.raw)
        path = self.store.root / f"{digest}.keyenc"
        original = path.read_bytes()
        self.assertNotIn(self.raw.encode(), original)
        self.assertEqual(self.store.get(digest), self.raw)
        self.assertEqual(self.store.put(self.raw), digest)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.store.root.iterdir()), [path])

    def test_concurrent_put_preserves_one_valid_canonical_file(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            digests = list(pool.map(self.store.put, [self.raw] * 4))
        self.assertEqual(len(set(digests)), 1)
        self.assertEqual(self.store.get(digests[0]), self.raw)
        self.assertEqual(len(list(self.store.root.iterdir())), 1)

    def test_temporary_name_collision_never_deletes_preexisting_file(self):
        from api_logistik.security import secret_store

        collision = self.store.root / ".collision.tmp"
        collision.write_bytes(b"preexisting synthetic material")
        with patch.object(secret_store.uuid, "uuid4") as generate:
            generate.return_value.hex = "collision"
            with self.assertRaises(SecretStoreError):
                self.store.put(self.raw)
        self.assertEqual(collision.read_bytes(), b"preexisting synthetic material")

    def test_untrusted_ancestor_aborts_before_creating_destination(self):
        from api_logistik.security import secret_store

        target = self.base / "never-created.key"
        with patch.object(secret_store, "_check_directory", side_effect=SecretStoreError()):
            with self.assertRaises(SecretStoreError):
                init_encryption_key(target)
        self.assertFalse(target.exists())

    def test_wrong_master_missing_and_tamper_fail_safely(self):
        digest = self.store.put(self.raw)
        wrong = EncryptedFileSecretStore(self.store.root, Fernet.generate_key())
        with self.assertRaises(SecretStoreError):
            wrong.get(digest)
        with self.assertRaises(SecretStoreError):
            self.store.get("f" * 64)
        path = self.store.root / f"{digest}.keyenc"
        path.write_bytes(b"corrupt synthetic ciphertext")
        for method in (self.store.get, lambda value: self.store.put(self.raw)):
            with self.assertRaises(SecretStoreError) as raised:
                method(digest)
            self.assertNotIn(self.raw, str(raised.exception))
        self.assertEqual(path.read_bytes(), b"corrupt synthetic ciphertext")

    def test_decrypted_digest_mismatch_is_rejected(self):
        digest = self.store.put(self.raw)
        path = self.store.root / f"{digest}.keyenc"
        path.write_bytes(Fernet(self.master).encrypt(("b" * 43).encode()))
        with self.assertRaises(SecretStoreError):
            self.store.get(digest)

    def test_secure_export_and_init_never_overwrite(self):
        digest = self.store.put(self.raw)
        destination = self.base / "exported.key"
        self.store.export(digest, destination)
        self.assertEqual(destination.read_text(), self.raw)
        with self.assertRaises(SecretStoreError):
            self.store.export(digest, destination)
        self.assertEqual(destination.read_text(), self.raw)
        master_path = self.base / "master.key"
        init_encryption_key(master_path)
        initial = master_path.read_bytes()
        Fernet(initial)
        with self.assertRaises(SecretStoreError):
            init_encryption_key(master_path)
        self.assertEqual(master_path.read_bytes(), initial)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(master_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.store.root.stat().st_mode), 0o700)

    def test_read_encryption_key_validates_private_material(self):
        path = self.base / "reader-master.key"
        init_encryption_key(path)
        self.assertEqual(read_encryption_key(path), path.read_bytes())
        path.write_bytes(b"invalid synthetic material")
        with self.assertRaises(SecretStoreError):
            read_encryption_key(path)
        with self.assertRaises(SecretStoreError):
            read_encryption_key(self.base / "missing-master.key")
        with self.assertRaises(SecretStoreError):
            read_encryption_key(self.store.root)

    def test_reader_rejects_unsafe_permissions(self):
        path = self.base / "unsafe-master.key"
        init_encryption_key(path)
        if os.name == "nt":
            from api_logistik.security import secret_store

            with patch.object(secret_store, "_check_windows_acl", side_effect=SecretStoreError()):
                with self.assertRaises(SecretStoreError):
                    read_encryption_key(path)
        else:
            path.chmod(0o644)
            with self.assertRaises(SecretStoreError):
                read_encryption_key(path)

    def test_export_refuses_ciphertext_root(self):
        digest = self.store.put(self.raw)
        with self.assertRaises(SecretStoreError):
            self.store.export(digest, self.store.root / "plaintext.key")
        self.assertFalse((self.store.root / "plaintext.key").exists())

    @unittest.skipUnless(os.name == "nt", "Windows reserved destinations")
    def test_reserved_device_and_alternate_stream_destinations_rejected(self):
        digest = self.store.put(self.raw)
        for name in ("CON", "NUL", "synthetic.key:stream", "trailing.key "):
            with self.assertRaises(SecretStoreError):
                self.store.export(digest, self.base / name)

    def test_invalid_digest_and_invalid_raw(self):
        for digest in ("../escape", "", "F" * 64, "a" * 63):
            with self.assertRaises(SecretStoreError):
                self.store.get(digest)
        for raw in ("", "a" * 42, self.raw + "\n"):
            with self.assertRaises(SecretStoreError):
                self.store.put(raw)

    def test_symlinks_never_followed_or_deleted(self):
        target = self.base / "target"
        target.write_bytes(b"unchanged synthetic data")
        link = self.base / "link"
        try:
            link.symlink_to(target)
        except OSError, NotImplementedError:
            self.skipTest("Host does not allow symlink creation.")
        digest = self.store.put(self.raw)
        with self.assertRaises(SecretStoreError):
            self.store.export(digest, link)
        self.assertEqual(target.read_bytes(), b"unchanged synthetic data")
        self.assertTrue(link.is_symlink())
        with self.assertRaises(SecretStoreError):
            EncryptedFileSecretStore(self.base / "through-link" / ".." / "link", self.master)
        malicious = self.store.root / f"{hash_api_key('b' * 43)}.keyenc"
        malicious.symlink_to(target)
        with self.assertRaises(SecretStoreError):
            self.store.put("b" * 43)
        self.assertTrue(malicious.is_symlink())

    @unittest.skipUnless(os.name == "nt", "Windows ACL ordering")
    def test_acl_failure_leaves_empty_file_before_plaintext(self):
        digest = self.store.put(self.raw)
        destination = self.base / "blocked.key"
        from api_logistik.security import secret_store

        real_run = subprocess.run

        def fail_acl(args, **kwargs):
            if args[0].lower() == "icacls.exe":
                self.assertEqual(destination.read_bytes(), b"")
                raise subprocess.CalledProcessError(1, args)
            return real_run(args, **kwargs)

        with patch.object(secret_store.subprocess, "run", side_effect=fail_acl):
            with self.assertRaises(SecretStoreError):
                self.store.export(digest, destination)
        self.assertEqual(destination.read_bytes(), b"")

    @unittest.skipIf(os.name == "nt", "POSIX permission validation")
    def test_untrusted_directory_rejected(self):
        unsafe = self.base / "unsafe"
        unsafe.mkdir(mode=0o777)
        unsafe.chmod(0o777)
        with self.assertRaises(SecretStoreError):
            EncryptedFileSecretStore(unsafe, self.master)
