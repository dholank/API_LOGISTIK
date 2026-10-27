from datetime import UTC, datetime
from typing import Any

import oracledb

from api_logistik.errors import DatabaseUnavailable, LockBusy, driver_error_code
from api_logistik.security.key_rotation import KeyRecord, RotationState

_STATE_COLUMNS = """SCOPE_ID, ACTIVE_KEY_ID, GRACE_KEY_ID, PENDING_KEY_ID,
    SYS_EXTRACT_UTC(NEXT_ROTATION_AT), SYS_EXTRACT_UTC(PENDING_READY_AT), VERSION,
    LAST_OPERATION_ID, SYS_EXTRACT_UTC(LAST_OPERATION_AT)"""
_KEY_COLUMNS = """KEY_ID, KEY_HASH, STATUS, SYS_EXTRACT_UTC(CREATED_AT),
    SYS_EXTRACT_UTC(ACTIVATES_AT), SYS_EXTRACT_UTC(EXPIRES_AT)"""


def utc_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise DatabaseUnavailable()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _state(row: Any) -> RotationState:
    return RotationState(
        scope_id=row[0],
        active_key_id=row[1],
        grace_key_id=row[2],
        pending_key_id=row[3],
        next_rotation_at=utc_timestamp(row[4]),
        pending_ready_at=utc_timestamp(row[5]),
        version=int(row[6]),
        last_operation_id=row[7],
        last_operation_at=utc_timestamp(row[8]),
    )


def _key(row: Any) -> KeyRecord | None:
    if row is None or row[0] is None:
        return None
    created = utc_timestamp(row[3])
    if created is None:
        raise DatabaseUnavailable()
    return KeyRecord(
        key_id=int(row[0]),
        key_hash=row[1],
        status=row[2],
        created_at=created,
        activates_at=utc_timestamp(row[4]),
        expires_at=utc_timestamp(row[5]),
    )


class ApiKeyRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def lookup(self, digest: str) -> tuple[KeyRecord | None, RotationState, datetime]:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """SELECT S.SCOPE_ID, S.ACTIVE_KEY_ID, S.GRACE_KEY_ID, S.PENDING_KEY_ID,
                        SYS_EXTRACT_UTC(S.NEXT_ROTATION_AT), SYS_EXTRACT_UTC(S.PENDING_READY_AT),
                        S.VERSION, S.LAST_OPERATION_ID, SYS_EXTRACT_UTC(S.LAST_OPERATION_AT),
                        K.KEY_ID, K.KEY_HASH, K.STATUS, SYS_EXTRACT_UTC(K.CREATED_AT),
                        SYS_EXTRACT_UTC(K.ACTIVATES_AT), SYS_EXTRACT_UTC(K.EXPIRES_AT),
                        SYS_EXTRACT_UTC(SYSTIMESTAMP)
                    FROM API_KEY_ROTATION_STATE S
                    LEFT JOIN API_KEY_AUTH K ON K.KEY_HASH = :digest
                        AND K.KEY_ID IN (S.ACTIVE_KEY_ID, S.GRACE_KEY_ID)
                    WHERE S.SCOPE_ID = 'GLOBAL'""",
                    digest=digest,
                )
                rows = cursor.fetchmany(2)
                if len(rows) != 1:
                    raise DatabaseUnavailable()
                row = rows[0]
                now = utc_timestamp(row[15])
                if now is None:
                    raise DatabaseUnavailable()
                return _key(row[9:15]), _state(row[:9]), now
        except oracledb.Error, ValueError, TypeError, IndexError:
            raise DatabaseUnavailable() from None

    def read_state(self, *, lock: bool = False) -> RotationState:
        sql = f"SELECT {_STATE_COLUMNS} FROM API_KEY_ROTATION_STATE WHERE SCOPE_ID = 'GLOBAL'"
        if lock:
            sql += " FOR UPDATE WAIT 5"
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchmany(2)
                if len(rows) != 1:
                    raise DatabaseUnavailable()
                return _state(rows[0])
        except oracledb.Error as exc:
            if driver_error_code(exc) in {"ORA-00054", "ORA-30006"}:
                raise LockBusy() from None
            raise DatabaseUnavailable() from None
        except ValueError, TypeError, IndexError:
            raise DatabaseUnavailable() from None

    def database_now(self) -> datetime:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) FROM DUAL")
                value = utc_timestamp(cursor.fetchone()[0])
                if value is None:
                    raise DatabaseUnavailable()
                return value
        except oracledb.Error, ValueError, TypeError, IndexError:
            raise DatabaseUnavailable() from None

    def get_key(self, identifier: int | None) -> KeyRecord | None:
        if identifier is None:
            return None
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_KEY_COLUMNS} FROM API_KEY_AUTH WHERE KEY_ID = :identifier",
                    identifier=identifier,
                )
                return _key(cursor.fetchone())
        except oracledb.Error, ValueError, TypeError, IndexError:
            raise DatabaseUnavailable() from None

    def find_by_hash(self, digest: str) -> KeyRecord | None:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_KEY_COLUMNS} FROM API_KEY_AUTH WHERE KEY_HASH = :digest",
                    digest=digest,
                )
                return _key(cursor.fetchone())
        except oracledb.Error, ValueError, TypeError, IndexError:
            raise DatabaseUnavailable() from None

    def insert_pending(self, digest: str, now: datetime, planned: datetime) -> KeyRecord:
        try:
            with self.connection.cursor() as cursor:
                output = cursor.var(str, size=40)
                cursor.setinputsizes(
                    created_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                    activates_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                )
                cursor.execute(
                    """INSERT INTO API_KEY_AUTH (KEY_HASH, STATUS, CREATED_AT, ACTIVATES_AT)
                    VALUES (:digest, 'PENDING', :created_at, :activates_at)
                    RETURNING KEY_ID INTO :identifier""",
                    digest=digest,
                    created_at=now,
                    activates_at=planned,
                    identifier=output,
                )
                raw = output.getvalue()
                if isinstance(raw, list):
                    raw = raw[0]
                return KeyRecord(int(raw), digest, "PENDING", now, planned, None)
        except oracledb.Error, ValueError, TypeError, IndexError:
            raise DatabaseUnavailable() from None

    def save_key(self, key: KeyRecord) -> None:
        try:
            with self.connection.cursor() as cursor:
                cursor.setinputsizes(
                    activates_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                    expires_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                )
                cursor.execute(
                    """UPDATE API_KEY_AUTH SET STATUS = :status,
                    ACTIVATES_AT = :activates_at, EXPIRES_AT = :expires_at
                    WHERE KEY_ID = :identifier AND KEY_HASH = :digest""",
                    status=key.status,
                    activates_at=key.activates_at,
                    expires_at=key.expires_at,
                    identifier=key.key_id,
                    digest=key.key_hash,
                )
                if cursor.rowcount != 1:
                    raise DatabaseUnavailable()
        except oracledb.Error:
            raise DatabaseUnavailable() from None

    def save_state(self, state: RotationState, expected_version: int) -> None:
        try:
            with self.connection.cursor() as cursor:
                cursor.setinputsizes(
                    next_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                    ready_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                    operation_at=oracledb.DB_TYPE_TIMESTAMP_TZ,
                )
                cursor.execute(
                    """UPDATE API_KEY_ROTATION_STATE SET
                    ACTIVE_KEY_ID = :active, GRACE_KEY_ID = :grace, PENDING_KEY_ID = :pending,
                    NEXT_ROTATION_AT = :next_at, PENDING_READY_AT = :ready_at, VERSION = :version,
                    LAST_OPERATION_ID = :operation, LAST_OPERATION_AT = :operation_at
                    WHERE SCOPE_ID = 'GLOBAL' AND VERSION = :expected""",
                    active=state.active_key_id,
                    grace=state.grace_key_id,
                    pending=state.pending_key_id,
                    next_at=state.next_rotation_at,
                    ready_at=state.pending_ready_at,
                    version=state.version,
                    operation=state.last_operation_id,
                    operation_at=state.last_operation_at,
                    expected=expected_version,
                )
                if cursor.rowcount != 1:
                    raise DatabaseUnavailable()
        except oracledb.Error:
            raise DatabaseUnavailable() from None
