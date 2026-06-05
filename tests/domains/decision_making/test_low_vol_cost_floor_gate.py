from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.config.domains import decision_making as domain_dm
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
)
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.decision_making.gates.low_vol_cost_floor import (
    _resolve_low_vol_threshold,
    evaluate_low_vol_cost_floor_gate,
)
from apps.reference.domains.decision_making.gates.safety_gates import SafetyGateResult
from apps.reference.shared.decision_primitives.score_lineage import (
    SIGNED_DECISION_SCORE,
    build_score_lineage_payload,
    build_score_lineage_record,
)


CONFIG_DIR = Path("config/aurora")


def _thresholds_payload(**overrides):
    payload = {
        "target_net_fee_multiple": 2.0,
        "min_tp_fee_coverage": 3.0,
        "min_rr": 1.2,
        "min_regime_confidence_by_regime": {
            "DEFAULT": 0.45,
            "LOW_VOLATILITY": 0.39,
        },
        "min_direction_confidence_by_regime": {
            "DEFAULT": 0.55,
            "LOW_VOLATILITY": 0.51,
        },
        "min_raw_score_by_regime": {
            "DEFAULT": 0.55,
            "LOW_VOLATILITY": 0.51,
        },
        "min_normalized_confidence_by_regime": {
            "DEFAULT": 0.55,
            "LOW_VOLATILITY": 0.51,
        },
    }
    payload.update(overrides)
    return payload


def _gate_config(**overrides):
    payload = {
        "enabled": True,
        "enforce_in_modes": ["testnet", "hybrid_live_data_testnet_exec"],
        "observe_only_in_modes": ["live", "production"],
        "regimes": ["LOW_VOLATILITY"],
        "fee": {
            "open_fee_bps": 4.0,
            "close_fee_bps": 4.0,
            "fee_source": "explicit_config",
        },
        "slippage": {
            "buffer_bps": 2.0,
            "source": "explicit_config",
        },
        "thresholds": _thresholds_payload(),
        "direction_confidence": {
            "required": True,
            "raw_signed_score_sources": ["signal_score", "final_score"],
            "normalized_confidence_sources": ["strategy_confidence", "judge_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        "geometry": {
            "require_tpsl": True,
            "missing_policy": "fail_closed",
        },
    }
    payload.update(overrides)
    return domain_dm.LowVolCostFloorGateConfig.model_validate(payload)


def _make_dm(*, trading_mode: str):
    with patch.object(DecisionMaking, "__init__", lambda *_args, **_kwargs: None):
        dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = MagicMock()
    dm.fsm = MagicMock()
    dm._builder = MagicMock()
    dm._emitter = MagicMock()
    dm.normalize_signals_mode = "signed_v2"
    dm.config = SimpleNamespace(
        trading_mode=trading_mode,
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                low_vol_cost_floor_gate=_gate_config(),
            )
        ),
    )
    return dm


def _allow_sg(*, regime: str = "LOW_VOLATILITY", regime_confidence: float = 0.8) -> SafetyGateResult:
    return SafetyGateResult(
        outcome="ALLOW",
        strategy_id="aurora",
        intent_side="LONG",
        trace_ts_ms=1_700_000_000_999,
        signal_score=0.9,
        regime=regime,
        regime_confidence=regime_confidence,
        why_short="allow:baseline",
    )


def _segment_candidate_evaluation(
    *,
    trading_mode: str = "testnet",
    regime_confidence: float = 0.8,
    side: str = "SELL",
    signal_score: float | None = -0.2,
    target_price: float | None = None,
    stop_price: float | None = None,
    strategy_trace=None,
    gate_cfg=None,
):
    normalized_side = str(side).upper()
    if normalized_side in {"SELL", "SHORT"}:
        resolved_target_price = 99.50 if target_price is None else target_price
        resolved_stop_price = 100.25 if stop_price is None else stop_price
    else:
        resolved_target_price = 100.50 if target_price is None else target_price
        resolved_stop_price = 99.75 if stop_price is None else stop_price

    return evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config() if gate_cfg is None else gate_cfg,
        trading_mode=trading_mode,
        regime="LOW_VOLATILITY",
        regime_confidence=regime_confidence,
        strategy_id="aurora",
        symbol="BTCUSDT",
        side=side,
        entry_price=100.0,
        target_price=resolved_target_price,
        stop_price=resolved_stop_price,
        strategy_trace=strategy_trace,
        signal_score=signal_score,
        reduce_only=False,
    )


def test_valid_low_vol_cost_floor_config_accepted() -> None:
    cfg = _gate_config()

    assert cfg.thresholds.min_regime_confidence_by_regime["LOW_VOLATILITY"] == 0.39
    assert cfg.thresholds.min_direction_confidence_by_regime["DEFAULT"] == 0.55
    assert cfg.observe_only_in_modes == ["live", "production"]
    assert cfg.direction_confidence.required is True
    assert cfg.direction_confidence.missing_policy == "fail_closed"


def test_low_vol_cost_floor_config_rejects_unknown_fields() -> None:
    try:
        _gate_config(unexpected_field=True)
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected validation failure for unknown field")

    assert "unexpected_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_low_vol_cost_floor_thresholds_require_default_and_low_volatility() -> None:
    try:
        _gate_config(
            thresholds={
                "target_net_fee_multiple": 2.0,
                "min_tp_fee_coverage": 3.0,
                "min_rr": 1.2,
                "min_regime_confidence_by_regime": {"DEFAULT": 0.45},
                "min_direction_confidence_by_regime": {"DEFAULT": 0.55},
            }
        )
    except Exception as exc:
        message = str(exc)
    else:
        raise AssertionError(
            "Expected validation failure for missing LOW_VOLATILITY threshold")

    assert "LOW_VOLATILITY" in message


def test_gate_inactive_when_disabled() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(enabled=False),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=101.0,
        stop_price=99.0,
        strategy_trace=None,
        signal_score=0.9,
        reduce_only=False,
    )

    assert evaluation.active is False
    assert evaluation.block is False
    assert evaluation.gate_mode == "disabled"


