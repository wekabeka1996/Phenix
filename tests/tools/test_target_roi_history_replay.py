from __future__ import annotations

import csv
import json
from pathlib import Path

from tools.analysis.replay_target_roi_from_runtime_logs import run_target_roi_history_replay


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_yaml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _write_candles(path: Path, rows: list[dict[str, float | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["open", "high", "low", "close", "timestamp"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _entry_rows(
    *,
    reserve_rid: str,
    reservation_id: str,
    rid: str,
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    leverage: float,
    target_price: float,
    stop_price: float,
    order_id: str,
    client_order_id: str,
    entry_ts_ms: int,
) -> list[dict]:
    return [
        {
            "rid": reserve_rid,
            "event_type": "ORDER_INTENT",
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
            "source_fsm": "ExposureGuard",
            "reservation_id": reservation_id,
            "metadata": {"leverage": str(leverage), "reduce_only": False},
            "timestamp": entry_ts_ms - 50,
        },
        {
            "rid": rid,
            "event_type": "ORDER_INTENT",
            "lifecycle_id": reservation_id,
            "symbol": symbol,
            "strategy_id": "aurora",
            "side": side,
            "quantity": quantity,
            "price": entry_price,
            "source_fsm": "DecisionMaking",
            "target_price": target_price,
            "stop_price": stop_price,
            "round_trip_fee_bps": 8.0,
            "regime": "TREND_UP" if side == "BUY" else "TREND_DOWN",
            "regime_confidence": 0.5,
            "timestamp": entry_ts_ms,
        },
        {
            "rid": rid,
            "event_type": "ORDER_PLACED",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "client_order_id": client_order_id,
            "order_id": order_id,
            "source_fsm": "ExecPosFSM",
            "adapter_response": {
                "clientOrderId": client_order_id,
                "orderId": order_id,
                "price": str(entry_price),
                "executedQty": "0",
            },
            "timestamp": entry_ts_ms + 10,
        },
        {
            "rid": client_order_id,
            "lifecycle_id": rid,
            "event_type": "ORDER_FILLED",
            "symbol": symbol,
            "side": side,
            "client_order_id": client_order_id,
            "order_id": order_id,
            "order_kind": "ENTRY",
            "quantity": quantity,
            "price": entry_price,
            "timestamp": entry_ts_ms + 20,
        },
    ]


def _build_workspace(tmp_path: Path) -> Path:
    workspace_root = tmp_path / "repo"
    eth_entry_ts_ms = 1_779_521_710_000
    btc_entry_ts_ms = 1_779_521_770_000
    wal_eth_ts_ms = eth_entry_ts_ms
    wal_btc_ts_ms = btc_entry_ts_ms
    _write_yaml(
        workspace_root / "config" / "aurora" / "instruments.yaml",
        """
        instruments:
          ETHUSDT:
            execution:
              target_leverage: 10
          BTCUSDT:
            execution:
              target_leverage: 5
          XRPUSDT:
            execution:
              target_leverage: 5
        """,
    )
    _write_yaml(
        workspace_root / "config" / "aurora" / "domains.yaml",
        """
        decision_making:
          low_vol_cost_floor_gate:
            fee:
              open_fee_bps: 4.0
              close_fee_bps: 4.0
              fee_source: static
        """,
    )
    _write_yaml(
        workspace_root / "config" / "aurora" / "strategies" / "aurora.yaml",
        "strategies: {}",
    )
    _write_yaml(workspace_root / "config" / "aurora" / "regime.yaml", "{}")

    logs_root = workspace_root / "logs"
    frozen_root = workspace_root / "frozen"
    wal_root = workspace_root / "ops" / "wal"

    current_rows = _entry_rows(
        reserve_rid="reserve-eth",
        reservation_id="res-eth",
        rid="aurora_ETHUSDT_1",
        symbol="ETHUSDT",
        side="BUY",
        quantity=1.0,
        entry_price=100.0,
        leverage=10.0,
        target_price=101.0,
        stop_price=99.0,
        order_id="10001",
        client_order_id="ENTRY-ETH-1",
        entry_ts_ms=eth_entry_ts_ms,
    )
    _write_jsonl(logs_root / "order_log_v1.jsonl", current_rows)

    snap1_rows = current_rows + _entry_rows(
        reserve_rid="reserve-btc",
        reservation_id="res-btc",
        rid="aurora_BTCUSDT_1",
        symbol="BTCUSDT",
        side="SELL",
        quantity=1.0,
        entry_price=200.0,
        leverage=5.0,
        target_price=197.0,
        stop_price=202.0,
        order_id="20001",
        client_order_id="ENTRY-BTC-1",
        entry_ts_ms=btc_entry_ts_ms,
    )
    _write_jsonl(
        frozen_root / "snap1" / "logs" / "order_log_v1.jsonl",
        snap1_rows,
    )
    _write_jsonl(
        frozen_root / "snap2" / "logs" / "order_log_v1.jsonl",
        current_rows,
    )

    _write_jsonl(
        wal_root / "2026-05-23.jsonl",
        [
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_INTENT_PROPOSED",
                "rid": "aurora_ETHUSDT_1",
                "ts": wal_eth_ts_ms,
                "pld": {
                    "rid": "aurora_ETHUSDT_1",
                    "instrument": "ETHUSDT",
                    "side": "BUY",
                    "ts_ms": wal_eth_ts_ms,
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "rid": "fill-eth-1",
                "event_ts_ms": wal_eth_ts_ms + 500,
                "pld": {
                    "rid": "aurora_ETHUSDT_1",
                    "symbol": "ETHUSDT",
                    "side": "BUY",
                    "qty": "1.0",
                    "quantity": "1.0",
                    "cumulative_qty": "1.0",
                    "price": "100.0",
                    "status": "FILLED",
                    "orderId": "10001",
                    "clientOrderId": "ENTRY-ETH-1",
                    "commission": "0.02",
                    "commissionAsset": "USDT",
                    "ts_ms": wal_eth_ts_ms + 500,
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_INTENT_PROPOSED",
                "rid": "aurora_BTCUSDT_1",
                "ts": wal_btc_ts_ms,
                "pld": {
                    "rid": "aurora_BTCUSDT_1",
                    "instrument": "BTCUSDT",
                    "side": "SELL",
                    "ts_ms": wal_btc_ts_ms,
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "rid": "fill-btc-1",
                "event_ts_ms": wal_btc_ts_ms + 500,
                "pld": {
                    "rid": "aurora_BTCUSDT_1",
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "qty": "1.0",
                    "quantity": "1.0",
                    "cumulative_qty": "1.0",
                    "price": "200.0",
                    "status": "FILLED",
                    "orderId": "20001",
                    "clientOrderId": "ENTRY-BTC-1",
                    "commission": "0.04",
                    "commissionAsset": "USDT",
                    "ts_ms": wal_btc_ts_ms + 500,
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "rid": "aurora_ETHUSDT_1:TP",
                "event_ts_ms": wal_eth_ts_ms + 60_000,
                "pld": {
                    "rid": "aurora_ETHUSDT_1:TP",
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "status": "FILLED",
                    "order_type": "take_profit_market",
                    "bracket_role": "TP",
                    "ts_ms": wal_eth_ts_ms + 60_000,
                },
            },
        ],
    )

    recorder_root = workspace_root / "data" / "raw_binance_klines_1m"
    _write_candles(
        recorder_root / "ETHUSDT_60.csv",
        [
            {
                "open": 100.0,
                "high": 101.2,
                "low": 99.5,
                "close": 100.7,
                "timestamp": 1_779_521_759_999,
            }
        ],
    )
    _write_candles(
        recorder_root / "BTCUSDT_60.csv",
        [
            {
                "open": 200.0,
                "high": 200.5,
                "low": 196.5,
                "close": 197.2,
                "timestamp": 1_779_521_819_999,
            }
        ],
    )

    return workspace_root


def test_run_target_roi_history_replay_dedupes_sources_and_audits_wal(tmp_path: Path) -> None:
    workspace_root = _build_workspace(tmp_path)
    report_root = workspace_root / "reports" / "history"

    manifest = run_target_roi_history_replay(
        workspace_root=workspace_root,
        runtime_root=workspace_root / "logs",
        report_root=report_root,
        include_frozen=True,
        include_wal=True,
        recorder_roots=[workspace_root / "data" / "raw_binance_klines_1m"],
        target_roi_pcts=[7.0],
        horizon_modes=["actual_close_window"],
        strict=False,
    )

    assert manifest["status"] == "ok"
    assert manifest["inventory"]["raw_canonical_entries"] == 4
    assert manifest["inventory"]["unique_canonical_entries"] == 2
    assert manifest["inventory"]["duplicate_entries_dropped"] == 2
    assert manifest["wal_inventory"]["open_rids"] == 2
    assert manifest["wal_inventory"]["wal_only_open_rids"] == 0
    assert manifest["wal_inventory"]["wal_reconstructed_entries"] == 0
    assert manifest["result_rows"] == 2

    summary_payload = json.loads(
        (report_root / "target_roi_summary.json").read_text(encoding="utf-8"))
    by_target_horizon = summary_payload["by_target_horizon"]
    assert len(by_target_horizon) == 1
    assert by_target_horizon[0]["trades"] == 2
    assert by_target_horizon[0]["target_hits"] == 2


def test_run_target_roi_history_replay_reconstructs_wal_only_actual_open(tmp_path: Path) -> None:
    workspace_root = _build_workspace(tmp_path)
    report_root = workspace_root / "reports" / "history_gap"
    _write_candles(
        workspace_root / "data" / "raw_binance_klines_1m" / "XRPUSDT_60.csv",
        [
            {
                "open": 10.0,
                "high": 10.7,
                "low": 9.8,
                "close": 10.2,
                "timestamp": 1_779_600_059_999,
            }
        ],
    )
    _write_jsonl(
        workspace_root / "ops" / "wal" / "2026-05-24.jsonl",
        [
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_INTENT_PROPOSED",
                "rid": "aurora_XRPUSDT_9",
                "ts": 1_779_600_000_000,
                "pld": {
                    "rid": "aurora_XRPUSDT_9",
                    "instrument": "XRPUSDT",
                    "side": "BUY",
                    "ts_ms": 1_779_600_000_000,
                    "strategy": "aurora",
                    "order": {
                        "qty": "3",
                        "price": "10.0",
                    },
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "ORDER_PLACED",
                "rid": "aurora_XRPUSDT_9",
                "ts": 1_779_600_000_400,
                "pld": {
                    "rid": "aurora_XRPUSDT_9",
                    "symbol": "XRPUSDT",
                    "side": "BUY",
                    "qty": "3",
                    "order_type": "LIMIT",
                    "order_id": "30001",
                    "client_order_id": "ENTRY-XRP-9",
                    "regime": "TREND_UP",
                    "regime_confidence": 0.7,
                    "ts_ms": 1_779_600_000_400,
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "PENDING_BRACKETS_STORED",
                "rid": "aurora_XRPUSDT_9",
                "ts": 1_779_600_000_450,
                "pld": {
                    "rid": "aurora_XRPUSDT_9",
                    "symbol": "XRPUSDT",
                    "side": "BUY",
                    "entry_order_id": "30001",
                    "entry_client_order_id": "ENTRY-XRP-9",
                    "sl": 9.5,
                    "tp": 10.5,
                    "qty": 3.0,
                    "ts_ms": 1_779_600_000_450,
                },
            },
            {
                "v": 1,
                "op": "EVT",
                "verb": "TRADE_EXECUTED",
                "rid": "fill-xrp-9",
                "event_ts_ms": 1_779_600_000_500,
                "pld": {
                    "rid": "aurora_XRPUSDT_9",
                    "symbol": "XRPUSDT",
                    "side": "BUY",
                    "qty": "3",
                    "quantity": "3",
                    "cumulative_qty": "3",
                    "price": "10.0",
                    "status": "FILLED",
                    "orderId": "30001",
                    "clientOrderId": "ENTRY-XRP-9",
                    "commission": "0.006",
                    "commissionAsset": "USDT",
                    "ts_ms": 1_779_600_000_500,
                },
            }
        ],
    )

    manifest = run_target_roi_history_replay(
        workspace_root=workspace_root,
        runtime_root=workspace_root / "logs",
        report_root=report_root,
        include_frozen=True,
        include_wal=True,
        recorder_roots=[workspace_root / "data" / "raw_binance_klines_1m"],
        target_roi_pcts=[7.0],
        horizon_modes=["actual_close_window"],
        strict=False,
    )

    assert manifest["status"] == "ok"
    assert manifest["wal_inventory"]["open_rids"] == 3
    assert manifest["wal_inventory"]["wal_reconstructed_entries"] == 1
    assert manifest["wal_inventory"]["wal_only_open_rids"] == 0
    assert manifest["result_rows"] == 3

    summary_payload = json.loads(
        (report_root / "target_roi_summary.json").read_text(encoding="utf-8"))
    by_source = summary_payload["by_source"]
    wal_rows = [
        row for row in by_source if row["inventory_source_label"] == "wal_fallback"
    ]
    assert len(wal_rows) == 1
    assert wal_rows[0]["trades"] == 1
