"""Pure lifecycle decisions; callers serialize and persist each transition atomically."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class KeyRecord:
    key_id: int
    key_hash: str = field(repr=False)
    status: str
    created_at: datetime
    activates_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True)
class RotationState:
    scope_id: str = "GLOBAL"
    active_key_id: int | None = None
    grace_key_id: int | None = None
    pending_key_id: int | None = None
    next_rotation_at: datetime | None = None
    pending_ready_at: datetime | None = None
    version: int = 0
    last_operation_id: str | None = None
    last_operation_at: datetime | None = None


@dataclass(frozen=True)
class Transition:
    state: RotationState
    keys: tuple[KeyRecord, ...]
    changed: bool = True


class RotationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _require(condition: bool, code: str = "INVALID_METADATA") -> None:
    if not condition:
        raise RotationError(
            code,
            {
                "STALE_VERSION": "Rotation version does not match.",
                "PENDING_EXISTS": "A pending candidate already exists.",
                "CANDIDATE_MISMATCH": "Pending candidate does not match.",
                "NOT_READY": "Pending candidate is not ready.",
                "NOT_DUE": "Rotation is not due.",
                "LIVE_GRACE": "A live grace key prevents normal activation.",
                "INVALID_OPERATION": "Operation identifier is invalid.",
            }.get(code, "Key or rotation metadata is inconsistent."),
        )


def _utc(value: datetime) -> bool:
    return isinstance(value, datetime) and value.utcoffset() == timedelta(0)


def _validate_state(state: RotationState, now: datetime) -> None:
    _require(_utc(now))
    _require(state.scope_id == "GLOBAL" and type(state.version) is int and state.version >= 0)
    pointers = (state.active_key_id, state.grace_key_id, state.pending_key_id)
    ids = [value for value in pointers if value is not None]
    _require(all(type(value) is int and value > 0 for value in ids))
    _require(len(ids) == len(set(ids)))
    _require(state.next_rotation_at is None or _utc(state.next_rotation_at))
    for value in (state.pending_ready_at, state.last_operation_at):
        _require(value is None or (_utc(value) and value <= now))
    _require(state.pending_ready_at is None or state.pending_key_id is not None)
    _require(state.active_key_id is None or state.next_rotation_at is not None)
    _require((state.last_operation_id is None) == (state.last_operation_at is None))


def _validate_key(key: KeyRecord, now: datetime) -> None:
    _require(type(key.key_id) is int and key.key_id > 0)
    _require(
        isinstance(key.key_hash, str) and re.fullmatch(r"[0-9a-f]{64}", key.key_hash) is not None
    )
    _require(
        isinstance(key.status, str)
        and key.status in {"PENDING", "ACTIVE", "GRACE", "EXPIRED", "REVOKED"}
    )
    _require(_utc(key.created_at) and key.created_at <= now)
    for value in (key.activates_at, key.expires_at):
        _require(value is None or _utc(value))
    if key.activates_at is not None:
        _require(key.created_at <= key.activates_at)
    if key.activates_at is not None and key.expires_at is not None:
        _require(key.activates_at < key.expires_at)
    if key.status in {"ACTIVE", "GRACE"}:
        _require(key.activates_at is not None and key.expires_at is not None)
        assert key.activates_at is not None and key.expires_at is not None
        _require(key.activates_at <= now)
        _require(key.expires_at <= key.activates_at + timedelta(days=8))


_NO_VERSION = object()


def _guard(
    state: RotationState,
    now: datetime,
    operation_id: str,
    expected_version: object = _NO_VERSION,
) -> Transition | None:
    _validate_state(state, now)
    _require(
        isinstance(operation_id, str)
        and 1 <= len(operation_id) <= 64
        and re.fullmatch(r"[A-Za-z0-9_.:-]+", operation_id) is not None,
        "INVALID_OPERATION",
    )
    if operation_id == state.last_operation_id:
        return Transition(state, (), False)
    if expected_version is not _NO_VERSION:
        _require(
            type(expected_version) is int and expected_version == state.version, "STALE_VERSION"
        )
    return None


def _finish(
    state: RotationState,
    keys: Iterable[KeyRecord],
    now: datetime,
    operation_id: str,
    **changes: Any,
) -> Transition:
    return Transition(
        replace(
            state,
            version=state.version + 1,
            last_operation_id=operation_id,
            last_operation_at=now,
            **changes,
        ),
        tuple(keys),
    )


def _candidate(state: RotationState, pending: KeyRecord, now: datetime) -> None:
    _validate_key(pending, now)
    _require(state.pending_key_id == pending.key_id, "CANDIDATE_MISMATCH")
    _require(pending.status == "PENDING")
    _require(pending.expires_at is None or pending.expires_at > now)


def attach_pending(
    state: RotationState, key: KeyRecord, now: datetime, operation_id: str, expected_version: int
) -> Transition:
    if retry := _guard(state, now, operation_id, expected_version):
        return retry
    _validate_key(key, now)
    _require(state.pending_key_id is None, "PENDING_EXISTS")
    _require(key.status == "PENDING")
    _require(key.key_id not in (state.active_key_id, state.grace_key_id))
    _require(key.expires_at is None or key.expires_at > now)
    return _finish(
        state, (key,), now, operation_id, pending_key_id=key.key_id, pending_ready_at=None
    )


def confirm_ready(
    state: RotationState,
    pending: KeyRecord,
    now: datetime,
    operation_id: str,
    expected_version: int,
) -> Transition:
    if retry := _guard(state, now, operation_id, expected_version):
        return retry
    _candidate(state, pending, now)
    return _finish(state, (), now, operation_id, pending_ready_at=now)


def _prior(record: KeyRecord | None, pointer: int | None, status: str, now: datetime) -> None:
    _require((record is None) == (pointer is None))
    if record is not None:
        _validate_key(record, now)
        _require(record.key_id == pointer and record.status in {status, "EXPIRED", "REVOKED"})


def _live(record: KeyRecord | None, now: datetime) -> bool:
    return (
        record is not None
        and record.status in {"ACTIVE", "GRACE"}
        and record.activates_at is not None
        and record.expires_at is not None
        and record.activates_at <= now < record.expires_at
    )


def activate(
    state: RotationState,
    pending: KeyRecord,
    active: KeyRecord | None,
    grace: KeyRecord | None,
    now: datetime,
    operation_id: str,
    expected_version: int,
    *,
    emergency: bool = False,
    manual: bool = False,
) -> Transition:
    if retry := _guard(state, now, operation_id, expected_version):
        return retry
    _candidate(state, pending, now)
    _require(type(emergency) is bool and type(manual) is bool)
    _require(state.pending_ready_at is not None, "NOT_READY")
    assert state.pending_ready_at is not None
    _require(pending.created_at <= state.pending_ready_at <= now)
    _prior(active, state.active_key_id, "ACTIVE", now)
    _prior(grace, state.grace_key_id, "GRACE", now)
    if not emergency:
        _require(not _live(grace, now), "LIVE_GRACE")
        _require(
            manual or state.next_rotation_at is None or now >= state.next_rotation_at, "NOT_DUE"
        )
    changed = []
    grace_id = None
    for record in (active, grace):
        if record is None or record.status in {"EXPIRED", "REVOKED"}:
            continue
        if not _live(record, now):
            changed.append(replace(record, status="EXPIRED"))
        elif emergency:
            changed.append(replace(record, status="REVOKED"))
        else:
            assert record.activates_at is not None and record.expires_at is not None
            expiry = min(
                record.expires_at,
                record.activates_at + timedelta(days=8),
                now + timedelta(hours=24),
            )
            changed.append(replace(record, status="GRACE", expires_at=expiry))
            grace_id = record.key_id
    changed.append(
        replace(pending, status="ACTIVE", activates_at=now, expires_at=now + timedelta(days=8))
    )
    return _finish(
        state,
        changed,
        now,
        operation_id,
        active_key_id=pending.key_id,
        grace_key_id=grace_id,
        pending_key_id=None,
        pending_ready_at=None,
        next_rotation_at=now + timedelta(days=7),
    )


def revoke(
    state: RotationState, key: KeyRecord, now: datetime, operation_id: str, expected_version: int
) -> Transition:
    if retry := _guard(state, now, operation_id, expected_version):
        return retry
    _validate_key(key, now)
    changes: dict[str, object] = {}
    for name in ("active_key_id", "grace_key_id", "pending_key_id"):
        if getattr(state, name) == key.key_id:
            changes[name] = None
            if name == "pending_key_id":
                changes["pending_ready_at"] = None
    records = () if key.status in {"EXPIRED", "REVOKED"} else (replace(key, status="REVOKED"),)
    if not records and not changes:
        return Transition(state, (), False)
    return _finish(state, records, now, operation_id, **changes)


def expire(
    state: RotationState, records: tuple[KeyRecord, ...], now: datetime, operation_id: str
) -> Transition:
    if retry := _guard(state, now, operation_id):
        return retry
    _require(len({key.key_id for key in records}) == len(records))
    changed = []
    changes: dict[str, object] = {}
    for key in records:
        _validate_key(key, now)
        expired = key.expires_at is not None and now >= key.expires_at
        if expired and key.status in {"ACTIVE", "GRACE"}:
            changed.append(replace(key, status="EXPIRED"))
        if key.status in {"EXPIRED", "REVOKED"} or (expired and key.status in {"ACTIVE", "GRACE"}):
            for name in ("active_key_id", "grace_key_id"):
                if getattr(state, name) == key.key_id:
                    changes[name] = None
    if not changed and not changes:
        return Transition(state, (), False)
    return _finish(state, changed, now, operation_id, **changes)
