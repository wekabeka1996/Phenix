"""Tests for vfoundation.core.adapters.idempotency_ledger — IdempotencyLedger."""
from __future__ import annotations

from vfoundation.core.adapters.idempotency_ledger import IdempotencyLedger, LedgerEntry


class TestCheckAndStore:
    def test_new_key_returns_false(self) -> None:
        ledger = IdempotencyLedger(ttl_seconds=60, max_entries=100)
        is_dup, event = ledger.check_and_store("k1", "PLACED", {"order_id": "1"})
        assert is_dup is False
        assert event is None

    def test_duplicate_returns_true(self) -> None:
        ledger = IdempotencyLedger(ttl_seconds=60, max_entries=100)
        ev = {"status": "FILLED"}
        ledger.check_and_store("k1", "PLACED", {"order_id": "1"}, event=ev)
        is_dup, event = ledger.check_and_store("k1", "PLACED", {"order_id": "1"})
        assert is_dup is True
        assert event == ev

    def test_expired_entry_treated_as_new(self) -> None:
        ledger = IdempotencyLedger(ttl_seconds=1, max_entries=100)
        ledger.check_and_store("k1", "PLACED", {"a": 1})
        # Backdate the entry
        ledger._ledger["k1"].first_seen_ts -= 1000
        is_dup, _ = ledger.check_and_store("k1", "PLACED", {"a": 1})
        assert is_dup is False


class TestGet:
    def test_get_existing(self) -> None:
        ledger = IdempotencyLedger()
        ledger.check_and_store("k1", "OK", {"x": 1})
        entry = ledger.get("k1")
        assert isinstance(entry, LedgerEntry)
        assert entry.key == "k1"
        assert entry.last_status == "OK"

    def test_get_missing(self) -> None:
        ledger = IdempotencyLedger()
        assert ledger.get("nope") is None

    def test_get_expired(self) -> None:
        ledger = IdempotencyLedger(ttl_seconds=1)
        ledger.check_and_store("k1", "OK", {"x": 1})
        ledger._ledger["k1"].first_seen_ts -= 1000
        assert ledger.get("k1") is None


class TestLRUEviction:
    def test_evicts_when_full(self) -> None:
        ledger = IdempotencyLedger(max_entries=2)
        ledger.check_and_store("k1", "OK", {"a": 1})
        ledger.check_and_store("k2", "OK", {"b": 2})
        ledger.check_and_store("k3", "OK", {"c": 3})  # evicts k1
        assert ledger.get("k1") is None
        assert ledger.get("k2") is not None
        assert ledger.get("k3") is not None


class TestClearAndSize:
    def test_clear(self) -> None:
        ledger = IdempotencyLedger()
        ledger.check_and_store("k1", "OK", {"x": 1})
        assert ledger.size() == 1
        ledger.clear()
        assert ledger.size() == 0

    def test_stats(self) -> None:
        ledger = IdempotencyLedger(ttl_seconds=120, max_entries=500)
        ledger.check_and_store("k1", "OK", {})
        s = ledger.stats()
        assert s["size"] == 1
        assert s["max_entries"] == 500
        assert s["ttl_seconds"] == 120
        assert s["oldest_entry_age_seconds"] is not None


class TestLedgerEntry:
    def test_dataclass(self) -> None:
        e = LedgerEntry(key="k1", first_seen_ts=1.0, last_status="OK",
                        last_payload_digest="abc123")
        assert e.key == "k1"
        assert e.last_event is None
