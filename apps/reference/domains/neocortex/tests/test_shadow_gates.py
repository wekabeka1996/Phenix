"""
Production-shadow gate tests for P8.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.gates import (
    ShadowGateEvaluator,
    ShadowGateViolationError,
)
from apps.reference.domains.neocortex.main import evaluate_startup_shadow_gates


def _safe_config():
    return load_config(Path("apps/reference/domains/neocortex/config"))


def _mutate(config, **updates):
    current = config
    for path, value in updates.items():
        parts = path.split(".")
        stack = []
        node = current
        for part in parts[:-1]:
            stack.append((node, part))
            node = getattr(node, part)
        updated = node.model_copy(update={parts[-1]: value})
        for parent, attr in reversed(stack):
            updated = parent.model_copy(update={attr: updated})
        current = updated
    return current


def test_production_shadow_passes_with_safe_config():
    config = _safe_config()
    evaluator = ShadowGateEvaluator()

    report = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)

    assert report.overall_status == "ready"
    assert report.mode == "offline_replay"
    assert report.blocking_gate_ids == []


def test_startup_hard_fails_when_policy_training_enabled():
    config = _mutate(_safe_config(), **{"neuro.ppo.policy_training_mode": "execution_only"})

    with pytest.raises(ShadowGateViolationError) as exc:
        evaluate_startup_shadow_gates(
            config,
            logger=MagicMock(),
            evaluated_at_ms=1_700_000_000_000,
        )

    assert "safety.policy_training_disabled" in exc.value.report.blocking_gate_ids


def test_startup_hard_fails_when_forbidden_advisory_flag_present():
    config = _mutate(_safe_config(), **{"neuro.shadow_gates.allow_advisory_influence": True})

    with pytest.raises(ShadowGateViolationError) as exc:
        evaluate_startup_shadow_gates(
            config,
            logger=MagicMock(),
            evaluated_at_ms=1_700_000_000_000,
        )

    assert "safety.no_advisory_or_live_authority" in exc.value.report.blocking_gate_ids


def test_startup_hard_fails_when_objective_split_disabled():
    config = _mutate(_safe_config(), **{"neuro.ppo.objective_split_enforced": False})

    with pytest.raises(ShadowGateViolationError) as exc:
        evaluate_startup_shadow_gates(
            config,
            logger=MagicMock(),
            evaluated_at_ms=1_700_000_000_000,
        )

    assert "semantic.objective_split" in exc.value.report.blocking_gate_ids


def test_startup_hard_fails_when_dataset_contract_invalid():
    config = _mutate(_safe_config(), **{"neuro.dataset.manifest_version": 0})

    with pytest.raises(ShadowGateViolationError) as exc:
        evaluate_startup_shadow_gates(
            config,
            logger=MagicMock(),
            evaluated_at_ms=1_700_000_000_000,
        )

    assert "admission.dataset_contract" in exc.value.report.blocking_gate_ids


def test_live_shadow_rejects_decimation_config_via_gates():
    config = _mutate(
        _safe_config(),
        **{
            "neuro.performance.operating_mode": "live_shadow",
            "neuro.performance.shadow_intent_emit_policy": "decimate_observational",
            "neuro.performance.shadow_intent_decimation_stride": 2,
        },
    )
    evaluator = ShadowGateEvaluator()

    report = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)

    assert report.overall_status == "not_ready"
    assert "operational.performance_contract" in report.blocking_gate_ids


def test_offline_replay_accepts_allowed_observational_decimation():
    config = _mutate(
        _safe_config(),
        **{
            "neuro.performance.operating_mode": "offline_replay",
            "neuro.performance.shadow_intent_emit_policy": "decimate_observational",
            "neuro.performance.shadow_intent_decimation_stride": 4,
        },
    )
    evaluator = ShadowGateEvaluator()

    report = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)

    assert report.overall_status == "ready"
    assert report.mode == "offline_replay"


def test_gate_report_is_deterministic_for_same_config_and_timestamp():
    config = _safe_config()
    evaluator = ShadowGateEvaluator()

    first = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)
    second = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)

    assert first.model_dump(mode="python") == second.model_dump(mode="python")


def test_blocking_gates_are_machine_readable():
    config = _mutate(
        _safe_config(),
        **{
            "neuro.ppo.policy_training_mode": "execution_only",
            "neuro.shadow_gates.allow_live_authority": True,
        },
    )
    evaluator = ShadowGateEvaluator()

    report = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)

    assert report.overall_status == "not_ready"
    assert sorted(report.blocking_gate_ids) == sorted(
        ["safety.no_advisory_or_live_authority", "safety.policy_training_disabled"]
    )
    failing = {gate.gate_id: gate for gate in report.gates if gate.status == "fail"}
    assert failing["safety.policy_training_disabled"].blocking is True
    assert failing["safety.no_advisory_or_live_authority"].blocking is True
