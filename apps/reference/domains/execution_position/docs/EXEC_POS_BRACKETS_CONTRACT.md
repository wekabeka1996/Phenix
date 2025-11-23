# BracketService Contract & Types Specification

**Version**: 1.0
**Status**: Contract-Only (Implementation TBD)
**Date**: 2025-11-21
**RID**: EP-PORT-BRACKETS-S1-PH1
**Owner**: Execution Position Domain

---

## 1. Overview

**Purpose**: This document defines the canonical contract for `BracketService`, a pure computation layer that:
1. Reconstructs bracket state from positions, orders, and guardian metadata.
2. Checks aggregated OCO invariants against current state.
3. Produces typed `BracketPlan` objects containing recommended `BracketAction`s.
4. Provides structured XAI why-chains for all decisions.
5. **Remains side-effect free** (no adapter calls, no logging in core logic).

**Architecture Position**:
```
ExecPosRuntimeV2 / ManageFlowFSM
         ↓
    BracketService (this contract)
         ↓ (queries only)
    bracket_aggregator + OrderGuardian + AggOcoWatchdogService
         ↓ (caller executes actions)
    BinanceAdapter (exchange operations)
```

**Related Documents**:
- `docs/EXEC_POS_BRACKETS_ANALYSIS.md` — Analysis of desired invariants, historical behaviors, V2 gaps.
- `docs/EXECUTION_POSITION_ORDER_GUARDIAN_CONTRACT.md` — OrderGuardian frozen contract v1.0.
- `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py` — Pure aggregated TP/SL computation.

**Contract Guarantees**:
- **Determinism**: For identical inputs (positions, orders, config), `evaluate()` produces identical `BracketPlan`.
- **Idempotency**: Re-evaluating same state without execution does not change recommendations.
- **No Side Effects**: Service only computes; caller (FSM/adapter) executes actions.
- **Explainability**: Every action has structured `why` field (≤80 chars).

---

## 2. Domain Glossary

### 2.1. Bracket Set
**Definition**: A collection of bracket orders (SL, TP) protecting a single aggregated position for `(symbol, side)`.

**Invariant**: In Aggregated OCO v1, exactly **one active bracket set** per `(symbol, side)` at any time.

**Lifecycle**:
- Created after entry fill (ManageFlowFSM places SL/TP).
- Updated on scale-in (recalc TP/SL to match new avg_entry).
- Updated on partial close (recalc TP/SL to match remaining qty).
- Removed when position closes to FLAT (OrderGuardian cleanup).

**Source of Truth**: OrderGuardian metadata (`BracketSetMeta` object).

---

### 2.2. Bracket Leg
**Definition**: A single order (ENTRY, SL, or TP) that is part of bracket protection for a position.

**Types**:
- **ENTRY**: Position-opening order (BUY/SELL).
- **SL**: Stop-loss order (reduceOnly=True, protects downside).
- **TP**: Take-profit order (reduceOnly=True, realizes upside).

**Properties**:
- `role`: Enum indicating ENTRY/SL/TP.
- `source`: Where leg data originated (guardian/runtime/wal/exchange).
- `order`: Full order details (`OrderView` object).

---

### 2.3. Bracket State
**Definition**: Complete snapshot of position + bracket orders + guardian metadata for `(symbol, side)` at a point in time.

**Purpose**: Input to `BracketService.evaluate()` method.

**Components**:
- `position_view`: Current position (qty, avg_entry, side) or None if FLAT.
- `bracket_set`: Active bracket legs (SL/TP orders) or None if no brackets.
- `guardian_meta`: OrderGuardian metadata (bracket_set_id, created_ts, version).

**Reconstruction**: Built by `BracketService.build_state()` from live positions/orders.

---

### 2.4. Bracket Plan
**Definition**: Evaluation result containing detected violations and recommended actions.

**Purpose**: Output of `BracketService.evaluate()` method.

**Components**:
- `state`: The `BracketState` that was evaluated.
- `actions`: List of typed `BracketAction` objects (CANCEL/PLACE_SL/PLACE_TP/ADJUST).
- `severity`: INFO (no issues), WARN (minor), ALERT (critical violation).
- `why`: High-level reason for plan (e.g., "missing_sl|pos>0_no_sl").

**Usage**: Caller (FSM) iterates `actions` and executes via adapter.

---

### 2.5. Aggregated OCO
**Definition**: Risk management architecture where **one bracket set** (SL+TP pair) protects the **aggregated position** (not individual entries).

**Key Properties**:
- TP/SL levels computed from `(avg_entry_price, position_qty, side, risk_cfg)`.
- Scale-in changes avg_entry → triggers recalc (if `recalc_on_scale_in=true`).
- Partial close changes qty → triggers recalc (if `recalc_on_partial_close=true`).
- One bracket set per side (no per-entry brackets).

**Contrast with Legacy**:
- Legacy (v1): Multiple bracket sets possible (one per entry order).
- Aggregated OCO (v2): Single bracket set per side (aggregated position).

---

### 2.6. Orphan SL/TP
**Definition**: Bracket orders (SL/TP) remaining active on exchange when position is FLAT (`position_amt ≈ 0`).

**Causes**:
- DEC:CLOSE execution succeeded but cleanup step failed.
- TP fill closed position but SL not cancelled.
- Exception during `reconcile_symbol()` left orphans.

**Detection**: Watchdog or BracketService finds reduceOnly orders with no corresponding position.

**Remediation**: CANCEL actions for all orphan brackets.

---

### 2.7. Recalc (Scale-In / Partial Close)
**Definition**: Process of updating bracket levels (TP/SL prices) when position state changes.

