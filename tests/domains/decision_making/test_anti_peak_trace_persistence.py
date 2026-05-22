"""
Anti-peak trace persistence tests.

Repair package: ANTI_PEAK_TRACE_PERSISTENCE_REPAIR

Proves that anti_peak_observability is:
- built correctly by _build_anti_peak_observability
- present in EVT:STRATEGY_SIGNAL_PRODUCED payload at scoring.anti_peak_observability
- present in EVT:STRATEGY_DECISION_BLOCKED payload at details.anti_peak_observability
- present in EVT:QUADRATIC_DECISION_TRACE payload at top-level anti_peak_observability
- present in EVT:DECISION_TRACE_EMITTED payload via trace_context passthrough
- present in EVT:TRADE_INTENT_REJECTED payload at details.anti_peak_observability
- preserved in shadow journal payload_fragment after build_payload_fragment
- disabled config truth (gate_disabled / non-authoritative) survives persistence
"""
from __future__ import annotations

import decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.shared.decision_primitives.scoring_kernel import ScoringResult
from apps.reference.telemetry.shadow_journal import build_payload_fragment


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _build_handler(*, emit_fn, scoring_result: ScoringResult) -> AuroraHandler:
    scoring_kernel_cls = type(
        "StubAuroraKernel",
        (),
        {"compute": staticmethod(lambda **_kwargs: scoring_result)},
    )
    with (
        patch.object(AuroraHandler, "_load_config", lambda self: None),
        patch(
            "apps.reference.domains.strategies.runtimes.aurora.decision.evaluate_quadratic_shadow",
            return_value=SimpleNamespace(state="NOT_REQUESTED"),
        ),
    ):
        handler = AuroraHandler(
            config=SimpleNamespace(
                strategies=SimpleNamespace(
                    aurora=SimpleNamespace(
                        decision=SimpleNamespace(scoring_version="quadratic"),
                    )
                ),
                regime_shift_inception=None,
                instruments=None,
            ),
            emit_fn=emit_fn,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._basis_required_bars_override = 0
    handler._is_symbol_enabled = lambda symbol: True
    handler._check_regime_liveness = lambda symbol, state: None
    handler._get_instrument_config = lambda symbol: SimpleNamespace(
        allowed_regimes=["LOW_VOLATILITY"],
        tick_size=None,
        volatility_entry_logic=None,
    )
    handler._get_signal_weights = lambda symbol, instr_cfg: {}
    handler._get_feature_neutrals = lambda symbol, instr_cfg: {}
    handler._get_essential_features = lambda symbol, instr_cfg: []
    handler._check_liquidity_gate = lambda **_kwargs: (True, {})
    handler._get_side_bias_state = lambda symbol: None
    handler._get_regime_thresholds = lambda symbol, instr_cfg: {
        "LOW_VOLATILITY": 1.0,
        "DEFAULT": 1.0,
    }
    handler._apply_vol_adj_gates = lambda *args, **kwargs: False
    handler._should_suppress_soft_exit = lambda *args, **kwargs: False
    handler._get_reentry_cooldown_sec = lambda symbol: 0.0
    handler.scoring_kernel_cls = scoring_kernel_cls
    handler.signal_threshold = decimal.Decimal("0.1")
    handler.neutral_threshold = decimal.Decimal("0.05")
    handler.direction_strength_cfg = {}
    handler.delta_price_cap_pct = decimal.Decimal("0.01")
    handler.normalize_signals_mode = "signed_v2"
    handler.score_multiplier = 1.25
    handler._quadratic_shadow_shield_fn = None
    handler._regime_smoother = None
    handler.objective_engine = None
    handler.exit_manager = SimpleNamespace(
        check_exit=lambda **_kwargs: (False, None, None)
    )
    state = handler._symbol_states["BTCUSDT"]
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42
    return handler


def _neutral_result() -> ScoringResult:
    return ScoringResult(
        score=decimal.Decimal("0"),
        side="",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "s_linear": 0.2,
            "admission_pre_shield": 0.25,
            "shield_reasons": [],
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "shield_multiplier": 1.0,
            "admission_shield_multiplier": 1.0,
            "side_why": "neutral:score=0.0000",
            "raw_exposure": 0.05,
        },
        deferred=False,
        defer_reason=None,
        shield_multiplier=decimal.Decimal("1.0"),
    )


