from pathlib import Path
from types import SimpleNamespace
import runpy

import pytest
from pydantic import ValidationError
from pydantic.fields import PydanticUndefined

from apps.reference.domains.neocortex.config_models import (
    AuthorityConfig,
    DatasetConfig,
    DatasetSplitConfig,
    EvaluationConfig,
    IngestConfig,
    OracleConfig,
    PPOConfig,
    PPOEntropyScheduleConfig,
    ReplayConfig,
    SequenceConfig,
    ShadowGateConfig,
    SystemConfig,
    VAEConfig,
    PPONumericalSafetyConfig,
    PerformanceConfig,
    NeuroConfig,
    NeocortexConfig,
    load_config,
)


MODEL_DEFAULT_WHITELIST = {
    SystemConfig: set(),
    IngestConfig: set(),
    VAEConfig: {"regime_aux"},
    VAEConfig.RegimeAuxConfig: {"alpha", "num_classes", "ema_decay", "alpha_schedule"},
    VAEConfig.RegimeAuxConfig.AlphaScheduleConfig: set(),
    PPONumericalSafetyConfig: set(),
    PPOConfig: {"entropy_schedule"},
    SequenceConfig: set(),
    DatasetConfig: {"manifest_version"},
    PerformanceConfig: set(),
    EvaluationConfig: {"report_version"},
    ShadowGateConfig: {"gate_set_version"},
    ReplayConfig: {
        "wal_dir",
        "wal_glob",
        "filter_verb",
        "features_dir",
        "orders_file",
        "core_log",
        "symbols",
        "batch_size",
        "poll_interval",
        "max_feature_lines_total_per_cycle",
        "max_feature_lines_per_symbol_per_cycle",
        "max_order_lines_per_cycle",
        "max_core_lines_per_cycle",
        "feature_missing_timestamp_policy",
        "legacy_feature_base_ts_ms",
    },
    OracleConfig: {"reward_matrix"},
    NeuroConfig: {"sequence", "dataset", "evaluation", "performance", "shadow_gates"},
    AuthorityConfig: set(),
}


def _unexpected_defaults(model_type: type) -> list[str]:
    whitelist = MODEL_DEFAULT_WHITELIST[model_type]
    unexpected = []
    for field_name, field_info in model_type.model_fields.items():
        if field_name in whitelist:
            continue
        has_default = field_info.default is not PydanticUndefined
        has_factory = field_info.default_factory is not None
        if has_default or has_factory:
            unexpected.append(field_name)
    return unexpected


@pytest.mark.parametrize(
    "model_type",
    [
        SystemConfig,
        IngestConfig,
        VAEConfig,
        VAEConfig.RegimeAuxConfig,
        VAEConfig.RegimeAuxConfig.AlphaScheduleConfig,
        PPONumericalSafetyConfig,
        PPOConfig,
        SequenceConfig,
        DatasetConfig,
        PerformanceConfig,
        EvaluationConfig,
        ShadowGateConfig,
        ReplayConfig,
        OracleConfig,
        NeuroConfig,
        AuthorityConfig,
    ],
)
def test_critical_neocortex_models_do_not_hide_business_defaults(model_type: type):
    unexpected = _unexpected_defaults(model_type)
    assert unexpected == [
    ], f"{model_type.__name__} has unexpected defaults: {unexpected}"


def test_actual_neocortex_ssot_yaml_is_explicit_and_loads():
    config = load_config(Path("apps/reference/domains/neocortex/config"))

    assert config.system.run_mode == "backtest"
    assert config.system.rng_seed == 42
    assert config.ingest.normalization_scope == "per_symbol"
    assert config.ingest.price_feature_mode == "log"
    assert config.ingest.delta_price_mode == "pct"
    assert config.replay.wal_dir.name == "wal"
    assert config.replay.filter_verb == "FEATURES_CALCULATED"
    assert config.neuro.performance.operating_mode == "offline_replay"
    assert config.neuro.shadow_gates.startup_enforcement == "strict"
    assert config.oracle is not None
    assert config.oracle.reward_matrix_enabled is True
    # Phase 2: §6.2 keys must be present
    assert config.trust_enabled is False
    assert config.evidence_capture.mode == "disabled"
    assert config.evidence_capture.collect_observation is False
    assert config.evidence_capture.collect_authority_request is False
    assert config.evidence_capture.collect_authority_response is False
    assert config.evidence_capture.emit_shadow_decision_logged is False
    assert config.authority.mode == "shadow"
    assert config.authority.deadline_ms == 10
    assert config.authority.fallback_policy == "baseline_yaml"
    assert config.authority.max_inflight_per_symbol == 1
    assert len(config.authority.modulation_allowlist) >= 1
    assert len(config.authority.signal_threshold_bias_bounds) == 2
    assert len(config.authority.cooldown_mult_bounds) == 2


