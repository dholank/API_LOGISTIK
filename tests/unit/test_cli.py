import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import oracledb
import pytest

from api_logistik import cli
from api_logistik.errors import CommitOutcomeUnknown, DatabaseUnavailable, LockBusy
from api_logistik.security.api_keys import hash_api_key
from api_logistik.security.key_rotation import KeyRecord, RotationError, RotationState
from api_logistik.security.secret_store import SecretStoreError

NOW = datetime(2026, 10, 26, 7, tzinfo=UTC)
OP = "11111111-1111-4111-8111-111111111111"
OTHER_OP = "22222222-2222-4222-8222-222222222222"
RAW = "synthetic-test-material-not-a-production-key"
DIGEST = hash_api_key(RAW)


def key(identifier, status="PENDING", *, activated=None, expires=None):
    return KeyRecord(
        identifier,
        DIGEST if identifier == 3 else str(identifier) * 64,
        status,
        NOW - timedelta(days=8),
        activated,
        expires,
    )


class MemoryPool:
    def __init__(self, state=None, keys=()):
        self.state = state or RotationState()
        self.keys = {record.key_id: record for record in keys}
        self.events = []
        self.now = NOW
        self.lock_hook = None
        self.fail_state = False
        self.commit_unknown = False
        self.apply_unknown = False
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.serial = 0
        self.fresh_pools = []

    def fresh_pool(self):
        fresh = MemoryPool(self.state, self.keys.values())
        fresh.now = self.now
        fresh.lock_hook = self.lock_hook
        self.lock_hook = None
        self.fresh_pools.append(fresh)
        return fresh

    @contextmanager
    def connection(self):
        self.serial += 1
        connection = MemoryConnection(self, self.serial)
        self.events.append(("acquire", connection.number))
        try:
            yield connection
        finally:
            self.events.append(("release", connection.number))

    def close(self):
        self.closed = True


class MemoryConnection:
    def __init__(self, pool, number):
        self.pool = pool
        self.number = number
        self.state = pool.state
        self.keys = pool.keys.copy()
        self.locked = False

    def commit(self):
        self.pool.events.append(("commit", self.number))
        self.pool.commits += 1
        if not self.pool.commit_unknown or self.pool.apply_unknown:
            self.pool.state, self.pool.keys = self.state, self.keys.copy()
        self.locked = False
        if self.pool.commit_unknown:
            raise oracledb.DatabaseError("synthetic-commit-outcome-unknown")

    def rollback(self):
        self.pool.events.append(("rollback", self.number))
        self.pool.rollbacks += 1
        self.locked = False


class MemoryRepository:
    def __init__(self, connection):
        self.connection = connection
        self.pool = connection.pool

    def read_state(self, *, lock=False):
        self.pool.events.append(("lock" if lock else "read", self.connection.number))
        if lock:
            self.connection.locked = True
            if self.pool.lock_hook:
                hook, self.pool.lock_hook = self.pool.lock_hook, None
                hook(self.connection)
        return self.connection.state

    def database_now(self):
        self.pool.events.append(("now", self.connection.number))
        return self.pool.now

    def get_key(self, identifier):
        self.pool.events.append(("get_key", identifier))
        return self.connection.keys.get(identifier)

    def find_by_hash(self, digest):
        return next(
            (record for record in self.connection.keys.values() if record.key_hash == digest), None
        )

    def insert_pending(self, digest, now, planned):
        assert self.connection.locked
        self.pool.events.append(("insert", digest))
        identifier = max(self.connection.keys, default=0) + 1
        record = KeyRecord(identifier, digest, "PENDING", now, planned, None)
        self.connection.keys[identifier] = record
        return record

    def save_key(self, record):
        assert self.connection.locked
        self.pool.events.append(("save_key", record.key_id))
        self.connection.keys[record.key_id] = record

    def save_state(self, state, expected_version):
        assert self.connection.locked
        assert self.connection.state.version == expected_version
        self.pool.events.append(("save_state", expected_version))
        if self.pool.fail_state:
            raise DatabaseUnavailable()
        self.connection.state = state


