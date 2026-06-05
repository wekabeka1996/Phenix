import decimal
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.decision_making.authority_bridge import NeocortexAuthorityBridge
from apps.reference.domains.decision_making.intent.builder import IntentBuilder
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    get_failure_outcome_total,
    reset_failure_outcomes,
)


class _FakeSG:
    intent_side = "LONG"
    trace_ts_ms = 1_700_000_000_000
    why_short = ""
    signal_score = 0.5
    regime = "TREND_UP"
    regime_confidence = 0.9
    trend_dir = 1
    trend_run_length = 1
    delta_price = 0
    pm_norm_10s = 0
    pm_norm_60s = 0
    pm_norm_300s = 0
    vol_pct_10s = 0
    vol_pct_60s = 0
    vol_pct_300s = 0


def _safe_decimal(value, default=None):
    if value in (None, "", "None"):
        return default
    return decimal.Decimal(str(value))


def _make_config():
    kelly_cfg = SimpleNamespace(
        base_probability="0.5",
        kelly_cap="0.25",
        kelly_alpha="0.8",
        payoff_ratio_r="1.5",
        p_min="0.45",
        p_max="0.65",
        uplift_factor="0.2",
    )
    strategy_cfg = SimpleNamespace(
        execution=SimpleNamespace(entry_order_type="LIMIT", entry_tif="GTC"),
        decision=SimpleNamespace(kelly=kelly_cfg),
    )
    return SimpleNamespace(strategies=SimpleNamespace(aurora=strategy_cfg))


def _make_builder(*, authority_bridge: NeocortexAuthorityBridge, shadow_emit_fn=None) -> IntentBuilder:
    clock = MagicMock()
    clock.now_ms.return_value = 1_700_000_000_000
    clock.now_sec.return_value = 1_700_000_000
    fsm = SimpleNamespace(order_index=None, emit=MagicMock())
    return IntentBuilder(
        logger=MagicMock(),
        fsm=fsm,
        clock=clock,
        config=_make_config(),
        tca_prefs={
            "max_slippage_bps": 25,
            "max_latency_ms": 3000,
            "maker_preference": "neutral",
        },
        risk_budgets={
            "trade_cvar95_max_bps": 100,
            "session_cvar95_max_bps": 200,
        },
        safe_decimal_fn=_safe_decimal,
        check_strategy_arbitration_fn=MagicMock(
            side_effect=lambda *_, commit=False, **__: {
                "allowed": True, "reason": None}
        ),
        warmup_gate_fn=lambda **_kwargs: False,
        emit_rejected_fn=MagicMock(),
        record_blocked_fn=MagicMock(),
        record_accepted_fn=MagicMock(),
        emit_deferred_fn=MagicMock(),
        get_side_bias_params_fn=MagicMock(return_value=(0, 600, 0.6, 0.9)),
        side_intent_window={},
        get_regime_epoch_ref_fn=lambda symbol: f"epoch:{symbol}:123",
        authority_bridge=authority_bridge,
        authority_deadline_budget_ms=20,
        shadow_emit_fn=shadow_emit_fn,
    )


def _build_kwargs(*, symbol: str, rid: str) -> dict:
    return {
        "symbol": symbol,
        "side": "BUY",
        "qty": decimal.Decimal("1.5"),
        "price": decimal.Decimal("50000.25"),
        "why_chain": ["authority_test"],
        "rid": rid,
        "reduce_only": False,
        "strategy_id": "aurora",
        "decision_ts_ms": 1_700_000_000_999,
        "stop_price": "49000.50",
        "target_price": decimal.Decimal("51000.75"),
        "entry_plan_trace": {"plan": "maker_pullback"},
        "tf_sec": 300,
        "max_slippage_bps": None,
        "max_latency_ms": None,
        "risk_score": 0.33,
        "tpsl_owner_ctx": None,
        "strategy_trace": {"objective": {"score": 0.9}},
        "normalize_mode": "signed_v2",
        "sg": _FakeSG(),
    }


def _make_request(symbol: str) -> ControlDecisionRequest:
    return ControlDecisionRequest(
        decision_id=str(uuid.uuid4()),
        rid="rid-authority-1",
        symbol=symbol,
        proposed_action="OPEN_LONG",
        deadline_ms=1_700_000_000_050,
        decision_basis_ts=1_700_000_000_000,
    )


