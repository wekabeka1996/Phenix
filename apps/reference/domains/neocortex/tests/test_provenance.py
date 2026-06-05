"""
Dataset provenance and manifest tests for P6.
"""

from pathlib import Path

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine


def _engine() -> DatasetPolicyEngine:
    config = load_config(Path("apps/reference/domains/neocortex/config"))
    return DatasetPolicyEngine(
        config.neuro.dataset,
        policy_training_mode=config.neuro.ppo.policy_training_mode,
        representation_training_mode=config.neuro.sequence.representation_training_mode,
        sequence_inference_mode=config.neuro.sequence.inference_mode,
    )


def test_provenance_sample_id_is_deterministic():
    engine = _engine()
    sample = {
        "event_ts_ms": 1_700_000_000_700,
        "symbol": "BTCUSDT",
        "features_vector": [0.1, 0.2],
        "sequence_contract_mode": "independent_rows",
    }

    first = engine.evaluate_sample(
        sample,
        objective_family="representation",
        source_type="features_event",
        source_ref="features:btc:1",
        source_event_type="EVT:FEATURES_CALCULATED",
        ingestion_mode="replay",
    )
    second = engine.evaluate_sample(
        sample,
        objective_family="representation",
        source_type="features_event",
        source_ref="features:btc:1",
        source_event_type="EVT:FEATURES_CALCULATED",
        ingestion_mode="replay",
    )

    assert first.provenance.dataset_sample_id == second.provenance.dataset_sample_id


def test_manifest_contains_counts_reasons_and_deterministic_non_overlapping_splits():
    engine = _engine()
    samples = [
        engine.evaluate_sample(
            {
                "event_ts_ms": 1_700_000_000_100 + idx,
                "symbol": "BTCUSDT",
                "features_vector": [float(idx), 0.2],
                "sequence_contract_mode": "independent_rows",
            },
            objective_family="representation",
            source_type="features_event",
            source_ref=f"features:btc:{idx}",
            source_event_type="EVT:FEATURES_CALCULATED",
            ingestion_mode="replay",
        )
        for idx in range(6)
    ]
    samples.append(
        engine.evaluate_sample(
            {
                "event_ts_ms": 1_700_000_000_500,
                "symbol": "BTCUSDT",
                "features_vector": [9.9, 8.8],
                "sequence_contract_mode": "independent_rows",
                "time_is_causal": False,
                "time_source": "legacy_non_causal_file_offset",
            },
            objective_family="representation",
            source_type="features_event",
            source_ref="features:btc:legacy",
            source_event_type="EVT:FEATURES_CALCULATED",
            ingestion_mode="replay",
        )
    )

    manifest_a = engine.build_manifest(samples, objective_family="representation")
    manifest_b = engine.build_manifest(samples, objective_family="representation")

    assert manifest_a.dataset_id == manifest_b.dataset_id
    assert manifest_a.sample_counts["trainable"] == 6
    assert manifest_a.sample_counts["eval_only"] == 1
    assert manifest_a.legacy_non_causal_count == 1
    assert manifest_a.exclusion_reason_counts["legacy_non_causal_representation"] == 1

    split_ids = []
    for split in manifest_a.splits:
        split_ids.extend(split.sample_ids)

    assert len(split_ids) == len(set(split_ids))
    assert set(split_ids) == {
        sample.provenance.dataset_sample_id
        for sample in samples
        if sample.eligibility_status == "trainable"
    }
