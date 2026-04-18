from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from apps.reference.domains.execution_position.terminal_order_contracts import (
    emit_canonical_terminal_order_event,
)
from apps.reference.telemetry.trade_lifecycle_logger import (
    POSITION_POLICY_SIDECAR_RECORD_KIND,
    trade_lifecycle,
)
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
from vfoundation.dr import wal


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_sidecar_close_request_state_uses_isolated_trade_lifecycle_sink(
    fsm_harness,
    tmp_path,
) -> None:
    fsm, bus, cfg = fsm_harness

    cfg.get_domain_mode.return_value = "testnet"  # type: ignore[attr-defined]

    adapter = AsyncMock()
    adapter.base_url = "https://testnet.binancefuture.com"
    adapter.get_open_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "1.0"}]
    adapter.get_open_orders.return_value = []

    fsm.adapter = adapter
    fsm.shadow_mode = False

    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="execution_position",
        dst="execution_position",
        rid="ppsreq:BTCUSDT:close-1",
        why="position_policy_sidecar_soft_close",
        pld={
            "symbol": "BTCUSDT",
            "reduce_only": True,
            "policy_context": {
                "symbol": "BTCUSDT",
                "policy_source": "position_policy_sidecar",
                "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
                "source_trace_id": "pps:BTCUSDT:1:1",
                "request_id": "ppsreq:BTCUSDT:close-1",
                "request_event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
                "requested_action": "SOFT_CLOSE",
                "requested_qty": None,
                "target_mode": "symbol_current_net_only",
                "allowed_action_scope": {
                    "soft_close_symbol_current_net_only": True,
                    "partial_reduce": False,
                    "bracket_mutation": False,
                    "exact_targeting": False,
                },
                "reason_codes": [
                    "trigger:regime_detected",
                    "recommend_soft_close_threshold_met",
                ],
                "score_snapshot": {"soft_close_pressure": 0.6},
                "position_snapshot": {"symbol": "BTCUSDT", "side": "BUY"},
                "feature_ref": {},
                "regime_ref": {},
                "freshness_snapshot": {},
                "fill_correlation": {},
                "portfolio_correlation": {},
                "action_package_version": "phase2_action_package_v1",
                "request_ts_ms": 1_000_000,
            },
        },
    )

    async def _run() -> None:
        fsm_sleep = AsyncMock()
        import apps.reference.domains.execution_position.fsm as fsm_mod

        orig_sleep = fsm_mod.asyncio.sleep
        fsm_mod.asyncio.sleep = fsm_sleep
        try:
            await fsm._execute_decision(decision)
        finally:
            fsm_mod.asyncio.sleep = orig_sleep

    asyncio.run(_run())

    isolated_path = Path(fsm._trade_lifecycle_log_path())
    assert isolated_path == tmp_path / "logs" / "trade_lifecycle.jsonl"
    assert isolated_path.resolve() != Path("logs/trade_lifecycle.jsonl").resolve()

    rows = _read_jsonl(isolated_path)
    sidecar_rows = [
        row
        for row in rows
        if row.get("record_kind") == POSITION_POLICY_SIDECAR_RECORD_KIND
        and row.get("request_id") == "ppsreq:BTCUSDT:close-1"
    ]
    assert len(sidecar_rows) == 1
    assert sidecar_rows[0]["trace_id"] == "pps:BTCUSDT:1:1"
    assert sidecar_rows[0]["request_state"] == "execution_submitted"
    assert sidecar_rows[0]["execution_close_side"] == "SELL"
    assert sidecar_rows[0]["execution_close_qty"] == "1.0"
    allowed = sidecar_rows[0]["policy_context"]["allowed_action_scope"]
    assert allowed["soft_close_symbol_current_net_only"] is True
    assert allowed["partial_reduce"] is False
    assert allowed["bracket_mutation"] is False
    assert allowed["exact_targeting"] is False

    state_events = [
        args[0]
        for topic, args, _kwargs in bus.events
        if topic == "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE"
    ]
    assert len(state_events) == 1
    assert state_events[0]["request_id"] == "ppsreq:BTCUSDT:close-1"


def test_canonical_order_rejected_still_writes_to_isolated_wal_and_lifecycle(
    tmp_path,
) -> None:
    bus = FSMCore()
    observed: list[dict] = []
    bus.listen("EVT:ORDER_REJECTED", lambda msg: observed.append(dict(msg.pld or {})))

    trade_lifecycle.on_intent(
        rid="rid-phase8-reject-1",
        symbol="BTCUSDT",
        side="BUY",
        strategy_id="aurora",
        entry_type="MARKET",
    )

    async def _run() -> None:
        await emit_canonical_terminal_order_event(
            fsm=SimpleNamespace(emit=bus.emit),
            event_name="EVT:ORDER_REJECTED",
            payload={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "reason_code": "ADAPTER_ERROR",
                "reason_text": "Order would immediately trigger.",
                "origin_class": "execution_adapter",
            },
            rid="rid-phase8-reject-1",
            src="execution_position",
            dst="decision_making",
            why="adapter_execution_failed",
            write_wal=True,
            fallback_ts_ms=1775300000000,
        )

    asyncio.run(_run())

    wal_records = wal.read_all()
    rejected = [row for row in wal_records if row.get("verb") == "ORDER_REJECTED"]
    assert len(rejected) == 1
    wal_payload = rejected[0]["pld"]
    assert wal_payload["reason_code"] == "ADAPTER_ERROR"
    assert wal_payload["reject_reason_normalized"] == "ADAPTER_ERROR: ORDER WOULD IMMEDIATELY TRIGGER."
    assert wal_payload["origin_class"] == "execution_adapter"

    assert len(observed) == 1
    assert observed[0]["reason_code"] == "ADAPTER_ERROR"
    assert observed[0]["symbol"] == "BTCUSDT"

    lifecycle_path = Path(trade_lifecycle._log_file)
    assert lifecycle_path == tmp_path / "logs" / "trade_lifecycle.jsonl"
    lifecycle_rows = _read_jsonl(lifecycle_path)
    assert len(lifecycle_rows) == 1
    assert lifecycle_rows[0]["rid"] == "rid-phase8-reject-1"
    assert lifecycle_rows[0]["status"] == "REJECTED"
    assert lifecycle_rows[0]["close_reason"] == "ADAPTER_ERROR: ORDER WOULD IMMEDIATELY TRIGGER."
