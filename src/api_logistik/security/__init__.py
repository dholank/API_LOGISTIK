"""GLOBAL API key primitives without database or environment side effects."""

from .api_keys import generate_api_key, hash_api_key, key_is_valid, valid_key_format
from .key_rotation import (
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
from .secret_store import (
    EncryptedFileSecretStore,
    SecretStoreError,
    init_encryption_key,
    read_encryption_key,
)

__all__ = [
    "KeyRecord",
    "RotationError",
    "RotationState",
    "Transition",
    "activate",
    "attach_pending",
    "confirm_ready",
    "expire",
    "revoke",
    "generate_api_key",
    "hash_api_key",
    "key_is_valid",
    "valid_key_format",
    "EncryptedFileSecretStore",
    "SecretStoreError",
    "init_encryption_key",
    "read_encryption_key",
]
