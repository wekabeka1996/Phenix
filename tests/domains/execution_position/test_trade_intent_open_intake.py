from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
from vfoundation.core.schema_registry import init_global_registry

from apps.reference.domains.execution_position.intent_router import IntentRouter
from apps.reference.domains.execution_position.trade_intent_open_intake import (
    INTENT_OPEN_INTAKE_CONTRACT,
)

pytest_plugins = ("tests.domains.execution_position.conftest",)


class _CaptureBus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str | None, object]] = []

    def emit(self, topic: str, payload=None, why=None, data_ref=None, **kwargs) -> None:
        self.emitted.append((topic, payload or {}, why, data_ref))

    def listen(self, *_args, **_kwargs) -> None:
        return None


def _make_intent_payload(**overrides) -> dict:
    payload = {
        "rid": "RID-TYPED-OPEN-1",
        "instrument": "BTCUSDT",
        "side": "BUY",
        "strategy": "aurora",
        "order": {
            "qty": "0.01",
            "price": "50000",
            "price_ref": "50000",
            "reduce_only": False,
            "order_type": "LIMIT",
            "tif": "GTC",
        },
        "valid_for_ms": 15000,
        "idempotent_key": "KEY-TYPED-OPEN-1",
        "stop_price": "49000",
        "target_price": "51000",
        "regime_epoch_ref": "stable_epoch:BTCUSDT:1700000000000",
        "regime": "TREND_UP",
        "regime_confidence": 0.81,
        "regime_provenance": {
            "source_kind": "detector_cache",
            "detector_event": None,
            "cache_snapshot": {
                "cache_write_ts_ms": 1700000000456,
                "regime": "TREND_UP",
                "confidence": 0.81,
            },
        },
        "tca_budget": {
            "max_slippage_bps": "10",
            "max_latency_ms": 100,
            "maker_preference": "False",
        },
        "p": "0.5",
        "payoff_ratio_r": "1.5",
        "risk_budget": {
            "trade_cvar95_max_bps": "50",
            "session_cvar95_max_bps": "100",
        },
        "size": {
            "notional_cap_usd": "500",
            "kelly_fraction": "0.1666666666666666666666666667",
        },
        "risk_context": {"risk_score": 0.55},
        "why": ["typed_open_intake_test"],
        "dto_version": "1.0.0",
        "schema_ref": "trade_intent_v1.json",
    }
    payload.update(overrides)
    return payload


def _make_intent_message(**overrides) -> Message:
    payload = _make_intent_payload(**overrides)
    return Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid=str(payload["rid"]),
        pld=payload,
        why="typed_open_intake_test",
    )


def _make_router() -> tuple[IntentRouter, MagicMock, _CaptureBus]:
    bus = _CaptureBus()
    fsm = MagicMock()
    fsm.bus = bus
    fsm.log_adapter = MagicMock()
    fsm.handle.return_value = SimpleNamespace(
        op="DEC",
        verb="OPEN",
        rid="RID-TYPED-OPEN-1",
        pld={"symbol": "BTCUSDT"},
        why="OPEN_OK",
        data_ref=[],
    )
    router = IntentRouter(fsm)
    return router, fsm, bus


def test_valid_trade_intent_passes_through_typed_open_intake_and_builds_cmd_open() -> None:
    router, fsm, _bus = _make_router()

    router.on_trade_intent_proposed(_make_intent_message())

    fsm.handle.assert_called_once()
    cmd_open = fsm.handle.call_args.args[0]
    assert cmd_open.op == "CMD"
    assert cmd_open.verb == "OPEN"
    assert cmd_open.pld["symbol"] == "BTCUSDT"
    assert cmd_open.pld["order_type"] == "LIMIT"
    assert cmd_open.pld["price"] == "50000"
    assert cmd_open.pld["tif"] == "GTC"
    assert cmd_open.pld["valid_for_ms"] == 15000
    assert cmd_open.pld["regime_epoch_ref"] == "stable_epoch:BTCUSDT:1700000000000"
    assert cmd_open.pld["metadata"]["execution_intake_contract"] == INTENT_OPEN_INTAKE_CONTRACT
    assert cmd_open.pld["metadata"]["execution_intake_path"] == "EVT:TRADE_INTENT_PROPOSED->CMD:OPEN"
    assert "tf_sec" not in cmd_open.pld["metadata"]


