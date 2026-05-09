from __future__ import annotations

import csv
import json
from pathlib import Path

import SEMA_ATOM_POC_02_REAL_LOG_ADAPTER as adapter


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_recorder_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "close", "high", "low"])
        writer.writeheader()
        writer.writerows(rows)


def test_side_aware_mfe_mae_sell_uses_sell_formula() -> None:
    bars = [
        adapter.Bar(ts_ms=1, close=100.0, high=103.0, low=97.0),
        adapter.Bar(ts_ms=2, close=99.0, high=101.0, low=95.0),
    ]
    mfe_bps, mae_bps = adapter.SideAwareMfeMaeCalculator.calculate("SELL", 100.0, bars)
    assert round(mfe_bps or 0.0, 6) == 500.0
    assert round(mae_bps or 0.0, 6) == -300.0


def test_rejected_collector_filters_missing_critical_fields() -> None:
    collector = adapter.RejectedDecisionCollector(
        [
            {
                "event_type": "DECISION_INTENT_REJECTED",
                "rid": "r1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "strategy_id": "aurora",
                "regime": None,
                "timestamp": 1000,
            }
        ]
    )
    contracts, summary = collector.collect()
    assert contracts == []
    assert summary["incomplete_rejected_buckets"]["incomplete_rejected_missing_critical_fields"] == 1


def test_rejected_collector_extracts_reference_price_and_marks_missing_regime_confidence() -> None:
    collector = adapter.RejectedDecisionCollector(
        [
            {
                "event_type": "DECISION_INTENT_REJECTED",
                "rid": "r2",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "strategy_id": "aurora",
                "regime": "LOW_VOLATILITY",
                "timestamp": 1000,
                "metadata": {
                    "low_vol_cost_floor": {
                        "entry_price": 100.0,
                        "direction_confidence": 0.12,
                    }
                },
            }
        ]
    )
    contracts, summary = collector.collect()
    assert summary["rejected_contracts_evaluated"] == 1
    assert len(contracts) == 1
    assert contracts[0].entry_price == 100.0
    assert "regime_confidence" in contracts[0].missing_fields


def test_encoder_keeps_realized_pnl_net_without_double_subtracting_fees() -> None:
    contract = adapter.RawContract(
        contract_kind="ACCEPTED",
        contract_id="a1",
        symbol="BTCUSDT",
        side="SELL",
        strategy_id="aurora",
        regime="TREND_DOWN",
        regime_confidence=0.6,
        direction_confidence=None,
        confidence_bucket="0.50..0.75",
        reference_price=100.0,
        entry_price=100.0,
        close_price=90.0,
        entry_ts_ms=1,
        event_ts_ms=2,
        close_ts_ms=2,
        realized_pnl_net=10.0,
        fees=2.0,
        trade_id="t1",
        close_reason="TP",
        pnl_status="resolved",
        reject_reason=None,
        lifecycle_id="l1",
        outcome_snapshot={},
        missing_fields=[],
        provenance={"entry_price_source": "entry_fill"},
    )
    atom = adapter.SemaEncoder().encode(contract)
    assert atom is not None
    assert atom.raw_contract["realized_pnl_net"] == 10.0
    assert atom.raw_contract["fees"] == 2.0
    assert atom.outcome_code == "ACCEPTED_WIN"


def test_pipeline_generates_atoms_and_report_from_minimal_fixture(tmp_path: Path) -> None:
    order_log = tmp_path / "capture" / "logs" / "order_log_v1.jsonl"
    recorder_root = tmp_path / "capture" / "data" / "recorder" / "2026-05-06"
    _write_jsonl(
        order_log,
        [
            {
                "rid": "rid1",
                "event_type": "ORDER_INTENT",
                "lifecycle_id": "lc1",
                "symbol": "BTCUSDT",
                "strategy_id": "aurora",
                "side": "SELL",
                "price": 100.0,
                "regime": "TREND_DOWN",
                "regime_confidence": 0.6,
                "source_fsm": "DecisionMaking",
                "timestamp": 1000,
            },
            {
                "rid": "fill1",
                "event_type": "ORDER_FILLED",
                "lifecycle_id": "lc1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "price": 100.0,
                "order_kind": "ENTRY",
                "timestamp": 1000,
            },
            {
                "rid": "rid1:TP",
                "event_type": "POSITION_CLOSED",
                "lifecycle_id": "lc1",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "trade_id": "t1",
                "fees": 1.0,
                "realized_pnl_net": 9.0,
                "close_reason": "TP",
                "metadata": {"close_price": 95.0, "realized_pnl": 10.0},
                "timestamp": 1900,
            },
            {
                "rid": "rej1",
                "event_type": "DECISION_INTENT_REJECTED",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "strategy_id": "aurora",
                "regime": "LOW_VOLATILITY",
                "regime_confidence": 0.4,
                "metadata": {
                    "reject_reason": "LOW_VOL_COST_FLOOR_DENY",
                    "low_vol_cost_floor": {"entry_price": 100.0, "direction_confidence": 0.1},
                },
                "timestamp": 1000,
            },
        ],
    )
    _write_recorder_csv(
        recorder_root / "BTCUSDT_300.csv",
        [
            {"timestamp": 1200, "close": 99.0, "high": 101.0, "low": 94.0},
            {"timestamp": 1900, "close": 95.0, "high": 100.0, "low": 90.0},
            {"timestamp": 1000 + 15 * 60 * 1000, "close": 103.0, "high": 104.0, "low": 102.0},
            {"timestamp": 1000 + 30 * 60 * 1000, "close": 105.0, "high": 106.0, "low": 104.0},
            {"timestamp": 1000 + 60 * 60 * 1000, "close": 110.0, "high": 111.0, "low": 109.0},
        ],
    )
    result = adapter.run_pipeline(
        order_log_path=order_log,
        recorder_root=tmp_path / "capture" / "data" / "recorder",
        output_saf_path=tmp_path / "aurora_real_logs_v02.saf.jsonl",
        output_report_path=tmp_path / "SEMA_ATOM_POC_02_REAL_LOG_ADAPTER_REPORT.md",
    )
    assert result.status == "READ_ONLY_REAL_LOG_RUN_COMPLETED"
    assert len(result.atoms) == 2
    report_text = result.report_path.read_text(encoding="utf-8")
    assert "SEMA_ATOM_POC_02_STATUS:" in report_text
    assert "READ_ONLY_REAL_LOG_RUN_COMPLETED" in report_text