class MemoryStore:
    def __init__(self, pool):
        self.pool = pool
        self.material = {}
        self.on_put = None
        self.on_get = None
        self.exports = []

    def put(self, raw):
        assert raw == RAW
        assert self.pool.events[-1][0] == "release", (
            "Secret must be durable before lock acquisition"
        )
        digest = hash_api_key(raw)
        self.pool.events.append(("store_put", digest))
        self.material[digest] = raw
        if self.on_put:
            self.on_put()
        return digest

    def get(self, digest):
        self.pool.events.append(("store_get", digest))
        if self.on_get:
            self.on_get()
        if digest not in self.material:
            raise SecretStoreError()
        return self.material[digest]

    def export(self, digest, destination):
        self.get(digest)
        self.exports.append((digest, destination))


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(cli, "ApiKeyRepository", MemoryRepository)
    monkeypatch.setattr(cli, "generate_api_key", lambda: RAW)

    def make(state=None, keys=()):
        pool = MemoryPool(state, keys)
        store = MemoryStore(pool)
        store.material[DIGEST] = RAW
        return cli.KeyOperator(pool, store, fresh_pool_factory=pool.fresh_pool), pool, store

    return make


def prepared_state(*, ready=False, active=False, grace=False):
    return RotationState(
        active_key_id=1 if active else None,
        grace_key_id=2 if grace else None,
        pending_key_id=3,
        next_rotation_at=NOW if active else None,
        pending_ready_at=NOW if ready else None,
        version=4,
    )


def test_prepare_stores_material_outside_lock_then_registers_and_commits_once(harness):
    operator, pool, store = harness()
    result = operator.prepare(OP, 0)
    names = [event[0] for event in pool.events]
    assert names.index("store_put") < names.index("lock") < names.index("insert")
    assert result.pending_key_id == 1 and result.version == 1
    assert pool.keys[1].key_hash in store.material
    assert pool.commits == 1 and pool.rollbacks == 0
    before = pool.events.copy()
    assert operator.prepare(OP, 0) == result
    assert pool.commits == 1
    assert not any(event[0] == "store_put" for event in pool.events[len(before) :])


def test_double_prepare_loser_preserves_winner_candidate_readiness_and_version(harness):
    operator, pool, store = harness()
    winner = RotationState(
        pending_key_id=8,
        pending_ready_at=NOW,
        version=2,
        last_operation_id=OTHER_OP,
        last_operation_at=NOW,
    )

    def winner_commits():
        pool.state = winner
        pool.keys[8] = key(8)

    store.on_put = winner_commits
    assert operator.prepare(OP, 0) == winner
    assert pool.state == winner
    assert pool.keys[8].status == "PENDING"
    assert not any(event[0] in {"insert", "save_state", "save_key"} for event in pool.events)
    assert store.material[DIGEST] == RAW


def test_prepare_rechecks_version_after_durable_store_before_insert(harness):
    operator, pool, store = harness()
    store.on_put = lambda: setattr(pool, "state", RotationState(version=1))
    with pytest.raises(RotationError) as error:
        operator.prepare(OP, 0)
    assert error.value.code == "STALE_VERSION"
    assert pool.commits == 0 and pool.rollbacks == 1
    assert pool.keys == {}
    assert store.material[DIGEST] == RAW


def test_prepare_store_failure_never_acquires_mutation_lock(harness, monkeypatch):
    operator, pool, store = harness()

    def unavailable(raw):
        raise SecretStoreError()

    monkeypatch.setattr(store, "put", unavailable)
    with pytest.raises(SecretStoreError):
        operator.prepare(OP, 0)
    assert not any(event[0] == "lock" for event in pool.events)
    assert pool.commits == 0 and pool.keys == {}


def test_pending_candidate_prepare_retry_does_not_reset_distribution(harness):
    state = prepared_state(ready=True)
    operator, pool, _ = harness(state, [key(3)])
    assert operator.prepare(OP, 4) == state
    assert pool.events == [("acquire", 1), ("read", 1), ("release", 1)]
    assert pool.commits == 0


def test_replace_pending_revokes_old_candidate_and_clears_readiness_atomically(harness):
    operator, pool, _ = harness(prepared_state(ready=True), [key(3)])
    pool.keys[3] = replace(pool.keys[3], key_hash="b" * 64)
    state = operator.prepare(OP, 4, replace_pending=True)
    assert state.pending_key_id == 4 and state.pending_ready_at is None
    assert pool.keys[3].status == "REVOKED"
    assert pool.keys[4].status == "PENDING"
    assert state.version > 4
    assert pool.commits == 1


