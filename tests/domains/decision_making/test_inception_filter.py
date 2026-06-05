import pytest
from decimal import Decimal
from apps.reference.domains.decision_making.gates.inception_filter import check_inception_eligibility, InceptionResult

class MockConfig:
    def __init__(self, enabled=True, action="micro_size", micro_size_fraction=0.25):
        self.enabled = enabled
        self.action = action
        self.micro_size_fraction = micro_size_fraction

def test_disabled_returns_not_eligible():
    cfg = MockConfig(enabled=False)
    res = check_inception_eligibility(
        "HIGH_VOL", "UNCERTAIN", ["HIGH_VOL"], Decimal("0.8"), Decimal("0.5"), "NORMAL", cfg
    )
    assert not res.eligible
    assert res.micro_fraction == 1.0
    assert res.why == "inception_disabled"

def test_rescue_scenario_eligible():
    cfg = MockConfig(enabled=True, action="micro_size", micro_size_fraction=0.25)
    res = check_inception_eligibility(
        raw_regime="HIGH_VOL",
        stable_regime="UNCERTAIN",
        allowed_regimes=["HIGH_VOL", "TREND_UP"],
        signal_score=Decimal("0.8"),
        signal_threshold_for_raw=Decimal("0.5"),
        stress_state="NORMAL",
        config=cfg
    )
    assert res.eligible
    assert res.micro_fraction == 0.25
    assert res.why == "inception:micro_0.25"

def test_both_allowed_not_eligible():
    cfg = MockConfig(enabled=True)
    res = check_inception_eligibility(
        raw_regime="HIGH_VOL",
        stable_regime="TREND_UP",
        allowed_regimes=["HIGH_VOL", "TREND_UP"],
        signal_score=Decimal("0.8"),
        signal_threshold_for_raw=Decimal("0.5"),
        stress_state="NORMAL",
        config=cfg
    )
    assert not res.eligible
    assert res.why == "stable_already_allowed"

def test_raw_not_in_allowed_not_eligible():
    cfg = MockConfig(enabled=True)
    res = check_inception_eligibility(
        raw_regime="MEAN_REVERSION",
        stable_regime="UNCERTAIN",
        allowed_regimes=["HIGH_VOL", "TREND_UP"],
        signal_score=Decimal("0.8"),
        signal_threshold_for_raw=Decimal("0.5"),
        stress_state="NORMAL",
        config=cfg
    )
    assert not res.eligible
    assert res.why == "raw_not_allowed"

def test_extreme_stress_blocks():
    cfg = MockConfig(enabled=True)
    res = check_inception_eligibility(
        raw_regime="HIGH_VOL",
        stable_regime="UNCERTAIN",
        allowed_regimes=["HIGH_VOL"],
        signal_score=Decimal("0.8"),
        signal_threshold_for_raw=Decimal("0.5"),
        stress_state="EXTREME",
        config=cfg
    )
    assert not res.eligible
    assert res.why == "extreme_stress"

def test_score_below_threshold_blocks():
    cfg = MockConfig(enabled=True)
    res = check_inception_eligibility(
        raw_regime="HIGH_VOL",
        stable_regime="UNCERTAIN",
        allowed_regimes=["HIGH_VOL"],
        signal_score=Decimal("0.4"),
        signal_threshold_for_raw=Decimal("0.5"),
        stress_state="NORMAL",
        config=cfg
    )
    assert not res.eligible
    assert res.why == "score_below_raw_threshold"

def test_micro_fraction_applied():
    cfg = MockConfig(enabled=True, action="micro_size", micro_size_fraction=0.1)
    res = check_inception_eligibility(
        raw_regime="HIGH_VOL",
        stable_regime="UNCERTAIN",
        allowed_regimes=["HIGH_VOL"],
        signal_score=Decimal("0.8"),
        signal_threshold_for_raw=Decimal("0.5"),
        stress_state="NORMAL",
        config=cfg
    )
    assert res.eligible
    assert res.micro_fraction == 0.1
