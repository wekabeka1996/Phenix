from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.domains.shadow_telemetry.contracts import TradingDecisionV1
from apps.reference.domains.shadow_telemetry.llm_orchestration import (
    DecisionCoordinator,
    MarketContextCollector,
    PositionGuardian,
)
from apps.reference.domains.shadow_telemetry.trading_read_models import (
    TradingReadModelService,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _runtime_stub():
    manage_flow = SimpleNamespace(
        has_active_lifecycle=lambda: True,
        state=SimpleNamespace(value="BRACKETS_PLACED"),
        position_side="BUY",
        position_qty=Decimal("1.5"),
        position_entry_price=Decimal("100.0"),
        entry_order_id="entry-1",
        entry_client_order_id="cid-1",
        sl_price=Decimal("99.0"),
        tp_price=Decimal("102.0"),
        _closing_position=False,
    )
    return SimpleNamespace(
        manage_flows={"BNBUSDT": manage_flow},
        _last_lifecycle_ikey_by_symbol={"BNBUSDT": "life-1"},
        _symbol_brackets={"BNBUSDT": {"sl_order_id": "sl-1", "tp_order_id": "tp-1"}},
        _last_close_reason_by_symbol={},
    )


def test_market_context_collector_and_guardian_persist_packets(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "data" / "shadow_telemetry" / "snapshots" / "BNBUSDT" / "2026-05-10" / "12.jsonl",
        [{"snapshot_id": "snap-1", "ts_ms": 1234, "symbol": "BNBUSDT", "tf_sec": 300, "features": {"obi": 0.2}}],
    )
    _write_jsonl(
        tmp_path / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl",
        [{"ts_ms": 1240, "symbol": "BNBUSDT", "neocortex_action": "NO_ACTION"}],
    )
    _write_jsonl(
        tmp_path / "logs" / "order_log_v1.jsonl",
        [{"ts_ms": 1250, "symbol": "BNBUSDT", "reason_code": "REJECT_TEST", "reason": "reject path"}],
    )
    (tmp_path / "data" / "risk_gate_state.json").write_text(
        json.dumps({"is_gate_open": True, "reference_equity": "2000.0"}),
        encoding="utf-8",
    )

    read_models = TradingReadModelService(project_root=tmp_path, execution_position=_runtime_stub())
    collector = MarketContextCollector(read_models)
    coordinator = DecisionCoordinator(project_root=tmp_path)
    guardian = PositionGuardian(collector=collector, coordinator=coordinator)

    packet = collector.collect_packet(symbol="BNBUSDT", packet_kind="fast", context_symbols=["BTCUSDT"])
    persisted_packet = coordinator.persist_packet(packet)
    guardian_packet = guardian.collect_guardian_packet(
        symbol="BNBUSDT",
        lifecycle_id="life-1",
        context_symbols=["BTCUSDT"],
    )

    assert packet.snapshot is not None
    assert persisted_packet["packet_kind"] == "fast"
    assert guardian_packet.packet_kind == "guardian"
    assert guardian_packet.lifecycle_id == "life-1"
    persisted_lines = (tmp_path / "logs" / "shadow_telemetry" / "market_context_packets_v1.jsonl").read_text(
        encoding="utf-8"
    ).strip().splitlines()
    assert len(persisted_lines) == 2


def test_decision_coordinator_persists_allowed_decision_and_rejects_blocked_action(tmp_path: Path) -> None:
    coordinator = DecisionCoordinator(
        project_root=tmp_path,
        execution_permissions={"allow_open": True, "allow_close": False, "allow_bracket_amend": True},
    )

    open_decision = TradingDecisionV1(
        action="OPEN_INTENT",
        symbol="BNBUSDT",
        confidence=0.82,
        rationale_short="breakout context aligned",
        packet_ref="packet-1",
        ttl_ms=300000,
        open={
            "side": "BUY",
            "qty": "0.5",
            "limit_price": "100.0",
            "tp_price": "101.5",
            "sl_price": "99.0",
        },
    )
    close_decision = TradingDecisionV1(
        action="CLOSE_POSITION",
        symbol="BNBUSDT",
        confidence=0.61,
        rationale_short="risk gate changed",
        packet_ref="packet-2",
        ttl_ms=300000,
        close={"lifecycle_id": "life-1", "reason": "risk-off"},
    )

    persisted = coordinator.persist_decision(open_decision)
    assert persisted["action"] == "OPEN_INTENT"
    stored = (tmp_path / "logs" / "shadow_telemetry" / "trading_decisions_v1.jsonl").read_text(
        encoding="utf-8"
    )
    assert "OPEN_INTENT" in stored

    with pytest.raises(ValueError, match="allow_close=false"):
        coordinator.persist_decision(close_decision)
