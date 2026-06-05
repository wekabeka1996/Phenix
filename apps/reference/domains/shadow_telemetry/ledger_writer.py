"""Compatibility wrapper for the neocortex-owned decision outcome ledger sink."""

from apps.reference.domains.neocortex.logic.ledger.decision_outcome_ledger import (
    DecisionOutcomeLedgerSink,
)


class ShadowTelemetrySink(DecisionOutcomeLedgerSink):
    """Backward-compatible alias for the legacy shadow telemetry import path."""


__all__ = ["DecisionOutcomeLedgerSink", "ShadowTelemetrySink"]
