# Aggregator OCO — Contract (Phase 1)

> **Version**: 1.0
> **Status**: Draft
> **Created**: 2025-11-30
> **RID**: `EXEC-AGGREGATOR-OCO-PHASE1-CONTRACT-AND-TYPES`

---

## 1. Purpose & Scope

### 1.1 What Aggregator OCO Does

The `aggregator_oco` subdomain is responsible for:

1. **Bracket State Assessment** — Given a position snapshot and current orders, determine the current bracket state (SL/TP present, missing, or drifted).

2. **Target Price Calculation** — Compute SL and TP prices based on entry price, side, `sl_pct`, and `tp_rr` ratio.

3. **Action Plan Generation** — Produce a `BracketPlan` containing actions (`PLACE_SL`, `PLACE_TP`, `CANCEL`, `ADJUST`, `NOOP`) that bring the bracket state into alignment with the desired state.

4. **XAI Traceability** — Every action includes a `why` field (≤80 chars) explaining the decision.

### 1.2 What Aggregator OCO Does NOT Do

| Out of Scope | Responsibility |
|--------------|----------------|
| Execute orders on Binance | `ExecutorPoolV2` / `binance_adapter.py` |
| Open/close positions | `ExecPosRuntimeV2` |
| Manage order lifecycle | `OrderIndex` |
| Network I/O | Adapter layer |
| Throttling decisions | Runtime layer |

**Key principle**: Aggregator OCO is a **pure computation layer**. It receives data, computes a plan, returns the plan. No side effects.

---

## 2. Inputs

### 2.1 AggregatorInput (Symbol Snapshot)

A point-in-time snapshot of a symbol's state:

```python
@dataclass
class AggregatorInput:
    symbol: str                           # e.g., "BTCUSDT"
    position: Optional[PositionSnapshot]  # None if flat
    orders: List[OrderSnapshot]           # Current bracket orders
    mark_price: Optional[Decimal]         # Current mark price (optional)
    ts: float                             # Snapshot timestamp
```

### 2.2 PositionSnapshot

```python
@dataclass
class PositionSnapshot:
    symbol: str
    side: Side                  # "LONG" | "SHORT"
    qty: Decimal                # Position quantity (always positive)
    entry_price: Decimal        # Average entry price
    unrealized_pnl: Optional[Decimal]  # Current P&L (optional)
```

### 2.3 OrderSnapshot

```python
@dataclass
class OrderSnapshot:
    symbol: str
    order_id: Optional[str]          # Exchange order ID
    client_order_id: Optional[str]   # Client-side order ID
    side: OrderSide                  # "BUY" | "SELL"
    type: OrderType                  # "STOP_MARKET" | "TAKE_PROFIT_MARKET" | ...
    stop_price: Optional[Decimal]    # Trigger price for stop orders
    status: OrderStatus              # "NEW" | "WORKING" | "FILLED" | ...
```

### 2.4 Config Slice

Configuration parameters passed to the evaluator:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sl_pct` | `Decimal` | 0.02 | Stop loss percentage (2% = 0.02) |
| `tp_rr` | `Decimal` | 2.0 | Take profit risk:reward ratio |
| `trailing_enabled` | `bool` | False | Enable trailing stop |
| `trailing_step_pct` | `Decimal` | 0.005 | Trailing step size |
| `tolerance_pct` | `Decimal` | 0.001 | Price drift tolerance (0.1%) |

---

## 3. Outputs

### 3.1 BracketPlan

The result of evaluating an `AggregatorInput`:

```python
@dataclass
class BracketPlan:
    symbol: str                    # Symbol this plan is for
    actions: List[BracketAction]   # Ordered list of actions to execute
    suppressed: bool               # True if plan should be skipped
    why: str                       # XAI: reason for plan (≤80 chars)