def test_confirm_checks_material_then_locks_exact_candidate_and_version(harness):
    operator, pool, _ = harness(prepared_state(), [key(3)])
    result = operator.confirm(3, 4, OP)
    names = [event[0] for event in pool.events]
    assert names.index("store_get") < names.index("lock") < names.index("save_state")
    assert result.pending_ready_at == NOW and result.version == 5
    assert pool.commits == 1
    assert operator.confirm(3, 4, OP) == result
    assert pool.state.version == 5


@pytest.mark.parametrize(
    "identifier,version,expected", [(9, 4, "CANDIDATE_MISMATCH"), (3, 3, "STALE_VERSION")]
)
def test_confirm_rejects_wrong_candidate_or_stale_version(harness, identifier, version, expected):
    operator, pool, _ = harness(prepared_state(), [key(3), key(9)])
    with pytest.raises(RotationError) as error:
        operator.confirm(identifier, version, OP)
    assert error.value.code == expected
    assert pool.state.pending_ready_at is None and pool.commits == 0


def test_confirm_missing_material_never_marks_readiness(harness):
    operator, pool, store = harness(prepared_state(), [key(3)])
    store.material.clear()
    with pytest.raises(SecretStoreError):
        operator.confirm(3, 4, OP)
    assert pool.state.pending_ready_at is None
    assert pool.commits == 0


@pytest.mark.parametrize("change", ["candidate", "version", "hash"])
def test_confirm_rechecks_state_changed_during_filesystem_read(harness, change):
    operator, pool, store = harness(prepared_state(), [key(3), key(9)])

    def concurrent_change():
        if change == "hash":
            pool.keys[3] = replace(pool.keys[3], key_hash="b" * 64)
        else:
            pool.state = replace(
                pool.state, version=5, pending_key_id=9 if change == "candidate" else 3
            )

    store.on_get = concurrent_change
    with pytest.raises(RotationError):
        operator.confirm(3, 4, OP)
    assert pool.state.pending_ready_at is None
    assert pool.commits == 0 and pool.rollbacks == 1


@pytest.mark.parametrize("emergency", [False, True])
def test_activate_persists_entire_engine_transition_atomically_once(harness, emergency):
    state = prepared_state(ready=True, active=True, grace=emergency)
    active = key(1, "ACTIVE", activated=NOW - timedelta(days=7), expires=NOW + timedelta(days=1))
    grace = key(2, "GRACE", activated=NOW - timedelta(days=7), expires=NOW + timedelta(hours=1))
    operator, pool, _ = harness(state, [active, key(3)] + ([grace] if emergency else []))
    result = operator.activate(4, OP, emergency=emergency)
    assert pool.keys[3].status == "ACTIVE"
    assert pool.keys[3].activates_at == NOW
    assert pool.keys[3].expires_at == NOW + timedelta(days=8)
    assert result.next_rotation_at == NOW + timedelta(days=7)
    assert pool.keys[1].status == ("REVOKED" if emergency else "GRACE")
    if emergency:
        assert pool.keys[2].status == "REVOKED" and result.grace_key_id is None
    assert result.pending_key_id is None and result.pending_ready_at is None
    assert pool.commits == 1
    assert operator.activate(4, OP, emergency=emergency) == result
    assert pool.state.version == 5


@pytest.mark.parametrize("action", ["activate", "revoke"])
def test_failed_state_write_rolls_back_key_updates_and_preserves_material(harness, action):
    state = prepared_state(ready=True)
    operator, pool, store = harness(state, [key(3)])
    pool.fail_state = True
    with pytest.raises(DatabaseUnavailable):
        if action == "activate":
            operator.activate(4, OP)
        else:
            operator.revoke(3, 4, OP)
    assert pool.state == state and pool.keys[3].status == "PENDING"
    assert pool.commits == 0 and pool.rollbacks == 1
    assert store.material[DIGEST] == RAW