**Triggers**:
- **Scale-in**: Entry fill while position already open → avg_entry changes → recalc.
- **Partial close**: TP/SL partial fill → remaining qty changes → recalc (if `recalc_on_partial_close=true`).

**Workflow**:
1. Detect state change (scale-in or partial close event).
2. BracketService evaluates new state → produces `BracketPlan`.
3. Plan contains: `[CANCEL(old_sl), CANCEL(old_tp), PLACE_SL(new_level), PLACE_TP(new_level)]`.
4. Caller executes actions → updates OrderGuardian metadata.

**Historical Bug** (from analysis): Legacy recalc did NOT call `clear_guardian_bracket_set()` before placing new brackets → old order IDs overwritten → orphans created.

**V2 Fix**: BracketService explicitly produces CANCEL actions for old brackets before PLACE actions.

---

## 3. Data Model

### 3.1. PositionView
**Definition**: Logical view of a position's current state.

```python
@dataclass(frozen=True)
class PositionView:
    """
    Normalized position snapshot for bracket evaluation.
    Source: adapter.get_open_positions() or ExecPosRuntimeV2 internal state.
    """
    symbol: str                     # e.g., "BTCUSDT"
    side: str                       # "LONG" or "SHORT" (canonical form)
    qty: Decimal                    # Current position quantity (abs value)
    avg_entry_price: Decimal        # Weighted average entry price
    realized_pnl: Optional[Decimal] # Cumulative realized PnL (optional)
    unrealized_pnl: Optional[Decimal]  # Unrealized PnL at current mark price (optional)
    update_ts: float                # Timestamp of last position update (seconds)
```

**Invariants**:
- `qty >= 0` (always absolute value).
- `side in {"LONG", "SHORT"}` (no "FLAT" side; FLAT = qty ≈ 0).
- `avg_entry_price > 0` if `qty > 0`.

**Source**: Reconstructed from REST API `/fapi/v2/positionRisk` or internal WAL.

---

### 3.2. OrderView
**Definition**: Logical view of an order's current state.

```python
@dataclass(frozen=True)
class OrderView:
    """
    Normalized order snapshot for bracket evaluation.
    Source: adapter.get_open_orders() or OrderGuardian metadata.
    """
    order_id: str                   # Exchange-assigned order ID
    client_order_id: str            # Client-assigned order ID (for tracking)
    symbol: str                     # e.g., "BTCUSDT"
    side: str                       # "BUY" or "SELL" (order side, not position side)
    order_type: str                 # "LIMIT", "MARKET", "STOP_MARKET", "TAKE_PROFIT_MARKET"
    qty: Decimal                    # Order quantity
    price: Optional[Decimal]        # Limit price (None for MARKET)
    stop_price: Optional[Decimal]   # Stop price (for STOP/TP orders)
    reduce_only: bool               # True for SL/TP (exit orders)
    close_position: bool            # True if order closes entire position
    status: str                     # "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED"
    created_ts: float               # Order creation timestamp (seconds)
    update_ts: float                # Last order update timestamp (seconds)
```

**Invariants**:
- `qty > 0`.
- `reduce_only=True` → order is bracket leg (SL/TP).
- `reduce_only=False` → order is entry leg (or scale-in).

**Source**: Reconstructed from REST API `/fapi/v1/openOrders` or OrderGuardian store.

---

### 3.3. BracketLeg
**Definition**: Classified order with role (ENTRY/SL/TP) and source metadata.

```python
@dataclass(frozen=True)
class BracketLeg:
    """
    A single order classified by its role in bracket protection.
    """
    leg_type: Literal["ENTRY", "SL", "TP"]  # Role in bracket set
    order: OrderView                        # Full order details
    source: str                             # "guardian" | "runtime" | "wal" | "exchange"
    confidence: float                       # 0.0-1.0: how confident is classification

    @property
    def order_id(self) -> str:
        return self.order.order_id

    @property
    def price(self) -> Optional[Decimal]:
        """Returns stop_price for SL/TP, else limit price."""
        return self.order.stop_price or self.order.price
```

**Classification Logic**:
- `reduce_only=True` + `order_type="STOP_MARKET"` → SL leg.
- `reduce_only=True` + `order_type="TAKE_PROFIT_MARKET"` → TP leg.
- `reduce_only=False` → ENTRY leg.

**Source**:
- `guardian`: Order found in OrderGuardian metadata.
- `runtime`: Order tracked by ExecPosRuntimeV2 internal state.
- `wal`: Order reconstructed from WAL replay.
- `exchange`: Order found in live open_orders but not in metadata.

---

### 3.4. BracketSet
**Definition**: Collection of all bracket legs for `(symbol, side)`.

```python
@dataclass(frozen=True)
class BracketSet:
    """
    Complete bracket set for a position (ENTRY + SL + TP legs).
    """
    symbol: str                     # e.g., "BTCUSDT"
    side: str                       # "LONG" or "SHORT"
    position_qty: Decimal           # Current position quantity
    avg_entry_price: Decimal        # Current average entry price
    legs: List[BracketLeg]          # All classified legs (ENTRY/SL/TP)
    created_ts: float               # Bracket set creation timestamp
    updated_ts: float               # Last bracket update timestamp
    meta: Optional[Dict[str, Any]]  # Guardian metadata (bracket_set_id, version)

    @property
    def sl_legs(self) -> List[BracketLeg]:
        return [leg for leg in self.legs if leg.leg_type == "SL"]

    @property
    def tp_legs(self) -> List[BracketLeg]:
        return [leg for leg in self.legs if leg.leg_type == "TP"]

    @property
    def entry_legs(self) -> List[BracketLeg]:
        return [leg for leg in self.legs if leg.leg_type == "ENTRY"]
```

