from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.domains.shadow_telemetry.trading_read_models import (
    TradingReadModelService,
    TradingReadModelUnavailableError,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_trading_read_models_build_latest_context_from_disk_and_runtime(tmp_path: Path) -> None:
    snapshots_path = tmp_path / "data" / "shadow_telemetry" / \
        "snapshots" / "BNBUSDT" / "2026-05-10" / "12.jsonl"
    _write_jsonl(
        snapshots_path,
        [
            {
                "snapshot_id": "snap-1",
                "ts_ms": 1000,
                "symbol": "BNBUSDT",
                "tf_sec": 300,
                "features": {"price": "100.0"},
                "regime": {"state": "TREND_UP"},
                "execution": {"event": "ORDER_PLACED"},
            }
        ],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [{"ts_ms": 1100, "symbol": "BNBUSDT", "reason_code": "TEST_REJECT",
            "reason": "reject", "strategy_id": "llm_microstructure"}],
    )
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [{"ts_ms": 1200, "symbol": "BNBUSDT",
            "neocortex_action": "OPEN_LONG", "gate_trace_summary": "ok"}],
    )
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "risk_gate_state.json").write_text(
        json.dumps({"is_gate_open": True, "reference_equity": "2000.0"}),
        encoding="utf-8",
    )

    manage_flow = SimpleNamespace(
        has_active_lifecycle=lambda: True,
        state=SimpleNamespace(value="BRACKETS_PLACED"),
        position_side="BUY",
        position_qty=Decimal("10"),
        position_entry_price=Decimal("100.5"),
        entry_order_id="entry-1",
        entry_client_order_id="cid-1",
        sl_price=Decimal("99.0"),
        tp_price=Decimal("102.0"),
        _closing_position=False,
    )
    runtime = SimpleNamespace(
        manage_flows={"BNBUSDT": manage_flow},
        _last_lifecycle_ikey_by_symbol={"BNBUSDT": "life-1"},
        _symbol_brackets={"BNBUSDT": {
            "sl_order_id": "sl-1", "tp_order_id": "tp-1"}},
        _last_close_reason_by_symbol={},
    )
    service = TradingReadModelService(
        project_root=tmp_path, execution_position=runtime)

    latest = service.get_context_latest(symbol="BNBUSDT", tf_sec=300)
    assert latest["snapshot"]["snapshot_id"] == "snap-1"
    assert latest["risk_gate"]["available"] is True
    assert latest["active_positions"][0]["lifecycle_id"] == "life-1"
    assert latest["recent_rejections"][0]["reason_code"] == "TEST_REJECT"
    assert latest["recent_decisions"][0]["decision"] == "OPEN_LONG"


def test_trading_read_models_lookup_bracket_state_by_lifecycle(tmp_path: Path) -> None:
    manage_flow = SimpleNamespace(
        has_active_lifecycle=lambda: True,
        state=SimpleNamespace(value="OPENED"),
        position_side="SELL",
        position_qty=Decimal("5"),
        position_entry_price=Decimal("10.0"),
        entry_order_id="entry-2",
        entry_client_order_id="cid-2",
        sl_price=Decimal("10.5"),
        tp_price=Decimal("9.5"),
        _closing_position=False,
    )
    runtime = SimpleNamespace(
        manage_flows={"XRPUSDT": manage_flow},
        _last_lifecycle_ikey_by_symbol={"XRPUSDT": "life-2"},
        _symbol_brackets={"XRPUSDT": {
            "sl_order_id": "sl-2", "tp_order_id": "tp-2"}},
        _last_close_reason_by_symbol={},
    )
    service = TradingReadModelService(
        project_root=tmp_path, execution_position=runtime)

    bracket_state = service.get_bracket_state("life-2")
    assert bracket_state is not None
    assert bracket_state["sl_order_id"] == "sl-2"
    assert bracket_state["tp_order_id"] == "tp-2"


def test_trading_read_models_fail_closed_when_execution_runtime_is_missing(tmp_path: Path) -> None:
    service = TradingReadModelService(
        project_root=tmp_path, execution_position=None)

    with pytest.raises(TradingReadModelUnavailableError):
        service.get_active_positions()


def test_trading_read_models_fail_closed_when_rejection_ledger_is_missing(tmp_path: Path) -> None:
    service = TradingReadModelService(
        project_root=tmp_path, execution_position=SimpleNamespace(manage_flows={}))

    with pytest.raises(TradingReadModelUnavailableError):
        service.get_recent_rejections(limit=5)


