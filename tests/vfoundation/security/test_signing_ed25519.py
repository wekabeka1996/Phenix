"""Tests for vfoundation.security.signing_ed25519 — Phase 1.1."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _set_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VFOUNDATION_KMS_SEED", "test-seed-12345")


def test_sign_verify_roundtrip() -> None:
    from vfoundation.security.signing_ed25519 import sign, verify

    payload = b"hello world"
    sig = sign(payload)
    assert verify(payload, sig) is True


def test_verify_rejects_bad_signature() -> None:
    from vfoundation.security.signing_ed25519 import sign, verify

    sig = sign(b"legit payload")
    assert verify(b"tampered payload", sig) is False


def test_verify_rejects_corrupted_signature() -> None:
    from vfoundation.security.signing_ed25519 import sign, verify

    sig = sign(b"data")
    bad_sig = bytearray(sig)
    bad_sig[0] ^= 0xFF
    assert verify(b"data", bytes(bad_sig)) is False


def test_keys_deterministic_from_seed() -> None:
    from vfoundation.security.signing_ed25519 import load_keys

    _, vk1 = load_keys()
    _, vk2 = load_keys()
    assert vk1._key == vk2._key


def test_different_seeds_produce_different_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from vfoundation.security.signing_ed25519 import load_keys

    _, vk_a = load_keys()
    monkeypatch.setenv("VFOUNDATION_KMS_SEED", "other-seed-99999")
    _, vk_b = load_keys()
    assert vk_a._key != vk_b._key


def test_signature_non_empty() -> None:
    from vfoundation.security.signing_ed25519 import sign

    sig = sign(b"any")
    assert len(sig) > 0, "Ed25519 signature must not be empty"


def test_verify_short_signature_returns_false():
    """PyNaCl raises ValueError for wrong-length signature — must return False."""
    from vfoundation.security.signing_ed25519 import sign, verify
    payload = b"test payload"
    assert verify(payload, b"short") is False


def test_verify_empty_signature_returns_false():
    """Empty bytes signature must return False, not raise."""
    from vfoundation.security.signing_ed25519 import verify
    assert verify(b"payload", b"") is False


def test_verify_wrong_payload_returns_false():
    """Correct signature but wrong payload must return False."""
    from vfoundation.security.signing_ed25519 import sign, verify
    payload = b"original"
    sig = sign(payload)
    assert verify(b"tampered", sig) is False


def test_verify_correct_signature_returns_true():
    """Sign then verify with correct data must return True."""
    from vfoundation.security.signing_ed25519 import sign, verify
    payload = b"authentic message"
    sig = sign(payload)
    assert verify(payload, sig) is True


def test_canonical_json_bytes_is_deterministic_for_key_order():
    from vfoundation.security.signing_ed25519 import canonical_json_bytes

    payload_a = {"b": 2, "a": 1, "nested": {"z": 9, "x": 7}}
    payload_b = {"nested": {"x": 7, "z": 9}, "a": 1, "b": 2}

    assert canonical_json_bytes(payload_a) == canonical_json_bytes(payload_b)


def test_sign_canonical_json_is_stable_and_verifiable():
    from vfoundation.security.signing_ed25519 import sign_canonical_json, verify_canonical_json

    payload_a = {"symbol": "BTCUSDT", "qty": "0.01", "side": "BUY"}
    payload_b = {"side": "BUY", "qty": "0.01", "symbol": "BTCUSDT"}

    sig_a = sign_canonical_json(payload_a)
    sig_b = sign_canonical_json(payload_b)

    assert sig_a == sig_b
    assert verify_canonical_json(payload_a, sig_a) is True
    assert verify_canonical_json(payload_b, sig_b) is True
