"""Authenticated ciphertext storage and explicit, owner-only secret exports."""

import csv
import io
import os
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .api_keys import hash_api_key, valid_key_format


class SecretStoreError(ValueError):
    def __init__(self, code: str = "SECRET_STORE_ERROR"):
        self.code = code
        self.message = "Secret storage operation failed."
        super().__init__(self.message)


def _windows_sid() -> str:
    result = subprocess.run(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True
    )
    rows = list(csv.reader(io.StringIO(result.stdout)))
    if len(rows) != 1 or len(rows[0]) != 2 or not re.fullmatch(r"S-1-\d+(?:-\d+)+", rows[0][1]):
        raise SecretStoreError()
    return rows[0][1]


def _restrict(path: Path) -> None:
    if os.name == "nt":
        sid = _windows_sid()
        subprocess.run(
            ["icacls.exe", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
            check=True,
            capture_output=True,
        )
        _check_windows_acl(path, private=True)
    else:
        os.chmod(path, 0o700 if path.is_dir() else 0o600, follow_symlinks=False)


def _check_windows_acl(path: Path, *, private: bool) -> None:
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = advapi.GetNamedSecurityInfoW
    get_info.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_info.restype = wintypes.DWORD
    convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.c_void_p,
    ]
    convert.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    descriptor = ctypes.c_void_p()
    text = wintypes.LPWSTR()
    try:
        if get_info(str(path), 1, 5, None, None, None, None, ctypes.byref(descriptor)):
            raise SecretStoreError()
        if not convert(descriptor, 1, 5, ctypes.byref(text), None):
            raise SecretStoreError()
        sddl = text.value
        if not sddl or "NO_ACCESS_CONTROL" in sddl:
            raise SecretStoreError()
        sid = _windows_sid()
        trusted = {sid, "SY", "BA", "CO", "OW", "S-1-3-4", "S-1-5-18", "S-1-5-32-544"}
        owner = re.search(r"O:(.*?)(?=[GDS]:|$)", sddl)
        trusted_installer = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
        if owner is None or owner[1] not in trusted | (
            {trusted_installer} if not private else set()
        ):
            raise SecretStoreError()
        for ace in re.findall(r"\(([^()]*)\)", sddl):
            fields = ace.split(";")
            if len(fields) != 6 or fields[0] not in {"A", "D"}:
                raise SecretStoreError()
            if fields[0] == "D" or fields[5] in trusted or "IO" in fields[1]:
                continue
            rights = fields[2]
            unsafe = any(right in rights for right in ("GA", "GW", "FA", "WD", "WO", "DC"))
            if rights.startswith("0x"):
                unsafe = bool(int(rights, 16) & 0x500D0040)
            if private or unsafe:
                raise SecretStoreError()
    finally:
        if text:
            kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        if descriptor:
            kernel.LocalFree(descriptor)


def _current_uid() -> int:
    if sys.platform == "win32":
        raise SecretStoreError()
    return os.getuid()


def _check_directory(path: Path, *, private: bool = False) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise SecretStoreError()
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise SecretStoreError()
    if os.name == "nt":
        _check_windows_acl(path, private=private)
    else:
        if info.st_uid not in {0, _current_uid()}:
            raise SecretStoreError()
        writable = info.st_mode & 0o022
        trusted_sticky = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (writable and not trusted_sticky) or (private and info.st_mode & 0o077):
            raise SecretStoreError()


def _prepare_directory(path: Path, *, create: bool, private: bool) -> Path:
    if ".." in Path(path).parts:
        raise SecretStoreError()
    if os.name == "nt" and os.path.isreserved(path):
        raise SecretStoreError()
    path = Path(os.path.abspath(path))
    missing = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise SecretStoreError()
        missing.append(current)
        current = current.parent
    for ancestor in reversed((current, *current.parents)):
        _check_directory(ancestor)
    if missing and not create:
        raise SecretStoreError()
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            _check_directory(directory, private=True)
        else:
            _restrict(directory)
    _check_directory(path, private=private)
    return path


