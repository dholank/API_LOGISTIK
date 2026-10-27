import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import oracledb
import pytest

from api_logistik.cli import KeyOperator
from api_logistik.config import Settings, load_settings
from api_logistik.db.api_key_repository import ApiKeyRepository
from api_logistik.db.pool import PoolManager
from api_logistik.db.transactions import transaction
from api_logistik.errors import driver_error_code
from api_logistik.security.api_keys import hash_api_key

WRITE_ACK = "I_ACKNOWLEDGE_ISOLATED_EMPTY_SCHEMA"
PROJECT = Path(__file__).resolve().parents[2]


def check(condition, code="INTEGRATION_CHECK_FAILED"):
    if not condition:
        pytest.fail(code, pytrace=False)


@contextmanager
def safe_errors():
    try:
        yield
    except Exception as exc:
        code = driver_error_code(exc) if isinstance(exc, oracledb.Error) else "INTEGRATION_FAILED"
        pytest.fail(code, pytrace=False)


def private_settings(monkeypatch, flag, expected):
    if os.environ.get(flag) != expected:
        pytest.skip("Oracle integration requires explicit opt-in")
    supplied = os.environ.get("ORACLE_TEST_ENV_FILE")
    check(bool(supplied), "EXPLICIT_PRIVATE_ENV_FILE_REQUIRED")
    with safe_errors():
        path = Path(supplied)
        check(path.is_absolute(), "ABSOLUTE_PRIVATE_ENV_FILE_REQUIRED")
        path = path.resolve(strict=True)
        check(path.is_file(), "PRIVATE_ENV_FILE_REQUIRED")
        check(path != (PROJECT / ".env").resolve(), "PROJECT_ENV_FILE_FORBIDDEN")
        check(not path.is_relative_to(PROJECT), "ENV_FILE_MUST_BE_OUTSIDE_PROJECT")
        # The opted-in file, not ambient application credentials, selects the test target.
        with monkeypatch.context() as isolated:
            for name in tuple(os.environ):
                if name.lower() in Settings.model_fields:
                    isolated.delenv(name)
            settings = load_settings(path)
        check(
            all((settings.oracle_dsn, settings.oracle_user, settings.oracle_password)),
            "EXPLICIT_TEST_CREDENTIALS_REQUIRED",
        )
        return settings


class MemoryStore:
    """Test double only: this does not prove secure or durable secret storage."""

    def __init__(self, barrier=None):
        self.material = {}
        self.barrier = barrier

    def put(self, raw):
        digest = hash_api_key(raw)
        self.material[digest] = raw
        if self.barrier:
            self.barrier.wait(timeout=15)
        return digest

    def get(self, digest):
        return self.material[digest]


