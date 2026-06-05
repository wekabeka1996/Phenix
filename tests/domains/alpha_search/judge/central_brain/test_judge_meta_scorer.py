from __future__ import annotations

from copy import deepcopy

from apps.reference.domains.alpha_search.judge.central_brain.contracts import (
    ExecutionReadinessBlock,
    HistoricalSurfaceEvidenceBlock,
    MarketContext,
    PortfolioContextBlock,
    RiskContextBlock,
)
from apps.reference.domains.alpha_search.judge.central_brain.envelope_builder import (
    build_judge_evidence_envelope,
)
from apps.reference.domains.alpha_search.judge.central_brain.meta_scorer import (
    score_judge_envelope,
)
from apps.reference.domains.regime_detector.context_envelope import (
    build_regime_context_envelope,
)
from apps.reference.domains.strategies.runtimes.aurora.native_expert_adapter import (
    build_aurora_expert_output,
)
from apps.reference.domains.strategies.runtimes.md_amr.native_expert_adapter import (
    build_md_amr_expert_output,
)
from apps.reference.domains.strategies.runtimes.mean_reversion.native_expert_adapter import (
    build_mean_reversion_expert_output,
)

from tests.domains.alpha_search.judge.central_brain.test_judge_policy_verdict_contract import (
    valid_config,
)


def _aurora(side: str = "BUY", confidence: float = 0.80):
    decision_score = confidence if side == "BUY" else -confidence
    return build_aurora_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1000,
            "side": side,
            "strategy_confidence": confidence,
            "features": {"ts_ms": 990, "obi": 0.2, "tfi": 0.1},
            "scoring": {"decision_score": decision_score, "pillar_sum": 0.4},
            "rid": "rid-a",
        },
        now_ms=1000,
    )


def _mr(side: str = "BUY", confidence: float = 0.80):
    return build_mean_reversion_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1000,
            "side": side,
            "confidence": confidence,
            "rsi": 31.0,
            "bb": {"pct_b": 0.1, "width": 0.04, "upper": 110.0, "mid": 100.0, "lower": 90.0},
            "volatility": {"atr": 12.0},
            "price_ctx": {"target_price": 103.0, "stop_price": 96.0},
            "rid": "rid-mr",
        },
        now_ms=1000,
    )


def _md(side: str = "BUY", confidence: float = 0.80):
    return build_md_amr_expert_output(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1000,
            "side": side,
            "intent_kind": "ENTRY",
            "conf_ratio": confidence,
            "trace": {"setup_quality": 0.8, "progress_state": "forming"},
            "rid": "rid-md",
        },
        now_ms=1000,
    )


def _regime(*, stale: bool = False):
    decision_ts = 1000 if not stale else 50_000
    return build_regime_context_envelope(
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1000,
            "regime": "LOW_VOLATILITY",
            "confidence": 0.8,
            "basis_tf_sec": 60,
            "rid": "rid-regime",
        },
        decision_ts_ms=decision_ts,
        freshness_threshold_ms=30_000,
    )


def _base_kwargs(**overrides):
    kwargs = {
        "symbol": "BTCUSDT",
        "created_ts_ms": 1000,
        "decision_id": "decision-1",
        "rid": "rid-1",
        "cycle_key": "cycle-1",
        "market_context": MarketContext(
            symbol="BTCUSDT",
            ts_ms=1000,
            data_freshness_state="FRESH",
            source_refs={"fixture": "market"},
        ),
        "regime_context": _regime(),
        "risk_context": RiskContextBlock(
            present=True,
            exposure_state="flat",
            risk_state="ok",
        ),
        "portfolio_context": PortfolioContextBlock(
            present=True,
            position_state="flat",
            symbol_exposure=0.0,
        ),
        "execution_readiness": ExecutionReadinessBlock(
            present=True,
            readiness_state="ready",
            blocking_reasons=[],
        ),
    }
    kwargs.update(overrides)
    return kwargs


def _envelope(**overrides):
    return build_judge_evidence_envelope(**_base_kwargs(**overrides))


def test_agree_long_with_sufficient_confidence_opens_long_shadow_only():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    assert verdict.verdict == "OPEN_LONG"
    assert verdict.authority_status == "shadow_only"
    assert verdict.applied is False


def test_agree_short_with_sufficient_confidence_opens_short_shadow_only():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("SELL"), mean_reversion=_mr("SELL")),
        valid_config(),
    )
    assert verdict.verdict == "OPEN_SHORT"
    assert verdict.authority_status == "shadow_only"
    assert verdict.applied is False


def test_disagree_lowers_confidence_and_never_opens():
    agree = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    disagree = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("SELL")),
        valid_config(),
    )
    assert disagree.confidence < agree.confidence
    assert disagree.verdict in {"NO_ENTRY", "UNKNOWN", "SUPPRESS"}


def test_single_expert_lower_confidence_than_multi_expert_agreement():
    single = score_judge_envelope(_envelope(aurora=_aurora("BUY")), valid_config())
    multi = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    assert single.confidence < multi.confidence