**Invariants** (from analysis):
- Exactly one SL leg (if `allow_unprotected_position=false`).
- Zero or one TP leg (TP is optional).
- Zero or more ENTRY legs (historical entries may remain tracked).

---

### 3.5. BracketState
**Definition**: Complete snapshot of position + bracket set for evaluation.

```python
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
    guardian_meta: Optional[Dict[str, Any]]  # OrderGuardian metadata (optional)
    snapshot_ts: float                  # Timestamp of state snapshot

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
```

**Usage**:
```python
# Example: Build state for BTCUSDT LONG
state = bracket_service.build_state(
    positions=[position_view],
    orders=[order1, order2, order3],
    guardian_meta=guardian.get_active_bracket_set("BTCUSDT", "LONG"),
    symbol="BTCUSDT",
    side="LONG",
)["BTCUSDT", "LONG"]
```

---

### 3.6. BracketAction
**Definition**: Atomic recommended action for bracket management.

```python
@dataclass(frozen=True)
class BracketAction:
    """
    Single recommended action for bracket management.
    Caller (FSM/adapter) decides whether to execute.
    """
    action_type: Literal["CANCEL", "PLACE_SL", "PLACE_TP", "ADJUST"]

    # For CANCEL/ADJUST actions
    order_id: Optional[str]         # Exchange order ID to cancel/adjust
    client_order_id: Optional[str]  # Client order ID (for tracking)

    # For PLACE_SL/PLACE_TP/ADJUST actions
    price: Optional[Decimal]        # Limit price (for TP) or stop price (for SL)
    qty: Optional[Decimal]          # Order quantity

    # XAI metadata
    reason_code: str                # "MISSING_SL" | "ORPHAN_SL" | "TOO_MANY_SL" | etc.
    why: str                        # Structured why (≤80 chars): "reason|detail"

    # Tracing
    rid: Optional[str]              # Request ID for tracing
    parent_why: Optional[str]       # Parent event that triggered this action
```

**Reason Codes** (examples):
- `MISSING_SL`: Position open but no SL order found.
- `ORPHAN_SL`: FLAT position but SL order still active.
- `TOO_MANY_SL`: Multiple SL orders for same position.
- `RECALC_SCALE_IN`: Scale-in fill requires bracket recalc.
- `RECALC_PARTIAL_CLOSE`: Partial TP/SL fill requires bracket recalc.
- `STALE_LEVELS`: Bracket levels do not match current position state.
- `DUPLICATE_SET`: Multiple bracket sets detected (DR/restart scenario).

**Why Format** (structured pattern):
```python
# Examples:
"missing_sl|pos>0_sl_count=0"
"orphan_sl|qty≈0_active_sl_ord=123"
"recalc_scale_in|avg_entry_24.1→25.3"
"too_many_sl|expected=1_actual=3"
"duplicate_set|found=2_kept_latest"
```

---

### 3.7. BracketPlan
**Definition**: Complete evaluation result with state + actions + severity.

```python
@dataclass(frozen=True)
class BracketPlan:
    """
    Evaluation result for a single (symbol, side) bracket state.
    Output of BracketService.evaluate().
    """
    symbol: str                     # e.g., "BTCUSDT"
    side: str                       # "LONG" or "SHORT"
    state: BracketState             # Input state that was evaluated
    actions: List[BracketAction]    # Recommended actions (ordered)
    severity: Literal["INFO", "WARN", "ALERT"]  # Violation severity
    why: str                        # High-level reason (≤80 chars)
    rid: Optional[str]              # Request ID for tracing
    evaluated_ts: float             # Timestamp of evaluation

    @property
    def has_actions(self) -> bool:
        """Plan contains actionable recommendations."""
        return len(self.actions) > 0

    @property
    def is_critical(self) -> bool:
        """Plan severity is ALERT (critical violation)."""
        return self.severity == "ALERT"
```

**Severity Levels**:
- `INFO`: No violations, informational only (e.g., brackets OK).
- `WARN`: Minor issue, not urgent (e.g., stale bracket levels, but SL exists).
- `ALERT`: Critical violation requiring immediate action (e.g., position open with no SL).

**Usage**:
```python
# Example: Evaluate state and execute plan
plan = bracket_service.evaluate(state, cfg, rid="REQ123")
if plan.has_actions:
    for action in plan.actions:
        if action.action_type == "CANCEL":
            await adapter.cancel_order(action.order_id)
        elif action.action_type == "PLACE_SL":
            await adapter.place_order(symbol=plan.symbol, side="SELL", ...)
    # Update guardian metadata
    guardian.register_bracket_set(...)
```

---

## 4. BracketService API

### 4.1. Service Initialization

```python
class BracketService:
    """
    Pure computation service for bracket state evaluation.
    No side effects (no adapter calls, no logging in core logic).
    """

    def __init__(
        self,
        aggregator: "BracketAggregator",      # bracket_aggregator module
        guardian: "OrderGuardianProtocol",    # OrderGuardian instance (query-only)
        watchdog: Optional["AggOcoWatchdogService"] = None,  # Optional watchdog hints
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
```

**Dependencies**:
- `BracketAggregator`: `bracket_aggregator.py` module (pure functions).
- `OrderGuardianProtocol`: OrderGuardian interface (query methods only: `get_active_bracket_set`, `list_all_bracket_sets`).
- `AggOcoWatchdogService`: Optional watchdog for recommendations (not used for core logic).

---

### 4.2. build_state() — State Reconstruction

```python
def build_state(
    self,
    positions: Iterable[PositionView],
    orders: Iterable[OrderView],
    guardian_meta: Optional[Any] = None,
    *,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    rid: Optional[str] = None,
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
        - Missing guardian metadata → logs warning, continues with partial state.
        - Ambiguous classification → marks leg with confidence < 1.0.
    """
    pass
```

