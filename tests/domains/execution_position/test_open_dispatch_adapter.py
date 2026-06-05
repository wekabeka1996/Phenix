from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.config_loader import get_config
from apps.reference.domains.execution_position.flows.open.intent_router import IntentRouter
from apps.reference.domains.execution_position.flows.open.open_dispatch_adapter import (
    OPEN_DISPATCH_CONTRACT,
    OPEN_DISPATCH_PATH,
    OpenDispatchAdapterError,
    OpenDispatchPayload,
)
from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message
from vfoundation.core.schema_registry import get_global_registry, init_global_registry

pytest_plugins = ("tests.domains.execution_position.conftest",)


def _build_execpos_with_real_bus():
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    cfg = get_config()
    bus = FSMCore()

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), \
            patch("apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"), \
            patch("apps.reference.domains.execution_position.fsm.MetricsCollector"), \
            patch("apps.reference.domains.execution_position.fsm.read_pending_brackets_from_wal", return_value={}):
        fsm = ExecPosFSM(config=cfg, fsm=bus, shadow_mode=True)

    fsm.log_adapter = MagicMock()
    portfolio_state = {
        "positions_last_ts_ms": 9_999_999_999_999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }
    fsm._latest_portfolio_state = dict(portfolio_state)
    fsm.exposure_guard.on_portfolio(dict(portfolio_state))
    return fsm, bus


def _cmd_open_message(rid: str = "RID-OPEN-DISPATCH") -> Message:
    return Message(
        op="CMD",
        verb="OPEN",
        src="execution_position",
        dst="execution_position",
        rid=rid,
        pld={
            "rid": rid,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.0104",
            "order_type": "LIMIT",
            "price": "10000.05",
            "price_ref": "10000.05",
            "tif": "GTC",
            "valid_for_ms": 60000,
            "stop_price": "9800",
            "target_price": "10200",
            "sl_pct": "0.02",
            "idempotent_key": f"KEY-{rid}",
            "regime": "TREND_UP",
            "regime_confidence": 0.87,
            "resolved_min_regime_confidence": 0.45,
            "threshold_applied": True,
            "threshold_verdict": "PASS",
            "threshold_reason": "regime_confidence=0.87 within band min=0.45",
            "regime_confidence_gate_verdict": "ALLOW",
            "regime_provenance": {
                "source_kind": "detector_cache",
                "detector_event": None,
                "cache_snapshot": {
                    "cache_write_ts_ms": 1700000000456,
                    "regime": "TREND_UP",
                    "confidence": 0.87,
                },
            },
        },
        why="open_dispatch_test",
    )


def _make_reduce_only_intent_message() -> Message:
    payload = {
        "rid": "RID-REDUCE-ONLY-PKG2",
        "instrument": "BTCUSDT",
        "side": "SELL",
        "strategy": "aurora",
        "order": {
            "qty": "0.01",
            "reduce_only": True,
            "order_type": "MARKET",
        },
        "idempotent_key": "KEY-REDUCE-ONLY-PKG2",
    }
    return Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        rid=str(payload["rid"]),
        pld=payload,
        why="pkg2_reduce_only",
    )


def _make_router() -> tuple[IntentRouter, MagicMock]:
    bus = MagicMock()
    fsm = MagicMock()
    fsm.bus = bus
    fsm.log_adapter = MagicMock()
    fsm.handle.return_value = SimpleNamespace(
        op="DEC",
        verb="OPEN",
        rid="RID-REDUCE-ONLY-PKG2",
        pld={"symbol": "BTCUSDT"},
        why="OPEN_OK",
        data_ref=[],
    )
    return IntentRouter(fsm), fsm


