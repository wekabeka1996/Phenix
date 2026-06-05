from __future__ import annotations

import decimal
from pathlib import Path

import pytest

from apps.reference.shared.decision_primitives.score_lineage import (
    COMPATIBILITY_ONLY,
    LIVE_AUTHORITATIVE,
    OBJECTIVE_GATE_THRESHOLD_FAMILY,
    SIGNED_OBJECTIVE_SCORE,
    build_score_lineage_payload,
    build_score_lineage_record,
    find_score_lineage_record,
    get_score_field_contract,
)
from apps.reference.shared.decision_primitives.scoring_kernel import (
    QuadraticScoringKernel,
)
from tools.forensics.aurora_scoring_truth_discriminator import build_summary


REPO_ROOT = Path(__file__).resolve().parents[3]


def _kernel(**overrides):
    kwargs = {
        "symbol": "BTCUSDT",
        "features": {"pillar_sum": 0.42},
        "warmup_readiness": {},
        "price": decimal.Decimal("50000"),
        "signal_weights": {},
        "feature_neutrals": {},
        "essential_features": [],
        "base_threshold": decimal.Decimal("0.1"),
        "regime_name": "DEFAULT",
        "regime_thresholds": {"DEFAULT": 1.0},
        "side_bias_state": None,
        "direction_strength_cfg": {},
        "delta_price_cap_pct": decimal.Decimal("0.005"),
        "neutral_threshold": decimal.Decimal("0.05"),
        "current_side": "",
        "admission_mode": "linear",
        "sizing_mode": "quadratic",
    }
    kwargs.update(overrides)
    return QuadraticScoringKernel.compute(**kwargs)


def _same_authoritative_kernel_output(left, right) -> None:
    assert left.deferred == right.deferred
    assert left.defer_reason == right.defer_reason
    assert left.side == right.side
    assert left.score == right.score
    assert left.raw_score == right.raw_score
    assert left.decision_score == right.decision_score
    assert left.sizing_score == right.sizing_score
    assert left.thr_buy == right.thr_buy
    assert left.thr_sell == right.thr_sell
    assert left.psi_vector["source"] == right.psi_vector["source"]
    assert left.psi_vector["s_linear"] == right.psi_vector["s_linear"]


def test_signal_weights_do_not_affect_kernel_when_pillar_sum_fixed() -> None:
    base = _kernel(features={"pillar_sum": 0.42}, signal_weights={})
    perturbed = _kernel(
        features={"pillar_sum": 0.42},
        signal_weights={
            "obi": 999.0,
            "tfi": -999.0,
            "macro_resid": 123.45,
        },
    )

    _same_authoritative_kernel_output(base, perturbed)


def test_feature_neutrals_do_not_affect_kernel_when_pillar_sum_fixed() -> None:
    base = _kernel(features={"pillar_sum": -0.37}, feature_neutrals={})
    perturbed = _kernel(
        features={"pillar_sum": -0.37},
        feature_neutrals={
            "obi": 0.99,
            "tfi": -0.99,
            "macro_resid": 5.0,
        },
    )

    _same_authoritative_kernel_output(base, perturbed)


def test_pillar_sum_changes_kernel_output() -> None:
    weak = _kernel(features={"pillar_sum": 0.2})
    strong = _kernel(features={"pillar_sum": 0.6})

    assert weak.raw_score != strong.raw_score
    assert weak.decision_score != strong.decision_score
    assert weak.sizing_score != strong.sizing_score
    assert weak.psi_vector["s_linear"] == pytest.approx(0.2)
    assert strong.psi_vector["s_linear"] == pytest.approx(0.6)


def test_live_decision_geometry_linear_admission_quadratic_sizing() -> None:
    summary = build_summary(REPO_ROOT)

    assert summary["geometry"]["status"] == "PRESENT"
    assert summary["geometry"]["admission_mode"] == "linear"
    assert summary["geometry"]["sizing_mode"] == "quadratic"
    assert (
        summary["verdicts"]["quadratic_logic_classification"]
        == "QUADRATIC_USED_FOR_SIZING_ONLY"
    )


def test_quadratic_changes_sizing_not_admission_when_config_linear() -> None:
    linear_sizing = _kernel(
        features={"pillar_sum": 0.4},
        admission_mode="linear",
        sizing_mode="linear",
    )
    quadratic_sizing = _kernel(
        features={"pillar_sum": 0.4},
        admission_mode="linear",
        sizing_mode="quadratic",
    )

    assert linear_sizing.decision_score == quadratic_sizing.decision_score
    assert linear_sizing.side == quadratic_sizing.side
    assert linear_sizing.sizing_score != quadratic_sizing.sizing_score
    assert quadratic_sizing.sizing_score == decimal.Decimal("0.16")