**Examples**:
```python
# Example 1: Build state for all positions
all_states = service.build_state(
    positions=adapter.get_open_positions(),
    orders=adapter.get_open_orders(),
    rid="DR_STARTUP",
)

# Example 2: Build state for specific symbol/side
btc_long_state = service.build_state(
    positions=[btc_position],
    orders=adapter.get_open_orders(symbol="BTCUSDT"),
    guardian_meta=guardian.get_active_bracket_set("BTCUSDT", "LONG"),
    symbol="BTCUSDT",
    side="LONG",
    rid="SCALE_IN_EVAL",
)["BTCUSDT", "LONG"]
```

---

### 4.3. evaluate() — Invariant Checking

```python
def evaluate(
    self,
    state: BracketState,
    cfg: "BracketRulesConfig",
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
        - Checks all invariants (see section 5).
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
    pass
```

**Examples**:
```python
# Example 1: Evaluate state after scale-in
plan = service.evaluate(
    state=btc_long_state,
    cfg=config.aggregated_oco,
    rid="SCALE_IN_EVAL",
)
if plan.has_actions:
    logger.info(f"Bracket plan: {plan.why}, actions={len(plan.actions)}")

# Example 2: Evaluate FLAT position with orphan SL
flat_state = BracketState(
    symbol="BTCUSDT",
    side="LONG",
    position_view=None,  # FLAT
    bracket_set=BracketSet(..., legs=[sl_leg]),  # Orphan SL
    snapshot_ts=time.time(),
)
plan = service.evaluate(flat_state, cfg)
# plan.actions = [BracketAction(action_type="CANCEL", order_id="123", ...)]
```

---

### 4.4. evaluate_all() — Batch Evaluation

```python
def evaluate_all(
    self,
    positions: Iterable[PositionView],
    orders: Iterable[OrderView],
    cfg: "BracketRulesConfig",
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
    pass
```

**Examples**:
```python
# Example: Watchdog batch evaluation
all_plans = service.evaluate_all(
    positions=adapter.get_open_positions(),
    orders=adapter.get_open_orders(),
    cfg=config.aggregated_oco,
    rid="WATCHDOG_CYCLE",
)

critical_plans = [p for p in all_plans if p.is_critical]
if critical_plans:
    logger.alert(f"Critical violations: {len(critical_plans)}")
    for plan in critical_plans:
        logger.alert(f"  {plan.symbol} {plan.side}: {plan.why}")
```

---

### 4.5. Error Handling Strategy

**Input Validation Errors** → Raise exceptions:
```python
# Examples:
raise ValueError("PositionView.qty must be >= 0")
raise ValueError("OrderView.order_id cannot be empty")
raise ValueError("BracketState.symbol cannot be None")
```

**Ambiguous States** → Return plan with severity=ALERT, no actions:
```python
# Example: Multiple valid bracket sets found (DR scenario)
return BracketPlan(
    symbol="BTCUSDT",
    side="LONG",
    state=state,
    actions=[],  # No actions (ambiguous)
    severity="ALERT",
    why="ambiguous_state|multiple_bracket_sets_found",
    rid=rid,
    evaluated_ts=time.time(),
)
```

**Partial State** (missing data) → Log warning, continue with degraded plan:
```python
# Example: Guardian metadata missing (DR/restart)
# Service still produces plan based on live orders, but logs warning.
logger.warning(f"Guardian metadata missing for {symbol} {side}, using live orders only")
```

---

## 5. Invariants & Enforcement

### 5.1. Invariant 1: One Bracket Set per (Symbol, Side)

**Definition**: At any time, for a non-zero position, exactly **one** bracket set should be registered.

**Check Logic**:
```python
if state.position_view and state.position_view.qty > 0:
    if state.bracket_set is None:
        # No bracket set → invariant OK if no SL/TP orders found
        pass
    else:
        # Check for duplicate bracket sets in live orders
        guardian_meta = state.guardian_meta
        live_orders = state.bracket_set.legs
        # Compare guardian_meta order_ids with live order_ids
        # If mismatch → duplicate set detected
```

**Typical Violation**: Multiple SL orders with different `clientOrderId` prefixes.

**Recommended Actions**:
```python
# Violation: Multiple bracket sets detected
actions = [
    BracketAction(
        action_type="CANCEL",
        order_id=old_sl_order.order_id,
        reason_code="DUPLICATE_SET",
        why="duplicate_set|old_sl_cancelled",
    ),
    BracketAction(
        action_type="CANCEL",
        order_id=old_tp_order.order_id,
        reason_code="DUPLICATE_SET",
        why="duplicate_set|old_tp_cancelled",
    ),
]
```

**Severity**: WARN (not critical if one valid set exists).

---

### 5.2. Invariant 2: Position Amount == 0 → No Brackets

**Definition**: When position is FLAT (`qty ≈ 0`), **no** reduceOnly brackets should exist.

**Check Logic**:
```python
if state.is_flat:  # position_view is None or qty == 0
    if state.has_brackets:  # bracket_set.legs not empty
        # Violation: Orphan brackets
        return BracketPlan(
            actions=[...CANCEL actions...],
            severity="WARN",
            why="orphan_brackets|pos_flat_sl_active",
        )
```

**Typical Violation**: TP fill closed position, but SL not cancelled.