def test_revoke_clears_pointer_and_readiness_with_one_commit_and_retry_is_idempotent(harness):
    operator, pool, _ = harness(prepared_state(ready=True), [key(3)])
    result = operator.revoke(3, 4, OP)
    assert result.pending_key_id is None and result.pending_ready_at is None
    assert pool.keys[3].status == "REVOKED" and result.version == 5
    assert pool.commits == 1
    assert operator.revoke(3, 4, OP) == result
    assert pool.state.version == 5


def test_activation_without_distribution_rolls_back_without_reviving_key(harness):
    operator, pool, _ = harness(prepared_state(), [key(3)])
    with pytest.raises(RotationError) as error:
        operator.activate(4, OP, emergency=True)
    assert error.value.code == "NOT_READY"
    assert pool.keys[3].status == "PENDING" and pool.commits == 0


@pytest.mark.parametrize(
    "offset,result,code,has_pending",
    [
        (-timedelta(hours=24, microseconds=1), "NOT_DUE", 0, False),
        (-timedelta(hours=24), "DISTRIBUTION_NOT_CONFIRMED", 2, True),
        (timedelta(0), "DISTRIBUTION_NOT_CONFIRMED", 2, True),
        (timedelta(days=1), "DISTRIBUTION_NOT_CONFIRMED", 2, True),
    ],
)
def test_tick_preparation_window_due_and_hard_expiry_without_readiness(
    harness, offset, result, code, has_pending
):
    activated = NOW - timedelta(days=7)
    active = key(1, "ACTIVE", activated=activated, expires=NOW + timedelta(days=1))
    state = RotationState(active_key_id=1, next_rotation_at=NOW, version=1)
    operator, pool, _ = harness(state, [active])
    pool.now = NOW + offset
    output, exit_code = operator.tick(OP)
    assert (output["result"], exit_code) == (result, code)
    assert (pool.state.pending_key_id is not None) == has_pending
    assert all(
        record.status != "ACTIVE" for identifier, record in pool.keys.items() if identifier != 1
    )
    if offset == timedelta(days=1):
        assert pool.keys[1].status == "EXPIRED" and pool.state.active_key_id is None
        names = [event[0] for event in pool.events]
        assert names.index("save_key") < names.index("store_put")


def test_tick_never_bootstraps_empty_state(harness):
    operator, pool, _ = harness()
    result, code = operator.tick(OP)
    assert (result["result"], code) == ("BOOTSTRAP_REQUIRED", 2)
    assert pool.state == RotationState() and pool.keys == {}
    assert not any(event[0] == "store_put" for event in pool.events)


@pytest.mark.parametrize("before_due", [True, False])
def test_ready_tick_waits_until_due_then_activates(harness, before_due):
    state = prepared_state(ready=True, active=True)
    active = key(1, "ACTIVE", activated=NOW - timedelta(days=7), expires=NOW + timedelta(days=1))
    operator, pool, _ = harness(state, [active, key(3)])
    if before_due:
        pool.now = NOW - timedelta(microseconds=1)
        pool.state = replace(state, pending_ready_at=pool.now)
    result, code = operator.tick(OP)
    assert code == 0
    assert result["result"] == ("WAITING_FOR_DUE" if before_due else "ACTIVATED")
    assert pool.keys[3].status == ("PENDING" if before_due else "ACTIVE")


@pytest.mark.parametrize("applied", [False, True])
def test_commit_unknown_preserves_material_and_reconciliation_locks_before_query(harness, applied):
    operator, pool, store = harness()
    pool.commit_unknown = True
    pool.apply_unknown = applied
    with pytest.raises(CommitOutcomeUnknown):
        operator.prepare(OP, 0)
    assert store.material[DIGEST] == RAW and operator.candidate_key_id == 1
    pool.commit_unknown = False
    start = len(pool.events)
    result = operator.reconcile(OP, 1)
    assert pool.events[start:] == []
    fresh = pool.fresh_pools[-1]
    assert fresh is not pool and fresh.closed
    events = fresh.events
    assert events[0][0] == "acquire" and events[1][0] == "lock"
    assert events[2] == ("get_key", 1)
    assert events[-2][0] == "rollback"
    assert result["original_operation_confirmed"] is applied
    assert result["manual_review_required"] is not applied
    assert store.material[DIGEST] == RAW