```

**Semantics**:
- `actions` are ordered: execute sequentially
- If `suppressed=True`, skip execution but log the `why`
- Empty `actions` list = NOOP (state is already correct)

### 3.2 BracketAction

A single action within a plan:

```python
@dataclass
class BracketAction:
    action: Literal["PLACE_SL", "PLACE_TP", "CANCEL", "ADJUST", "NOOP"]
    leg_type: Optional[BracketLegType]  # "SL" | "TP" | None
    target_price: Optional[Decimal]     # Price for PLACE_*/ADJUST
    order_ref: Optional[str]            # Order ID for CANCEL/ADJUST
    why: str                            # XAI: reason for action (≤80 chars)
```

**Action Semantics**:

| Action | Description | Required Fields |
|--------|-------------|-----------------|
| `PLACE_SL` | Place new stop loss order | `leg_type="SL"`, `target_price` |
| `PLACE_TP` | Place new take profit order | `leg_type="TP"`, `target_price` |
| `CANCEL` | Cancel existing bracket order | `order_ref` |
| `ADJUST` | Modify existing bracket price | `order_ref`, `target_price` |
| `NOOP` | No action needed | (none) |

---

## 4. Invariants

### 4.1 Bracket Cardinality

- **At most ONE active SL per symbol**
- **At most ONE active TP per symbol**
- If multiple SL/TP orders exist → plan should contain `CANCEL` for extras

### 4.2 Flat Position Invariant

If `position is None` or `qty == 0`:
- Only valid actions: `CANCEL`, `NOOP`
- Never `PLACE_SL`, `PLACE_TP`, `ADJUST`

### 4.3 Fail-Closed Principle

When state is ambiguous or invalid:
- Prefer `NOOP` or `CANCEL` over `PLACE_*`
- Never place new brackets in uncertain state
- Always include `why` explaining the decision

### 4.4 XAI Coverage

- Every `BracketAction.why` must be non-empty
- Every `BracketPlan.why` must be non-empty
- Format: snake_case identifier (e.g., `"missing_sl"`, `"price_drift_0.5pct"`)

### 4.5 Price Validity

- `target_price` must be > 0 for `PLACE_*` and `ADJUST`
- SL price must be on the "loss" side of entry:
  - LONG: `sl_price < entry_price`
  - SHORT: `sl_price > entry_price`
- TP price must be on the "profit" side of entry:
  - LONG: `tp_price > entry_price`
  - SHORT: `tp_price < entry_price`

---

## 5. Relation to Existing Code

### 5.1 Current Implementation

The logic described in this contract is **currently implemented** in:

| File | Role |
|------|------|
| `bracket_service.py` | `BracketService.build_state()`, `.evaluate()` |
| `tp_sl_math.py` | `compute_tpsl_levels()` — core SL/TP math |
| `bracket_aggregator.py` | `compute_aggregated_brackets()` — price wrapper |

### 5.2 Phase 1 Status

**Phase 1 = Contract Only**

- This document defines the target interface
- `contracts.py` provides Python types matching this contract
- Implementation remains in `bracket_service.py`
- No changes to runtime behavior

### 5.3 Future Phases

| Phase | Scope |
|-------|-------|
| Phase 2 | Migrate `bracket_service.py` internals to use contract types |
| Phase 3 | Extract evaluator function to `aggregator_oco/` |
| Phase 4 | Runtime calls new subdomain instead of old service |

---

## 6. Examples

### 6.1 New Position Needs Brackets

**Input**:
```python
AggregatorInput(
    symbol="BTCUSDT",
    position=PositionSnapshot(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("30000"),
    ),
    orders=[],  # No brackets yet
)
```

**Output**:
```python
BracketPlan(
    symbol="BTCUSDT",
    actions=[
        BracketAction(action="PLACE_SL", leg_type="SL",
                      target_price=Decimal("29400"), why="missing_sl"),
        BracketAction(action="PLACE_TP", leg_type="TP",
                      target_price=Decimal("31200"), why="missing_tp"),
    ],
    suppressed=False,
    why="new_position_needs_brackets",
)
```

### 6.2 Position Closed, Orphan Brackets

**Input**:
```python
AggregatorInput(
    symbol="BTCUSDT",
    position=None,  # Flat
    orders=[
        OrderSnapshot(order_id="sl-123", type="STOP_MARKET", ...),
        OrderSnapshot(order_id="tp-456", type="TAKE_PROFIT_MARKET", ...),
    ],
)
```

**Output**:
```python
BracketPlan(
    symbol="BTCUSDT",
    actions=[
        BracketAction(action="CANCEL", order_ref="sl-123", why="orphan_sl_flat"),
        BracketAction(action="CANCEL", order_ref="tp-456", why="orphan_tp_flat"),
    ],
    suppressed=False,
    why="cleanup_orphan_brackets",
)
```

### 6.3 Brackets Correct, No Action

**Input**:
```python
AggregatorInput(
    symbol="BTCUSDT",
    position=PositionSnapshot(..., entry_price=Decimal("30000")),
    orders=[
        OrderSnapshot(type="STOP_MARKET", stop_price=Decimal("29400")),
        OrderSnapshot(type="TAKE_PROFIT_MARKET", stop_price=Decimal("31200")),
    ],
)
```

**Output**:
```python
BracketPlan(
    symbol="BTCUSDT",
    actions=[],  # Empty = NOOP
    suppressed=False,
    why="brackets_correct",
)
```

---

## 7. Type Definitions Reference

Full type definitions are in:

```
apps/reference/domains/execution_position/aggregator_oco/contracts.py
```

**Literal Types**:
- `Side = Literal["LONG", "SHORT"]`
- `OrderSide = Literal["BUY", "SELL"]`
- `OrderType = Literal["STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT", "MARKET"]`
- `OrderStatus = Literal["NEW", "WORKING", "FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED"]`
- `BracketLegType = Literal["SL", "TP"]`
- `ActionType = Literal["PLACE_SL", "PLACE_TP", "CANCEL", "ADJUST", "NOOP"]`

---

## 8. Engine Entry Point (Phase 3)

### 8.1 Primary Function

```python
from aggregator_oco.engine import compute_bracket_plan

