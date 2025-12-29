"""
BracketService — Pure Computation Layer for Bracket State Management
=====================================================================

╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️  DEPRECATED / TEST-ONLY — Phase 10 (2025-11-30)                          ║
║                                                                              ║
║  This module is RETIRED from production code as of PHASE10.                  ║
║  Production path now uses:                                                   ║
║    aggregator_oco/core_math.py → _compute_bracket_plan_core()                ║
║                                                                              ║
║  This file is preserved ONLY for:                                            ║
║    1. Test harness (unit tests that build mock BracketState)                 ║
║    2. Historical reference and audit trail                                   ║
║    3. Potential re-use of types: BracketLeg, BracketSet, BracketState        ║
║                                                                              ║
║  DO NOT import BracketService in production runtime code.                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Contract: EP-PORT-BRACKETS-S1-PH1 (v1.0)
Implementation: EP-PORT-BRACKETS-S1-PH2

This module provides a side-effect-free service for:
- Reconstructing bracket state from positions + orders + guardian metadata.
- Checking aggregated OCO invariants.
- Producing typed BracketPlan with recommended BracketAction(s).
- Providing structured XAI why-chains for all decisions.

NO side effects:
- No adapter calls.
- No logging in core logic.
- No global state.

All actions are recommendations; caller (FSM/adapter) executes them.
"""
from __future__ import annotations

import re
import time
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple, NamedTuple

# Phase 2: Import contract types from aggregator_oco
from apps.reference.domains.execution_position.aggregator_oco.contracts import (
    BracketAction as _ContractBracketAction,
    BracketPlan as _ContractBracketPlan,
    SeverityType,
)

# Phase 7: Import core math for SL/TP calculation (single source of truth)
from apps.reference.domains.execution_position.aggregator_oco.core_math import (
    compute_desired_levels as _core_compute_desired_levels,
    PriceConstraints as _CorePriceConstraints,
)


# ============================================================================
# R2-D: Position Cycle ID Utilities
# ============================================================================

def parse_cycle_id_from_client_order_id(client_order_id: str) -> int:
    """
    Parse cycle_id from clientOrderId format: "AUR-{symbol}-{side}-{action}-C{cycle_id}-{fingerprint}"

    Returns:
        cycle_id (int): Parsed cycle_id, or 0 if not found (legacy orders).
    """
    if not client_order_id:
        return 0

    # Match pattern: "-C<digits>-" or "-C<digits>" at end
    match = re.search(r'-C(\d+)(?:-|$)', client_order_id)
    if match:
        return int(match.group(1))

    return 0  # Legacy order without cycle_id


def build_position_id(symbol: str, position: PositionView) -> str:
    """
    Build deterministic position fingerprint for bracket clientOrderId.
    """
    qty_tag = f"{abs(position.qty):.4f}"
    price_tag = f"{position.avg_entry_price:.2f}" if position.avg_entry_price else "0"
    return f"{qty_tag}-{price_tag}"


def make_bracket_client_order_id(
    symbol: str,
    action_type: str,
    exit_side: Optional[str],
    qty: float,
    price: Optional[Decimal],
    position: Optional[PositionView] = None,
) -> str:
    """
    Generate deterministic clientOrderId for bracket orders to improve idempotency.
    R2-D: Includes cycle_id suffix for position lifecycle separation.
    """
    if position is not None:
        # Compact format to avoid truncation collisions
        # AUR-{symbol}-{S/L}-{TP/SL}-C{cycle}-{hash}

        # 1. Compact Side
        side_code = "L" if position.side == "LONG" else "S"

        # 2. Compact Action
        if "TP" in action_type:
            act_code = "TP"
        elif "SL" in action_type:
            act_code = "SL"
        else:
            act_code = "XX"

        # 3. Cycle
        cycle_suffix = f"C{position.cycle_id}"

        # 4. Position Fingerprint (Qty + Price + Timestamp)
        # We use a hash to ensure changes in qty/price result in different IDs
        # even if the prefix consumes most of the space.
        # Add timestamp to ensure uniqueness across restarts
        import time
        pos_fingerprint = f"{abs(position.qty):.8f}_{position.avg_entry_price:.8f}_{time.time_ns()}"
        pos_hash = hashlib.sha256(
            pos_fingerprint.encode("utf-8")).hexdigest()[:6]

        # Construct ID
        # AUR-BNBUSDT-S-TP-C0-a1b2c3
        base = f"AUR-{symbol}-{side_code}-{act_code}-{cycle_suffix}-{pos_hash}"

        # If still too long (very long symbol), truncate symbol, not hash
        if len(base) > 32:
            overage = len(base) - 32
            # Truncate symbol from the end, keeping at least 4 chars
            if len(symbol) > overage + 4:
                short_symbol = symbol[:-overage]
                base = f"AUR-{short_symbol}-{side_code}-{act_code}-{cycle_suffix}-{pos_hash}"
            else:
                # Fallback: keep hash, truncate middle
                # AUR-...-a1b2c3 (keep last 7 chars: -hash)
                prefix_len = 32 - 7
                prefix = f"AUR-{symbol}-{side_code}-{act_code}-{cycle_suffix}"
                base = f"{prefix[:prefix_len]}-{pos_hash}"

        return base

    seed = f"{symbol}|{action_type}|{exit_side}|{qty}|{price}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return f"AUR-BRK-{digest}"


# ============================================================================
# Data Models (Contract Section 3)
# ============================================================================

