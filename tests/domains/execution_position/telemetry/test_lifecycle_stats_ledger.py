from __future__ import annotations

from pathlib import Path

from apps.reference.domains.execution_position.telemetry.lifecycle_stats_ledger import (
    ExecutionLifecycleStatsLedger,
    FINAL_ROW_STATUS,
    PROVISIONAL_ROW_STATUS,
    load_latest_execution_lifecycle_row,
)


def test_seed_entry_writes_initial_provisional_row(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )

    row = ledger.seed_entry(
        lifecycle_id="life-1",
        entry_rid="rid-1",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_010,
        entry_price=100.0,
        qty=2.0,
        fees=0.15,
    )

    assert row is not None
    assert row.row_status == PROVISIONAL_ROW_STATUS
    assert row.provisional_status == "entry_filled"
    assert row.best_price_in_trade_direction == 100.0
    assert row.worst_price_against_trade == 100.0
    assert row.mfe_usdt == 0.0
    assert row.mae_usdt == 0.0
    assert row.peak_edge_usd == 0.0
    assert row.fees == 0.15

    latest = load_latest_execution_lifecycle_row(
        lifecycle_id="life-1",
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
    )
    assert latest is not None
    assert latest["entry_rid"] == "rid-1"
    assert latest["row_status"] == PROVISIONAL_ROW_STATUS


def test_open_update_computes_path_stats_and_first_positive_pnl(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_100,
    )
    ledger.seed_entry(
        lifecycle_id="life-2",
        entry_rid="rid-2",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_010,
        entry_price=100.0,
        qty=2.0,
    )

    first = ledger.update_open(
        lifecycle_id="life-2",
        mark_price=104.0,
        observed_ts_ms=1_700_000_000_200,
    )
    assert first is not None
    assert first.best_price_in_trade_direction == 104.0
    assert first.worst_price_against_trade == 100.0
    assert first.mfe_usdt == 8.0
    assert first.mae_usdt == 0.0
    assert first.mfe_bps == 400.0
    assert first.peak_edge_usd == 8.0
    assert first.peak_giveback_usd == 0.0
    assert first.first_positive_pnl_ts_ms == 1_700_000_000_200

    second = ledger.update_open(
        lifecycle_id="life-2",
        mark_price=101.0,
        observed_ts_ms=1_700_000_000_300,
    )
    assert second is not None
    assert second.best_price_in_trade_direction == 104.0
    assert second.worst_price_against_trade == 100.0
    assert second.mfe_usdt == 8.0
    assert second.peak_edge_usd == 8.0
    assert second.peak_giveback_usd == 6.0
    assert second.peak_giveback_pct == 75.0
    assert second.first_positive_pnl_ts_ms == 1_700_000_000_200


def test_duplicate_provisional_state_is_not_reappended(tmp_path: Path) -> None:
    log_file = tmp_path / "execution_lifecycle_stats_v1.jsonl"
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(log_file),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    ledger.seed_entry(
        lifecycle_id="life-3",
        entry_rid="rid-3",
        symbol="BTCUSDT",
        side="SELL",
        entry_ts_ms=1_700_000_000_010,
        entry_price=100.0,
        qty=2.0,
    )

    first = ledger.update_open(
        lifecycle_id="life-3",
        mark_price=95.0,
        observed_ts_ms=1_700_000_000_100,
    )
    duplicate = ledger.update_open(
        lifecycle_id="life-3",
        mark_price=95.0,
        observed_ts_ms=1_700_000_000_200,
    )

    assert first is not None
    assert duplicate is None
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_short_side_update_computes_side_aware_mfe_mae_and_giveback(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_100,
    )
    ledger.seed_entry(
        lifecycle_id="life-short-1",
        entry_rid="rid-short-1",
        symbol="BTCUSDT",
        side="SELL",
        entry_ts_ms=1_700_000_000_010,
        entry_price=100.0,
        qty=2.0,
    )

    favorable = ledger.update_open(
        lifecycle_id="life-short-1",
        mark_price=95.0,
        observed_ts_ms=1_700_000_000_200,
    )
    assert favorable is not None
    assert favorable.best_price_in_trade_direction == 95.0
    assert favorable.worst_price_against_trade == 100.0
    assert favorable.mfe_usdt == 10.0
    assert favorable.mae_usdt == 0.0
    assert favorable.peak_edge_usd == 10.0
    assert favorable.first_positive_pnl_ts_ms == 1_700_000_000_200

    adverse = ledger.update_open(
        lifecycle_id="life-short-1",
        mark_price=102.0,
        observed_ts_ms=1_700_000_000_300,
    )
    assert adverse is not None
    assert adverse.best_price_in_trade_direction == 95.0
    assert adverse.worst_price_against_trade == 102.0
    assert adverse.mfe_usdt == 10.0
    assert adverse.mae_usdt == 4.0
    assert adverse.mfe_bps == 500.0
    assert adverse.mae_bps == 200.0
    assert adverse.peak_edge_usd == 10.0
    assert adverse.peak_giveback_usd == 14.0
    assert adverse.peak_giveback_pct == 140.0
    assert adverse.first_positive_pnl_ts_ms == 1_700_000_000_200


def test_close_request_and_finalize_preserve_path_stats_and_emit_final_row(tmp_path: Path) -> None:
    ledger = ExecutionLifecycleStatsLedger(
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
        clock_ms_fn=lambda: 1_700_000_000_000,
    )
    ledger.seed_entry(
        lifecycle_id="life-4",
        entry_rid="rid-4",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_010,
        entry_price=100.0,
        qty=2.0,
    )
    ledger.update_open(
        lifecycle_id="life-4",
        mark_price=103.0,
        observed_ts_ms=1_700_000_000_100,
    )

    requested = ledger.mark_close_requested(
        lifecycle_id="life-4",
        current_unrealized=4.5,
        close_actor="position_policy_sidecar",
    )
    assert requested is not None
    assert requested.provisional_status == "close_requested"
    assert requested.current_unrealized_at_close_request == 4.5
    assert requested.close_actor == "POSITION_POLICY_SIDECAR"

    final = ledger.finalize_close(
        lifecycle_id="life-4",
        close_ts_ms=1_700_000_000_500,
        close_actor="position_policy_sidecar",
        close_reason="close",
        gross_pnl=5.0,
        fees=0.4,
        net_pnl=4.6,
    )
    assert final is not None
    assert final.row_status == FINAL_ROW_STATUS
    assert final.provisional_status is None
    assert final.close_ts_ms == 1_700_000_000_500
    assert final.close_actor == "POSITION_POLICY_SIDECAR"
    assert final.close_reason == "CLOSE"
    assert final.gross_pnl == 5.0
    assert final.fees == 0.4
    assert final.net_pnl == 4.6
    assert final.best_price_in_trade_direction == 103.0
    assert final.mfe_usdt == 6.0

    latest = load_latest_execution_lifecycle_row(
        lifecycle_id="life-4",
        log_file=str(tmp_path / "execution_lifecycle_stats_v1.jsonl"),
    )
    assert latest is not None
    assert latest["row_status"] == FINAL_ROW_STATUS
    assert latest["net_pnl"] == 4.6
