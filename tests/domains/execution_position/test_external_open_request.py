"""
test_external_open_request.py

Tests CMD:EXTERNAL_OPEN_REQUEST_V1 intake handler in IntentRouter.
Covers: gates, valid_for_ms resolution, config failure separation,
provenance isolation, and guard chain reuse.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest


def _make_external_payload(**overrides) -> Dict[str, Any]:
    """Minimal valid CMD:EXTERNAL_OPEN_REQUEST_V1 payload."""
    base = {
        "rid": "ext-rid-001",
        "intent_id": "ext-intent-001",
        "symbol": "BNBUSDT",
        "side": "BUY",
        "qty": "1.0",
        "order_type": "LIMIT",
        "price": "300.50",
        "tif": "GTC",
        "valid_for_ms": None,
        "stop_price": "295.00",
        "target_price": "310.00",
        "idempotent_key": "idem-ext-001",
        "source": "external_llm",
        "snapshot_ref": {"snapshot_id": "snap-1", "inputs_digest": "digest12345678"},
        "why_short": "test external signal",
    }
    base.update(overrides)
    return base


def _make_msg(pld: Dict[str, Any]):
    """Build a Message-like object for IntentRouter."""
    from vfoundation.core.fsm_emit_compat import Message
    return Message(
        op="CMD",
        verb="EXTERNAL_OPEN_REQUEST_V1",
        src="shadow_telemetry",
        dst="execution_position",
        rid=pld.get("rid", "test-rid"),
        pld=pld,
        why="test",
    )


def _build_router(*, config_ttl: Optional[int] = 120000, config_reachable: bool = True):
    """
    Build IntentRouter with mocked FSM.
    config_ttl: value of pending_entry_ttl_ms (None = field absent)
    config_reachable: if False, config access raises AttributeError
    """
    from apps.reference.domains.execution_position.intent_router import IntentRouter

    fsm = MagicMock()
    fsm.bus = MagicMock()
    fsm.log_adapter = MagicMock()

    emitted_events = []

    def capture_emit(event_name, payload, why="", data_ref=None):
        emitted_events.append({"event": event_name, "payload": payload, "why": why})

    fsm.bus.emit.side_effect = capture_emit

    if config_reachable:
        llm_cfg = MagicMock()
        llm_cfg.pending_entry_ttl_ms = config_ttl
        fsm.config = MagicMock()
        fsm.config.strategies.llm_microstructure = llm_cfg
    else:
        # Config path must raise AttributeError — use spec=[] so attribute access fails
        config_mock = MagicMock()
        strategies_mock = MagicMock(spec=[])
        config_mock.strategies = strategies_mock
        fsm.config = config_mock

    router = IntentRouter(fsm)
    return router, fsm, emitted_events


def _get_reject_events(emitted):
    return [e for e in emitted if e["event"] == "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1"]


def _get_trade_intent_rejected(emitted):
    return [e for e in emitted if e["event"] == "EVT:TRADE_INTENT_REJECTED"]


# ============================================================
# Happy path
# ============================================================

class TestExternalOpenRequestHappyPath:

    def test_external_request_reaches_handle_and_produces_dec_open(self):
        router, fsm, emitted = _build_router(config_ttl=120000)
        result_msg = MagicMock()
        result_msg.op = "DEC"
        result_msg.verb = "OPEN"
        result_msg.rid = "ext-rid-001"
        result_msg.pld = {"symbol": "BNBUSDT"}
        result_msg.why = "approved"
        result_msg.data_ref = None
        fsm.handle.return_value = result_msg

        msg = _make_msg(_make_external_payload())
        router.on_external_open_request(msg)

        fsm.handle.assert_called_once()
        cmd_open = fsm.handle.call_args[0][0]
        assert cmd_open.op == "CMD"
        assert cmd_open.verb == "OPEN"
        assert cmd_open.pld["symbol"] == "BNBUSDT"
        assert cmd_open.pld["strategy"] == "llm_microstructure"

    def test_valid_for_ms_from_config_fallback(self):
        router, fsm, emitted = _build_router(config_ttl=120000)
        fsm.handle.return_value = MagicMock(op="DEC", verb="OPEN", rid="r1", pld={}, why="ok", data_ref=None)

        msg = _make_msg(_make_external_payload(valid_for_ms=None))
        router.on_external_open_request(msg)

        cmd_open = fsm.handle.call_args[0][0]
        assert cmd_open.pld["valid_for_ms"] == 120000

    def test_valid_for_ms_from_payload(self):
        router, fsm, emitted = _build_router(config_ttl=120000)
        fsm.handle.return_value = MagicMock(op="DEC", verb="OPEN", rid="r1", pld={}, why="ok", data_ref=None)

        msg = _make_msg(_make_external_payload(valid_for_ms=60000))
        router.on_external_open_request(msg)

        cmd_open = fsm.handle.call_args[0][0]
        assert cmd_open.pld["valid_for_ms"] == 60000

    def test_price_ref_set_for_exposure_guard(self):
        router, fsm, emitted = _build_router(config_ttl=120000)
        fsm.handle.return_value = MagicMock(op="DEC", verb="OPEN", rid="r1", pld={}, why="ok", data_ref=None)

        msg = _make_msg(_make_external_payload(price="300.50"))
        router.on_external_open_request(msg)

        cmd_open = fsm.handle.call_args[0][0]
        assert cmd_open.pld["price_ref"] == "300.50"

    def test_strategy_is_llm_microstructure(self):
        router, fsm, emitted = _build_router(config_ttl=120000)
        fsm.handle.return_value = MagicMock(op="DEC", verb="OPEN", rid="r1", pld={}, why="ok", data_ref=None)

        msg = _make_msg(_make_external_payload())
        router.on_external_open_request(msg)

        cmd_open = fsm.handle.call_args[0][0]
        assert cmd_open.pld["strategy"] == "llm_microstructure"

    def test_preserves_intent_id_through_to_cmd_open_metadata(self):
        router, fsm, emitted = _build_router(config_ttl=120000)
        fsm.handle.return_value = MagicMock(op="DEC", verb="OPEN", rid="r1", pld={}, why="ok", data_ref=None)

        msg = _make_msg(_make_external_payload(intent_id="ext-intent-unique-42"))
        router.on_external_open_request(msg)

        cmd_open = fsm.handle.call_args[0][0]
        assert cmd_open.pld["metadata"]["source_intent_id"] == "ext-intent-unique-42"


# ============================================================
# Gate rejections
# ============================================================

class TestExternalOpenRequestGateRejections:

    def test_reject_missing_intent_id(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(intent_id=None))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-MISSING-INTENT-ID"
        assert rejects[0]["payload"]["intent_id"] is None  # NOT "unknown"
        fsm.handle.assert_not_called()

    def test_reject_invalid_source(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(source="internal_dm"))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-SOURCE-INVALID"
        fsm.handle.assert_not_called()

    def test_reject_if_order_type_not_limit_in_v1(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(order_type="MARKET"))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-ORDER-TYPE-NOT-LIMIT"
        fsm.handle.assert_not_called()

    def test_reject_if_tif_missing_and_no_config_default(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(tif=None))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-MISSING-TIF"
        fsm.handle.assert_not_called()

    def test_reject_missing_price_for_limit_v1(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(price=None))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-MISSING-PRICE"
        fsm.handle.assert_not_called()


# ============================================================
# valid_for_ms resolution & config error separation
# ============================================================

class TestExternalOpenRequestValidForMs:

    def test_reject_missing_valid_for_ms(self):
        router, fsm, emitted = _build_router(config_ttl=None)
        msg = _make_msg(_make_external_payload(valid_for_ms=None))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-MISSING-VALID-FOR-MS"
        fsm.handle.assert_not_called()

    def test_reject_config_missing_emits_config_code(self):
        router, fsm, emitted = _build_router(config_reachable=False)
        msg = _make_msg(_make_external_payload(valid_for_ms=None))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-CONFIG-MISSING"
        fsm.handle.assert_not_called()

    def test_reject_config_invalid_ttl_emits_config_invalid(self):
        router, fsm, emitted = _build_router(config_ttl=500)
        msg = _make_msg(_make_external_payload(valid_for_ms=None))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXT-CONFIG-INVALID"
        fsm.handle.assert_not_called()


# ============================================================
# Provenance isolation & reject event shape
# ============================================================

class TestExternalOpenRequestProvenance:

    def test_external_reject_event_never_emits_trade_intent_rejected(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(source="bad_source"))
        router.on_external_open_request(msg)

        trade_rejects = _get_trade_intent_rejected(emitted)
        assert len(trade_rejects) == 0, "External path must NEVER emit EVT:TRADE_INTENT_REJECTED"

        ext_rejects = _get_reject_events(emitted)
        assert len(ext_rejects) == 1

    def test_rejection_emits_external_event_with_schema_fields(self):
        router, fsm, emitted = _build_router()
        msg = _make_msg(_make_external_payload(source="bad"))
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        pld = rejects[0]["payload"]
        assert "ts_ms" in pld
        assert "rid" in pld
        assert "intent_id" in pld
        assert "symbol" in pld
        assert "reason_code" in pld
        assert "reason_text" in pld
        assert pld["source"] == "external_llm"
        assert pld["strategy"] == "llm_microstructure"
        assert pld["stage"] == "EXTERNAL_INTAKE"


# ============================================================
# Guard chain applies (EP guards via handle())
# ============================================================

class TestExternalOpenRequestGuardChain:

    def test_cooldown_guard_applies(self):
        """When handle() returns ERR, it's routed as external rejection."""
        router, fsm, emitted = _build_router(config_ttl=120000)
        err_result = MagicMock()
        err_result.op = "ERR"
        err_result.verb = "OPEN"
        err_result.rid = "ext-rid-001"
        err_result.pld = {"symbol": "BNBUSDT"}
        err_result.why = "cooldown_active:BNBUSDT"
        err_result.data_ref = None
        fsm.handle.return_value = err_result

        msg = _make_msg(_make_external_payload())
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXECUTION-REJECTED"

    def test_exposure_guard_applies(self):
        """When handle() returns ERR for exposure, it's routed as external rejection."""
        router, fsm, emitted = _build_router(config_ttl=120000)
        err_result = MagicMock()
        err_result.op = "ERR"
        err_result.verb = "OPEN"
        err_result.rid = "ext-rid-001"
        err_result.pld = {"symbol": "BNBUSDT"}
        err_result.why = "exposure_exceeded:BNBUSDT"
        err_result.data_ref = None
        fsm.handle.return_value = err_result

        msg = _make_msg(_make_external_payload())
        router.on_external_open_request(msg)

        rejects = _get_reject_events(emitted)
        assert len(rejects) == 1
        assert rejects[0]["payload"]["reason_code"] == "NRR-EXECUTION-REJECTED"
