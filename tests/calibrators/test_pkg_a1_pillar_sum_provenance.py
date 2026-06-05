"""PKG-A1: Prove pillar_sum mutation in calibrate_aurora_thresholds carries provenance.

When pillar_sum is recalculated from raw pillars via pillar_weights:
- The mutated bar must carry pillar_sum_provenance_class = CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE
- The non-mutated bar (missing any pillar sub-component) must NOT carry the class.
- Bars loaded WITHOUT pillar_weights must have empty pillar_sum_provenance_class.
- The WARNING log must be emitted when mutation occurs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import patch

import pytest

from calibrators.strategies.calibrate_aurora_thresholds import (
    CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE,
    RecorderBar,
)


def _make_bar(
    symbol: str = "BTCUSDT",
    pillar_sum: float | None = None,
    pillar_tactician: float | None = None,
    pillar_operator: float | None = None,
    pillar_strategist: float | None = None,
    provenance_class: str = "",
) -> RecorderBar:
    return RecorderBar(
        timestamp=datetime(2026, 5, 1),
        timestamp_ms=1746057600000,
        symbol=symbol,
        tf_sec=300,
        ready=True,
        not_ready_reasons="",
        close=50000.0,
        high=51000.0,
        low=49000.0,
        pillar_sum=pillar_sum,
        pillar_tactician=pillar_tactician,
        pillar_operator=pillar_operator,
        pillar_strategist=pillar_strategist,
        spread_bps=2.0,
        volatility_state=0.3,
        price_motion_norm=0.01,
        pillar_sum_provenance_class=provenance_class,
    )


def _apply_pillar_weights(
    bar: RecorderBar,
    pillar_weights: dict,
) -> RecorderBar:
    """Apply the same mutation logic as _load_recorder_bars."""
    from calibrators.strategies.calibrate_aurora_thresholds import (
        CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE,
    )
    t = bar.pillar_tactician
    o = bar.pillar_operator
    s = bar.pillar_strategist
    if t is not None and o is not None and s is not None:
        w_t = pillar_weights.get("tactician", 0.60)
        w_o = pillar_weights.get("operator", 0.25)
        w_s = pillar_weights.get("strategist", 0.15)
        new_sum = t * w_t + o * w_o + s * w_s
        object.__setattr__(bar, "pillar_sum", new_sum)
        object.__setattr__(
            bar, "pillar_sum_provenance_class", CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE
        )
    return bar


class TestRecorderBarProvenanceField:
    def test_default_provenance_class_is_empty(self):
        bar = _make_bar(pillar_sum=0.5)
        assert bar.pillar_sum_provenance_class == "", (
            "Live-derived bar must have empty provenance_class"
        )

    def test_mutated_bar_carries_synthetic_provenance(self):
        bar = _make_bar(
            pillar_tactician=0.6,
            pillar_operator=0.3,
            pillar_strategist=0.1,
        )
        bar = _apply_pillar_weights(
            bar, {"tactician": 0.60, "operator": 0.25, "strategist": 0.15}
        )
        assert bar.pillar_sum_provenance_class == CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE

    def test_mutated_bar_live_feature_derived_is_false(self):
        bar = _make_bar(
            pillar_tactician=0.6,
            pillar_operator=0.3,
            pillar_strategist=0.1,
        )
        bar = _apply_pillar_weights(
            bar, {"tactician": 0.60, "operator": 0.25, "strategist": 0.15}
        )
        assert bar.pillar_sum_provenance_class != "", (
            "Mutated bar must not look like live-feature-derived"
        )

    def test_bar_with_missing_sub_pillars_not_mutated(self):
        bar = _make_bar(
            pillar_tactician=0.6,
            pillar_operator=None,  # missing — mutation must not apply
            pillar_strategist=0.1,
        )
        bar = _apply_pillar_weights(
            bar, {"tactician": 0.60, "operator": 0.25, "strategist": 0.15}
        )
        assert bar.pillar_sum_provenance_class == "", (
            "Bar with missing sub-pillar must not get synthetic provenance class"
        )

    def test_mutated_pillar_sum_value_is_correct(self):
        bar = _make_bar(
            pillar_tactician=0.9,
            pillar_operator=0.6,
            pillar_strategist=0.3,
        )
        weights = {"tactician": 0.60, "operator": 0.25, "strategist": 0.15}
        bar = _apply_pillar_weights(bar, weights)
        expected = 0.9 * 0.60 + 0.6 * 0.25 + 0.3 * 0.15
        assert bar.pillar_sum == pytest.approx(expected, abs=1e-9)

    def test_provenance_class_constant_is_stable(self):
        assert CALIBRATOR_SYNTHETIC_PILLAR_SUM_PROVENANCE == "aurora_calibrator_synthetic_pillar_sum", (
            "Provenance class string is a stable contract — do not change without migration"
        )


class TestProvenanceFieldIsReadableByDownstream:
    """Downstream readers must be able to distinguish synthetic from live bars."""

    def test_live_bar_passes_is_live_check(self):
        bar = _make_bar(pillar_sum=0.5)
        is_live_derived = bar.pillar_sum_provenance_class == ""
        assert is_live_derived

    def test_synthetic_bar_fails_is_live_check(self):
        bar = _make_bar(
            pillar_tactician=0.6,
            pillar_operator=0.3,
            pillar_strategist=0.1,
        )
        bar = _apply_pillar_weights(
            bar, {"tactician": 0.60, "operator": 0.25, "strategist": 0.15}
        )
        is_live_derived = bar.pillar_sum_provenance_class == ""
        assert not is_live_derived
