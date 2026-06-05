"""Tests for vfoundation.obs.tracing — Phase 1.8."""
from __future__ import annotations

from vfoundation.obs.tracing import new_span


def test_new_span_returns_hex_id() -> None:
    span_id, parent = new_span()
    assert isinstance(span_id, str)
    assert len(span_id) == 32  # uuid4 hex is 32 chars
    int(span_id, 16)  # must be valid hex


def test_new_span_no_parent() -> None:
    _, parent = new_span()
    assert parent is None


def test_new_span_with_parent() -> None:
    span_id, parent = new_span(parent="abc123")
    assert parent == "abc123"
    assert span_id != "abc123"


def test_new_span_unique_ids() -> None:
    ids = {new_span()[0] for _ in range(100)}
    assert len(ids) == 100