def test_empty_root_payload_fails_closed():
    with pytest.raises(ValidationError):
        NeocortexConfig.model_validate({})


def test_ingest_config_duplicate_features_and_clip_bounds_raise() -> None:
    base = {
        "feature_list": ["price"],
        "normalization_method": "zscore",
        "normalization_window": 100,
        "normalization_scope": "global",
        "price_feature_mode": "raw",
        "delta_price_mode": "raw",
        "feature_clip_abs": {"price": 1.0},
        "buffer_size": 1000,
        "min_samples_before_ready": 1,
        "nan_strategy": "zero",
    }

    with pytest.raises(ValidationError):
        IngestConfig.model_validate(
            {**base, "feature_list": ["price", "price"]})

    with pytest.raises(ValueError, match="must be numeric"):
        IngestConfig.validate_feature_clip_abs({"price": True})

    for bad_clip in (
        {"": 1.0},
        {"price": 0.0},
        {"price": float("inf")},
    ):
        with pytest.raises(ValidationError):
            IngestConfig.model_validate({**base, "feature_clip_abs": bad_clip})


def test_entropy_and_split_and_evaluation_bounds_raise() -> None:
    with pytest.raises(ValidationError):
        PPOEntropyScheduleConfig.model_validate(
            {"start": 0.1, "end": 0.2, "total_steps": 100}
        )

    with pytest.raises(ValidationError, match="live_shadow requires"):
        PerformanceConfig.model_validate(
            {
                "operating_mode": "live_shadow",
                "shadow_intent_emit_policy": "emit_all",
                "shadow_intent_decimation_stride": 2,
                "shadow_jsonl_write_policy": "buffered",
                "telemetry_write_policy": "buffered",
                "non_critical_queue_limit": 2048,
                "shadow_log_flush_threshold": 64,
                "telemetry_flush_threshold": 64,
                "flush_interval_ms": 1000,
                "non_critical_overflow_policy": "drop_oldest",
            }
        )

    with pytest.raises(ValidationError):
        DatasetSplitConfig.model_validate(
            {"train_ratio": 0.6, "val_ratio": 0.3, "test_ratio": 0.2}
        )

    with pytest.raises(ValidationError, match="strictly between 0 and 1"):
        EvaluationConfig.model_validate(
            {
                "report_version": 1,
                "calibration_bins": 5,
                "confidence_bucket_edges": [0.0, 0.5],
                "missing_confidence_policy": "not_available",
                "advisory_status": "forbidden",
            }
        )

    with pytest.raises(ValidationError, match="strictly increasing"):
        EvaluationConfig.model_validate(
            {
                "report_version": 1,
                "calibration_bins": 5,
                "confidence_bucket_edges": [0.2, 0.2],
                "missing_confidence_policy": "not_available",
                "advisory_status": "forbidden",
            }
        )

    with pytest.raises(ValidationError):
        EvaluationConfig.model_validate(
            {
                "report_version": 1,
                "calibration_bins": 5,
                "confidence_bucket_edges": [],
                "missing_confidence_policy": "not_available",
                "advisory_status": "forbidden",
            }
        )


