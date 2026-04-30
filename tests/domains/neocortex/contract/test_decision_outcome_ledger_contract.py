from __future__ import annotations

import pytest

from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
    ExecutionOutcome,
)


def _row_kwargs(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision_id": "decision-1",
        "rid": "RID-1",
        "symbol": "btcusdt",
        "authority_mode": "shadow",
        "request_ts_ms": 1_700_000_000_000,
        "response_ts_ms": 1_700_000_000_001,
        "apply_result": "GATED_ALLOW",
        "fallback_reason": None,
        "terminal_status": DecisionOutcomeTerminalStatus.VETOED,
        "dataset_visibility": "trainable",
        "neocortex_action": "ALLOW",
    }
    payload.update(overrides)
    return payload


def test_contract_normalizes_enforce_mode_and_deny_action() -> None:
    row = DecisionOutcomeLedgerRow(
        **_row_kwargs(authority_mode="enforce", neocortex_action="DENY")
    )
    assert row.symbol == "BTCUSDT"
    assert row.authority_mode == "gated"
    assert row.neocortex_action == "BLOCK"


def test_contract_rejects_response_before_request() -> None:
    with pytest.raises(ValueError, match="response_ts_ms must be >= request_ts_ms"):
        DecisionOutcomeLedgerRow(
            **_row_kwargs(response_ts_ms=1_699_999_999_999)
        )


def test_contract_requires_invalid_reason_for_invalid_dataset() -> None:
    with pytest.raises(
        ValueError,
        match="invalid_reason_code is required when terminal_status=INVALID_FOR_DATASET",
    ):
        DecisionOutcomeLedgerRow(
            **_row_kwargs(
                terminal_status=DecisionOutcomeTerminalStatus.INVALID_FOR_DATASET,
                dataset_visibility="diagnostics_only",
            )
        )


def test_contract_rejects_trainable_invalid_reason_combination() -> None:
    with pytest.raises(ValueError, match="trainable rows cannot carry invalid_reason_code"):
        DecisionOutcomeLedgerRow(
            **_row_kwargs(
                invalid_reason_code="UNJOINABLE_LIFECYCLE",
                terminal_status=DecisionOutcomeTerminalStatus.VETOED,
                dataset_visibility="trainable",
            )
        )


def test_contract_accepts_explicit_matching_execution_outcome() -> None:
    row = DecisionOutcomeLedgerRow(
        **_row_kwargs(
            terminal_status=DecisionOutcomeTerminalStatus.REJECTED_UPSTREAM,
            execution_outcome=ExecutionOutcome.EXCHANGE_REJECTED,
        )
    )
    assert row.execution_outcome is ExecutionOutcome.EXCHANGE_REJECTED


def test_contract_rejects_mismatched_execution_outcome() -> None:
    with pytest.raises(
        ValueError,
        match="execution_outcome must match terminal_status compatibility mapping",
    ):
        DecisionOutcomeLedgerRow(
            **_row_kwargs(
                terminal_status=DecisionOutcomeTerminalStatus.VETOED,
                execution_outcome=ExecutionOutcome.EXECUTED,
            )
        )
