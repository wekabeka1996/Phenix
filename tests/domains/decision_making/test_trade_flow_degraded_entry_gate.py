from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from apps.reference.config.domains.decision_making import TradeFlowGateConfig
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
)
from apps.reference.domains.decision_making.gates import trade_flow_gate
from apps.reference.domains.decision_making.gateway.protocol import (
    GateContext,
    GateOutcome,
)


def _build_context(
    *,
    enabled=True,
    strategy_id="aurora",
    sensitive_strategies=None,
    block_states=None,
    missing_state_behavior="observe_only",
    unknown_state_behavior="observe_only",
    intent_kind="ENTRY",
    reduce_only=False,
    is_reduce_path=False,
    trade_flow_state=None,
):
    if sensitive_strategies is None:
        sensitive_strategies = ["aurora"]
    if block_states is None:
        block_states = ["degraded", "stale"]

    # Setup config
    gate_cfg = MagicMock()
    gate_cfg.enabled = enabled
    gate_cfg.sensitive_strategies = sensitive_strategies
    gate_cfg.block_states = block_states
    gate_cfg.missing_state_behavior = missing_state_behavior
    gate_cfg.unknown_state_behavior = unknown_state_behavior
    gate_cfg.apply_to = ["ENTRY"]
    gate_cfg.preserve = ["FULL_CLOSE", "PARTIAL_CLOSE"]

    dm_cfg = MagicMock()
    dm_cfg.trade_flow_gate = gate_cfg

    config = MagicMock()
    config.domains.decision_making = dm_cfg

    # Setup dm symbol states
    symbol_state = {}
    if trade_flow_state is not None:
        symbol_state["features"] = {"trade_flow_state": trade_flow_state}

    dm = MagicMock()
    dm.symbol_states = {"BTCUSDT": symbol_state}

    # Setup GateContext
    ctx = MagicMock(spec=GateContext)
    ctx.symbol = "BTCUSDT"
    ctx.strategy_id = strategy_id
    ctx.is_reduce_path = is_reduce_path
    ctx.pld = {"intent_kind": intent_kind, "reduce_only": reduce_only}
    ctx.config = config
    ctx.dm = dm

    return ctx


def test_t6c3_degraded_blocks_new_entry_sensitive_strategy():
    ctx = _build_context(trade_flow_state="degraded")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.BLOCK
    assert res.reason_code == NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK


def test_t6c3_stale_blocks_new_entry_sensitive_strategy():
    ctx = _build_context(trade_flow_state="stale")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.BLOCK
    assert res.reason_code == NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK


def test_t6c3_fresh_does_not_block():
    ctx = _build_context(trade_flow_state="fresh")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_unknown_is_observe_only_by_default():
    ctx = _build_context(trade_flow_state="unknown", unknown_state_behavior="observe_only")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_unknown_can_fail_closed_if_configured():
    ctx = _build_context(trade_flow_state="unknown", unknown_state_behavior="fail_closed")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.BLOCK


def test_t6c3_missing_metadata_is_observe_only_by_default():
    ctx = _build_context(trade_flow_state=None, missing_state_behavior="observe_only")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_missing_metadata_can_fail_closed_if_configured():
    ctx = _build_context(trade_flow_state=None, missing_state_behavior="fail_closed")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.BLOCK


def test_t6c3_non_sensitive_strategy_not_blocked():
    ctx = _build_context(strategy_id="mean_reversion", trade_flow_state="degraded")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_close_is_not_blocked():
    ctx = _build_context(intent_kind="FULL_CLOSE", trade_flow_state="degraded")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_reduce_only_is_not_blocked():
    ctx = _build_context(reduce_only=True, trade_flow_state="degraded")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_is_reduce_path_is_not_blocked():
    ctx = _build_context(is_reduce_path=True, trade_flow_state="degraded")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_gate_disabled_does_not_block():
    ctx = _build_context(enabled=False, trade_flow_state="degraded")
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.PASS


def test_t6c3_config_validation():
    # Valid config
    cfg = TradeFlowGateConfig(
        enabled=True,
        sensitive_strategies=["aurora"],
        block_states=["degraded", "stale"],
        missing_state_behavior="observe_only",
        unknown_state_behavior="observe_only",
        apply_to=["ENTRY"],
        preserve=["FULL_CLOSE", "PARTIAL_CLOSE"],
    )
    assert cfg.enabled is True

    # Invalid missing behavior raises ValidationError
    with pytest.raises(ValidationError):
        TradeFlowGateConfig(
            enabled=True,
            sensitive_strategies=["aurora"],
            block_states=["degraded"],
            missing_state_behavior="invalid_behavior",
            unknown_state_behavior="observe_only",
            apply_to=["ENTRY"],
            preserve=["FULL_CLOSE"],
        )


def test_t6c3_reason_registered():
    assert hasattr(NormalizedRejectReasons, "TRADE_FLOW_DEGRADED_ENTRY_BLOCK")
    assert NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK == "NRR-064"


def test_t6c3_missing_intent_kind_defaults_to_entry():
    ctx = _build_context(trade_flow_state="degraded")
    if "intent_kind" in ctx.pld:
        del ctx.pld["intent_kind"]
    res = trade_flow_gate.check(ctx)
    assert res.outcome == GateOutcome.BLOCK
    assert res.reason_code == NormalizedRejectReasons.TRADE_FLOW_DEGRADED_ENTRY_BLOCK


def test_t6c3_gate_chain_integration():
    from apps.reference.domains.decision_making.gateway.chain import GateChain

    ctx = _build_context(trade_flow_state="degraded")
    chain = GateChain([trade_flow_gate.check])

    res = chain.run(ctx)
    assert not res.passed
    assert res.final_outcome == GateOutcome.BLOCK
    assert len(res.trace) == 1
    assert res.trace[0].gate_name == "trade_flow"
    assert res.trace[0].outcome == GateOutcome.BLOCK

