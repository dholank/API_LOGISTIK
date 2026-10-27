from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import oracledb
import pytest

from api_logistik.db.api_key_repository import ApiKeyRepository, utc_timestamp
from api_logistik.errors import DatabaseUnavailable, LockBusy
from api_logistik.security.key_rotation import KeyRecord, RotationState

NOW = datetime(2026, 10, 26, 7, tzinfo=UTC)
DIGEST = "a" * 64
STATE_ROW = ("GLOBAL", 1, None, 2, NOW.replace(tzinfo=None), None, 4, None, None)
KEY_ROW = (1, DIGEST, "ACTIVE", NOW.replace(tzinfo=None), NOW, NOW + timedelta(days=8))


class Cursor:
    def __init__(self, rows=(), *, rowcount=1, returning="7", error=None):
        self.rows = list(rows)
        self.rowcount = rowcount
        self.returning = returning
        self.error = error
        self.calls = []
        self.sizes = {}
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute(self, sql, **binds):
        self.calls.append((" ".join(sql.upper().split()), binds))
        if self.error:
            raise self.error

    def fetchmany(self, count):
        assert count == 2
        return self.rows[:count]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def var(self, kind, **kwargs):
        return SimpleNamespace(getvalue=lambda: self.returning)

    def setinputsizes(self, **sizes):
        self.sizes.update(sizes)


class Connection:
    def __init__(self, cursor):
        self.handle = cursor

    def cursor(self):
        return self.handle

    def commit(self):
        pytest.fail("Repository must not commit")

    def rollback(self):
        pytest.fail("Repository must not own transaction rollback")


def repository(rows=(), **kwargs):
    cursor = Cursor(rows, **kwargs)
    return ApiKeyRepository(Connection(cursor)), cursor


def test_lookup_binds_only_digest_and_limits_membership_to_live_pointers():
    repo, cursor = repository([STATE_ROW + KEY_ROW + (NOW.replace(tzinfo=None),)])
    key, state, now = repo.lookup(DIGEST)
    sql, binds = cursor.calls[0]
    assert binds == {"digest": DIGEST}
    assert "K.KEY_HASH = :DIGEST" in sql
    assert "K.KEY_ID IN (S.ACTIVE_KEY_ID, S.GRACE_KEY_ID)" in sql
    assert "WHERE S.SCOPE_ID = 'GLOBAL'" in sql
    assert "SYS_EXTRACT_UTC(SYSTIMESTAMP)" in sql
    assert DIGEST not in sql
    assert key.key_id == state.active_key_id == 1
    assert key.created_at == now == NOW
    assert state.next_rotation_at == NOW
    assert cursor.closed


def test_unmatched_hash_preserves_global_state_and_returns_no_key():
    repo, _ = repository([STATE_ROW + (None,) * 6 + (NOW,)])
    key, state, now = repo.lookup(DIGEST)
    assert key is None
    assert state.version == 4
    assert now == NOW


@pytest.mark.parametrize("rows", [[], [STATE_ROW, STATE_ROW]])
@pytest.mark.parametrize("lock", [False, True])
def test_singleton_is_required_even_for_bootstrap(rows, lock):
    repo, cursor = repository(rows)
    with pytest.raises(DatabaseUnavailable) as error:
        repo.read_state(lock=lock)
    assert error.value.status_code == 503
    assert all(not sql.startswith(("INSERT", "MERGE", "CREATE")) for sql, _ in cursor.calls)


def test_locked_state_uses_bounded_global_row_lock():
    repo, cursor = repository([STATE_ROW])
    assert repo.read_state(lock=True).version == 4
    assert cursor.calls[0][0].endswith("WHERE SCOPE_ID = 'GLOBAL' FOR UPDATE WAIT 5")
    assert "SYS_EXTRACT_UTC(NEXT_ROTATION_AT)" in cursor.calls[0][0]


@pytest.mark.parametrize("code", ["ORA-00054", "ORA-30006"])
def test_oracle_lock_timeout_is_retryable_busy(code):
    error = oracledb.DatabaseError(SimpleNamespace(full_code=code))
    repo, cursor = repository(error=error)
    with pytest.raises(LockBusy):
        repo.read_state(lock=True)
    assert cursor.closed


@pytest.mark.parametrize(
    "method,args",
    [
        ("lookup", (DIGEST,)),
        ("read_state", ()),
        ("database_now", ()),
        ("get_key", (1,)),
        ("find_by_hash", (DIGEST,)),
        ("insert_pending", (DIGEST, NOW, NOW)),
        ("save_key", (KeyRecord(*KEY_ROW[:3], NOW, NOW, NOW + timedelta(days=8)),)),
        ("save_state", (RotationState(), 0)),
    ],
)
def test_backend_errors_are_sanitized_service_unavailability(method, args):
    repo, cursor = repository(error=oracledb.DatabaseError("synthetic-private-dsn"))
    with pytest.raises(DatabaseUnavailable) as error:
        getattr(repo, method)(*args)
    assert error.value.status_code == 503
    assert "synthetic-private-dsn" not in str(error.value)
    assert cursor.closed


