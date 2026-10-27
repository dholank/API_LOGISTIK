import argparse
import getpass
import json
import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from api_logistik.config import Settings, load_settings
from api_logistik.db.api_key_repository import ApiKeyRepository
from api_logistik.db.pool import PoolManager
from api_logistik.db.transactions import transaction
from api_logistik.errors import ApplicationError, CommitOutcomeUnknown, ConfigurationError, LockBusy
from api_logistik.logging_config import configure_logging
from api_logistik.security.api_keys import generate_api_key
from api_logistik.security.key_rotation import (
    KeyRecord,
    RotationError,
    RotationState,
    Transition,
    activate,
    attach_pending,
    confirm_ready,
    expire,
    revoke,
)
from api_logistik.security.secret_store import (
    EncryptedFileSecretStore,
    SecretStoreError,
    init_encryption_key,
    read_encryption_key,
)

_LOG = logging.getLogger("api_logistik.operator")
_REASONS = (
    "bootstrap",
    "scheduled",
    "manual_rotation",
    "suspected_compromise",
    "distribution_confirmed",
    "key_retired",
    "recovery",
)


def _operation(value: str | None) -> str:
    return str(uuid.UUID(value)) if value else str(uuid.uuid4())


def _stage(operation: str, name: str) -> str:
    return str(uuid.uuid5(uuid.UUID(operation), name))


def _public_state(state: RotationState) -> dict[str, Any]:
    return {
        "scope": state.scope_id,
        "active_key_id": state.active_key_id,
        "grace_key_id": state.grace_key_id,
        "pending_key_id": state.pending_key_id,
        "next_rotation_at": state.next_rotation_at,
        "pending_ready_at": state.pending_ready_at,
        "version": state.version,
        "last_operation_id": state.last_operation_id,
        "last_operation_at": state.last_operation_at,
    }


def _require_outside_project(path: Path) -> None:
    resolved = path.resolve()
    if any(
        (parent / "pyproject.toml").is_file() or (parent / ".git").exists()
        for parent in (resolved, *resolved.parents)
    ):
        raise RotationError(
            "PRIVATE_PATH_REQUIRED", "Secret material must be stored outside project directories."
        )


def _store(settings: Settings) -> EncryptedFileSecretStore:
    if settings.key_secret_store_dir is None:
        raise ConfigurationError()
    _require_outside_project(settings.key_secret_store_dir)
    if settings.key_encryption_key_file:
        _require_outside_project(settings.key_encryption_key_file)
        key = read_encryption_key(settings.key_encryption_key_file)
    elif settings.key_encryption_key:
        try:
            key = settings.key_encryption_key.get_secret_value().encode("ascii")
        except UnicodeError:
            raise ConfigurationError() from None
    else:
        raise ConfigurationError()
    return EncryptedFileSecretStore(settings.key_secret_store_dir, key)