def _private_write(destination: Path, payload: bytes) -> None:
    if ".." in Path(destination).parts:
        raise SecretStoreError()
    if os.name == "nt" and os.path.isreserved(destination):
        raise SecretStoreError()
    destination = Path(os.path.abspath(destination))
    _prepare_directory(destination.parent, create=False, private=False)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    fd = os.open(destination, flags, 0o600)
    try:
        # The Windows file stays empty until its inherited ACL has been removed.
        _restrict(destination)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)
    _sync_directory(destination.parent)


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def init_encryption_key(destination: Path) -> None:
    try:
        _private_write(destination, Fernet.generate_key())
    except OSError, ValueError, subprocess.SubprocessError:
        raise SecretStoreError() from None


def read_encryption_key(path: Path) -> bytes:
    try:
        if ".." in Path(path).parts or (os.name == "nt" and os.path.isreserved(path)):
            raise SecretStoreError()
        path = Path(os.path.abspath(path))
        _prepare_directory(path.parent, create=False, private=False)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SecretStoreError()
        if os.name == "nt":
            _check_windows_acl(path, private=True)
        elif info.st_uid != _current_uid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise SecretStoreError()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise SecretStoreError()
            material = stream.read(45)
        if re.fullmatch(rb"[A-Za-z0-9_-]{43}=", material) is None:
            raise SecretStoreError()
        Fernet(material)
        return material
    except OSError, ValueError, TypeError, subprocess.SubprocessError:
        raise SecretStoreError() from None


class EncryptedFileSecretStore:
    def __init__(self, root: Path, encryption_key: bytes):
        try:
            self._fernet = Fernet(encryption_key)
            self.root = _prepare_directory(root, create=True, private=True)
            info = self.root.stat()
            self._identity = (info.st_dev, info.st_ino)
        except OSError, ValueError, TypeError, subprocess.SubprocessError:
            raise SecretStoreError() from None

    def _path(self, digest: str) -> Path:
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SecretStoreError()
        _prepare_directory(self.root, create=False, private=True)
        info = self.root.stat()
        if (info.st_dev, info.st_ino) != self._identity:
            raise SecretStoreError()
        return self.root / f"{digest}.keyenc"

    def put(self, raw_key: str) -> str:
        temporary = None
        created_temporary = False
        try:
            if not valid_key_format(raw_key):
                raise SecretStoreError()
            digest = hash_api_key(raw_key)
            destination = self._path(digest)
            if destination.exists() or destination.is_symlink():
                self.get(digest)
                return digest
            temporary = self.root / f".{uuid.uuid4().hex}.tmp"
            _private_write(temporary, self._fernet.encrypt(raw_key.encode("utf-8")))
            created_temporary = True
            try:
                os.link(temporary, destination)
            except FileExistsError:
                self.get(digest)
            _sync_directory(self.root)
            self.get(digest)
            return digest
        except OSError, ValueError, TypeError, subprocess.SubprocessError:
            raise SecretStoreError() from None
        finally:
            if created_temporary and temporary is not None:
                temporary.unlink()

    def get(self, digest: str) -> str:
        try:
            path = self._path(digest)
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise SecretStoreError()
            fd = os.open(
                path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            )
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
                    raise SecretStoreError()
                raw = self._fernet.decrypt(stream.read(4097)).decode("utf-8")
            if not valid_key_format(raw) or hash_api_key(raw) != digest:
                raise SecretStoreError()
            return raw
        except OSError, ValueError, TypeError, InvalidToken, subprocess.SubprocessError:
            raise SecretStoreError() from None

    def export(self, digest: str, destination: Path) -> None:
        try:
            if ".." in Path(destination).parts:
                raise SecretStoreError()
            if os.name == "nt" and os.path.isreserved(destination):
                raise SecretStoreError()
            target = Path(os.path.abspath(destination))
            if target == self.root or self.root in target.parents:
                raise SecretStoreError()
            _private_write(target, self.get(digest).encode("utf-8"))
        except OSError, ValueError, TypeError, subprocess.SubprocessError:
            raise SecretStoreError() from None