def _buy_result() -> ScoringResult:
    return ScoringResult(
        score=decimal.Decimal("0.36"),
        side="buy",
        thr_buy=decimal.Decimal("0.1"),
        thr_sell=decimal.Decimal("0.1"),
        psi_vector={
            "s_linear": 0.6,
            "admission_pre_shield": 0.44,
            "final_score": 0.36,
            "shield_reasons": [],
            "threshold_factor": 1.0,
            "thr_buy": 0.1,
            "thr_sell": 0.1,
            "shield_multiplier": 1.0,
            "admission_shield_multiplier": 1.0,
            "side_why": "enter:buy",
            "raw_exposure": 0.5,
        },
        deferred=False,
        defer_reason=None,
        shield_multiplier=decimal.Decimal("1.0"),
    )


_BASE_CMD = {
    "symbol": "BTCUSDT",
    "tf_sec": 300,
    "bar_close_ts": 1_700_000_000_000,
    "warmup": {"full_ready": True, "ready": {}},
    "features": {
        "price": "100.0",
        "pillar_sum": 0.2,
        "pillar_contribs": {},
    },
}


# ---------------------------------------------------------------------------
# Test 1 — builder produces block
# ---------------------------------------------------------------------------


def test_anti_peak_builder_produces_block() -> None:
    """_build_anti_peak_observability returns a valid block with required fields."""
    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_neutral_result(),
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None

    result = _neutral_result()
    block = handler._build_anti_peak_observability(
        symbol="BTCUSDT",
        features={"price_motion": {"pm_norm_300s": 2.5}},
        result=result,
        state=handler._symbol_states["BTCUSDT"],
        pillar_sum=0.2,
        raw_exposure=0.05,
    )

    assert isinstance(block, dict), "block must be a dict"
    assert block["enabled"] is False
    assert block["gate_disabled"] is True
    assert block["motion_classification"] == "gate_disabled"
    assert block["disabled_config_snapshot"] is not None
    assert block["reason"] == "gate_disabled"
    assert "motion" in block, "motion key must be present"
    assert "score_path" in block, "score_path key must be present"
    assert "enabled" in block["motion"], "motion.enabled must be present"
    # With gates disabled (default), missing_reason should be non-None
    assert block["motion"]["missing_reason"] is not None or block["motion"]["enabled"]


def test_anti_peak_builder_produces_block_with_gates_enabled() -> None:
    """Builder with vol_gates_enabled=True populates motion sigma fields."""
    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_neutral_result(),
    )
    handler.vol_gates_enabled = True
    handler.anti_fomo_sigma = 10.0
    handler.anti_flat_sigma = 0.3
    handler.motion_window_sec = 300
    handler.vol_gates_config_state = {}

    result = _neutral_result()
    block = handler._build_anti_peak_observability(
        symbol="BTCUSDT",
        features={"price_motion": {"pm_norm_300s": 2.5}},
        result=result,
        state=handler._symbol_states["BTCUSDT"],
        pillar_sum=0.2,
        raw_exposure=0.05,
    )

    assert block["motion"]["enabled"] is True
    assert block["motion"]["motion_norm_sigma"] == 2.5
    assert block["motion"]["anti_fomo_sigma"] == 10.0
    assert block["motion"]["anti_flat_sigma"] == 0.3
    assert block["enabled"] is True
    assert block["gate_disabled"] is False
    assert block["active_config"]["anti_fomo_sigma"] == 10.0
    assert block["motion_classification"] == "within_band"
    assert block["motion_norm_sigma"] == 2.5
    assert block["consumed_by_gate"] is None
    assert block["score_path"] is not None


def test_anti_peak_builder_marks_insufficient_motion_without_neutral_defaults() -> None:
    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_neutral_result(),
    )
    handler.vol_gates_enabled = True
    handler.anti_fomo_sigma = 10.0
    handler.anti_flat_sigma = 0.3
    handler.motion_window_sec = 300
    handler.vol_gates_config_state = {
        "enabled": True,
        "anti_flat_sigma": 0.3,
        "anti_fomo_sigma": 10.0,
        "motion_window_sec": 300,
        "anti_flat_sigma_value_source": "active_config",
        "anti_fomo_sigma_value_source": "active_config",
        "motion_window_sec_value_source": "active_config",
        "missing_reason": None,
    }

    block = handler._build_anti_peak_observability(
        symbol="BTCUSDT",
        features={},
        result=_neutral_result(),
        state=handler._symbol_states["BTCUSDT"],
        pillar_sum=0.2,
        raw_exposure=0.05,
    )

    assert block["motion_classification"] == "insufficient_motion_data"
    assert block["motion_norm_sigma"] is None
    assert block["missing_inputs"]["motion_norm_sigma"] == "price_motion_block_missing"
    assert block["reason"] == "missing_from_features"


