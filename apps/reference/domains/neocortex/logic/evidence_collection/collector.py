from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4
import time

from pydantic import BaseModel, ValidationError

from apps.reference.domains.neocortex.config_models import DatasetCutoverConfig
from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureReasonCode,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    ObservationEnvelope,
)
from apps.reference.domains.neocortex.logic.datasets.cutover import (
    DatasetCutoverEvaluator,
    build_dataset_cutover_summary,
)
from apps.reference.domains.neocortex.logic.evidence_collection.contracts import (
    DecisionOutcomeEvidenceSummary,
    EvidenceCollectionBundle,
    EvidenceCollectionSummary,
    ObservationEvidenceSummary,
)
from apps.reference.domains.neocortex.logic.evidence_collection.summary import (
    build_bundle_completeness,
    legacy_experiments_import_state,
    merge_histograms,
)


_DECISION_JOIN_KEYS = {
    "decision_id",
    "rid",
    "lifecycle_id",
    "trade_id",
    "no_join",
}
_SYNTHETIC_FALLBACK_STATUSES = {
    DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED.value,
    DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_NO_EXECUTION.value,
}


def _payload(item: ObservationEnvelope | DecisionOutcomeLedgerRow | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, BaseModel):
        return item.model_dump(mode="json")
    return {str(key): value for key, value in dict(item).items()}


def _text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _truthy(value: object | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"} if value is not None else False


def _normalized_join_kind(payload: Mapping[str, Any]) -> str:
    support_quality = payload.get("support_quality")
    if isinstance(support_quality, Mapping):
        joined_by = _text(support_quality.get("joined_by"))
        if joined_by in _DECISION_JOIN_KEYS:
            return joined_by
    data_quality_flags = payload.get("data_quality_flags")
    if isinstance(data_quality_flags, Mapping):
        joined_by = _text(data_quality_flags.get("joined_by"))
        if joined_by in _DECISION_JOIN_KEYS:
            return joined_by
    joined_by = _text(payload.get("joined_by"))
    if joined_by in _DECISION_JOIN_KEYS:
        return joined_by
    return "no_join"


def _is_synthetic_fallback(payload: Mapping[str, Any]) -> bool:
    terminal_status = _text(payload.get("terminal_status")).upper()
    if terminal_status in _SYNTHETIC_FALLBACK_STATUSES:
        return True
    fallback_reason = _text(payload.get("fallback_reason")).upper()
    if fallback_reason:
        return True
    apply_result = _text(payload.get("apply_result")).upper()
    if apply_result.startswith("FALLBACK"):
        return True
    neocortex_action = _text(payload.get("neocortex_action")).upper()
    return neocortex_action == "FALLBACK"


def _ensure_observation_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_time_is_causal": payload.get("event_time_is_causal"),
        "trainable": payload.get("trainable"),
        "dataset_visibility": payload.get("dataset_visibility"),
        "invalid_reason_code": payload.get("invalid_reason_code"),
    }


@dataclass(slots=True)
class _CollectorState:
    observation: ObservationEvidenceSummary = field(
        default_factory=ObservationEvidenceSummary)
    decision: DecisionOutcomeEvidenceSummary = field(
        default_factory=DecisionOutcomeEvidenceSummary)
    invalid_reason_histogram: Counter[str] = field(default_factory=Counter)
    cutover_rows: list[DecisionOutcomeLedgerRow] = field(default_factory=list)


