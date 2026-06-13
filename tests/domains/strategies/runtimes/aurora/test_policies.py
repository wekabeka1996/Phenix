from __future__ import annotations

from decimal import Decimal

from apps.reference.domains.strategies.runtimes.aurora.policies import (
    HoldingPeriodPolicy,
    HoldingPeriodSnapshot,
    RegimeInertiaPolicy,
    RegimeInertiaSnapshot,
    RegimeTpslCalculator,
)


def test_holding_period_policy_uses_monotonic_duration_snapshot() -> None:
    decision = HoldingPeriodPolicy().evaluate(
        HoldingPeriodSnapshot(
            enabled=True,
            apply_to_flips=True,
            is_flip=False,
            entry_timestamp=100.0,
            now_monotonic=125.0,
            min_duration_sec=60.0,
            score=Decimal("0.2"),
            emergency_threshold=0.9,
        )
    )

    assert decision.suppress is True
    assert decision.reason_code == "HOLDING_PERIOD_ACTIVE"
    assert decision.time_in_position_sec == 25.0


def test_regime_inertia_immediate_risk_off_without_state_mutation() -> None:
    severity = {"FLAT_LOW": 1, "FLAT_HIGH": 3}
    policy = RegimeInertiaPolicy(lambda regime: severity.get(regime or "", 0))

    result = policy.apply(
        RegimeInertiaSnapshot(
            raw_previous="FLAT_LOW",
            effective_previous="FLAT_LOW",
            raw_candidate="FLAT_HIGH",
            raw_change_ts=10.0,
            now_monotonic=12.0,
            anti_churn_enabled=True,
            confirm_window_sec=300.0,
            same_severity_confirm_window_sec=60.0,
            immediate_risk_off=True,
        )
    )

    assert result.raw == "FLAT_HIGH"
    assert result.effective == "FLAT_HIGH"
    assert result.raw_change_ts == 12.0


def test_regime_tpsl_calculator_prefers_effective_regime_when_anti_churn_enabled() -> None:
    result = RegimeTpslCalculator().select_regime(
        raw_regime="FLAT_LOW",
        effective_regime="FLAT_NORMAL",
        anti_churn_enabled=True,
    )

    assert result.regime_used == "FLAT_NORMAL"
    assert result.reason == "effective_regime"