@pytest.fixture(autouse=True)
def _reset_failure_outcomes_fixture():
    reset_failure_outcomes()
    yield
    reset_failure_outcomes()


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_fast_ai_allow_passes_intent(
    mock_wal,
    mock_policy,
    *_patches,
):
    async def _allow(req: ControlDecisionRequest) -> ControlDecisionResponse:
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=ControlDecisionAction.ALLOW,
            apply_result="FAST_ALLOW",
            fallback_reason=None,
            ttl_ms=5,
        )

    bridge = NeocortexAuthorityBridge(authority_fn=_allow)
    # keep bridge instance alive for coverage parity
    response = bridge._remaining_ttl_ms
    assert response is not None

    direct = __import__("asyncio").run(
        bridge.request_authority(_make_request("BTCUSDT"), timeout_ms=5))
    assert direct.action == ControlDecisionAction.ALLOW

    shadow_events: list[tuple[str, dict, str]] = []
    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    builder = _make_builder(
        authority_bridge=bridge,
        shadow_emit_fn=lambda event_name, payload, why: shadow_events.append(
            (event_name, payload, why)
        ),
    )
    builder.build_and_emit(
        **_build_kwargs(symbol="BTCUSDT", rid="RID-FAST-AI"))

    emitted = [
        call for call in builder._fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:TRADE_INTENT_PROPOSED"
    ]
    assert len(emitted) == 1
    trade_intent = emitted[0].kwargs["payload"]
    assert trade_intent["authority_context"]["decision_id"]
    assert trade_intent["authority_context"]["apply_result"] == "FAST_ALLOW"
    assert trade_intent["authority_context"]["authority_mode"] == "shadow"
    assert shadow_events
    event_name, payload, _why = shadow_events[0]
    assert event_name == "SHADOW:NEOCORTEX_DECISION_LOGGED"
    assert payload["request_ts_ms"] == 1_700_000_000_000
    assert payload["response_ts_ms"] == payload["decision_ts_ms"]
    assert payload["apply_result"] == "FAST_ALLOW"
    assert payload["authority_mode"] == "shadow"


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_slow_ai_timeout_falls_back_and_intent_still_passes(
    mock_wal,
    mock_policy,
    *_patches,
):
    async def _slow_allow(req: ControlDecisionRequest) -> ControlDecisionResponse:
        await __import__("asyncio").sleep(0.1)
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=ControlDecisionAction.ALLOW,
            apply_result="SLOW_ALLOW",
            fallback_reason=None,
            ttl_ms=5,
        )

    bridge = NeocortexAuthorityBridge(authority_fn=_slow_allow)
    direct = __import__("asyncio").run(
        bridge.request_authority(_make_request("1000PEPEUSDT"), timeout_ms=10)
    )
    assert direct.action == ControlDecisionAction.FALLBACK
    assert direct.fallback_reason == "BRIDGE_TIMEOUT"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code="BRIDGE_TIMEOUT",
    ) == 1

    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    builder = _make_builder(authority_bridge=bridge)
    builder.build_and_emit(
        **_build_kwargs(symbol="1000PEPEUSDT", rid="RID-SLOW-AI"))

    emitted = [
        call for call in builder._fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:TRADE_INTENT_PROPOSED"
    ]
    assert len(emitted) == 1
    trade_intent = emitted[0].kwargs["payload"]
    assert trade_intent["authority_context"]["fallback_reason"] == "BRIDGE_TIMEOUT"
    assert trade_intent["authority_context"]["apply_result"] == "FALLBACK_BASELINE"


@patch("apps.reference.domains.decision_making.intent.builder.order_logger.write")
@patch("apps.reference.domains.decision_making.intent.builder.print")
@patch("apps.reference.domains.decision_making.intent.builder.emit_regime_decision_audit")
@patch("apps.reference.domains.decision_making.intent.builder._trade_lifecycle", None)
@patch("apps.reference.domains.decision_making.intent.builder.IntentBuilder._resolve_order_policy")
@patch("apps.reference.domains.decision_making.intent.builder.wal.append")
def test_ai_veto_blocks_intent_emission(
    mock_wal,
    mock_policy,
    *_patches,
):
    async def _block(req: ControlDecisionRequest) -> ControlDecisionResponse:
        return ControlDecisionResponse(
            decision_id=req.decision_id,
            action=ControlDecisionAction.BLOCK,
            apply_result="MODEL_VETO",
            fallback_reason=None,
            ttl_ms=20,
        )

    bridge = NeocortexAuthorityBridge(authority_fn=_block)
    direct = __import__("asyncio").run(
        bridge.request_authority(_make_request("BTCUSDT"), timeout_ms=5))
    assert direct.action == ControlDecisionAction.BLOCK

    mock_policy.return_value = ("LIMIT", "GTC", 10_000)
    mock_wal.return_value = "wal-ok"
    builder = _make_builder(authority_bridge=bridge)
    builder.build_and_emit(
        **_build_kwargs(symbol="BTCUSDT", rid="RID-VETO-AI"))

    intent_emits = [
        call for call in builder._fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:TRADE_INTENT_PROPOSED"
    ]
    blocked_emits = [
        call for call in builder._fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:DECISION_BLOCKED"
    ]

    assert intent_emits == []
    assert len(blocked_emits) == 1
    assert mock_wal.call_count == 1
    assert mock_wal.call_args.args[0]["verb"] == "DECISION_BLOCKED"


def test_authority_handler_failure_falls_back_and_records_outcome() -> None:
    async def _boom(_req: ControlDecisionRequest) -> ControlDecisionResponse:
        raise RuntimeError("bridge unavailable")

    bridge = NeocortexAuthorityBridge(authority_fn=_boom)
    response = __import__("asyncio").run(
        bridge.request_authority(_make_request("BTCUSDT"), timeout_ms=5)
    )

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "HANDLER_FAILURE"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code="HANDLER_FAILURE",
    ) == 1


def test_missing_baseline_controller_falls_back_and_records_outcome(tmp_path) -> None:
    bridge = NeocortexAuthorityBridge(model_path=tmp_path / "missing.pkl")

    response = __import__("asyncio").run(
        bridge.request_authority(_make_request("ETHUSDT"), timeout_ms=5)
    )

    assert response.action == ControlDecisionAction.FALLBACK
    assert response.fallback_reason == "BASELINE_UNAVAILABLE"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code="BASELINE_UNAVAILABLE",
    ) == 1
