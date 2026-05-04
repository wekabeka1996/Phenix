from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from apps.reference.domains.neocortex.config_models import DatasetCutoverConfig
from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import FailureReasonCode
from apps.reference.domains.neocortex.logic.datasets.contracts import (
    DatasetCutoverDecision,
    DatasetCutoverSummary,
)
from apps.reference.telemetry.metrics import (
    inc_neocortex_dataset_cutover_allowed,
    inc_neocortex_dataset_cutover_blocked,
    set_neocortex_dataset_diagnostics_only_rows,
    set_neocortex_dataset_trainable_rows,
)


def _coerce_int(value: object, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, coerced)


def _coerce_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_dataset_cutover_summary(
    rows: Iterable[DecisionOutcomeLedgerRow],
    *,
    metadata: Mapping[str, object] | None = None,
) -> DatasetCutoverSummary:
    metadata_map = metadata or {}
    collected_rows = list(rows)
    invalid_rows_by_reason: Counter[str] = Counter()
    trainable_rows = 0
    diagnostics_only_rows = 0
    real_executed_rows = 0
    terminal_incomplete_rows = 0

    for row in collected_rows:
        if row.dataset_visibility == "trainable":
            trainable_rows += 1
        else:
            diagnostics_only_rows += 1

        if row.invalid_reason_code:
            invalid_rows_by_reason[str(
                row.invalid_reason_code).strip().upper()] += 1

        if row.terminal_status == DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED:
            real_executed_rows += 1

        if row.terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET:
            terminal_incomplete_rows += 1

    total_rows = len(collected_rows)
    terminal_complete_rows = max(0, total_rows - terminal_incomplete_rows)

    return DatasetCutoverSummary(
        total_rows=total_rows,
        trainable_rows=trainable_rows,
        diagnostics_only_rows=diagnostics_only_rows,
        invalid_rows_by_reason=dict(sorted(invalid_rows_by_reason.items())),
        real_executed_rows=real_executed_rows,
        synthetic_rows=_coerce_int(
            metadata_map.get("synthetic_rows"), default=0),
        used_synthetic_fallback=_coerce_bool(
            metadata_map.get("used_synthetic_fallback"),
            default=False,
        ),
        reward_valid=_coerce_bool(
            metadata_map.get("reward_valid"), default=False),
        reward_methodology=_coerce_optional_text(
            metadata_map.get("reward_methodology")),
        terminal_complete_rows=terminal_complete_rows,
        terminal_incomplete_rows=terminal_incomplete_rows,
    )


class DatasetCutoverEvaluator:
    """Aggregate admission guard for trainable dataset promotion/export."""

    def __init__(self, config: DatasetCutoverConfig) -> None:
        self._config = config

    def evaluate_dataset_cutover_admission(
        self,
        summary: DatasetCutoverSummary,
    ) -> DatasetCutoverDecision:
        blocking_reasons: list[str] = []

        if summary.real_executed_rows < self._config.min_real_executed_rows:
            blocking_reasons.append(
                FailureReasonCode.INSUFFICIENT_REAL_EXECUTED_ROWS.value
            )

        if summary.terminal_incomplete_rows > 0:
            blocking_reasons.append(
                FailureReasonCode.TERMINAL_OUTCOME_INCOMPLETE.value
            )

        non_causal_rows = int(
            summary.invalid_rows_by_reason.get(
                FailureReasonCode.NON_CAUSAL_TIME.value,
                0,
            )
        )
        if non_causal_rows > self._config.max_non_causal_rows:
            blocking_reasons.append(FailureReasonCode.NON_CAUSAL_TIME.value)

        if (
            not self._config.allow_synthetic_fallback
            and (summary.used_synthetic_fallback or summary.synthetic_rows > 0)
        ):
            blocking_reasons.append(
                FailureReasonCode.SYNTHETIC_FALLBACK_PRESENT.value
            )

        if self._config.require_reward_methodology:
            if not summary.reward_valid:
                blocking_reasons.append(FailureReasonCode.REWARD_INVALID.value)
            if not summary.reward_methodology:
                blocking_reasons.append(
                    FailureReasonCode.REWARD_METHODOLOGY_MISSING.value
                )

        set_neocortex_dataset_trainable_rows(summary.trainable_rows)
        set_neocortex_dataset_diagnostics_only_rows(
            summary.diagnostics_only_rows)

        if blocking_reasons:
            for reason_code in blocking_reasons:
                inc_neocortex_dataset_cutover_blocked(reason_code)
        else:
            inc_neocortex_dataset_cutover_allowed()

        summary_payload = summary.model_dump(
            mode="python",
            exclude={"cutover_allowed", "blocking_reasons"},
        )
        return DatasetCutoverDecision(
            **summary_payload,
            cutover_allowed=not blocking_reasons,
            blocking_reasons=blocking_reasons,
        )

    def evaluate_rows(
        self,
        rows: Iterable[DecisionOutcomeLedgerRow],
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> DatasetCutoverDecision:
        summary = build_dataset_cutover_summary(rows, metadata=metadata)
        return self.evaluate_dataset_cutover_admission(summary)


__all__ = [
    "DatasetCutoverEvaluator",
    "build_dataset_cutover_summary",
]
