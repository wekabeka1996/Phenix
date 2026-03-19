"""
test_llm_command_mapper_emits_strategy_signal.py

Tests the CMD:LLM_INTENT_SUBMIT_V1 -> EVT:STRATEGY_SIGNAL_PRODUCED mapper.

AUDIT FINDINGS verified:
  - mapper hardcodes tf_sec=300 (profile declares timeframe_sec=60) — DRIFT
  - strategy_id is "llm_microstructure"
  - readiness.warmup_ok=True (hardcoded bypass)
  - price_ctx.entry_price = cmd.order.limit_price
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call
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
    """
    AUDIT: Proves mapper behavior for CMD:LLM_INTENT_SUBMIT_V1.
    """

    def _build_fsm_and_run_mapper(self, cmd_payload: Dict[str, Any]):
        """Helper: register mapper on mock FSM and dispatch command."""
        from apps.reference.domains.shadow_telemetry.main_bridge import register_llm_command_mapper
        from vfoundation.core.protocol import Message

        captured_events = []

        fsm = MagicMock()

        def fake_emit(event_name: str, payload: Any = None, why: str = "") -> None:
            captured_events.append({"event": event_name, "payload": payload, "why": why})

        fsm.emit.side_effect = fake_emit

        # Capture the listener handler
        registered_handler = {}

        def fake_listen(event_name: str, handler) -> None:
            registered_handler[event_name] = handler

        fsm.listen.side_effect = fake_listen

        register_llm_command_mapper(fsm)

        assert "CMD:LLM_INTENT_SUBMIT_V1" in registered_handler, (
            "Mapper must register listener for CMD:LLM_INTENT_SUBMIT_V1"
        )
        handler = registered_handler["CMD:LLM_INTENT_SUBMIT_V1"]

        # Build event
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

    def test_mapper_emits_strategy_signal_produced(self):
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)

        signal_events = [e for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"]]
        assert len(signal_events) == 1, (
            f"Expected exactly 1 EVT:STRATEGY_SIGNAL_PRODUCED, got {len(signal_events)}"
        )

    def test_mapper_hardcodes_tf_sec_300_not_profile_60(self):
        """
        AUDIT FINDING H1 — CONFIRMED DRIFT:
        Mapper hardcodes tf_sec=300. Profile declares timeframe_sec=60.
        This is a semantic error (not a runtime blocker since ttl_by_tf_sec has 300:1200)
        but creates valid_for_ms=1200s instead of the ~300s expected for a 60s timeframe.
        """
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)
        signal_events = [e for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"]]
        assert len(signal_events) == 1

        pld = signal_events[0]["payload"]
        tf_sec = pld.get("tf_sec")

        # CONFIRMED DRIFT: mapper emits 300, not 60 (the profile value)
        assert tf_sec == 300, (
            f"AUDIT: Mapper emits tf_sec={tf_sec!r} but profile declares timeframe_sec=60. "
            "This is a semantic drift. The fix is to align mapper tf_sec with profile."
        )
        # Document what the correct value should be:
        assert tf_sec != 60, (
            "If this fails, mapper was already fixed to use profile value. Update test."
        )

    def test_mapper_sets_strategy_id_llm_microstructure(self):
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"])

        assert pld["strategy_id"] == "llm_microstructure", (
            f"Expected strategy_id='llm_microstructure' but got {pld['strategy_id']!r}"
        )

    def test_mapper_sets_warmup_ok_true(self):
        """Mapper hardcodes warmup_ok=True to bypass warmup gate for external intents."""
        cmd = _make_cmd_payload()
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"])

        readiness = pld.get("readiness", {})
        assert readiness.get("warmup_ok") is True, (
            f"Expected warmup_ok=True in signal payload, got {readiness!r}"
        )

    def test_mapper_carries_price_ctx_from_cmd(self):
        cmd = _make_cmd_payload(
            limit_price="0.012345",
            sl_price="0.011000",
            tp_price="0.014000",
        )
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"])

        price_ctx = pld.get("price_ctx", {})
        assert price_ctx.get("entry_price") == "0.012345"
        assert price_ctx.get("stop_price") == "0.011000"
        assert price_ctx.get("target_price") == "0.014000"

    def test_mapper_preserves_symbol_and_side(self):
        cmd = _make_cmd_payload(symbol="1000PEPEUSDT", side="BUY")
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"])

        assert pld["symbol"] == "1000PEPEUSDT"
        assert pld["side"] == "BUY"

    def test_mapper_preserves_rid_from_intent_id(self):
        cmd = _make_cmd_payload(intent_id="test-intent-xyz")
        events = self._build_fsm_and_run_mapper(cmd)
        pld = next(e["payload"] for e in events if "STRATEGY_SIGNAL_PRODUCED" in e["event"])

        assert pld["rid"] == "test-intent-xyz", (
            f"Expected rid=intent_id='test-intent-xyz', got {pld['rid']!r}"
        )
