from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.reference.config.testnet_proof import ProofExposure
from apps.reference.bootstrap.async_runtime import AsyncLoopRuntime
from apps.reference.domains.decision_making.primitives.position_queries import (
    PositionQueries,
)
from apps.reference.domains.execution_position.guards.exposure_manager import (
    ExposureManager,
)
from apps.reference.domains.execution_position.guards.soft_clip import (
    SoftClipEngine,
    SoftLimitConfig,
    load_soft_limit_config,
)
from apps.reference.domains.shadow_telemetry.agent_trade_intent_v2 import (
    AgentTradeIntentV2,
)
from apps.reference.shared.decision_primitives.sizing_margin_first import (
    compute_notional_target,
    compute_qty,
)
from tests.domains.shadow_telemetry.test_agent_trade_intent_v2 import (
    NOW,
    _intent_payload,
    _processor,
    _snapshot,
)
from tests.domains.shadow_telemetry.p46_1f_runtime_harness import P46RuntimeHarness
from tests.domains.execution_position.test_p46_1g_s1_async_dispatch import (
    RecordingVenueAdapter,
)
from vfoundation.core.fsm_emit_compat import Message


EQUITY = Decimal("3093.52554595")
PRIOR_PRICE = Decimal("0.0722")
FEE_BUFFER = Decimal("0.001")
CLIP_MIN = Decimal("10")


def _queries(
    *,
    margin_pct: Decimal,
    fee_buffer: Decimal | None = FEE_BUFFER,
    step_size: Decimal | None = Decimal("1"),
    min_notional: Decimal | None = Decimal("5"),
) -> PositionQueries:
    sizing_values = {"margin_pct": margin_pct}
    if fee_buffer is not None:
        sizing_values["fee_buffer_fraction"] = fee_buffer
    instrument = SimpleNamespace(
        sizing=SimpleNamespace(**sizing_values),
        execution=SimpleNamespace(target_leverage=10),
        step_size=step_size,
        min_qty=Decimal("1"),
        min_notional=min_notional,
    )
    return PositionQueries(
        config=SimpleNamespace(instruments={"DOGEUSDT": instrument}),
        get_portfolio=lambda: None,
        min_pos_size_usd=Decimal("5"),
        liq_cap_usd=Decimal("20"),
        logger=logging.getLogger("test.p46_1g_s2"),
    )


def _clip(requested: Decimal, **updates):
    values = {
        "clip_min_notional_usdt": CLIP_MIN,
        "directional_ratio_max": Decimal("20"),
        "side_exposure_usdt": Decimal("2000"),
        "margin_exposure_usdt": Decimal("5000"),
    }
    values.update(updates)
    engine = SoftClipEngine(SoftLimitConfig(**values))
    return engine.calculate_clipped_size(
        notional_usd=requested,
        symbol="DOGEUSDT",
        order_side="BUY",
        long_margin=Decimal("0"),
        short_margin=Decimal("0"),
        total_margin_exposure=Decimal("0"),
        symbol_leverage=Decimal("10"),
    )


def test_exact_prior_soft_limit_below_clip_min_reproducer() -> None:
    prior_margin_pct = Decimal("10") / (EQUITY * Decimal("10"))
    margin, target = compute_notional_target(
        equity=EQUITY,
        margin_pct=prior_margin_pct,
        leverage=10,
        notional_cap=Decimal("20"),
        fee_buffer=FEE_BUFFER,
    )
    raw_qty, rounded_qty = compute_qty(
        notional_target=target,
        price=PRIOR_PRICE,
        step_size=Decimal("1"),
    )
    rounded_notional = rounded_qty * PRIOR_PRICE
    result = _clip(rounded_notional)

    assert margin.quantize(Decimal("0.000000000001")) == Decimal("0.999000000000")
    assert target.quantize(Decimal("0.000000000001")) == Decimal("9.990000000000")
    assert raw_qty > Decimal("138")
    assert rounded_qty == Decimal("138")
    assert rounded_notional == Decimal("9.9636")
    assert result.allowed is False
    assert result.reason == "BELOW_CLIP_MIN"


@pytest.mark.parametrize(
    ("requested", "allowed"),
    [
        (Decimal("9.9999"), False),
        (Decimal("10"), True),
        (Decimal("10.0001"), True),
    ],
)
def test_clip_min_boundaries(requested: Decimal, allowed: bool) -> None:
    assert _clip(requested).allowed is allowed


def test_operator_cap_boundary_is_strict() -> None:
    assert ProofExposure(
        target_notional_quote=Decimal("20"),
        operator_max_notional_quote=Decimal("20"),
    ).target_notional_quote == Decimal("20")
    with pytest.raises(ValidationError):
        ProofExposure(
            target_notional_quote=Decimal("20.0001"),
            operator_max_notional_quote=Decimal("20"),
        )


def test_price_motion_changes_step_rounded_quantity() -> None:
    first = compute_qty(
        notional_target=Decimal("11"),
        price=Decimal("0.0722"),
        step_size=Decimal("1"),
    )
    second = compute_qty(
        notional_target=Decimal("11"),
        price=Decimal("0.0735"),
        step_size=Decimal("1"),
    )
    assert first[1] == Decimal("152")
    assert second[1] == Decimal("149")


def test_fee_buffer_is_applied_once_from_explicit_instrument_config() -> None:
    target = Decimal("11")
    margin_pct = target / (
        EQUITY * (Decimal("1") - FEE_BUFFER) * Decimal("10")
    )
    qty, why, reason, debug = _queries(margin_pct=margin_pct).calculate_position_size(
        "DOGEUSDT",
        PRIOR_PRICE,
        "BUY",
        {"portfolio": {"equity": str(EQUITY)}},
    )
    assert reason is None
    assert why == "margin_first_ok"
    assert qty == Decimal("152")
    assert Decimal(debug["notional_target"]) == target
    assert debug["fee_buffer_fraction"] == "0.001"