class KeyOperator:
    def __init__(
        self,
        pool: PoolManager,
        store: EncryptedFileSecretStore | None = None,
        *,
        fresh_pool_factory: Callable[[], PoolManager] | None = None,
    ) -> None:
        self.pool = pool
        self.store = store
        self._fresh_pool_factory = fresh_pool_factory or (
            lambda: PoolManager(pool.settings, writer=True)
        )
        self.candidate_key_id: int | None = None

    def _secret_store(self) -> EncryptedFileSecretStore:
        if self.store is None:
            raise ConfigurationError()
        return self.store

    @staticmethod
    def _apply(repo: ApiKeyRepository, before: RotationState, change: Transition) -> None:
        if change.changed:
            for key in change.keys:
                repo.save_key(key)
            repo.save_state(change.state, before.version)

    def _mutate(
        self,
        callback: Callable[[ApiKeyRepository, RotationState, datetime], Transition],
    ) -> RotationState:
        with self.pool.connection() as connection:
            with transaction(connection):
                repo = ApiKeyRepository(connection)
                before = repo.read_state(lock=True)
                now = repo.database_now()
                change = callback(repo, before, now)
                self._apply(repo, before, change)
                state = change.state
        return state

    def status(self) -> dict[str, Any]:
        with self.pool.connection() as connection:
            repo = ApiKeyRepository(connection)
            state = repo.read_state()
            now = repo.database_now()
            records = [
                repo.get_key(i)
                for i in (state.active_key_id, state.grace_key_id, state.pending_key_id)
            ]
        result = _public_state(state)
        result["database_time"] = now
        result["keys"] = [
            {
                "key_id": key.key_id,
                "status": key.status,
                "activates_at": key.activates_at,
                "expires_at": key.expires_at,
            }
            for key in records
            if key is not None
        ]
        issues = []
        if state.next_rotation_at is None:
            issues.append("BOOTSTRAP_REQUIRED")
        elif now >= state.next_rotation_at - timedelta(hours=24):
            if state.pending_key_id is None:
                issues.append("MISSING_SUCCESSOR")
            elif state.pending_ready_at is None:
                issues.append("DISTRIBUTION_NOT_CONFIRMED")
        if any(key and key.expires_at and now >= key.expires_at for key in records):
            issues.append("EXPIRED_TIMESTAMP")
        result["issues"] = issues
        return result

    def prepare(
        self,
        operation: str,
        expected_version: int | None,
        *,
        replace_pending: bool = False,
    ) -> RotationState:
        with self.pool.connection() as connection:
            before = ApiKeyRepository(connection).read_state()
        if before.last_operation_id == operation:
            return before
        if before.pending_key_id is not None and not replace_pending:
            return before
        if expected_version is not None and expected_version != before.version:
            raise RotationError("STALE_VERSION", "Rotation version does not match.")
        digest = self._secret_store().put(generate_api_key())

        def register(repo: ApiKeyRepository, state: RotationState, now: datetime) -> Transition:
            if state.last_operation_id == operation:
                return Transition(state, (), False)
            if state.pending_key_id is not None and not replace_pending:
                return Transition(state, (), False)
            if expected_version is not None and state.version != expected_version:
                raise RotationError("STALE_VERSION", "Rotation version does not match.")
            original = state
            changed: tuple[KeyRecord, ...] = ()
            if state.pending_key_id is not None:
                old = repo.get_key(state.pending_key_id)
                if old is None:
                    raise ConfigurationError()
                discarded = revoke(
                    state, old, now, _stage(operation, "replace_pending"), state.version
                )
                state, changed = discarded.state, discarded.keys
            if repo.find_by_hash(digest) is not None:
                raise RotationError(
                    "HASH_ALREADY_REGISTERED", "Candidate must be freshly generated."
                )
            planned = max(state.next_rotation_at or now, now)
            key = repo.insert_pending(digest, now, planned)
            self.candidate_key_id = key.key_id
            attached = attach_pending(state, key, now, operation, state.version)
            return Transition(attached.state, changed + attached.keys, attached.state != original)

        return self._mutate(register)

    def confirm(self, identifier: int, expected_version: int, operation: str) -> RotationState:
        with self.pool.connection() as connection:
            repo = ApiKeyRepository(connection)
            state = repo.read_state()
            key = repo.get_key(identifier)
        if state.last_operation_id == operation:
            return state
        if key is None or state.pending_key_id != identifier:
            raise RotationError("CANDIDATE_MISMATCH", "Pending candidate does not match.")
        self._secret_store().get(key.key_hash)

        def mark(repo: ApiKeyRepository, current: RotationState, now: datetime) -> Transition:
            candidate = repo.get_key(identifier)
            if candidate is None or candidate.key_hash != key.key_hash:
                raise RotationError("CANDIDATE_MISMATCH", "Pending candidate does not match.")
            return confirm_ready(current, candidate, now, operation, expected_version)

        return self._mutate(mark)

    def activate(
        self,
        expected_version: int,
        operation: str,
        *,
        emergency: bool = False,
        manual: bool = False,
    ) -> RotationState:
        def promote(repo: ApiKeyRepository, state: RotationState, now: datetime) -> Transition:
            if state.last_operation_id == operation:
                return Transition(state, (), False)
            candidate = repo.get_key(state.pending_key_id)
            if candidate is None:
                raise RotationError("NO_PENDING", "No pending candidate exists.")
            return activate(
                state,
                candidate,
                repo.get_key(state.active_key_id),
                repo.get_key(state.grace_key_id),
                now,
                operation,
                expected_version,
                emergency=emergency,
                manual=manual,
            )

        return self._mutate(promote)

    def revoke(self, identifier: int, expected_version: int, operation: str) -> RotationState:
        def retire(repo: ApiKeyRepository, state: RotationState, now: datetime) -> Transition:
            key = repo.get_key(identifier)
            if key is None:
                raise RotationError("KEY_NOT_FOUND", "Key does not exist.")
            return revoke(state, key, now, operation, expected_version)

        return self._mutate(retire)

    def export(self, identifier: int, destination: Path) -> None:
        _require_outside_project(destination)
        with self.pool.connection() as connection:
            repo = ApiKeyRepository(connection)
            state = repo.read_state()
            key = repo.get_key(identifier)
        if (
            key is None
            or identifier not in (state.active_key_id, state.pending_key_id)
            or key.status not in {"ACTIVE", "PENDING"}
        ):
            raise RotationError(
                "EXPORT_NOT_ALLOWED", "Only the current active or pending material may be exported."
            )
        self._secret_store().export(key.key_hash, destination)

    def reconcile(self, operation: str, identifier: int | None) -> dict[str, Any]:
        fresh = self._fresh_pool_factory()
        try:
            with fresh.connection() as connection:
                with transaction(connection, write=False):
                    repo = ApiKeyRepository(connection)
                    state = repo.read_state(lock=True)
                    key = repo.get_key(identifier)
                    result = _public_state(state)
                    result.update(
                        original_operation_confirmed=state.last_operation_id == operation,
                        historical_key_found=key is not None,
                        key_status=key.status if key else None,
                        manual_review_required=state.last_operation_id != operation,
                    )
            return result
        finally:
            fresh.close()

    def tick(self, operation: str) -> tuple[dict[str, Any], int]:
        def cleanup(repo: ApiKeyRepository, state: RotationState, now: datetime) -> Transition:
            records = tuple(
                key
                for i in (state.active_key_id, state.grace_key_id)
                if (key := repo.get_key(i)) is not None
            )
            return expire(state, records, now, _stage(operation, "expire"))

        self._mutate(cleanup)
        status = self.status()
        due = status["next_rotation_at"]
        now = status["database_time"]
        if due is None:
            return {"result": "BOOTSTRAP_REQUIRED", **status}, 2
        if now < due - timedelta(hours=24):
            return {"result": "NOT_DUE", **status}, 0
        if status["pending_key_id"] is None:
            self.prepare(_stage(operation, "prepare"), None)
            status = self.status()
        if status["pending_ready_at"] is None:
            _LOG.warning(
                "rotation_blocked",
                extra={"operation_id": operation, "error_code": "DISTRIBUTION_NOT_CONFIRMED"},
            )
            return {"result": "DISTRIBUTION_NOT_CONFIRMED", **status}, 2
        if status["database_time"] < status["next_rotation_at"]:
            return {"result": "WAITING_FOR_DUE", **status}, 0
        state = self.activate(status["version"], _stage(operation, "activate"))
        return {"result": "ACTIVATED", **_public_state(state)}, 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Global API Key operator; never prints raw keys.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--operation-id")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in (
        "init-secret-key",
        "prepare",
        "confirm-distributed",
        "activate",
        "revoke",
        "tick",
        "status",
        "reconcile",
        "export",
    ):
        command = commands.add_parser(name)
        command.add_argument("--env-file", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--operation-id", default=argparse.SUPPRESS)
        if name in {"init-secret-key", "export"}:
            command.add_argument("--output", type=Path, required=True)
        if name in {"confirm-distributed", "activate", "revoke"}:
            command.add_argument("--expected-version", type=int, required=True)
        if name == "prepare":
            command.add_argument("--expected-version", type=int, required=True)
            command.add_argument("--replace-pending", action="store_true")
            command.add_argument("--emergency", action="store_true")
        if name in {"confirm-distributed", "revoke", "export"}:
            command.add_argument("--key-id", type=int, required=True)
        if name == "reconcile":
            command.add_argument("--key-id", type=int)
        if name in {"prepare", "confirm-distributed", "activate", "revoke"}:
            command.add_argument("--reason", choices=_REASONS, required=True)
        if name == "activate":
            flags = command.add_mutually_exclusive_group()
            flags.add_argument("--manual", action="store_true")
            flags.add_argument("--emergency", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = _parser().parse_args(argv)
    pool: PoolManager | None = None
    operator: KeyOperator | None = None
    operation = ""
    try:
        if args.command == "reconcile" and not args.operation_id:
            raise RotationError(
                "OPERATION_ID_REQUIRED", "Supply the original operation identifier."
            )
        operation = _operation(args.operation_id)
        settings = load_settings(args.env_file)
        if args.command not in {"status"} and not settings.operator_authorized:
            raise RotationError(
                "OPERATOR_AUTHORIZATION_REQUIRED",
                "Operator authorization acknowledgement is required.",
            )
        actor = getpass.getuser()
        _LOG.info(
            "operator_intent",
            extra={
                "operation_id": operation,
                "actor": actor,
                "action": args.command,
                "reason": getattr(args, "reason", None),
            },
        )
        if args.command == "init-secret-key":
            _require_outside_project(args.output)
            init_encryption_key(args.output)
            result: dict[str, Any] = {"result": "PRIVATE_KEY_FILE_CREATED"}
            exit_code = 0
        else:
            pool = PoolManager(settings, writer=args.command != "status")
            needs_store = args.command in {"prepare", "confirm-distributed", "export", "tick"}
            operator = KeyOperator(pool, _store(settings) if needs_store else None)
            exit_code = 0
            if args.command == "status":
                result = operator.status()
            elif args.command == "prepare":
                result = _public_state(
                    operator.prepare(
                        operation,
                        args.expected_version,
                        replace_pending=args.replace_pending or args.emergency,
                    )
                )
            elif args.command == "confirm-distributed":
                result = _public_state(
                    operator.confirm(args.key_id, args.expected_version, operation)
                )
            elif args.command == "activate":
                result = _public_state(
                    operator.activate(
                        args.expected_version,
                        operation,
                        emergency=args.emergency,
                        manual=args.manual,
                    )
                )
            elif args.command == "revoke":
                result = _public_state(
                    operator.revoke(args.key_id, args.expected_version, operation)
                )
            elif args.command == "export":
                operator.export(args.key_id, args.output)
                result = {"result": "PRIVATE_EXPORT_CREATED", "key_id": args.key_id}
            elif args.command == "reconcile":
                result = operator.reconcile(operation, args.key_id)
            else:
                result, exit_code = operator.tick(operation)
        print(json.dumps({"ok": exit_code == 0, "operation_id": operation, **result}, default=str))
        _LOG.info(
            "operator_result",
            extra={
                "operation_id": operation,
                "actor": actor,
                "action": args.command,
                "result": "success" if exit_code == 0 else "blocked",
                "version": result.get("version"),
            },
        )
        return exit_code
    except (ApplicationError, RotationError, SecretStoreError) as exc:
        code = exc.code
        exit_code = (
            4
            if isinstance(exc, CommitOutcomeUnknown)
            else 3
            if isinstance(exc, LockBusy)
            else 2
            if isinstance(exc, RotationError)
            else 1
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "operation_id": operation,
                    "error_code": code,
                    "candidate_key_id": operator.candidate_key_id if operator else None,
                }
            )
        )
        _LOG.error(
            "operator_failed",
            extra={
                "operation_id": operation,
                "action": args.command,
                "error_code": code,
                "result": "unknown" if exit_code == 4 else "failed",
            },
        )
        return exit_code
    except Exception:
        print(json.dumps({"ok": False, "operation_id": operation, "error_code": "INTERNAL_ERROR"}))
        return 1
    finally:
        if pool:
            pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