# ---------------------------------------------------------------------------
# Test 2 — strategy signal payload preserves block
# ---------------------------------------------------------------------------


def test_strategy_signal_payload_preserves_anti_peak_observability() -> None:
    """EVT:STRATEGY_SIGNAL_PRODUCED has scoring.anti_peak_observability."""
    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_buy_result(),
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None

    handler._process_decision("BTCUSDT", _BASE_CMD)

    signals = [p for n, p in emitted if n == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert signals, "Expected at least one EVT:STRATEGY_SIGNAL_PRODUCED"
    signal = signals[0]
    assert "scoring" in signal, "scoring block missing from signal payload"
    scoring = signal["scoring"]
    assert "anti_peak_observability" in scoring, (
        "anti_peak_observability missing from scoring block"
    )
    aps = scoring["anti_peak_observability"]
    assert isinstance(aps, dict), "anti_peak_observability must be a dict"
    assert aps["score_before_shields"] == 0.44
    assert aps["score_after_shields"] == 0.36
    assert aps["signal_threshold"] == 0.1
    assert "motion" in aps
    assert "score_path" in aps


# ---------------------------------------------------------------------------
# Test 3 — strategy blocked payload preserves block
# ---------------------------------------------------------------------------


def test_strategy_blocked_payload_preserves_anti_peak_observability() -> None:
    """EVT:STRATEGY_DECISION_BLOCKED details.anti_peak_observability is present for post-quadratic blocks."""
    blocked_calls: list = []

    def _capture_blocked(**kwargs):
        blocked_calls.append(kwargs)

    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_buy_result(),
    )
    # Replace _emit_strategy_blocked to capture the kwargs directly
    handler._emit_strategy_blocked = _capture_blocked

    # Force an entry-plan-missing block (post-regime-gate, post-vol-gate, pre-execution)
    handler.execution_gate = SimpleNamespace(
        check_entry=lambda **_: (False, "TEST_GATE_FAIL")
    )
    handler.entry_plan_calculator = SimpleNamespace(
        compute=lambda **_: SimpleNamespace(
            entry_price=decimal.Decimal("100.0"),
            stop_loss_price=decimal.Decimal("99.0"),
            take_profit_price=decimal.Decimal("101.0"),
        )
    )

    handler._process_decision("BTCUSDT", _BASE_CMD)

    assert blocked_calls, "Expected at least one _emit_strategy_blocked call"
    block_call = blocked_calls[-1]
    details = block_call.get("details") or {}
    assert "anti_peak_observability" in details, (
        f"anti_peak_observability missing from blocked details: {list(details.keys())}"
    )
    aps = details["anti_peak_observability"]
    assert isinstance(aps, dict)
    assert aps["source"] == "missing"
    assert aps["consumed_by_gate"] is False


# ---------------------------------------------------------------------------
# Test 4 — quadratic trace payload preserves block
# ---------------------------------------------------------------------------


def test_quadratic_decision_trace_payload_preserves_anti_peak_observability() -> None:
    """EVT:QUADRATIC_DECISION_TRACE has top-level anti_peak_observability."""
    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_neutral_result(),
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None

    handler._process_decision("BTCUSDT", _BASE_CMD)

    traces = [p for n, p in emitted if n == "EVT:QUADRATIC_DECISION_TRACE"]
    assert traces, "Expected at least one EVT:QUADRATIC_DECISION_TRACE"
    trace = traces[0]
    assert "anti_peak_observability" in trace, (
        "anti_peak_observability missing from EVT:QUADRATIC_DECISION_TRACE payload"
    )
    aps = trace["anti_peak_observability"]
    assert isinstance(aps, dict)
    assert aps["source"] == "missing"
    assert aps["consumed_by_gate"] is None
    assert aps["motion"]["enabled"] is False


# ---------------------------------------------------------------------------
# Test 5 — decision trace payload preserves block (via payload assembler)
# ---------------------------------------------------------------------------