def test_replay_config_path_and_legacy_policy_branches() -> None:
    replay = load_config(
        Path("apps/reference/domains/neocortex/config")).replay
    replay_data = replay.model_dump(mode="python")
    replay_data["wal_dir"] = None
    replay_data["features_dir"] = None
    replay_data["orders_file"] = None
    replay_data["core_log"] = None
    replay_data["feature_missing_timestamp_policy"] = "fail_closed"
    parsed = ReplayConfig.model_validate(replay_data)
    assert parsed.wal_dir == Path("ops/wal").resolve()
    assert parsed.features_dir is None
    assert parsed.orders_file is None
    assert parsed.core_log is None
    assert parsed.is_phase7 is False

    replay_data["feature_missing_timestamp_policy"] = "legacy_non_causal_file_offset"
    replay_data["legacy_feature_base_ts_ms"] = None
    with pytest.raises(ValidationError):
        ReplayConfig.model_validate(replay_data)


def test_neocortex_config_dimension_and_operating_mode_validation() -> None:
    config = load_config(Path("apps/reference/domains/neocortex/config"))
    cfg = config.model_dump(mode="python")

    cfg["neuro"]["vae"]["input_dim"] = cfg["neuro"]["vae"]["input_dim"] + 1
    with pytest.raises(ValidationError):
        NeocortexConfig.model_validate(cfg)

    cfg = config.model_dump(mode="python")
    cfg["neuro"]["ppo"]["state_dim"] = cfg["neuro"]["vae"]["latent_dim"] - 1
    with pytest.raises(ValidationError):
        NeocortexConfig.model_validate(cfg)

    cfg = config.model_dump(mode="python")
    cfg["system"]["run_mode"] = "live"
    cfg["neuro"]["performance"]["operating_mode"] = "offline_replay"
    with pytest.raises(ValidationError):
        NeocortexConfig.model_validate(cfg)

    cfg = config.model_dump(mode="python")
    cfg["system"]["run_mode"] = "live"
    cfg["neuro"]["performance"]["operating_mode"] = "live_shadow"
    cfg["neuro"]["performance"]["shadow_intent_emit_policy"] = "emit_all"
    cfg["neuro"]["performance"]["shadow_intent_decimation_stride"] = 1
    cfg["neuro"]["shadow_gates"]["startup_enforcement"] = "report_only"
    with pytest.raises(ValidationError):
        NeocortexConfig.model_validate(cfg)

    result = NeocortexConfig.validate_dimensions(
        config.neuro,
        SimpleNamespace(data={}),
    )
    assert result is config.neuro

    cfg = config.model_dump(mode="python")
    cfg["system"]["run_mode"] = "live"
    cfg["neuro"]["performance"]["operating_mode"] = "live_shadow"
    cfg["neuro"]["performance"]["shadow_intent_emit_policy"] = "emit_all"
    cfg["neuro"]["performance"]["shadow_intent_decimation_stride"] = 1
    cfg["neuro"]["shadow_gates"]["startup_enforcement"] = "report_only"
    with pytest.raises(ValidationError, match="startup_enforcement='strict'"):
        NeocortexConfig.model_validate(cfg)


def test_neocortex_config_load_fails_closed_on_missing_required_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Missing system config"):
        load_config(tmp_path)

    (tmp_path / "system.yaml").write_text(
        "trust_enabled: false\nevidence_capture: {mode: disabled, collect_observation: false, collect_authority_request: false, collect_authority_response: false, emit_shadow_decision_logged: false}\nauthority: {mode: shadow, deadline_ms: 10, fallback_policy: baseline_yaml, max_inflight_per_symbol: 1, modulation_allowlist: [bias], signal_threshold_bias_bounds: [-0.5, 0.5], cooldown_mult_bounds: [1.0, 3.0]}\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Missing ingest config"):
        load_config(tmp_path)

    (tmp_path / "ingest.yaml").write_text(
        "feature_list: [price]\nnormalization_method: zscore\nnormalization_window: 100\nnormalization_scope: per_symbol\nbuffer_size: 1\nmin_samples_before_ready: 1\nnan_strategy: zero\nprice_feature_mode: raw\ndelta_price_mode: raw\nfeature_clip_abs: {}\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Missing neuro config"):
        load_config(tmp_path)


def test_neocortex_config_main_guard_executes(tmp_path: Path, capsys) -> None:
    runpy.run_path(
        str(Path("apps/reference/domains/neocortex/config_models.py")),
        run_name="__main__",
    )
    captured = capsys.readouterr()
    assert "Config loaded successfully" in captured.out
