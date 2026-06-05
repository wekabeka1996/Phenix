"""
R4 audit fix: TASK40 lifecycle_id cache must NOT be updated by close fills.

Root cause: TASK40 in _apply_fill_bookkeeping() ran for ALL fills (ENTRY + CLOSE/SL/TP),
replacing the aurora entry lifecycle_id in _last_lifecycle_ikey_by_symbol with the
close order's idempotent_key. finalize_close() then received a key never seeded in the
ledger → silent KeyError → no FINAL row (18/19 positions affected in production).

Fix: Added `order_kind == "ENTRY"` guard at TASK40 lifecycle_id cache write.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_position.orchestration.event_handlers import (
    EPEventHandlers,
)
from apps.reference.domains.execution_position.telemetry.lifecycle_stats_ledger import (
    ExecutionLifecycleStatsLedger,
    FINAL_ROW_STATUS,
    PROVISIONAL_ROW_STATUS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(tmp_path: Path) -> ExecutionLifecycleStatsLedger:
    return ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_800_000_000_000,
    )


def _make_mock_fsm(ledger: ExecutionLifecycleStatsLedger) -> MagicMock:
    fsm = MagicMock()
    fsm._lifecycle_stats_ledger = ledger
    fsm._last_lifecycle_rid_by_symbol = {}
    fsm._last_lifecycle_fill_price_by_symbol = {}
    fsm._last_realized_pnl_by_symbol = {}
    fsm._last_close_reason_by_symbol = {}
    fsm._last_lifecycle_ikey_by_symbol = {}
    fsm._last_trade_id_by_symbol = {}
    fsm._last_entry_side_by_symbol = {}
    fsm._accumulated_fees_by_symbol = {}
    fsm._close_accounting_truth_by_symbol = {}
    fsm._pending_intent_data = {}
    fsm._pending_entry_meta = {}
    fsm._pending_brackets = {}
    fsm._open_regime_by_symbol = {}
    fsm._open_strategy_by_symbol = {}
    fsm._last_position_closed_ts = {}
    fsm._prev_position_amts = {}
    fsm._mark_processed_event.return_value = True
    fsm.exposure_guard.state.postfill_reservations = {}
    fsm.exposure_guard.expire_stale.return_value = []
    fsm.exposure_guard.get_exposure_summary.return_value = {}
    fsm.exposure_guard.on_portfolio.return_value = None
    fsm._get_async_loop.return_value = None
    fsm._latest_portfolio_state = {}
    fsm.bus = None
    fsm.get_recent_terminal_close_proof.return_value = None
    fsm.order_index = None
    fsm.fsm.order_index = None
    fsm._clear_bracket_owner.return_value = None
    fsm._apply_authoritative_local_close_reset.return_value = None
    fsm.order_guardian = None
    return fsm


def _make_entry_fill_event(symbol: str = "BTCUSDT", lifecycle_id: str = "aurora_BTCUSDT_1000") -> SimpleNamespace:
    """Simulate a final ENTRY fill whose clientOrderId maps to an aurora lifecycle_id."""
    return SimpleNamespace(
        pld={
            "orderId": "EX-ENTRY-001",
            "symbol": symbol,
            "quantity": "0.01",
            "rid": lifecycle_id,
            "clientOrderId": f"ENTRY-{symbol}-open-1",
            "tradeId": "T-1001",
            "commission": "0.05",
            "commissionAsset": "USDT",
            "realizedPnl": "0.0",
            "price": "80000.0",
            "side": "BUY",
            "status": "FILLED",
        },
        rid=lifecycle_id,
    )


def _make_close_fill_event(
    symbol: str = "BTCUSDT",
    client_order_id: str = "ppsreq:pps:BTCUSDT:1000:1",
    order_id: str = "EX-CLOSE-001",
    close_kind: str = "CLOSE",  # CLOSE | SL | TP
    idempotent_key: str = "ppsreq:pps:BTCUSDT:1000:1",
) -> SimpleNamespace:
    return SimpleNamespace(
        pld={
            "orderId": order_id,
            "symbol": symbol,
            "quantity": "0.01",
            "rid": client_order_id,
            "clientOrderId": client_order_id,
            "tradeId": "T-2001",
            "commission": "0.05",
            "commissionAsset": "USDT",
            "realizedPnl": "-5.0",
            "price": "79500.0",
            "side": "SELL",
            "status": "FILLED",
            "close_reason": close_kind,
        },
        rid=client_order_id,
    )


def _entry_order_ref(lifecycle_id: str = "aurora_BTCUSDT_1000") -> SimpleNamespace:
    return SimpleNamespace(idempotent_key=lifecycle_id, side="BUY")


def _close_order_ref(idempotent_key: str = "ppsreq:pps:BTCUSDT:1000:1") -> SimpleNamespace:
    return SimpleNamespace(idempotent_key=idempotent_key, side="SELL")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTask40CloseFillGuard:
    """TASK40 lifecycle_id cache must only be updated by ENTRY fills."""

    def test_entry_fill_sets_lifecycle_ikey(self, tmp_path):
        """ENTRY fill populates _last_lifecycle_ikey_by_symbol."""
        ledger = _make_ledger(tmp_path)
        fsm = _make_mock_fsm(ledger)
        entry_ref = _entry_order_ref("aurora_BTCUSDT_1000")
        fsm.fsm.order_index = MagicMock()
        fsm.fsm.order_index.get.return_value = entry_ref

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            None,
        ), patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
        ) as mock_log, patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
        ) as mock_clk:
            mock_clk.return_value.now_ms.return_value = 1_800_000_000_000
            mock_log.return_value.write.return_value = None
            EPEventHandlers(fsm).on_order_fill(
                _make_entry_fill_event("BTCUSDT", "aurora_BTCUSDT_1000"))

        assert fsm._last_lifecycle_ikey_by_symbol.get(
            "BTCUSDT") == "aurora_BTCUSDT_1000"

    def test_pps_close_fill_does_not_overwrite_entry_lifecycle_ikey(self, tmp_path):
        """
        PPS close fill MUST NOT overwrite the aurora entry lifecycle_id.
        This was the root cause of 17/18 missing FINAL lifecycle_stats rows in production.
        """
        ledger = _make_ledger(tmp_path)
        fsm = _make_mock_fsm(ledger)
        # Simulate state after entry fill: aurora lifecycle_id is already cached
        fsm._last_lifecycle_ikey_by_symbol["BTCUSDT"] = "aurora_BTCUSDT_1000"

        close_ref = _close_order_ref("ppsreq:pps:BTCUSDT:2000:1")
        fsm.fsm.order_index = MagicMock()
        fsm.fsm.order_index.get.return_value = close_ref

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            None,
        ), patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
        ) as mock_log, patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
        ) as mock_clk:
            mock_clk.return_value.now_ms.return_value = 1_800_000_001_000
            mock_log.return_value.write.return_value = None
            EPEventHandlers(fsm).on_order_fill(
                _make_close_fill_event(
                    "BTCUSDT",
                    client_order_id="ppsreq:pps:BTCUSDT:2000:1",
                    order_id="EX-CLOSE-001",
                    close_kind="CLOSE",
                )
            )

        # Aurora lifecycle_id must be preserved — not overwritten by ppsreq key
        assert fsm._last_lifecycle_ikey_by_symbol.get(
            "BTCUSDT") == "aurora_BTCUSDT_1000"

    def test_sl_bracket_fill_does_not_overwrite_entry_lifecycle_ikey(self, tmp_path):
        """SL bracket fill (UUID idempotent_key) must not overwrite aurora entry lifecycle_id."""
        ledger = _make_ledger(tmp_path)
        fsm = _make_mock_fsm(ledger)
        fsm._last_lifecycle_ikey_by_symbol["XRPUSDT"] = "aurora_XRPUSDT_5000"

        sl_ref = _close_order_ref("a38c5227-7285-450b-bd9d-cb9ba6022c5a")
        fsm.fsm.order_index = MagicMock()
        fsm.fsm.order_index.get.return_value = sl_ref

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            None,
        ), patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
        ) as mock_log, patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
        ) as mock_clk:
            mock_clk.return_value.now_ms.return_value = 1_800_000_002_000
            mock_log.return_value.write.return_value = None
            EPEventHandlers(fsm).on_order_fill(
                _make_close_fill_event(
                    "XRPUSDT",
                    client_order_id="aurora_XRPUSDT_5000:SL",
                    order_id="EX-SL-001",
                    close_kind="SL",
                )
            )

        assert fsm._last_lifecycle_ikey_by_symbol.get(
            "XRPUSDT") == "aurora_XRPUSDT_5000"

    def test_tp_bracket_fill_does_not_overwrite_entry_lifecycle_ikey(self, tmp_path):
        """TP bracket fill (UUID idempotent_key) must not overwrite aurora entry lifecycle_id."""
        ledger = _make_ledger(tmp_path)
        fsm = _make_mock_fsm(ledger)
        fsm._last_lifecycle_ikey_by_symbol["BNBUSDT"] = "aurora_BNBUSDT_7000"

        tp_ref = _close_order_ref("08e86a93-32a6-458b-b94c-e1e4e06932d6")
        fsm.fsm.order_index = MagicMock()
        fsm.fsm.order_index.get.return_value = tp_ref

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            None,
        ), patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
        ) as mock_log, patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
        ) as mock_clk:
            mock_clk.return_value.now_ms.return_value = 1_800_000_003_000
            mock_log.return_value.write.return_value = None
            EPEventHandlers(fsm).on_order_fill(
                _make_close_fill_event(
                    "BNBUSDT",
                    client_order_id="aurora_BNBUSDT_7000:TP",
                    order_id="EX-TP-001",
                    close_kind="TP",
                )
            )

        assert fsm._last_lifecycle_ikey_by_symbol.get(
            "BNBUSDT") == "aurora_BNBUSDT_7000"

    def test_finalize_close_writes_final_row_after_pps_close(self, tmp_path):
        """
        End-to-end: entry fill seeds lifecycle, PPS close fill must NOT corrupt the key,
        finalize_close() must write a FINAL row using the aurora entry lifecycle_id.
        """
        ledger = _make_ledger(tmp_path)
        # Seed the entry lifecycle
        ledger.seed_entry(
            lifecycle_id="aurora_BTCUSDT_1000",
            entry_rid="ENTRY-BTCUSDT-open-1",
            symbol="BTCUSDT",
            side="BUY",
            entry_ts_ms=1_800_000_000_000,
            entry_price=80000.0,
            qty=0.01,
        )

        fsm = _make_mock_fsm(ledger)
        fsm._last_lifecycle_ikey_by_symbol["BTCUSDT"] = "aurora_BTCUSDT_1000"

        close_ref = _close_order_ref("ppsreq:pps:BTCUSDT:2000:1")
        fsm.fsm.order_index = MagicMock()
        fsm.fsm.order_index.get.return_value = close_ref

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            None,
        ), patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
        ) as mock_log, patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
        ) as mock_clk:
            mock_clk.return_value.now_ms.return_value = 1_800_000_001_000
            mock_log.return_value.write.return_value = None
            EPEventHandlers(fsm).on_order_fill(
                _make_close_fill_event(
                    "BTCUSDT",
                    client_order_id="ppsreq:pps:BTCUSDT:2000:1",
                    order_id="EX-CLOSE-001",
                    close_kind="CLOSE",
                )
            )

        # lifecycle_id preserved — now simulate finalize
        assert fsm._last_lifecycle_ikey_by_symbol.get(
            "BTCUSDT") == "aurora_BTCUSDT_1000"

        ledger.finalize_close(
            lifecycle_id="aurora_BTCUSDT_1000",
            close_ts_ms=1_800_000_001_000,
            close_actor="EXECUTION_POSITION",
            close_reason="CLOSE",
            gross_pnl=-5.0,
            fees=0.05,
            net_pnl=-5.05,
        )

        final = ledger.get_latest(lifecycle_id="aurora_BTCUSDT_1000")
        assert final is not None
        assert final.row_status == FINAL_ROW_STATUS
        assert final.provisional_status is None
        assert final.net_pnl == pytest.approx(-5.05)
        assert final.close_reason == "CLOSE"

    def test_entry_fill_when_cache_empty_still_seeds_correctly(self, tmp_path):
        """ENTRY fill when lifecycle cache is empty seeds the aurora lifecycle_id correctly."""
        ledger = _make_ledger(tmp_path)
        fsm = _make_mock_fsm(ledger)
        # Cache is empty (fresh symbol)
        assert "ETHUSDT" not in fsm._last_lifecycle_ikey_by_symbol

        entry_ref = _entry_order_ref("aurora_ETHUSDT_3000")
        fsm.fsm.order_index = MagicMock()
        fsm.fsm.order_index.get.return_value = entry_ref

        ev = _make_entry_fill_event("ETHUSDT", "aurora_ETHUSDT_3000")
        ev.pld["clientOrderId"] = "ENTRY-ETHUSDT-open-1"
        ev.pld["symbol"] = "ETHUSDT"

        with patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
            None,
        ), patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
        ) as mock_log, patch(
            "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
        ) as mock_clk:
            mock_clk.return_value.now_ms.return_value = 1_800_000_004_000
            mock_log.return_value.write.return_value = None
            EPEventHandlers(fsm).on_order_fill(ev)

        assert fsm._last_lifecycle_ikey_by_symbol.get(
            "ETHUSDT") == "aurora_ETHUSDT_3000"
        seeded = ledger.get_latest(lifecycle_id="aurora_ETHUSDT_3000")
        assert seeded is not None
        assert seeded.provisional_status == "entry_filled"