def test_existing_exposure_is_applied_once_to_remaining_margin() -> None:
    engine = SoftClipEngine(SoftLimitConfig(
        clip_min_notional_usdt=Decimal("10"),
        directional_ratio_max=Decimal("20"),
        side_exposure_usdt=Decimal("2000"),
        margin_exposure_usdt=Decimal("5000"),
    ))
    result = engine.calculate_clipped_size(
        notional_usd=Decimal("11"),
        symbol="DOGEUSDT",
        order_side="BUY",
        long_margin=Decimal("0"),
        short_margin=Decimal("0"),
        total_margin_exposure=Decimal("4999"),
        symbol_leverage=Decimal("10"),
    )
    assert result.allowed is True
    assert result.clipped_notional == Decimal("10")
    assert "MARGIN_AVAILABLE:10.00" in result.clip_reasons


def test_missing_risk_config_and_instrument_filters_fail_closed() -> None:
    with pytest.raises(ValueError, match="soft_limits"):
        load_soft_limit_config({})

    qty, _why, reason, debug = _queries(
        margin_pct=Decimal("0.1"), step_size=None
    ).calculate_position_size(
        "DOGEUSDT",
        PRIOR_PRICE,
        "BUY",
        {"portfolio": {"equity": str(EQUITY)}},
    )
    assert qty is None
    assert reason == "CONFIG_REGIME_SIZING_INVALID"
    assert debug["step_size"] == "None"


def test_missing_fee_buffer_config_fails_closed() -> None:
    qty, why, reason, _debug = _queries(
        margin_pct=Decimal("0.1"), fee_buffer=None
    ).calculate_position_size(
        "DOGEUSDT",
        PRIOR_PRICE,
        "BUY",
        {"portfolio": {"equity": str(EQUITY)}},
    )
    assert qty is None
    assert reason == "CONFIG_REGIME_SIZING_INVALID"
    assert why == "missing_or_invalid_fee_buffer_fraction"


def test_quantity_is_converted_to_quote_notional_before_guard() -> None:
    captured: list[Decimal] = []

    class Guard:
        def can_open(self, _symbol, notional, _portfolio, **_kwargs):
            captured.append(notional)
            return {"allowed": False, "reason": "SOFT_LIMIT_BELOW_CLIP_MIN"}

    fake_fsm = SimpleNamespace(
        _latest_portfolio_state={"positions": []},
        exposure_guard=Guard(),
        metrics_collector=None,
    )
    result = ExposureManager(fake_fsm).check_exposure_fail_closed(Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="intent-s2-unit",
        pld={
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "qty": "138",
            "price_ref": "0.0722",
            "idempotent_key": "intent-s2-unit",
            "config_version": "p46-1e-v1",
        },
        why="unit_coherence",
    ))
    assert result is not None
    assert captured == [Decimal("9.9636")]
    assert result.pld["exposure_decision_id"] == "exposure:intent-s2-unit"


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"account_snapshot_at": NOW - timedelta(seconds=16)}, "ACCOUNT_SNAPSHOT_STALE"),
        ({"market_snapshot_at": NOW - timedelta(seconds=16)}, "MARKET_SNAPSHOT_STALE"),
        ({"account_snapshot_at": None}, "ACCOUNT_SNAPSHOT_TIMESTAMP_MISSING"),
        ({"market_snapshot_at": None}, "MARKET_SNAPSHOT_TIMESTAMP_MISSING"),
    ],
)
def test_stale_or_missing_snapshot_time_rejects_sizing(updates, reason) -> None:
    result = _processor(_snapshot(**updates)).process(
        AgentTradeIntentV2.model_validate(_intent_payload())
    )
    assert result.downstream_command is None
    assert reason in result.sizing.rejection_reasons


def test_same_inputs_are_deterministic_and_caller_quantity_is_rejected() -> None:
    intent = AgentTradeIntentV2.model_validate(_intent_payload())
    processor = _processor()
    assert processor.process(intent) == processor.process(intent)
    with pytest.raises(ValidationError):
        AgentTradeIntentV2.model_validate(_intent_payload(qty="152"))


def test_exposure_rejection_emits_no_execution_decision_or_adapter_call(
    tmp_path, monkeypatch
) -> None:
    harness = P46RuntimeHarness(tmp_path, monkeypatch)
    adapter = RecordingVenueAdapter()
    runtime = AsyncLoopRuntime(name="P46S2ExposureRejectLoop")
    loop = runtime.start()
    harness.adapter = adapter
    harness.execution_fsm.adapter = adapter
    harness.execution_fsm.shadow_mode = False
    harness.execution_fsm.set_async_loop(loop)
    harness.execution_fsm.exposure_guard.soft_limit_config.clip_min_notional_usdt = (
        Decimal("1000")
    )

    harness.start()
    try:
        assert harness.post(harness.payload()).status_code == 202
        harness.wait_for(lambda: len(harness.fsm_ingress) == 1)
        harness.wait_for(lambda: len(harness.fsm_results) == 1)
        assert harness.fsm_results[0].op == "ERR"
        assert harness.fsm_results[0].verb == "OPEN"
        assert adapter.submit_calls == []
        decisions = [
            name for name, _payload, _why in harness.bus.emissions
            if name == "DEC:OPEN"
        ]
        assert decisions == []
    finally:
        harness.stop()
        runtime.stop()