@dataclass(frozen=True)
class PositionView:
    """
    Normalized position snapshot for bracket evaluation.
    Source: adapter.get_open_positions() or ExecPosRuntimeV2 internal state.
    """
    symbol: str                         # e.g., "BTCUSDT"
    side: str                           # "LONG" or "SHORT" (canonical form)
    qty: Decimal                        # Current position quantity (abs value)
    avg_entry_price: Decimal            # Weighted average entry price
    # Cumulative realized PnL (optional)
    realized_pnl: Optional[Decimal] = None
    # Unrealized PnL at current mark price (optional)
    unrealized_pnl: Optional[Decimal] = None
    # Timestamp of last position update (seconds)
    update_ts: float = field(default_factory=time.time)
    cycle_id: int = 0                   # R2-D: Position cycle identifier

    def __post_init__(self):
        """Validate invariants."""
        if self.qty < 0:
            raise ValueError(f"PositionView.qty must be >= 0, got {self.qty}")
        if self.side not in ("LONG", "SHORT"):
            raise ValueError(
                f"PositionView.side must be LONG or SHORT, got {self.side!r}")
        if self.qty > 0 and self.avg_entry_price <= 0:
            raise ValueError(
                f"PositionView.avg_entry_price must be > 0 when qty > 0, got {self.avg_entry_price}")


@dataclass(frozen=True)
class OrderView:
    """
    Normalized order snapshot for bracket evaluation.
    Source: adapter.get_open_orders() or OrderGuardian metadata.
    """
    order_id: str                       # Exchange-assigned order ID
    # Client-assigned order ID (for tracking)
    client_order_id: str
    symbol: str                         # e.g., "BTCUSDT"
    # "BUY" or "SELL" (order side, not position side)
    side: str
    # "LIMIT", "MARKET", "STOP_MARKET", "TAKE_PROFIT_MARKET"
    order_type: str
    qty: Decimal                        # Order quantity
    price: Optional[Decimal] = None     # Limit price (None for MARKET)
    stop_price: Optional[Decimal] = None   # Stop price (for STOP/TP orders)
    reduce_only: bool = False           # True for SL/TP (exit orders)
    close_position: bool = False        # True if order closes entire position
    status: str = "NEW"                 # "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED"
    # Order creation timestamp (seconds)
    created_ts: float = field(default_factory=time.time)
    # Last order update timestamp (seconds)
    update_ts: float = field(default_factory=time.time)
    # R2-D: Position cycle identifier (parsed from clientOrderId)
    cycle_id: int = 0

    def __post_init__(self):
        """Validate invariants."""
        if not self.order_id:
            raise ValueError("OrderView.order_id cannot be empty")
        if self.qty <= 0:
            raise ValueError(f"OrderView.qty must be > 0, got {self.qty}")
        if self.side not in ("BUY", "SELL"):
            raise ValueError(
                f"OrderView.side must be BUY or SELL, got {self.side!r}")
        if self.status not in ("NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED"):
            raise ValueError(f"OrderView.status invalid: {self.status!r}")


@dataclass(frozen=True)
class BracketLeg:
    """
    A single order classified by its role in bracket protection.
    """
    leg_type: Literal["ENTRY", "SL", "TP"]  # Role in bracket set
    order: OrderView                        # Full order details
    # "guardian" | "runtime" | "wal" | "exchange"
    source: str = "exchange"
    confidence: float = 1.0                 # 0.0-1.0: how confident is classification

    @property
    def order_id(self) -> str:
        return self.order.order_id

    @property
    def price(self) -> Optional[Decimal]:
        """Returns stop_price for SL/TP, else limit price."""
        return self.order.stop_price or self.order.price


@dataclass(frozen=True)
class BracketSet:
    """
    Complete bracket set for a position (ENTRY + SL + TP legs).
    """
    symbol: str                         # e.g., "BTCUSDT"
    side: str                           # "LONG" or "SHORT"
    position_qty: Decimal               # Current position quantity
    avg_entry_price: Decimal            # Current average entry price
    legs: List[BracketLeg]              # All classified legs (ENTRY/SL/TP)
    created_ts: float                   # Bracket set creation timestamp
    updated_ts: float                   # Last bracket update timestamp
    # Guardian metadata (bracket_set_id, version)
    meta: Optional[Dict[str, Any]] = None

    @property
    def sl_legs(self) -> List[BracketLeg]:
        return [leg for leg in self.legs if leg.leg_type == "SL"]

    @property
    def tp_legs(self) -> List[BracketLeg]:
        return [leg for leg in self.legs if leg.leg_type == "TP"]

    @property
    def entry_legs(self) -> List[BracketLeg]:
        return [leg for leg in self.legs if leg.leg_type == "ENTRY"]


@dataclass(frozen=True)
class BracketState:
    """
    Immutable snapshot of bracket state for (symbol, side).
    Input to BracketService.evaluate().
    """
    symbol: str                         # e.g., "BTCUSDT"
    side: str                           # "LONG" or "SHORT"
    position_view: Optional[PositionView]  # None if FLAT position
    bracket_set: Optional[BracketSet]   # None if no brackets
    # OrderGuardian metadata (optional)
    guardian_meta: Optional[Dict[str, Any]] = None
    # Timestamp of state snapshot
    snapshot_ts: float = field(default_factory=time.time)
    # R2-E: Instrument precision for rounding (default 0.01 for backward compatibility)
    tick_size: Decimal = field(default=Decimal("0.01"))

    @property
    def is_flat(self) -> bool:
        """Position is FLAT (qty ≈ 0)."""
        return self.position_view is None or self.position_view.qty == 0

    @property
    def has_brackets(self) -> bool:
        """Brackets exist for this position."""
        return self.bracket_set is not None and len(self.bracket_set.legs) > 0

    @property
    def sl_count(self) -> int:
        """Count of SL legs in bracket set."""
        return len(self.bracket_set.sl_legs) if self.bracket_set else 0

    @property
    def tp_count(self) -> int:
        """Count of TP legs in bracket set."""
        return len(self.bracket_set.tp_legs) if self.bracket_set else 0


