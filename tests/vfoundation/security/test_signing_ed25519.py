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
