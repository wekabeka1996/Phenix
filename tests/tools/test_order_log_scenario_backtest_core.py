from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.order_log_scenario_backtest.candles import load_1m_candles
from tools.order_log_scenario_backtest.exit_policies import (
    build_sidecar_request_index,
    materialize_trade_result,
    sidecar_only_exit,
    tp_sl_only_exit,
)
from tools.order_log_scenario_backtest.gates import (
    evaluate_nrr026,
    evaluate_nrr027,
    evaluate_nrr028,
    evaluate_nrr029,
    evaluate_nrr030,
)
from tools.order_log_scenario_backtest.models import CanonicalEntry, CandleSeries, ScenarioRuntime
from tools.order_log_scenario_backtest.pyramiding import (
    PYRAMIDING_SCENARIO_ID,
    build_pyramiding_enabled_entry_set,
)
from tools.order_log_scenario_backtest.quadratic_regime_forensics import (
    QUADRATIC_REGIME_SCENARIO_ID,
    _confidence_sweep_rows,
    _variant_rows,
)
from tools.order_log_scenario_backtest.regime_confidence import (
    REGIME_CONFIDENCE_SCENARIO_ID,
    build_regime_confidence_disabled_entry_set,
)
from tools.order_log_scenario_backtest.reconstruct import reconstruct_canonical_entries
from tools.order_log_scenario_backtest.schema_probe import probe_schema


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_yaml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _iso_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _write_candles(path: Path, start_close_ts_ms: int, minutes: int, price: float, overrides: dict[int, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["open", "high", "low", "close", "timestamp"])
        writer.writeheader()
        for idx in range(minutes):
            row = {
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "timestamp": str(start_close_ts_ms + idx * 60000),
            }
            row.update(overrides.get(idx, {}))
            writer.writerow(row)


def _build_runtime(tmp_path: Path) -> tuple[Path, Path, Path, int]:
    workspace_root = tmp_path / "repo"
    runtime_root = workspace_root / "logs"
    report_root = workspace_root / "reports" / "order_log_scenario_backtest"
    base_dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    entry1_ts_ms = int((base_dt + timedelta(seconds=10)).timestamp() * 1000)
    entry2_ts_ms = int((base_dt + timedelta(minutes=5, seconds=10)).timestamp() * 1000)
    entry3_ts_ms = int((base_dt + timedelta(minutes=10, seconds=10)).timestamp() * 1000)

    order_log_rows = [
        {"event_type": "BOOT", "timestamp": entry1_ts_ms - 1000, "source_fsm": "OrderLoggerV1", "rid": "boot-1", "symbol": "_SYSTEM_"},
        {
            "rid": "reserve-eth",
            "event_type": "ORDER_INTENT",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "quantity": "1",
            "source_fsm": "ExposureGuard",
            "reservation_id": "res-eth",
            "metadata": {"leverage": "10", "reduce_only": False},
            "timestamp": entry1_ts_ms - 50,
        },
        {
            "rid": "aurora_ETHUSDT_1",
            "event_type": "ORDER_INTENT",
            "lifecycle_id": "res-eth",
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "side": "BUY",
            "quantity": 1.0,
            "price": 100.0,
            "source_fsm": "DecisionMaking",
            "regime": "TREND_DOWN",
            "regime_confidence": 0.15,
            "trend_dir": "DOWN",
            "trend_confidence": 0.1,
            "trend_run_length": 3,
            "price_motion_context": {"pm_norm_10s": -1.2, "pm_norm_60s": -0.6, "pm_norm_300s": -0.8},
            "metadata": {
                "resolved_min_regime_confidence": 0.2,
                "resolved_min_regime_confidence_source": "domain_regime_specific",
            },
            "timestamp": entry1_ts_ms,
        },
        {
            "rid": "aurora_ETHUSDT_1",
            "event_type": "ORDER_PLACED",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "quantity": 1.0,
            "client_order_id": "ENTRY-ETH-1",
            "order_id": "10001",
            "source_fsm": "ExecPosFSM",
            "adapter_response": {"clientOrderId": "ENTRY-ETH-1", "orderId": "10001", "price": "100.0", "executedQty": "0"},
            "timestamp": entry1_ts_ms + 10,
        },
        {
            "rid": "ENTRY-ETH-1",
            "lifecycle_id": "aurora_ETHUSDT_1",
            "event_type": "ORDER_FILLED",
            "symbol": "ETHUSDT",
            "side": "BUY",
            "client_order_id": "ENTRY-ETH-1",
            "order_id": "10001",
            "order_kind": "ENTRY",
            "quantity": 1.0,
            "price": 100.0,
            "timestamp": entry1_ts_ms + 20,
        },
        {
            "rid": "reserve-btc",
            "event_type": "ORDER_INTENT",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "quantity": "1",
            "source_fsm": "ExposureGuard",
            "reservation_id": "res-btc",
            "metadata": {"leverage": "10", "reduce_only": False},
            "timestamp": entry2_ts_ms - 50,
        },
        {
            "rid": "aurora_BTCUSDT_1",
            "event_type": "ORDER_INTENT",
            "lifecycle_id": "res-btc",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "SELL",
            "quantity": 1.0,
            "price": 200.0,
            "source_fsm": "DecisionMaking",
            "regime": "TREND_UP",
            "regime_confidence": 0.5,
            "trend_dir": "UP",
            "trend_confidence": 0.55,
            "trend_run_length": 3,
            "price_motion_context": {"pm_norm_10s": 1.1, "pm_norm_60s": 0.7, "pm_norm_300s": 0.9},
            "metadata": {
                "resolved_min_regime_confidence": 0.2,
                "resolved_min_regime_confidence_source": "domain_regime_specific",
            },
            "timestamp": entry2_ts_ms,
        },
        {
            "rid": "ENTRY-BTC-1",
            "lifecycle_id": "aurora_BTCUSDT_1",
            "event_type": "ORDER_FILLED",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "client_order_id": "ENTRY-BTC-1",
            "order_id": "20001",
            "order_kind": "ENTRY",
            "quantity": 1.0,
            "price": 200.0,
            "timestamp": entry2_ts_ms + 20,
        },
        {
            "rid": "reserve-xrp",
            "event_type": "ORDER_INTENT",
            "symbol": "XRPUSDT",
            "side": "BUY",
            "quantity": "2",
            "source_fsm": "ExposureGuard",
            "reservation_id": "res-xrp",
            "metadata": {"leverage": "5", "reduce_only": False},
            "timestamp": entry3_ts_ms - 50,
        },
        {
            "rid": "aurora_XRPUSDT_1",
            "event_type": "ORDER_INTENT",
            "lifecycle_id": "res-xrp",
            "symbol": "XRPUSDT",
            "strategy_id": "aurora",
            "side": "BUY",
            "quantity": 2.0,
            "price": 50.0,
            "source_fsm": "DecisionMaking",
            "regime": "LOW_VOLATILITY",
            "regime_confidence": 0.5,
            "trend_dir": "UP",
            "trend_confidence": 0.6,
            "trend_run_length": 1,
            "price_motion_context": {"pm_norm_10s": 0.1, "pm_norm_60s": 0.1, "pm_norm_300s": 0.05},
            "metadata": {
                "resolved_min_regime_confidence": 0.35,
                "resolved_min_regime_confidence_source": "domain_default",
            },
            "timestamp": entry3_ts_ms,
        },
        {
            "rid": "ENTRY-XRP-1",
            "lifecycle_id": "aurora_XRPUSDT_1",
            "event_type": "ORDER_FILLED",
            "symbol": "XRPUSDT",
            "side": "BUY",
            "client_order_id": "ENTRY-XRP-1",
            "order_id": "30001",
            "order_kind": "ENTRY",
            "quantity": 2.0,
            "price": 50.0,
            "timestamp": entry3_ts_ms + 20,
        },
    ]
    _write_jsonl(runtime_root / "order_log_v1.jsonl", order_log_rows)

    sidecar_rows = [
        {
            "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
            "symbol": "ETHUSDT",
            "lifecycle_id": "aurora_ETHUSDT_1",
            "request_id": "req-eth",
            "request_ts_ms": entry1_ts_ms + 180000,
            "fill_correlation": {"rid": "aurora_ETHUSDT_1", "lifecycle_id": "aurora_ETHUSDT_1"},
            "trace_id": "trace-eth",
            "ts_ms": entry1_ts_ms + 180000,
        },
        {
            "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
            "symbol": "BTCUSDT",
            "lifecycle_id": "aurora_BTCUSDT_1",
            "request_id": "req-btc",
            "request_ts_ms": entry2_ts_ms + 180000,
            "fill_correlation": {"rid": "aurora_BTCUSDT_1", "lifecycle_id": "aurora_BTCUSDT_1"},
            "trace_id": "trace-btc",
            "ts_ms": entry2_ts_ms + 180000,
        },
    ]
    _write_jsonl(runtime_root / "trade_lifecycle.jsonl", sidecar_rows)

    shadow_rows = [
        {
            "event_name": "EVT:QUADRATIC_DECISION_TRACE",
            "rid": "aurora_ETHUSDT_pyramid_1",
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "side": "buy",
            "ts_ms": entry1_ts_ms + 120000,
            "payload_fragment": {
                "symbol": "ETHUSDT",
                "regime": "TREND_DOWN",
                "regime_confidence": 0.25,
                "strategy_id": "aurora",
                "ts_ms": entry1_ts_ms + 120000,
                "side": "buy",
                "anti_peak_observability": {
                    "score_path": {"final_score": 0.025, "signal_threshold": 0.001},
                },
            },
        },
        {
            "event_name": "EVT:TRADE_INTENT_REJECTED",
            "rid": "aurora_ETHUSDT_pyramid_1",
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "side": "buy",
            "ts_ms": entry1_ts_ms + 120001,
            "payload_fragment": {
                "symbol": "ETHUSDT",
                "strategy_id": "aurora",
                "side": "buy",
                "ts_ms": entry1_ts_ms + 120000,
                "reason_code": "ANTI_PYRAMIDING_BLOCK",
                "why_chain": ["enter:buy:score=0.0250>=thr_buy=0.0010"],
            },
        },
        {
            "event_name": "EVT:QUADRATIC_DECISION_TRACE",
            "rid": "aurora_BTCUSDT_pyramid_1",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "sell",
            "ts_ms": entry2_ts_ms + 120000,
            "payload_fragment": {
                "symbol": "BTCUSDT",
                "regime": "TREND_UP",
                "regime_confidence": 0.35,
                "strategy_id": "aurora",
                "ts_ms": entry2_ts_ms + 120000,
                "side": "sell",
                "anti_peak_observability": {
                    "score_path": {"final_score": -0.022, "signal_threshold": 0.0006},
                },
            },
        },
        {
            "event_name": "EVT:TRADE_INTENT_REJECTED",
            "rid": "aurora_BTCUSDT_pyramid_1",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "sell",
            "ts_ms": entry2_ts_ms + 120001,
            "payload_fragment": {
                "symbol": "BTCUSDT",
                "strategy_id": "aurora",
                "side": "sell",
                "ts_ms": entry2_ts_ms + 120000,
                "reason_code": "ANTI_PYRAMIDING_BLOCK",
                "why_chain": ["enter:sell:score=-0.0220<=-thr_sell=0.0006"],
            },
        },
    ]
    _write_jsonl(runtime_root / "shadow_critical_event_journal_v1.jsonl", shadow_rows)

    confidence_rows = [
        {
            "record_type": "decision",
            "schema_version": "1.0.0",
            "ts_ms": entry1_ts_ms + 120000,
            "symbol": "ETHUSDT",
            "rid": "aurora_ETHUSDT_conf_1",
            "strategy_id": "aurora",
            "intent_side": "LONG",
            "outcome": "DENY",
            "regime_used": "TREND_DOWN",
            "regime_confidence_used": 0.15,
            "detector_event_ts_ms": entry1_ts_ms + 119999,
            "bar_close_ts_ms": int((base_dt + timedelta(minutes=2)).timestamp() * 1000),
            "basis_tf_sec": 300,
            "source_model": "sma_trend_v1",
            "resolved_min_regime_confidence": 0.2,
            "resolved_min_regime_confidence_source": "domain_regime_specific",
            "resolved_max_regime_confidence": None,
            "resolved_max_regime_confidence_source": None,
            "regime_confidence_breach_kind": "below_min",
            "regime_confidence_gate_verdict": "DENY",
            "threshold_reason": "regime_confidence=0.15 <= min=0.2",
            "deny_reason": "NRR-026",
            "why_short": "below_min",
        },
        {
            "record_type": "decision",
            "schema_version": "1.0.0",
            "ts_ms": entry2_ts_ms + 120000,
            "symbol": "BTCUSDT",
            "rid": "aurora_BTCUSDT_conf_1",
            "strategy_id": "aurora",
            "intent_side": "SHORT",
            "outcome": "DENY",
            "regime_used": "TREND_UP",
            "regime_confidence_used": 0.5,
            "detector_event_ts_ms": entry2_ts_ms + 119999,
            "bar_close_ts_ms": int((base_dt + timedelta(minutes=7)).timestamp() * 1000),
            "basis_tf_sec": 300,
            "source_model": "sma_trend_v1",
            "resolved_min_regime_confidence": 0.2,
            "resolved_min_regime_confidence_source": "domain_regime_specific",
            "resolved_max_regime_confidence": 0.4,
            "resolved_max_regime_confidence_source": "domain_regime_specific",
            "regime_confidence_breach_kind": "above_max",
            "regime_confidence_gate_verdict": "DENY",
            "threshold_reason": "regime_confidence=0.5 > max=0.4",
            "deny_reason": "NRR-063",
            "why_short": "above_max",
        },
    ]
    _write_jsonl(runtime_root / "regime_confidence_audit_v1.jsonl", confidence_rows)

    shadow_confidence_rows = [
        {
            "event_name": "EVT:QUADRATIC_DECISION_TRACE",
            "rid": "aurora_ETHUSDT_conf_1",
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "side": "buy",
            "ts_ms": entry1_ts_ms + 120000,
            "payload_fragment": {
                "symbol": "ETHUSDT",
                "regime": "TREND_DOWN",
                "regime_confidence": 0.15,
                "strategy_id": "aurora",
                "ts_ms": entry1_ts_ms + 120000,
                "side": "buy",
                "anti_peak_observability": {
                    "score_path": {"final_score": 0.03, "signal_threshold": 0.001},
                },
            },
        },
        {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "rid": "aurora_ETHUSDT_conf_1",
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "side": "BUY",
            "ts_ms": entry1_ts_ms + 120001,
            "payload_fragment": {
                "symbol": "ETHUSDT",
                "why_chain": ["enter:buy:score=0.0300>=thr_buy=0.0010"],
                "strategy_id": "aurora",
                "ts_ms": entry1_ts_ms + 120000,
                "side": "BUY",
            },
        },
        {
            "event_name": "EVT:DECISION_TRACE_EMITTED",
            "rid": "aurora_ETHUSDT_conf_1",
            "symbol": "ETHUSDT",
            "strategy_id": "aurora",
            "side": "BUY",
            "ts_ms": entry1_ts_ms + 120002,
            "payload_fragment": {
                "symbol": "ETHUSDT",
                "regime": "TREND_DOWN",
                "regime_confidence": 0.15,
                "event_ts_ms": entry1_ts_ms + 120000,
                "why": "below_min",
                "reject_reason": "NRR-026",
                "strategy_id": "aurora",
                "side": "BUY",
            },
        },
        {
            "event_name": "EVT:QUADRATIC_DECISION_TRACE",
            "rid": "aurora_BTCUSDT_conf_1",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "sell",
            "ts_ms": entry2_ts_ms + 120000,
            "payload_fragment": {
                "symbol": "BTCUSDT",
                "regime": "TREND_UP",
                "regime_confidence": 0.5,
                "strategy_id": "aurora",
                "ts_ms": entry2_ts_ms + 120000,
                "side": "sell",
                "anti_peak_observability": {
                    "score_path": {"final_score": -0.03, "signal_threshold": 0.001},
                },
            },
        },
        {
            "event_name": "EVT:STRATEGY_SIGNAL_PRODUCED",
            "rid": "aurora_BTCUSDT_conf_1",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "SELL",
            "ts_ms": entry2_ts_ms + 120001,
            "payload_fragment": {
                "symbol": "BTCUSDT",
                "why_chain": ["enter:sell:score=-0.0300<=-thr_sell=0.0010"],
                "strategy_id": "aurora",
                "ts_ms": entry2_ts_ms + 120000,
                "side": "SELL",
            },
        },
        {
            "event_name": "EVT:DECISION_TRACE_EMITTED",
            "rid": "aurora_BTCUSDT_conf_1",
            "symbol": "BTCUSDT",
            "strategy_id": "aurora",
            "side": "SELL",
            "ts_ms": entry2_ts_ms + 120002,
            "payload_fragment": {
                "symbol": "BTCUSDT",
                "regime": "TREND_UP",
                "regime_confidence": 0.5,
                "event_ts_ms": entry2_ts_ms + 120000,
                "why": "above_max",
                "reject_reason": "NRR-063",
                "strategy_id": "aurora",
                "side": "SELL",
            },
        },
    ]
    _write_jsonl(runtime_root / "shadow_critical_event_journal_v1.jsonl", shadow_rows + shadow_confidence_rows)

    _write_yaml(
        workspace_root / "config" / "aurora" / "domains.yaml",
        """
decision_making:
  directional_sanity:
    enabled: true
    min_regime_confidence: 0.35
    min_regime_confidence_by_regime:
      DEFAULT: 0.35
      TREND_UP: 0.2
      TREND_DOWN: 0.2
    hard_veto_consecutive_bars: 2
    hard_veto_consecutive_bars_by_regime: {}
    nrr026_enabled: false
    nrr027_enabled: false
  price_motion_sanity:
    enabled: false
    flash_window_sec: 10
    bleed_window_sec: 60
    flash_threshold_norm: 1.0
    bleed_threshold_norm: 0.5
    require_bleed_ready: true
  low_vol_cost_floor_gate:
    fee:
      open_fee_bps: 4.0
      close_fee_bps: 4.0
      fee_source: explicit_config
""",
    )
    _write_yaml(
        workspace_root / "config" / "aurora" / "instruments.yaml",
        """
instruments:
  ETHUSDT:
    execution:
      target_leverage: 10
      margin_mode: cross
  BTCUSDT:
    execution:
      target_leverage: 10
      margin_mode: cross
  XRPUSDT:
    execution:
      target_leverage: 5
      margin_mode: cross
""",
    )
    _write_yaml(workspace_root / "config" / "aurora" / "regime.yaml", "{}")
    _write_yaml(
        workspace_root / "config" / "aurora" / "strategies" / "aurora.yaml",
        """
strategies:
  aurora:
    assets:
      ETHUSDT:
        enabled: true
        exit:
          sl_pct: 0.01
          regime_tpsl:
            enabled: true
            mode: pct_mult
            sl_mult:
              DEFAULT: 1.0
            tp_mult:
              DEFAULT: 1.0
            min_sl_pct: 0.003
            max_sl_pct: 0.06
            min_tp_rr: 0.5
            max_tp_rr: 5.0
            min_dist_bps: 15
        take_profit:
          tp_low_ratio: 1.0
          partial_exit_pct: 0.5
        allowed_regimes: [TREND_DOWN, TREND_UP]
      BTCUSDT:
        enabled: true
        exit:
          sl_pct: 0.01
          regime_tpsl:
            enabled: true
            mode: pct_mult
            sl_mult:
              DEFAULT: 1.0
            tp_mult:
              DEFAULT: 1.0
            min_sl_pct: 0.003
            max_sl_pct: 0.06
            min_tp_rr: 0.5
            max_tp_rr: 5.0
            min_dist_bps: 15
        take_profit:
          tp_low_ratio: 1.0
          partial_exit_pct: 0.5
        allowed_regimes: [TREND_DOWN, TREND_UP]
      XRPUSDT:
        enabled: true
        exit:
          sl_pct: 0.01
          regime_tpsl:
            enabled: true
            mode: pct_mult
            sl_mult:
              DEFAULT: 1.0
            tp_mult:
              DEFAULT: 1.0
            min_sl_pct: 0.003
            max_sl_pct: 0.06
            min_tp_rr: 0.5
            max_tp_rr: 5.0
            min_dist_bps: 15
        take_profit:
          tp_low_ratio: 1.0
          partial_exit_pct: 0.5
        allowed_regimes: [LOW_VOLATILITY, TREND_UP]
""",
    )

    candle_start_close_ts_ms = int((base_dt + timedelta(minutes=1)).timestamp() * 1000) - 1
    _write_candles(
        workspace_root / "data" / "recorder" / "ETHUSDT_60.csv",
        candle_start_close_ts_ms,
        1452,
        100.0,
        {
            0: {"high": 100.2, "low": 98.5, "close": 99.2},
            4: {"open": 98.7, "high": 99.0, "low": 98.4, "close": 98.8},
        },
    )
    _write_candles(
        workspace_root / "data" / "recorder" / "BTCUSDT_60.csv",
        candle_start_close_ts_ms,
        1452,
        200.0,
        {
            5: {"open": 200.0, "high": 200.4, "low": 197.5, "close": 198.2},
            9: {"open": 197.0, "high": 197.5, "low": 196.5, "close": 197.2},
        },
    )
    _write_candles(
        workspace_root / "data" / "recorder" / "XRPUSDT_60.csv",
        candle_start_close_ts_ms,
        1452,
        50.0,
        {
            10: {"open": 50.0, "high": 50.7, "low": 49.9, "close": 50.6},
        },
    )
    return workspace_root, runtime_root, report_root, entry1_ts_ms


def test_schema_probe_reads_head_slice(tmp_path: Path) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    payload = probe_schema(runtime_root / "order_log_v1.jsonl", report_root, max_lines=20)
    captured = {(item["event_type"], item["source_fsm"]) for item in payload["captured_families"]}
    assert ("BOOT", "") in captured
    assert ("ORDER_INTENT", "DecisionMaking") in captured
    assert ("ORDER_FILLED", "") in captured
    assert payload["lines_read"] <= 20


def test_reconstruct_canonical_entries_aggregates_multi_fill(tmp_path: Path) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    order_log = runtime_root / "order_log_v1.jsonl"
    rows = order_log.read_text(encoding="utf-8").strip().splitlines()
    multi_fill = {
        "rid": "ENTRY-ETH-1",
        "lifecycle_id": "aurora_ETHUSDT_1",
        "event_type": "ORDER_FILLED",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "client_order_id": "ENTRY-ETH-1",
        "order_id": "10001",
        "order_kind": "ENTRY",
        "quantity": 1.0,
        "price": 102.0,
        "timestamp": json.loads(rows[4])["timestamp"] + 5,
    }
    _write_jsonl(
        order_log,
        [json.loads(line) for line in rows] + [multi_fill],
    )
    entries, unresolved_rows, manifest = reconstruct_canonical_entries(workspace_root, runtime_root, report_root)
    eth = next(entry for entry in entries if entry.symbol == "ETHUSDT")
    assert round(eth.entry_price, 6) == round((100.0 + 102.0) / 2.0, 6)
    assert eth.qty == 2.0
    assert eth.lifecycle_id == "aurora_ETHUSDT_1"
    assert manifest["canonical_entries"] == 3
    assert unresolved_rows == []


def test_gate_parity_adapters() -> None:
    entry = CanonicalEntry(
        entry_id="e1",
        lifecycle_id="e1",
        rid="e1",
        trade_id="",
        symbol="ETHUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_ts_ms=1,
        entry_time_iso="",
        entry_price=100.0,
        qty=1.0,
        leverage=10.0,
        timestamp_quality="direct_order_log",
        reconstruction_confidence="high",
        regime_at_entry="TREND_DOWN",
        regime_confidence_at_entry=0.15,
        regime_source="direct",
        trend_dir="DOWN",
        trend_confidence=0.1,
        trend_run_length=3,
        pm_norm_10s=-1.2,
        pm_norm_60s=-0.6,
        pm_norm_300s=-0.8,
        resolved_min_regime_confidence=0.2,
    )
    runtime = ScenarioRuntime(
        workspace_root=Path("."),
        runtime_root=Path("."),
        report_root=Path("."),
        config={
            "directional_sanity": {
                "min_regime_confidence": 0.35,
                "min_regime_confidence_by_regime": {"DEFAULT": 0.35, "TREND_DOWN": 0.2},
                "hard_veto_consecutive_bars": 2,
            },
            "price_motion_sanity": {
                "flash_threshold_norm": 1.0,
                "bleed_threshold_norm": 0.5,
                "require_bleed_ready": True,
            },
        },
        candles_by_symbol={},
        strict=True,
    )
    assert not evaluate_nrr026(entry, runtime).allowed
    assert not evaluate_nrr027(entry, runtime).allowed
    assert evaluate_nrr028(entry, runtime).allowed
    assert not evaluate_nrr029(entry, runtime).allowed
    assert not evaluate_nrr030(entry, runtime).allowed


def test_tp_sl_only_exit_and_sidecar_only_exit() -> None:
    entry = CanonicalEntry(
        entry_id="e1",
        lifecycle_id="e1",
        rid="e1",
        trade_id="",
        symbol="ETHUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_ts_ms=10_000,
        entry_time_iso="",
        entry_price=100.0,
        qty=1.0,
        leverage=10.0,
        timestamp_quality="direct_order_log",
        reconstruction_confidence="high",
        regime_at_entry="TREND_UP",
        regime_confidence_at_entry=0.5,
        regime_source="direct",
    )
    candles = CandleSeries(
        symbol="ETHUSDT",
        rows=[
            {"timestamp": 59_999, "open": 100.0, "high": 101.5, "low": 98.5, "close": 100.2},
            {"timestamp": 119_999, "open": 99.1, "high": 99.4, "low": 98.9, "close": 99.2},
        ],
        timestamps=[59_999, 119_999],
    )
    runtime = ScenarioRuntime(
        workspace_root=Path("."),
        runtime_root=Path("."),
        report_root=Path("."),
        config={
            "fees": {"open_fee_bps": 4.0, "close_fee_bps": 4.0},
            "assets": {
                "ETHUSDT": {
                    "sl_pct": 0.01,
                    "tp_low_ratio": 1.0,
                    "regime_tpsl": {
                        "enabled": True,
                        "mode": "pct_mult",
                        "sl_mult": {"DEFAULT": 1.0},
                        "tp_mult": {"DEFAULT": 1.0},
                        "min_sl_pct": 0.003,
                        "max_sl_pct": 0.06,
                        "min_tp_rr": 0.5,
                        "max_tp_rr": 5.0,
                        "min_dist_bps": 15,
                    },
                }
            },
        },
        candles_by_symbol={"ETHUSDT": candles},
        strict=True,
    )
    exit_event, extras = tp_sl_only_exit(entry, runtime)
    assert exit_event.reason == "sl_first_ambiguous_intrabar"
    assert round(float(extras["sl_price"]), 6) == 99.0

    runtime.sidecar_requests = [
        {
            "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
            "symbol": "ETHUSDT",
            "lifecycle_id": "e1",
            "request_id": "req-1",
            "request_ts_ms": 20_000,
            "ts_ms": 20_000,
            "fill_correlation": {"rid": "e1", "lifecycle_id": "e1"},
            "trace_id": "trace-1",
        }
    ]
    runtime.sidecar_request_index = build_sidecar_request_index(runtime.sidecar_requests)
    sidecar_event, sidecar_extras = sidecar_only_exit(entry, runtime)
    assert sidecar_event.reason == "sidecar_close_requested"
    assert sidecar_event.price == 99.1
    result_row = materialize_trade_result("sidecar_only", entry, runtime, sidecar_event, sidecar_extras)
    assert result_row["status"] == "loss"


def test_build_pyramiding_enabled_entry_set_materializes_synthetic_adds(tmp_path: Path) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    entries, _, _ = reconstruct_canonical_entries(workspace_root, runtime_root, report_root)
    candles_by_symbol = load_1m_candles(workspace_root, [workspace_root / "data" / "recorder"])
    runtime = ScenarioRuntime(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        config={
            "strategy_id": "aurora",
            "instruments": {
                "ETHUSDT": {"target_leverage": 10},
                "BTCUSDT": {"target_leverage": 10},
                "XRPUSDT": {"target_leverage": 5},
            },
        },
        candles_by_symbol=candles_by_symbol,
        strict=True,
    )
    combined = build_pyramiding_enabled_entry_set(
        entries,
        runtime,
        materialize_price_proxy=True,
        emit_artifacts=True,
    )
    synthetic = [entry for entry in combined if entry.entry_origin == "synthetic_pyramiding_reject_proxy"]
    assert len(synthetic) == 2
    assert {entry.symbol for entry in synthetic} == {"ETHUSDT", "BTCUSDT"}
    assert all(entry.qty == 0.0 for entry in synthetic)
    assert (report_root / "pyramiding_candidate_audit.csv").exists()
    assert (report_root / "pyramiding_candidate_summary.json").exists()


def test_build_regime_confidence_disabled_entry_set_materializes_synthetic_entries(tmp_path: Path) -> None:
    workspace_root, runtime_root, report_root, _ = _build_runtime(tmp_path)
    entries, _, _ = reconstruct_canonical_entries(workspace_root, runtime_root, report_root)
    candles_by_symbol = load_1m_candles(workspace_root, [workspace_root / "data" / "recorder"])
    runtime = ScenarioRuntime(
        workspace_root=workspace_root,
        runtime_root=runtime_root,
        report_root=report_root,
        config={
            "strategy_id": "aurora",
            "instruments": {
                "ETHUSDT": {"target_leverage": 10},
                "BTCUSDT": {"target_leverage": 10},
                "XRPUSDT": {"target_leverage": 5},
            },
        },
        candles_by_symbol=candles_by_symbol,
        strict=True,
    )
    combined = build_regime_confidence_disabled_entry_set(
        entries,
        runtime,
        materialize_price_proxy=True,
        emit_artifacts=True,
    )
    synthetic = [entry for entry in combined if entry.entry_origin == "synthetic_regime_confidence_gate_proxy"]
    assert len(synthetic) == 2
    assert {entry.symbol for entry in synthetic} == {"ETHUSDT", "BTCUSDT"}
    assert all(entry.qty == 0.0 for entry in synthetic)
    assert (report_root / REGIME_CONFIDENCE_SCENARIO_ID / "candidate_audit.csv").exists()
    assert (report_root / REGIME_CONFIDENCE_SCENARIO_ID / "microstructure_review.csv").exists()


def test_quadratic_regime_variant_logic_distinguishes_btc_doge_vs_eth() -> None:
    cases = [
        {
            "entry_id": "btc",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "actual_trade_status": "loss",
            "actual_exit_reason": "actual_close_sl",
            "actual_net_pnl_roi_pct": -12.49,
            "regime_confidence_at_entry": 0.20597874586033435,
            "score_margin_abs": 0.02399765,
            "motion_abs_sigma": 5.23979871,
            "raw_regime_mismatch": True,
            "signal_to_fill_sec": 48.944,
        },
        {
            "entry_id": "doge",
            "symbol": "DOGEUSDT",
            "side": "SELL",
            "actual_trade_status": "loss",
            "actual_exit_reason": "actual_close_sl",
            "actual_net_pnl_roi_pct": -5.23886905,
            "regime_confidence_at_entry": 0.3431086177341437,
            "score_margin_abs": 0.00077267,
            "motion_abs_sigma": 4.24979493,
            "raw_regime_mismatch": False,
            "signal_to_fill_sec": 458.351,
        },
        {
            "entry_id": "eth",
            "symbol": "ETHUSDT",
            "side": "SELL",
            "actual_trade_status": "loss",
            "actual_exit_reason": "actual_close_tp",
            "actual_net_pnl_roi_pct": -1.59637767,
            "regime_confidence_at_entry": 0.4707958596937715,
            "score_margin_abs": 0.00528261,
            "motion_abs_sigma": 2.73576752,
            "raw_regime_mismatch": False,
            "signal_to_fill_sec": 206.28,
        },
    ]
    confidence_rows = _confidence_sweep_rows(cases)
    floor_035 = next(row for row in confidence_rows if row["threshold"] == 0.35)
    assert floor_035["blocked_entries"] == 2
    assert floor_035["blocked_loss_sl_entries"] == 2
    assert floor_035["blocked_loss_tp_tag_entries"] == 0

    matrix_rows, variant_rows = _variant_rows(cases)
    assert any(row["variant_id"] == "combined_safe_short_v2" for row in matrix_rows)
    combined_v2 = next(row for row in variant_rows if row["variant_id"] == "combined_safe_short_v2")
    combined_v3 = next(row for row in variant_rows if row["variant_id"] == "combined_safe_short_v3_zero_entry")
    assert combined_v2["blocked_entries"] == 2
    assert combined_v2["blocked_loss_sl_entries"] == 2
    assert combined_v2["allowed_entries"] == 1
    assert combined_v3["blocked_entries"] == 3
    assert combined_v3["allowed_entries"] == 0