# ============================================================================
# Phase 2: Re-export BracketAction and BracketPlan from contracts.py
# ============================================================================
# These types are now defined in aggregator_oco/contracts.py (single source of truth)
# We re-export them here for backward compatibility with existing imports.

BracketAction = _ContractBracketAction
BracketPlan = _ContractBracketPlan


class BracketExecutionPlan(NamedTuple):
    """
    Thin wrapper over BracketPlan actions with XAI reason (tooling/runtime hand-off).
    """
    actions: List[BracketAction]
    why: str

    @staticmethod
    def from_plan(plan: "BracketPlan") -> "BracketExecutionPlan":
        """Helper to wrap an existing BracketPlan."""
        return BracketExecutionPlan(actions=plan.actions, why=plan.why)


# ============================================================================
# Config Model (Contract Section 6)
# ============================================================================

@dataclass(frozen=True)
class BracketRulesConfig:
    """
    Configuration for bracket evaluation rules.
    Maps to YAML: config.domains.execution.manage.brackets.aggregated_oco
    """
    enabled: bool = True
    allow_unprotected_position: bool = False    # Strict mode (require SL)
    recalc_on_partial_close: bool = True        # Always recalc (V2 invariant)
    recalc_on_scale_in: bool = True             # Always recalc (V2 invariant)
    ttl_protect_new_bracket_ms: int = 5000      # 5 seconds TTL protection
    max_tp_legs: int = 1                        # One TP per position
    max_sl_legs: int = 1                        # One SL per position
    sl_pct: float = 0.02                        # 2% SL distance from entry
    tp_rr: float = 2.0                          # 2:1 reward/risk ratio
    # R2-E: Recreate SL/TP if missing (fail-closed)
    recreate_missing_brackets: bool = True


# ============================================================================
# BracketService (Contract Section 4)
# ============================================================================

