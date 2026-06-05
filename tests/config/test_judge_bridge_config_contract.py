from __future__ import annotations

from copy import deepcopy

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config.domains.decision_making import (
    DecisionMakingDomainConfig,
    JudgeBridgeConfig,
)


def valid_payload() -> dict:
    return {
        "enabled": False,
        "authority_mode": "shadow",
        "allowed_runtime_modes": [
            "backtest",
            "testnet",
            "hybrid_live_data_testnet_exec",
        ],
        "forbidden_runtime_modes": ["production", "live"],
        "confidence_policy": {
            "unknown_policy": "fail_closed",
            "allow_overlapping_bands": False,
            "open_bands": [{"min": 0.55, "max": 0.85, "action": "allow"}],
            "suppress_bands": [{"min": 0.90, "max": 1.00, "action": "suppress"}],
        },
        "hard_gates": {
            "judge_cannot_override": [
                "panic_killswitch",
                "exchange_filter_fail",
                "exposure_limit",
                "stale_features",
                "stale_regime",
                "order_guardian_block",
            ]
        },
        "calibration_guard": {
            "required_for_hybrid_gated": False,
            "required_for_live_gated": True,
            "accepted_artifact_path": None,
            "auto_apply": False,
        },
        "shadow_capture": {
            "enabled": False,
            "output_dir": "logs/shadow_telemetry",
            "evidence_envelope_file": "judge_evidence_envelope_v2.jsonl",
            "policy_verdict_file": "judge_policy_verdict_v2.jsonl",
            "bridge_decision_file": "judge_bridge_decision_v1.jsonl",
            "calibration_row_file": "judge_shadow_calibration_row_v1.jsonl",
            "meta_scoring": {
                "schema_version": "1.0.0",
                "agreement_weight": 0.35,
                "confidence_weight": 0.35,
                "regime_weight": 0.15,
                "historical_surface_weight": 0.10,
                "missingness_penalty_weight": 0.02,
                "freshness_penalty_weight": 1.0,
                "disagreement_penalty_weight": 0.20,
                "no_expert_penalty": 0.40,
                "unknown_cap": 0.25,
                "min_confidence": 0.0,
                "max_confidence": 1.0,
                "verdict_thresholds": {
                    "open_long_min_confidence": 0.60,
                    "open_short_min_confidence": 0.60,
                    "suppress_max_confidence": 0.20,
                    "unknown_max_evidence_score": 0.05,
                },
                "stale_policy": {
                    "stale_regime_penalty": 0.10,
                    "stale_market_penalty": 0.10,
                    "missing_execution_readiness_penalty": 0.05,
                    "missing_risk_context_penalty": 0.05,
                    "missing_portfolio_context_penalty": 0.05,
                },
                "hard_unknown_conditions": {
                    "no_strategy_experts": True,
                    "missing_regime_context": False,
                    "missing_market_context": False,
                },
                "agreement_state_scores": {
                    "agree": 1.0,
                    "single_expert": 0.45,
                    "unknown": 0.0,
                    "disagree": 0.0,
                    "no_experts": 0.0,
                },
            },
        },
    }


def test_valid_disabled_shadow_config_validates():
    cfg = JudgeBridgeConfig.model_validate(valid_payload())
    assert cfg.enabled is False
    assert cfg.authority_mode == "shadow"


def test_domains_yaml_runtime_shadow_capture_config_validates():
    data = yaml.safe_load(open("config/aurora/domains.yaml", encoding="utf-8"))
    cfg = DecisionMakingDomainConfig.model_validate(data["decision_making"])
    assert cfg.judge_bridge.enabled is True
    assert cfg.judge_bridge.authority_mode == "shadow"
    assert cfg.judge_bridge.shadow_capture.enabled is True


def test_unknown_field_rejected():
    payload = valid_payload()
    payload["hidden"] = True
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_invalid_authority_mode_rejected():
    payload = valid_payload()
    payload["authority_mode"] = "full_auto"
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_confidence_band_outside_range_rejected():
    payload = valid_payload()
    payload["confidence_policy"]["open_bands"][0]["max"] = 1.5
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_band_min_greater_equal_max_rejected():
    payload = valid_payload()
    payload["confidence_policy"]["open_bands"][0]["min"] = 0.85
    payload["confidence_policy"]["open_bands"][0]["max"] = 0.85
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_overlapping_bands_rejected():
    payload = valid_payload()
    payload["confidence_policy"]["open_bands"].append(
        {"min": 0.75, "max": 0.95, "action": "allow"}
    )
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_overlapping_bands_allowed_only_when_flag_true():
    payload = valid_payload()
    payload["confidence_policy"]["allow_overlapping_bands"] = True
    payload["confidence_policy"]["open_bands"].append(
        {"min": 0.75, "max": 0.84, "action": "allow"}
    )
    cfg = JudgeBridgeConfig.model_validate(payload)
    assert len(cfg.confidence_policy.open_bands) == 2


def test_conflicting_allow_suppress_same_range_rejected():
    payload = valid_payload()
    payload["confidence_policy"]["allow_overlapping_bands"] = True
    payload["confidence_policy"]["suppress_bands"][0]["min"] = 0.70
    payload["confidence_policy"]["suppress_bands"][0]["max"] = 0.80
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_auto_apply_true_rejected():
    payload = valid_payload()
    payload["calibration_guard"]["auto_apply"] = True
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_missing_mandatory_hard_gate_rejected():
    payload = valid_payload()
    payload["hard_gates"]["judge_cannot_override"].remove("panic_killswitch")
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_live_gated_rejected_without_accepted_artifact():
    payload = valid_payload()
    payload["enabled"] = True
    payload["authority_mode"] = "live_gated"
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_production_live_runtime_must_be_forbidden():
    payload = valid_payload()
    payload["forbidden_runtime_modes"] = ["production"]
    with pytest.raises(ValidationError):
        JudgeBridgeConfig.model_validate(payload)


def test_enabled_false_config_has_no_authority_effect():
    cfg = JudgeBridgeConfig.model_validate(valid_payload())
    assert cfg.enabled is False
    assert cfg.authority_mode == "shadow"


def hybrid_config_payload() -> dict:
    payload = deepcopy(valid_payload())
    payload["enabled"] = True
    payload["authority_mode"] = "hybrid_gated"
    return payload
