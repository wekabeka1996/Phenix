"""Tests for vfoundation.core.idempotency.errors — all error classes, WHY ≤80 enforcement."""

from __future__ import annotations

import pytest

from vfoundation.core.idempotency.errors import (
    BusyError,
    CBOpenError,
    ConflictError,
    IdempotencyError,
    MissingError,
    StoreError,
    TimeoutError,
)


# ── IdempotencyError (base) ──────────────────────────────────────────────


class TestIdempotencyError:
    def test_code(self) -> None:
        e = IdempotencyError(why="test reason")
        assert e.code == "ERR.idemp.base"

    def test_why_stored(self) -> None:
        e = IdempotencyError(why="some reason")
        assert e.why == "some reason"

    def test_details_stored(self) -> None:
        e = IdempotencyError(why="reason", details="extra info")
        assert e.details == "extra info"

    def test_message_includes_code_and_why(self) -> None:
        e = IdempotencyError(why="test")
        assert "ERR.idemp.base" in str(e)
        assert "test" in str(e)

    def test_message_includes_details(self) -> None:
        e = IdempotencyError(why="reason", details="d1")
        assert "d1" in str(e)

    def test_why_80_chars_accepted(self) -> None:
        e = IdempotencyError(why="x" * 80)
        assert len(e.why) == 80

    def test_why_81_chars_rejected(self) -> None:
        with pytest.raises(ValueError, match="WHY must be ≤80"):
            IdempotencyError(why="x" * 81)

    def test_is_exception(self) -> None:
        e = IdempotencyError(why="test")
        assert isinstance(e, Exception)


# ── ConflictError ─────────────────────────────────────────────────────────


class TestConflictError:
    def test_code(self) -> None:
        e = ConflictError(key="k1", expected_digest="aaa", actual_digest="bbb")
        assert e.code == "ERR.idemp.conflict"

    def test_why_contains_key(self) -> None:
        e = ConflictError(key="order-123", expected_digest="a" * 32, actual_digest="b" * 32)
        assert "order-123" in e.why

    def test_details_contain_digests(self) -> None:
        e = ConflictError(key="k", expected_digest="exp123", actual_digest="act456")
        assert e.details is not None
        assert "exp123" in e.details
        assert "act456" in e.details

    def test_is_idempotency_error(self) -> None:
        e = ConflictError(key="k", expected_digest="a", actual_digest="b")
        assert isinstance(e, IdempotencyError)

    def test_long_key_truncated_in_why(self) -> None:
        long_key = "k" * 100
        e = ConflictError(key=long_key, expected_digest="a", actual_digest="b")
        assert len(e.why) <= 80


# ── BusyError ─────────────────────────────────────────────────────────────


class TestBusyError:
    def test_code(self) -> None:
        e = BusyError(key="k1", owner="worker-2")
        assert e.code == "ERR.idemp.busy"

    def test_why_contains_key_and_owner(self) -> None:
        e = BusyError(key="order-1", owner="w3")
        assert "order-1" in e.why
        assert "w3" in e.why

    def test_why_within_80(self) -> None:
        e = BusyError(key="k" * 50, owner="o" * 50)
        assert len(e.why) <= 80

    def test_is_idempotency_error(self) -> None:
        assert isinstance(BusyError(key="k", owner="o"), IdempotencyError)


# ── TimeoutError ──────────────────────────────────────────────────────────


class TestTimeoutError:
    def test_code(self) -> None:
        e = TimeoutError(operation="reserve", timeout_ms=100, elapsed_ms=150)
        assert e.code == "ERR.idemp.timeout"

    def test_why_contains_operation(self) -> None:
        e = TimeoutError(operation="reserve", timeout_ms=100, elapsed_ms=150)
        assert "reserve" in e.why

    def test_why_contains_times(self) -> None:
        e = TimeoutError(operation="confirm", timeout_ms=200, elapsed_ms=300)
        assert "300" in e.why and "200" in e.why


# ── CBOpenError ───────────────────────────────────────────────────────────


class TestCBOpenError:
    def test_code(self) -> None:
        e = CBOpenError(operation="reserve")
        assert e.code == "ERR.idemp.cb_open"

    def test_why_contains_operation(self) -> None:
        e = CBOpenError(operation="confirm")
        assert "confirm" in e.why

    def test_is_idempotency_error(self) -> None:
        assert isinstance(CBOpenError(operation="x"), IdempotencyError)


# ── MissingError ──────────────────────────────────────────────────────────


class TestMissingError:
    def test_code(self) -> None:
        e = MissingError(key="k1", operation="confirm")
        assert e.code == "ERR.idemp.missing"

    def test_why_contains_key_and_op(self) -> None:
        e = MissingError(key="order-1", operation="release")
        assert "order-1" in e.why
        assert "release" in e.why

    def test_long_key_fits_80(self) -> None:
        e = MissingError(key="k" * 100, operation="confirm")
        assert len(e.why) <= 80


# ── StoreError ────────────────────────────────────────────────────────────


class TestStoreError:
    def test_code(self) -> None:
        e = StoreError(operation="reserve", backend_error="redis down")
        assert e.code == "ERR.idemp.store"

    def test_why_contains_operation(self) -> None:
        e = StoreError(operation="confirm", backend_error="timeout")
        assert "confirm" in e.why

    def test_details_truncated(self) -> None:
        long_err = "x" * 200
        e = StoreError(operation="reserve", backend_error=long_err)
        assert e.details is not None
        assert len(e.details) <= 60

    def test_empty_backend_error(self) -> None:
        e = StoreError(operation="reserve", backend_error="")
        assert e.details is None