class BracketService:
    """
    Pure computation service for bracket state evaluation.
    No side effects (no adapter calls, no logging in core logic).
    """

    def __init__(
        self,
        aggregator: Any,                        # bracket_aggregator module
        # OrderGuardian instance (query-only)
        guardian: Any,
        watchdog: Optional[Any] = None,         # Optional watchdog hints
    ):
        """
        Initialize service with dependencies (query-only interfaces).

        Args:
            aggregator: Pure function module for computing TP/SL levels.
            guardian: OrderGuardian instance (for metadata queries).
            watchdog: Optional watchdog for additional hints.
        """
        self._aggregator = aggregator
        self._guardian = guardian
        self._watchdog = watchdog
        import logging
        self.logger = logging.getLogger(self.__class__.__name__)

    def build_state(
        self,
        positions: Iterable[PositionView],
        orders: Iterable[OrderView],
        guardian_meta: Optional[Any] = None,
        *,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        rid: Optional[str] = None,
        tick_size: Optional[Decimal] = None,
    ) -> Dict[Tuple[str, str], BracketState]:
        """
        Reconstruct BracketState for all or specific (symbol, side) pairs.

        Args:
            positions: Iterable of PositionView objects (from adapter or runtime).
            orders: Iterable of OrderView objects (from adapter or OrderGuardian).
            guardian_meta: Optional guardian metadata (for rehydration scenarios).
            symbol: Optional symbol filter (if None, all symbols processed).
            side: Optional side filter (if None, all sides processed).
            rid: Optional request ID for tracing.
            tick_size: Optional instrument tick size (default 0.01).

        Returns:
            Dict mapping (symbol, side) -> BracketState.

        Behavior:
            - Groups positions by (symbol, side).
            - Classifies orders into BracketLeg objects (ENTRY/SL/TP).
            - Constructs BracketSet for each position.
            - Queries OrderGuardian for metadata (bracket_set_id, created_ts, version).
            - Returns immutable BracketState snapshots.

        Determinism:
            - For identical inputs, produces identical output.
            - No hidden state, no side effects.

        Error Handling:
            - Invalid position/order data → raises ValueError with descriptive message.
            - Missing guardian metadata → continues with partial state.
            - Ambiguous classification → marks leg with confidence < 1.0.
        """
        # Group positions by (symbol, side)
        pos_map: Dict[Tuple[str, str], PositionView] = {}
        for pos in positions:
            key = (pos.symbol, pos.side)
            # Apply filters
            if symbol and pos.symbol != symbol:
                continue
            if side and pos.side != side:
                continue
            pos_map[key] = pos

        # Group orders by (symbol, side)
        orders_map: Dict[Tuple[str, str], List[OrderView]] = {}
        for order in orders:
            # Infer position side from order side (BUY → LONG, SELL → SHORT for reduce_only)
            # For entry orders, we need to match with position
            # For now, group by symbol only, then match
            if symbol and order.symbol != symbol:
                continue
            orders_map.setdefault(order.symbol, []).append(order)

        # Build BracketState for each (symbol, side)
        states: Dict[Tuple[str, str], BracketState] = {}

        # Process all observed (symbol, side) pairs
        all_keys = set(pos_map.keys())

        # If symbol/side filters provided, only process those
        if symbol and side:
            # Explicit filter: only add if has position or orders for this symbol
            if (symbol, side) in pos_map or symbol in orders_map:
                all_keys.add((symbol, side))
        else:
            # No explicit filter: add all sides for symbols with orders
            for sym in orders_map.keys():
                # Orders may belong to LONG or SHORT positions
                # Only add if filters don't exclude them
                if side is None or side == "LONG":
                    all_keys.add((sym, "LONG"))
                if side is None or side == "SHORT":
                    all_keys.add((sym, "SHORT"))

        for key in all_keys:
            sym, sde = key
            pos_view = pos_map.get(key)

            # Get orders for this symbol
            symbol_orders = orders_map.get(sym, [])

            # Classify orders into legs
            legs = self._classify_orders(symbol_orders, sde, pos_view)

            # Build BracketSet only if legs exist or position exists
            bracket_set = None
            if legs or pos_view:
                created_ts = min(
                    (leg.order.created_ts for leg in legs), default=time.time())
                updated_ts = max(
                    (leg.order.update_ts for leg in legs), default=time.time())

                bracket_set = BracketSet(
                    symbol=sym,
                    side=sde,
                    position_qty=pos_view.qty if pos_view else Decimal(0),
                    avg_entry_price=pos_view.avg_entry_price if pos_view else Decimal(
                        0),
                    legs=legs,
                    created_ts=created_ts,
                    updated_ts=updated_ts,
                    meta=None,  # guardian_meta would go here if structured
                )

                # Build BracketState only if bracket_set exists (i.e., legs or pos_view)
                state = BracketState(
                    symbol=sym,
                    side=sde,
                    position_view=pos_view,
                    bracket_set=bracket_set,
                    guardian_meta=None,  # Pass through as-is if needed
                    snapshot_ts=time.time(),
                    tick_size=tick_size if tick_size is not None else Decimal(
                        "0.01"),
                )

                states[key] = state

        return states

    def _classify_orders(
        self,
        orders: List[OrderView],
        side: str,
        position: Optional[PositionView],
    ) -> List[BracketLeg]:
        """
        Classify orders into BracketLeg objects (ENTRY/SL/TP).

        Classification Logic:
        - reduce_only=True + order_type ∈ {"STOP_MARKET", "STOP"} → SL
        - reduce_only=True + order_type ∈ {"TAKE_PROFIT_MARKET", "TAKE_PROFIT"} → TP
        - reduce_only=False → ENTRY

        Args:
            orders: List of orders for this symbol.
            side: Position side ("LONG" or "SHORT").
            position: Optional position view (for context).

        Returns:
            List of BracketLeg objects.
        """
        legs = []

        for order in orders:
            # Filter orders by side compatibility
            # LONG position: exit orders are SELL, entry orders are BUY
            # SHORT position: exit orders are BUY, entry orders are SELL
            if order.reduce_only or order.close_position:
                # Exit order
                if side == "LONG" and order.side != "SELL":
                    continue  # Skip incompatible order
                if side == "SHORT" and order.side != "BUY":
                    continue  # Skip incompatible order
            else:
                # Entry order
                if side == "LONG" and order.side != "BUY":
                    continue  # Skip incompatible order
                if side == "SHORT" and order.side != "SELL":
                    continue  # Skip incompatible order

            # Determine leg type
            if order.reduce_only or order.close_position:
                # Exit orders (SL/TP)
                if "STOP" in order.order_type.upper():
                    leg_type = "SL"
                elif "TAKE_PROFIT" in order.order_type.upper() or "LIMIT" in order.order_type.upper():
                    leg_type = "TP"
                else:
                    # Ambiguous, default to SL for safety
                    leg_type = "SL"
            else:
                # Entry order
                leg_type = "ENTRY"

            leg = BracketLeg(
                leg_type=leg_type,  # type: ignore
                order=order,
                source="exchange",
                confidence=1.0,
            )
            legs.append(leg)

        return legs

    def _is_price_match(self, p1: Decimal, p2: Decimal, tolerance: Decimal = Decimal("0.0001")) -> bool:
        """Check if prices match within tolerance."""
        return abs(p1 - p2) <= tolerance

    def evaluate(
        self,
        state: BracketState,
        cfg: BracketRulesConfig,
        *,
        rid: Optional[str] = None,
    ) -> BracketPlan:
        """
        Evaluate BracketState against invariants and produce BracketPlan.

        Args:
            state: Immutable BracketState snapshot (from build_state()).
            cfg: Config object with aggregated_oco.* settings.
            rid: Optional request ID for tracing.

        Returns:
            BracketPlan with recommended actions, severity, and why.

        Behavior:
            - Checks all invariants (see contract section 5).
            - For each violation, generates appropriate BracketAction(s).
            - Computes desired bracket levels via bracket_aggregator (if needed).
            - Returns plan with ordered actions (CANCEL before PLACE).
            - If no violations, returns plan with severity=INFO and empty actions.

        Determinism:
            - For identical (state, cfg), produces identical plan.
            - Pure function, no side effects.

        Error Handling:
            - Invalid state → raises ValueError.
            - Ambiguous state (e.g., multiple valid interpretations) → returns plan with severity=ALERT, no actions, and descriptive why.
        """
        # Validate state
        if not state.symbol:
            raise ValueError("BracketState.symbol cannot be empty")
        if state.side not in ("LONG", "SHORT"):
            raise ValueError(
                f"BracketState.side must be LONG or SHORT, got {state.side!r}")

        # If disabled, return INFO no-op
        if not cfg.enabled:
            return BracketPlan(
                symbol=state.symbol,
                side=state.side,
                state=state,
                actions=[],
                severity="INFO",
                why="bracket_eval_disabled|cfg.enabled=false",
                rid=rid,
            )

        actions: List[BracketAction] = []
        severity: Literal["INFO", "WARN", "ALERT"] = "INFO"
        why = "brackets_ok|no_violations"

        # R2-D: Filter brackets by cycle_id and CANCEL orphans from previous cycles
        if state.bracket_set:
            current_cycle = state.position_view.cycle_id if state.position_view else 0

            # Separate current cycle brackets from old cycle orphans
            current_cycle_legs: List[BracketLeg] = []
            orphan_cycle_legs: List[BracketLeg] = []

            for leg in state.bracket_set.legs:
                if leg.order.cycle_id == current_cycle:
                    current_cycle_legs.append(leg)
                else:
                    orphan_cycle_legs.append(leg)

            # CANCEL orphan brackets from previous cycles
            if orphan_cycle_legs:
                severity = "WARN" if severity == "INFO" else severity
                why = f"orphan_cycle_mismatch|current={current_cycle}"

                for leg in orphan_cycle_legs:
                    actions.append(BracketAction(
                        action="CANCEL",
                        order_ref=leg.order_id,
                        client_order_id=leg.order.client_order_id,
                        reason_code="ORPHAN_CYCLE",
                        why=f"orphan_cycle|leg_cycle={leg.order.cycle_id}_pos_cycle={current_cycle}",
                        rid=rid,
                    ))

            # Rebuild bracket_set with only current cycle legs (filter by .legs field)
            if current_cycle_legs != state.bracket_set.legs:
                from dataclasses import replace as dc_replace
                state = dc_replace(state, bracket_set=dc_replace(
                    state.bracket_set,
                    legs=current_cycle_legs,
                ))

        # INVARIANT 1: Position FLAT → No Brackets (Orphan detection)
        if state.is_flat and state.has_brackets:
            severity = "WARN"
            why = "orphan_brackets|pos_flat_sl_or_tp_active"

            # CANCEL all SL/TP legs
            for leg in state.bracket_set.sl_legs:  # type: ignore
                actions.append(BracketAction(
                    action="CANCEL",
                    order_ref=leg.order_id,
                    client_order_id=leg.order.client_order_id,
                    reason_code="ORPHAN_SL",
                    why="orphan_sl|qty≈0_active_sl",
                    rid=rid,
                ))

            for leg in state.bracket_set.tp_legs:  # type: ignore
                actions.append(BracketAction(
                    action="CANCEL",
                    order_ref=leg.order_id,
                    client_order_id=leg.order.client_order_id,
                    reason_code="ORPHAN_TP",
                    why="orphan_tp|qty≈0_active_tp",
                    rid=rid,
                ))

        # INVARIANT 2: Position > 0 → Check SL requirements
        elif not state.is_flat and state.position_view:
            sl_count = state.sl_count
            tp_count = state.tp_count  # Define tp_count for this block

            # Missing SL
            if sl_count == 0:
                if not cfg.allow_unprotected_position:
                    # R2-E: Check if we should recreate missing brackets
                    if cfg.recreate_missing_brackets:
                        severity = "ALERT"
                        why = f"missing_sl|pos>0_sl_count=0"

                        # Compute desired SL level
                        desired_levels = self._compute_desired_levels(
                            state, cfg)

                        actions.append(BracketAction(
                            action="PLACE_SL", leg_type="SL",
                            target_price=desired_levels["sl_price"],
                            qty=state.position_view.qty,
                            reason_code="MISSING_SL_RECREATED",
                            why="missing_sl_recreated|recreate_missing_brackets=true",
                            rid=rid,
                        ))
                    else:
                        # Honor missing: do not recreate, but warn
                        severity = "WARN"
                        why = "missing_sl_honored|recreate_missing_brackets=false"
                        self.logger.warning(
                            "[BracketService] Missing SL for open position; honoring config recreate_missing_brackets=False",
                            extra={
                                "symbol": state.symbol, "cycle_id": state.position_view.cycle_id if state.position_view else 0, "rid": rid},
                        )
                else:
                    # Allowed unprotected position
                    severity = "INFO"
                    why = "unprotected_ok|cfg.allow_unprotected_position=true"

            # INVARIANT 2b: Missing TP when position exists
            if state.position_view.qty != 0 and tp_count == 0:
                # Only place TP if we have SL (or are placing one)
                # This ensures we don't place TP without protection
                if sl_count > 0 or any(a.action == "PLACE_SL" for a in actions):
                    # R2-E: Check if we should recreate missing TP
                    if cfg.recreate_missing_brackets:
                        desired_levels = self._compute_desired_levels(
                            state, cfg)

                        actions.append(BracketAction(
                            action="PLACE_TP", leg_type="TP",
                            target_price=desired_levels["tp_price"],
                            qty=state.position_view.qty,
                            reason_code="MISSING_TP_RECREATED",
                            why="missing_tp_recreated|recreate_missing_brackets=true",
                            rid=rid,
                        ))

                        if severity == "INFO":
                            severity = "WARN"
                            why = f"missing_tp|pos>0_tp_count=0"
                    else:
                        # Honor missing: do not recreate, but warn
                        if severity == "INFO":
                            severity = "WARN"
                            why = "missing_tp_honored|recreate_missing_brackets=false"
                        self.logger.warning(
                            "[BracketService] Missing TP for open position; honoring config recreate_missing_brackets=False",
                            extra={
                                "symbol": state.symbol, "cycle_id": state.position_view.cycle_id if state.position_view else 0, "rid": rid},
                        )

            # Too many SL
            if sl_count > cfg.max_sl_legs:
                severity = "WARN"
                why = f"too_many_sl|expected={cfg.max_sl_legs}_actual={sl_count}"

                # CANCEL extra SL orders (keep first one, cancel others)
                # type: ignore
                extra_sl_legs = state.bracket_set.sl_legs[cfg.max_sl_legs:]
                for i, leg in enumerate(extra_sl_legs):
                    actions.append(BracketAction(
                        action="CANCEL",
                        order_ref=leg.order_id,
                        client_order_id=leg.order.client_order_id,
                        reason_code="TOO_MANY_SL",
                        why=f"too_many_sl|redundant_sl_{i}",
                        rid=rid,
                    ))

            # INVARIANT 3: Check stale levels (if exactly 1 SL)
            if sl_count == 1 and severity == "INFO":
                desired_levels = self._compute_desired_levels(state, cfg)
                current_sl_leg = state.bracket_set.sl_legs[0]  # type: ignore
                current_sl_price = current_sl_leg.price

                # Check if SL price is stale (using tolerance)
                if current_sl_price and not self._is_price_match(current_sl_price, desired_levels["sl_price"]):
                    severity = "WARN"
                    why = f"stale_levels|sl_{current_sl_price}→{desired_levels['sl_price']}"

                    # CANCEL old SL
                    actions.append(BracketAction(
                        action="CANCEL",
                        order_ref=current_sl_leg.order_id,
                        client_order_id=current_sl_leg.order.client_order_id,
                        reason_code="STALE_LEVELS",
                        why="recalc|cancel_old_sl",
                        rid=rid,
                    ))

                    # PLACE new SL
                    actions.append(BracketAction(
                        action="PLACE_SL", leg_type="SL",
                        target_price=desired_levels["sl_price"],
                        qty=state.position_view.qty,
                        reason_code="STALE_LEVELS",
                        why=f"recalc|sl_update_{current_sl_price}→{desired_levels['sl_price']}"[
                            :80],
                        rid=rid,
                    ))

                # Check TP if exists
                if state.tp_count == 1:
                    # type: ignore
                    current_tp_leg = state.bracket_set.tp_legs[0]
                    current_tp_price = current_tp_leg.price

                    if current_tp_price and not self._is_price_match(current_tp_price, desired_levels["tp_price"]):
                        if severity == "INFO":
                            severity = "WARN"
                            why = f"stale_levels|tp_{current_tp_price}→{desired_levels['tp_price']}"

                        # CANCEL old TP
                        actions.append(BracketAction(
                            action="CANCEL",
                            order_ref=current_tp_leg.order_id,
                            client_order_id=current_tp_leg.order.client_order_id,
                            reason_code="STALE_LEVELS",
                            why="recalc|cancel_old_tp",
                            rid=rid,
                        ))

                        # PLACE new TP
                        actions.append(BracketAction(
                            action="PLACE_TP", leg_type="TP",
                            target_price=desired_levels["tp_price"],
                            qty=state.position_view.qty,
                            reason_code="STALE_LEVELS",
                            why=f"recalc|tp_update_{current_tp_price}→{desired_levels['tp_price']}"[
                                :80],
                            rid=rid,
                        ))

        # INVARIANT R1-B: Size sync — sum(bracket_qty) <= abs(position_qty) per side
        # This MUST run after all other invariant checks to ensure oversized brackets are cancelled
        size_invariant_actions = self._enforce_size_invariants(
            state, cfg, rid=rid)
        if size_invariant_actions:
            actions.extend(size_invariant_actions)
            if severity == "INFO":
                severity = "WARN"
            if why == "brackets_ok|no_violations":
                why = "size_invariant_violation|bracket_qty>position_qty"

        return BracketPlan(
            symbol=state.symbol,
            side=state.side,
            state=state,
            actions=actions,
            severity=severity,
            why=why[:80],  # Ensure ≤80 chars
            rid=rid,
        )

    def _compute_desired_levels(
        self,
        state: BracketState,
        cfg: BracketRulesConfig,
    ) -> Dict[str, Decimal]:
        """
        Compute desired SL/TP levels using aggregator.

        Args:
            state: Current bracket state.
            cfg: Bracket rules config.

        Returns:
            Dict with "sl_price" and "tp_price" keys.
        """
        if not state.position_view:
            return {"sl_price": Decimal(0), "tp_price": Decimal(0)}

        # Call aggregator (if available)
        if hasattr(self._aggregator, 'compute_aggregated_brackets'):
            # Import types from bracket_aggregator
            from vfoundation.apps.reference.domains.execution_position.bracket_aggregator import (
                AggregatedOcoRiskConfig,
                InstrumentPriceConstraints,
            )

            risk_cfg = AggregatedOcoRiskConfig(
                sl_pct=Decimal(str(cfg.sl_pct)),
                tp_rr=Decimal(str(cfg.tp_rr)),
            )

            # Simple constraints (will be overridden by caller with real data)
            constraints = InstrumentPriceConstraints(
                tick_size=state.tick_size,
                min_price=state.tick_size,
            )

            levels = self._aggregator.compute_aggregated_brackets(
                position_amt=state.position_view.qty,
                avg_entry_price=state.position_view.avg_entry_price,
                side=state.side,
                risk_cfg=risk_cfg,
                constraints=constraints,
                why="bracket_service_eval",
            )

            return {
                "sl_price": levels.sl_price,
                "tp_price": levels.tp_price,
            }

        # Phase 7: Delegate to core_math.compute_desired_levels (single source of truth)
        sl_pct = Decimal(str(cfg.sl_pct))
        tp_rr = Decimal(str(cfg.tp_rr))

        # Build optional constraints for rounding
        constraints = None
        if state.tick_size and state.tick_size > 0:
            constraints = _CorePriceConstraints(
                tick_size=state.tick_size,
                min_price=state.tick_size,
            )

        # Call core_math — the single source of SL/TP formulas
        desired = _core_compute_desired_levels(
            side=state.side,
            entry_price=state.position_view.avg_entry_price,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
            constraints=constraints,
        )

        return {
            "sl_price": desired.sl_price,
            "tp_price": desired.tp_price,
        }

    def _enforce_size_invariants(
        self,
        state: BracketState,
        cfg: BracketRulesConfig,
        *,
        rid: Optional[str] = None,
    ) -> List[BracketAction]:
        """
        Enforce R1-B size invariants: sum(bracket_qty) <= abs(position_qty) per side.

        This method runs AFTER all other invariant checks to ensure that:
        - sum(SL_qty) <= abs(position_qty)
        - sum(TP_qty) <= abs(position_qty)

        If violations detected:
        - Generate CANCEL actions for oversized brackets
        - Generate PLACE_SL/PLACE_TP with correct qty (if recalc_on_partial_close=True)

        Args:
            state: Current bracket state with position + bracket legs.
            cfg: Bracket rules config (for reference).
            rid: Optional request ID for tracing.

        Returns:
            List of BracketAction(CANCEL + PLACE) for resized brackets, or [] if no violations.

        Behavior:
            - FLAT position (qty≈0): Return [] (orphan cleanup handled separately)
            - Calculate total_sl_qty and total_tp_qty from state.bracket_set
            - If total exceeds position_qty:
              1. CANCEL oversized bracket
              2. PLACE new bracket with correct qty (if recalc_on_partial_close=True)
        """
        actions: List[BracketAction] = []

        # Skip if position is FLAT (orphan cleanup handled by main evaluate logic)
        if state.is_flat or not state.position_view:
            return actions

        position_qty = abs(state.position_view.qty)

        # Compute desired levels for PLACE actions
        desired_levels = self._compute_desired_levels(state, cfg)

        # Track if we need to place new brackets after cancelling
        need_place_sl = False
        need_place_tp = False

        # Check SL invariant: sum(SL_qty) <= position_qty
        sl_legs = state.bracket_set.sl_legs if state.bracket_set else []
        total_sl_qty = sum(leg.order.qty for leg in sl_legs if leg.order.qty)

        if total_sl_qty > position_qty:
            excess_sl = total_sl_qty - position_qty

            # Sort SL legs by created_ts (oldest first) or confidence (lowest first)
            sorted_sl_legs = sorted(
                sl_legs,
                key=lambda leg: (leg.confidence, leg.order.created_ts),
            )

            cancelled_qty = Decimal(0)
            for leg in sorted_sl_legs:
                if cancelled_qty >= excess_sl:
                    break

                actions.append(BracketAction(
                    action="CANCEL",
                    order_ref=leg.order_id,
                    client_order_id=leg.order.client_order_id,
                    reason_code="SIZE_INVARIANT_SL",
                    why=f"size_sync|sl_overshoot_{total_sl_qty}>{position_qty}",
                    rid=rid,
                ))

                cancelled_qty += leg.order.qty

            # R2-B-FIX: After cancelling oversized SL, place new SL with correct qty
            if cfg.recalc_on_partial_close and position_qty > 0:
                need_place_sl = True

        # Check TP invariant: sum(TP_qty) <= position_qty
        tp_legs = state.bracket_set.tp_legs if state.bracket_set else []
        total_tp_qty = sum(leg.order.qty for leg in tp_legs if leg.order.qty)

        if total_tp_qty > position_qty:
            excess_tp = total_tp_qty - position_qty

            # Sort TP legs similarly
            sorted_tp_legs = sorted(
                tp_legs,
                key=lambda leg: (leg.confidence, leg.order.created_ts),
            )

            cancelled_qty = Decimal(0)
            for leg in sorted_tp_legs:
                if cancelled_qty >= excess_tp:
                    break

                actions.append(BracketAction(
                    action="CANCEL",
                    order_ref=leg.order_id,
                    client_order_id=leg.order.client_order_id,
                    reason_code="SIZE_INVARIANT_TP",
                    why=f"size_sync|tp_overshoot_{total_tp_qty}>{position_qty}",
                    rid=rid,
                ))

                cancelled_qty += leg.order.qty

            # R2-B-FIX: After cancelling oversized TP, place new TP with correct qty
            if cfg.recalc_on_partial_close and position_qty > 0:
                need_place_tp = True

        # R2-B-FIX: Place resized brackets AFTER all CANCEL actions
        if need_place_sl:
            actions.append(BracketAction(
                action="PLACE_SL", leg_type="SL",
                target_price=desired_levels["sl_price"],
                qty=position_qty,
                reason_code="PARTIAL_CLOSE_RESIZE_SL",
                why=f"size_sync|resize_sl_to_{position_qty}",
                rid=rid,
            ))

        if need_place_tp:
            actions.append(BracketAction(
                action="PLACE_TP", leg_type="TP",
                target_price=desired_levels["tp_price"],
                qty=position_qty,
                reason_code="PARTIAL_CLOSE_RESIZE_TP",
                why=f"size_sync|resize_tp_to_{position_qty}",
                rid=rid,
            ))

        return actions

    def evaluate_all(
        self,
        positions: Iterable[PositionView],
        orders: Iterable[OrderView],
        cfg: BracketRulesConfig,
        guardian_meta: Optional[Any] = None,
        *,
        rid: Optional[str] = None,
    ) -> List[BracketPlan]:
        """
        Build state for all (symbol, side) pairs and evaluate each.
        Convenience method combining build_state() + evaluate() for all positions.

        Args:
            positions: Iterable of PositionView objects.
            orders: Iterable of OrderView objects.
            cfg: Config object with aggregated_oco.* settings.
            guardian_meta: Optional guardian metadata.
            rid: Optional request ID for tracing.

        Returns:
            List of BracketPlan objects (one per position).

        Behavior:
            - Calls build_state(positions, orders, guardian_meta).
            - For each state, calls evaluate(state, cfg).
            - Returns list of plans (unfiltered).

        Usage:
            - Background watchdog: evaluate all positions periodically.
            - DR/restart: check all positions for violations.
        """
        # Build all states
        states = self.build_state(
            positions=positions,
            orders=orders,
            guardian_meta=guardian_meta,
            rid=rid,
        )

        # Evaluate each state
        plans = []
        for state in states.values():
            plan = self.evaluate(state, cfg, rid=rid)
            plans.append(plan)

        return plans

    # Recovery helper (pure; same semantics as evaluate_all)
    def evaluate_all_for_recovery(
        self,
        positions: Iterable[PositionView],
        orders: Iterable[OrderView],
        cfg: BracketRulesConfig,
        guardian_meta: Optional[Any] = None,
        *,
        rid: Optional[str] = None,
    ) -> List[BracketPlan]:
        """
        Recovery pass wrapper: identical to evaluate_all, kept explicit for DR wiring.

        This method provides semantic context for Disaster Recovery (DR) scenarios.
        It allows callers to explicitly signal that they are performing a recovery
        evaluation, which aids in code readability and finding usages related to
        system restoration.
        """
        return self.evaluate_all(positions=positions, orders=orders, cfg=cfg, guardian_meta=guardian_meta, rid=rid)

    def on_algo_order_filled(
        self,
        update: Any,
        state: BracketState,
        cfg: BracketRulesConfig,
        rid: Optional[str] = None,
    ) -> BracketPlan:
        """
        React to ALGO_UPDATE event (e.g. conditional order filled).
        Pure function: returns a BracketPlan based on the update and current state.

        This method serves as an extension hook for Algo Order integration.
        Currently, it delegates to evaluate(), but it allows for future
        specialized logic (e.g., handling trailing stop triggers or
        conditional order chains) without changing the core interface.

        Args:
            update: AlgoOrderUpdate object (or dict).
            state: Current BracketState.
            cfg: Bracket configuration.
            rid: Request ID.

        Returns:
            BracketPlan recommending actions (if any).
        """
        # This method serves as the integration point for AlgoOrderIndex updates.
        # Since this service is pure, we treat the update as a signal to re-evaluate
        # the current state. The caller (Runtime) is responsible for ensuring
        # 'state' reflects the latest world view (including the effects of the fill if applied).

        # In the future, we can add specific logic here if Algo Orders carry
        # information not present in standard Position/Order views.

        return self.evaluate(state, cfg, rid=rid)

    def plan_orphan_cleanup(
        self,
        symbol: str,
        orders: Iterable[OrderView],
        *,
        rid: Optional[str] = None,
    ) -> BracketPlan:
        """
        Generate plan to cancel all orphan brackets (e.g. when position is FLAT).

        Args:
            symbol: Trading symbol.
            orders: All open orders for the symbol.
            rid: Optional request ID.

        Returns:
            BracketPlan with CANCEL actions for all reduce-only orders.
        """
        actions: List[BracketAction] = []

        for order in orders:
            # Check if order is a bracket (reduce_only SL/TP)
            is_bracket = order.reduce_only or order.close_position
            if not is_bracket:
                continue

            # Check order type compatibility
            is_sl = "STOP" in order.order_type.upper()
            is_tp = "TAKE_PROFIT" in order.order_type.upper(
            ) or "LIMIT" in order.order_type.upper()

            if is_sl or is_tp:
                actions.append(BracketAction(
                    action="CANCEL",
                    order_ref=order.order_id,
                    client_order_id=order.client_order_id,
                    reason_code="ORPHAN_CLEANUP",
                    why="orphan_cleanup|position_flat",
                    rid=rid,
                ))

        return BracketPlan(
            symbol=symbol,
            side="FLAT",  # Virtual side
            state=BracketState(
                symbol=symbol,
                side="LONG",  # Dummy side to satisfy validation
                position_view=None,
                bracket_set=None,
            ),
            actions=actions,
            severity="WARN" if actions else "INFO",
            why="orphan_cleanup_plan",
            rid=rid,
        )

    def plan_reverse_cleanup(
        self,
        symbol: str,
        prev_side: str,
        new_side: str,
        orders: Iterable[OrderView],
        *,
        rid: Optional[str] = None,
    ) -> BracketPlan:
        """
        Generate plan to cancel brackets from previous side after a reversal.

        Args:
            symbol: Trading symbol.
            prev_side: Previous position side ("LONG" or "SHORT").
            new_side: New position side ("LONG" or "SHORT").
            orders: All open orders for the symbol.
            rid: Optional request ID.

        Returns:
            BracketPlan with CANCEL actions for old side brackets.
        """
        actions: List[BracketAction] = []

        # Determine old exit side
        # LONG position -> SL/TP are SELL
        # SHORT position -> SL/TP are BUY
        old_exit_side = "SELL" if prev_side == "LONG" else "BUY"

        for order in orders:
            # Check if order is a bracket (reduce_only)
            is_bracket = order.reduce_only or order.close_position
            if not is_bracket:
                continue

            # Check if order side matches old exit side
            if order.side != old_exit_side:
                continue

            # Check order type compatibility
            is_sl = "STOP" in order.order_type.upper()
            is_tp = "TAKE_PROFIT" in order.order_type.upper(
            ) or "LIMIT" in order.order_type.upper()

            if is_sl or is_tp:
                actions.append(BracketAction(
                    action="CANCEL",
                    order_ref=order.order_id,
                    client_order_id=order.client_order_id,
                    reason_code="REVERSE_CLEANUP",
                    why=f"reverse_cleanup|{prev_side}->{new_side}",
                    rid=rid,
                ))

        return BracketPlan(
            symbol=symbol,
            side=new_side,
            state=BracketState(
                symbol=symbol,
                side=new_side,
                position_view=None,  # Not needed for cleanup plan
                bracket_set=None,
            ),
            actions=actions,
            severity="WARN" if actions else "INFO",
            why="reverse_cleanup_plan",
            rid=rid,
        )
