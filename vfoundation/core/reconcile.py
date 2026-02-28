"""
RECONCILE verb handler (Phase 13.1).

Implements position reconciliation between internal WAL state and
exchange-reported positions. Detects and classifies divergences.

Constitution verb registry requirement: RECONCILE must appear in
vfoundation/dictionaries/verb_registry_v1.yaml before use.
See: docs/verb_registry_v1.yaml (Phase 13 registry entry required).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ReconcileStatus(str, Enum):
    """Status of a reconciliation check for a single symbol position."""
    MATCH = "MATCH"           # Internal and external agree
    DIVERGED = "DIVERGED"     # Values differ beyond tolerance
    MISSING_LOCAL = "MISSING_LOCAL"    # External has position, internal doesn't
    MISSING_EXTERNAL = "MISSING_EXTERNAL"  # Internal has position, external doesn't


@dataclass
class PositionSnapshot:
    """Position snapshot from one source (internal WAL or external exchange)."""
    symbol: str
    qty: float
    cost_basis: Optional[float] = None
    source: str = "unknown"


@dataclass
class ReconcileMismatch:
    """Divergence found during reconciliation."""
    symbol: str
    status: ReconcileStatus
    internal_qty: Optional[float]
    external_qty: Optional[float]
    delta_qty: Optional[float]
    reason: str = ""


@dataclass
class ReconcileReport:
    """Result of a reconciliation run."""
    total_symbols: int
    matched: int
    mismatches: List[ReconcileMismatch] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def match_rate(self) -> float:
        """Fraction of symbols that matched (0.0–1.0)."""
        if self.total_symbols == 0:
            return 1.0
        return self.matched / self.total_symbols

    @property
    def all_match(self) -> bool:
        """True if all symbols matched (no mismatches)."""
        return len(self.mismatches) == 0


class PositionReconciler:
    """
    Reconciles internal positions (from WAL) against exchange-reported positions.

    Args:
        tolerance: Maximum absolute quantity divergence before flagging as DIVERGED.
                   Defaults to 1e-8 (float precision tolerance).
    """

    def __init__(self, tolerance: float = 1e-8) -> None:
        self.tolerance = tolerance

    def reconcile(
        self,
        internal: List[PositionSnapshot],
        external: List[PositionSnapshot],
    ) -> ReconcileReport:
        """
        Compare internal and external position snapshots.

        Args:
            internal: List of positions from WAL/internal state.
            external: List of positions from exchange.

        Returns:
            ReconcileReport with match statistics and mismatch details.
        """
        internal_map: Dict[str, PositionSnapshot] = {p.symbol: p for p in internal}
        external_map: Dict[str, PositionSnapshot] = {p.symbol: p for p in external}
        all_symbols = set(internal_map) | set(external_map)

        mismatches: List[ReconcileMismatch] = []
        matched = 0

        for symbol in sorted(all_symbols):
            int_pos = internal_map.get(symbol)
            ext_pos = external_map.get(symbol)

            if int_pos is None:
                mismatches.append(ReconcileMismatch(
                    symbol=symbol,
                    status=ReconcileStatus.MISSING_LOCAL,
                    internal_qty=None,
                    external_qty=ext_pos.qty if ext_pos else None,
                    delta_qty=ext_pos.qty if ext_pos else None,
                    reason=f"No internal position for {symbol}",
                ))
            elif ext_pos is None:
                mismatches.append(ReconcileMismatch(
                    symbol=symbol,
                    status=ReconcileStatus.MISSING_EXTERNAL,
                    internal_qty=int_pos.qty,
                    external_qty=None,
                    delta_qty=int_pos.qty,
                    reason=f"Exchange has no position for {symbol}",
                ))
            else:
                delta = abs(int_pos.qty - ext_pos.qty)
                if delta <= self.tolerance:
                    matched += 1
                else:
                    mismatches.append(ReconcileMismatch(
                        symbol=symbol,
                        status=ReconcileStatus.DIVERGED,
                        internal_qty=int_pos.qty,
                        external_qty=ext_pos.qty,
                        delta_qty=int_pos.qty - ext_pos.qty,
                        reason=f"Qty delta={delta:.8f} exceeds tolerance={self.tolerance}",
                    ))

        return ReconcileReport(
            total_symbols=len(all_symbols),
            matched=matched,
            mismatches=mismatches,
        )


class ReconcileEngine:
    """Blueprint 13.1: WAL-based reconciliation with CMD:REPAIR emission.

    Reads WAL fill events, builds internal PositionSnapshot list,
    reconciles against external positions, and emits CMD:REPAIR dicts
    for each mismatch.
    """

    def __init__(
        self,
        reconciler: Optional[PositionReconciler] = None,
        tolerance: float = 1e-8,
    ) -> None:
        self._reconciler = reconciler or PositionReconciler(tolerance=tolerance)

    def reconcile_from_wal(
        self,
        wal_events: List[Dict[str, Any]],
        external: List[PositionSnapshot],
        since_ts: int = 0,
    ) -> Tuple[ReconcileReport, List[Dict[str, Any]]]:
        """Reconcile WAL fills against external positions.

        Args:
            wal_events: List of WAL event dicts (must have 'ts', 'verb', 'pld').
            external: Exchange-reported position snapshots.
            since_ts: Only consider WAL events with ts > since_ts.

        Returns:
            (report, repair_commands): ReconcileReport and list of CMD:REPAIR dicts.
        """
        # Filter WAL events by timestamp
        fills = [
            e for e in wal_events
            if int(e.get("ts", 0)) > since_ts
            and e.get("verb") in ("FILL", "ORDER_FILL")
        ]

        # Build internal position snapshots from fills
        position_map: Dict[str, float] = {}
        for fill in fills:
            pld = fill.get("pld", {})
            symbol = pld.get("symbol", "")
            qty = float(pld.get("qty", 0))
            side = pld.get("side", "BUY")
            if symbol:
                if side == "SELL":
                    position_map[symbol] = position_map.get(symbol, 0.0) - qty
                else:
                    position_map[symbol] = position_map.get(symbol, 0.0) + qty

        internal = [
            PositionSnapshot(symbol=sym, qty=qty, source="wal")
            for sym, qty in position_map.items()
        ]

        # Delegate to PositionReconciler
        report = self._reconciler.reconcile(internal, external)

        # Build CMD:REPAIR commands for mismatches
        repairs: List[Dict[str, Any]] = []
        for mm in report.mismatches:
            repairs.append({
                "op": "CMD",
                "verb": "REPAIR",
                "pld": {
                    "symbol": mm.symbol,
                    "status": mm.status.value,
                    "internal_qty": mm.internal_qty,
                    "external_qty": mm.external_qty,
                    "delta_qty": mm.delta_qty,
                    "reason": mm.reason,
                },
            })

        return report, repairs
