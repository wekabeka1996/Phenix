"""Negative and contract tests for the LOW_VOL_COST_FLOOR direction-confidence
scale-separation contract.

Each test verifies one of:
  1. raw_signed_score sources routed to min_raw_score threshold family
  2. normalized_confidence sources routed to min_normalized_confidence threshold family
  3. missing sources fail closed (cannot be selected)
  4. judge_confidence rejected when live_producer_required=True and no proof in trace
  5. judge_confidence allowed when live_producer_required=False
  6. reject trace explicitly carries threshold_family and normalization_applied
"""
from __future__ import annotations

import pytest

from apps.reference.config.domains import decision_making as domain_dm
from apps.reference.domains.decision_making.gates.low_vol_cost_floor import (
    evaluate_low_vol_cost_floor_gate,
)


def _base_thresholds(**overrides) -> dict:
    payload = {
        "target_net_fee_multiple": 2.0,
        "min_tp_fee_coverage": 3.0,
        "min_rr": 1.2,
        "min_regime_confidence_by_regime": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39},
        "min_direction_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.30},
    }
    payload.update(overrides)
    return payload


def _make_cfg(*, direction_confidence: dict, thresholds: dict | None = None) -> domain_dm.LowVolCostFloorGateConfig:
    return domain_dm.LowVolCostFloorGateConfig.model_validate({
        "enabled": True,
        "enforce_in_modes": ["testnet"],
        "observe_only_in_modes": ["live", "production"],
        "regimes": ["LOW_VOLATILITY"],
        "fee": {"open_fee_bps": 4.0, "close_fee_bps": 4.0, "fee_source": "explicit_config"},
        "slippage": {"buffer_bps": 2.0, "source": "explicit_config"},
        "thresholds": thresholds or _base_thresholds(),
        "direction_confidence": direction_confidence,
        "geometry": {"require_tpsl": True, "missing_policy": "fail_closed"},
    })


def _evaluate(cfg, *, signal_score=None, strategy_trace=None, side="BUY"):
    return evaluate_low_vol_cost_floor_gate(
        gate_cfg=cfg,
        trading_mode="testnet",
        regime="LOW_VOLATILITY",
        regime_confidence=0.8,
        side=side,
        entry_price=100.0,
        target_price=100.30,
        stop_price=99.75,
        strategy_trace=strategy_trace,
        signal_score=signal_score,
        reduce_only=False,
    )


# ---------------------------------------------------------------------------
# Test 1: raw_signed_score source is compared to min_raw_score threshold, NOT
# to min_normalized_confidence threshold.
# ---------------------------------------------------------------------------

def test_raw_score_uses_raw_threshold_not_normalized() -> None:
    """signal_score=0.4 blocked by min_raw_score=0.5, allowed by min_normalized=0.3.

    Proves the gate uses the raw-score threshold family for raw_signed_score sources.
    """
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_raw_score_by_regime={"DEFAULT": 0.5, "LOW_VOLATILITY": 0.5},
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.3, "LOW_VOLATILITY": 0.3},
        ),
    )

    result = _evaluate(cfg, signal_score=0.4)

    assert result.block is True, "Should block: abs(0.4) < raw_threshold(0.5)"
    assert "direction_confidence_below_threshold" in result.details["violations"]
    assert result.details["direction_confidence_threshold_family"] == "raw_signed_score"
    assert result.details["direction_confidence_context"]["threshold_family"] == "raw_signed_score"
    assert result.details["direction_confidence_context"]["normalization_applied"] is True
    assert result.details["resolved_min_direction_confidence"] == pytest.approx(
        0.5)


def test_raw_score_above_raw_threshold_passes_even_if_below_normalized() -> None:
    """signal_score=0.6 passes min_raw_score=0.5 but would fail min_normalized=0.7.

    Proves the gate does NOT apply the normalized threshold to raw sources.
    """
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_raw_score_by_regime={"DEFAULT": 0.5, "LOW_VOLATILITY": 0.5},
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.7, "LOW_VOLATILITY": 0.7},
        ),
    )

    result = _evaluate(cfg, signal_score=0.6)

    assert "direction_confidence_below_threshold" not in result.details.get(
        "violations", [])
    assert result.details["direction_confidence_threshold_family"] == "raw_signed_score"
    assert result.details["resolved_min_direction_confidence"] == pytest.approx(
        0.5)


# ---------------------------------------------------------------------------
# Test 2: normalized_confidence source is compared to min_normalized_confidence
# threshold, NOT to min_raw_score threshold.
# ---------------------------------------------------------------------------