class NeocortexEvidenceCollector:
    """Report-only collector for Phase 8A evidence bundle generation."""

    def __init__(self, *, cutover_config: DatasetCutoverConfig) -> None:
        self._cutover_config = cutover_config
        self._evaluator = DatasetCutoverEvaluator(cutover_config)
        self._state = _CollectorState()

    @property
    def cutover_config(self) -> DatasetCutoverConfig:
        return self._cutover_config

    def collect(self, item: ObservationEnvelope | DecisionOutcomeLedgerRow | Mapping[str, Any]) -> None:
        payload = _payload(item)
        if self._looks_like_observation(payload):
            self.collect_observation(item)
            return
        if self._looks_like_decision(payload):
            self.collect_decision_outcome(item)
            return
        raise TypeError(
            "NeocortexEvidenceCollector.collect expected ObservationEnvelope, "
            "DecisionOutcomeLedgerRow, or a compatible mapping"
        )

    def collect_observation(self, item: ObservationEnvelope | Mapping[str, Any]) -> None:
        payload = _payload(item)
        self._state.observation = self._state.observation.model_copy(
            update={
                "observation_envelope_count": self._state.observation.observation_envelope_count + 1,
                "causal_valid_count": self._state.observation.causal_valid_count + int(payload.get("event_time_is_causal") is True),
                "trainable_count": self._state.observation.trainable_count + int(
                    payload.get("event_time_is_causal") is True
                    and payload.get("trainable") is True
                    and _text(payload.get("dataset_visibility")) == "trainable"
                ),
                "diagnostics_only_count": self._state.observation.diagnostics_only_count + int(
                    payload.get("event_time_is_causal") is False
                    and payload.get("trainable") is False
                    and _text(payload.get("dataset_visibility")) == "diagnostics_only"
                ),
                "invalid_count": self._state.observation.invalid_count + int(
                    not (
                        payload.get("event_time_is_causal") is True
                        and payload.get("trainable") is True
                        and _text(payload.get("dataset_visibility")) == "trainable"
                    )
                    and not (
                        payload.get("event_time_is_causal") is False
                        and payload.get("trainable") is False
                        and _text(payload.get("dataset_visibility")) == "diagnostics_only"
                    )
                ),
            }
        )

        if payload.get("event_time_is_causal") is False:
            self._state.invalid_reason_histogram[FailureReasonCode.NON_CAUSAL_TIME.value] += 1
        elif not (
            payload.get("event_time_is_causal") is True
            and payload.get("trainable") is True
            and _text(payload.get("dataset_visibility")) == "trainable"
        ) and not (
            payload.get("event_time_is_causal") is False
            and payload.get("trainable") is False
            and _text(payload.get("dataset_visibility")) == "diagnostics_only"
        ):
            self._state.invalid_reason_histogram[FailureReasonCode.MISSING_REQUIRED_STATE.value] += 1

    def collect_decision_outcome(self, item: DecisionOutcomeLedgerRow | Mapping[str, Any]) -> None:
        payload = _payload(item)
        join_kind = _normalized_join_kind(payload)
        terminal_status = _text(payload.get("terminal_status"))

        decision_updates = {
            "decision_row_count": self._state.decision.decision_row_count + 1,
            "decision_id_join_count": self._state.decision.decision_id_join_count + int(join_kind == "decision_id"),
            "rid_join_count": self._state.decision.rid_join_count + int(join_kind == "rid"),
            "lifecycle_id_join_count": self._state.decision.lifecycle_id_join_count + int(join_kind == "lifecycle_id"),
            "trade_id_join_count": self._state.decision.trade_id_join_count + int(join_kind == "trade_id"),
            "no_join_count": self._state.decision.no_join_count + int(join_kind == "no_join"),
            "terminal_joined_count": self._state.decision.terminal_joined_count + int(bool(terminal_status)),
            "terminal_missing_count": self._state.decision.terminal_missing_count + int(not bool(terminal_status)),
            "synthetic_fallback_count": self._state.decision.synthetic_fallback_count + int(_is_synthetic_fallback(payload)),
        }

        if not terminal_status:
            decision_updates["invalid_count"] = self._state.decision.invalid_count + 1
            self._state.invalid_reason_histogram["TERMINAL_EVENT_MISSING"] += 1
            self._state.decision = self._state.decision.model_copy(
                update=decision_updates)
            return

        normalized_payload = dict(payload)
        if join_kind == "no_join" or _is_synthetic_fallback(payload):
            normalized_payload["dataset_visibility"] = "diagnostics_only"

        try:
            canonical_row = DecisionOutcomeLedgerRow.model_validate(
                normalized_payload)
        except ValidationError:
            decision_updates["invalid_count"] = self._state.decision.invalid_count + 1
            self._state.invalid_reason_histogram[FailureReasonCode.MISSING_REQUIRED_STATE.value] += 1
            self._state.decision = self._state.decision.model_copy(
                update=decision_updates)
            return

        if canonical_row.dataset_visibility == "trainable":
            decision_updates["trainable_count"] = self._state.decision.trainable_count + 1
        else:
            decision_updates["diagnostics_only_count"] = self._state.decision.diagnostics_only_count + 1

        if canonical_row.invalid_reason_code is not None:
            decision_updates["invalid_count"] = self._state.decision.invalid_count + 1
            self._state.invalid_reason_histogram[str(
                canonical_row.invalid_reason_code).strip().upper()] += 1

        if canonical_row.terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
            if canonical_row.invalid_reason_code is None:
                decision_updates["invalid_count"] = self._state.decision.invalid_count + 1
                self._state.invalid_reason_histogram[FailureReasonCode.MISSING_REQUIRED_STATE.value] += 1

        self._state.cutover_rows.append(canonical_row)
        self._state.decision = self._state.decision.model_copy(
            update=decision_updates)

    def finalize(
        self,
        *,
        reward_valid_requested: bool = False,
        reward_methodology: str | None = None,
        synthetic_rows: int | None = None,
        used_synthetic_fallback: bool | None = None,
    ) -> EvidenceCollectionBundle:
        reward_methodology_present = bool(_text(reward_methodology))
        reward_valid = bool(
            reward_valid_requested and reward_methodology_present)
        if self._cutover_config.require_reward_methodology and not reward_methodology_present:
            reward_valid = False

        metadata = {
            "synthetic_rows": int(
                synthetic_rows if synthetic_rows is not None else self._state.decision.synthetic_fallback_count
            ),
            "used_synthetic_fallback": bool(
                used_synthetic_fallback if used_synthetic_fallback is not None else self._state.decision.synthetic_fallback_count > 0
            ),
            "reward_valid": reward_valid,
            "reward_methodology": reward_methodology,
        }
        dataset_cutover_summary = build_dataset_cutover_summary(
            self._state.cutover_rows,
            metadata=metadata,
        )
        dataset_cutover_decision = self._evaluator.evaluate_dataset_cutover_admission(
            dataset_cutover_summary
        )
        legacy_imported, legacy_modules = legacy_experiments_import_state()

        summary = EvidenceCollectionSummary(
            observation=self._state.observation,
            decision_outcome=self._state.decision.model_copy(
                update={
                    "reward_valid_rows_count": (
                        self._state.decision.decision_row_count if reward_valid else 0
                    )
                }
            ),
            invalid_reason_histogram=merge_histograms(
                dict(self._state.invalid_reason_histogram)),
            reward_methodology=reward_methodology,
            reward_methodology_present=reward_methodology_present,
            reward_valid_requested=bool(reward_valid_requested),
            reward_valid=reward_valid,
            dataset_cutover_summary=dataset_cutover_summary,
            dataset_cutover_decision=dataset_cutover_decision,
            legacy_experiments_imported=legacy_imported,
            legacy_experiments_modules=legacy_modules,
            evidence_bundle_complete=build_bundle_completeness(
                EvidenceCollectionSummary(
                    observation=self._state.observation,
                    decision_outcome=self._state.decision,
                    invalid_reason_histogram=merge_histograms(
                        dict(self._state.invalid_reason_histogram)),
                    reward_methodology=reward_methodology,
                    reward_methodology_present=reward_methodology_present,
                    reward_valid_requested=bool(reward_valid_requested),
                    reward_valid=reward_valid,
                    dataset_cutover_summary=dataset_cutover_summary,
                    dataset_cutover_decision=dataset_cutover_decision,
                    legacy_experiments_imported=legacy_imported,
                    legacy_experiments_modules=legacy_modules,
                )
            ),
        )

        return EvidenceCollectionBundle(
            generated_at_ms=int(time.time() * 1000),
            summary=summary,
        )

    @staticmethod
    def _looks_like_observation(payload: Mapping[str, Any]) -> bool:
        return "event_time_is_causal" in payload or "state_vector" in payload or "context_vector" in payload

    @staticmethod
    def _looks_like_decision(payload: Mapping[str, Any]) -> bool:
        return "decision_id" in payload and "terminal_status" in payload or "support_quality" in payload