def test_no_experts_unknown():
    verdict = score_judge_envelope(_envelope(), valid_config())
    assert verdict.verdict == "UNKNOWN"
    assert "hard_unknown:no_strategy_experts" in verdict.rationale.blocking_reasons


def test_none_unknown_only_never_opens():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("NONE"), mean_reversion=_mr("UNKNOWN")),
        valid_config(),
    )
    assert verdict.verdict != "OPEN_LONG"
    assert verdict.verdict != "OPEN_SHORT"


def test_missing_regime_context_can_trigger_hard_unknown():
    config = valid_config().model_copy(
        update={
            "hard_unknown_conditions": valid_config().hard_unknown_conditions.model_copy(
                update={"missing_regime_context": True}
            )
        }
    )
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY"), regime_context=None),
        config,
    )
    assert verdict.verdict == "UNKNOWN"
    assert "hard_unknown:missing_regime_context" in verdict.rationale.blocking_reasons


def test_stale_regime_creates_freshness_warning_and_penalty():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY"), regime_context=_regime(stale=True)),
        valid_config(),
    )
    assert "regime_context:STALE" in verdict.rationale.freshness_warnings
    assert verdict.score_components.freshness_penalty > 0


def test_missing_risk_portfolio_execution_readiness_penalized():
    full = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    missing = score_judge_envelope(
        build_judge_evidence_envelope(
            symbol="BTCUSDT",
            created_ts_ms=1000,
            market_context=_base_kwargs()["market_context"],
            regime_context=_regime(),
            aurora=_aurora("BUY"),
            mean_reversion=_mr("BUY"),
        ),
        valid_config(),
    )
    assert missing.confidence < full.confidence
    assert "risk_context" in missing.rationale.missing_evidence
    assert "portfolio_context" in missing.rationale.missing_evidence
    assert "execution_readiness" in missing.rationale.missing_evidence


def test_positive_historical_surface_can_boost_within_configured_bound():
    no_surface = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    with_surface = score_judge_envelope(
        _envelope(
            aurora=_aurora("BUY"),
            mean_reversion=_mr("BUY"),
            historical_surface_evidence=HistoricalSurfaceEvidenceBlock(
                present=True,
                surface_key="surface-1",
                sample_count=100,
                expectancy_net=0.02,
                confidence_interval_low=0.01,
                confidence_interval_high=0.03,
            ),
        ),
        valid_config(),
    )
    assert with_surface.score_components.historical_surface_component == (
        valid_config().historical_surface_weight
    )
    assert with_surface.confidence >= no_surface.confidence


def test_missing_historical_surface_gives_no_hidden_boost():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    assert verdict.score_components.historical_surface_component == 0.0


def test_confidence_clamps_to_configured_bounds():
    config = valid_config().model_copy(
        update={
            "max_confidence": 0.5,
            "verdict_thresholds": valid_config().verdict_thresholds.model_copy(
                update={
                    "open_long_min_confidence": 0.5,
                    "open_short_min_confidence": 0.5,
                }
            ),
        }
    )
    verdict = score_judge_envelope(
        _envelope(
            aurora=_aurora("BUY", 1.0),
            mean_reversion=_mr("BUY", 1.0),
            md_amr=_md("BUY", 1.0),
            historical_surface_evidence=HistoricalSurfaceEvidenceBlock(
                present=True,
                surface_key="surface-1",
                sample_count=100,
                expectancy_net=0.02,
                confidence_interval_low=0.01,
                confidence_interval_high=0.03,
            ),
        ),
        config,
    )
    assert verdict.confidence == 0.5


def test_confidence_band_classified_deterministically():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    assert verdict.confidence_band.label == "open_candidate"
    again = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    assert verdict.confidence_band == again.confidence_band


def test_rationale_lists_supporting_and_dissenting_experts():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("SELL"), md_amr=_md("BUY")),
        valid_config(),
    )
    assert set(verdict.rationale.supporting_experts) == {"aurora", "md_amr"}
    assert verdict.rationale.dissenting_experts == ["mean_reversion"]


def test_score_components_reconcile_to_final_confidence():
    verdict = score_judge_envelope(
        _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY")),
        valid_config(),
    )
    components = verdict.score_components
    expected = (
        components.agreement_component
        + components.expert_confidence_component
        + components.regime_component
        + components.historical_surface_component
        - components.missingness_penalty
        - components.freshness_penalty
        - components.disagreement_penalty
    )
    assert components.final_score_before_clamp == expected
    assert verdict.confidence == components.final_confidence


def test_scorer_does_not_mutate_envelope_and_is_deterministic():
    envelope = _envelope(aurora=_aurora("BUY"), mean_reversion=_mr("BUY"))
    before = deepcopy(envelope.model_dump())
    first = score_judge_envelope(envelope, valid_config())
    second = score_judge_envelope(envelope, valid_config())
    assert envelope.model_dump() == before
    assert first == second