**Recommended Actions**:
```python
# Violation: FLAT position with active SL
actions = [
    BracketAction(
        action_type="CANCEL",
        order_id=sl_order.order_id,
        reason_code="ORPHAN_SL",
        why="orphan_sl|qty≈0_active_sl",
    ),
]

# Violation: FLAT position with active TP (edge case)
actions.append(
    BracketAction(
        action_type="CANCEL",
        order_id=tp_order.order_id,
        reason_code="ORPHAN_TP",
        why="orphan_tp|qty≈0_active_tp",
    )
)
```

**Severity**: WARN (not critical, but wastes exchange rate limits).

---

### 5.3. Invariant 3: Position > 0 → Exactly One SL (if !allow_unprotected_position)

**Definition**: Open position must have exactly **one active SL order** protecting downside.

**Check Logic**:
```python
if state.position_view and state.position_view.qty > 0:
    sl_count = state.sl_count
    if sl_count == 0:
        if not cfg.allow_unprotected_position:
            # Violation: Missing SL
            return BracketPlan(
                actions=[...PLACE_SL action...],
                severity="ALERT",  # Critical!
                why="missing_sl|pos>0_sl_count=0",
            )
    elif sl_count > 1:
        # Violation: Too many SL orders
        return BracketPlan(
            actions=[...CANCEL extra SL actions...],
            severity="WARN",
            why="too_many_sl|expected=1_actual={sl_count}",
        )
```

**Typical Violations**:
- **Missing SL**: Scale-in recalc failed, old SL cancelled but new SL not placed.
- **Too many SL**: Duplicate placement during DR/restart.

**Recommended Actions**:
```python
# Violation: Missing SL
desired_levels = bracket_aggregator.compute_aggregated_brackets(
    position_amt=state.position_view.qty,
    avg_entry_price=state.position_view.avg_entry_price,
    side=state.side,
    risk_cfg=cfg.risk_cfg,
    constraints=cfg.constraints,
)
actions = [
    BracketAction(
        action_type="PLACE_SL",
        price=desired_levels.sl_price,
        qty=state.position_view.qty,
        reason_code="MISSING_SL",
        why="missing_sl|pos>0_no_sl",
    ),
]

# Violation: Too many SL (keep one, cancel others)
# Choose "best" SL (closest to desired level or latest created_ts)
actions = [
    BracketAction(
        action_type="CANCEL",
        order_id=extra_sl.order_id,
        reason_code="TOO_MANY_SL",
        why=f"too_many_sl|redundant_sl_{i}",
    )
    for i, extra_sl in enumerate(extra_sl_orders)
]
```

**Severity**:
- Missing SL → ALERT (critical).
- Too many SL → WARN (not critical if at least one valid SL exists).

---

### 5.4. Invariant 4: Bracket Levels Match Aggregated Position State

**Definition**: TP/SL prices must be computed from **current** `(avg_entry_price, position_qty)`.

**Check Logic**:
```python
if state.position_view and state.bracket_set:
    # Compute desired levels
    desired_levels = bracket_aggregator.compute_aggregated_brackets(
        position_amt=state.position_view.qty,
        avg_entry_price=state.position_view.avg_entry_price,
        side=state.side,
        risk_cfg=cfg.risk_cfg,
        constraints=cfg.constraints,
    )

    # Compare with current bracket prices
    current_sl_price = state.bracket_set.sl_legs[0].price if state.bracket_set.sl_legs else None
    current_tp_price = state.bracket_set.tp_legs[0].price if state.bracket_set.tp_legs else None

    if current_sl_price != desired_levels.sl_price or current_tp_price != desired_levels.tp_price:
        # Violation: Stale bracket levels
        return BracketPlan(
            actions=[...CANCEL old, PLACE new...],
            severity="WARN",
            why=f"stale_levels|sl_{current_sl_price}→{desired_levels.sl_price}",
        )
```

**Typical Violations**:
- Scale-in changed avg_entry but brackets not recalculated.
- Partial close changed qty but brackets not recalculated.

**Recommended Actions**:
```python
# Violation: Stale bracket levels (recalc required)
actions = [
    # 1. Cancel old brackets
    BracketAction(
        action_type="CANCEL",
        order_id=old_sl.order_id,
        reason_code="RECALC_SCALE_IN",
        why=f"recalc|cancel_old_sl",
    ),
    BracketAction(
        action_type="CANCEL",
        order_id=old_tp.order_id,
        reason_code="RECALC_SCALE_IN",
        why=f"recalc|cancel_old_tp",
    ),
    # 2. Place new brackets
    BracketAction(
        action_type="PLACE_SL",
        price=desired_levels.sl_price,
        qty=state.position_view.qty,
        reason_code="RECALC_SCALE_IN",
        why=f"recalc_scale_in|avg_entry_{old_avg}→{new_avg}",
    ),
    BracketAction(
        action_type="PLACE_TP",
        price=desired_levels.tp_price,
        qty=state.position_view.qty,
        reason_code="RECALC_SCALE_IN",
        why=f"recalc_scale_in|tp_update",
    ),
]
```

**Severity**: WARN (SL exists, but at wrong level → still protected, but suboptimal).

---

### 5.5. Invariant 5: TTL Protection for New Brackets

**Definition**: Newly placed brackets (within `ttl_protect_new_bracket_ms`) are **protected** from cleanup.

**Check Logic**:
```python
if state.bracket_set:
    now_ts = time.time()
    for leg in state.bracket_set.legs:
        age_ms = (now_ts - leg.order.created_ts) * 1000
        if age_ms < cfg.ttl_protect_new_bracket_ms:
            # Leg is protected by TTL → skip CANCEL action
            logger.debug(f"TTL protection: {leg.order_id} age={age_ms}ms")
            continue
```

**Typical Usage**:
- Watchdog detects duplicate SL, but new SL just placed (< 5s ago) → skip CANCEL for new SL.
- Prevents race: cleanup cycle runs just after new brackets placed.