def test_reconcile_refreshes_state_under_lock_not_from_prior_status(harness):
    operator, pool, _ = harness()
    operator.status()

    def resolved_transaction(connection):
        connection.state = RotationState(version=2, last_operation_id=OP, last_operation_at=NOW)

    pool.lock_hook = resolved_transaction
    result = operator.reconcile(OP, None)
    assert result["version"] == 2 and result["original_operation_confirmed"]
    assert pool.commits == 0 and pool.rollbacks == 0
    assert pool.fresh_pools[-1].rollbacks == 1
    assert pool.fresh_pools[-1].closed


def test_reconcile_cannot_infer_historic_outcome_from_key_presence(harness):
    state = RotationState(version=9, last_operation_id=OTHER_OP, last_operation_at=NOW)
    operator, _, _ = harness(state, [key(3)])
    result = operator.reconcile(OP, 3)
    assert result["historical_key_found"]
    assert not result["original_operation_confirmed"]
    assert result["manual_review_required"]


@pytest.fixture
def cli_main(monkeypatch, harness):
    operator, pool, store = harness(prepared_state(), [key(3)])
    config = SimpleNamespace(operator_authorized=True, credential="synthetic-credential-canary")
    monkeypatch.setattr(cli, "load_settings", lambda path=None: config)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(cli, "getpass", SimpleNamespace(getuser=lambda: "synthetic-operator"))
    monkeypatch.setattr(cli, "PoolManager", lambda settings, *, writer: pool)
    monkeypatch.setattr(cli, "_store", lambda settings: store)
    return config, operator, pool, store


@pytest.mark.parametrize(
    "exception,exit_code,code",
    [
        (CommitOutcomeUnknown(), 4, "COMMIT_OUTCOME_UNKNOWN"),
        (LockBusy(), 3, "ROTATION_LOCK_BUSY"),
        (RotationError("NOT_READY", "synthetic-private-message"), 2, "NOT_READY"),
        (DatabaseUnavailable(), 1, "DB_UNAVAILABLE"),
        (RuntimeError("synthetic-private-message"), 1, "INTERNAL_ERROR"),
    ],
)
def test_cli_failure_exit_codes_redaction_and_pool_cleanup(
    cli_main, monkeypatch, capsys, caplog, exception, exit_code, code
):
    _, _, pool, _ = cli_main

    def fail(self, *args, **kwargs):
        raise exception

    monkeypatch.setattr(cli.KeyOperator, "activate", fail)
    assert cli.main(["activate", "--expected-version", "4", "--reason", "scheduled"]) == exit_code
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["error_code"] == code and not output["ok"]
    assert pool.closed
    for canary in (RAW, DIGEST, "synthetic-private-message", "synthetic-credential-canary"):
        assert canary not in captured.out + captured.err + caplog.text


@pytest.mark.parametrize(
    "args",
    [
        ["prepare", "--expected-version", "4", "--reason", "scheduled"],
        [
            "confirm-distributed",
            "--key-id",
            "3",
            "--expected-version",
            "4",
            "--reason",
            "distribution_confirmed",
        ],
        ["activate", "--expected-version", "4", "--reason", "scheduled"],
        ["revoke", "--key-id", "3", "--expected-version", "4", "--reason", "key_retired"],
        ["tick"],
        ["export", "--key-id", "3", "--output", "synthetic-private.out"],
        ["init-secret-key", "--output", "synthetic-master.key"],
        ["reconcile", "--operation-id", OP],
    ],
)
def test_cli_requires_authorization_before_any_operator_resource(
    cli_main, monkeypatch, capsys, args
):
    config, _, pool, _ = cli_main
    config.operator_authorized = False

    def forbidden(*args, **kwargs):
        pytest.fail("Unauthorized command accessed operator resource")

    monkeypatch.setattr(cli, "PoolManager", forbidden)
    monkeypatch.setattr(cli, "init_encryption_key", forbidden)
    monkeypatch.setattr(cli, "_store", forbidden)
    assert cli.main(args) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "OPERATOR_AUTHORIZATION_REQUIRED"
    assert pool.events == []


