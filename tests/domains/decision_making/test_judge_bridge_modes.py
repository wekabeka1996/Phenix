from __future__ import annotations

from copy import deepcopy

from apps.reference.config.domains.decision_making import JudgeBridgeConfig
from apps.reference.domains.alpha_search.judge.central_brain.verdict import (
    ConfidenceBand,
    JudgePolicyVerdictV2,
    PolicyContext,
    ScoreComponents,
    VerdictRationale,
    VerdictSourceRefs,
)
from apps.reference.domains.decision_making.judge_bridge import (
    JudgeBridgeCandidateContext,
    evaluate_judge_bridge,
)

from tests.config.test_judge_bridge_config_contract import (
    hybrid_config_payload,
    valid_payload,
)


def _config(*, mode: str = "shadow", enabled: bool = True) -> JudgeBridgeConfig:
    payload = deepcopy(valid_payload())
    payload["enabled"] = enabled
    payload["authority_mode"] = mode
    if mode == "live_gated":
        payload["calibration_guard"]["accepted_artifact_path"] = "reports/accepted.json"
    return JudgeBridgeConfig.model_validate(payload)


def _hybrid_config() -> JudgeBridgeConfig:
    return JudgeBridgeConfig.model_validate(hybrid_config_payload())


def _verdict(verdict: str = "OPEN_LONG", confidence: float = 0.70) -> JudgePolicyVerdictV2:
    return JudgePolicyVerdictV2(
        verdict_id=f"verdict-{verdict}-{confidence}",
        envelope_id="env-1",
        created_ts_ms=1000,
        symbol="BTCUSDT",
        question_type="entry",
        verdict=verdict,
        confidence=confidence,
        confidence_band=ConfidenceBand(min=0.55, max=0.85, label="open_candidate"),
        rationale=VerdictRationale(
            summary="fixture",
            disagreement_state="AGREE_LONG",
        ),
        score_components=ScoreComponents(
            agreement_component=0.3,
            expert_confidence_component=0.3,
            regime_component=0.1,
            historical_surface_component=0.0,
            missingness_penalty=0.0,
            freshness_penalty=0.0,
            disagreement_penalty=0.0,
            final_score_before_clamp=confidence,
            final_confidence=confidence,
        ),
        policy_context=PolicyContext(runtime_mode="testnet"),
        source_refs=VerdictSourceRefs(
            envelope_id="env-1",
            decision_id="decision-1",
            rid="rid-1",
            cycle_key="cycle-1",
        ),
    )


def _candidate(side: str = "BUY", exists: bool = True) -> JudgeBridgeCandidateContext:
    return JudgeBridgeCandidateContext(
        decision_id="decision-1",
        symbol="BTCUSDT",
        side=side,
        candidate_exists=exists,
        hard_gate_results={
            "panic_killswitch": True,
            "exchange_filter_fail": True,
            "exposure_limit": True,
            "stale_features": True,
            "stale_regime": True,
            "order_guardian_block": True,
        },
        hard_gate_blocking_reasons=[],
    )


def test_shadow_mode_record_only_no_effect():
    decision = evaluate_judge_bridge(_verdict(), _config(mode="shadow"), "testnet", _candidate())
    assert decision.bridge_action == "record_only"
    assert decision.applied is False
    assert decision.no_effect is True


def test_advisory_mode_record_only_no_effect():
    decision = evaluate_judge_bridge(_verdict(), _config(mode="advisory"), "testnet", _candidate())
    assert decision.bridge_action == "record_only"
    assert decision.applied is False
    assert decision.no_effect is True


def test_hybrid_gated_disabled_returns_skip_no_effect():
    decision = evaluate_judge_bridge(
        _verdict(),
        _config(mode="hybrid_gated", enabled=False),
        "testnet",
        _candidate(),
    )
    assert decision.bridge_action == "skip"
    assert decision.no_effect is True


def test_hybrid_gated_missing_candidate_does_not_create_candidate():
    decision = evaluate_judge_bridge(
        _verdict(),
        _hybrid_config(),
        "testnet",
        _candidate(exists=False),
    )
    assert decision.bridge_action == "skip"
    assert "bridge_cannot_create_candidate" in decision.reason_codes


def test_hybrid_gated_open_long_allows_existing_buy_candidate_in_band():
    decision = evaluate_judge_bridge(
        _verdict("OPEN_LONG", 0.70),
        _hybrid_config(),
        "testnet",
        _candidate("BUY"),
    )
    assert decision.bridge_action == "allow"
    assert decision.applied is True
    assert decision.no_effect is False


def test_hybrid_gated_open_short_allows_existing_sell_candidate_in_band():
    decision = evaluate_judge_bridge(
        _verdict("OPEN_SHORT", 0.70),
        _hybrid_config(),
        "testnet",
        _candidate("SELL"),
    )
    assert decision.bridge_action == "allow"
    assert decision.applied is True
    assert decision.no_effect is False


def test_side_mismatch_never_allows():
    decision = evaluate_judge_bridge(
        _verdict("OPEN_LONG", 0.70),
        _hybrid_config(),
        "testnet",
        _candidate("SELL"),
    )
    assert decision.bridge_action == "blocked"
    assert decision.applied is False
    assert decision.no_effect is True


def test_suppress_in_suppress_band_suppresses_existing_candidate_only():
    decision = evaluate_judge_bridge(
        _verdict("SUPPRESS", 0.95),
        _hybrid_config(),
        "testnet",
        _candidate("BUY"),
    )
    assert decision.bridge_action == "suppress"
    assert decision.applied is True
    assert decision.no_effect is False


def test_unknown_fail_closed_blocks_no_effect():
    decision = evaluate_judge_bridge(
        _verdict("UNKNOWN", 0.10),
        _hybrid_config(),
        "testnet",
        _candidate("BUY"),
    )
    assert decision.bridge_action == "blocked"
    assert decision.unknown_policy_applied is True
    assert decision.no_effect is True


def test_no_entry_blocks_no_effect():
    decision = evaluate_judge_bridge(
        _verdict("NO_ENTRY", 0.40),
        _hybrid_config(),
        "testnet",
        _candidate("BUY"),
    )
    assert decision.bridge_action == "blocked"
    assert decision.no_effect is True


def test_live_gated_blocked_in_phase_7():
    decision = evaluate_judge_bridge(
        _verdict(),
        _config(mode="live_gated"),
        "testnet",
        _candidate("BUY"),
    )
    assert decision.bridge_action == "blocked"
    assert "live_gated_blocked_in_phase_7" in decision.reason_codes


def test_deterministic_bridge_decision_id():
    first = evaluate_judge_bridge(_verdict(), _hybrid_config(), "testnet", _candidate("BUY"))
    second = evaluate_judge_bridge(_verdict(), _hybrid_config(), "testnet", _candidate("BUY"))
    assert first.bridge_decision_id == second.bridge_decision_id