def _external_open_request_message(
    rid: str = "RID-EXT-OPEN-DISPATCH",
) -> Message:
    return Message(
        op="CMD",
        verb="EXTERNAL_OPEN_REQUEST_V1",
        src="shadow_telemetry",
        dst="execution_position",
        rid=rid,
        pld={
            "rid": rid,
            "intent_id": f"intent-{rid}",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.0104",
            "source": "external_llm",
            "order_type": "LIMIT",
            "price": "10000.05",
            "tif": "GTC",
            "valid_for_ms": 60_000,
            "stop_price": "9800",
            "target_price": "10200",
            "idempotent_key": f"KEY-{rid}",
            "snapshot_ref": {
                "snapshot_id": f"snap-{rid}",
                "inputs_digest": "digest-12345678",
            },
            "why_short": "pkg2 seam proof",
        },
        why="external_open_dispatch_test",
    )


def test_typed_open_dispatch_payload_builds_bounded_dec_open_surface() -> None:
    payload = OpenDispatchPayload.from_cmd_open(
        symbol="BTCUSDT",
        side="BUY",
        normalized_qty=Decimal("0.001"),
        order_type="LIMIT",
        normalized_price=Decimal("10000.01"),
        tif="GTC",
        valid_for_ms=60000,
        stop_price="9800",
        target_price="10200",
        sl_pct="0.02",
        idempotent_key="KEY-UNIT-1",
        regime="TREND_UP",
        regime_confidence=0.87,
        resolved_min_regime_confidence=0.45,
        threshold_applied=True,
        threshold_verdict="PASS",
        threshold_reason="regime_confidence=0.87 within band min=0.45",
        regime_confidence_gate_verdict="ALLOW",
        regime_epoch_ref=None,
        regime_provenance={"source_kind": "detector_cache",
                           "detector_event": None, "cache_snapshot": None},
    )

    assert payload.symbol == "BTCUSDT"
    assert payload.qty == "0.001"
    assert payload.price == "10000.01"
    dec_open_payload = payload.to_dec_open_payload()
    assert dec_open_payload["order_type"] == "LIMIT"
    assert dec_open_payload["resolved_min_regime_confidence"] == 0.45
    assert dec_open_payload["threshold_applied"] is True
    assert dec_open_payload["threshold_verdict"] == "PASS"
    assert dec_open_payload["threshold_reason"] == "regime_confidence=0.87 within band min=0.45"
    assert dec_open_payload["regime_confidence_gate_verdict"] == "ALLOW"


def test_typed_open_dispatch_rejects_inconsistent_limit_bridge_fail_closed() -> None:
    with pytest.raises(OpenDispatchAdapterError, match="LIMIT dispatch requires price"):
        OpenDispatchPayload.from_cmd_open(
            symbol="BTCUSDT",
            side="BUY",
            normalized_qty=Decimal("0.001"),
            order_type="LIMIT",
            normalized_price=None,
            tif="GTC",
            valid_for_ms=60000,
            stop_price=None,
            target_price=None,
            sl_pct=None,
            idempotent_key="KEY-UNIT-2",
            regime=None,
            regime_confidence=None,
            resolved_min_regime_confidence=None,
            threshold_applied=None,
            threshold_verdict=None,
            threshold_reason=None,
            regime_confidence_gate_verdict=None,
            regime_epoch_ref=None,
            regime_provenance=None,
        )


def test_live_cmd_open_hot_path_is_runtime_governed_by_typed_open_dispatch_adapter() -> None:
    init_global_registry(project_root=".")
    fsm, _bus = _build_execpos_with_real_bus()

    with patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        wraps=OpenDispatchPayload.from_cmd_open,
    ) as wrapped_dispatch, patch(
        "apps.reference.domains.execution_position.fsm.wal.append",
        return_value="wal-ok",
    ):
        result = fsm.handle(_cmd_open_message())

    assert wrapped_dispatch.call_count == 1
    assert result is not None
    assert result.op == "DEC" and result.verb == "OPEN"
    assert result.pld["resolved_min_regime_confidence"] == 0.45
    assert result.pld["threshold_applied"] is True
    assert result.pld["threshold_verdict"] == "PASS"
    assert result.pld["threshold_reason"] == "regime_confidence=0.87 within band min=0.45"
    assert result.pld["regime_confidence_gate_verdict"] == "ALLOW"
    assert any(
        isinstance(ref, str)
        and ref.startswith("obs://execution_position/open_dispatch?")
        and f"contract={OPEN_DISPATCH_CONTRACT}" in ref
        for ref in (result.data_ref or [])
    )


