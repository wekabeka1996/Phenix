from __future__ import annotations

from copy import deepcopy

from apps.reference.domains.alpha_search.judge.central_brain.envelope_builder import (
    build_judge_evidence_envelope,
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


def _aurora_payload(side: str = "BUY") -> dict:
    score = 0.7 if side == "BUY" else -0.7
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 1000,
        "side": side,
        "features": {"ts_ms": 990, "obi": 0.2, "tfi": 0.1},
        "scoring": {"decision_score": score, "pillar_sum": score},
        "rid": "rid-a",
    }


def _mr_payload(side: str = "BUY") -> dict:
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 1000,
        "side": side,
        "confidence": 0.55,
        "rsi": 31.0,
        "bb": {"pct_b": 0.1, "width": 0.04, "upper": 110.0, "mid": 100.0, "lower": 90.0},
        "volatility": {"atr": 12.0},
        "price_ctx": {"target_price": 103.0, "stop_price": 96.0},
        "rid": "rid-mr",
    }


def _md_payload(side: str = "BUY") -> dict:
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 1000,
        "side": side,
        "intent_kind": "ENTRY",
        "conf_ratio": 0.6,
        "trace": {"setup_quality": 0.8, "progress_state": "forming"},
        "rid": "rid-md",
    }


def _regime_payload() -> dict:
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 980,
        "regime": "LOW_VOLATILITY",
        "confidence": 0.8,
        "basis_tf_sec": 60,
        "rid": "rid-regime",
    }


def _aurora(side: str = "BUY"):
    return build_aurora_expert_output(_aurora_payload(side), now_ms=1000)


def _mr(side: str = "BUY"):
    return build_mean_reversion_expert_output(_mr_payload(side), now_ms=1000)


def _md(side: str = "BUY"):
    return build_md_amr_expert_output(_md_payload(side), now_ms=1000)


def _regime():
    return build_regime_context_envelope(
        _regime_payload(),
        decision_ts_ms=1000,
        freshness_threshold_ms=30_000,
    )


def test_builder_creates_envelope_from_aurora_and_regime_only():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora(),
        regime_context=_regime(),
    )
    assert envelope.authority_status == "evidence_only"
    assert envelope.regime_context.present is True
    assert envelope.strategy_opinions.aurora is not None
    assert envelope.strategy_opinions.mean_reversion is None
    assert envelope.disagreement_map.agreement_state == "SINGLE_EXPERT"


def test_builder_creates_envelope_from_all_native_opinions_and_regime():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora("BUY"),
        mean_reversion=_mr("BUY"),
        md_amr=_md("BUY"),
        regime_context=_regime(),
    )
    assert envelope.strategy_opinions.aurora is not None
    assert envelope.strategy_opinions.mean_reversion is not None
    assert envelope.strategy_opinions.md_amr is not None
    assert envelope.disagreement_map.agreement_state == "AGREE_LONG"


def test_builder_handles_no_strategy_opinions_as_no_experts():
    envelope = build_judge_evidence_envelope(symbol="BTCUSDT", created_ts_ms=1000)
    assert envelope.disagreement_map.agreement_state == "NO_EXPERTS"
    assert envelope.freshness_missingness_map.per_block["aurora"] == "MISSING"


def test_builder_classifies_agree_long():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora("BUY"),
        mean_reversion=_mr("BUY"),
    )
    assert envelope.disagreement_map.agreement_state == "AGREE_LONG"


def test_builder_classifies_agree_short():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora("SELL"),
        mean_reversion=_mr("SELL"),
    )
    assert envelope.disagreement_map.agreement_state == "AGREE_SHORT"


def test_builder_classifies_disagree():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora("BUY"),
        mean_reversion=_mr("SELL"),
    )
    assert envelope.disagreement_map.agreement_state == "DISAGREE"


def test_builder_classifies_single_expert():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        md_amr=_md("SELL"),
    )
    assert envelope.disagreement_map.agreement_state == "SINGLE_EXPERT"


def test_builder_classifies_unknown_for_none_unknown_only():
    envelope = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=_aurora("NONE"),
        mean_reversion=_mr("UNKNOWN"),
    )
    assert envelope.disagreement_map.agreement_state == "UNKNOWN"


def test_builder_records_missing_context_blocks():
    envelope = build_judge_evidence_envelope(symbol="BTCUSDT", created_ts_ms=1000)
    assert envelope.risk_context.present is False
    assert envelope.portfolio_context.present is False
    assert envelope.execution_readiness.present is False
    assert envelope.historical_surface_evidence.present is False
    assert envelope.risk_context.missing_reason == "not_supplied"
    assert envelope.freshness_missingness_map.per_block["market_context"] == "MISSING"


def test_builder_uses_deterministic_envelope_ids():
    first = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        decision_id="decision-1",
    )
    second = build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        decision_id="decision-1",
    )
    assert first.envelope_id == second.envelope_id


def test_builder_does_not_mutate_input_dicts():
    aurora = _aurora().model_dump()
    regime = _regime().model_dump()
    aurora_before = deepcopy(aurora)
    regime_before = deepcopy(regime)
    build_judge_evidence_envelope(
        symbol="BTCUSDT",
        created_ts_ms=1000,
        aurora=aurora,
        regime_context=regime,
    )
    assert aurora == aurora_before
    assert regime == regime_before
