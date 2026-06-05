from tools.calibration.bootstrap_stability import (
    bootstrap_expectancy_ci,
    stability_verdict,
)


def test_bootstrap_ci_returns_positive_lower_for_consistent_positive_series() -> None:
    ci = bootstrap_expectancy_ci([0.02, 0.03, 0.01, 0.025, 0.02], draws=300, seed=11)
    verdict = stability_verdict(ci)
    assert verdict["lower"] > 0
    assert verdict["stable"] is True


def test_bootstrap_ci_marks_wide_or_negative_series_unstable() -> None:
    ci = bootstrap_expectancy_ci([0.05, -0.08, 0.12, -0.10, 0.02], draws=300, seed=11)
    verdict = stability_verdict(ci)
    assert verdict["stable"] is False
