"""Ed25519 licence-payload verification — pure-Python unit tests.

The licence-loader code path is exercised end-to-end in the e2e
deployment tests; here we focus on signature verification logic so a
broken sign-key handler can't ship undetected.
"""
from __future__ import annotations

import base64
import json

import pytest

from app.core.licence import LicenceError, verify_licence_payload


def _gen_key():
    """Generate a throwaway Ed25519 keypair. Returns (privkey, pub_pem_bytes)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub_pem


def test_valid_signature_round_trips() -> None:
    priv, pub_pem = _gen_key()
    payload = json.dumps({"tenant_id": "abc", "modules": ["AEGIS-CORE"]}).encode("utf-8")
    sig = base64.b64encode(priv.sign(payload)).decode("ascii")
    parsed = verify_licence_payload(payload, sig, pub_pem)
    assert parsed["tenant_id"] == "abc"
    assert parsed["modules"] == ["AEGIS-CORE"]


def test_tampered_payload_rejected() -> None:
    priv, pub_pem = _gen_key()
    payload = json.dumps({"tenant_id": "abc"}).encode("utf-8")
    sig = base64.b64encode(priv.sign(payload)).decode("ascii")
    tampered = payload.replace(b"abc", b"xyz")
    with pytest.raises(LicenceError, match="invalid licence signature"):
        verify_licence_payload(tampered, sig, pub_pem)


def test_wrong_key_rejected() -> None:
    priv1, _ = _gen_key()
    _, pub_pem2 = _gen_key()
    payload = json.dumps({"tenant_id": "abc"}).encode("utf-8")
    sig = base64.b64encode(priv1.sign(payload)).decode("ascii")
    with pytest.raises(LicenceError, match="invalid licence signature"):
        verify_licence_payload(payload, sig, pub_pem2)


def test_garbage_signature_rejected() -> None:
    _, pub_pem = _gen_key()
    payload = json.dumps({"tenant_id": "abc"}).encode("utf-8")
    with pytest.raises(LicenceError):
        verify_licence_payload(payload, "not-base64", pub_pem)


def test_garbage_pubkey_rejected() -> None:
    priv, _ = _gen_key()
    payload = json.dumps({"tenant_id": "abc"}).encode("utf-8")
    sig = base64.b64encode(priv.sign(payload)).decode("ascii")
    with pytest.raises(LicenceError, match="public key load failed"):
        verify_licence_payload(payload, sig, b"-----not a key-----")
