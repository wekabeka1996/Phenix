"""
test_mapper_emits_external_open_request.py

Tests that register_llm_command_mapper() correctly maps
CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1
with correct payload shape and honest field forwarding.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock


def _make_cmd_payload(**overrides) -> Dict[str, Any]:
    base = {
        "request_id": "req-1",
        "intent_id": "intent-42",
        "ts_ms": 1_700_000_000_000,
        "symbol": "BNBUSDT",
        "side": "BUY",
        "order": {
            "type": "LIMIT",
            "limit_price": "300.50",
            "qty": "1.0",
            "time_in_force": "GTC",
        },
        "brackets": {
            "tp_price": "310.00",
            "sl_price": "295.00",
        },
        "snapshot_ref": {
            "snapshot_id": "snap-1",
            "inputs_digest": "digest12345678",
        },
        "why_short": "test llm signal",
        "idempotency_key": "idem-key-42-long-enough",
    }
    base.update(overrides)
    return base


def _run_mapper(cmd_payload: Dict[str, Any]):
    from apps.reference.domains.shadow_telemetry.main_bridge import register_llm_command_mapper
    from vfoundation.core.protocol import Message

    captured = []
    fsm = MagicMock()

    def fake_emit(event_name, payload=None, why=""):
        captured.append({"event": event_name, "payload": payload, "why": why})

    fsm.emit.side_effect = fake_emit

    registered = {}

    def fake_listen(event_name, handler):
        registered[event_name] = handler

    fsm.listen.side_effect = fake_listen

    register_llm_command_mapper(fsm)
    handler = registered["CMD:LLM_INTENT_SUBMIT_V1"]

    evt = Message(
        op="CMD",
        verb="LLM_INTENT_SUBMIT_V1",
        src="shadow_telemetry",
        dst="main",
        rid=cmd_payload["intent_id"],
        pld=cmd_payload,
        why="test",
    )
    handler(evt)
    return captured


def _get_ext_payload(captured):
    return next(e["payload"] for e in captured if e["event"] == "CMD:EXTERNAL_OPEN_REQUEST_V1")


class TestMapperEmitsExternalOpenRequest:

    def test_mapper_emits_external_open_request_v1(self):
        events = _run_mapper(_make_cmd_payload())
        ext_events = [e for e in events if e["event"]
                      == "CMD:EXTERNAL_OPEN_REQUEST_V1"]
        assert len(ext_events) == 1

    def test_mapper_payload_has_source(self):
        pld = _get_ext_payload(_run_mapper(_make_cmd_payload()))
        assert pld["source"] == "external_llm"

    def test_mapper_payload_has_intent_id(self):
        pld = _get_ext_payload(_run_mapper(
            _make_cmd_payload(intent_id="my-intent-99")))
        assert pld["intent_id"] == "my-intent-99"

    def test_mapper_carries_brackets(self):
        pld = _get_ext_payload(_run_mapper(_make_cmd_payload()))
        assert pld["stop_price"] == "295.00"
        assert pld["target_price"] == "310.00"

    def test_mapper_carries_snapshot_ref(self):
        pld = _get_ext_payload(_run_mapper(_make_cmd_payload()))
        snap = pld["snapshot_ref"]
        assert snap is not None
        assert snap["snapshot_id"] == "snap-1"
        assert snap["inputs_digest"] == "digest12345678"

    def test_mapper_tif_explicit_no_fallback(self):
        """tif must come directly from cmd.order.time_in_force, not injected as GTC."""
        pld = _get_ext_payload(_run_mapper(_make_cmd_payload()))
        assert pld["tif"] == "GTC"

        # Verify IOC is forwarded as-is
        custom = _make_cmd_payload()
        custom["order"]["time_in_force"] = "IOC"
        pld2 = _get_ext_payload(_run_mapper(custom))
        assert pld2["tif"] == "IOC"