**Recommended Actions**:
```python
# Example: Too many SL detected, but one is TTL-protected
actions = [
    BracketAction(
        action_type="CANCEL",
        order_id=old_sl.order_id,
        reason_code="TOO_MANY_SL",
        why="too_many_sl|old_sl_cancelled",
    ),
    # New SL is TTL-protected → NOT included in actions
]
```

**Severity**: INFO (TTL protection is working as designed).

---

## 6. Config Contract

### 6.1. Configuration Fields

**YAML Path**: `config.domains.execution.manage.brackets.aggregated_oco`

```yaml
aggregated_oco:
  enabled: bool                         # Master switch for aggregated OCO
  allow_unprotected_position: bool      # Allow position without SL (testing mode)
  recalc_on_partial_close: bool         # Recalc brackets on partial TP/SL fill
  recalc_on_scale_in: bool              # Recalc brackets on scale-in fill
  ttl_protect_new_bracket_ms: int       # TTL protection window (ms)
  max_tp_legs: int                      # Max TP orders per position (default: 1)
  max_sl_legs: int                      # Max SL orders per position (default: 1)
  sl_pct: float                         # SL distance from entry (e.g., 0.02 = 2%)
  tp_rr: float                          # TP risk/reward ratio (e.g., 2.0 = 2:1)
```

### 6.2. Defaults & Validation

**Defaults**:
```python
DEFAULT_CONFIG = {
    "enabled": True,
    "allow_unprotected_position": False,  # Strict mode
    "recalc_on_partial_close": True,      # Always recalc (V2 invariant)
    "recalc_on_scale_in": True,           # Always recalc (V2 invariant)
    "ttl_protect_new_bracket_ms": 5000,   # 5 seconds
    "max_tp_legs": 1,                     # One TP per position
    "max_sl_legs": 1,                     # One SL per position
    "sl_pct": 0.02,                       # 2% SL
    "tp_rr": 2.0,                         # 2:1 reward/risk
}
```

**Validation Rules** (enforced by config resolver):
```python
# If aggregated_only_mode=true:
assert cfg.allow_unprotected_position == False, "aggregated_only requires strict SL"
assert cfg.recalc_on_partial_close == True, "aggregated_only requires recalc on partial close"
assert cfg.max_sl_legs == 1, "aggregated_only allows exactly one SL"

# TTL window sanity check:
assert 1000 <= cfg.ttl_protect_new_bracket_ms <= 30000, "TTL must be 1-30 seconds"

# Risk parameters:
assert 0 < cfg.sl_pct < 0.5, "sl_pct must be 0-50%"
assert 0 < cfg.tp_rr < 10, "tp_rr must be 0-10x"
```

### 6.3. Config Influence on evaluate()

**allow_unprotected_position**:
- If `false`: Missing SL → severity=ALERT, PLACE_SL action.
- If `true`: Missing SL → severity=INFO, no action (permissive mode).

**recalc_on_partial_close**:
- If `true`: Partial fill detected → BracketService produces recalc plan (CANCEL old + PLACE new).
- If `false`: Partial fill ignored → BracketService only checks stale levels (WARN).

**recalc_on_scale_in**:
- If `true`: Scale-in detected (avg_entry changed) → BracketService produces recalc plan.
- If `false`: Scale-in ignored → stale levels tolerated (WARN only).

**ttl_protect_new_bracket_ms**:
- CANCEL actions skip legs with `age_ms < ttl_protect_new_bracket_ms`.

**max_sl_legs / max_tp_legs**:
- Used in "too many SL/TP" check:
  ```python
  if sl_count > cfg.max_sl_legs:
      # Produce CANCEL actions for extra SL orders
  ```

---

## 7. Integration Points

### 7.1. Integration with bracket_aggregator

**Purpose**: Compute desired TP/SL levels from position state + risk config.

**Interface**:
```python
from vfoundation.apps.reference.domains.execution_position.bracket_aggregator import (
    compute_aggregated_brackets,
    AggregatedOcoRiskConfig,
    InstrumentPriceConstraints,
)

# BracketService calls aggregator:
risk_cfg = AggregatedOcoRiskConfig(
    sl_pct=Decimal(str(cfg.sl_pct)),
    tp_rr=Decimal(str(cfg.tp_rr)),
)
constraints = InstrumentPriceConstraints(
    tick_size=Decimal("0.01"),
    min_price=Decimal("0.01"),
)
levels = compute_aggregated_brackets(
    position_amt=state.position_view.qty,
    avg_entry_price=state.position_view.avg_entry_price,
    side=state.side,
    risk_cfg=risk_cfg,
    constraints=constraints,
    why="bracket_service_recalc",
)
# levels.sl_price, levels.tp_price, levels.why
```

**Contract**:
- `compute_aggregated_brackets()` is pure function (no side effects).
- Returns `AggregatedBracketLevels` with rounded prices (tick_size compliant).
- `why` field (≤80 chars) passed through to BracketAction.

**Usage in BracketService**:
- Called during `evaluate()` when checking "bracket levels match position state" invariant.
- Called when producing PLACE_SL/PLACE_TP actions.

---

### 7.2. Integration with OrderGuardian

**Purpose**: Query bracket metadata for state reconstruction and validation.

**Interface** (query-only):
```python
# BracketService queries guardian:
guardian_meta = self._guardian.get_active_bracket_set(symbol="BTCUSDT", side="LONG")
# Returns BracketSetMeta or None

all_metas = self._guardian.list_all_bracket_sets()
# Returns List[BracketSetMeta]
```

