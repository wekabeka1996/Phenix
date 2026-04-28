"""
Production-shadow gate tests for P8.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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


def test_startup_enforce_report_only_returns_not_ready_report() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.shadow_gates.startup_enforcement": "report_only"},
    )
    evaluator = ShadowGateEvaluator()
    report = SimpleNamespace(
        overall_status="not_ready",
        blocking_gate_ids=["semantic.manifest_contracts"],
    )

    with patch.object(evaluator, "evaluate", return_value=report):
        returned = evaluator.enforce_startup(config, evaluated_at_ms=1_700_000_000_000)

    assert returned is report


def test_startup_strict_raises_on_not_ready_report() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.shadow_gates.startup_enforcement": "strict"},
    )
    evaluator = ShadowGateEvaluator()
    report = SimpleNamespace(
        overall_status="not_ready",
        blocking_gate_ids=["semantic.manifest_contracts"],
    )

    with patch.object(evaluator, "evaluate", return_value=report):
        with pytest.raises(ShadowGateViolationError):
            evaluator.enforce_startup(config, evaluated_at_ms=1_700_000_000_000)


def test_manifest_contract_check_can_be_disabled() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.shadow_gates.require_domain_manifest_contracts": False},
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.manifest_contracts")
    assert gate.status == "pass"


def test_manifest_contract_missing_file_blocks(tmp_path: Path) -> None:
    config = _safe_config()
    evaluator = ShadowGateEvaluator(domain_manifest_path=tmp_path / "missing-domain.yaml")

    report = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.manifest_contracts")
    assert gate.status == "fail"


def test_manifest_contract_missing_sections_blocks(tmp_path: Path) -> None:
    config = _safe_config()
    manifest_path = tmp_path / "domain.yaml"
    manifest_path.write_text(
        "domain:\n  contracts:\n    time: {}\n",
        encoding="utf-8",
    )
    evaluator = ShadowGateEvaluator(domain_manifest_path=manifest_path)

    report = evaluator.evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.manifest_contracts")
    assert gate.status == "fail"


def test_sequence_contract_rejects_invalid_inference_mode() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.sequence.inference_mode": "stateful"},
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.sequence_contract")
    assert gate.status == "fail"


def test_sequence_contract_rejects_invalid_representation_mode() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.sequence.representation_training_mode": "coupled_rows"},
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.sequence_contract")
    assert gate.status == "fail"


def test_dataset_contract_rejects_bad_ratio_sum() -> None:
    config = _mutate(
        _safe_config(),
        **{
            "neuro.dataset.split.train_ratio": 0.5,
            "neuro.dataset.split.val_ratio": 0.25,
            "neuro.dataset.split.test_ratio": 0.1,
        },
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "admission.dataset_contract")
    assert gate.status == "fail"


def test_performance_contract_rejects_invalid_operating_mode() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.performance.operating_mode": "experimental"},
    )
    gate = ShadowGateEvaluator()._check_performance_contract(config)
    assert gate.status == "fail"


def test_performance_contract_rejects_live_shadow_stride() -> None:
    config = _mutate(
        _safe_config(),
        **{
            "neuro.performance.operating_mode": "live_shadow",
            "neuro.performance.shadow_intent_emit_policy": "emit_all",
            "neuro.performance.shadow_intent_decimation_stride": 2,
        },
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "operational.performance_contract")
    assert gate.status == "fail"


def test_performance_contract_passes_fail_closed_live_shadow_policy() -> None:
    config = _mutate(
        _safe_config(),
        **{
            "neuro.performance.operating_mode": "offline_replay",
            "replay.feature_missing_timestamp_policy": "fail_closed",
        },
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    time_gate = next(g for g in report.gates if g.gate_id == "semantic.time_contract_mode")
    causal_gate = next(g for g in report.gates if g.gate_id == "causal_time.hard_gate")
    assert time_gate.status == "pass"
    assert causal_gate.status == "pass"


def test_performance_contract_rejects_offline_invalid_emit_policy() -> None:
    config = _mutate(
        _safe_config(),
        **{
            "neuro.performance.operating_mode": "offline_replay",
            "neuro.performance.shadow_intent_emit_policy": "bogus",
        },
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "operational.performance_contract")
    assert gate.status == "fail"


def test_budget_contract_rejects_queue_limit_and_flush_interval() -> None:
    queue_config = _mutate(
        _safe_config(),
        **{"neuro.performance.non_critical_queue_limit": 1},
    )
    queue_report = ShadowGateEvaluator().evaluate(
        queue_config, evaluated_at_ms=1_700_000_000_000
    )
    queue_gate = next(g for g in queue_report.gates if g.gate_id == "operational.budget_contract")
    assert queue_gate.status == "fail"

    flush_config = _mutate(
        _safe_config(),
        **{"neuro.performance.flush_interval_ms": 0},
    )
    flush_report = ShadowGateEvaluator().evaluate(
        flush_config, evaluated_at_ms=1_700_000_000_000
    )
    flush_gate = next(g for g in flush_report.gates if g.gate_id == "operational.budget_contract")
    assert flush_gate.status == "fail"


def test_policy_training_reenable_flag_blocks() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.shadow_gates.allow_policy_training_reenable": True},
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "safety.policy_training_disabled")
    assert gate.status == "fail"


def test_sequence_contract_requires_all_reset_boundaries() -> None:
    config = _mutate(
        _safe_config(),
        **{"neuro.sequence.reset_on_symbol_switch": False},
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.sequence_contract")
    assert gate.status == "fail"


def test_time_contract_warn_branch_for_offline_legacy_policy() -> None:
    config = _mutate(
        _safe_config(),
        **{
            "neuro.performance.operating_mode": "offline_replay",
            "replay.feature_missing_timestamp_policy": "legacy_non_causal_file_offset",
        },
    )
    report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)
    gate = next(g for g in report.gates if g.gate_id == "semantic.time_contract_mode")
    assert gate.status == "warn"


def test_dataset_admission_selftest_can_fail_closed() -> None:
    config = _mutate(_safe_config(), **{"neuro.ppo.policy_training_mode": "disabled"})

    class _TrainableResult(SimpleNamespace):
        pass

    fake_engine = SimpleNamespace()
    fake_engine.evaluate_sample = lambda *args, **kwargs: _TrainableResult(
        is_trainable=True
    )

    with patch(
        "apps.reference.domains.neocortex.logic.gates.shadow.DatasetPolicyEngine",
        return_value=fake_engine,
    ):
        report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)

    gate = next(g for g in report.gates if g.gate_id == "admission.dataset_selftest")
    assert gate.status == "fail"


def test_dataset_admission_selftest_blocks_unresolved_execution_sample() -> None:
    config = _mutate(_safe_config(), **{"neuro.ppo.policy_training_mode": "disabled"})

    class _TrainableResult(SimpleNamespace):
        pass

    class _FakeEngine:
        def __init__(self) -> None:
            self.calls = 0

        def evaluate_sample(self, *args, **kwargs):
            self.calls += 1
            return _TrainableResult(is_trainable=self.calls == 2)

    with patch(
        "apps.reference.domains.neocortex.logic.gates.shadow.DatasetPolicyEngine",
        return_value=_FakeEngine(),
    ):
        report = ShadowGateEvaluator().evaluate(config, evaluated_at_ms=1_700_000_000_000)

    gate = next(g for g in report.gates if g.gate_id == "admission.dataset_selftest")
    assert gate.status == "fail"
