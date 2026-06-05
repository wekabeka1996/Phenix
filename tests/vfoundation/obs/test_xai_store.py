"""
Phase 11.1: Tests for vfoundation.obs.xai_store.

Covers: XAIRecord, InMemoryXAIStore (store/get/list_rids/clear), thread safety,
WHY-discipline enforcement, cap at max_records_per_rid.
"""
from __future__ import annotations

import threading
from typing import List

import pytest

from vfoundation.obs.xai_store import InMemoryXAIStore, XAIRecord, XAIStore


# ─────────────────────────────────────────────────────────────────────────────
# TestXAIRecord
# ─────────────────────────────────────────────────────────────────────────────


class TestXAIRecord:
    """Tests for the XAIRecord dataclass / container."""

    def test_create_minimal(self) -> None:
        """XAIRecord should be creatable with required fields only."""
        r = XAIRecord(rid="r1", step=0, verb="EVAL", why="test why")
        assert r.rid == "r1"
        assert r.step == 0
        assert r.verb == "EVAL"
        assert r.why == "test why"
        assert r.meta == {}

    def test_why_too_long_raises(self) -> None:
        """WHY > 80 chars should raise ValueError."""
        with pytest.raises(ValueError, match="80"):
            XAIRecord(rid="r1", step=0, verb="EVAL", why="x" * 81)

    def test_why_exactly_80_chars_ok(self) -> None:
        """WHY of exactly 80 chars should NOT raise."""
        r = XAIRecord(rid="r1", step=0, verb="EVAL", why="x" * 80)
        assert len(r.why) == 80

    def test_to_dict_structure(self) -> None:
        """to_dict() should include all fields."""
        r = XAIRecord(
            rid="r2", step=1, verb="OPEN", why="position opened",
            payload_summary="qty=1.0", meta={"source": "fsm"}
        )
        d = r.to_dict()
        assert d["rid"] == "r2"
        assert d["step"] == 1
        assert d["verb"] == "OPEN"
        assert d["why"] == "position opened"
        assert d["payload_summary"] == "qty=1.0"
        assert d["meta"]["source"] == "fsm"


# ─────────────────────────────────────────────────────────────────────────────
# TestInMemoryXAIStore
# ─────────────────────────────────────────────────────────────────────────────


class TestInMemoryXAIStore:
    """Tests for InMemoryXAIStore."""

    @pytest.fixture()
    def store(self) -> InMemoryXAIStore:
        return InMemoryXAIStore()

    def test_is_xai_store_subclass(self, store: InMemoryXAIStore) -> None:
        """InMemoryXAIStore must be a subclass of XAIStore ABC."""
        assert isinstance(store, XAIStore)

    def test_store_and_get(self, store: InMemoryXAIStore) -> None:
        """store() then get() should return the stored record."""
        record = XAIRecord(rid="r1", step=0, verb="EVAL", why="test")
        store.store("r1", record)
        records = store.get("r1")
        assert len(records) == 1
        assert records[0].verb == "EVAL"

    def test_get_unknown_rid_returns_empty(self, store: InMemoryXAIStore) -> None:
        """get() for unknown rid should return []."""
        assert store.get("nonexistent-rid") == []

    def test_get_returns_sorted_by_step(self, store: InMemoryXAIStore) -> None:
        """get() should return records sorted by step, not insertion order."""
        store.store("r1", XAIRecord(rid="r1", step=2, verb="CLOSE", why="step 2"))
        store.store("r1", XAIRecord(rid="r1", step=0, verb="EVAL", why="step 0"))
        store.store("r1", XAIRecord(rid="r1", step=1, verb="OPEN", why="step 1"))
        records = store.get("r1")
        steps = [r.step for r in records]
        assert steps == [0, 1, 2], f"expected sorted steps [0,1,2], got {steps}"

    def test_list_rids(self, store: InMemoryXAIStore) -> None:
        """list_rids() should return all stored request IDs."""
        for rid in ["r3", "r1", "r2"]:
            store.store(rid, XAIRecord(rid=rid, step=0, verb="EVAL", why="test"))
        rids = store.list_rids()
        assert sorted(rids) == ["r1", "r2", "r3"]

    def test_clear_removes_all(self, store: InMemoryXAIStore) -> None:
        """clear() should remove all stored records."""
        store.store("r1", XAIRecord(rid="r1", step=0, verb="EVAL", why="test"))
        store.clear()
        assert store.get("r1") == []
        assert store.list_rids() == []

    def test_cap_at_max_records_per_rid(self) -> None:
        """Records exceeding max_records_per_rid should be dropped."""
        store = InMemoryXAIStore(max_records_per_rid=3)
        for i in range(5):
            store.store("r1", XAIRecord(rid="r1", step=i, verb="EVAL", why="test"))
        records = store.get("r1")
        assert len(records) <= 3, f"expected at most 3 records, got {len(records)}"

    def test_thread_safety(self, store: InMemoryXAIStore) -> None:
        """Concurrent store() calls must not corrupt the store. Thread-safe test."""
        errors: List[Exception] = []
        rid = "concurrent-rid"

        def worker(step_start: int) -> None:
            try:
                for i in range(step_start, step_start + 20):
                    store.store(rid, XAIRecord(rid=rid, step=i, verb="EVAL", why="concurrent"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i * 20,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"got exceptions during concurrent access: {errors}"
        records = store.get(rid)
        assert len(records) > 0, "expected records to be stored after concurrent writes"