def test_decision_trace_payload_assembler_propagates_anti_peak_observability() -> None:
    """payload_assembler.build_decision_trace_payload preserves anti_peak_observability from trace_context."""
    from apps.reference.domains.decision_making.intent.payload_assembler import (
        build_decision_trace_payload,
    )

    # Minimal ScoringGateway-like stub
    sg = SimpleNamespace(
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        trend_dir="UP",
        trend_run_length=3,
        trend_confidence=0.7,
        delta_price=0.01,
        pm_norm_10s=0.5,
        pm_norm_60s=1.2,
        pm_norm_300s=2.1,
        pm_norm_900s=None,
        vol_pct_10s=0.001,
        vol_pct_60s=0.002,
        vol_pct_300s=0.003,
        vol_pct_900s=None,
        gate_outcome="ALLOW",
        deny_reason=None,
        why="enter:buy",
        resolved_regime_confidence_strategy_id="aurora",
        resolved_regime_confidence_symbol="BTCUSDT",
        resolved_regime_confidence_regime_key="LOW_VOLATILITY",
        min_regime_confidence=None,
        resolved_min_regime_confidence=None,
        resolved_min_regime_confidence_source=None,
        resolved_min_regime_confidence_strategy_id=None,
        resolved_min_regime_confidence_regime_key=None,
        resolved_max_regime_confidence=None,
        resolved_max_regime_confidence_source=None,
        resolved_max_regime_confidence_strategy_id=None,
        resolved_max_regime_confidence_regime_key=None,
        resolved_regime_confidence_band_active=None,
        regime_confidence_breach_kind=None,
        regime_confidence_gate_verdict="ALLOW",
        threshold_applied=None,
        threshold_verdict="PASS",
        threshold_reason=None,
        apply_safety_gates=False,
        directional_sanity_enabled=False,
        nrr026_enabled=False,
        nrr026_effective_enforced=False,
        nrr027_enabled=False,
        nrr027_effective_enforced=False,
        price_motion_sanity_enabled=False,
        price_motion_backtest_bypass=False,
        nrr028_enabled=False,
        nrr028_effective_enforced=False,
        nrr029_enabled=False,
        nrr029_effective_enforced=False,
        nrr030_enabled=False,
        nrr030_effective_enforced=False,
        nrr063_enabled=False,
        nrr063_effective_enforced=False,
        low_vol_cost_floor_details=None,
    )

    anti_peak_block = {
        "schema_version": "1.0.0",
        "strategy_id": "aurora",
        "symbol": "BTCUSDT",
        "motion": {
            "enabled": False,
            "missing_reason": "gate_disabled",
        },
        "score_path": {
            "final_score": 0.36,
        },
    }

    strategy_trace = {
        "signal_score": 0.36,
        "decision_score": 0.36,
        "anti_peak_observability": anti_peak_block,
    }

    payload = build_decision_trace_payload(
        rid="test_rid",
        symbol="BTCUSDT",
        strategy_id="aurora",
        trace_ts_ms=1_700_000_000_000,
        intent_side="LONG",
        order_side="BUY",
        lifecycle_id=None,
        sg=sg,
        strategy_trace=strategy_trace,
        regime_provenance=None,
        tpsl_owner_ctx=None,
        gate_outcome="ALLOW",
        deny_reason=None,
        why="enter:buy",
    )

    assert "anti_peak_observability" in payload, (
        "EVT:DECISION_TRACE_EMITTED payload missing anti_peak_observability"
    )
    aps = payload["anti_peak_observability"]
    assert isinstance(aps, dict)
    assert aps["motion"]["enabled"] is False
    assert aps["motion"]["missing_reason"] == "gate_disabled"


def test_trade_intent_rejected_payload_preserves_anti_peak_observability() -> None:
    anti_peak_block = {
        "schema_version": "1.0.0",
        "enabled": True,
        "gate_disabled": False,
        "motion_classification": "within_band",
        "missing_inputs": {},
        "active_config": {"enabled": True, "anti_fomo_sigma": 10.0},
        "disabled_config_snapshot": None,
        "anti_fomo_sigma": 10.0,
        "anti_flat_sigma": 0.3,
        "window_sec": 300,
        "anti_fomo_sigma_value_source": "active_config",
        "anti_flat_sigma_value_source": "active_config",
        "window_sec_value_source": "active_config",
        "motion_norm_sigma": 2.5,
        "score_before_shields": 0.44,
        "score_after_shields": 0.36,
        "final_score": 0.36,
        "signal_threshold": 0.1,
        "danger_zone_applied": False,
        "context_shield_applied": None,
        "attenuated_below_threshold": False,
        "consumed_by_gate": True,
        "source": "cmd_typed",
        "ready": True,
        "reason": "not_applied:motion_within_allowed_band",
    }
    dm = SimpleNamespace(
        _emit_trade_intent_rejected=Mock(),
        _record_blocked_intent=lambda _symbol: None,
        logger=SimpleNamespace(error=lambda *args, **kwargs: None),
    )
    gateway = StrategyGateway(dm)

    gateway._reject(
        symbol="BTCUSDT",
        strategy_id="aurora",
        side="BUY",
        rid="rid-reject-1",
        reason_code="NRR-TEST",
        reason="DECISION",
        context="test_context",
        why_chain=["TEST"],
        details={"origin": "unit"},
        signal_payload={
            "scoring": {"anti_peak_observability": anti_peak_block}
        },
    )

    rejected = dm._emit_trade_intent_rejected.call_args.kwargs
    assert rejected["details"]["anti_peak_observability"]["enabled"] is True
    fragment = build_payload_fragment(
        {"symbol": "BTCUSDT", "details": rejected["details"]},
        event_name="EVT:TRADE_INTENT_REJECTED",
    )
    assert fragment["anti_peak_observability"]["consumed_by_gate"] is True


