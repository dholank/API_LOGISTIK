"""Opaque keys and fail-closed checks against the GLOBAL lifecycle metadata."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta

from .key_rotation import KeyRecord, RotationError, RotationState, _validate_key, _validate_state


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def valid_key_format(raw: str) -> bool:
    return (
        isinstance(raw, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", raw, flags=re.ASCII) is not None
    )


def key_is_valid(key: KeyRecord, state: RotationState, now: datetime) -> bool:
    try:
        _validate_state(state, now)
        _validate_key(key, now)
        if key.activates_at is None or key.expires_at is None:
            return False
        if key.status == "ACTIVE":
            if state.active_key_id != key.key_id:
                return False
            if state.next_rotation_at != key.activates_at + timedelta(days=7):
                return False
            if key.expires_at != key.activates_at + timedelta(days=8):
                return False
        elif key.status == "GRACE":
            if state.grace_key_id != key.key_id or state.next_rotation_at is None:
                return False
            cutover = state.next_rotation_at - timedelta(days=7)
            if not key.activates_at <= cutover <= now:
                return False
            if key.expires_at > cutover + timedelta(hours=24):
                return False
        else:
            return False
        return key.activates_at <= now < key.expires_at
    except RotationError, TypeError, ValueError, AttributeError, OverflowError:
        return False
