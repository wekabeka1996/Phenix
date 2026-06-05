"""Tests for vfoundation.dr.merkle — Phase 1.9."""
from __future__ import annotations

import hashlib

from vfoundation.dr.merkle import merkle_root


def test_empty_list() -> None:
    expected = hashlib.sha256(b"").hexdigest()
    assert merkle_root([]) == expected


def test_single_hash() -> None:
    h = hashlib.sha256(b"hello").hexdigest()
    result = merkle_root([h])
    assert isinstance(result, str)
    assert len(result) == 64  # sha256 hex


def test_two_hashes() -> None:
    h1 = hashlib.sha256(b"a").hexdigest()
    h2 = hashlib.sha256(b"b").hexdigest()
    expected = hashlib.sha256(bytes.fromhex(h1) + bytes.fromhex(h2)).hexdigest()
    assert merkle_root([h1, h2]) == expected


def test_odd_count_duplicates_last() -> None:
    h1 = hashlib.sha256(b"x").hexdigest()
    h2 = hashlib.sha256(b"y").hexdigest()
    h3 = hashlib.sha256(b"z").hexdigest()
    p12 = hashlib.sha256(bytes.fromhex(h1) + bytes.fromhex(h2)).digest()
    p33 = hashlib.sha256(bytes.fromhex(h3) + bytes.fromhex(h3)).digest()
    expected = hashlib.sha256(p12 + p33).hexdigest()
    assert merkle_root([h1, h2, h3]) == expected


def test_deterministic() -> None:
    hashes = [hashlib.sha256(f"item{i}".encode()).hexdigest() for i in range(4)]
    r1 = merkle_root(hashes)
    r2 = merkle_root(hashes)
    assert r1 == r2
