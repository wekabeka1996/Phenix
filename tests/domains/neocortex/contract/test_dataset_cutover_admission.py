from __future__ import annotations

import re
from pathlib import Path

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
    ExecutionOutcome,
)
from apps.reference.domains.neocortex.logic.datasets import (
    DatasetCutoverEvaluator,
    build_dataset_cutover_summary,
)
from apps.reference.telemetry.metrics import generate_latest


CONFIG_DIR = Path("apps/reference/domains/neocortex/config")


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    label_fragments = [f'{key}="{value}"' for key, value in labels.items()]
    pattern = re.compile(r" (-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)$")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(fragment in line for fragment in label_fragments):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        match = pattern.search(line)
        if match is not None:
            return float(match.group(1))
    return 0.0


def _cutover_evaluator() -> DatasetCutoverEvaluator:
    config = load_config(CONFIG_DIR)
    return DatasetCutoverEvaluator(config.neuro.dataset.cutover)


def _row(
    *,
    decision_id: str,
    terminal_status: DecisionOutcomeTerminalStatus,
    dataset_visibility: str = "trainable",
    invalid_reason_code: str | None = None,
) -> DecisionOutcomeLedgerRow:
    return DecisionOutcomeLedgerRow(
        decision_id=decision_id,
        rid=f"rid-{decision_id}",
        symbol="BTCUSDT",
        authority_mode="shadow",
        request_ts_ms=1_700_000_000_000,
        response_ts_ms=1_700_000_000_010,
        terminal_status=terminal_status,
        dataset_visibility=dataset_visibility,
        invalid_reason_code=invalid_reason_code,
        neocortex_action="ALLOW",
        execution_outcome=ExecutionOutcome.EXECUTED
        if terminal_status in {
            DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
        }
        else (
            ExecutionOutcome.PENDING_TIMEOUT
            if terminal_status == DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET
            else ExecutionOutcome.FSM_BLOCKED
        ),
    )


def test_dataset_cutover_blocks_without_real_executed_rows() -> None:
    evaluator = _cutover_evaluator()
    summary = build_dataset_cutover_summary(
        [
            _row(
                decision_id="fallback-1",
                terminal_status=DecisionOutcomeTerminalStatus.BASELINE_FALLBACK_EXECUTED,
            )
        ],
        metadata={
            "reward_valid": True,
            "reward_methodology": "ope_v1",
        },
    )

    decision = evaluator.evaluate_dataset_cutover_admission(summary)

    assert decision.cutover_allowed is False
    assert decision.real_executed_rows == 0
    assert "INSUFFICIENT_REAL_EXECUTED_ROWS" in decision.blocking_reasons


def test_dataset_cutover_blocks_on_synthetic_fallback_metadata() -> None:
    evaluator = _cutover_evaluator()
    summary = build_dataset_cutover_summary(
        [
            _row(
                decision_id="real-1",
                terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            )
        ],
        metadata={
            "synthetic_rows": 3,
            "used_synthetic_fallback": True,
            "reward_valid": True,
            "reward_methodology": "ope_v1",
        },
    )

    decision = evaluator.evaluate_dataset_cutover_admission(summary)

    assert decision.cutover_allowed is False
    assert "SYNTHETIC_FALLBACK_PRESENT" in decision.blocking_reasons


def test_dataset_cutover_blocks_on_non_causal_invalid_rows_and_terminal_incomplete() -> None:
    evaluator = _cutover_evaluator()
    summary = build_dataset_cutover_summary(
        [
            _row(
                decision_id="real-1",
                terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            ),
            _row(
                decision_id="invalid-1",
                terminal_status=DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
                dataset_visibility="diagnostics_only",
                invalid_reason_code="NON_CAUSAL_TIME",
            ),
        ],
        metadata={
            "reward_valid": True,
            "reward_methodology": "ope_v1",
        },
    )

    decision = evaluator.evaluate_dataset_cutover_admission(summary)

    assert decision.cutover_allowed is False
    assert decision.invalid_rows_by_reason["NON_CAUSAL_TIME"] == 1
    assert "NON_CAUSAL_TIME" in decision.blocking_reasons
    assert "TERMINAL_OUTCOME_INCOMPLETE" in decision.blocking_reasons


def test_dataset_cutover_blocks_when_reward_methodology_is_missing() -> None:
    evaluator = _cutover_evaluator()
    summary = build_dataset_cutover_summary(
        [
            _row(
                decision_id="real-1",
                terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            )
        ],
        metadata={
            "reward_valid": True,
        },
    )

    decision = evaluator.evaluate_dataset_cutover_admission(summary)

    assert decision.cutover_allowed is False
    assert "REWARD_METHODOLOGY_MISSING" in decision.blocking_reasons


def test_dataset_cutover_allows_real_causal_dataset_and_emits_metrics() -> None:
    evaluator = _cutover_evaluator()
    allowed_before = _metric_value("neocortex_dataset_cutover_allowed_total")
    trainable_before = _metric_value("neocortex_dataset_trainable_rows")
    diagnostics_before = _metric_value(
        "neocortex_dataset_diagnostics_only_rows")

    summary = build_dataset_cutover_summary(
        [
            _row(
                decision_id="real-1",
                terminal_status=DecisionOutcomeTerminalStatus.EXECUTED_AND_CLOSED,
            ),
            _row(
                decision_id="diag-1",
                terminal_status=DecisionOutcomeTerminalStatus.VETOED,
                dataset_visibility="diagnostics_only",
            ),
        ],
        metadata={
            "reward_valid": True,
            "reward_methodology": "ope_v1",
        },
    )

    decision = evaluator.evaluate_dataset_cutover_admission(summary)

    assert summary.trainable_rows == 1
    assert summary.diagnostics_only_rows == 1
    assert decision.cutover_allowed is True
    assert decision.blocking_reasons == []
    assert _metric_value(
        "neocortex_dataset_cutover_allowed_total") == allowed_before + 1.0
    assert _metric_value("neocortex_dataset_trainable_rows") == 1.0
    assert _metric_value("neocortex_dataset_diagnostics_only_rows") == 1.0
    assert _metric_value(
        "neocortex_dataset_trainable_rows") != trainable_before or trainable_before == 1.0
    assert _metric_value(
        "neocortex_dataset_diagnostics_only_rows") != diagnostics_before or diagnostics_before == 1.0