def test_normalized_confidence_uses_normalized_threshold_not_raw() -> None:
    """strategy_confidence=0.4 blocked by min_normalized=0.5, allowed by min_raw=0.3.

    Proves the gate uses the normalized threshold family for normalized sources.
    """
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_raw_score_by_regime={"DEFAULT": 0.3, "LOW_VOLATILITY": 0.3},
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.5, "LOW_VOLATILITY": 0.5},
        ),
    )

    result = _evaluate(
        cfg,
        strategy_trace={"strategy_confidence": 0.4,
                        "strategy_confidence_side_scope": "BUY"},
    )

    assert result.block is True, "Should block: 0.4 < normalized_threshold(0.5)"
    assert "direction_confidence_below_threshold" in result.details["violations"]
    assert result.details["direction_confidence_threshold_family"] == "normalized_confidence"
    assert result.details["direction_confidence_context"]["threshold_family"] == "normalized_confidence"
    assert result.details["direction_confidence_context"]["normalization_applied"] is False
    assert result.details["resolved_min_direction_confidence"] == pytest.approx(
        0.5)


def test_normalized_above_normalized_threshold_passes_even_if_below_raw() -> None:
    """strategy_confidence=0.6 passes min_normalized=0.5 but would fail min_raw=0.7."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_raw_score_by_regime={"DEFAULT": 0.7, "LOW_VOLATILITY": 0.7},
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.5, "LOW_VOLATILITY": 0.5},
        ),
    )

    result = _evaluate(
        cfg,
        strategy_trace={"strategy_confidence": 0.6,
                        "strategy_confidence_side_scope": "BUY"},
    )

    assert "direction_confidence_below_threshold" not in result.details.get(
        "violations", [])
    assert result.details["direction_confidence_threshold_family"] == "normalized_confidence"
    assert result.details["resolved_min_direction_confidence"] == pytest.approx(
        0.5)


# ---------------------------------------------------------------------------
# Test 3: missing sources fail closed — cannot be selected.
# ---------------------------------------------------------------------------

def test_missing_all_sources_fails_closed() -> None:
    """No signal_score, no strategy_confidence → direction_confidence_missing violation."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
    )

    result = _evaluate(cfg, signal_score=None, strategy_trace=None)

    assert result.block is True
    assert "direction_confidence_missing" in result.details["violations"]
    assert result.details["direction_confidence"] is None
    assert result.details["direction_confidence_context"]["present"] is False
    # missing_source_list must enumerate what was tried and found absent
    assert "signal_score" in result.details["missing_source_list"]
    assert "strategy_confidence" in result.details["missing_source_list"]


def test_missing_source_cannot_be_selected_when_only_other_source_has_value() -> None:
    """Only signal_score=0.8 in allowed, strategy_confidence not in allowed.

    strategy_confidence in trace must not be selected because it is not in any source family.
    """
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
    )

    result = _evaluate(
        cfg,
        signal_score=None,
        strategy_trace={"strategy_confidence": 0.9,
                        "strategy_confidence_side_scope": "BUY"},
    )

    # signal_score not provided, strategy_confidence not in allowed families → missing
    assert result.block is True
    assert "direction_confidence_missing" in result.details["violations"]


# ---------------------------------------------------------------------------
# Test 4: judge_confidence requires live producer flag when configured.
# ---------------------------------------------------------------------------

def test_judge_confidence_rejected_when_live_producer_required_and_no_proof() -> None:
    """judge_confidence in trace but no judge_confidence_live_producer_proof → blocked."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["judge_confidence"],
            "judge_confidence_live_producer_required": True,
            "missing_policy": "fail_closed",
        },
    )

    result = _evaluate(
        cfg,
        strategy_trace={
            "judge_confidence": 0.9,
            "judge_confidence_side_scope": "BUY",
            # no judge_confidence_live_producer_proof key
        },
    )

    assert result.block is True
    assert "judge_confidence_no_live_producer" in result.details["violations"]
    assert result.details["direction_confidence"] is None


def test_judge_confidence_rejected_when_live_producer_required_and_proof_is_false() -> None:
    """judge_confidence with proof=False also fails."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["judge_confidence"],
            "judge_confidence_live_producer_required": True,
            "missing_policy": "fail_closed",
        },
    )

    result = _evaluate(
        cfg,
        strategy_trace={
            "judge_confidence": 0.9,
            "judge_confidence_side_scope": "BUY",
            "judge_confidence_live_producer_proof": False,
        },
    )

    assert result.block is True
    assert "judge_confidence_no_live_producer" in result.details["violations"]


# ---------------------------------------------------------------------------
# Test 5: judge_confidence allowed when live_producer_required=False.
# ---------------------------------------------------------------------------

def test_judge_confidence_allowed_when_live_producer_required_is_false() -> None:
    """judge_confidence accepted when flag is False, regardless of proof field."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["judge_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.5, "LOW_VOLATILITY": 0.5},
        ),
    )

    result = _evaluate(
        cfg,
        strategy_trace={
            "judge_confidence": 0.9,
            "judge_confidence_side_scope": "BUY",
            # no proof field at all
        },
    )

    assert "judge_confidence_no_live_producer" not in result.details.get(
        "violations", [])
    assert result.details["direction_confidence_source"] == "judge_confidence"
    assert result.details["direction_confidence_threshold_family"] == "normalized_confidence"


def test_judge_confidence_allowed_with_live_producer_proof_true() -> None:
    """judge_confidence accepted when flag=True AND proof=True in trace."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["judge_confidence"],
            "judge_confidence_live_producer_required": True,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.5, "LOW_VOLATILITY": 0.5},
        ),
    )

    result = _evaluate(
        cfg,
        strategy_trace={
            "judge_confidence": 0.9,
            "judge_confidence_side_scope": "BUY",
            "judge_confidence_live_producer_proof": True,
        },
    )

    assert "judge_confidence_no_live_producer" not in result.details.get(
        "violations", [])
    assert result.details["direction_confidence_source"] == "judge_confidence"
    assert result.details["direction_confidence"] == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Test 6: reject trace explicitly carries threshold_family and normalization_applied.