def test_invalid_trade_intent_missing_order_type_is_rejected_fail_closed_at_typed_intake() -> None:
    router, fsm, bus = _make_router()
    msg = _make_intent_message(
        order={"qty": "0.01", "price": "50000", "reduce_only": False, "tif": "GTC"})

    router.on_trade_intent_proposed(msg)

    fsm.handle.assert_not_called()
    rejects = [payload for topic, payload, _why,
               _data_ref in bus.emitted if topic == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    assert "NRR-INTENT-MISSING-ORDER_TYPE" in rejects[0]["why"]
    assert rejects[0]["details"]["execution_intake_contract"] == INTENT_OPEN_INTAKE_CONTRACT


def test_reduce_only_close_routing_is_unchanged_and_does_not_use_typed_open_intake() -> None:
    router, fsm, _bus = _make_router()
    msg = _make_intent_message(
        rid="RID-REDUCE-ONLY-1",
        order={
            "qty": "0.01",
            "reduce_only": True,
            "order_type": "MARKET",
        },
    )

    with patch("apps.reference.domains.execution_position.intent_router.parse_trade_intent_open_intake") as mock_parse:
        router.on_trade_intent_proposed(msg)

    mock_parse.assert_not_called()
    fsm.handle.assert_called_once()
    cmd_close = fsm.handle.call_args.args[0]
    assert cmd_close.op == "CMD"
    assert cmd_close.verb == "CLOSE"
    assert cmd_close.pld["symbol"] == "BTCUSDT"


def test_live_execpos_open_path_does_not_bypass_typed_intake(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000",
        "positions": [],
        "positions_last_ts_ms": 9_999_999_999_999,
    }
    fsm.exposure_guard.on_portfolio(fsm._latest_portfolio_state)

    with patch(
        "apps.reference.domains.execution_position.intent_router.parse_trade_intent_open_intake",
        wraps=__import__(
            "apps.reference.domains.execution_position.intent_router",
            fromlist=["parse_trade_intent_open_intake"],
        ).parse_trade_intent_open_intake,
    ) as wrapped_parse:
        fsm._on_trade_intent_proposed(_make_intent_message())

    assert wrapped_parse.call_count == 1


def test_schema_active_live_seam_rejects_out_of_range_regime_confidence_at_typed_intake(fsm_config) -> None:
    init_global_registry(project_root=".")
    bus = FSMCore()
    rejects: list[dict] = []
    opened: list[dict] = []
    bus.listen("EVT:TRADE_INTENT_REJECTED",
               lambda msg: rejects.append(msg.pld))
    bus.listen("DEC:OPEN", lambda msg: opened.append(msg.pld))

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        fsm = __import__(
            "apps.reference.domains.execution_position.fsm",
            fromlist=["ExecPosFSM"],
        ).ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)
        fsm.order_guardian = mock_guardian_cls.return_value

    payload = _make_intent_payload(
        rid="RID-SCHEMA-ACTIVE-TYPED-REJECT-1",
        idempotent_key="KEY-SCHEMA-ACTIVE-TYPED-REJECT-1",
        regime_confidence=1.5,
        why=["schema_active_typed_reject"],
    )

    bus.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload=payload,
        why="schema_active_typed_reject",
    )

    assert opened == []
    assert len(rejects) == 1
    assert rejects[0]["reason_code"] == "NRR-INTENT-OPEN-INTAKE-INVALID"
    assert rejects[0]["details"]["execution_intake_contract"] == INTENT_OPEN_INTAKE_CONTRACT
    assert rejects[0]["details"]["execution_intake_stage"] == "typed_open_intake"


def test_downstream_cmd_open_payload_validation_still_runs_after_typed_intake(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000",
        "positions": [],
        "positions_last_ts_ms": 9_999_999_999_999,
    }
    fsm.exposure_guard.on_portfolio(fsm._latest_portfolio_state)

    from apps.reference.domains.execution_position.fsm_open import CmdOpenPayload

    original_validate = CmdOpenPayload.model_validate
    calls: list[dict] = []

    def _wrapped_validate(payload):
        calls.append(dict(payload))
        return original_validate(payload)

    with patch.object(CmdOpenPayload, "model_validate", side_effect=_wrapped_validate):
        fsm._on_trade_intent_proposed(_make_intent_message())

    assert calls, "Expected downstream CmdOpenPayload.model_validate to run"
    assert calls[0]["metadata"]["execution_intake_contract"] == INTENT_OPEN_INTAKE_CONTRACT
    assert calls[0]["regime_epoch_ref"] == "stable_epoch:BTCUSDT:1700000000000"


def test_schema_validation_for_trade_intent_proposed_remains_compatible() -> None:
    init_global_registry(project_root=".")
    bus = FSMCore()
    observed: list[dict] = []
    bus.listen("EVT:TRADE_INTENT_PROPOSED",
               lambda msg: observed.append(msg.pld))
    payload = _make_intent_payload()

    bus.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload=payload,
        why="schema_compatibility",
    )

    assert observed
    assert observed[0]["instrument"] == "BTCUSDT"
    assert observed[0]["regime_epoch_ref"] == "stable_epoch:BTCUSDT:1700000000000"


def test_typed_intake_rejection_diagnostics_are_operator_visible() -> None:
    router, fsm, bus = _make_router()
    msg = _make_intent_message(
        order={"qty": "0.01", "reduce_only": False, "order_type": "LIMIT", "tif": "GTC"})

    router.on_trade_intent_proposed(msg)

    fsm.handle.assert_not_called()
    rejects = [payload for topic, payload, _why,
               _data_ref in bus.emitted if topic == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    assert rejects[0]["details"]["execution_intake_contract"] == INTENT_OPEN_INTAKE_CONTRACT
    assert rejects[0]["details"]["execution_intake_stage"] == "typed_open_intake"
