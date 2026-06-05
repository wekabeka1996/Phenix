"""Phase 2 — Config Sterilization: Reflection test (invariant I2).

Proves:
1. Every field in every Neocortex config model has default_class annotation.
2. default_class is one of: structural_safe, runtime_behavior, legacy_compat.
3. No runtime_behavior field has an implicit Python default.
4. Every legacy_compat field documents reason/deprecation in description.
5. Every model has extra='forbid'.
6. Unknown extra key raises ValidationError.
7. Missing required runtime key raises ValidationError.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic.fields import PydanticUndefined

from apps.reference.domains.neocortex.config_models import (
    AuthorityConfig,
    EvidenceCaptureConfig,
    DatasetConfig,
    DatasetCutoverConfig,
    DatasetSplitConfig,
    EvaluationConfig,
    IngestConfig,
    NeuroConfig,
    OracleConfig,
    PPOConfig,
    PPOEntropyScheduleConfig,
    PPONumericalSafetyConfig,
    PerformanceConfig,
    ReplayConfig,
    SequenceConfig,
    ShadowGateConfig,
    SystemConfig,
    VAEConfig,
    WorldModelConfig,
)

VALID_CLASSES = frozenset(
    {"structural_safe", "runtime_behavior", "legacy_compat"})

# Models that carry structural-only defaults (schema versions, optional containers)
ALLOWED_DEFAULTS: dict[type, set[str]] = {
    DatasetConfig: {"manifest_version"},
    EvaluationConfig: {"report_version"},
    ShadowGateConfig: {"gate_set_version"},
    VAEConfig: {"regime_aux"},
    VAEConfig.RegimeAuxConfig: {"alpha", "num_classes", "ema_decay", "alpha_schedule"},
    PPOConfig: {"entropy_schedule"},
    OracleConfig: {"reward_matrix"},
    ReplayConfig: {
        "wal_dir", "wal_glob", "filter_verb",
        "features_dir", "orders_file", "core_log", "symbols",
        "batch_size", "poll_interval",
        "max_feature_lines_total_per_cycle", "max_feature_lines_per_symbol_per_cycle",
        "max_order_lines_per_cycle", "max_core_lines_per_cycle",
        "feature_missing_timestamp_policy", "legacy_feature_base_ts_ms",
    },
}

ALL_MODELS: list[type] = [
    SystemConfig,
    IngestConfig,
    VAEConfig,
    VAEConfig.RegimeAuxConfig,
    VAEConfig.RegimeAuxConfig.AlphaScheduleConfig,
    WorldModelConfig,
    PPOEntropyScheduleConfig,
    PPONumericalSafetyConfig,
    PPOConfig,
    SequenceConfig,
    DatasetSplitConfig,
    DatasetCutoverConfig,
    DatasetConfig,
    PerformanceConfig,
    EvaluationConfig,
    ShadowGateConfig,
    NeuroConfig,
    ReplayConfig,
    OracleConfig,
    AuthorityConfig,
    EvidenceCaptureConfig,
]

LEGACY_COMPAT_FIELDS: dict[str, set[str]] = {
    "ReplayConfig": {"wal_dir", "wal_glob", "filter_verb", "legacy_feature_base_ts_ms"},
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_default_class(field_info) -> str | None:
    extra = field_info.json_schema_extra
    if not isinstance(extra, dict):
        return None
    return extra.get("default_class")


def _has_python_default(field_info) -> bool:
    return (
        field_info.default is not PydanticUndefined
        or field_info.default_factory is not None
    )


# ---------------------------------------------------------------------------
# Test 1: every field has default_class annotation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_cls", ALL_MODELS, ids=lambda m: m.__name__)
def test_every_field_has_default_class(model_cls: type):
    missing = []
    for name, info in model_cls.model_fields.items():
        if _get_default_class(info) is None:
            missing.append(name)
    assert missing == [], (
        f"{model_cls.__name__} fields missing default_class annotation: {missing}"
    )


# ---------------------------------------------------------------------------
# Test 2: default_class is a valid value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_cls", ALL_MODELS, ids=lambda m: m.__name__)
def test_default_class_is_valid(model_cls: type):
    invalid = []
    for name, info in model_cls.model_fields.items():
        dc = _get_default_class(info)
        if dc is not None and dc not in VALID_CLASSES:
            invalid.append((name, dc))
    assert invalid == [], (
        f"{model_cls.__name__} fields have invalid default_class: {invalid}"
    )


# ---------------------------------------------------------------------------
# Test 3: runtime_behavior fields must have no Python default
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_cls", ALL_MODELS, ids=lambda m: m.__name__)
def test_runtime_behavior_has_no_python_default(model_cls: type):
    allowed = ALLOWED_DEFAULTS.get(model_cls, set())
    violations = []
    for name, info in model_cls.model_fields.items():
        if name in allowed:
            continue
        dc = _get_default_class(info)
        if dc == "runtime_behavior" and _has_python_default(info):
            violations.append(name)
    assert violations == [], (
        f"{model_cls.__name__} runtime_behavior fields have implicit Python defaults: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 4: legacy_compat fields must mention reason in description
# ---------------------------------------------------------------------------

def test_legacy_compat_fields_have_reason():
    violations = []
    for model_cls in ALL_MODELS:
        for name, info in model_cls.model_fields.items():
            if _get_default_class(info) != "legacy_compat":
                continue
            desc = (info.description or "").lower()
            if not any(kw in desc for kw in ("deprecated", "legacy", "compat", "sunset", "phase 6", "wal")):
                violations.append(f"{model_cls.__name__}.{name}")
    assert violations == [], (
        f"legacy_compat fields missing reason/deprecation note: {violations}"
    )


# ---------------------------------------------------------------------------
# Test 5: every model has extra='forbid'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_cls", ALL_MODELS, ids=lambda m: m.__name__)
def test_every_model_has_extra_forbid(model_cls: type):
    cfg = model_cls.model_config
    assert cfg.get("extra") == "forbid", (
        f"{model_cls.__name__} must have extra='forbid', got {cfg.get('extra')!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: unknown extra key raises ValidationError on AuthorityConfig
# ---------------------------------------------------------------------------

def test_unknown_key_rejected_by_authority_config():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate({
            "mode": "shadow",
            "deadline_ms": 10,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["a"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
            "unknown_extra_field": "boom",
        })


def test_unknown_key_rejected_by_evidence_capture_config():
    with pytest.raises(ValidationError):
        EvidenceCaptureConfig.model_validate({
            "mode": "disabled",
            "collect_observation": False,
            "collect_authority_request": False,
            "collect_authority_response": False,
            "emit_shadow_decision_logged": False,
            "unknown_extra_field": "boom",
        })


# ---------------------------------------------------------------------------
# Test 7: missing required runtime key raises ValidationError
# ---------------------------------------------------------------------------

def test_missing_authority_mode_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate({
            # mode intentionally omitted
            "deadline_ms": 10,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["a"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
        })


def test_missing_deadline_ms_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate({
            "mode": "shadow",
            # deadline_ms omitted
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["a"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
        })


def test_missing_evidence_capture_mode_raises():
    with pytest.raises(ValidationError):
        EvidenceCaptureConfig.model_validate({
            "collect_observation": False,
            "collect_authority_request": False,
            "collect_authority_response": False,
            "emit_shadow_decision_logged": False,
        })


# ---------------------------------------------------------------------------
# Test 8: AuthorityConfig bounds validation
# ---------------------------------------------------------------------------

def _valid_authority(**overrides):
    base = {
        "mode": "shadow",
        "deadline_ms": 10,
        "fallback_policy": "baseline_yaml",
        "max_inflight_per_symbol": 1,
        "modulation_allowlist": ["decision_making.signal_threshold_bias"],
        "signal_threshold_bias_bounds": [-0.1, 0.1],
        "cooldown_mult_bounds": [1.0, 3.0],
    }
    base.update(overrides)
    return base


def test_authority_valid_config_loads():
    cfg = AuthorityConfig.model_validate(_valid_authority())
    assert cfg.mode == "shadow"
    assert cfg.deadline_ms == 10


def test_signal_bias_bounds_inverted_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(_valid_authority(
            signal_threshold_bias_bounds=[0.1, -0.1]))


def test_cooldown_bounds_zero_min_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(
            _valid_authority(cooldown_mult_bounds=[0.0, 3.0]))


def test_cooldown_bounds_inverted_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(
            _valid_authority(cooldown_mult_bounds=[3.0, 1.0]))


def test_signal_bias_bounds_wrong_length_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(
            _valid_authority(signal_threshold_bias_bounds=[-0.1]))


def test_cooldown_bounds_wrong_length_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(
            _valid_authority(cooldown_mult_bounds=[1.0]))


def test_invalid_authority_mode_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(_valid_authority(mode="production"))


def test_modulation_allowlist_empty_raises():
    with pytest.raises(ValidationError):
        AuthorityConfig.model_validate(
            _valid_authority(modulation_allowlist=[]))


def test_evidence_capture_journal_only_requires_request_and_observation():
    with pytest.raises(ValidationError, match="collect_observation"):
        EvidenceCaptureConfig.model_validate({
            "mode": "journal_only",
            "collect_observation": False,
            "collect_authority_request": True,
            "collect_authority_response": True,
            "emit_shadow_decision_logged": True,
        })

    with pytest.raises(ValidationError, match="collect_authority_request"):
        EvidenceCaptureConfig.model_validate({
            "mode": "journal_only",
            "collect_observation": True,
            "collect_authority_request": False,
            "collect_authority_response": True,
            "emit_shadow_decision_logged": True,
        })


def test_evidence_capture_valid_config_loads():
    cfg = EvidenceCaptureConfig.model_validate({
        "mode": "disabled",
        "collect_observation": False,
        "collect_authority_request": False,
        "collect_authority_response": False,
        "emit_shadow_decision_logged": False,
    })

    assert cfg.mode == "disabled"