def test_score_lineage_marks_admission_and_sizing_fields() -> None:
    summary = build_summary(REPO_ROOT)
    rows = {
        row["field_or_surface"]: row for row in summary["producer_consumer_map"]
    }

    assert rows["pillar_sum"]["authority_status"] == "LIVE_AUTHORITATIVE"
    assert rows["raw_score"]["authority_status"] == "LIVE_AUTHORITATIVE"
    assert rows["decision_score"]["authority_status"] == "LIVE_AUTHORITATIVE"
    assert rows["sizing_score"]["producer"] == "QuadraticScoringKernel.compute"
    assert rows["score"]["authority_status"] == "COMPATIBILITY_ONLY"


def test_aurora_signal_weights_perturbation_runtime_effect_or_declared_unprovable() -> None:
    summary = build_summary(REPO_ROOT)

    assert summary["verdicts"]["signal_weights_effect"] in {
        "SIGNAL_WEIGHTS_DEAD_CONFIG_CONFIRMED",
        "SIGNAL_WEIGHTS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM",
    }
    assert (
        summary["verdicts"]["signal_weights_effect"]
        == "SIGNAL_WEIGHTS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM"
    )
    assert any(
        gap["verdict"] == "SIGNAL_WEIGHTS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM"
        for gap in summary["testability_gaps"]
    )


def test_feature_neutrals_live_aurora_effect_or_declared_unprovable() -> None:
    summary = build_summary(REPO_ROOT)

    assert summary["verdicts"]["feature_neutrals_effect"] in {
        "FEATURE_NEUTRALS_DEAD_FOR_LIVE_AURORA",
        "FEATURE_NEUTRALS_USED_BY_JUDGE_ONLY",
        "FEATURE_NEUTRALS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM",
    }
    assert (
        summary["verdicts"]["feature_neutrals_effect"]
        == "FEATURE_NEUTRALS_EFFECT_BLOCKED_BY_MISSING_TEST_SEAM"
    )


def test_low_vol_consumed_score_fields_have_authority_status() -> None:
    summary = build_summary(REPO_ROOT)
    rows = {
        row["field_or_surface"]: row for row in summary["producer_consumer_map"]
    }

    for field in (
        "signal_score",
        "final_score",
        "judge_confidence",
        "strategy_confidence",
    ):
        assert rows[field]["authority_status"] in {
            "LIVE_AUTHORITATIVE",
            "SHADOW_ONLY",
            "COMPATIBILITY_ONLY",
        }
        assert rows[field]["runtime_active"] in {
            "YES_COMPATIBILITY_OR_TRACE",
            "CANDIDATE_OR_SHADOW",
        }

    assert summary["downstream_lineage"]["low_vol_uses_find_score_lineage_record"]
    assert (
        summary["verdicts"]["downstream_gate_lineage_status"]
        == "LOW_VOL_CONSUMES_COMPATIBILITY_ALIAS"
    )


def test_objective_override_preserves_lineage_or_reports_gap() -> None:
    payload = build_score_lineage_payload(
        [
            build_score_lineage_record(
                field="decision_score",
                value=0.31,
                producer="QuadraticScoringKernel.compute",
                consumer_stage="aurora.strategy_signal_payload",
            ),
            build_score_lineage_record(
                field="objective_score",
                value=0.44,
                producer="objective_gate_evaluator",
                consumer_stage="aurora.strategy_signal_payload",
            ),
            build_score_lineage_record(
                field="score",
                value=0.44,
                producer="objective_gate_evaluator",
                consumer_stage="aurora.strategy_signal_payload",
                scale=SIGNED_OBJECTIVE_SCORE,
                threshold_family=OBJECTIVE_GATE_THRESHOLD_FAMILY,
                live_authority_status=LIVE_AUTHORITATIVE,
                compatibility_alias_for="objective_score",
                post_objective_override=True,
            ),
        ]
    )

    objective = find_score_lineage_record(payload, "objective_score")
    final_score = find_score_lineage_record(payload, "score")

    assert objective is not None
    assert objective["live_authority_status"] == LIVE_AUTHORITATIVE
    assert final_score is not None
    assert final_score["post_objective_override"] is True
    assert final_score["compatibility_alias_for"] == "objective_score"
    assert final_score["scale"] == SIGNED_OBJECTIVE_SCORE


def test_legacy_alias_consumption_is_reported_not_silently_accepted() -> None:
    score_contract = get_score_field_contract("score")
    signal_contract = get_score_field_contract("signal_score")
    final_raw_contract = get_score_field_contract("final_score_raw")
    summary = build_summary(REPO_ROOT)

    assert score_contract is not None
    assert score_contract.live_authority_status == COMPATIBILITY_ONLY
    assert signal_contract is not None
    assert signal_contract.live_authority_status == COMPATIBILITY_ONLY
    assert final_raw_contract is not None
    assert final_raw_contract.live_authority_status == "deprecated_alias"
    assert "signal_score" in summary["downstream_lineage"]["legacy_aliases_reported"]
    assert "final_score" in summary["downstream_lineage"]["legacy_aliases_reported"]
