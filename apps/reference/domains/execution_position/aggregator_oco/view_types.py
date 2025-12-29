"""
View Types for Aggregator OCO — Contract Layer
================================================

Phase 11: Extracted from bracket_service.py to break production dependency.

These dataclasses represent normalized views of positions and orders
used by the Aggregator OCO engine, runtime, and cleanup modules.

NO imports from bracket_service — this is the source of truth for view types.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


# ============================================================================
# Position Cycle ID Utilities
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


# ============================================================================
# View Data Models
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


# ============================================================================
# Client Order ID Generation
# ============================================================================

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

        # 4. Position Fingerprint (Qty + Price)
        # We use a hash to ensure changes in qty/price result in different IDs
        # even if the prefix consumes most of the space.
        pos_fingerprint = f"{abs(position.qty):.8f}_{position.avg_entry_price:.8f}"
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
# Bracket Rules Configuration (for runtime)
# ============================================================================

@dataclass(frozen=True)
class BracketRulesConfig:
    """
    Configuration for bracket evaluation rules.
    Maps to YAML: config.domains.execution.manage.brackets.aggregated_oco

    Phase 11: Extracted from bracket_service.py for runtime use.
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
