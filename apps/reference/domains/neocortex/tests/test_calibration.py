from pathlib import Path

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.datasets.contracts import (
    DatasetEvaluatedSample,
    DatasetSampleProvenance,
)
from apps.reference.domains.neocortex.logic.evaluation import ShadowOfflineEvaluator


def _config():
    return load_config(Path("apps/reference/domains/neocortex/config"))


def _regime_sample(
    dataset_sample_id: str,
    event_ts_ms: int,
    *,
    predicted_regime: int,
    realized_regime: int,
    confidence=None,
) -> DatasetEvaluatedSample:
    sample = {
        "event_ts_ms": event_ts_ms,
        "predicted_regime": predicted_regime,
        "realized_regime": realized_regime,
        "symbol": "BTCUSDT",
    }
    if confidence is not None:
        sample["confidence"] = confidence
    provenance = DatasetSampleProvenance(
        dataset_sample_id=dataset_sample_id,
        objective_family="regime_supervision",
        source_type="test",
        source_ref=f"fixture:{dataset_sample_id}",
        source_event_type="EVT:NEOCORTEX_REGIME_PREDICTION",
        event_ts_ms=event_ts_ms,
        symbol="BTCUSDT",
        ingestion_mode="backtest",
        legacy_causal_mode=False,
        sequence_contract_mode=None,
        policy_training_mode="disabled",
        eligibility_status="trainable",
        exclusion_reasons=[],
        quarantine_reasons=[],
    )
    return DatasetEvaluatedSample(
        objective_family="regime_supervision",
        eligibility_status="trainable",
        is_trainable=True,
        sample=sample,
        provenance=provenance,
    )


def test_calibration_report_is_honest_when_confidence_missing():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)

    _, calibration = evaluator.evaluate_regime_supervision(
        [
            _regime_sample(
                "no-confidence",
                1_700_000_000_100,
                predicted_regime=1,
                realized_regime=1,
            )
        ],
        evaluated_at_ms=1_700_000_100_000,
    )

    assert calibration.status == "not_available"
    assert calibration.confidence_source == "sample.confidence"
    assert calibration.reliability_summary["scored_samples"] == 0


def test_calibration_report_bins_confidence_when_available():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)

    _, calibration = evaluator.evaluate_regime_supervision(
        [
            _regime_sample("c1", 1_700_000_000_100, predicted_regime=1, realized_regime=1, confidence=0.9),
            _regime_sample("c2", 1_700_000_000_200, predicted_regime=1, realized_regime=0, confidence=0.8),
            _regime_sample("c3", 1_700_000_000_300, predicted_regime=0, realized_regime=0, confidence=0.3),
            _regime_sample("c4", 1_700_000_000_400, predicted_regime=0, realized_regime=1, confidence=0.4),
        ],
        evaluated_at_ms=1_700_000_100_000,
    )

    assert calibration.status == "available"
    assert calibration.number_of_bins == config.neuro.evaluation.calibration_bins
    assert sum(calibration.counts_per_bin) == 4
    assert calibration.reliability_summary["scored_samples"] == 4