def test_trading_read_models_market_overview_requires_explicit_symbols_and_risk_gate(
    tmp_path: Path,
) -> None:
    service = TradingReadModelService(
        project_root=tmp_path,
        execution_position=SimpleNamespace(
            manage_flows={},
            _last_lifecycle_ikey_by_symbol={},
            _symbol_brackets={},
            _last_close_reason_by_symbol={},
        ),
    )

    with pytest.raises(TradingReadModelUnavailableError):
        service.get_market_overview(symbols=[], tf_sec=300)


def test_trading_read_models_allow_degraded_positions_from_portfolio_journal(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "logs" / "shadow_critical_event_journal_v1.jsonl",
        [
            {
                "event_name": "EVT:EXPOSURE_SUMMARY_UPDATED",
                "payload_fragment": {
                    "portfolio_state": {
                        "positions_last_ts_ms": 12345,
                        "positions": [
                            {
                                "symbol": "ETHUSDT",
                                "net_position": "-2.5",
                                "avg_entry_price": "2500.0",
                                "markPrice": "2490.0",
                                "unrealizedPnl": "25.0",
                                "venues": ["binance_futures"],
                            }
                        ],
                    }
                },
            }
        ],
    )
    service = TradingReadModelService(
        project_root=tmp_path, execution_position=None)

    positions = service.get_active_positions(allow_degraded=True)

    assert positions == [
        {
            "symbol": "ETHUSDT",
            "lifecycle_id": None,
            "state": "PORTFOLIO_ONLY",
            "side": "SELL",
            "qty": "2.5",
            "entry_price": "2500.0",
            "sl_price": None,
            "tp_price": None,
            "sl_order_id": None,
            "tp_order_id": None,
            "closing_position": False,
            "last_close_reason": None,
            "source": "portfolio_state",
            "portfolio_truth": True,
            "positions_last_ts_ms": 12345,
            "markPrice": "2490.0",
            "unrealizedPnl": "25.0",
        }
    ]


def test_trading_read_models_market_overview_allow_degraded_uses_snapshot_store_and_env_risk_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SnapshotStoreStub:
        source_name = "shadow_telemetry_api"

        def latest(self, symbol: str | None, tf_sec: int | None):
            if symbol == "BTCUSDT" and tf_sec == 300:
                return {
                    "snapshot_id": "snap-btc",
                    "ts_ms": 1000,
                    "symbol": "BTCUSDT",
                    "tf_sec": 300,
                    "features": {"price": "100.0"},
                    "regime": {"state": "TREND_UP"},
                    "execution": {"event": "ORDER_PLACED"},
                }
            return None

        def tail(self, symbol: str | None, limit: int):
            return []

    _write_jsonl(
        tmp_path / "logs" / "shadow_critical_event_journal_v1.jsonl",
        [
            {
                "event_name": "EVT:EXPOSURE_SUMMARY_UPDATED",
                "payload_fragment": {
                    "portfolio_state": {
                        "positions_last_ts_ms": 12345,
                        "positions": [],
                    }
                },
            }
        ],
    )
    risk_gate_path = tmp_path / "runtime" / "risk_gate_state.json"
    risk_gate_path.parent.mkdir(parents=True, exist_ok=True)
    risk_gate_path.write_text(
        json.dumps({"is_gate_open": True, "reference_equity": "2000.0"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(risk_gate_path))
    service = TradingReadModelService(
        project_root=tmp_path,
        snapshot_store=SnapshotStoreStub(),
        execution_position=None,
    )

    overview = service.get_market_overview(
        symbols=["BTCUSDT", "ETHUSDT"],
        tf_sec=300,
        allow_degraded=True,
    )

    assert overview["snapshots"] == [
        {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "ts_ms": 1000,
            "regime": {"state": "TREND_UP"},
            "features": {"price": "100.0"},
            "execution": {"event": "ORDER_PLACED"},
            "available": True,
        },
        {
            "symbol": "ETHUSDT",
            "tf_sec": 300,
            "ts_ms": None,
            "regime": None,
            "features": None,
            "execution": None,
            "available": False,
        },
    ]
    assert overview["risk_gate"]["available"] is True
    assert overview["risk_gate"]["source_path"] == str(risk_gate_path)
    assert overview["active_positions"] == []
    assert overview["runtime_health"] == {
        "execution_position_available": False,
        "snapshot_source": "shadow_telemetry_api",
        "risk_gate_available": True,
        "degraded": True,
        "degraded_reasons": [
            "missing_snapshot_truth",
            "recent_rejections_unavailable",
            "execution_position_unavailable",
        ],
    }
