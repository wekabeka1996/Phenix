from pathlib import Path

import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.datasets.contracts import (
    DatasetEvaluatedSample,
    DatasetSampleProvenance,
)
from apps.reference.domains.neocortex.logic.evaluation import ShadowOfflineEvaluator
from apps.reference.domains.neocortex.logic.gates import ShadowGateEvaluator


def _config():
    return load_config(Path("apps/reference/domains/neocortex/config"))


def _evaluated_sample(
    *,
    dataset_sample_id: str,
    objective_family: str,
    eligibility_status: str,
    event_ts_ms: int,
    sample: dict,
    symbol: str = "BTCUSDT",
    lifecycle_id: str | None = None,
    trade_id: str | None = None,
    exclusion_reasons: list[str] | None = None,
    quarantine_reasons: list[str] | None = None,
) -> DatasetEvaluatedSample:
    provenance = DatasetSampleProvenance(
        dataset_sample_id=dataset_sample_id,
        objective_family=objective_family,
        source_type="test",
        source_ref=f"fixture:{dataset_sample_id}",
        source_event_type="TEST_EVENT",
        event_ts_ms=event_ts_ms,
        symbol=symbol,
        lifecycle_id=lifecycle_id,
        trade_id=trade_id,
        ingestion_mode="backtest",
        legacy_causal_mode=False,
        sequence_contract_mode=(
            "independent_rows" if objective_family == "representation" else None
        ),
        policy_training_mode="disabled",
        eligibility_status=eligibility_status,
        exclusion_reasons=exclusion_reasons or [],
        quarantine_reasons=quarantine_reasons or [],
    )
    return DatasetEvaluatedSample(
        objective_family=objective_family,
        eligibility_status=eligibility_status,
        is_trainable=eligibility_status == "trainable",
        sample=sample,
        provenance=provenance,
    )


def test_regime_evaluation_report_is_deterministic_and_family_isolated():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)
    samples = [
        _evaluated_sample(
            dataset_sample_id="regime-a",
            objective_family="regime_supervision",
            eligibility_status="trainable",
            event_ts_ms=1_700_000_000_100,
            sample={
                "event_ts_ms": 1_700_000_000_100,
                "symbol": "BTCUSDT",
                "predicted_regime": 1,
                "realized_regime": 1,
                "confidence": 0.9,
            },
            symbol="BTCUSDT",
        ),
        _evaluated_sample(
            dataset_sample_id="regime-b",
            objective_family="regime_supervision",
            eligibility_status="trainable",
            event_ts_ms=1_700_000_000_200,
            sample={
                "event_ts_ms": 1_700_000_000_200,
                "symbol": "ETHUSDT",
                "predicted_regime": 2,
                "realized_regime": 1,
                "confidence": 0.8,
            },
            symbol="ETHUSDT",
        ),
        _evaluated_sample(
            dataset_sample_id="regime-c",
            objective_family="regime_supervision",
            eligibility_status="rejected",
            event_ts_ms=1_700_000_000_300,
            sample={
                "event_ts_ms": 1_700_000_000_300,
                "symbol": "SOLUSDT",
                "predicted_regime": None,
                "realized_regime": None,
            },
            symbol="SOLUSDT",
            exclusion_reasons=["missing_regime_target"],
        ),
    ]

    first, _ = evaluator.evaluate_regime_supervision(
        samples,
        evaluated_at_ms=1_700_000_100_000,
    )
    second, _ = evaluator.evaluate_regime_supervision(
        samples,
        evaluated_at_ms=1_700_000_100_000,
    )

    assert first.model_dump(mode="python") == second.model_dump(mode="python")
    assert first.objective_family == "regime_supervision"
    assert first.sample_counts["included"] == 2
    assert first.sample_counts["excluded"] == 1
    assert first.key_metrics["accuracy"] == 0.5
    assert "reward_complete_rate" not in first.key_metrics