def test_gate_observes_but_does_not_block_in_live_by_default() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="live",
        regime="LOW_VOLATILITY",
        regime_confidence=0.5,
        side="BUY",
        entry_price=100.0,
        target_price=100.1,
        stop_price=99.9,
        strategy_trace=None,
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.active is True
    assert evaluation.gate_mode == "observe_only"
    assert evaluation.block is False
    assert evaluation.threshold_failed is True
    assert "actual_tp_bps_below_required_gross_tp" in evaluation.details["violations"]


def test_gate_blocks_in_testnet_when_tp_below_required_fee_floor() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.1,
        stop_price=99.0,
        strategy_trace=None,
        signal_score=0.9,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.reason == "LOW_VOL_COST_FLOOR_BLOCKED"
    assert evaluation.details["required_gross_tp_bps"] == 26.0
    assert "actual_tp_bps_below_required_gross_tp" in evaluation.details["violations"]


def test_gate_allows_in_testnet_when_fee_floor_rr_and_confidence_pass() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 0.9,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.threshold_failed is False
    assert evaluation.details["tp_fee_coverage_ratio"] == 3.75
    assert evaluation.details["rr_ratio"] == 1.2


def test_sell_direction_only_raw_signal_candidate_is_allowed_by_segment_override() -> None:
    evaluation = _segment_candidate_evaluation()

    assert evaluation.block is False
    assert evaluation.threshold_failed is True
    assert evaluation.reason == "LOW_VOL_COST_FLOOR_PASS"
    assert evaluation.details["reason"] == "LOW_VOL_COST_FLOOR_SEGMENT_OVERRIDE_ALLOW"
    assert evaluation.details["gate_reason"] == "LOW_VOL_COST_FLOOR_PASS"
    assert evaluation.details["nrr062_segment_override_applied"] is True
    assert evaluation.details["nrr062_segment_override_name"] == "LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL"
    assert evaluation.details["nrr062_segment_override_no_production"] is True
    assert evaluation.details["original_nrr062_reason"] == "LOW_VOL_COST_FLOOR_BLOCKED"
    assert evaluation.details["original_low_vol_reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"
    assert evaluation.details["selected_source"] == "signal_score"
    assert evaluation.details["selected_scale"] == "raw_signed_score"
    assert evaluation.details["threshold_family"] == "raw_signed_score"
    assert evaluation.details["violations"] == [
        "direction_confidence_below_threshold"]


def test_buy_direction_only_raw_signal_remains_blocked() -> None:
    evaluation = _segment_candidate_evaluation(side="BUY", signal_score=0.2)

    assert evaluation.block is True
    assert evaluation.details["nrr062_segment_override_applied"] is False
    assert evaluation.details["selected_source"] == "signal_score"
    assert evaluation.details["selected_scale"] == "raw_signed_score"
    assert evaluation.details["threshold_family"] == "raw_signed_score"
    assert evaluation.details["violations"] == [
        "direction_confidence_below_threshold"]


def test_sell_dual_regime_and_direction_failure_remains_blocked() -> None:
    evaluation = _segment_candidate_evaluation(regime_confidence=0.3)

    assert evaluation.block is True
    assert evaluation.details["nrr062_segment_override_applied"] is False
    assert evaluation.details["violations"] == [
        "regime_confidence_below_threshold",
        "direction_confidence_below_threshold",
    ]


def test_sell_geometry_failure_remains_blocked() -> None:
    evaluation = _segment_candidate_evaluation(
        signal_score=-0.8, target_price=99.90)

    assert evaluation.block is True
    assert evaluation.details["nrr062_segment_override_applied"] is False
    assert "actual_tp_bps_below_required_gross_tp" in evaluation.details["violations"]


@pytest.mark.parametrize("trading_mode", ["live", "production"])
def test_live_and_production_candidate_remain_unmodified(trading_mode: str) -> None:
    evaluation = _segment_candidate_evaluation(trading_mode=trading_mode)

    assert evaluation.block is False
    assert evaluation.gate_mode == "observe_only"
    assert evaluation.details["would_block"] is True
    assert evaluation.details["nrr062_segment_override_applied"] is False
    assert evaluation.details["reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"


def test_missing_selected_source_scale_and_family_fails_closed_for_override() -> None:
    evaluation = _segment_candidate_evaluation(
        signal_score=None, strategy_trace=None)

    assert evaluation.block is True
    assert evaluation.details["nrr062_segment_override_applied"] is False
    assert evaluation.details["selected_source"] == "unavailable"
    assert evaluation.details["selected_scale"] == "unknown"
    assert evaluation.details["threshold_family"] == "unknown"


def test_current_config_allows_segment_override_without_new_yaml_fields() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    gate_cfg = cfg.domains.decision_making.low_vol_cost_floor_gate

    evaluation = _segment_candidate_evaluation(gate_cfg=gate_cfg)

    assert evaluation.block is False
    assert evaluation.details["nrr062_segment_override_applied"] is True
    assert evaluation.details["selected_source"] == "signal_score"
    assert evaluation.details["selected_scale"] == "raw_signed_score"
    assert evaluation.details["threshold_family"] == "raw_signed_score"


def test_regime_confidence_threshold_resolved_by_regime_map() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.38,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=0.9,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["resolved_min_regime_confidence"] == 0.39
    assert "regime_confidence_below_threshold" in evaluation.details["violations"]


def test_direction_confidence_threshold_resolved_by_regime_map() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 0.50,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["direction_confidence_source"] == "strategy_confidence"
    assert evaluation.details["resolved_min_direction_confidence"] == 0.51
    assert "direction_confidence_below_threshold" in evaluation.details["violations"]


def test_missing_direction_confidence_follows_configured_policy() -> None:
    cfg = _gate_config(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "warn_and_allow",
        }
    )
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.threshold_failed is False
    assert evaluation.details["direction_confidence"] is None
    assert "LOW_VOL_COST_FLOOR_UNSCORABLE:direction_confidence_missing" in evaluation.details[
        "warnings"]


def test_missing_geometry_follows_configured_policy() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=None,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=0.9,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert "geometry_missing" in evaluation.details["violations"]


def test_metadata_includes_required_economic_fields() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="SELL",
        entry_price=100.0,
        target_price=99.70,
        stop_price=100.25,
        strategy_trace={
            "objective": {"final_score": -0.8, "side": "SELL"},
            "strategy_confidence": 0.8,
            "strategy_confidence_side_scope": "SELL",
        },
        signal_score=None,
        reduce_only=False,
    )

    expected_keys = {
        "reason",
        "gate_reason",
        "regime",
        "regime_confidence",
        "resolved_min_regime_confidence",
        "resolved_min_regime_confidence_source",
        "resolved_min_regime_confidence_strategy_id",
        "resolved_min_regime_confidence_symbol",
        "side",
        "direction_confidence",
        "direction_confidence_source",
        "direction_confidence_side_scope",
        "direction_confidence_required",
        "direction_confidence_missing_policy",
        "direction_confidence_failure_reason",
        "resolved_min_direction_confidence",
        "resolved_min_direction_confidence_source",
        "resolved_min_direction_confidence_strategy_id",
        "resolved_min_direction_confidence_symbol",
        "entry_price",
        "target_price",
        "stop_price",
        "actual_tp_bps",
        "actual_sl_bps",
        "round_trip_fee_bps",
        "required_gross_tp_bps",
        "target_net_fee_multiple",
        "tp_fee_coverage_ratio",
        "rr_ratio",
        "trading_mode",
        "gate_mode",
        "evaluated",
        "evaluation_stage",
        "missing_inputs",
        "score_context",
        "price_motion_context",
        "liquidity_context",
        "thresholds",
        "subcondition_verdicts",
        "provenance_context",
        "economics_context",
        "direction_confidence_context",
        "direction_confidence_selected_value",
        "direction_confidence_selected_source",
        "direction_confidence_selected_scale",
        "direction_confidence_required_threshold",
        "direction_confidence_threshold_source",
        "direction_confidence_margin",
        "direction_confidence_side_match",
        "proposed_side",
        "signal_score_raw",
        "signal_score_abs",
        "strategy_confidence_candidate",
        "strategy_confidence_side_scope",
        "final_score_raw",
        "judge_confidence_candidate",
        "active_allowed_sources",
        "missing_allowed_sources",
        "confidence_resolution_status",
        "aurora_pillar_confidence_candidate",
        "aurora_threshold_factor",
        "aurora_raw_score_to_threshold_ratio",
        "decision_id",
        "cycle_key",
        "features_ts_ms",
        "detector_event",
        "observation_summary",
    }

    assert expected_keys.issubset(evaluation.details.keys())
    assert evaluation.details["direction_confidence_source"] == "strategy_confidence"
    assert evaluation.details["direction_confidence_side_scope"] == "SELL"
    assert evaluation.details["evaluated"] is True
    assert evaluation.details["price_motion_context"]["missing"]["pm_norm_60s"] is True
    assert evaluation.details["score_context"]["final_score"] == -0.8
    assert evaluation.details["direction_confidence_context"]["passed"] is True
    assert evaluation.details["subcondition_verdicts"]["rr_passed"] is True
    assert evaluation.details["direction_confidence_selected_scale"] == "normalized_confidence"
    assert evaluation.details["confidence_resolution_status"] == "present_passed"


