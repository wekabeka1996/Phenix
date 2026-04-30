"""Compatibility wrapper for the neocortex-owned decision outcome row contract."""

from apps.reference.domains.neocortex.contracts.decision_outcome_ledger import (
    DECISION_OUTCOME_LEDGER_SCHEMA_PASSPORT_ID,
    DECISION_OUTCOME_LEDGER_VERSION,
    DecisionOutcomeLedgerRow,
    DecisionOutcomeTerminalStatus,
    ExecutionOutcome,
    map_terminal_status_to_execution_outcome,
)


__all__ = [
    "DECISION_OUTCOME_LEDGER_SCHEMA_PASSPORT_ID",
    "DECISION_OUTCOME_LEDGER_VERSION",
    "DecisionOutcomeLedgerRow",
    "DecisionOutcomeTerminalStatus",
    "ExecutionOutcome",
    "map_terminal_status_to_execution_outcome",
]