# ---------------------------------------------------------------------------
# Test 6 — shadow journal payload_fragment preserves block
# ---------------------------------------------------------------------------


def test_shadow_journal_payload_fragment_preserves_anti_peak_observability() -> None:
    """build_payload_fragment copies anti_peak_observability from event payload to persisted fragment."""
    anti_peak_block = {
        "schema_version": "1.0.0",
        "strategy_id": "aurora",
        "symbol": "BTCUSDT",
        "motion": {
            "enabled": False,
            "missing_reason": "gate_disabled",
            "motion_norm_sigma": None,
            "anti_fomo_sigma": 10.0,
            "anti_flat_sigma": 0.3,
        },
        "score_path": {
            "final_score": 0.36,
            "signal_threshold": 0.1,
        },
    }

    # Simulate payload as it would arrive at build_payload_fragment
    payload = {
        "symbol": "BTCUSDT",
        "strategy_id": "aurora",
        "side": "BUY",
        "reason_code": "REGIME_NOT_ALLOWLISTED",
        "anti_peak_observability": anti_peak_block,
        "ts_ms": 1_700_000_000_000,
    }

    fragment = build_payload_fragment(payload)

    assert "anti_peak_observability" in fragment, (
        "build_payload_fragment must preserve anti_peak_observability in output fragment"
    )
    aps = fragment["anti_peak_observability"]
    assert isinstance(
        aps, dict), "anti_peak_observability in fragment must be a dict"
    assert aps["motion"]["enabled"] is False
    assert aps["motion"]["missing_reason"] == "gate_disabled"
    assert aps["score_path"]["final_score"] == 0.36


def test_shadow_journal_hoists_anti_peak_from_strategy_signal_scoring() -> None:
    anti_peak_block = {
        "enabled": False,
        "gate_disabled": True,
        "motion_classification": "gate_disabled",
        "missing_inputs": {},
        "disabled_config_snapshot": {"enabled": False},
        "source": "missing",
        "ready": False,
        "reason": "gate_disabled",
    }
    payload = {
        "symbol": "BTCUSDT",
        "strategy_id": "aurora",
        "scoring": {"anti_peak_observability": anti_peak_block},
    }

    fragment = build_payload_fragment(
        payload,
        event_name="EVT:STRATEGY_SIGNAL_PRODUCED",
    )

    assert fragment["anti_peak_observability"]["gate_disabled"] is True


def test_shadow_journal_hoists_anti_peak_from_blocked_details() -> None:
    anti_peak_block = {
        "enabled": True,
        "gate_disabled": False,
        "motion_classification": "anti_flat_triggered",
        "missing_inputs": {},
        "source": "cmd_typed",
        "ready": True,
        "reason": "anti_flat_threshold_breached",
    }
    payload = {
        "symbol": "BTCUSDT",
        "details": {"anti_peak_observability": anti_peak_block},
    }

    fragment = build_payload_fragment(
        payload,
        event_name="EVT:STRATEGY_DECISION_BLOCKED",
    )

    assert fragment["anti_peak_observability"]["motion_classification"] == "anti_flat_triggered"