def test_observability_details_capture_explicit_missing_flags() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "strategy_confidence": 0.77,
            "strategy_confidence_candidate": 0.88,
            "strategy_confidence_side_scope": "BUY",
            "direction_confidence": 0.77,
            "direction_confidence_source": "strategy_confidence",
            "direction_confidence_side_scope": "BUY",
            "final_score_raw": 0.81,
            "judge_confidence_candidate": 0.66,
            "decision_id": "decision-1",
            "cycle_key": "ENTRY:DOGEUSDT:300:1700000000000",
            "features_ts_ms": 1_700_000_000_000,
            "detector_event": {"bar_close_ts_ms": 1_700_000_000_299},
            "aurora_pillar_confidence_candidate": 0.95,
            "aurora_threshold_factor": 0.14,
            "aurora_raw_score_to_threshold_ratio": 0.95,
            "ret_60s": 0.012,
            "objective": {
                "score": 0.81,
                "threshold": 0.54,
                "threshold_margin": 0.27,
            },
        },
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.details["score_context"]["objective_score"] == 0.81
    assert evaluation.details["score_context"]["score_threshold"] == 0.54
    assert evaluation.details["score_context"]["score_margin"] == 0.27
    assert evaluation.details["price_motion_context"]["ret_60s"] == 0.012
    assert evaluation.details["price_motion_context"]["missing"]["ret_300s"] is True
    assert evaluation.details["liquidity_context"]["missing"]["spread_bps"] is True
    assert evaluation.details["missing_inputs"]["signal_score"] is True
    assert evaluation.details["provenance_context"]["strategy_trace_present"] is True
    assert evaluation.details["observation_summary"]["threshold_failed"] is False
    assert evaluation.details["strategy_confidence_candidate"] == 0.88
    assert evaluation.details["strategy_confidence_side_scope"] == "BUY"
    assert evaluation.details["final_score_raw"] == 0.81
    assert evaluation.details["judge_confidence_candidate"] == 0.66
    assert evaluation.details["decision_id"] == "decision-1"
    assert evaluation.details["cycle_key"] == "ENTRY:DOGEUSDT:300:1700000000000"
    assert evaluation.details["features_ts_ms"] == 1_700_000_000_000
    assert evaluation.details["detector_event"]["bar_close_ts_ms"] == 1_700_000_000_299
    assert evaluation.details["aurora_pillar_confidence_candidate"] == 0.95
    assert evaluation.details["aurora_threshold_factor"] == 0.14
    assert evaluation.details["aurora_raw_score_to_threshold_ratio"] == 0.95


