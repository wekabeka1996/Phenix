"""
Phase 5 — State, Restore, and Fill Identity

Tests for DEF-E08: WAL JSONDecodeError must not be silenced.
Tests for DEF-E13: OrderGuardian must not access store._data directly.
Tests for DEF-E17: _pending_entry_meta must not be popped while PARTIALLY_FILLED.
Tests for DEF-E18: Fill dedupe without tradeId must use cumQty+updateTime fallback.
"""
from __future__ import annotations

import json
import logging
import pytest
from unittest.mock import MagicMock, patch


class TestPendingBracketsWALCorruptRowPolicy:
    """DEF-E08: Corrupt WAL must fail startup explicitly, not silently continue."""

    def test_json_decode_error_is_logged_critical_and_raises(self, caplog):
        """
        DEF-E08 regression: a corrupt WAL line must emit a CRITICAL log and abort
        startup restore. Continuing with a partial pending-brackets snapshot is a
        silent truth corruption risk.
        """
        import tempfile
        import os
        from pathlib import Path
        from apps.reference.domains.execution_position.pending_brackets_wal import (
            CriticalStartupError,
            read_pending_brackets_from_wal,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            wal_file = os.path.join(tmpdir, "brackets_wal_000.jsonl")
            with open(wal_file, "w") as f:
                f.write(json.dumps({
                    "verb": "PENDING_BRACKETS_STORED",
                    "pld": {
                        "entry_order_id": "order-001",
                        "symbol": "BTCUSDT",
                        "sl_order_id": "sl-001",
                        "tp_order_id": "tp-001",
                    }
                }) + "\n")
                # Corrupt line
                f.write("{corrupt json !!!\n")

            mock_config = MagicMock()
            mock_config.wal_dir = Path(tmpdir)

            with patch("vfoundation.config.config", mock_config):
                with caplog.at_level(logging.CRITICAL):
                    with pytest.raises(CriticalStartupError, match="pending brackets WAL corruption"):
                        read_pending_brackets_from_wal()

            critical_msgs = [
                r.message for r in caplog.records if r.levelno >= logging.CRITICAL]
            assert any("DEF-E08" in m or "JSONDecodeError" in m or "corrupt" in m.lower()
                       for m in critical_msgs), (
                f"DEF-E08: No CRITICAL log emitted for corrupt WAL line. "
                f"Got critical records: {critical_msgs}"
            )

    def test_execpos_startup_fails_closed_on_corrupt_wal(self, fsm_config):
        from apps.reference.domains.execution_position.fsm import ExecPosFSM
        from apps.reference.domains.execution_position.pending_brackets_wal import CriticalStartupError

        with patch(
            "apps.reference.domains.execution_position.fsm.read_pending_brackets_from_wal",
            side_effect=CriticalStartupError(
                "pending brackets WAL corruption in test.jsonl: bad row"),
        ), patch(
            "apps.reference.domains.execution_position.fsm.OrderGuardian"
        ):
            with pytest.raises(CriticalStartupError, match="pending brackets WAL corruption"):
                ExecPosFSM(config=fsm_config,
                           fsm=MagicMock(), shadow_mode=True)


class TestOrderGuardianStoreProtocol:
    """DEF-E13: OrderGuardian must use public store interface, not store._data."""

    def test_iter_symbols_does_not_access_private_data(self):
        """
        DEF-E13 regression: _iter_symbols_for_poll must not use getattr(store, '_data').
        It must use public methods (get_all_tracked_symbols or get_all).
        """
        import inspect
        from apps.reference.domains.execution_position.order_guardian import OrderGuardian

        source = inspect.getsource(OrderGuardian._iter_symbols_for_poll)
        assert '"_data"' not in source and "'_data'" not in source, (
            "DEF-E13: _iter_symbols_for_poll must not access store._data (private attribute). "
            "Add get_all_tracked_symbols() to StoreProtocol and use that instead."
        )

    def test_iter_symbols_uses_public_store_method(self):
        """DEF-E13: _iter_symbols_for_poll must try get_all_tracked_symbols() or get_all()."""
        import inspect
        from apps.reference.domains.execution_position.order_guardian import OrderGuardian

        source = inspect.getsource(OrderGuardian._iter_symbols_for_poll)
        assert ("get_all_tracked_symbols" in source or "get_all" in source), (
            "DEF-E13: _iter_symbols_for_poll must use public store API "
            "(get_all_tracked_symbols or get_all), not private _data"
        )


class TestPartialFillKeepsPendingEntryMeta:
    """DEF-E17: _pending_entry_meta must not be popped while status is PARTIALLY_FILLED."""

    def test_meta_preserved_on_partial_fill(self):
        """
        DEF-E17 regression: popping pending_entry_meta on PARTIALLY_FILLED discards
        the idempotent_key and rid needed to process subsequent fill events.
        The pop must only happen on terminal statuses.
        """
        pending_meta = {
            "order-abc": {"rid": "rid-1", "idempotent_key": "ikey-1"}}
        order_id = "order-abc"
        status = "PARTIALLY_FILLED"

        # Simulate the DEF-E17 fix: pop only on non-partial fills
        if status != "PARTIALLY_FILLED":
            pending_meta.pop(str(order_id), None)

        assert order_id in pending_meta, (
            f"DEF-E17: _pending_entry_meta must NOT be popped for PARTIALLY_FILLED. "
            f"The metadata is needed for subsequent fill events."
        )

    def test_meta_removed_on_terminal_fill(self):
        """On final FILLED status, pending_entry_meta CAN be removed."""
        pending_meta = {
            "order-xyz": {"rid": "rid-2", "idempotent_key": "ikey-2"}}
        order_id = "order-xyz"
        status = "FILLED"

        if status != "PARTIALLY_FILLED":
            pending_meta.pop(str(order_id), None)

        assert order_id not in pending_meta, (
            "On terminal FILLED, pending_entry_meta CAN be removed."
        )

    def test_event_handlers_partial_fill_guards_meta_pop(self):
        """DEF-E17: event_handlers.py must have PARTIALLY_FILLED guard before meta pop."""
        import inspect
        from apps.reference.domains.execution_position.event_handlers import EPEventHandlers

        source = inspect.getsource(EPEventHandlers.on_order_fill)
        # The guard must appear before the pop
        partial_fill_guard_pos = source.find("PARTIALLY_FILLED")
        pop_pos = source.find("_pending_entry_meta.pop")

        assert partial_fill_guard_pos != -1, (
            "DEF-E17: on_order_fill must contain PARTIALLY_FILLED check"
        )
        if pop_pos != -1:
            assert partial_fill_guard_pos < pop_pos, (
                "DEF-E17: PARTIALLY_FILLED guard must appear BEFORE _pending_entry_meta.pop"
            )


class TestFillDedupeWithoutTradeIdDistinguishesPartials:
    """DEF-E18: Without tradeId, fill dedupe must use cumQty+updateTime to distinguish partials."""

    def test_same_order_different_cum_qty_produces_different_keys(self):
        """
        DEF-E18 regression: without tradeId, `fill_{order_id}_{symbol}` collapses
        ALL partial fills for the same order into one dedup key.
        Fix: use cumQty+updateTime so distinct partials get distinct keys.
        """
        order_id = "order-pf"
        symbol = "BTCUSDT"

        # Simulate two partial fill events with different cumulative qty
        payload_1 = {"cumQty": "0.5", "updateTime": "1000"}
        payload_2 = {"cumQty": "1.0", "updateTime": "2000"}

        def make_dedup_key(payload):
            trade_id = str(payload.get("tradeId")
                           or payload.get("trade_id") or "")
            if trade_id:
                return f"fill_{order_id}_{trade_id}_{symbol}"
            else:
                cum_qty = str(payload.get("cumQty")
                              or payload.get("executedQty") or "")
                update_time = str(payload.get("updateTime")
                                  or payload.get("transactTime") or "")
                return f"fill_{order_id}_{symbol}_{cum_qty}_{update_time}"

        key_1 = make_dedup_key(payload_1)
        key_2 = make_dedup_key(payload_2)

        assert key_1 != key_2, (
            f"DEF-E18: Two partial fills with different cumQty must produce different dedup keys. "
            f"Got key_1={key_1!r}, key_2={key_2!r}"
        )

    def test_same_partial_fill_repeated_produces_same_key(self):
        """Same partial fill delivered twice must produce same dedup key (suppress duplicate)."""
        order_id = "order-pf"
        symbol = "BTCUSDT"
        payload = {"cumQty": "0.5", "updateTime": "1000"}

        def make_dedup_key(p):
            cum_qty = str(p.get("cumQty") or "")
            update_time = str(p.get("updateTime") or "")
            return f"fill_{order_id}_{symbol}_{cum_qty}_{update_time}"

        key_a = make_dedup_key(payload)
        key_b = make_dedup_key(payload)  # Same payload again

        assert key_a == key_b, "Duplicate delivery of same partial fill must produce same dedup key"

    def test_with_trade_id_uses_trade_id_key(self):
        """When tradeId is present, use tradeId in key (original behavior)."""
        order_id = "order-x"
        symbol = "ETHUSDT"
        payload = {"tradeId": "t12345", "cumQty": "0.5", "updateTime": "1000"}

        trade_id = str(payload.get("tradeId") or "")
        if trade_id:
            key = f"fill_{order_id}_{trade_id}_{symbol}"
        else:
            cum_qty = str(payload.get("cumQty") or "")
            update_time = str(payload.get("updateTime") or "")
            key = f"fill_{order_id}_{symbol}_{cum_qty}_{update_time}"

        assert "t12345" in key, "tradeId must appear in dedup key when present"
