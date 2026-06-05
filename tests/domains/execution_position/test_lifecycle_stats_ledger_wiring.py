from __future__ import annotations

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


class _CaptureBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str | None, object, dict]] = []

    def emit(self, topic: str, payload=None, why=None, data_ref=None, **kwargs) -> None:
        self.events.append((topic, payload or {}, why, data_ref, kwargs))


def _make_mock_fsm(ledger: ExecutionLifecycleStatsLedger):
    mock_fsm = MagicMock()
    mock_fsm._lifecycle_stats_ledger = ledger
    mock_fsm._last_lifecycle_rid_by_symbol = {}
    mock_fsm._last_lifecycle_fill_price_by_symbol = {}
    mock_fsm._last_realized_pnl_by_symbol = {}
    mock_fsm._last_close_reason_by_symbol = {}
    mock_fsm._last_lifecycle_ikey_by_symbol = {}
    mock_fsm._last_trade_id_by_symbol = {}
    mock_fsm._last_entry_side_by_symbol = {}
    mock_fsm._accumulated_fees_by_symbol = {}
    mock_fsm._close_accounting_truth_by_symbol = {}
    mock_fsm._pending_intent_data = {}
    mock_fsm._pending_entry_meta = {}
    mock_fsm._pending_brackets = {}
    mock_fsm._open_regime_by_symbol = {}
    mock_fsm._open_strategy_by_symbol = {}
    mock_fsm._last_position_closed_ts = {}
    mock_fsm._prev_position_amts = {}
    mock_fsm._mark_processed_event.return_value = True
    mock_fsm.exposure_guard.state.postfill_reservations = {}
    mock_fsm.exposure_guard.expire_stale.return_value = []
    mock_fsm.exposure_guard.get_exposure_summary.return_value = {}
    mock_fsm.exposure_guard.on_portfolio.return_value = None
    mock_fsm._get_async_loop.return_value = None
    mock_fsm._latest_portfolio_state = {}
    mock_fsm.bus = _CaptureBus()
    mock_fsm.get_recent_terminal_close_proof.return_value = None
    mock_fsm.order_index = None
    mock_fsm.fsm.order_index = None
    mock_fsm._clear_bracket_owner.return_value = None
    mock_fsm._apply_authoritative_local_close_reset.return_value = None
    mock_fsm.order_guardian = None
    return mock_fsm


def _make_fill_event():
    return SimpleNamespace(
        pld={
            "orderId": "EX-ORD-001",
            "symbol": "BTCUSDT",
            "quantity": "0.02",
            "rid": "ENTRY-BTCUSDT-open-1",
            "clientOrderId": "ENTRY-BTCUSDT-open-1",
            "tradeId": "10001",
            "commission": "0.05",
            "commissionAsset": "USDT",
            "realizedPnl": "0.0",
            "price": "50000.0",
            "side": "BUY",
            "status": "FILLED",
        },
        rid="ENTRY-BTCUSDT-open-1",
    )


def test_on_order_fill_seeds_execution_owned_lifecycle_stats(tmp_path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_100,
    )
    fsm = _make_mock_fsm(ledger)
    fsm.fsm.order_index = MagicMock()
    order_ref = SimpleNamespace(idempotent_key="idem-key-001", side="BUY")
    fsm.fsm.order_index.get.return_value = order_ref

    written = []
    with patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
        None,
    ), patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
    ) as mock_log_fn, patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
    ) as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_100
        mock_log_fn.return_value.write.side_effect = written.append
        EPEventHandlers(fsm).on_order_fill(_make_fill_event())

    latest = ledger.get_latest(lifecycle_id="idem-key-001")
    assert latest is not None
    assert latest.row_status == PROVISIONAL_ROW_STATUS
    assert latest.provisional_status == "entry_filled"
    assert latest.entry_rid == "ENTRY-BTCUSDT-open-1"
    assert latest.entry_price == 50000.0
    assert latest.qty == 0.02
    assert latest.fees == pytest.approx(0.05)


def test_on_portfolio_state_updated_updates_provisional_path_stats(tmp_path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_200,
    )
    ledger.seed_entry(
        lifecycle_id="idem-key-002",
        entry_rid="ENTRY-BTCUSDT-open-2",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=50000.0,
        qty=0.02,
    )
    fsm = _make_mock_fsm(ledger)
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "idem-key-002"}
    fsm._prev_position_amts = {"BTCUSDT": 0.02}

    event = SimpleNamespace(
        pld={
            "positions_last_ts_ms": 1_700_000_000_250,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "net_position": "0.02",
                    "avg_entry_price": "50000.0",
                    "markPrice": "50500.0",
                    "unrealizedPnl": "10.0",
                }
            ],
        }
    )

    with patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
        None,
    ), patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
    ) as mock_log_fn, patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
    ) as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_250
        mock_clock.return_value.now_sec.return_value = 1_700_000_000.25
        mock_log_fn.return_value.write.side_effect = []
        EPEventHandlers(fsm).on_portfolio_state_updated(event)

    latest = ledger.get_latest(lifecycle_id="idem-key-002")
    assert latest is not None
    assert latest.row_status == PROVISIONAL_ROW_STATUS
    assert latest.provisional_status == "open_live"
    assert latest.best_price_in_trade_direction == 50500.0
    assert latest.mfe_usdt == pytest.approx(10.0)
    assert latest.mfe_bps == pytest.approx(100.0)
    assert latest.peak_edge_usd == pytest.approx(10.0)
    assert latest.first_positive_pnl_ts_ms == 1_700_000_000_250