class IsolatedSchema:
    def __init__(self, settings):
        self.settings = settings
        self.pools = []
        self.operators = []
        self.stores = []
        self.operations = set()
        self.employee_ids = {91827}
        marker = uuid.uuid4().hex
        self.employee_names = {label: f"{label}_{marker}" for label in ("IT", "UP", "RB")}
        self.key_ids = set()
        self.initial = None
        self.pool = self.new_pool()

    def new_pool(self):
        pool = PoolManager(self.settings, writer=True)
        self.pools.append(pool)
        return pool

    def operator(self, pool=None, barrier=None):
        store = MemoryStore(barrier)
        operator = KeyOperator(pool or self.pool, store)
        self.stores.append(store)
        self.operators.append(operator)
        return operator, store

    def operation(self):
        value = str(uuid.uuid4())
        self.operations.add(value)
        return value

    def prepare(self, operator, version=None):
        try:
            state = operator.prepare(self.operation(), version)
            if state.pending_key_id:
                self.key_ids.add(state.pending_key_id)
            return state
        finally:
            if operator.candidate_key_id:
                self.key_ids.add(operator.candidate_key_id)

    def bootstrap(self):
        operator, store = self.operator()
        state = self.prepare(operator, self.initial.version)
        identifier = state.pending_key_id
        check(identifier is not None, "BOOTSTRAP_PENDING_REQUIRED")
        state = operator.confirm(identifier, state.version, self.operation())
        state = operator.activate(state.version, self.operation())
        with self.pool.connection() as connection:
            with transaction(connection, write=False):
                key = ApiKeyRepository(connection).get_key(identifier)
                check(key is not None and key.status == "ACTIVE", "BOOTSTRAP_ACTIVE_REQUIRED")
                raw = store.get(key.key_hash)
        return state, raw

    def require_empty(self):
        with self.pool.connection() as connection:
            with transaction(connection, write=False):
                repository = ApiKeyRepository(connection)
                initial = repository.read_state(lock=True)
                check(
                    all(
                        value is None
                        for value in (
                            initial.active_key_id,
                            initial.grace_key_id,
                            initial.pending_key_id,
                            initial.next_rotation_at,
                            initial.pending_ready_at,
                            initial.last_operation_id,
                            initial.last_operation_at,
                        )
                    ),
                    "GLOBAL_MUST_BE_EMPTY",
                )
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM KARYAWAN")
                    check(cursor.fetchone()[0] == 0, "KARYAWAN_MUST_BE_EMPTY")
                    cursor.execute("SELECT COUNT(*) FROM API_KEY_AUTH")
                    check(cursor.fetchone()[0] == 0, "API_KEY_AUTH_MUST_BE_EMPTY")
                    cursor.execute("SELECT COUNT(*) FROM API_KEY_ROTATION_STATE")
                    check(cursor.fetchone()[0] == 1, "ONLY_GLOBAL_ROW_ALLOWED")
                self.initial = initial

    def cleanup(self):
        if self.initial is None:
            return
        for operator in self.operators:
            if operator.candidate_key_id:
                self.key_ids.add(operator.candidate_key_id)
        digests = {digest for store in self.stores for digest in store.material}
        with self.pool.connection() as connection:
            with transaction(connection):
                with connection.cursor() as cursor:
                    # Freeze all three tables before checking ownership or deleting any fixture row.
                    cursor.execute("LOCK TABLE API_KEY_ROTATION_STATE IN EXCLUSIVE MODE NOWAIT")
                    cursor.execute("LOCK TABLE API_KEY_AUTH IN EXCLUSIVE MODE NOWAIT")
                    cursor.execute("LOCK TABLE KARYAWAN IN EXCLUSIVE MODE NOWAIT")
                    cursor.execute("SELECT COUNT(*) FROM API_KEY_ROTATION_STATE")
                    check(cursor.fetchone()[0] == 1, "CLEANUP_REFUSED_FOREIGN_STATE")
                    repository = ApiKeyRepository(connection)
                    state = repository.read_state(lock=True)
                    refs = {
                        value
                        for value in (state.active_key_id, state.grace_key_id, state.pending_key_id)
                        if value is not None
                    }
                    check(refs <= self.key_ids, "CLEANUP_REFUSED_FOREIGN_REFERENCES")
                    check(
                        state.last_operation_id in self.operations | {None},
                        "CLEANUP_REFUSED_FOREIGN_OPERATION",
                    )
                    cursor.execute("SELECT KEY_ID, KEY_HASH FROM API_KEY_AUTH")
                    check(
                        all(
                            row[0] in self.key_ids and row[1] in digests
                            for row in cursor.fetchall()
                        ),
                        "CLEANUP_REFUSED_FOREIGN_KEY",
                    )
                    cursor.execute(
                        "SELECT ID_KARYAWAN, NAMA, CABANG, NO_TELP, STATUS FROM KARYAWAN"
                    )
                    check(
                        all(
                            row[0] in self.employee_ids
                            and row[1] in self.employee_names.values()
                            and row[2] == "Test"
                            and row[3] in {"001234", "0009", "0001"}
                            and row[4] == "AKTIF"
                            for row in cursor.fetchall()
                        ),
                        "CLEANUP_REFUSED_FOREIGN_EMPLOYEE",
                    )
                    repository.save_state(self.initial, state.version)
                    for identifier in self.employee_ids:
                        cursor.execute(
                            "DELETE FROM KARYAWAN WHERE ID_KARYAWAN = :identifier",
                            identifier=identifier,
                        )
                    for identifier in self.key_ids:
                        cursor.execute(
                            "DELETE FROM API_KEY_AUTH WHERE KEY_ID = :identifier",
                            identifier=identifier,
                        )

    def close(self):
        for pool in reversed(self.pools):
            pool.close()


@pytest.fixture
def readonly_oracle(monkeypatch):
    settings = private_settings(monkeypatch, "RUN_ORACLE_READONLY_INTEGRATION", "1")
    pool = PoolManager(settings)
    try:
        yield SimpleNamespace(pool=pool, check=check, safe_errors=safe_errors)
    finally:
        with safe_errors():
            pool.close()


@pytest.fixture
def isolated_oracle(monkeypatch):
    settings = private_settings(monkeypatch, "RUN_ORACLE_WRITE_INTEGRATION", WRITE_ACK)
    check(settings.environment == "test", "WRITE_REQUIRES_TEST_ENVIRONMENT")
    if settings.oracle_writer_user:
        check(
            settings.oracle_writer_user == settings.oracle_user,
            "WRITE_TESTS_REQUIRE_SAME_AUTH_AND_WRITER_SCHEMA",
        )
    rig = IsolatedSchema(settings)
    try:
        with safe_errors():
            rig.require_empty()
        yield SimpleNamespace(rig=rig, check=check, safe_errors=safe_errors)
    finally:
        try:
            with safe_errors():
                rig.cleanup()
        finally:
            with safe_errors():
                rig.close()