def test_observability_details_extract_ret_fields_from_nested_price_motion() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "strategy_confidence": 0.77,
            "strategy_confidence_side_scope": "BUY",
            "price_motion": {
                "pm_norm_60s": 0.62,
                "pm_norm_300s": 0.91,
                "vol_pct_300s": 0.004,
                "ret_60s": 0.0012,
                "ret_300s": 0.0034,
            },
            "market": {
                "spread_bps": 0.04,
                "liquidity_kappa": 0.998,
                "absorption": -0.12,
            },
        },
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.details["price_motion_context"]["ret_60s"] == 0.0012
    assert evaluation.details["price_motion_context"]["ret_300s"] == 0.0034
    assert evaluation.details["price_motion_context"]["missing"]["ret_60s"] is False
    assert evaluation.details["price_motion_context"]["missing"]["ret_300s"] is False
    assert evaluation.details["price_motion_context"]["pm_norm_60s"] == 0.62
    assert evaluation.details["price_motion_context"]["pm_norm_300s"] == 0.91
    assert evaluation.details["price_motion_context"]["vol_pct_300s"] == 0.004
    assert evaluation.details["liquidity_context"]["spread_bps"] == 0.04
    assert evaluation.details["liquidity_context"]["liquidity_kappa"] == 0.998
    assert evaluation.details["liquidity_context"]["absorption"] == -0.12


def test_observability_details_keep_missing_ret_fields_explicit_without_fallbacks() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "strategy_confidence": 0.77,
            "strategy_confidence_side_scope": "BUY",
            "price_motion": {
                "pm_norm_60s": 0.62,
                "pm_norm_300s": 0.91,
                "vol_pct_300s": 0.004,
            },
        },
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.details["price_motion_context"]["ret_60s"] is None
    assert evaluation.details["price_motion_context"]["ret_300s"] is None
    assert evaluation.details["price_motion_context"]["missing"]["ret_60s"] is True
    assert evaluation.details["price_motion_context"]["missing"]["ret_300s"] is True
    assert evaluation.details["missing_inputs"]["ret_60s"] is True
    assert evaluation.details["missing_inputs"]["ret_300s"] is True


def test_signal_score_observability_fields_capture_raw_scale_and_margin_without_changing_block() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "active_threshold": 0.0005,
            "aurora_threshold_factor": 0.14,
            "aurora_pillar_confidence_candidate": 0.029285714285714286,
            "aurora_raw_score_to_threshold_ratio": 0.029285714285714286,
        },
        signal_score=0.0041,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["signal_score_raw"] == 0.0041
    assert evaluation.details["signal_score_abs"] == 0.0041
    assert evaluation.details["direction_confidence_selected_source"] == "signal_score"
    assert evaluation.details["direction_confidence_selected_scale"] == "raw_signed_score"
    assert evaluation.details["direction_confidence_required_threshold"] == 0.51
    assert evaluation.details["direction_confidence_margin"] == pytest.approx(
        0.0041 - 0.51)
    assert evaluation.details["confidence_resolution_status"] == "present_below_threshold"
    assert "direction_confidence_below_threshold" in evaluation.details["violations"]


def test_strategy_confidence_candidate_is_logged_without_being_selected() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "strategy_confidence_candidate": 0.88,
            "strategy_confidence_side_scope": "BUY",
        },
        signal_score=0.50,
        reduce_only=False,
    )

    assert evaluation.details["strategy_confidence_candidate"] == 0.88
    assert evaluation.details["strategy_confidence_side_scope"] == "BUY"
    assert evaluation.details["direction_confidence_selected_source"] == "signal_score"
    assert evaluation.details["direction_confidence_source"] == "signal_score"


def test_missing_direction_confidence_logs_missing_allowed_sources_and_missing_status() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score", "final_score"],
            "normalized_confidence_sources": ["strategy_confidence", "judge_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.9,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["confidence_resolution_status"] == "missing"
    assert evaluation.details["missing_allowed_sources"] == [
        "signal_score",
        "final_score",
        "strategy_confidence",
        "judge_confidence",
    ]


def test_wrong_side_signed_score_logs_side_mismatch_without_relaxing_gate() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "signal_score": -0.9,
            "score_lineage": build_score_lineage_payload(
                [
                    build_score_lineage_record(
                        field="signal_score",
                        value=-0.9,
                        producer="StrategyGateway strategy_trace assembly",
                        consumer_stage="strategy_gateway.strategy_trace",
                        scale=SIGNED_DECISION_SCORE,
                        compatibility_alias_for="decision_score",
                    )
                ]
            ),
        },
        signal_score=-0.9,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["direction_confidence_side_match"] is False
    assert evaluation.details["confidence_resolution_status"] == "wrong_side"
    assert evaluation.details["direction_confidence_failure_reason"] == "invalid_direction_confidence_value"


def test_high_signal_score_logs_present_passed_status() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 0.85,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.details["confidence_resolution_status"] == "present_passed"
    assert evaluation.details["direction_confidence_side_match"] is True


def test_strategy_symbol_threshold_override_applies_only_to_matching_symbol() -> None:
    cfg = _gate_config(
        thresholds=_thresholds_payload(
            min_regime_confidence_overrides_by_strategy_symbol={
                "aurora": {
                    "XRPUSDT": {"DEFAULT": 0.46, "LOW_VOLATILITY": 0.45},
                },
            },
            min_normalized_confidence_overrides_by_strategy_symbol={
                "aurora": {
                    "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59},
                },
            },
        )
    )

    xrp_evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.44,
        strategy_id="aurora",
        symbol="XRPUSDT",
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 0.58,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )
    btc_evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.44,
        strategy_id="aurora",
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 0.58,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )

    assert xrp_evaluation.block is True
    assert xrp_evaluation.details["resolved_min_regime_confidence"] == 0.45
    assert xrp_evaluation.details["resolved_min_regime_confidence_source"] == "strategy_symbol_override"
    assert xrp_evaluation.details["resolved_min_direction_confidence"] == 0.59
    assert xrp_evaluation.details["resolved_min_direction_confidence_source"] == "strategy_symbol_override"
    assert xrp_evaluation.details["resolved_min_direction_confidence_symbol"] == "XRPUSDT"
    assert btc_evaluation.block is False
    assert btc_evaluation.details["resolved_min_regime_confidence"] == 0.39
    assert btc_evaluation.details["resolved_min_regime_confidence_source"] == "global_regime"
    assert btc_evaluation.details["resolved_min_direction_confidence"] == 0.51
    assert btc_evaluation.details["resolved_min_direction_confidence_source"] == "global_regime"


