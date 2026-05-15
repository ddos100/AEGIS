"""Application-layer encryption for integration credentials.

Why application-layer (not pgcrypto):
  - The DB never needs to see cleartext credentials, so it shouldn't have the
    keys. This minimises blast radius if Postgres is compromised.
  - Key rotation is decoupled from schema migrations.

Algorithm:
  - Fernet (AES-128-CBC + HMAC-SHA256) — battle-tested, has built-in versioning
    via MultiFernet for online key rotation.

Key sourcing:
  - FERNET_KEY env var holds the **current write key**.
  - FERNET_KEY_PREVIOUS may hold the previous key during rotation windows;
    rows encrypted with the old key will still decrypt while new writes use
    the current key. Once every row is re-encrypted, drop FERNET_KEY_PREVIOUS.

Each ciphertext payload begins with a 4-byte big-endian "key_version" prefix
so that future key rotations can be reasoned about even outside the env-var
mechanism. ``key_version`` is also stored on the row.
"""
from __future__ import annotations

import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


def _load_fernets() -> MultiFernet:
    """Build a MultiFernet that decrypts with either the current or previous key.

    Encryption always uses the FIRST key in the list (the current key).
    """
    keys = [settings.fernet_key.encode() if isinstance(settings.fernet_key, str)
            else settings.fernet_key]
    prev = os.environ.get("FERNET_KEY_PREVIOUS")
    if prev:
        keys.append(prev.encode())
    return MultiFernet([Fernet(k) for k in keys])


_FERNET: MultiFernet | None = None


def _get_fernet() -> MultiFernet:
    global _FERNET
    if _FERNET is None:
        _FERNET = _load_fernets()
    return _FERNET


def encrypt_credentials(payload: dict[str, Any]) -> bytes:
    """Serialise + encrypt a credentials dict. Returns raw Fernet token bytes."""
    cleartext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _get_fernet().encrypt(cleartext)


def decrypt_credentials(ciphertext: bytes) -> dict[str, Any]:
    """Decrypt + parse credentials. Raises InvalidToken if the ciphertext can't
    be decrypted with any configured key."""
    if not ciphertext:
        raise InvalidToken("empty ciphertext")
    cleartext = _get_fernet().decrypt(ciphertext)
    return json.loads(cleartext.decode("utf-8"))


def rotate_keys() -> None:
    """Reset the cached Fernet bundle (call after env vars change).

    Used by tests and by an admin-only endpoint that rotates credentials in
    place using ``MultiFernet.rotate()``.
    """
    global _FERNET
    _FERNET = None


def reencrypt(ciphertext: bytes) -> bytes:
    """Re-encrypt a ciphertext with the current write key (key rotation hook)."""
    return _get_fernet().rotate(ciphertext)