**Contract**:
- BracketService **does NOT call** guardian mutation methods (`register_bracket_set`, `clear_bracket_set_for_position`, etc.).
- Guardian metadata used for:
  - Validating bracket set uniqueness (one per symbol/side).
  - TTL protection (check `created_ts` field).
  - Conflict resolution (DR/restart: choose bracket set with latest timestamp).

**Caller Responsibility** (FSM):
- After executing BracketPlan actions, FSM must call `OrderGuardian.register_bracket_set()` to update metadata.
- After CANCEL actions, FSM may call `OrderGuardian.clear_bracket_set_for_position()` if position FLAT.

---

### 7.3. Integration with AggOcoWatchdogService

**Purpose**: Optionally use watchdog recommendations as hints (NOT source of truth).

**Interface**:
```python
# BracketService MAY query watchdog:
watchdog_recs = self._watchdog.analyze(
    open_orders=orders,
    positions=positions,
    bracket_metas=guardian_metas,
)
# Returns List[WatchdogRecommendation]
```

**Contract**:
- Watchdog recommendations are **advisory only** (not trusted as ground truth).
- BracketService performs its own invariant checks (does not blindly trust watchdog).
- Watchdog hints may be used to prioritize evaluation order (critical violations first).

**Note**: In practice, BracketService likely does NOT need watchdog integration (redundant). Watchdog remains for background monitoring only.

---

### 7.4. Integration with ExecPosRuntimeV2 / ManageFlowFSM

**Future Usage** (out of scope for this contract, but documented for clarity):

#### After Scale-In Fill:
```python
# ManageFlowFSM detects scale-in fill
position_view = runtime.get_position_snapshot(symbol)
orders = adapter.get_open_orders(symbol)

# Build state
state = bracket_service.build_state(
    positions=[position_view],
    orders=orders,
    guardian_meta=guardian.get_active_bracket_set(symbol, side),
    symbol=symbol,
    side=side,
    rid=rid,
)[symbol, side]

# Evaluate
plan = bracket_service.evaluate(state, cfg, rid=rid)

# Execute actions
for action in plan.actions:
    if action.action_type == "CANCEL":
        await adapter.cancel_order(action.order_id)
    elif action.action_type == "PLACE_SL":
        result = await adapter.place_order(
            symbol=symbol,
            side="SELL" if side == "LONG" else "BUY",
            order_type="STOP_MARKET",
            stop_price=action.price,
            qty=action.qty,
            reduce_only=True,
        )
        sl_order_id = result["orderId"]

# Update guardian
guardian.register_bracket_set(
    bracket_set_id=f"RID_{rid}",
    symbol=symbol,
    side=side,
    sl_order_id=sl_order_id,
    tp_order_id=tp_order_id,
    created_ts=time.time(),
)
```

#### During DR/Restart:
```python
# ExecPosFSM startup: check all positions
positions = adapter.get_open_positions()
orders = adapter.get_open_orders()

all_plans = bracket_service.evaluate_all(
    positions=positions,
    orders=orders,
    cfg=cfg,
    rid="DR_STARTUP",
)

critical_plans = [p for p in all_plans if p.is_critical]
for plan in critical_plans:
    logger.alert(f"DR violation: {plan.symbol} {plan.side} - {plan.why}")
    # Execute plan actions (cleanup orphans, place missing SL, etc.)
```

---

## 8. Explainability & RID Propagation

### 8.1. Why Field Format

**Pattern**: `reason|detail` (≤80 chars total)

**Examples**:
```python
# Missing SL
"missing_sl|pos>0_sl_count=0"
"missing_sl|pos_qty=1.5_no_sl_orders"

# Orphan SL
"orphan_sl|qty≈0_active_sl_ord=123"
"orphan_sl|flat_pos_sl_not_cancelled"

# Too many SL
"too_many_sl|expected=1_actual=3"
"too_many_sl|duplicate_sl_orders"

# Recalc scale-in
"recalc_scale_in|avg_entry_24.1→25.3"
"recalc_scale_in|qty_0.5→1.0_tp_sl_update"

# Recalc partial close
"recalc_partial_close|qty_1.0→0.5"
"recalc_partial_close|tp_partial_fill_recalc"

# Stale levels
"stale_levels|sl_24.5→24.8_tp_ok"
"stale_levels|tp_26.0→26.5_sl_ok"

# Duplicate set
"duplicate_set|found=2_kept_latest"
"duplicate_set|dr_conflict_resolved"

# Ambiguous state
"ambiguous_state|multiple_sl_sources"
"ambiguous_state|guardian_meta_mismatch"
```

**Structure**:
- `reason`: Short reason code (snake_case).
- `detail`: Specific context (qty, price, order_id, etc.).
- Separator: `|` (vertical bar).

---

### 8.2. RID Propagation

**Pattern**: Pass `rid` parameter through all BracketService methods.

```python
# FSM initiates with RID
rid = "REQ_SCALE_IN_BTC_001"

# RID passed to build_state
state = bracket_service.build_state(
    positions=positions,
    orders=orders,
    rid=rid,
)[symbol, side]

# RID passed to evaluate
plan = bracket_service.evaluate(state, cfg, rid=rid)

# RID present in plan
assert plan.rid == rid

# RID present in all actions
for action in plan.actions:
    assert action.rid == rid
```

**Logging**:
```python
# BracketService logs (external to core logic)
logger.info(
    "BracketPlan produced",
    extra={
        "rid": plan.rid,
        "symbol": plan.symbol,
        "side": plan.side,
        "severity": plan.severity,
        "action_count": len(plan.actions),
        "why": plan.why,
    },
)
```

**Adapter Calls** (by FSM):
```python
# FSM propagates RID to adapter
result = await adapter.cancel_order(
    order_id=action.order_id,
    rid=action.rid,  # RID propagates to adapter logs
)
```