def test_shadow_journal_payload_fragment_preserves_anti_peak_for_quadratic_trace() -> None:
    """payload_fragment from EVT:QUADRATIC_DECISION_TRACE includes anti_peak_observability."""
    anti_peak_block = {
        "schema_version": "1.0.0",
        "symbol": "BTCUSDT",
        "motion": {
            "enabled": True,
            "motion_norm_sigma": 3.5,
            "anti_fomo_triggered": False,
            "anti_flat_triggered": False,
        },
        "score_path": {"final_score": 0.0, "signal_threshold": 0.1},
        "classification": {"hard_blocked": False},
    }

    # Simulate EVT:QUADRATIC_DECISION_TRACE payload shape
    payload = {
        "symbol": "BTCUSDT",
        "strategy_id": "aurora",
        "side": "",
        "rid": "aurora_BTCUSDT_1700000000000",
        "ts_ms": 1_700_000_000_000,
        "anti_peak_observability": anti_peak_block,
    }

    fragment = build_payload_fragment(payload)

    assert "anti_peak_observability" in fragment
    assert fragment["anti_peak_observability"]["motion"]["enabled"] is True
    assert fragment["anti_peak_observability"]["motion"]["motion_norm_sigma"] == 3.5


# ---------------------------------------------------------------------------
# Test 7 — disabled config truth survives persistence
# ---------------------------------------------------------------------------


def test_disabled_config_truth_survives_persistence() -> None:
    """With vol gates disabled, persisted fragment shows enabled=false and gate_disabled."""
    emitted: list = []
    handler = _build_handler(
        emit_fn=lambda name, payload: emitted.append((name, payload)),
        scoring_result=_buy_result(),
    )
    handler.execution_gate = None
    handler.entry_plan_calculator = None
    handler.vol_gates_enabled = False
    handler.anti_fomo_sigma = 10.0
    handler.anti_flat_sigma = 0.3
    handler.motion_window_sec = 300
    handler.vol_gates_config_state = {
        "enabled": False,
        "anti_flat_sigma": 0.3,
        "anti_fomo_sigma": 10.0,
        "motion_window_sec": 300,
        "anti_flat_sigma_value_source": "disabled_config_snapshot",
        "anti_fomo_sigma_value_source": "disabled_config_snapshot",
        "motion_window_sec_value_source": "disabled_config_snapshot",
        "missing_reason": "gate_disabled",
    }

    handler._process_decision("BTCUSDT", {
        **_BASE_CMD,
        "features": {
            "price": "100.0",
            "pillar_sum": 0.6,
            "pillar_contribs": {},
            "price_motion": {"pm_norm_300s": 12.0},
        },
    })

    signals = [p for n, p in emitted if n == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert signals
    signal = signals[0]
    aps = signal["scoring"]["anti_peak_observability"]

    # Verify disabled state in live payload
    assert aps["gate_disabled"] is True
    assert aps["disabled_config_snapshot"]["enabled"] is False
    assert aps["motion"]["enabled"] is False, "motion.enabled must be False when disabled"
    assert aps["motion"]["missing_reason"] == "gate_disabled", (
        "missing_reason must be gate_disabled when vol gates are disabled"
    )
    assert aps["motion"]["anti_fomo_sigma_value_source"] == "disabled_config_snapshot", (
        "value_source must indicate non-authoritative snapshot"
    )

    # Verify disabled state survives payload_fragment
    fragment = build_payload_fragment(
        {"anti_peak_observability": aps, "symbol": "BTCUSDT"})

    assert "anti_peak_observability" in fragment, "fragment must preserve anti_peak_observability"
    frag_aps = fragment["anti_peak_observability"]
    assert frag_aps["motion"]["enabled"] is False
    assert frag_aps["motion"]["missing_reason"] == "gate_disabled"
    # No active-looking authoritative threshold in non-authoritative source
    assert frag_aps["motion"]["anti_fomo_sigma_value_source"] == "disabled_config_snapshot"


def test_disabled_config_no_active_authoritative_threshold_in_fragment() -> None:
    """When gates disabled, persisted fragment must not carry active_config as value_source."""
    anti_peak_block = {
        "schema_version": "1.0.0",
        "symbol": "BTCUSDT",
        "motion": {
            "enabled": False,
            "missing_reason": "gate_disabled",
            "anti_fomo_sigma_value_source": "disabled_config_snapshot",
            "anti_flat_sigma_value_source": "disabled_config_snapshot",
            "window_sec_value_source": "disabled_config_snapshot",
            "anti_fomo_sigma": 10.0,
            "anti_flat_sigma": 0.3,
            "motion_norm_sigma": None,
        },
    }

    fragment = build_payload_fragment(
        {"anti_peak_observability": anti_peak_block})
    aps = fragment["anti_peak_observability"]

    assert aps["motion"]["anti_fomo_sigma_value_source"] != "active_config", (
        "disabled gates must not show active_config as source"
    )
    assert aps["motion"]["enabled"] is False