def test_cli_status_does_not_require_write_authorization_or_expose_hash(cli_main, capsys, caplog):
    config, _, pool, _ = cli_main
    config.operator_authorized = False
    assert cli.main(["status"]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["pending_key_id"] == 3
    assert RAW not in output.out + output.err + caplog.text
    assert DIGEST not in output.out + output.err + caplog.text
    assert "synthetic-credential-canary" not in output.out + output.err + caplog.text
    assert pool.commits == 0 and pool.closed


def test_cli_status_exception_message_is_redacted(cli_main, monkeypatch, capsys, caplog):
    def fail(self):
        raise RuntimeError(RAW + " synthetic-credential-canary")

    monkeypatch.setattr(cli.KeyOperator, "status", fail)
    assert cli.main(["status"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["error_code"] == "INTERNAL_ERROR"
    assert RAW not in output.out + output.err + caplog.text
    assert "synthetic-credential-canary" not in output.out + output.err + caplog.text


def test_cli_export_delegates_private_output_to_store_without_printing_material(
    cli_main, capsys, caplog, private_tmp_path
):
    _, _, pool, store = cli_main
    destination = private_tmp_path / "synthetic-private.out"
    assert cli.main(["export", "--key-id", "3", "--output", str(destination)]) == 0
    assert store.exports == [(DIGEST, destination)]
    output = capsys.readouterr()
    assert json.loads(output.out)["result"] == "PRIVATE_EXPORT_CREATED"
    assert RAW not in output.out + output.err + caplog.text
    assert pool.commits == 0


@pytest.mark.parametrize(
    "status,pointer", [("GRACE", "grace_key_id"), ("REVOKED", None), ("EXPIRED", None)]
)
def test_export_refuses_historical_or_non_exportable_key(
    harness, status, pointer, private_tmp_path
):
    state = RotationState(**({pointer: 3} if pointer else {}))
    operator, _, store = harness(state, [key(3, status)])
    with pytest.raises(RotationError) as error:
        operator.export(3, private_tmp_path / "synthetic-private.out")
    assert error.value.code == "EXPORT_NOT_ALLOWED" and store.exports == []


def test_reconcile_default_factory_constructs_and_closes_distinct_pool(harness, monkeypatch):
    _, original, store = harness()
    original.settings = SimpleNamespace(marker="synthetic-settings")
    fresh = MemoryPool(RotationState(version=6))
    calls = []

    def factory(settings, *, writer):
        calls.append((settings, writer))
        return fresh

    monkeypatch.setattr(cli, "PoolManager", factory)
    operator = cli.KeyOperator(original, store)
    result = operator.reconcile(OP, None)
    assert calls == [(original.settings, True)]
    assert result["version"] == 6
    assert original.events == [] and original.commits == 0
    assert fresh.events[1][0] == "lock"
    assert fresh.closed and fresh.rollbacks == 1 and fresh.commits == 0


def test_reconcile_lock_failure_closes_fresh_pool_and_preserves_material(harness):
    operator, original, store = harness()

    def busy(connection):
        raise LockBusy()

    original.lock_hook = busy
    with pytest.raises(LockBusy):
        operator.reconcile(OP, 3)
    fresh = original.fresh_pools[-1]
    assert fresh.closed and fresh.rollbacks == 1
    assert not any(event[0] == "get_key" for event in fresh.events)
    assert original.events == [] and store.material[DIGEST] == RAW


def test_cli_real_prepare_commit_unknown_reports_candidate_and_keeps_material(cli_main, capsys):
    _, _, pool, store = cli_main
    pool.state = RotationState()
    pool.keys.clear()
    pool.commit_unknown = True
    assert cli.main(["prepare", "--expected-version", "0", "--reason", "bootstrap"]) == 4
    result = json.loads(capsys.readouterr().out)
    assert result["error_code"] == "COMMIT_OUTCOME_UNKNOWN"
    assert result["candidate_key_id"] == 1
    assert pool.state.pending_key_id is None
    assert store.material[DIGEST] == RAW and pool.closed


@pytest.mark.parametrize("status", ["EXPIRED", "REVOKED"])
def test_operator_never_revives_terminal_candidate(harness, status):
    operator, pool, _ = harness(prepared_state(ready=True), [key(3, status)])
    with pytest.raises(RotationError):
        operator.activate(4, OP, emergency=True)
    assert pool.keys[3].status == status
    assert pool.commits == 0 and pool.rollbacks == 1


def test_late_tick_expires_old_key_before_activating_ready_successor(harness):
    active = key(1, "ACTIVE", activated=NOW - timedelta(days=7), expires=NOW + timedelta(days=1))
    operator, pool, _ = harness(prepared_state(ready=True, active=True), [active, key(3)])
    pool.now = NOW + timedelta(days=1)
    result, code = operator.tick(OP)
    assert (result["result"], code) == ("ACTIVATED", 0)
    assert pool.keys[1].status == "EXPIRED"
    assert pool.state.active_key_id == 3 and pool.state.grace_key_id is None
    assert pool.keys[3].expires_at == pool.now + timedelta(days=8)
    saves = [event for event in pool.events if event[0] == "save_key"]
    assert saves[0] == ("save_key", 1) and saves[-1] == ("save_key", 3)


def test_cli_emergency_prepare_forces_fresh_pending_replacement(cli_main, monkeypatch, capsys):
    calls = []

    def prepare(self, operation, expected_version, *, replace_pending=False):
        calls.append((expected_version, replace_pending))
        return prepared_state()

    monkeypatch.setattr(cli.KeyOperator, "prepare", prepare)
    assert (
        cli.main(
            [
                "prepare",
                "--expected-version",
                "4",
                "--emergency",
                "--reason",
                "suspected_compromise",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert calls == [(4, True)]


@pytest.fixture
def private_tmp_path(tmp_path):
    resolved = tmp_path.resolve()
    if any(
        (parent / "pyproject.toml").is_file() or (parent / ".git").exists()
        for parent in (resolved, *resolved.parents)
    ):
        pytest.skip(
            "Runner temp is inside a project; use external --basetemp or Docker offline-tests"
        )
    cli._require_outside_project(tmp_path)
    return tmp_path


@pytest.fixture(params=["pyproject.toml", ".git", ".git-directory"])
def project_directory(private_tmp_path, request):
    root = private_tmp_path / "synthetic-project"
    root.mkdir()
    if request.param == ".git-directory":
        (root / ".git").mkdir()
    else:
        (root / request.param).write_text("synthetic project marker", encoding="utf-8")
    return root


def test_export_rejects_project_destination_before_database_or_store(harness, project_directory):
    operator, pool, store = harness(prepared_state(), [key(3)])
    destination = project_directory / "nested" / "private.out"
    with pytest.raises(RotationError) as error:
        operator.export(3, destination)
    assert error.value.code == "PRIVATE_PATH_REQUIRED"
    assert pool.events == [] and store.exports == []
    assert not destination.exists()


def test_cli_init_master_key_rejects_project_destination_before_generation(
    cli_main, monkeypatch, capsys, project_directory
):
    _, _, pool, _ = cli_main
    destination = project_directory / "nested" / "master.key"

    def forbidden(*args, **kwargs):
        pytest.fail("Project destination reached secret generation or database")

    monkeypatch.setattr(cli, "init_encryption_key", forbidden)
    monkeypatch.setattr(cli, "PoolManager", forbidden)
    assert cli.main(["init-secret-key", "--output", str(destination)]) == 2
    assert json.loads(capsys.readouterr().out)["error_code"] == "PRIVATE_PATH_REQUIRED"
    assert pool.events == [] and not destination.exists()


@pytest.mark.parametrize("blocked_component", ["store_root", "master_file"])
def test_store_rejects_project_paths_before_reading_master_or_secret_material(
    monkeypatch, project_directory, private_tmp_path, blocked_component
):
    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe secret path reached material access or store initialization")

    config = SimpleNamespace(
        key_secret_store_dir=(
            project_directory / "nested" / "secrets"
            if blocked_component == "store_root"
            else private_tmp_path / "private-secrets"
        ),
        key_encryption_key_file=(
            project_directory / "nested" / "master.key"
            if blocked_component == "master_file"
            else private_tmp_path / "private-master.key"
        ),
        key_encryption_key=SimpleNamespace(get_secret_value=forbidden),
    )
    monkeypatch.setattr(cli, "read_encryption_key", forbidden)
    monkeypatch.setattr(cli, "EncryptedFileSecretStore", forbidden)
    with pytest.raises(RotationError) as error:
        cli._store(config)
    assert error.value.code == "PRIVATE_PATH_REQUIRED"
    assert not config.key_secret_store_dir.exists()
    assert not config.key_encryption_key_file.exists()
