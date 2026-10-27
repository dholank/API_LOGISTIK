import hashlib
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from api_logistik.security.api_keys import (
    generate_api_key,
    hash_api_key,
    key_is_valid,
    valid_key_format,
)
from api_logistik.security.key_rotation import KeyRecord, RotationState


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 1, 1, tzinfo=UTC)
        self.raw = "a" * 43
        self.key = KeyRecord(
            1, hash_api_key(self.raw), "ACTIVE", self.at, self.at, self.at + timedelta(days=8)
        )
        self.state = RotationState(active_key_id=1, next_rotation_at=self.at + timedelta(days=7))

    def test_generation_uses_requested_entropy(self):
        with patch(
            "api_logistik.security.api_keys.secrets.token_urlsafe", return_value=self.raw
        ) as generate:
            self.assertEqual(generate_api_key(), self.raw)
            generate.assert_called_once_with(32)

    def test_digest_exact_utf8_no_normalization(self):
        self.assertEqual(
            hash_api_key("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
        self.assertEqual(hash_api_key("é"), hashlib.sha256("é".encode()).hexdigest())
        self.assertNotEqual(hash_api_key(self.raw), hash_api_key(" " + self.raw))

    def test_exact_ascii_format(self):
        self.assertTrue(valid_key_format("A" * 41 + "_-"))
        for raw in (
            None,
            "",
            "a" * 42,
            "a" * 44,
            self.raw + "\n",
            " " + self.raw,
            "é" * 43,
            "=" * 43,
            "Ａ" * 43,
        ):
            with self.subTest(kind=type(raw).__name__):
                self.assertFalse(valid_key_format(raw))

    def test_time_window_boundaries(self):
        self.assertFalse(key_is_valid(self.key, self.state, self.at - timedelta(microseconds=1)))
        self.assertTrue(key_is_valid(self.key, self.state, self.at))
        self.assertTrue(
            key_is_valid(self.key, self.state, self.key.expires_at - timedelta(microseconds=1))
        )
        self.assertFalse(key_is_valid(self.key, self.state, self.key.expires_at))

    def test_terminal_and_pointer_mismatch_fail_closed(self):
        for status in ("PENDING", "EXPIRED", "REVOKED", "OTHER", "GRACE"):
            self.assertFalse(key_is_valid(replace(self.key, status=status), self.state, self.at))
        self.assertFalse(key_is_valid(self.key, replace(self.state, active_key_id=2), self.at))

    def test_grace_and_inconsistent_metadata(self):
        grace = replace(self.key, status="GRACE", expires_at=self.at + timedelta(hours=24))
        state = RotationState(grace_key_id=1, next_rotation_at=self.at + timedelta(days=7))
        self.assertTrue(key_is_valid(grace, state, self.at))
        bad_keys = [
            replace(self.key, expires_at=None),
            replace(self.key, activates_at=None),
            replace(self.key, key_hash="invalid"),
            replace(self.key, expires_at=self.at + timedelta(days=9)),
            replace(self.key, created_at=self.at.replace(tzinfo=None)),
        ]
        for key in bad_keys:
            self.assertFalse(key_is_valid(key, self.state, self.at))
        self.assertFalse(key_is_valid(self.key, replace(self.state, pending_key_id=1), self.at))
        self.assertFalse(
            key_is_valid(self.key, replace(self.state, next_rotation_at=self.at), self.at)
        )
        self.assertFalse(key_is_valid(self.key, self.state, self.at.replace(tzinfo=None)))

    def test_record_immutable_and_hash_not_represented(self):
        self.assertNotIn(self.key.key_hash, repr(self.key))
        with self.assertRaises(FrozenInstanceError):
            self.key.status = "PENDING"