def test_position_close_finalizes_lifecycle_stats_before_cache_cleanup(tmp_path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_300,
    )
    ledger.seed_entry(
        lifecycle_id="life-close-1",
        entry_rid="ENTRY-BTCUSDT-open-3",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=50000.0,
        qty=0.02,
    )
    ledger.update_open(
        lifecycle_id="life-close-1",
        mark_price=50500.0,
        observed_ts_ms=1_700_000_000_200,
        unrealized_pnl=10.0,
    )
    fsm = _make_mock_fsm(ledger)
    fsm._prev_position_amts = {"BTCUSDT": 0.02}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-open-3"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50000.0}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "life-close-1"}
    fsm._last_trade_id_by_symbol = {"BTCUSDT": "close-trade-1"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._accumulated_fees_by_symbol = {"BTCUSDT": 0.4}
    fsm._close_accounting_truth_by_symbol = {
        "BTCUSDT": {
            "trade_id": "close-trade-1",
            "close_price": 50450.0,
            "realized_pnl": 9.0,
            "fees": 0.4,
            "lifecycle_id": "life-close-1",
            "entry_side": "BUY",
            "close_reason": "CLOSE",
            "pnl_status": "resolved",
            "pnl_source": "close_fill",
            "economic_close_detected": True,
            "economic_close_kind": "explicit_close_fill",
        }
    }
    fsm._open_regime_by_symbol = {"BTCUSDT": {
        "regime_epoch_ref": "stable_epoch:BTCUSDT:1"}}

    event = SimpleNamespace(
        pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]})

    written = []
    with patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
        None,
    ), patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
    ) as mock_log_fn, patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
    ) as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_300
        mock_clock.return_value.now_sec.return_value = 1_700_000_000.3
        mock_log_fn.return_value.write.side_effect = written.append
        EPEventHandlers(fsm).on_portfolio_state_updated(event)

    latest = ledger.get_latest(lifecycle_id="life-close-1")
    assert latest is not None
    assert latest.row_status == FINAL_ROW_STATUS
    assert latest.close_reason == "CLOSE"
    assert latest.close_actor == "EXECUTION_POSITION"
    assert latest.gross_pnl == pytest.approx(9.0)
    assert latest.fees == pytest.approx(0.4)
    assert latest.net_pnl == pytest.approx(8.6)
    assert latest.mfe_usdt == pytest.approx(10.0)
    assert "BTCUSDT" not in fsm._last_lifecycle_ikey_by_symbol
    assert "BTCUSDT" not in fsm._accumulated_fees_by_symbol


def test_position_close_with_unresolved_accounting_does_not_synthesize_pnl_or_fees(tmp_path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_350,
    )
    ledger.seed_entry(
        lifecycle_id="life-close-unresolved-1",
        entry_rid="ENTRY-BTCUSDT-open-4",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_000,
        entry_price=50000.0,
        qty=0.02,
    )
    ledger.update_open(
        lifecycle_id="life-close-unresolved-1",
        mark_price=50500.0,
        observed_ts_ms=1_700_000_000_200,
        unrealized_pnl=10.0,
    )
    fsm = _make_mock_fsm(ledger)
    fsm._prev_position_amts = {"BTCUSDT": 0.02}
    fsm._last_lifecycle_rid_by_symbol = {"BTCUSDT": "ENTRY-BTCUSDT-open-4"}
    fsm._last_lifecycle_fill_price_by_symbol = {"BTCUSDT": 50000.0}
    fsm._last_lifecycle_ikey_by_symbol = {"BTCUSDT": "life-close-unresolved-1"}
    fsm._last_trade_id_by_symbol = {"BTCUSDT": "close-trade-unresolved-1"}
    fsm._last_entry_side_by_symbol = {"BTCUSDT": "BUY"}
    fsm._accumulated_fees_by_symbol = {"BTCUSDT": 0.4}
    fsm._close_accounting_truth_by_symbol = {
        "BTCUSDT": {
            "trade_id": None,
            "close_price": 50450.0,
            "realized_pnl": None,
            "fees": 0.4,
            "lifecycle_id": "life-close-unresolved-1",
            "entry_side": "BUY",
            "close_reason": "CLOSE",
            "pnl_status": "unresolved",
            "pnl_source": "close_fill",
            "economic_close_detected": True,
            "economic_close_kind": "explicit_close_fill",
            "accounting_unresolved_reason": "missing_close_fill_trade_id_realized_pnl",
        }
    }
    fsm._open_regime_by_symbol = {"BTCUSDT": {
        "regime_epoch_ref": "stable_epoch:BTCUSDT:2"}}

    event = SimpleNamespace(
        pld={"positions": [{"symbol": "BTCUSDT", "positionAmt": 0.0}]})

    with patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._trade_lifecycle",
        None,
    ), patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers._get_order_logger"
    ) as mock_log_fn, patch(
        "apps.reference.domains.execution_position.orchestration.event_handlers.get_clock"
    ) as mock_clock:
        mock_clock.return_value.now_ms.return_value = 1_700_000_000_350
        mock_clock.return_value.now_sec.return_value = 1_700_000_000.35
        mock_log_fn.return_value.write.side_effect = []
        EPEventHandlers(fsm).on_portfolio_state_updated(event)

    latest = ledger.get_latest(lifecycle_id="life-close-unresolved-1")
    assert latest is not None
    assert latest.row_status == FINAL_ROW_STATUS
    assert latest.close_reason == "CLOSE"
    assert latest.gross_pnl is None
    assert latest.fees is None
    assert latest.net_pnl is None
    assert latest.mfe_usdt == pytest.approx(10.0)
