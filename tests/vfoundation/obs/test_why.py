"""Tests for vfoundation.obs.why — Phase 1.7."""
from __future__ import annotations

from vfoundation.obs.why import append_why


def test_append_why_adds_to_chain() -> None:
    chain = ["init"]
    result = append_why(chain, "step2")
    assert result == ["init", "step2"]


def test_append_why_does_not_mutate_original() -> None:
    chain = ["a", "b"]
    result = append_why(chain, "c")
    assert chain == ["a", "b"]
    assert result == ["a", "b", "c"]


def test_append_why_empty_string_skipped() -> None:
    chain = ["x"]
    result = append_why(chain, "")
    assert result == ["x"]


def test_append_why_from_empty_chain() -> None:
    result = append_why([], "first")
    assert result == ["first"]
