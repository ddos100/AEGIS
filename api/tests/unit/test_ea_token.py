"""Endpoint Agent device-token signing — pure-Python unit tests.

Locks the HMAC-SHA256 round-trip contract that the agent's bearer
credential depends on. No DB, no HTTP — just the signer.
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from app.core.ea_token import (
    mint_device_token,
    token_fingerprint,
    verify_device_token,
)


def test_round_trip_valid_token() -> None:
    tid = uuid4()
    did = uuid4()
    tok = mint_device_token(tenant_id=tid, device_id=did)
    claims = verify_device_token(tok)
    assert claims["tenant_id"] == str(tid)
    assert claims["device_id"] == str(did)
    assert claims["v"] == 1
    assert isinstance(claims["iat"], int)


def test_two_part_token_format() -> None:
    tid = uuid4()
    did = uuid4()
    tok = mint_device_token(tenant_id=tid, device_id=did)
    assert tok.count(".") == 1


def test_tampered_payload_rejected() -> None:
    tok = mint_device_token(tenant_id=uuid4(), device_id=uuid4())
    body, sig = tok.split(".", 1)
    tampered = body + "AAAA" + "." + sig
    with pytest.raises(ValueError):
        verify_device_token(tampered)


def test_tampered_signature_rejected() -> None:
    tok = mint_device_token(tenant_id=uuid4(), device_id=uuid4())
    body, sig = tok.split(".", 1)
    tampered = body + "." + ("A" * 8 + sig[8:] if len(sig) > 8 else sig + "AA")
    with pytest.raises(ValueError):
        verify_device_token(tampered)


def test_garbage_token_rejected() -> None:
    with pytest.raises(ValueError):
        verify_device_token("not a token at all")


def test_missing_dot_rejected() -> None:
    with pytest.raises(ValueError):
        verify_device_token("abcdefghij")


def test_fingerprint_is_64_hex() -> None:
    tok = mint_device_token(tenant_id=uuid4(), device_id=uuid4())
    fp = token_fingerprint(tok)
    assert len(fp) == 64
    int(fp, 16)  # raises if not hex


def test_fingerprint_stable() -> None:
    tok = mint_device_token(tenant_id=uuid4(), device_id=uuid4())
    assert token_fingerprint(tok) == token_fingerprint(tok)


def test_different_tokens_different_fingerprints() -> None:
    a = mint_device_token(tenant_id=uuid4(), device_id=uuid4())
    b = mint_device_token(tenant_id=uuid4(), device_id=uuid4())
    assert token_fingerprint(a) != token_fingerprint(b)