@pytest.mark.parametrize(
    ("strategy_id", "expected_direction_threshold", "expected_regime_threshold"),
    [
        ("aurora", 0.59, 0.45),
        ("md_amr", 0.88, 0.90),
        ("mean_reversion", 0.79, 0.82),
        ("llm_microstructure", 0.74, 0.78),
    ],
)
def test_strategy_symbol_threshold_override_supports_each_strategy(
    strategy_id: str,
    expected_direction_threshold: float,
    expected_regime_threshold: float,
) -> None:
    cfg = _gate_config(
        thresholds=_thresholds_payload(
            min_regime_confidence_overrides_by_strategy_symbol={
                "aurora": {
                    "XRPUSDT": {"DEFAULT": 0.46, "LOW_VOLATILITY": 0.45},
                },
                "md_amr": {
                    "XRPUSDT": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.90},
                },
                "mean_reversion": {
                    "XRPUSDT": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.82},
                },
                "llm_microstructure": {
                    "XRPUSDT": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.78},
                },
            },
            min_normalized_confidence_overrides_by_strategy_symbol={
                "aurora": {
                    "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59},
                },
                "md_amr": {
                    "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.88},
                },
                "mean_reversion": {
                    "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.79},
                },
                "llm_microstructure": {
                    "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.74},
                },
            },
        )
    )

    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=1.0,
        strategy_id=strategy_id,
        symbol="XRPUSDT",
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 1.0,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.details["resolved_min_direction_confidence"] == expected_direction_threshold
    assert evaluation.details["resolved_min_regime_confidence"] == expected_regime_threshold
    assert evaluation.details["resolved_min_direction_confidence_source"] == "strategy_symbol_override"
    assert evaluation.details["resolved_min_regime_confidence_source"] == "strategy_symbol_override"
    assert evaluation.details["resolved_min_direction_confidence_strategy_id"] == strategy_id
    assert evaluation.details["resolved_min_direction_confidence_symbol"] == "XRPUSDT"


def test_strategy_symbol_override_uses_default_map_without_leaking_low_vol_thresholds() -> None:
    regime_resolution = _resolve_low_vol_threshold(
        mapping={"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39},
        overrides_by_strategy_symbol={
            "aurora": {
                "XRPUSDT": {"DEFAULT": 0.46, "LOW_VOLATILITY": 0.45},
            },
        },
        strategy_id="aurora",
        symbol="XRPUSDT",
        regime="TREND_UP",
    )
    direction_resolution = _resolve_low_vol_threshold(
        mapping={"DEFAULT": 0.55, "LOW_VOLATILITY": 0.51},
        overrides_by_strategy_symbol={
            "aurora": {
                "XRPUSDT": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.59},
            },
        },
        strategy_id="aurora",
        symbol="XRPUSDT",
        regime="TREND_UP",
    )

    assert regime_resolution.value == 0.46
    assert regime_resolution.source == "strategy_symbol_override"
    assert regime_resolution.regime_key == "DEFAULT"
    assert direction_resolution.value == 0.55
    assert direction_resolution.source == "strategy_symbol_override"
    assert direction_resolution.regime_key == "DEFAULT"


def test_current_config_requires_explicit_live_normalized_confidence_for_aurora() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()
    gate_cfg = cfg.domains.decision_making.low_vol_cost_floor_gate

    aurora_xrp = evaluate_low_vol_cost_floor_gate(
        gate_cfg=gate_cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.9,
        strategy_id="aurora",
        symbol="XRPUSDT",
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=0.69,
        reduce_only=False,
    )
    md_amr_xrp = evaluate_low_vol_cost_floor_gate(
        gate_cfg=gate_cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.9,
        strategy_id="md_amr",
        symbol="XRPUSDT",
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        # md_amr uses normalized confidence — pass strategy_confidence with side scope
        strategy_trace={"strategy_confidence": 0.69,
                        "strategy_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )
    aurora_btc = evaluate_low_vol_cost_floor_gate(
        gate_cfg=gate_cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.9,
        strategy_id="aurora",
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=0.69,
        reduce_only=False,
    )

    expected_regime_conf = gate_cfg.thresholds.min_regime_confidence_overrides_by_strategy_symbol[
        "aurora"]["XRPUSDT"]["LOW_VOLATILITY"]
    expected_direction_conf = gate_cfg.thresholds.min_raw_score_overrides_by_strategy_symbol[
        "aurora"]["XRPUSDT"]["LOW_VOLATILITY"]
    expected_md_regime_conf = gate_cfg.thresholds.min_regime_confidence_overrides_by_strategy_symbol[
        "md_amr"]["XRPUSDT"]["LOW_VOLATILITY"]
    expected_md_direction_conf = gate_cfg.thresholds.min_normalized_confidence_overrides_by_strategy_symbol[
        "md_amr"]["XRPUSDT"]["LOW_VOLATILITY"]
    expected_btc_regime_conf = gate_cfg.thresholds.min_regime_confidence_by_regime[
        "LOW_VOLATILITY"]
    expected_btc_direction_conf = gate_cfg.thresholds.min_raw_score_by_regime[
        "LOW_VOLATILITY"]

    assert aurora_xrp.block is False
    assert aurora_xrp.details["resolved_min_regime_confidence"] == expected_regime_conf
    assert aurora_xrp.details["resolved_min_direction_confidence"] == expected_direction_conf
    assert aurora_xrp.details["resolved_min_direction_confidence_source"] == "strategy_symbol_override"
    assert md_amr_xrp.block is False
    assert md_amr_xrp.details["resolved_min_regime_confidence"] == expected_md_regime_conf
    assert md_amr_xrp.details["resolved_min_direction_confidence"] == expected_md_direction_conf
    assert md_amr_xrp.details["resolved_min_direction_confidence_source"] == "strategy_symbol_override"
    assert aurora_btc.block is False
    assert aurora_btc.details["resolved_min_regime_confidence"] == expected_btc_regime_conf
    assert aurora_btc.details["resolved_min_direction_confidence"] == expected_btc_direction_conf


def test_missing_direction_confidence_blocks_fail_closed_even_with_high_regime_confidence() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.99,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["direction_confidence_failure_reason"] == "direction_confidence_missing"
    assert "direction_confidence_missing" in evaluation.details["violations"]


def test_legacy_strategy_confidence_without_side_scope_blocks_fail_closed() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"strategy_confidence": 0.9},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"
    assert evaluation.details["direction_confidence_failure_reason"] == "non_side_aware_direction_confidence"
    assert evaluation.details["direction_confidence_is_side_aware"] is False


def test_explicit_direction_confidence_without_source_blocks_fail_closed() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={"direction_confidence": 0.9,
                        "direction_confidence_side_scope": "BUY"},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["direction_confidence_failure_reason"] == "missing_direction_confidence_source"
    assert "missing_direction_confidence_source" in evaluation.details["violations"]


def test_explicit_direction_confidence_unsupported_source_blocks_fail_closed() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "direction_confidence": 0.9,
            "direction_confidence_source": "mystery_confidence",
            "direction_confidence_side_scope": "BUY",
        },
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["direction_confidence_source"] == "mystery_confidence"
    assert evaluation.details["direction_confidence_failure_reason"] == "unsupported_direction_confidence_source"


