"""Unit tests for the Fernet credential helper."""
from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.core import crypto


@pytest.fixture(autouse=True)
def reset_fernet_after_each_test():
    yield
    crypto.rotate_keys()


def test_roundtrip_simple_payload() -> None:
    ct = crypto.encrypt_credentials({"hello": "world"})
    assert isinstance(ct, bytes)
    assert b"hello" not in ct                     # not plaintext
    assert crypto.decrypt_credentials(ct) == {"hello": "world"}


def test_roundtrip_complex_payload() -> None:
    payload = {
        "tenant_id":    "abc",
        "client_id":    "def",
        "client_secret": "very-secret",
        "regions":      ["us-east-1", "ap-south-1"],
        "nested":       {"k": True, "n": 42},
    }
    assert crypto.decrypt_credentials(crypto.encrypt_credentials(payload)) == payload


def test_empty_ciphertext_raises() -> None:
    with pytest.raises(InvalidToken):
        crypto.decrypt_credentials(b"")


def test_garbage_ciphertext_raises() -> None:
    with pytest.raises(InvalidToken):
        crypto.decrypt_credentials(b"not-a-fernet-token")


def test_previous_key_still_decrypts() -> None:
    """Set up two keys (rotation scenario) and confirm both decrypt."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    payload = {"v": "secret"}

    # Encrypt with the OLD key
    old_ct = Fernet(old_key).encrypt(b'{"v":"secret"}')

    # Configure app crypto with new_key as current, old_key as previous
    from app.core.config import settings
    settings.fernet_key = new_key.decode()
    os.environ["FERNET_KEY_PREVIOUS"] = old_key.decode()
    crypto.rotate_keys()

    try:
        # Old token still decrypts via the previous key
        assert crypto.decrypt_credentials(old_ct) == payload
        # New writes use the new key
        new_ct = crypto.encrypt_credentials(payload)
        assert new_ct != old_ct
    finally:
        os.environ.pop("FERNET_KEY_PREVIOUS", None)
