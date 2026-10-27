import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

from api_logistik.security.key_rotation import (
    KeyRecord,
    RotationError,
    RotationState,
    activate,
    attach_pending,
    confirm_ready,
    expire,
    revoke,
)


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 1, 1, tzinfo=UTC)
        self.pending = KeyRecord(1, "1" * 64, "PENDING", self.at, None, None)
        self.empty = RotationState()

    def ready(self, pending=None, state=None, now=None):
        pending = pending or self.pending
        state = state or self.empty
        now = now or self.at
        prepared = attach_pending(state, pending, now, "prepare", state.version)
        return confirm_ready(prepared.state, pending, now, "ready", prepared.state.version).state

    def initial(self):
        state = self.ready()
        return activate(state, self.pending, None, None, self.at, "initial", state.version)

    def assert_code(self, code, callable_, *args, **kwargs):
        with self.assertRaises(RotationError) as raised:
            callable_(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)
        self.assertNotIn(self.pending.key_hash, repr(raised.exception))

    def test_bootstrap_readiness_required(self):
        prepared = attach_pending(self.empty, self.pending, self.at, "p", 0)
        self.assert_code(
            "NOT_READY", activate, prepared.state, self.pending, None, None, self.at, "a", 1
        )
        result = self.initial()
        self.assertEqual(result.state.next_rotation_at, self.at + timedelta(days=7))
        self.assertEqual(result.keys[0].expires_at, self.at + timedelta(days=8))
        self.assertIsNone(result.state.pending_key_id)
        self.assertIsNone(result.state.pending_ready_at)

    def test_stale_ack_and_duplicate_candidate(self):
        prepared = attach_pending(self.empty, self.pending, self.at, "prepare", 0)
        self.assert_code(
            "STALE_VERSION", confirm_ready, prepared.state, self.pending, self.at, "ack", 0
        )
        self.assert_code(
            "CANDIDATE_MISMATCH",
            confirm_ready,
            prepared.state,
            replace(self.pending, key_id=2),
            self.at,
            "ack",
            1,
        )
        self.assert_code(
            "PENDING_EXISTS",
            attach_pending,
            prepared.state,
            replace(self.pending, key_id=2),
            self.at,
            "p2",
            1,
        )
        self.assert_code(
            "STALE_VERSION", confirm_ready, prepared.state, self.pending, self.at, "ack", None
        )

    def test_terminal_and_invalid_status_never_attach_or_activate(self):
        for status in ("ACTIVE", "GRACE", "EXPIRED", "REVOKED", "OTHER"):
            self.assert_code(
                "INVALID_METADATA",
                attach_pending,
                self.empty,
                replace(self.pending, status=status),
                self.at,
                "p",
                0,
            )
        state = self.ready()
        for status in ("EXPIRED", "REVOKED"):
            self.assert_code(
                "INVALID_METADATA",
                activate,
                state,
                replace(self.pending, status=status),
                None,
                None,
                self.at,
                "a",
                state.version,
            )

    def test_normal_due_and_actual_cutover(self):
        first = self.initial()
        pending = replace(self.pending, key_id=2, key_hash="2" * 64)
        before_due = self.at + timedelta(days=7) - timedelta(microseconds=1)
        state = self.ready(pending, first.state, before_due)
        self.assert_code(
            "NOT_DUE",
            activate,
            state,
            pending,
            first.keys[0],
            None,
            before_due,
            "rotate",
            state.version,
        )
        now = self.at + timedelta(days=7, hours=12)
        result = activate(state, pending, first.keys[0], None, now, "rotate", state.version)
        old, new = result.keys
        self.assertEqual(old.status, "GRACE")
        self.assertEqual(old.expires_at, self.at + timedelta(days=8))
        self.assertEqual(new.activates_at, now)
        self.assertEqual(new.expires_at, now + timedelta(days=8))
        self.assertEqual(result.state.next_rotation_at, now + timedelta(days=7))

    def test_late_activation_does_not_revive_expired_active(self):
        first = self.initial()
        pending = replace(self.pending, key_id=2, key_hash="2" * 64)
        now = self.at + timedelta(days=8)
        state = self.ready(pending, first.state, now)
        result = activate(state, pending, first.keys[0], None, now, "rotate", state.version)
        self.assertEqual(result.keys[0].status, "EXPIRED")
        self.assertIsNone(result.state.grace_key_id)

    def test_explicit_early_manual_and_grace_limit(self):
        first = self.initial()
        pending = replace(self.pending, key_id=2, key_hash="2" * 64)
        now = self.at + timedelta(days=1)
        state = self.ready(pending, first.state, now)
        second = activate(
            state, pending, first.keys[0], None, now, "manual", state.version, manual=True
        )
        self.assertEqual(second.keys[0].expires_at, now + timedelta(hours=24))
        third = replace(self.pending, key_id=3, key_hash="3" * 64)
        next_state = self.ready(third, second.state, now)
        self.assert_code(
            "LIVE_GRACE",
            activate,
            next_state,
            third,
            second.keys[1],
            second.keys[0],
            now,
            "third",
            next_state.version,
            manual=True,
        )

    def test_emergency_revokes_all_live_but_requires_readiness(self):
        first = self.initial()
        now = self.at + timedelta(hours=1)
        grace = replace(first.keys[0], key_id=3, key_hash="3" * 64, status="GRACE")
        pending = replace(self.pending, key_id=2, key_hash="2" * 64)
        base = replace(first.state, grace_key_id=3)
        prepared = attach_pending(base, pending, now, "prep2", base.version)
        self.assert_code(
            "NOT_READY",
            activate,
            prepared.state,
            pending,
            first.keys[0],
            grace,
            now,
            "e",
            prepared.state.version,
            emergency=True,
        )
        state = confirm_ready(prepared.state, pending, now, "ack2", prepared.state.version).state
        result = activate(
            state, pending, first.keys[0], grace, now, "e", state.version, emergency=True
        )
        self.assertEqual([key.status for key in result.keys], ["REVOKED", "REVOKED", "ACTIVE"])
        self.assertIsNone(result.state.grace_key_id)

    def test_retry_checks_operation_before_old_version(self):
        first = attach_pending(self.empty, self.pending, self.at, "same", 0)
        retry = attach_pending(first.state, self.pending, self.at, "same", 0)
        self.assertFalse(retry.changed)
        self.assertEqual(retry.keys, ())
        self.assertEqual(retry.state, first.state)

    def test_revoke_clears_only_matching_pointer_and_readiness(self):
        state = self.ready()
        result = revoke(state, self.pending, self.at, "revoke", state.version)
        self.assertIsNone(result.state.pending_key_id)
        self.assertIsNone(result.state.pending_ready_at)
        self.assertEqual(result.keys[0].status, "REVOKED")
        self.assertFalse(
            revoke(result.state, result.keys[0], self.at, "again", result.state.version).changed
        )
        first = self.initial()
        other = replace(self.pending, key_id=2)
        state = self.ready(other, first.state)
        revoked = revoke(state, first.keys[0], self.at, "r", state.version)
        self.assertIsNone(revoked.state.active_key_id)
        self.assertEqual(revoked.state.pending_key_id, 2)
        self.assertIsNotNone(revoked.state.pending_ready_at)

    def test_cleanup_does_not_activate_pending(self):
        first = self.initial()
        pending = replace(self.pending, key_id=2, key_hash="2" * 64)
        state = self.ready(pending, first.state)
        now = self.at + timedelta(days=8)
        result = expire(state, (first.keys[0], pending), now, "cleanup")
        self.assertEqual(result.keys[0].status, "EXPIRED")
        self.assertIsNone(result.state.active_key_id)
        self.assertEqual(result.state.pending_key_id, 2)
        self.assertIsNotNone(result.state.pending_ready_at)
        self.assertFalse(expire(result.state, result.keys, now, "again").changed)

    def test_new_candidate_resets_readiness(self):
        state = self.ready()
        result = revoke(state, self.pending, self.at, "r", state.version)
        new = replace(self.pending, key_id=2, key_hash="2" * 64)
        attached = attach_pending(result.state, new, self.at, "new", result.state.version)
        self.assertIsNone(attached.state.pending_ready_at)
        self.assert_code(
            "CANDIDATE_MISMATCH",
            confirm_ready,
            attached.state,
            self.pending,
            self.at,
            "stale",
            attached.state.version,
        )

    def test_utc_and_record_pointer_consistency(self):
        for now in (self.at.replace(tzinfo=None), self.at.astimezone(timezone(timedelta(hours=7)))):
            self.assert_code(
                "INVALID_METADATA", attach_pending, self.empty, self.pending, now, "p", 0
            )
        first = self.initial()
        pending = replace(self.pending, key_id=2, key_hash="2" * 64)
        state = self.ready(pending, first.state)
        self.assert_code(
            "INVALID_METADATA",
            activate,
            state,
            pending,
            None,
            None,
            self.at,
            "x",
            state.version,
            emergency=True,
        )

    def test_concurrent_proposals_need_caller_compare_and_swap(self):
        def propose(number):
            return attach_pending(
                self.empty, replace(self.pending, key_id=number), self.at, f"p{number}", 0
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            proposals = list(pool.map(propose, (1, 2)))
        committed = proposals[0].state
        self.assert_code(
            "STALE_VERSION",
            attach_pending,
            committed,
            proposals[1].keys[0],
            self.at,
            "retry-other",
            0,
        )
        self.assertEqual(self.empty.version, 0)
