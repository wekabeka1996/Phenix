"""Tests for vfoundation.security.redaction — Phase 1.2."""
from __future__ import annotations

from vfoundation.security.redaction import redact, SENSITIVE


def test_sensitive_fields_masked() -> None:
    data = {"secret": "s3cr3t", "api_key": "ABCDEF", "token": "tok123", "password": "pw"}
    out = redact(data)
    for key in SENSITIVE:
        assert out[key] == "***"


def test_non_sensitive_fields_preserved() -> None:
    data = {"name": "alice", "role": "admin", "secret": "x"}
    out = redact(data)
    assert out["name"] == "alice"
    assert out["role"] == "admin"


def test_empty_dict() -> None:
    assert redact({}) == {}


def test_mixed_types_preserved() -> None:
    data = {"count": 42, "flag": True, "token": "tok"}
    out = redact(data)
    assert out["count"] == 42
    assert out["flag"] is True
    assert out["token"] == "***"
