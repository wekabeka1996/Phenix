"""
Production-shadow gate evaluator for neocortex.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, cast

import yaml
from pydantic import BaseModel, ConfigDict

from apps.reference.domains.neocortex.config_models import NeocortexConfig
from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine


GateSeverity = Literal["info", "warn", "error"]
GateStatus = Literal["pass", "warn", "fail"]


class ShadowGateResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    gate_id: str
    severity: GateSeverity
    status: GateStatus
    message: str
    blocking: bool
    evidence_anchor: Optional[str] = None


class ShadowReadinessReport(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    gate_set_version: int
    evaluated_at_ms: int
    overall_status: Literal["ready", "not_ready"]
    mode: Literal["live_shadow", "offline_replay"]
    startup_enforcement: Literal["strict", "report_only"]
    gates: List[ShadowGateResult]
    blocking_gate_ids: List[str]


class ShadowGateViolationError(RuntimeError):
    def __init__(self, report: ShadowReadinessReport):
        self.report = report
        gate_ids = ", ".join(report.blocking_gate_ids) or "unknown"
        super().__init__(f"Neocortex production-shadow gates failed: {gate_ids}")


class ShadowGateEvaluator:
    """Evaluate production-shadow readiness from canonical config + manifest."""

    def __init__(self, *, domain_manifest_path: Optional[Path] = None) -> None:
        self.domain_manifest_path = (
            Path(domain_manifest_path).resolve()
            if domain_manifest_path is not None
            else Path(__file__).resolve().parents[2] / "domain.yaml"
        )

    def evaluate(
        self,
        config: NeocortexConfig,
        *,
        evaluated_at_ms: Optional[int] = None,
    ) -> ShadowReadinessReport:
        gates: List[ShadowGateResult] = []
        gates.append(self._check_manifest_contracts(config))
        gates.append(self._check_policy_training_disabled(config))
        gates.append(self._check_forbidden_authority_flags(config))
        gates.append(self._check_objective_split(config))
        gates.append(self._check_sequence_contract(config))
        gates.append(self._check_dataset_contract(config))
        gates.append(self._check_performance_contract(config))
        gates.append(self._check_time_contract_mode(config))
        gates.append(self._check_causal_time_hard_gate(config))
        gates.append(self._check_dataset_admission_selftest(config))
        gates.append(self._check_operational_budget_contract(config))

        blocking_gate_ids = [
            gate.gate_id
            for gate in gates
            if gate.blocking and gate.status == "fail"
        ]
        overall_status: Literal["ready", "not_ready"] = (
            "ready" if not blocking_gate_ids else "not_ready"
        )

        return ShadowReadinessReport(
            gate_set_version=int(config.neuro.shadow_gates.gate_set_version),
            evaluated_at_ms=int(
                evaluated_at_ms if evaluated_at_ms is not None else time.time() * 1000.0
            ),
            overall_status=overall_status,
            mode=cast(Literal["live_shadow", "offline_replay"], str(config.neuro.performance.operating_mode)),
            startup_enforcement=cast(Literal["strict", "report_only"], str(config.neuro.shadow_gates.startup_enforcement)),
            gates=gates,
            blocking_gate_ids=blocking_gate_ids,
        )

    def enforce_startup(
        self,
        config: NeocortexConfig,
        *,
        evaluated_at_ms: Optional[int] = None,
    ) -> ShadowReadinessReport:
        report = self.evaluate(config, evaluated_at_ms=evaluated_at_ms)
        if (
            config.neuro.shadow_gates.startup_enforcement == "strict"
            and report.overall_status != "ready"
        ):
            raise ShadowGateViolationError(report)
        return report

    def _pass(
        self,
        gate_id: str,
        message: str,
        *,
        severity: GateSeverity = "info",
        evidence_anchor: Optional[str] = None,
    ) -> ShadowGateResult:
        return ShadowGateResult(
            gate_id=gate_id,
            severity=severity,
            status="pass",
            message=message,
            blocking=False,
            evidence_anchor=evidence_anchor,
        )

    def _warn(
        self,
        gate_id: str,
        message: str,
        *,
        evidence_anchor: Optional[str] = None,
    ) -> ShadowGateResult:
        return ShadowGateResult(
            gate_id=gate_id,
            severity="warn",
            status="warn",
            message=message,
            blocking=False,
            evidence_anchor=evidence_anchor,
        )

    def _fail(
        self,
        gate_id: str,
        message: str,
        *,
        evidence_anchor: Optional[str] = None,
    ) -> ShadowGateResult:
        return ShadowGateResult(
            gate_id=gate_id,
            severity="error",
            status="fail",
            message=message,
            blocking=True,
            evidence_anchor=evidence_anchor,
        )

    def _check_manifest_contracts(self, config: NeocortexConfig) -> ShadowGateResult:
        if not config.neuro.shadow_gates.require_domain_manifest_contracts:
            return self._pass(
                "semantic.manifest_contracts",
                "Domain manifest contract checks disabled by explicit gate config.",
                evidence_anchor="config.neuro.shadow_gates.require_domain_manifest_contracts=false",
            )
        if not self.domain_manifest_path.exists():
            return self._fail(
                "semantic.manifest_contracts",
                "domain.yaml missing; cannot prove production-shadow contract surface.",
                evidence_anchor=str(self.domain_manifest_path),
            )
        with open(self.domain_manifest_path, "r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle) or {}
        contracts = (((manifest or {}).get("domain") or {}).get("contracts") or {})
        required = {
            "time",
            "episode_lifecycle",
            "reward",
            "objectives",
            "sequence",
            "dataset",
            "performance",
        }
        missing = sorted(required.difference(contracts.keys()))
        if missing:
            return self._fail(
                "semantic.manifest_contracts",
                f"domain.yaml missing required contract sections: {missing}",
                evidence_anchor=str(self.domain_manifest_path),
            )
        return self._pass(
            "semantic.manifest_contracts",
            "Domain manifest exposes required production-shadow contract sections.",
            evidence_anchor=str(self.domain_manifest_path),
        )

    def _check_policy_training_disabled(self, config: NeocortexConfig) -> ShadowGateResult:
        if config.neuro.shadow_gates.allow_policy_training_reenable:
            return self._fail(
                "safety.policy_training_disabled",
                "allow_policy_training_reenable=true is forbidden in production shadow.",
                evidence_anchor="config.neuro.shadow_gates.allow_policy_training_reenable",
            )
        if config.neuro.ppo.policy_training_mode != "disabled":
            return self._fail(
                "safety.policy_training_disabled",
                f"policy_training_mode={config.neuro.ppo.policy_training_mode!r} is forbidden in production shadow.",
                evidence_anchor="config.neuro.ppo.policy_training_mode",
            )
        return self._pass(
            "safety.policy_training_disabled",
            "Policy training remains blocked for production shadow.",
            evidence_anchor="config.neuro.ppo.policy_training_mode=disabled",
        )

    def _check_forbidden_authority_flags(self, config: NeocortexConfig) -> ShadowGateResult:
        if config.neuro.shadow_gates.allow_advisory_influence:
            return self._fail(
                "safety.no_advisory_or_live_authority",
                "allow_advisory_influence=true is forbidden in production shadow.",
                evidence_anchor="config.neuro.shadow_gates.allow_advisory_influence",
            )
        if config.neuro.shadow_gates.allow_live_authority:
            return self._fail(
                "safety.no_advisory_or_live_authority",
                "allow_live_authority=true is forbidden in production shadow.",
                evidence_anchor="config.neuro.shadow_gates.allow_live_authority",
            )
        return self._pass(
            "safety.no_advisory_or_live_authority",
            "Advisory influence and live authority remain blocked.",
            evidence_anchor="config.neuro.shadow_gates.allow_* = false",
        )

    def _check_objective_split(self, config: NeocortexConfig) -> ShadowGateResult:
        if not bool(config.neuro.ppo.objective_split_enforced):
            return self._fail(
                "semantic.objective_split",
                "objective_split_enforced=false is forbidden in production shadow.",
                evidence_anchor="config.neuro.ppo.objective_split_enforced",
            )
        return self._pass(
            "semantic.objective_split",
            "Objective split remains enforced.",
            evidence_anchor="config.neuro.ppo.objective_split_enforced=true",
        )

    def _check_sequence_contract(self, config: NeocortexConfig) -> ShadowGateResult:
        sequence = config.neuro.sequence
        if sequence.inference_mode != "stateless_per_event":
            return self._fail(
                "semantic.sequence_contract",
                "Unsupported sequence inference mode for production shadow.",
                evidence_anchor="config.neuro.sequence.inference_mode",
            )
        if sequence.representation_training_mode != "independent_rows":
            return self._fail(
                "semantic.sequence_contract",
                "Unsupported representation training mode for production shadow.",
                evidence_anchor="config.neuro.sequence.representation_training_mode",
            )
        if not all(
            (
                sequence.reset_on_replay_start,
                sequence.reset_on_symbol_switch,
                sequence.reset_on_objective_family_switch,
                sequence.reset_on_episode_boundary,
            )
        ):
            return self._fail(
                "semantic.sequence_contract",
                "All canonical sequence reset boundaries must remain enabled.",
                evidence_anchor="config.neuro.sequence.reset_on_*",
            )
        return self._pass(
            "semantic.sequence_contract",
            "Narrowed sequence contract remains active.",
            evidence_anchor="config.neuro.sequence",
        )

    def _check_dataset_contract(self, config: NeocortexConfig) -> ShadowGateResult:
        dataset = config.neuro.dataset
        if int(dataset.manifest_version) < 1:
            return self._fail(
                "admission.dataset_contract",
                "Dataset manifest_version must be >= 1.",
                evidence_anchor="config.neuro.dataset.manifest_version",
            )
        split_total = (
            float(dataset.split.train_ratio)
            + float(dataset.split.val_ratio)
            + float(dataset.split.test_ratio)
        )
        if abs(split_total - 1.0) > 1e-6:
            return self._fail(
                "admission.dataset_contract",
                "Dataset split ratios must sum to 1.0.",
                evidence_anchor="config.neuro.dataset.split",
            )
        return self._pass(
            "admission.dataset_contract",
            "Dataset provenance/eligibility manifest contract is configured.",
            evidence_anchor="config.neuro.dataset",
        )

    def _check_performance_contract(self, config: NeocortexConfig) -> ShadowGateResult:
        perf = config.neuro.performance
        if perf.operating_mode not in {"live_shadow", "offline_replay"}:
            return self._fail(
                "operational.performance_contract",
                f"Unsupported operating_mode={perf.operating_mode!r}.",
                evidence_anchor="config.neuro.performance.operating_mode",
            )
        if perf.operating_mode == "live_shadow":
            if perf.shadow_intent_emit_policy != "emit_all":
                return self._fail(
                    "operational.performance_contract",
                    "live_shadow requires full shadow emission semantics.",
                    evidence_anchor="config.neuro.performance.shadow_intent_emit_policy",
                )
            if int(perf.shadow_intent_decimation_stride) != 1:
                return self._fail(
                    "operational.performance_contract",
                    "live_shadow forbids observational shadow decimation.",
                    evidence_anchor="config.neuro.performance.shadow_intent_decimation_stride",
                )
        else:
            if perf.shadow_intent_emit_policy not in {"emit_all", "decimate_observational"}:
                return self._fail(
                    "operational.performance_contract",
                    "offline_replay shadow emit policy is unsupported.",
                    evidence_anchor="config.neuro.performance.shadow_intent_emit_policy",
                )
        return self._pass(
            "operational.performance_contract",
            "Performance/replay mode contract is self-consistent.",
            evidence_anchor="config.neuro.performance",
        )

    def _check_time_contract_mode(self, config: NeocortexConfig) -> ShadowGateResult:
        policy = config.replay.feature_missing_timestamp_policy
        if config.neuro.performance.operating_mode == "live_shadow":
            if policy != "fail_closed":
                return self._fail(
                    "semantic.time_contract_mode",
                    "live_shadow requires fail-closed feature timestamp policy.",
                    evidence_anchor="config.replay.feature_missing_timestamp_policy",
                )
            return self._pass(
                "semantic.time_contract_mode",
                "live_shadow uses fail-closed causal timestamp policy.",
                evidence_anchor="config.replay.feature_missing_timestamp_policy=fail_closed",
            )
        if policy == "legacy_non_causal_file_offset":
            return self._warn(
                "semantic.time_contract_mode",
                "offline_replay uses legacy non-causal feature compatibility; dataset gates keep causal-sensitive trainable paths blocked.",
                evidence_anchor="config.replay.feature_missing_timestamp_policy=legacy_non_causal_file_offset",
            )
        return self._pass(
            "semantic.time_contract_mode",
            "Replay timestamp policy is causally strict.",
            evidence_anchor="config.replay.feature_missing_timestamp_policy",
        )

    def _check_dataset_admission_selftest(self, config: NeocortexConfig) -> ShadowGateResult:
        engine = DatasetPolicyEngine(
            config.neuro.dataset,
            policy_training_mode=config.neuro.ppo.policy_training_mode,
            representation_training_mode=config.neuro.sequence.representation_training_mode,
            sequence_inference_mode=config.neuro.sequence.inference_mode,
        )
        policy_eval = None
        if config.neuro.ppo.policy_training_mode == "disabled":
            policy_eval = engine.evaluate_sample(
                {
                    "event_ts_ms": 1_700_000_000_100,
                    "symbol": "BTCUSDT",
                    "trade_id": "trade-1",
                    "lifecycle_id": "life-1",
                    "reward_complete": True,
                    "sequence_contract_mode": config.neuro.sequence.inference_mode,
                },
                objective_family="policy",
                source_type="gate_selftest",
                source_ref="policy-selftest",
                source_event_type="POLICY_SAMPLE",
                ingestion_mode=str(config.system.run_mode),
            )
        unresolved_eval = engine.evaluate_sample(
            {
                "event_ts_ms": 1_700_000_000_200,
                "symbol": "BTCUSDT",
                "trade_id": "trade-2",
                "reward_complete": True,
                "unresolved_lifecycle": True,
            },
            objective_family="execution_quality",
            source_type="gate_selftest",
            source_ref="execution-selftest",
            source_event_type="POSITION_CLOSED",
            ingestion_mode=str(config.system.run_mode),
        )
        if policy_eval is not None and policy_eval.is_trainable:
            return self._fail(
                "admission.dataset_selftest",
                "Policy sample self-test became trainable under production shadow.",
                evidence_anchor="DatasetPolicyEngine(policy)",
            )
        if unresolved_eval.is_trainable:
            return self._fail(
                "admission.dataset_selftest",
                "Unresolved execution sample self-test became trainable.",
                evidence_anchor="DatasetPolicyEngine(execution_quality)",
            )
        return self._pass(
            "admission.dataset_selftest",
            "Dataset admission self-tests keep policy and unresolved execution samples out of trainable paths.",
            evidence_anchor="DatasetPolicyEngine self-test",
        )

    def _check_operational_budget_contract(self, config: NeocortexConfig) -> ShadowGateResult:
        perf = config.neuro.performance
        if int(perf.non_critical_queue_limit) < max(
            int(perf.shadow_log_flush_threshold),
            int(perf.telemetry_flush_threshold),
        ):
            return self._fail(
                "operational.budget_contract",
                "non_critical_queue_limit must be >= flush thresholds.",
                evidence_anchor="config.neuro.performance.non_critical_queue_limit",
            )
        if int(perf.flush_interval_ms) <= 0:
            return self._fail(
                "operational.budget_contract",
                "flush_interval_ms must be > 0.",
                evidence_anchor="config.neuro.performance.flush_interval_ms",
            )
        return self._pass(
            "operational.budget_contract",
            "Operational buffer/flush budget contract is sane.",
            evidence_anchor="config.neuro.performance.{queue_limit,flush_*}",
        )
    def _check_causal_time_hard_gate(self, config: NeocortexConfig) -> ShadowGateResult:
        """Phase 1 I3 hard gate: production-shadow must never accept non-causal timestamp policy.

        Fails closed if feature_missing_timestamp_policy=legacy_non_causal_file_offset
        when operating_mode=live_shadow.
        Also fails if ANY non-fail_closed policy is configured for live_shadow.
        In offline_replay this is a warn-only gate (diagnostic legacy is allowed but dataset
        admission keeps non-causal rows diagnostics_only).
        """
        policy = config.replay.feature_missing_timestamp_policy
        mode = config.neuro.performance.operating_mode

        if mode == "live_shadow":
            if policy != "fail_closed":
                return self._fail(
                    "causal_time.hard_gate",
                    (
                        f"Production-shadow (live_shadow) requires "
                        f"feature_missing_timestamp_policy='fail_closed'; "
                        f"got {policy!r}. Non-causal timestamps cannot become trainable "
                        f"or authority-adjacent."
                    ),
                    evidence_anchor="config.replay.feature_missing_timestamp_policy",
                )
            return self._pass(
                "causal_time.hard_gate",
                "I3 causal time hard gate: live_shadow uses fail_closed timestamp policy.",
                evidence_anchor="config.replay.feature_missing_timestamp_policy=fail_closed",
            )

        # offline_replay: allow legacy compat only if diagnostics_legacy is explicitly declared.
        # Rows are still kept non-trainable by parser I3 fields; this gate documents the contract.
        if policy == "legacy_non_causal_file_offset":
            return self._warn(
                "causal_time.hard_gate",
                (
                    "offline_replay uses legacy_non_causal_file_offset policy. "
                    "All non-causal rows will have trainable=false and "
                    "dataset_visibility=diagnostics_only per I3."
                ),
                evidence_anchor="config.replay.feature_missing_timestamp_policy=legacy_non_causal_file_offset",
            )
        return self._pass(
            "causal_time.hard_gate",
            "I3 causal time hard gate: causal timestamp policy is strictest available.",
            evidence_anchor=f"config.replay.feature_missing_timestamp_policy={policy!r}",
        )