def test_execution_quality_report_respects_reward_completeness_and_diagnostics():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)
    samples = [
        _evaluated_sample(
            dataset_sample_id="exec-a",
            objective_family="execution_quality",
            eligibility_status="trainable",
            event_ts_ms=1_700_000_000_100,
            sample={
                "event_ts_ms": 1_700_000_000_100,
                "trade_id": "trade-1",
                "lifecycle_id": "life-1",
                "reward_complete": True,
                "close_event": "POSITION_CLOSED",
                "fill_count": 2,
                "filled_quantity": 1.5,
            },
            trade_id="trade-1",
            lifecycle_id="life-1",
        ),
        _evaluated_sample(
            dataset_sample_id="exec-b",
            objective_family="execution_quality",
            eligibility_status="diagnostics_only",
            event_ts_ms=1_700_000_000_200,
            sample={
                "event_ts_ms": 1_700_000_000_200,
                "trade_id": "trade-2",
                "lifecycle_id": "life-2",
                "reward_complete": False,
                "reward_missing": True,
                "close_event": "POSITION_CLOSED",
                "fill_count": 1,
            },
            trade_id="trade-2",
            lifecycle_id="life-2",
            exclusion_reasons=["reward_incomplete"],
        ),
        _evaluated_sample(
            dataset_sample_id="exec-c",
            objective_family="execution_quality",
            eligibility_status="quarantined",
            event_ts_ms=1_700_000_000_300,
            sample={
                "event_ts_ms": 1_700_000_000_300,
                "trade_id": "trade-3",
                "unresolved_lifecycle": True,
            },
            trade_id="trade-3",
            quarantine_reasons=["unresolved_lifecycle"],
        ),
    ]

    report = evaluator.evaluate_execution_quality(
        samples,
        evaluated_at_ms=1_700_000_100_000,
    )

    assert report.objective_family == "execution_quality"
    assert report.sample_counts["diagnostics_only"] == 1
    assert report.sample_counts["quarantined"] == 1
    assert report.diagnostics_only_count == 1
    assert report.unresolved_count == 1
    assert report.key_metrics["reward_complete_rate"] == 0.5
    assert "accuracy" not in report.key_metrics


def test_regime_evaluator_rejects_mixed_objective_family():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)
    mixed = [
        _evaluated_sample(
            dataset_sample_id="exec-a",
            objective_family="execution_quality",
            eligibility_status="trainable",
            event_ts_ms=1_700_000_000_100,
            sample={
                "event_ts_ms": 1_700_000_000_100,
                "trade_id": "trade-1",
                "reward_complete": True,
            },
            trade_id="trade-1",
        )
    ]

    with pytest.raises(ValueError):
        evaluator.evaluate_regime_supervision(
            mixed,
            evaluated_at_ms=1_700_000_100_000,
        )


def test_advisory_readiness_report_remains_forbidden():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)
    gate_report = ShadowGateEvaluator().evaluate(
        config,
        evaluated_at_ms=1_700_000_100_000,
    )
    regime_report, calibration_report = evaluator.evaluate_regime_supervision(
        [
            _evaluated_sample(
                dataset_sample_id="regime-no-conf",
                objective_family="regime_supervision",
                eligibility_status="trainable",
                event_ts_ms=1_700_000_000_100,
                sample={
                    "event_ts_ms": 1_700_000_000_100,
                    "predicted_regime": 1,
                    "realized_regime": 1,
                },
            )
        ],
        evaluated_at_ms=1_700_000_100_000,
    )
    execution_report = evaluator.evaluate_execution_quality(
        [
            _evaluated_sample(
                dataset_sample_id="exec-trainable",
                objective_family="execution_quality",
                eligibility_status="trainable",
                event_ts_ms=1_700_000_000_200,
                sample={
                    "event_ts_ms": 1_700_000_000_200,
                    "trade_id": "trade-1",
                    "lifecycle_id": "life-1",
                    "reward_complete": True,
                },
                trade_id="trade-1",
                lifecycle_id="life-1",
            )
        ],
        evaluated_at_ms=1_700_000_100_000,
    )
    disagreement_report = evaluator.evaluate_disagreement(
        [],
        evaluated_at_ms=1_700_000_100_000,
    )

    prereq = evaluator.build_advisory_readiness_report(
        config=config,
        gate_report=gate_report,
        regime_report=regime_report,
        execution_report=execution_report,
        calibration_report=calibration_report,
        disagreement_report=disagreement_report,
        evaluated_at_ms=1_700_000_100_000,
    )

    assert prereq.advisory_status == "forbidden"
    assert "advisory_enable_forbidden_in_p9" in prereq.blocking_reasons
    assert "calibration_evidence_not_available" in prereq.unsatisfied_prereqs
    assert "NEO-ACCEPTANCE-CAMPAIGN-SHADOW-ANALYTICS" in prereq.recommended_next_packages