plan = compute_bracket_plan(agg_input, cfg, rid="optional-trace-id")
```

**Signature**:
```python
def compute_bracket_plan(
    agg_input: AggregatorInput,
    cfg: BracketConfig,
    *,
    rid: Optional[str] = None,
) -> BracketPlan
```

### 8.2 Current Implementation (Phase 3)

- Adapts `AggregatorInput` to legacy `BracketState` format
- Adapts `BracketConfig` to legacy `BracketRulesConfig` format
- Delegates computation to `shadow_execpos/bracket_service.py`
- Returns `BracketPlan` (contract type)

**Key property**: Zero-diff behavior — produces same results as direct `bracket_service.evaluate()` calls.

### 8.3 Future Plans (Phase 4+)

- Gradually migrate business logic from `bracket_service.py` to `engine.py`
- Eventually `bracket_service.evaluate()` will be deprecated
- Runtime will call `compute_bracket_plan()` directly

### 8.4 Files

| File | Purpose |
|------|---------|
| `engine.py` | Contract entrypoint implementation |
| `test_engine_shadow.py` | Shadow tests verifying engine vs bracket_service parity |

---

## 9. Behavior Specification (Phase 5)

### 9.1 Reference Document

See [`AGGREGATOR_OCO_BEHAVIOR.md`](./AGGREGATOR_OCO_BEHAVIOR.md) for:
- Core invariants (INV-1 through INV-8)
- Scenario table with test matrix (A1..D4)
- Formula reference for SL/TP calculation
- Mapping to test coverage

### 9.2 Scenario Tests

| File | Coverage |
|------|----------|
| `test_engine_scenarios.py` | 18 tests covering A1, A2, B1, B2, B3, C2, D3 + invariants + formula verification |

### 9.3 Purpose

The behavior spec freezes current system behavior as a reference before:
- Extracting math logic from `bracket_service.py` to pure `aggregator_oco.core`
- Refactoring internal algorithms
- Adding new features

Any deviation from the documented behavior must be intentional and documented.

---

*End of Contract v1.2*