@pytest.mark.parametrize("rows", [[], [STATE_ROW + KEY_ROW + (NOW,)] * 2])
def test_auth_lookup_requires_exactly_one_state_row(rows):
    repo, _ = repository(rows)
    with pytest.raises(DatabaseUnavailable):
        repo.lookup(DIGEST)


@pytest.mark.parametrize("value", [None, "2026-10-26", 123])
def test_auth_lookup_requires_database_timestamp(value):
    repo, _ = repository([STATE_ROW + KEY_ROW + (value,)])
    with pytest.raises(DatabaseUnavailable):
        repo.lookup(DIGEST)


def test_utc_conversion_handles_extract_utc_and_aware_driver_values():
    assert utc_timestamp(NOW.replace(tzinfo=None)) == NOW
    assert utc_timestamp(NOW.astimezone(timezone(timedelta(hours=7)))) == NOW
    assert utc_timestamp(None) is None
    with pytest.raises(DatabaseUnavailable):
        utc_timestamp("not-a-timestamp")


@pytest.mark.parametrize("returned", ["7", 7, ["7"], [7]])
def test_insert_pending_handles_scalar_and_array_returning_identifier(returned):
    planned = NOW + timedelta(days=1)
    repo, cursor = repository(returning=returned)
    key = repo.insert_pending(DIGEST, NOW, planned)
    sql, binds = cursor.calls[0]
    assert key == KeyRecord(7, DIGEST, "PENDING", NOW, planned, None)
    assert "RETURNING KEY_ID INTO :IDENTIFIER" in sql
    assert binds["created_at"] == NOW
    assert binds["activates_at"] == planned
    assert cursor.sizes == dict.fromkeys(
        ("created_at", "activates_at"), oracledb.DB_TYPE_TIMESTAMP_TZ
    )


@pytest.mark.parametrize("returned", [None, [], [None], "not-an-id"])
def test_invalid_returning_identifier_fails_closed(returned):
    repo, _ = repository(returning=returned)
    with pytest.raises(DatabaseUnavailable):
        repo.insert_pending(DIGEST, NOW, NOW)


@pytest.mark.parametrize("rowcount", [0, 2, -1])
@pytest.mark.parametrize("method", ["save_key", "save_state"])
def test_optimistic_updates_require_exactly_one_affected_row(rowcount, method):
    repo, _ = repository(rowcount=rowcount)
    with pytest.raises(DatabaseUnavailable):
        if method == "save_state":
            repo.save_state(RotationState(version=5), 4)
        else:
            repo.save_key(KeyRecord(1, DIGEST, "REVOKED", NOW, NOW, None))


def test_save_state_guards_expected_version_and_binds_all_timestamps_as_tstz():
    state = RotationState(
        active_key_id=1,
        next_rotation_at=NOW,
        version=5,
        last_operation_id="test-operation",
        last_operation_at=NOW,
    )
    repo, cursor = repository()
    repo.save_state(state, 4)
    sql, binds = cursor.calls[0]
    assert "WHERE SCOPE_ID = 'GLOBAL' AND VERSION = :EXPECTED" in sql
    assert binds["expected"] == 4 and binds["version"] == 5
    assert binds["active"] == 1 and binds["operation_at"] == NOW
    assert cursor.sizes == dict.fromkeys(
        ("next_at", "ready_at", "operation_at"), oracledb.DB_TYPE_TIMESTAMP_TZ
    )


def test_save_key_binds_identity_digest_and_dates_without_transaction_side_effects():
    repo, cursor = repository()
    key = KeyRecord(1, DIGEST, "GRACE", NOW, NOW, NOW + timedelta(hours=24))
    repo.save_key(key)
    sql, binds = cursor.calls[0]
    assert "WHERE KEY_ID = :IDENTIFIER AND KEY_HASH = :DIGEST" in sql
    assert binds == {
        "status": "GRACE",
        "activates_at": NOW,
        "expires_at": key.expires_at,
        "identifier": 1,
        "digest": DIGEST,
    }
    assert cursor.sizes == dict.fromkeys(
        ("activates_at", "expires_at"), oracledb.DB_TYPE_TIMESTAMP_TZ
    )


def test_null_key_pointer_does_not_query_database():
    repo, cursor = repository()
    assert repo.get_key(None) is None
    assert cursor.calls == []


def test_database_time_comes_from_utc_extracted_server_clock():
    repo, cursor = repository([(NOW.replace(tzinfo=None),)])
    assert repo.database_now() == NOW
    assert cursor.calls == [("SELECT SYS_EXTRACT_UTC(SYSTIMESTAMP) FROM DUAL", {})]
