"""
Hot-path coverage gap tests for shadow.py branch closure.

Targets uncovered lines: 108-114, 167, 173, 192, 205, 211, 224, 230, 243,
257, 263, 276, 290, 301, 315, 321-332, 334-338, 349-354, 361-364,
380-396, 411-420, 434-443, 463-473, 482-490.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.gates.shadow import (
    ShadowGateEvaluator,
    ShadowGateViolationError,
)

CONFIG_DIR = (
    Path(__file__).resolve().parents[4]
    / "apps" / "reference" / "domains" / "neocortex" / "config"
)


def _base_config():
    return load_config(CONFIG_DIR)


def _patch_config(base, **path_updates):
    """Return a deeply-patched config via Pydantic model_copy."""
    config = base
    for dotted_path, value in path_updates.items():
        parts = dotted_path.split(".")
        obj = config
        for part in parts[:-1]:
            obj = getattr(obj, part)
        final_attr = parts[-1]
        parent_parts = parts[:-1]
        # rebuild from innermost outward
        updated = obj.model_copy(update={final_attr: value})
        for part in reversed(parent_parts):
            parent = config
            for p in parent_parts[: parent_parts.index(part)]:
                parent = getattr(parent, p)
            updated = parent.model_copy(update={part: updated})
            parent_parts = parent_parts[: parent_parts.index(part)]
        config = updated
    return config


def _live_shadow_config(base=None):
    """Produce a live_shadow config with fail_closed timestamp policy."""
    cfg = base or _base_config()
    neuro = cfg.neuro.model_copy(
        update={
            "performance": cfg.neuro.performance.model_copy(
                update={"operating_mode": "live_shadow"}
            )
        }
    )
    replay = cfg.replay.model_copy(
        update={"feature_missing_timestamp_policy": "fail_closed"}
    )
    return cfg.model_copy(update={"neuro": neuro, "replay": replay})


def setup_function():
    pass  # stateless evaluator, no counters to reset


# ---------------------------------------------------------------------------
# enforce_startup (lines 108-114)
# ---------------------------------------------------------------------------

class TestEnforceStartup:
    def test_enforce_startup_passes_when_ready(self):
        cfg = _base_config()
        report = ShadowGateEvaluator().enforce_startup(cfg)
        assert report is not None

    def test_enforce_startup_raises_when_strict_and_not_ready(self):
        cfg = _base_config()
        neuro = cfg.neuro.model_copy(
            update={
                "shadow_gates": cfg.neuro.shadow_gates.model_copy(
                    update={"startup_enforcement": "strict"}
                )
            }
        )
        cfg = cfg.model_copy(update={"neuro": neuro})
        evaluator = ShadowGateEvaluator()
        # Patch the evaluate result to return not-ready
        fake_report = SimpleNamespace(overall_status="not_ready", model_dump_json=lambda: "{}")
        with patch.object(evaluator, "evaluate", return_value=fake_report):
            with pytest.raises(ShadowGateViolationError):
                evaluator.enforce_startup(cfg)

    def test_enforce_startup_report_only_does_not_raise_when_not_ready(self):
        cfg = _base_config()
        neuro = cfg.neuro.model_copy(
            update={
                "shadow_gates": cfg.neuro.shadow_gates.model_copy(
                    update={"startup_enforcement": "report_only"}
                )
            }
        )
        cfg = cfg.model_copy(update={"neuro": neuro})
        evaluator = ShadowGateEvaluator()
        fake_report = SimpleNamespace(overall_status="not_ready", model_dump_json=lambda: "{}")
        with patch.object(evaluator, "evaluate", return_value=fake_report):
            report = evaluator.enforce_startup(cfg)
        assert report.overall_status == "not_ready"


# ---------------------------------------------------------------------------
# _check_manifest_contracts (lines 167, 173, 192)
# ---------------------------------------------------------------------------

class TestManifestContracts:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_manifest_contracts(cfg)

    def test_manifest_contracts_disabled_by_gate_config(self):
        cfg = _base_config()
        shadow_gates = cfg.neuro.shadow_gates.model_copy(
            update={"require_domain_manifest_contracts": False}
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"shadow_gates": shadow_gates})}
        )
        result = self._eval(cfg)
        assert result.status == "pass"
        assert result.blocking is False

    def test_manifest_contracts_missing_domain_yaml(self, tmp_path):
        cfg = _base_config()
        evaluator = ShadowGateEvaluator()
        evaluator.domain_manifest_path = tmp_path / "nonexistent.yaml"
        result = evaluator._check_manifest_contracts(cfg)
        assert result.status == "fail"
        assert result.blocking is True

    def test_manifest_contracts_missing_required_sections(self, tmp_path):
        import yaml

        manifest = {"domain": {"contracts": {"time": {}, "episode_lifecycle": {}}}}
        path = tmp_path / "domain.yaml"
        path.write_text(yaml.dump(manifest), encoding="utf-8")
        cfg = _base_config()
        evaluator = ShadowGateEvaluator()
        evaluator.domain_manifest_path = path
        result = evaluator._check_manifest_contracts(cfg)
        assert result.status == "fail"
        assert "missing required contract sections" in result.message


# ---------------------------------------------------------------------------
# _check_policy_training_disabled (lines 205, 211)
# ---------------------------------------------------------------------------

class TestPolicyTrainingDisabled:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_policy_training_disabled(cfg)

    def test_allow_policy_training_reenable_flag_fails(self):
        cfg = _base_config()
        shadow_gates = cfg.neuro.shadow_gates.model_copy(
            update={"allow_policy_training_reenable": True}
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"shadow_gates": shadow_gates})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "allow_policy_training_reenable" in result.message

    def test_policy_training_mode_enabled_fails(self):
        cfg = _base_config()
        ppo = cfg.neuro.ppo.model_copy(update={"policy_training_mode": "online"})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"ppo": ppo})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "policy_training_mode" in result.message


# ---------------------------------------------------------------------------
# _check_forbidden_authority_flags (lines 224, 230)
# ---------------------------------------------------------------------------

class TestForbiddenAuthorityFlags:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_forbidden_authority_flags(cfg)

    def test_allow_advisory_influence_fails(self):
        cfg = _base_config()
        shadow_gates = cfg.neuro.shadow_gates.model_copy(
            update={"allow_advisory_influence": True}
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"shadow_gates": shadow_gates})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "allow_advisory_influence" in result.message

    def test_allow_live_authority_fails(self):
        cfg = _base_config()
        shadow_gates = cfg.neuro.shadow_gates.model_copy(
            update={"allow_live_authority": True}
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"shadow_gates": shadow_gates})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "allow_live_authority" in result.message


# ---------------------------------------------------------------------------
# _check_objective_split (line 243)
# ---------------------------------------------------------------------------

class TestObjectiveSplit:
    def test_objective_split_not_enforced_fails(self):
        cfg = _base_config()
        ppo = cfg.neuro.ppo.model_copy(update={"objective_split_enforced": False})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"ppo": ppo})}
        )
        result = ShadowGateEvaluator()._check_objective_split(cfg)
        assert result.status == "fail"
        assert result.blocking is True


# ---------------------------------------------------------------------------
# _check_sequence_contract (lines 257, 263, 276)
# ---------------------------------------------------------------------------

class TestSequenceContract:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_sequence_contract(cfg)

    def test_bad_inference_mode_fails(self):
        cfg = _base_config()
        seq = cfg.neuro.sequence.model_copy(update={"inference_mode": "stateful"})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"sequence": seq})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "inference mode" in result.message.lower()

    def test_bad_representation_training_mode_fails(self):
        cfg = _base_config()
        seq = cfg.neuro.sequence.model_copy(
            update={"representation_training_mode": "shared_batch"}
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"sequence": seq})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "representation training" in result.message.lower()

    def test_reset_flag_disabled_fails(self):
        cfg = _base_config()
        seq = cfg.neuro.sequence.model_copy(update={"reset_on_replay_start": False})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"sequence": seq})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "reset" in result.message.lower()


# ---------------------------------------------------------------------------
# _check_dataset_contract (lines 290, 301)
# ---------------------------------------------------------------------------

class TestDatasetContract:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_dataset_contract(cfg)

    def test_manifest_version_below_1_fails(self):
        cfg = _base_config()
        dataset = cfg.neuro.dataset.model_copy(update={"manifest_version": 0})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"dataset": dataset})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "manifest_version" in result.message

    def test_split_ratio_sum_not_1_fails(self):
        cfg = _base_config()
        split = cfg.neuro.dataset.split.model_copy(
            update={"train_ratio": 0.8, "val_ratio": 0.1, "test_ratio": 0.5}
        )
        dataset = cfg.neuro.dataset.model_copy(update={"split": split})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"dataset": dataset})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "sum to 1.0" in result.message


# ---------------------------------------------------------------------------
# _check_performance_contract (lines 315, 321-332, 334-338)
# ---------------------------------------------------------------------------

class TestPerformanceContract:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_performance_contract(cfg)

    def test_bad_operating_mode_fails(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(update={"operating_mode": "live_enforce"})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"performance": perf})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "operating_mode" in result.message

    def test_live_shadow_non_emit_all_policy_fails(self):
        cfg = _live_shadow_config()
        perf = cfg.neuro.performance.model_copy(
            update={"shadow_intent_emit_policy": "decimate_observational"}
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"performance": perf})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "live_shadow" in result.message

    def test_live_shadow_decimation_stride_not_1_fails(self):
        cfg = _live_shadow_config()
        perf = cfg.neuro.performance.model_copy(
            update={
                "shadow_intent_emit_policy": "emit_all",
                "shadow_intent_decimation_stride": 2,
            }
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"performance": perf})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "decimation" in result.message.lower()

    def test_offline_replay_bad_emit_policy_fails(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(
            update={
                "operating_mode": "offline_replay",
                "shadow_intent_emit_policy": "invalid_policy",
            }
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"performance": perf})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "offline_replay" in result.message


# ---------------------------------------------------------------------------
# _check_time_contract_mode (lines 349-354, 361-364)
# ---------------------------------------------------------------------------

class TestTimeContractMode:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_time_contract_mode(cfg)

    def test_live_shadow_non_fail_closed_policy_fails(self):
        cfg = _live_shadow_config()
        replay = cfg.replay.model_copy(
            update={"feature_missing_timestamp_policy": "legacy_non_causal_file_offset"}
        )
        cfg = cfg.model_copy(update={"replay": replay})
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "fail-closed" in result.message.lower()

    def test_offline_replay_legacy_policy_warns(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(update={"operating_mode": "offline_replay"})
        replay = cfg.replay.model_copy(
            update={"feature_missing_timestamp_policy": "legacy_non_causal_file_offset"}
        )
        cfg = cfg.model_copy(
            update={
                "neuro": cfg.neuro.model_copy(update={"performance": perf}),
                "replay": replay,
            }
        )
        result = self._eval(cfg)
        assert result.status == "warn"
        assert result.blocking is False


# ---------------------------------------------------------------------------
# _check_dataset_admission_selftest (lines 380-396, 411-420)
# ---------------------------------------------------------------------------

class TestDatasetAdmissionSelftest:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_dataset_admission_selftest(cfg)

    def test_selftest_passes_with_default_config(self):
        cfg = _base_config()
        result = self._eval(cfg)
        assert result.status == "pass"

    def test_selftest_policy_eval_path_exercised(self):
        """Config with policy_training_mode=disabled triggers policy_eval branch."""
        cfg = _base_config()
        ppo = cfg.neuro.ppo.model_copy(update={"policy_training_mode": "disabled"})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"ppo": ppo})}
        )
        result = self._eval(cfg)
        # Should pass (policy sample must NOT be trainable)
        assert result.status == "pass"

    def test_selftest_fails_if_policy_sample_becomes_trainable(self):
        cfg = _base_config()
        # Patch engine so policy_eval.is_trainable = True
        fake_trainable = SimpleNamespace(is_trainable=True, eligibility_status="trainable")
        fake_blocked = SimpleNamespace(is_trainable=False, eligibility_status="diagnostics_only")
        from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine
        with patch.object(
            DatasetPolicyEngine, "evaluate_sample",
            side_effect=[fake_trainable, fake_blocked],
        ):
            result = self._eval(cfg)
        assert result.status == "fail"
        assert "trainable" in result.message.lower()

    def test_selftest_fails_if_unresolved_sample_becomes_trainable(self):
        cfg = _base_config()
        ppo = cfg.neuro.ppo.model_copy(update={"policy_training_mode": "disabled"})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"ppo": ppo})}
        )
        fake_blocked = SimpleNamespace(is_trainable=False, eligibility_status="diagnostics_only")
        fake_trainable = SimpleNamespace(is_trainable=True, eligibility_status="trainable")
        from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine
        with patch.object(
            DatasetPolicyEngine, "evaluate_sample",
            side_effect=[fake_blocked, fake_trainable],
        ):
            result = self._eval(cfg)
        assert result.status == "fail"
        assert "unresolved" in result.message.lower()


# ---------------------------------------------------------------------------
# _check_operational_budget_contract (lines 434-443)
# ---------------------------------------------------------------------------

class TestOperationalBudgetContract:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_operational_budget_contract(cfg)

    def test_queue_limit_below_flush_threshold_fails(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(
            update={
                "non_critical_queue_limit": 1,
                "shadow_log_flush_threshold": 100,
            }
        )
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"performance": perf})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "non_critical_queue_limit" in result.message

    def test_flush_interval_zero_fails(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(update={"flush_interval_ms": 0})
        cfg = cfg.model_copy(
            update={"neuro": cfg.neuro.model_copy(update={"performance": perf})}
        )
        result = self._eval(cfg)
        assert result.status == "fail"
        assert "flush_interval_ms" in result.message


# ---------------------------------------------------------------------------
# _check_causal_time_hard_gate (lines 463-473, 482-490)
# ---------------------------------------------------------------------------

class TestCausalTimeHardGate:
    def _eval(self, cfg):
        return ShadowGateEvaluator()._check_causal_time_hard_gate(cfg)

    def test_live_shadow_non_fail_closed_is_hard_fail(self):
        cfg = _live_shadow_config()
        replay = cfg.replay.model_copy(
            update={"feature_missing_timestamp_policy": "legacy_non_causal_file_offset"}
        )
        cfg = cfg.model_copy(update={"replay": replay})
        result = self._eval(cfg)
        assert result.status == "fail"
        assert result.blocking is True
        assert "fail_closed" in result.message

    def test_live_shadow_fail_closed_passes_hard_gate(self):
        cfg = _live_shadow_config()
        result = self._eval(cfg)
        assert result.status == "pass"
        assert "I3 causal time hard gate" in result.message

    def test_offline_replay_legacy_policy_warns_hard_gate(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(update={"operating_mode": "offline_replay"})
        replay = cfg.replay.model_copy(
            update={"feature_missing_timestamp_policy": "legacy_non_causal_file_offset"}
        )
        cfg = cfg.model_copy(
            update={
                "neuro": cfg.neuro.model_copy(update={"performance": perf}),
                "replay": replay,
            }
        )
        result = self._eval(cfg)
        assert result.status == "warn"
        assert result.blocking is False
        assert "legacy" in result.message.lower()

    def test_offline_replay_strict_policy_passes_hard_gate(self):
        cfg = _base_config()
        perf = cfg.neuro.performance.model_copy(update={"operating_mode": "offline_replay"})
        replay = cfg.replay.model_copy(
            update={"feature_missing_timestamp_policy": "fail_closed"}
        )
        cfg = cfg.model_copy(
            update={
                "neuro": cfg.neuro.model_copy(update={"performance": perf}),
                "replay": replay,
            }
        )
        result = self._eval(cfg)
        assert result.status == "pass"