---

### 8.3. Parent Why Chain

**Pattern**: `parent_why` field in `BracketAction` links to triggering event.

```python
# Example: Scale-in fill event triggers recalc
fill_event_why = "scale_in_fill|qty_0.5→1.0"

# BracketService produces actions with parent_why
action = BracketAction(
    action_type="PLACE_SL",
    price=Decimal("24.8"),
    qty=Decimal("1.0"),
    reason_code="RECALC_SCALE_IN",
    why="recalc_scale_in|avg_entry_24.1→25.3",
    rid=rid,
    parent_why=fill_event_why,  # Links to fill event
)
```

**Usage**: Audit trail links position event → bracket decision → order action.

---

## 9. Testing Strategy

**Unit Tests** (future: `test_bracket_service.py`):
- Test `build_state()`:
  - Happy path: position + orders → valid BracketState.
  - Edge case: FLAT position with no orders → empty BracketState.
  - Edge case: Position with no guardian metadata → partial state.
- Test `evaluate()`:
  - Happy path: Valid state → plan with severity=INFO, no actions.
  - Missing SL: Open position, no SL → plan with PLACE_SL action.
  - Orphan SL: FLAT position, active SL → plan with CANCEL action.
  - Too many SL: 3 SL orders → plan with 2 CANCEL actions.
  - Stale levels: avg_entry changed → plan with CANCEL + PLACE actions.
  - TTL protection: New SL skipped in cleanup.
- Test `evaluate_all()`:
  - Batch processing: 3 positions → 3 plans.
  - Mixed severities: INFO + WARN + ALERT plans.

**Integration Tests** (future: `test_bracket_service_integration.py`):
- Test with live adapter (testnet):
  - Open position → evaluate → execute plan → verify brackets placed.
  - Scale-in → evaluate → execute recalc plan → verify new brackets.
  - Close position → evaluate → execute cleanup plan → verify orphans removed.

**Contract Compliance Tests** (future: `test_bracket_service_contract.py`):
- Verify determinism: Same inputs → same plan.
- Verify idempotency: Re-evaluate without execution → same plan.
- Verify no side effects: evaluate() does not call adapter.
- Verify why field format: All actions have `reason|detail` pattern.

---

## 10. Future Evolution

### ✅ Phase 2 COMPLETED (EP-PORT-BRACKETS-S1-PH2) — 2025-01-19

**Implementation**: `shadow_execpos/bracket_service.py` (757 lines)
**Tests**: `tests/domains/execution_position/shadow_execpos/test_bracket_service.py` (833 lines)

**Completed Work**:
- ✅ All 7 data models implemented with immutable dataclasses + validation
- ✅ BracketRulesConfig with defaults per risk strategy
- ✅ BracketService class: `build_state()`, `evaluate()`, `evaluate_all()`
- ✅ 17 comprehensive unit tests (100% pass rate)
- ✅ Integration with `bracket_aggregator.py` for TP/SL calculation
- ✅ Pure computation logic (no side effects, deterministic)

**Test Coverage**:
```
test_build_state_flat_no_orders
test_build_state_single_long_position_with_sl_tp
test_build_state_flat_position_with_orphan_sl
test_evaluate_missing_sl_alert
test_evaluate_missing_sl_allowed (permissive mode)
test_evaluate_orphan_sl_warn
test_evaluate_orphan_sl_and_tp_warn
test_evaluate_too_many_sl_warn
test_evaluate_stale_sl_level_warn
test_evaluate_stale_sl_and_tp_levels_warn
test_evaluate_all_multiple_positions
test_evaluate_all_mixed_severities
test_position_view_invariants
test_order_view_invariants
test_bracket_action_why_truncation
test_evaluate_disabled_config
test_evaluate_invalid_state_raises_error
```

**Run Tests**:
```bash
pytest tests/domains/execution_position/shadow_execpos/test_bracket_service.py -q
```

---

### 🔄 Phase 3 (future task)

**Scope**: Runtime Integration
- Wire BracketService into ManageFlowFSM (replace manual recalc logic).
- Update ExecPosRuntimeV2 to call `evaluate()` during DR/restart.
- Add WHY-chain propagation to logs (RID → JOURNAL).
- Implement TTL protection for new brackets.

---

### 🔮 Phase 4 (future task)

**Scope**: Advanced Features
- Persistent state: Replace InMemoryStore with Redis for bracket metadata.
- Cross-symbol coordination: Prevent portfolio-level over-leverage.
- Multi-leg brackets: Support trailing stops, conditional TP levels.
- Canary rollout: Shadow evaluation before live execution.

---

## 11. References

**Source Documents**:
- `docs/EXEC_POS_BRACKETS_ANALYSIS.md` — Analysis of bracket invariants, gaps, historical behaviors.
- `docs/EXECUTION_POSITION_ORDER_GUARDIAN_CONTRACT.md` — OrderGuardian frozen contract v1.0.
- `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py` — Pure aggregated TP/SL computation.
- `apps/reference/domains/execution_position/shadow_execpos/watchdog.py` — AggOcoWatchdogService detect-only.

**Related Tasks**:
- `EP-LEGACY-PURGE-S1` — Completed: removed all legacy ExecPosFSM references.
- `EP-PORT-BRACKETS-S1-PH0` — Completed: analysis document.
- `EP-PORT-BRACKETS-S1-PH1` — This document: contract design.
- `EP-PORT-BRACKETS-S1-PH2` — Next: implementation.

**Maintainer**: Execution Position Domain
**Review**: Architecture WG

---

**End of BracketService Contract v1.0 — Ready for Implementation (PHASE 2)**
