from __future__ import annotations

from apps.reference.domains.strategies.runtimes.md_amr.regime_allowlist import (
    MDAMRRegimeAllowlistEvaluator,
)


def test_md_amr_regime_allowlist_expands_flat_market_aliases() -> None:
    evaluator = MDAMRRegimeAllowlistEvaluator()

    evaluation = evaluator.evaluate(
        current_regime="LOW_FLAT",
        allowed_regimes=["LOW_VOLATILITY"],
    )

    assert evaluation.current_regime == "FLAT_LOW"
    assert evaluation.effective_allowed_regimes == ["LOW_VOLATILITY", "FLAT_LOW"]
    assert evaluation.allowed is True
