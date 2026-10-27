import re


class ApplicationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DatabaseUnavailable(ApplicationError):
    def __init__(self) -> None:
        super().__init__("DB_UNAVAILABLE", "Layanan database tidak tersedia", 503)


class DatabaseContractError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("INTERNAL_ERROR", "Terjadi kesalahan internal", 500)


class CommitOutcomeUnknown(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "COMMIT_OUTCOME_UNKNOWN",
            "Hasil transaksi belum dapat dipastikan; lakukan rekonsiliasi sebelum mengulang",
            503,
        )


class AuthenticationRejected(ApplicationError):
    def __init__(self) -> None:
        super().__init__("AUTH_001", "API Key tidak valid atau sudah kedaluwarsa", 401)


class LockBusy(ApplicationError):
    def __init__(self) -> None:
        super().__init__("ROTATION_LOCK_BUSY", "Operasi lain sedang memegang lock rotasi", 503)


class BusinessFailure(ApplicationError):
    pass


class ConfigurationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("CONFIGURATION_ERROR", "Konfigurasi aplikasi tidak valid", 503)


def driver_error_code(exc: Exception) -> str:
    item = exc.args[0] if exc.args else None
    code = getattr(item, "full_code", "")
    return (
        code
        if isinstance(code, str) and re.fullmatch(r"(?:ORA|DPY|DPI)-\d{4,5}", code)
        else "DATABASE_ERROR"
    )


def is_availability_error(exc: Exception) -> bool:
    code = driver_error_code(exc)
    return code.startswith(("DPY-", "DPI-")) or code in {
        "ORA-00028",
        "ORA-01012",
        "ORA-01017",
        "ORA-01033",
        "ORA-01034",
        "ORA-01089",
        "ORA-03113",
        "ORA-03114",
        "ORA-03135",
        "ORA-12154",
        "ORA-12170",
        "ORA-12514",
        "ORA-12516",
        "ORA-12518",
        "ORA-12520",
        "ORA-12535",
        "ORA-12537",
        "ORA-12541",
        "ORA-12543",
        "ORA-12545",
        "ORA-12547",
        "ORA-12560",
        "ORA-12571",
    }