def test_open_dispatch_rejection_is_fail_closed_and_diagnostic() -> None:
    init_global_registry(project_root=".")
    fsm, _bus = _build_execpos_with_real_bus()

    with patch(
        "apps.reference.domains.execution_position.fsm.wal.append",
        return_value="wal-ok",
    ), patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        side_effect=OpenDispatchAdapterError("forced dispatch failure"),
    ):
        result = fsm.handle(_cmd_open_message(rid="RID-OPEN-DISPATCH-REJECT"))

    assert result is not None
    assert result.op == "ERR" and result.verb == "OPEN"
    assert result.why == "OPEN_DISPATCH_FAIL"
    assert "dispatch adapter rejected" in result.pld["reason"]
    assert any(
        isinstance(ref, str)
        and ref.startswith("obs://execution_position/open_dispatch?")
        and "status=reject" in ref
        for ref in (result.data_ref or [])
    )


def test_downstream_dec_open_schema_validation_still_runs_after_typed_dispatch() -> None:
    init_global_registry(project_root=".")
    fsm, _bus = _build_execpos_with_real_bus()

    with patch("apps.reference.domains.execution_position.fsm.wal.append", return_value="wal-ok"):
        result = fsm.handle(_cmd_open_message(rid="RID-OPEN-DISPATCH-SCHEMA"))

    registry = get_global_registry()
    assert registry is not None
    validator = registry.get_validator("DEC", "OPEN")
    assert validator is not None
    validator.validate(result.pld)


def test_external_open_request_routes_through_runtime_typed_open_dispatch_adapter() -> None:
    init_global_registry(project_root=".")
    fsm, bus = _build_execpos_with_real_bus()
    observed_decisions: list[Message] = []
    bus.listen("DEC:OPEN", lambda msg: observed_decisions.append(msg))
    open_flow = fsm._get_or_create_open_flow("BTCUSDT")

    with patch.object(fsm, "handle", wraps=fsm.handle) as wrapped_fsm_handle, patch.object(
        open_flow,
        "handle",
        wraps=open_flow.handle,
    ) as wrapped_open_flow_handle, patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        wraps=OpenDispatchPayload.from_cmd_open,
    ) as wrapped_dispatch, patch(
        "apps.reference.domains.execution_position.fsm.wal.append",
        return_value="wal-ok",
    ):
        fsm._intent_router.on_external_open_request(
            _external_open_request_message(),
        )

    wrapped_fsm_handle.assert_called_once()
    wrapped_open_flow_handle.assert_called_once()
    assert wrapped_dispatch.call_count == 1
    assert observed_decisions
    assert observed_decisions[0].verb == "OPEN"
    assert any(
        isinstance(ref, str)
        and ref.startswith("obs://execution_position/open_dispatch?")
        and f"contract={OPEN_DISPATCH_CONTRACT}" in ref
        for ref in (observed_decisions[0].data_ref or [])
    )


def test_handle_async_routes_through_same_typed_open_dispatch_adapter(fsm_config) -> None:
    fsm = OpenFlowFSM(cooldown_sec=0.0, guard_enabled=True, config=fsm_config)

    with patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        wraps=OpenDispatchPayload.from_cmd_open,
    ) as wrapped_dispatch:
        result = asyncio.run(
            fsm.handle_async(_cmd_open_message(rid="RID-OPEN-DISPATCH-ASYNC")),
        )

    assert wrapped_dispatch.call_count == 1
    assert result is not None
    assert result.op == "DEC" and result.verb == "OPEN"
    assert any(
        isinstance(ref, str)
        and ref.startswith("obs://execution_position/open_dispatch?")
        and f"contract={OPEN_DISPATCH_CONTRACT}" in ref
        for ref in (result.data_ref or [])
    )


