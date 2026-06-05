"""
test_llm_command_mapper_emits_strategy_signal.py

Tests the CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1 mapper.

Updated: mapper no longer emits EVT:STRATEGY_SIGNAL_PRODUCED.
It now emits CMD:EXTERNAL_OPEN_REQUEST_V1 with flat payload + honest provenance.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from typing import Any, Dict


def _make_cmd_payload(
    intent_id: str = "test-intent-001",
    symbol: str = "1000PEPEUSDT",
    side: str = "BUY",
    limit_price: str = "0.012345",
    qty: str = "1000",
    time_in_force: str = "GTC",
    sl_price: str = "0.011000",
    tp_price: str = "0.014000",
    why_short: str = "llm_test_signal",
    ts_ms: int = 1_700_000_000_000,
) -> Dict[str, Any]:
    return {
        "intent_id": intent_id,
        "request_id": "req-001",
        "symbol": symbol,
        "side": side,
        "ts_ms": ts_ms,
        "why_short": why_short,
        "idempotency_key": "idem-001",
        "order": {
            "type": "LIMIT",
            "time_in_force": time_in_force,
            "limit_price": limit_price,
            "qty": qty,
        },
        "brackets": {
            "tp_price": tp_price,
            "sl_price": sl_price,
        },
        "snapshot_ref": None,
        "model_meta": None,
        "policy_hints": {},
    }


class TestLLMCommandMapper:
    """Tests mapper CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1."""

    def _build_fsm_and_run_mapper(self, cmd_payload: Dict[str, Any]):
        """Helper: register mapper on mock FSM and dispatch command."""
        from apps.reference.domains.shadow_telemetry.main_bridge import register_llm_command_mapper
        from vfoundation.core.protocol import Message

        captured_events = []

        fsm = MagicMock()

        def fake_emit(event_name: str, payload: Any = None, why: str = "") -> None:
            captured_events.append({"event": event_name, "payload": payload, "why": why})

        fsm.emit.side_effect = fake_emit

        registered_handler = {}

        def fake_listen(event_name: str, handler) -> None:
            registered_handler[event_name] = handler

        fsm.listen.side_effect = fake_listen

        register_llm_command_mapper(fsm)

        assert "CMD:LLM_INTENT_SUBMIT_V1" in registered_handler
        handler = registered_handler["CMD:LLM_INTENT_SUBMIT_V1"]

        evt = Message(
            op="CMD",
            verb="LLM_INTENT_SUBMIT_V1",
            src="shadow_telemetry_api",
            dst="main",
            rid=cmd_payload["intent_id"],
            pld=cmd_payload,
            why="llm_intent_submit",
        )

        handler(evt)
        return captured_events

    def test_mapper_emits_external_open_request_v1(self):
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)

        ext_events = [e for e in events if e["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1"]
        assert len(ext_events) == 1, (
            f"Expected exactly 1 CMD:EXTERNAL_OPEN_REQUEST_V1, got {len(ext_events)}"
        )

    def test_mapper_does_not_emit_strategy_signal_produced(self):
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)
        signal_events = [e for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"]]
        assert len(signal_events) == 0, "Mapper must NOT emit EVT:STRATEGY_SIGNAL_PRODUCED"

    def test_mapper_does_not_emit_cmd_open(self):
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)
        open_events = [e for e in events if e["event"] == "CMD:OPEN"]
        assert len(open_events) == 0, "Mapper must NOT emit CMD:OPEN directly"

    def test_mapper_sets_source_external_llm(self):
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if e["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
        assert pld["source"] == "external_llm"

    def test_mapper_sets_intent_id(self):
        cmd = _make_cmd_payload(intent_id="test-intent-xyz")
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if e["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
        assert pld["intent_id"] == "test-intent-xyz"

    def test_mapper_preserves_symbol_and_side(self):
        cmd = _make_cmd_payload(symbol="1000PEPEUSDT", side="BUY")
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if e["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
        assert pld["symbol"] == "1000PEPEUSDT"
        assert pld["side"] == "BUY"

    def test_mapper_carries_order_fields_flat(self):
        cmd = _make_cmd_payload(
            limit_price="0.012345",
            qty="1000",
            time_in_force="GTC",
        )
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if e["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")
        assert pld["price"] == "0.012345"
        assert pld["qty"] == "1000"
        assert pld["order_type"] == "LIMIT"
        assert pld["tif"] == "GTC"
