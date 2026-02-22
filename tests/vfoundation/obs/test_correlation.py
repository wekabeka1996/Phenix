"""Tests for vfoundation.obs.correlation — CorrelationStore."""
from __future__ import annotations

import time
from unittest.mock import patch

from vfoundation.obs.correlation import CorrelationStore


class TestPutEntryAck:
    def test_roundtrip(self) -> None:
        store = CorrelationStore(ttl_hours=1.0)
        store.put_entry_ack("ord-1", {"corr_id": "c1", "rid": "r1"})
        got = store.get_by_order_id("ord-1")
        assert got is not None
        assert got["corr_id"] == "c1"
        assert got["rid"] == "r1"
        assert "timestamp" in got

    def test_not_found(self) -> None:
        store = CorrelationStore()
        assert store.get_by_order_id("unknown") is None

    def test_overwrite(self) -> None:
        store = CorrelationStore()
        store.put_entry_ack("ord-1", {"corr_id": "v1"})
        store.put_entry_ack("ord-1", {"corr_id": "v2"})
        assert store.get_by_order_id("ord-1")["corr_id"] == "v2"


class TestPutSlTpAck:
    def test_roundtrip(self) -> None:
        store = CorrelationStore()
        store.put_sl_tp_ack("sl-1", "entry-1", "c1", "oco-1", "r1")
        got = store.get_by_order_id("sl-1")
        assert got is not None
        assert got["parent_client_order_id"] == "entry-1"
        assert got["oco_group_id"] == "oco-1"
        assert got["corr_id"] == "c1"
        assert got["rid"] == "r1"


class TestTTL:
    def test_expired_entry_returns_none(self) -> None:
        store = CorrelationStore(ttl_hours=1.0)
        store.put_entry_ack("o1", {"corr_id": "c1"})

        # Backdate timestamp beyond TTL to simulate expiry
        store.store["o1"]["timestamp"] -= 7200  # 2h ago, TTL is 1h

        assert store.get_by_order_id("o1") is None
        # entry should be deleted after expired access
        assert "o1" not in store.store

    def test_cleanup_removes_expired(self) -> None:
        store = CorrelationStore(ttl_hours=1.0)
        store.put_entry_ack("o1", {"corr_id": "c1"})
        store.put_entry_ack("o2", {"corr_id": "c2"})

        # Age o1 beyond TTL
        store.store["o1"]["timestamp"] -= 7200

        # Trigger cleanup via another put
        store.put_entry_ack("o3", {"corr_id": "c3"})

        assert "o1" not in store.store
        assert "o2" in store.store
        assert "o3" in store.store


class TestGetStats:
    def test_stats_structure(self) -> None:
        store = CorrelationStore(ttl_hours=2.0)
        store.put_entry_ack("o1", {"corr_id": "c1"})
        store.put_entry_ack("o2", {"corr_id": "c2"})
        stats = store.get_stats()
        assert stats["total_entries"] == 2
        assert stats["ttl_seconds"] == 7200

    def test_stats_after_cleanup(self) -> None:
        store = CorrelationStore(ttl_hours=1.0)
        store.put_entry_ack("o1", {"corr_id": "c1"})
        store.store["o1"]["timestamp"] -= 7200
        stats = store.get_stats()
        assert stats["total_entries"] == 0


class TestOrderIdCoercion:
    def test_int_order_id_works(self) -> None:
        store = CorrelationStore()
        store.put_entry_ack(12345, {"corr_id": "c1"})
        assert store.get_by_order_id(12345) is not None
        assert store.get_by_order_id("12345") is not None