# ---------------------------------------------------------------------------

def test_reject_trace_includes_threshold_family_and_normalization_for_raw_source() -> None:
    """Blocked raw_signed_score result has threshold_family and normalization_applied in details."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_raw_score_by_regime={"DEFAULT": 0.8, "LOW_VOLATILITY": 0.8},
        ),
    )

    result = _evaluate(cfg, signal_score=0.5)

    assert result.block is True
    # Top-level details field
    assert result.details.get(
        "direction_confidence_threshold_family") == "raw_signed_score"
    # direction_confidence_context sub-dict
    ctx = result.details["direction_confidence_context"]
    assert ctx["threshold_family"] == "raw_signed_score"
    assert ctx["normalization_applied"] is True


def test_reject_trace_includes_threshold_family_and_normalization_for_normalized_source() -> None:
    """Blocked normalized_confidence result has threshold_family in details."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
        thresholds=_base_thresholds(
            min_normalized_confidence_by_regime={
                "DEFAULT": 0.8, "LOW_VOLATILITY": 0.8},
        ),
    )

    result = _evaluate(
        cfg,
        strategy_trace={"strategy_confidence": 0.5,
                        "strategy_confidence_side_scope": "BUY"},
    )

    assert result.block is True
    assert result.details.get(
        "direction_confidence_threshold_family") == "normalized_confidence"
    ctx = result.details["direction_confidence_context"]
    assert ctx["threshold_family"] == "normalized_confidence"
    assert ctx["normalization_applied"] is False


def test_missing_source_list_populated_in_reject_trace() -> None:
    """missing_source_list in details enumerates every configured source that was absent."""
    cfg = _make_cfg(
        direction_confidence={
            "required": True,
            "raw_signed_score_sources": ["signal_score", "final_score"],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        },
    )

    result = _evaluate(cfg, signal_score=None, strategy_trace=None)

    assert result.block is True
    missing = result.details["missing_source_list"]
    assert set(missing) == {"signal_score",
                            "final_score", "strategy_confidence"}


# ---------------------------------------------------------------------------
# Config model contract tests.
# ---------------------------------------------------------------------------

def test_both_source_families_empty_raises_validation_error() -> None:
    """Config with no sources at all is rejected at model validation time."""
    with pytest.raises(Exception, match="at least one source family"):
        domain_dm.LowVolDirectionConfidenceConfig.model_validate({
            "required": True,
            "raw_signed_score_sources": [],
            "normalized_confidence_sources": [],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        })


def test_wrong_source_in_raw_family_raises_validation_error() -> None:
    """strategy_confidence in raw_signed_score_sources is rejected at model validation."""
    with pytest.raises(Exception):
        domain_dm.LowVolDirectionConfidenceConfig.model_validate({
            "required": True,
            # wrong family
            "raw_signed_score_sources": ["strategy_confidence"],
            "normalized_confidence_sources": ["strategy_confidence"],
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        })


def test_wrong_source_in_normalized_family_raises_validation_error() -> None:
    """signal_score in normalized_confidence_sources is rejected at model validation."""
    with pytest.raises(Exception):
        domain_dm.LowVolDirectionConfidenceConfig.model_validate({
            "required": True,
            "raw_signed_score_sources": ["signal_score"],
            "normalized_confidence_sources": ["signal_score"],  # wrong family
            "judge_confidence_live_producer_required": False,
            "missing_policy": "fail_closed",
        })


def test_migration_alias_populates_both_new_threshold_families() -> None:
    """When only min_direction_confidence_by_regime is set, both split families inherit its values."""
    cfg = domain_dm.LowVolCostFloorThresholdsConfig.model_validate({
        "target_net_fee_multiple": 2.0,
        "min_tp_fee_coverage": 3.0,
        "min_rr": 1.2,
        "min_regime_confidence_by_regime": {"DEFAULT": 0.45, "LOW_VOLATILITY": 0.39},
        "min_direction_confidence_by_regime": {"DEFAULT": 0.55, "LOW_VOLATILITY": 0.25},
        # New split fields intentionally absent — migration alias should populate them.
    })

    assert cfg.min_raw_score_by_regime == {
        "DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}
    assert cfg.min_normalized_confidence_by_regime == {
        "DEFAULT": 0.55, "LOW_VOLATILITY": 0.25}