def test_explicit_direction_confidence_malformed_value_blocks_fail_closed() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "direction_confidence": "NaN",
            "direction_confidence_source": "strategy_confidence",
            "direction_confidence_side_scope": "BUY",
        },
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is True
    assert evaluation.details["direction_confidence_failure_reason"] == "invalid_direction_confidence_value"


def test_explicit_side_aware_strategy_confidence_allows() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace={
            "direction_confidence": 0.9,
            "direction_confidence_source": "strategy_confidence",
            "direction_confidence_side_scope": "BUY",
        },
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.details["direction_confidence"] == 0.9
    assert evaluation.details["direction_confidence_source"] == "strategy_confidence"
    assert evaluation.details["direction_confidence_side_scope"] == "BUY"


def test_observe_only_direction_confidence_failure_sets_would_block_metadata() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="live",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="BUY",
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=None,
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.gate_mode == "observe_only"
    assert evaluation.details["would_block"] is True
    assert evaluation.details["would_block_direction_confidence"] is True
    assert evaluation.details["reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"


def test_sell_side_resolves_signed_final_score_confidence() -> None:
    evaluation = evaluate_low_vol_cost_floor_gate(
        gate_cfg=_gate_config(direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["final_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        }),
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side="SELL",
        entry_price=100.0,
        target_price=99.70,
        stop_price=100.25,
        strategy_trace={"objective": {"final_score": -0.85, "side": "SELL"}},
        signal_score=None,
        reduce_only=False,
    )

    assert evaluation.block is False
    assert evaluation.details["direction_confidence"] == 0.85
    assert evaluation.details["direction_confidence_source"] == "final_score"
    assert evaluation.details["direction_confidence_side_scope"] == "SELL"


def test_propose_trade_intent_blocks_low_vol_cost_floor_in_testnet() -> None:
    dm = _make_dm(trading_mode="testnet")
    sg = _allow_sg()
    sg.pm_norm_60s = 0.21
    sg.pm_norm_300s = 0.34
    sg.vol_pct_300s = 0.004
    sg.ret_60s = 0.0015
    sg.ret_300s = 0.0045

    with patch(
        "apps.reference.domains.decision_making.core.facade.order_logger.write"
    ) as mock_order_write, patch(
        "apps.reference.domains.decision_making.core.facade.emit_regime_decision_audit"
    ):
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=1,
            price=100.0,
            why_chain=["signal_score=0.9"],
            rid="rid-low-vol-block-1",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
            stop_price=99.0,
            target_price=100.1,
            strategy_trace=None,
            safety_gate_result=sg,
        )

    dm._builder.build_and_emit.assert_not_called()
    dm._emitter.emit_trade_intent_rejected.assert_called_once()
    rejected = dm._emitter.emit_trade_intent_rejected.call_args.kwargs
    assert rejected["reason_code"] == NormalizedRejectReasons.LOW_VOL_COST_FLOOR_BLOCKED
    assert rejected["details"]["required_gross_tp_bps"] == 26.0

    decision_trace_calls = [
        call.kwargs["payload"]
        for call in dm.fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:DECISION_TRACE_EMITTED"
    ]
    assert len(decision_trace_calls) == 1
    assert decision_trace_calls[0]["deny_reason"] == NormalizedRejectReasons.LOW_VOL_COST_FLOOR_BLOCKED
    assert decision_trace_calls[0]["low_vol_cost_floor"]["gate_mode"] == "enforced"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["persistence_context"]["rid"] == "rid-low-vol-block-1"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["persistence_context"]["decision_outcome"] == "DENY"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["confidence_resolution_status"] == "present_passed"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["price_motion_context"]["pm_norm_60s"] == 0.21
    assert decision_trace_calls[0]["low_vol_cost_floor"]["price_motion_context"]["pm_norm_300s"] == 0.34
    assert decision_trace_calls[0]["low_vol_cost_floor"]["price_motion_context"]["vol_pct_300s"] == 0.004
    assert decision_trace_calls[0]["low_vol_cost_floor"]["price_motion_context"]["ret_60s"] == 0.0015
    assert decision_trace_calls[0]["low_vol_cost_floor"]["price_motion_context"]["ret_300s"] == 0.0045
    assert decision_trace_calls[0]["low_vol_cost_floor"]["missing_inputs"]["ret_60s"] is False
    assert decision_trace_calls[0]["low_vol_cost_floor"]["missing_inputs"]["ret_300s"] is False

    metadata = mock_order_write.call_args.args[0]["metadata"]
    assert metadata["reject_reason"] == "LOW_VOL_COST_FLOOR_DENY"
    assert metadata["low_vol_cost_floor"]["evaluation_stage"] == "post_safety_gate"
    assert metadata["low_vol_cost_floor"]["evaluated"] is True
    assert metadata["low_vol_cost_floor"]["threshold_failed"] is True
    assert metadata["low_vol_cost_floor"]["price_motion_context"]["ret_60s"] == 0.0015
    assert metadata["low_vol_cost_floor"]["price_motion_context"]["ret_300s"] == 0.0045
    assert metadata["low_vol_cost_floor"]["persistence_context"]["order_logger_event"] == "DECISION_INTENT_REJECTED"


@pytest.mark.parametrize("trading_mode", ["testnet", "hybrid_live_data_testnet_exec"])
def test_propose_trade_intent_allows_segment_override_in_enforced_runtime_modes(trading_mode: str) -> None:
    dm = _make_dm(trading_mode=trading_mode)
    sg = _allow_sg()
    sg.intent_side = "SHORT"
    sg.signal_score = -0.2

    dm._propose_trade_intent(
        symbol="BTCUSDT",
        side="SELL",
        qty=1,
        price=100.0,
        why_chain=["signal_score=-0.2"],
        rid=f"rid-low-vol-segment-{trading_mode}",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        stop_price=100.25,
        target_price=99.50,
        strategy_trace=None,
        safety_gate_result=sg,
    )

    dm._emitter.emit_trade_intent_rejected.assert_not_called()
    dm._builder.build_and_emit.assert_called_once()
    kwargs = dm._builder.build_and_emit.call_args.kwargs
    low_vol_details = kwargs["strategy_trace"]["low_vol_cost_floor"]

    assert low_vol_details["gate_mode"] == "enforced"
    assert low_vol_details["threshold_failed"] is True
    assert low_vol_details["reason"] == "LOW_VOL_COST_FLOOR_SEGMENT_OVERRIDE_ALLOW"
    assert low_vol_details["nrr062_segment_override_applied"] is True
    assert low_vol_details["nrr062_segment_override_name"] == "LOW_VOL_SHORT_DIRECTION_ONLY_RAW_SIGNAL"
    assert low_vol_details["nrr062_segment_override_no_production"] is True
    assert low_vol_details["original_nrr062_reason"] == "LOW_VOL_COST_FLOOR_BLOCKED"
    assert low_vol_details["original_low_vol_reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"
    assert low_vol_details["selected_source"] == "signal_score"
    assert low_vol_details["selected_scale"] == "raw_signed_score"
    assert low_vol_details["threshold_family"] == "raw_signed_score"
    assert kwargs["sg"].low_vol_cost_floor_details["nrr062_segment_override_applied"] is True
    assert kwargs["sg"].low_vol_cost_floor_details["persistence_context"]["decision_outcome"] == "ALLOW"


def test_propose_trade_intent_prior_safety_deny_attaches_low_vol_geometry_metadata() -> None:
    dm = _make_dm(trading_mode="testnet")
    sg = _allow_sg()
    sg.outcome = "DENY"
    sg.deny_reason = "NRR-026"
    sg.why_short = "trend confirmation failed"

    with patch(
        "apps.reference.domains.decision_making.core.facade.order_logger.write"
    ) as mock_order_write, patch(
        "apps.reference.domains.decision_making.core.facade.emit_regime_decision_audit"
    ), patch(
        "apps.reference.domains.decision_making.core.facade.evaluate_low_vol_cost_floor_gate"
    ) as mock_low_vol_evaluator:
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=1,
            price=100.0,
            why_chain=["geometry_source=why_chain", "signal_score=0.9"],
            rid="rid-prior-gate-low-vol-1",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
            stop_price=99.75,
            target_price=100.30,
            strategy_trace=None,
            safety_gate_result=sg,
        )

    dm._builder.build_and_emit.assert_not_called()
    dm._emitter.emit_trade_intent_rejected.assert_not_called()
    mock_low_vol_evaluator.assert_not_called()

    decision_trace_calls = [
        call.kwargs["payload"]
        for call in dm.fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:DECISION_TRACE_EMITTED"
    ]
    assert len(decision_trace_calls) == 1
    assert decision_trace_calls[0]["deny_reason"] == "NRR-026"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["evaluation_stage"] == "prior_safety_gate"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["evaluated"] is False
    assert decision_trace_calls[0]["low_vol_cost_floor"]["geometry_available"] is True
    assert decision_trace_calls[0]["low_vol_cost_floor"]["geometry_source"] == "facade_inputs"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["entry_price"] == 100.0
    assert decision_trace_calls[0]["low_vol_cost_floor"]["target_price"] == 100.3
    assert decision_trace_calls[0]["low_vol_cost_floor"]["stop_price"] == 99.75
    assert decision_trace_calls[0]["low_vol_cost_floor"]["actual_tp_bps"] == 30.0
    assert decision_trace_calls[0]["low_vol_cost_floor"]["actual_sl_bps"] == 25.0
    assert decision_trace_calls[0]["low_vol_cost_floor"]["side"] == "BUY"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["regime"] == "LOW_VOLATILITY"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["regime_confidence"] == 0.8
    assert decision_trace_calls[0]["low_vol_cost_floor"]["strategy_id"] == "aurora"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["symbol"] == "BTCUSDT"
    assert decision_trace_calls[0]["low_vol_cost_floor"]["persistence_context"]["decision_outcome"] == "DENY"

    metadata = mock_order_write.call_args.args[0]["metadata"]
    assert metadata["reject_reason"] == "SAFETY_GATES_DENY"
    assert metadata["low_vol_cost_floor"]["evaluation_stage"] == "prior_safety_gate"
    assert metadata["low_vol_cost_floor"]["evaluated"] is False
    assert metadata["low_vol_cost_floor"]["geometry_available"] is True
    assert metadata["low_vol_cost_floor"]["geometry_source"] == "facade_inputs"
    assert metadata["low_vol_cost_floor"]["actual_tp_bps"] == 30.0
    assert metadata["low_vol_cost_floor"]["actual_sl_bps"] == 25.0
    assert metadata["low_vol_cost_floor"]["side"] == "BUY"
    assert metadata["low_vol_cost_floor"]["regime"] == "LOW_VOLATILITY"
    assert metadata["low_vol_cost_floor"]["regime_confidence"] == 0.8
    assert metadata["low_vol_cost_floor"]["strategy_id"] == "aurora"
    assert metadata["low_vol_cost_floor"]["symbol"] == "BTCUSDT"
    assert metadata["low_vol_cost_floor"]["geometry_source"] != "geometry_source=why_chain"
    assert metadata["low_vol_cost_floor"]["persistence_context"]["rid"] == "rid-prior-gate-low-vol-1"


def test_propose_trade_intent_prior_safety_deny_non_low_vol_does_not_emit_low_vol_metadata() -> None:
    dm = _make_dm(trading_mode="testnet")
    sg = _allow_sg(regime="TRENDING")
    sg.outcome = "DENY"
    sg.deny_reason = "NRR-026"
    sg.why_short = "trend confirmation failed"

    with patch(
        "apps.reference.domains.decision_making.core.facade.order_logger.write"
    ) as mock_order_write, patch(
        "apps.reference.domains.decision_making.core.facade.emit_regime_decision_audit"
    ), patch(
        "apps.reference.domains.decision_making.core.facade.evaluate_low_vol_cost_floor_gate"
    ) as mock_low_vol_evaluator:
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=1,
            price=100.0,
            why_chain=["geometry_source=why_chain"],
            rid="rid-prior-gate-non-low-vol-1",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
            stop_price=99.75,
            target_price=100.30,
            strategy_trace=None,
            safety_gate_result=sg,
        )

    dm._builder.build_and_emit.assert_not_called()
    dm._emitter.emit_trade_intent_rejected.assert_not_called()
    mock_low_vol_evaluator.assert_not_called()

    decision_trace_calls = [
        call.kwargs["payload"]
        for call in dm.fsm.emit.call_args_list
        if call.args and call.args[0] == "EVT:DECISION_TRACE_EMITTED"
    ]
    assert len(decision_trace_calls) == 1
    assert decision_trace_calls[0]["deny_reason"] == "NRR-026"
    assert "low_vol_cost_floor" not in decision_trace_calls[0]

    metadata = mock_order_write.call_args.args[0]["metadata"]
    assert metadata["reject_reason"] == "SAFETY_GATES_DENY"
    assert metadata["low_vol_cost_floor"] is None


def test_propose_trade_intent_observes_in_live_without_blocking() -> None:
    dm = _make_dm(trading_mode="live")
    sg = _allow_sg()
    sg.pm_norm_60s = 0.11
    sg.vol_pct_300s = 0.002
    sg.ret_60s = 0.0007
    sg.ret_300s = 0.0021

    dm._propose_trade_intent(
        symbol="BTCUSDT",
        side="BUY",
        qty=1,
        price=100.0,
        why_chain=["signal_score=0.9"],
        rid="rid-low-vol-observe-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        stop_price=99.0,
        target_price=100.1,
        strategy_trace=None,
        safety_gate_result=sg,
    )

    dm._emitter.emit_trade_intent_rejected.assert_not_called()
    dm._builder.build_and_emit.assert_called_once()
    kwargs = dm._builder.build_and_emit.call_args.kwargs
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["gate_mode"] == "observe_only"
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["threshold_failed"] is True
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["would_block"] is True
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["persistence_context"]["decision_outcome"] == "ALLOW"
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["confidence_resolution_status"] == "present_passed"
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["price_motion_context"]["pm_norm_60s"] == 0.11
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["price_motion_context"]["vol_pct_300s"] == 0.002
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["price_motion_context"]["ret_60s"] == 0.0007
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["price_motion_context"]["ret_300s"] == 0.0021
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["missing_inputs"]["ret_60s"] is False
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["missing_inputs"]["ret_300s"] is False
    assert kwargs["sg"].low_vol_cost_floor_details["gate_mode"] == "observe_only"
    assert kwargs["sg"].low_vol_cost_floor_details["persistence_context"]["order_logger_event"] == "ORDER_INTENT"


def test_propose_trade_intent_keeps_ret_missing_explicit_when_safety_gate_lacks_returns() -> None:
    dm = _make_dm(trading_mode="live")
    sg = _allow_sg()
    sg.pm_norm_60s = 0.11
    sg.pm_norm_300s = 0.44
    sg.vol_pct_300s = 0.002

    dm._propose_trade_intent(
        symbol="BTCUSDT",
        side="BUY",
        qty=1,
        price=100.0,
        why_chain=["signal_score=0.9"],
        rid="rid-low-vol-ret-missing-1",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_000_999,
        stop_price=99.0,
        target_price=100.1,
        strategy_trace=None,
        safety_gate_result=sg,
    )

    dm._emitter.emit_trade_intent_rejected.assert_not_called()
    dm._builder.build_and_emit.assert_called_once()
    kwargs = dm._builder.build_and_emit.call_args.kwargs
    price_motion_context = kwargs["strategy_trace"]["low_vol_cost_floor"]["price_motion_context"]

    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["gate_mode"] == "observe_only"
    assert price_motion_context["ret_60s"] is None
    assert price_motion_context["ret_300s"] is None
    assert price_motion_context["missing"]["ret_60s"] is True
    assert price_motion_context["missing"]["ret_300s"] is True
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["missing_inputs"]["ret_60s"] is True
    assert kwargs["strategy_trace"]["low_vol_cost_floor"]["missing_inputs"]["ret_300s"] is True


def test_propose_trade_intent_reject_metadata_includes_direction_confidence_details() -> None:
    dm = _make_dm(trading_mode="testnet")
    sg = _allow_sg()
    sg.signal_score = None

    with patch(
        "apps.reference.domains.decision_making.core.facade.order_logger.write"
    ) as mock_order_write, patch(
        "apps.reference.domains.decision_making.core.facade.emit_regime_decision_audit"
    ):
        dm._propose_trade_intent(
            symbol="BTCUSDT",
            side="BUY",
            qty=1,
            price=100.0,
            why_chain=[],
            rid="rid-low-vol-dirconf-1",
            reduce_only=False,
            strategy_id="aurora",
            decision_ts_ms=1_700_000_000_999,
            stop_price=99.75,
            target_price=100.30,
            strategy_trace=None,
            safety_gate_result=sg,
        )

    rejected = dm._emitter.emit_trade_intent_rejected.call_args.kwargs
    assert rejected["reason_code"] == NormalizedRejectReasons.LOW_VOL_COST_FLOOR_BLOCKED
    assert rejected["details"]["reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"
    assert rejected["details"]["direction_confidence_failure_reason"] == "direction_confidence_missing"

    metadata = mock_order_write.call_args.args[0]["metadata"]
    assert metadata["low_vol_cost_floor"]["reason"] == "LOW_VOL_DIRECTION_CONFIDENCE_BLOCKED"
    assert metadata["low_vol_cost_floor"]["direction_confidence_failure_reason"] == "direction_confidence_missing"