def test_real_router_emit_path_auto_enforces_dec_open_schema() -> None:
    init_global_registry(project_root=".")
    fsm, bus = _build_execpos_with_real_bus()
    observed_decisions: list[Message] = []
    observed_rejects: list[Message] = []
    bus.listen("DEC:OPEN", lambda msg: observed_decisions.append(msg))
    bus.listen(
        "EVT:EXTERNAL_OPEN_REQUEST_REJECTED_V1",
        lambda msg: observed_rejects.append(msg),
    )
    original_to_dec_open_payload = OpenDispatchPayload.to_dec_open_payload

    def _invalid_payload(self: OpenDispatchPayload) -> dict:
        payload = original_to_dec_open_payload(self)
        payload["rid"] = "RID-DRIFT"
        return payload

    with patch(
        "apps.reference.domains.execution_position.fsm.wal.append",
        return_value="wal-ok",
    ), patch.object(
        OpenDispatchPayload,
        "to_dec_open_payload",
        autospec=True,
        side_effect=_invalid_payload,
    ):
        fsm._intent_router.on_external_open_request(
            _external_open_request_message(rid="RID-EXT-OPEN-DISPATCH-SCHEMA"),
        )

    assert observed_decisions == []
    assert observed_rejects, "Expected external rejection after DEC:OPEN schema validation failure"
    assert observed_rejects[0].pld["reason_code"] == "NRR-EXECUTION-EXCEPTION"
    assert "rid" in str(observed_rejects[0].pld["reason_text"])


def test_package1_intake_markers_remain_unaffected_before_dispatch_adapter_runs(fsm_harness) -> None:
    from apps.reference.domains.execution_position.flows.open.fsm_open import CmdOpenPayload
    from tests.domains.execution_position.test_trade_intent_open_intake import _make_intent_message

    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = {
        "equity_free_usdt": "10000",
        "positions": [],
        "positions_last_ts_ms": 9_999_999_999_999,
    }
    fsm.exposure_guard.on_portfolio(fsm._latest_portfolio_state)

    original_validate = CmdOpenPayload.model_validate
    validated_payloads: list[dict] = []

    def _wrapped_validate(payload):
        validated_payloads.append(dict(payload))
        return original_validate(payload)

    with patch.object(CmdOpenPayload, "model_validate", side_effect=_wrapped_validate), patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        wraps=OpenDispatchPayload.from_cmd_open,
    ) as wrapped_dispatch:
        fsm._on_trade_intent_proposed(_make_intent_message())

    assert validated_payloads
    assert validated_payloads[0]["metadata"]["execution_intake_contract"] == "trade_intent_open_intake_v1"
    assert validated_payloads[0]["metadata"]["execution_intake_path"] == "EVT:TRADE_INTENT_PROPOSED->CMD:OPEN"
    assert wrapped_dispatch.call_count == 1


def test_reduce_only_close_path_does_not_use_open_dispatch_adapter() -> None:
    router, fsm = _make_router()

    with patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        wraps=OpenDispatchPayload.from_cmd_open,
    ) as wrapped_dispatch:
        router.on_trade_intent_proposed(_make_reduce_only_intent_message())

    wrapped_dispatch.assert_not_called()
    fsm.handle.assert_called_once()
    cmd_close = fsm.handle.call_args.args[0]
    assert cmd_close.op == "CMD"
    assert cmd_close.verb == "CLOSE"


def test_fill_ingress_path_does_not_use_open_dispatch_adapter(fsm_harness) -> None:
    fsm, _bus, _cfg = fsm_harness

    fill_msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="adapter",
        dst="execution_position",
        rid="RID-FILL-PKG2",
        pld={"symbol": "BTCUSDT"},
        why="fill_path_pkg2",
    )

    with patch.object(
        fsm._fill_ingress_coordinator,
        "handle_canonical_fill_ingress",
        return_value=None,
    ) as wrapped_fill, patch(
        "apps.reference.domains.execution_position.flows.open.fsm_open.OpenDispatchPayload.from_cmd_open",
        wraps=OpenDispatchPayload.from_cmd_open,
    ) as wrapped_dispatch:
        fsm.handle(fill_msg)

    wrapped_fill.assert_called_once()
    wrapped_dispatch.assert_not_called()
