"""
P9 offline evaluator / calibration / disagreement engine.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from apps.reference.domains.neocortex.config_models import EvaluationConfig, NeocortexConfig
from apps.reference.domains.neocortex.logic.datasets.contracts import DatasetEvaluatedSample
from apps.reference.domains.neocortex.logic.gates import ShadowGateEvaluator
from apps.reference.domains.neocortex.logic.gates.shadow import ShadowReadinessReport

from .contracts import (
    AdvisoryReadinessPrereqReport,
    CalibrationBinSummary,
    CalibrationReport,
    DisagreementReport,
    ShadowDisagreementSample,
    ShadowEvaluationReport,
)


INCLUDED_STATUSES = {"trainable", "eval_only", "diagnostics_only"}
EXCLUDED_STATUSES = {"quarantined", "rejected"}


class ShadowOfflineEvaluator:
    """Deterministic offline evaluator for neocortex shadow outputs."""

    def __init__(self, config: EvaluationConfig) -> None:
        self.config = config

    def evaluate_regime_supervision(
        self,
        samples: Sequence[DatasetEvaluatedSample],
        *,
        evaluated_at_ms: Optional[int] = None,
    ) -> tuple[ShadowEvaluationReport, CalibrationReport]:
        normalized = self._normalize_dataset_samples(
            samples,
            expected_family="regime_supervision",
        )
        report = self._build_regime_report(
            normalized,
            evaluated_at_ms=self._resolve_eval_time(evaluated_at_ms),
        )
        calibration = self._build_regime_calibration_report(
            normalized,
            evaluated_at_ms=report.evaluated_at_ms,
        )
        return report, calibration

    def evaluate_execution_quality(
        self,
        samples: Sequence[DatasetEvaluatedSample],
        *,
        evaluated_at_ms: Optional[int] = None,
    ) -> ShadowEvaluationReport:
        normalized = self._normalize_dataset_samples(
            samples,
            expected_family="execution_quality",
        )
        return self._build_execution_report(
            normalized,
            evaluated_at_ms=self._resolve_eval_time(evaluated_at_ms),
        )

    def evaluate_disagreement(
        self,
        comparisons: Sequence[ShadowDisagreementSample | Mapping[str, Any]],
        *,
        evaluated_at_ms: Optional[int] = None,
    ) -> DisagreementReport:
        normalized = self._normalize_disagreement_samples(comparisons)
        comparable = [
            item for item in normalized
            if item.comparison_status == "comparable"
            and item.aurora_action is not None
            and item.shadow_action is not None
        ]
        disagreements = [
            item for item in comparable
            if item.shadow_action != item.aurora_action
        ]
        by_symbol = Counter(item.symbol for item in disagreements)
        by_regime = Counter((item.regime or "unknown") for item in disagreements)
        by_confidence_bucket = Counter(
            self._bucket_confidence(item.shadow_confidence)
            for item in disagreements
        )
        severity_buckets = Counter(
            (item.severity or "unclassified") for item in disagreements
        )
        unresolved_count = sum(
            1
            for item in normalized
            if item.comparison_status != "comparable"
            or item.aurora_action is None
        )
        total_compared = len(comparable)
        disagreement_count = len(disagreements)
        disagreement_rate = (
            disagreement_count / total_compared if total_compared else 0.0
        )
        report_id = self._digest_id(
            "disagreement",
            {
                "version": int(self.config.report_version),
                "comparison_ids": sorted(item.comparison_id for item in normalized),
            },
        )
        return DisagreementReport(
            report_id=report_id,
            evaluated_at_ms=self._resolve_eval_time(evaluated_at_ms),
            total_compared=total_compared,
            disagreement_count=disagreement_count,
            disagreement_rate=disagreement_rate,
            by_symbol=dict(sorted(by_symbol.items())),
            by_regime=dict(sorted(by_regime.items())),
            by_confidence_bucket=dict(sorted(by_confidence_bucket.items())),
            severity_buckets=dict(sorted(severity_buckets.items())),
            unresolved_comparison_count=unresolved_count,
        )

    def build_advisory_readiness_report(
        self,
        *,
        config: NeocortexConfig,
        gate_report: Optional[ShadowReadinessReport] = None,
        regime_report: Optional[ShadowEvaluationReport] = None,
        execution_report: Optional[ShadowEvaluationReport] = None,
        calibration_report: Optional[CalibrationReport] = None,
        disagreement_report: Optional[DisagreementReport] = None,
        evaluated_at_ms: Optional[int] = None,
    ) -> AdvisoryReadinessPrereqReport:
        resolved_time = self._resolve_eval_time(evaluated_at_ms)
        gate = gate_report or ShadowGateEvaluator().evaluate(
            config,
            evaluated_at_ms=resolved_time,
        )
        satisfied: list[str] = []
        unsatisfied: list[str] = []
        blocking: list[str] = ["advisory_enable_forbidden_in_p9"]

        if gate.overall_status == "ready":
            satisfied.append("production_shadow_gates_ready")
        else:
            unsatisfied.append("production_shadow_gates_not_ready")
            blocking.append("production_shadow_gates_not_ready")

        if config.neuro.ppo.policy_training_mode == "disabled":
            satisfied.append("policy_training_still_disabled")
        else:
            unsatisfied.append("policy_training_must_remain_disabled")
            blocking.append("policy_training_must_remain_disabled")

        if (
            not config.neuro.shadow_gates.allow_advisory_influence
            and not config.neuro.shadow_gates.allow_live_authority
        ):
            satisfied.append("advisory_and_live_authority_blocked")
        else:
            unsatisfied.append("advisory_or_live_authority_not_blocked")
            blocking.append("advisory_or_live_authority_not_blocked")

        if regime_report is not None and regime_report.sample_counts.get("included", 0) > 0:
            satisfied.append("regime_evaluation_available")
        else:
            unsatisfied.append("missing_regime_evaluation_report")

        if execution_report is not None and execution_report.sample_counts.get("included", 0) > 0:
            satisfied.append("execution_quality_evaluation_available")
        else:
            unsatisfied.append("missing_execution_quality_evaluation_report")

        if disagreement_report is not None and (
            disagreement_report.total_compared > 0
            or disagreement_report.unresolved_comparison_count > 0
        ):
            satisfied.append("disagreement_report_available")
        else:
            unsatisfied.append("no_shadow_vs_aurora_comparison_corpus")
            blocking.append("no_shadow_vs_aurora_comparison_corpus")

        if calibration_report is not None and calibration_report.status == "available":
            satisfied.append("calibration_evidence_available")
        else:
            unsatisfied.append("calibration_evidence_not_available")
            blocking.append("calibration_evidence_not_available")

        unsatisfied.append("future_advisory_gate_package_required")
        recommended = [
            "NEO-ACCEPTANCE-CAMPAIGN-SHADOW-ANALYTICS",
            "NEO-CALIBRATION-EVIDENCE-HARDENING",
            "NEO-FUTURE-ADVISORY-ONLY-GATES",
        ]
        report_id = self._digest_id(
            "advisory",
            {
                "version": int(self.config.report_version),
                "gate_status": gate.overall_status,
                "regime_report": getattr(regime_report, "evaluation_id", None),
                "execution_report": getattr(execution_report, "evaluation_id", None),
                "calibration_report": getattr(calibration_report, "report_id", None),
                "disagreement_report": getattr(disagreement_report, "report_id", None),
            },
        )
        return AdvisoryReadinessPrereqReport(
            report_id=report_id,
            evaluated_at_ms=resolved_time,
            advisory_status=str(self.config.advisory_status),
            production_shadow_status=gate.overall_status,
            satisfied_prereqs=sorted(set(satisfied)),
            unsatisfied_prereqs=sorted(set(unsatisfied)),
            blocking_reasons=sorted(set(blocking)),
            recommended_next_packages=recommended,
        )

    def _build_regime_report(
        self,
        samples: List[DatasetEvaluatedSample],
        *,
        evaluated_at_ms: int,
    ) -> ShadowEvaluationReport:
        included = [item for item in samples if item.eligibility_status in INCLUDED_STATUSES]
        unresolved_count = sum(
            1
            for item in samples
            if item.sample.get("unresolved_lifecycle") or item.sample.get("unresolved_close")
        )
        diagnostics_only_count = sum(
            1 for item in samples if item.eligibility_status == "diagnostics_only"
        )
        valid_labels = [
            item for item in included
            if item.sample.get("predicted_regime") is not None
            and item.sample.get("realized_regime") is not None
        ]
        correct = sum(
            1
            for item in valid_labels
            if int(item.sample["predicted_regime"]) == int(item.sample["realized_regime"])
        )
        accuracy = correct / len(valid_labels) if valid_labels else None
        label_coverage_rate = len(valid_labels) / len(included) if included else 0.0
        predicted_counts = Counter(
            str(int(item.sample["predicted_regime"])) for item in valid_labels
        )
        realized_counts = Counter(
            str(int(item.sample["realized_regime"])) for item in valid_labels
        )
        confusion = Counter(
            f"{int(item.sample['predicted_regime'])}->{int(item.sample['realized_regime'])}"
            for item in valid_labels
        )
        report_id = self._build_evaluation_id("regime_supervision", samples)
        return ShadowEvaluationReport(
            evaluation_id=report_id,
            evaluated_at_ms=evaluated_at_ms,
            objective_family="regime_supervision",
            time_window=self._time_window(samples),
            sample_counts=self._sample_counts(samples),
            key_metrics={
                "label_coverage_rate": label_coverage_rate,
                "accuracy": accuracy,
                "abstain_count": len(included) - len(valid_labels),
                "predicted_class_distribution": dict(sorted(predicted_counts.items())),
                "realized_class_distribution": dict(sorted(realized_counts.items())),
                "confusion_summary": dict(sorted(confusion.items())),
            },
            unresolved_count=unresolved_count,
            diagnostics_only_count=diagnostics_only_count,
            symbols_coverage=self._symbols_coverage(included),
            regimes_coverage=dict(sorted(realized_counts.items())),
        )

    def _build_regime_calibration_report(
        self,
        samples: List[DatasetEvaluatedSample],
        *,
        evaluated_at_ms: int,
    ) -> CalibrationReport:
        records: list[tuple[float, int]] = []
        for item in samples:
            if item.eligibility_status not in INCLUDED_STATUSES:
                continue
            confidence = item.sample.get("confidence")
            predicted = item.sample.get("predicted_regime")
            realized = item.sample.get("realized_regime")
            if confidence is None or predicted is None or realized is None:
                continue
            try:
                conf = float(confidence)
            except (TypeError, ValueError):
                continue
            if conf < 0.0 or conf > 1.0:
                continue
            outcome = 1 if int(predicted) == int(realized) else 0
            records.append((conf, outcome))
        return self._build_calibration_report(
            objective_family="regime_supervision",
            record_id_payload=[item.provenance.dataset_sample_id for item in samples],
            confidence_source="sample.confidence",
            records=records,
            evaluated_at_ms=evaluated_at_ms,
        )

    def _build_calibration_report(
        self,
        *,
        objective_family: str,
        record_id_payload: List[str],
        confidence_source: str,
        records: list[tuple[float, int]],
        evaluated_at_ms: int,
    ) -> CalibrationReport:
        report_id = self._digest_id(
            f"calibration:{objective_family}",
            {
                "version": int(self.config.report_version),
                "records": sorted(record_id_payload),
                "confidence_source": confidence_source,
                "bins": int(self.config.calibration_bins),
            },
        )
        if not records:
            return CalibrationReport(
                report_id=report_id,
                evaluated_at_ms=evaluated_at_ms,
                objective_family=objective_family,
                confidence_source=confidence_source,
                status=str(self.config.missing_confidence_policy),
                number_of_bins=int(self.config.calibration_bins),
                counts_per_bin=[0] * int(self.config.calibration_bins),
                empirical_outcome_per_bin=[None] * int(self.config.calibration_bins),
                bin_summaries=[
                    CalibrationBinSummary(
                        bin_index=index,
                        lower_bound=index / int(self.config.calibration_bins),
                        upper_bound=(index + 1) / int(self.config.calibration_bins),
                        sample_count=0,
                    )
                    for index in range(int(self.config.calibration_bins))
                ],
                reliability_summary={
                    "scored_samples": 0,
                    "average_confidence": None,
                    "average_accuracy": None,
                    "mean_absolute_calibration_gap": None,
                    "max_absolute_calibration_gap": None,
                },
                message="Confidence signal unavailable or unsupported for this evaluation corpus.",
            )

        bins: list[list[tuple[float, int]]] = [[] for _ in range(int(self.config.calibration_bins))]
        for confidence, outcome in records:
            index = min(
                int(confidence * int(self.config.calibration_bins)),
                int(self.config.calibration_bins) - 1,
            )
            bins[index].append((confidence, outcome))

        counts_per_bin: list[int] = []
        empirical_per_bin: list[Optional[float]] = []
        bin_summaries: list[CalibrationBinSummary] = []
        gaps: list[float] = []
        for index, items in enumerate(bins):
            count = len(items)
            lower = index / int(self.config.calibration_bins)
            upper = (index + 1) / int(self.config.calibration_bins)
            counts_per_bin.append(count)
            if items:
                mean_conf = sum(item[0] for item in items) / count
                empirical = sum(item[1] for item in items) / count
                gaps.append(abs(mean_conf - empirical))
            else:
                mean_conf = None
                empirical = None
            empirical_per_bin.append(empirical)
            bin_summaries.append(
                CalibrationBinSummary(
                    bin_index=index,
                    lower_bound=lower,
                    upper_bound=upper,
                    sample_count=count,
                    mean_confidence=mean_conf,
                    empirical_accuracy=empirical,
                )
            )
        avg_conf = sum(item[0] for item in records) / len(records)
        avg_acc = sum(item[1] for item in records) / len(records)
        return CalibrationReport(
            report_id=report_id,
            evaluated_at_ms=evaluated_at_ms,
            objective_family=objective_family,
            confidence_source=confidence_source,
            status="available",
            number_of_bins=int(self.config.calibration_bins),
            counts_per_bin=counts_per_bin,
            empirical_outcome_per_bin=empirical_per_bin,
            bin_summaries=bin_summaries,
            reliability_summary={
                "scored_samples": len(records),
                "average_confidence": avg_conf,
                "average_accuracy": avg_acc,
                "mean_absolute_calibration_gap": (sum(gaps) / len(gaps)) if gaps else 0.0,
                "max_absolute_calibration_gap": max(gaps) if gaps else 0.0,
            },
            message="Calibration report built from confidence-bearing regime supervision samples.",
        )

    def _build_execution_report(
        self,
        samples: List[DatasetEvaluatedSample],
        *,
        evaluated_at_ms: int,
    ) -> ShadowEvaluationReport:
        included = [item for item in samples if item.eligibility_status in INCLUDED_STATUSES]
        unresolved_count = sum(
            1
            for item in samples
            if item.sample.get("unresolved_lifecycle")
            or item.sample.get("unresolved_close")
            or "unresolved_lifecycle" in item.provenance.quarantine_reasons
        )
        diagnostics_only_count = sum(
            1 for item in samples if item.eligibility_status == "diagnostics_only"
        )
        reward_complete_true = sum(
            1 for item in included if item.sample.get("reward_complete") is True
        )
        reward_complete_rate = (
            reward_complete_true / len(included) if included else 0.0
        )
        close_events = Counter(
            str(item.sample.get("close_event") or "unknown") for item in included
        )
        lifecycle_states = Counter(
            str(item.sample.get("lifecycle_state") or "unknown") for item in included
        )
        diagnostic_categories = Counter()
        for item in samples:
            diagnostic_categories.update(item.provenance.exclusion_reasons)
            diagnostic_categories.update(item.provenance.quarantine_reasons)
        fill_counts = [
            int(item.sample["fill_count"])
            for item in included
            if item.sample.get("fill_count") is not None
        ]
        filled_quantities = [
            float(item.sample["filled_quantity"])
            for item in included
            if item.sample.get("filled_quantity") is not None
        ]
        report_id = self._build_evaluation_id("execution_quality", samples)
        return ShadowEvaluationReport(
            evaluation_id=report_id,
            evaluated_at_ms=evaluated_at_ms,
            objective_family="execution_quality",
            time_window=self._time_window(samples),
            sample_counts=self._sample_counts(samples),
            key_metrics={
                "reward_complete_rate": reward_complete_rate,
                "trainable_vs_diagnostics": {
                    "trainable": sum(
                        1 for item in samples if item.eligibility_status == "trainable"
                    ),
                    "diagnostics_only": diagnostics_only_count,
                },
                "close_event_distribution": dict(sorted(close_events.items())),
                "lifecycle_state_distribution": dict(sorted(lifecycle_states.items())),
                "diagnostic_category_counts": dict(sorted(diagnostic_categories.items())),
                "avg_fill_count": (
                    sum(fill_counts) / len(fill_counts) if fill_counts else None
                ),
                "avg_filled_quantity": (
                    sum(filled_quantities) / len(filled_quantities)
                    if filled_quantities else None
                ),
            },
            unresolved_count=unresolved_count,
            diagnostics_only_count=diagnostics_only_count,
            symbols_coverage=self._symbols_coverage(included),
            regimes_coverage={},
        )

    def _normalize_dataset_samples(
        self,
        samples: Sequence[DatasetEvaluatedSample],
        *,
        expected_family: str,
    ) -> List[DatasetEvaluatedSample]:
        normalized = list(samples)
        for item in normalized:
            if item.objective_family != expected_family:
                raise ValueError(
                    f"Mixed objective families are forbidden: expected {expected_family}, got {item.objective_family}"
                )
        return sorted(
            normalized,
            key=lambda item: (
                item.provenance.event_ts_ms,
                item.provenance.dataset_sample_id,
            ),
        )

    def _normalize_disagreement_samples(
        self,
        comparisons: Sequence[ShadowDisagreementSample | Mapping[str, Any]],
    ) -> List[ShadowDisagreementSample]:
        normalized = [
            item if isinstance(item, ShadowDisagreementSample)
            else ShadowDisagreementSample(**dict(item))
            for item in comparisons
        ]
        return sorted(
            normalized,
            key=lambda item: (item.event_ts_ms, item.comparison_id),
        )

    def _sample_counts(self, samples: Sequence[DatasetEvaluatedSample]) -> dict[str, int]:
        counts = Counter(item.eligibility_status for item in samples)
        included = sum(1 for item in samples if item.eligibility_status in INCLUDED_STATUSES)
        excluded = sum(1 for item in samples if item.eligibility_status in EXCLUDED_STATUSES)
        return {
            "total": len(samples),
            "included": included,
            "excluded": excluded,
            "trainable": int(counts.get("trainable", 0)),
            "eval_only": int(counts.get("eval_only", 0)),
            "diagnostics_only": int(counts.get("diagnostics_only", 0)),
            "quarantined": int(counts.get("quarantined", 0)),
            "rejected": int(counts.get("rejected", 0)),
        }

    def _symbols_coverage(self, samples: Sequence[DatasetEvaluatedSample]) -> dict[str, int]:
        counts = Counter()
        for item in samples:
            symbol = item.provenance.symbol or item.sample.get("symbol")
            if symbol:
                counts[str(symbol)] += 1
        return dict(sorted(counts.items()))

    def _time_window(self, samples: Sequence[DatasetEvaluatedSample]) -> dict[str, Optional[int]]:
        event_times = [item.provenance.event_ts_ms for item in samples if item.provenance.event_ts_ms > 0]
        return {
            "start_event_ts_ms": min(event_times) if event_times else None,
            "end_event_ts_ms": max(event_times) if event_times else None,
        }

    def _build_evaluation_id(
        self,
        objective_family: str,
        samples: Sequence[DatasetEvaluatedSample],
    ) -> str:
        return self._digest_id(
            f"evaluation:{objective_family}",
            {
                "version": int(self.config.report_version),
                "sample_ids": sorted(item.provenance.dataset_sample_id for item in samples),
            },
        )

    def _bucket_confidence(self, confidence: Optional[float]) -> str:
        if confidence is None:
            return "unknown"
        value = float(confidence)
        lower = 0.0
        for edge in self.config.confidence_bucket_edges:
            if value <= edge:
                return f"[{lower:.2f},{edge:.2f}]"
            lower = edge
        return f"({lower:.2f},1.00]"

    def _resolve_eval_time(self, evaluated_at_ms: Optional[int]) -> int:
        return int(evaluated_at_ms if evaluated_at_ms is not None else time.time() * 1000.0)

    def _digest_id(self, prefix: str, payload: Mapping[str, Any]) -> str:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return f"{prefix}:{digest}"
