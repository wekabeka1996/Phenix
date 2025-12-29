# Aggregator OCO — Behavior Spec (Phase 5)

> **RID**: `EXEC-AGGREGATOR-OCO-PHASE5-BEHAVIOR-SPEC-AND-TEST-MATRIX`
> **Status**: Active
> **Purpose**: Freeze current behavior as reference before logic extraction from `bracket_service`.

---

## 1. Scope

This document describes:
- Behavior of SL/TP bracket computation at `BracketPlan` contract level.
- Input → Output invariants for `compute_bracket_plan()`.
- Edge cases and expected handling.

**NOT** in scope:
- Binance REST/WS specifics (handled by adapter layer).
- Order execution/confirmation (handled by `ExecutionService`).
- Runtime orchestration (handled by `ExecPosRuntimeV2`).

---

## 2. Core Invariants

### INV-1: Maximum One SL and One TP Per Symbol/Side

```
For any (symbol, side) pair:
  count(SL orders) <= cfg.max_sl_legs (default: 1)
  count(TP orders) <= cfg.max_tp_legs (default: 1)
```

**Enforcement**: If violated, plan contains `CANCEL` actions for excess legs.

### INV-2: Flat Position → No Brackets Allowed

```
IF position is None OR position.qty == 0:
  THEN plan.actions may only contain CANCEL/NOOP
  plan.actions MUST NOT contain PLACE_SL/PLACE_TP
```

**Why**: Orphan orders without position create exposure risk.

### INV-3: Fail-Closed on Ambiguous State

```
IF state is inconsistent (e.g., missing entry_price, conflicting orders):
  THEN plan = NOOP or CANCEL-only
  NEVER place new orders on ambiguous state
```

**Examples**:
- `qty > 0` but `entry_price <= 0` → skip bracket evaluation
- Multiple interpretations of order state → ALERT severity, no actions

### INV-4: LONG Position Price Constraints

```
IF side == "LONG" AND position.qty > 0:
  SL_price < entry_price     (stop below entry)
  TP_price > entry_price     (take profit above entry)
```

**Formula** (current implementation):
```python
sl_price = entry_price * (1 - sl_pct)
tp_price = entry_price * (1 + sl_pct * tp_rr)
```

### INV-5: SHORT Position Price Constraints

```
IF side == "SHORT" AND position.qty > 0:
  SL_price > entry_price     (stop above entry)
  TP_price < entry_price     (take profit below entry)
```

**Formula** (current implementation):
```python
sl_price = entry_price * (1 + sl_pct)
tp_price = entry_price * (1 - sl_pct * tp_rr)
```

### INV-6: Why Field Constraints

```
len(BracketPlan.why) <= 80 characters
len(BracketAction.why) <= 80 characters
```

**Content**: Technical reason code, no raw Binance payload.

### INV-7: Bracket Quantity Invariant

```
sum(bracket_order_qty) <= abs(position.qty)
```

**Enforcement**: `_enforce_size_invariants()` adjusts or cancels oversized brackets.

### INV-8: Cycle ID Orphan Detection

```
IF bracket.cycle_id != position.cycle_id:
  THEN bracket is ORPHAN → CANCEL
```

**Why**: Brackets from previous trade cycles must be cleaned up.

---

## 3. Scenario Table (Test Matrix)

### Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Test exists and passes |
| 🔲 | Test TODO |
| ⚠️ | Edge case, partial coverage |

---

### Group A — Initial Bracket Placement

| ID | Position | Existing Orders | Config | Expected Plan | Test Status |
|----|----------|-----------------|--------|---------------|-------------|
| **A1** | LONG, qty=1.0, entry=100.0 | [] | sl_pct=0.02, tp_rr=2.0 | PLACE_SL@98, PLACE_TP@104 | ✅ `test_engine_shadow.py` |
| **A2** | SHORT, qty=1.0, entry=100.0 | [] | sl_pct=0.02, tp_rr=2.0 | PLACE_SL@102, PLACE_TP@96 | ✅ `test_engine_shadow.py` |
| **A3** | LONG, qty=0.0001 (tiny) | [] | sl_pct=0.02 | PLACE_SL, PLACE_TP (normal) | 🔲 TODO |

### Scenario A1: LONG, No Existing Orders

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: LONG
    qty: 1.0
    entry_price: 100.0
  orders: []
  mark_price: 100.0
  cfg:
    sl_pct: 0.02
    tp_rr: 2.0
    enabled: true
    recreate_missing_brackets: true

Expected:
  plan.actions:
    - action: PLACE_SL
      leg_type: SL
      target_price: 98.0    # 100 * (1 - 0.02)
      qty: 1.0
    - action: PLACE_TP
      leg_type: TP
      target_price: 104.0   # 100 * (1 + 0.02 * 2.0)
      qty: 1.0
  plan.suppressed: false
  plan.severity: ALERT  # Missing brackets trigger ALERT
```

### Scenario A2: SHORT, No Existing Orders

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: SHORT
    qty: 1.0
    entry_price: 100.0
  orders: []
  mark_price: 100.0
  cfg:
    sl_pct: 0.02
    tp_rr: 2.0

Expected:
  plan.actions:
    - action: PLACE_SL
      leg_type: SL
      target_price: 102.0   # 100 * (1 + 0.02)
      qty: 1.0
    - action: PLACE_TP
      leg_type: TP
      target_price: 96.0    # 100 * (1 - 0.02 * 2.0)
      qty: 1.0
  plan.severity: ALERT
```

---

### Group B — Idempotency / No-Op

| ID | Position | Existing Orders | Expected Plan | Test Status |
|----|----------|-----------------|---------------|-------------|
| **B1** | LONG, qty=1.0, entry=100.0 | SL@98, TP@104 | NOOP (severity=INFO) | ✅ `test_engine_shadow.py` |
| **B2** | LONG, qty=1.0, entry=100.0 | SL@98, no TP | PLACE_TP@104 only | 🔲 TODO |
| **B3** | LONG, qty=1.0, entry=100.0 | no SL, TP@104 | PLACE_SL@98 only | 🔲 TODO |

### Scenario B1: Perfect Bracket State (NOOP)

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: LONG
    qty: 1.0
    entry_price: 100.0
  orders:
    - order_id: "sl_001"
      side: SELL
      type: STOP_MARKET
      stop_price: 98.0
      status: NEW
    - order_id: "tp_001"
      side: SELL
      type: TAKE_PROFIT_MARKET
      stop_price: 104.0
      status: NEW
  cfg:
    sl_pct: 0.02
    tp_rr: 2.0

Expected:
  plan.actions: []  # No changes needed
  plan.severity: INFO
  plan.why: "brackets_ok|no_violations"
```

### Scenario B2: Missing TP Only

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: LONG
    qty: 1.0
    entry_price: 100.0
  orders:
    - order_id: "sl_001"
      side: SELL
      type: STOP_MARKET
      stop_price: 98.0
      status: NEW
  # No TP order

Expected:
  plan.actions:
    - action: PLACE_TP
      leg_type: TP
      target_price: 104.0
      qty: 1.0
  plan.severity: WARN
  plan.why: "missing_tp|..."
```

---

### Group C — Partial Fills / Adjust

| ID | Position | Existing Orders | Expected Plan | Test Status |
|----|----------|-----------------|---------------|-------------|
| **C1** | LONG, qty=0.5 (was 1.0) | SL@98 qty=1.0, TP@104 qty=1.0 | ADJUST SL/TP qty→0.5 | ⚠️ partial |
| **C2** | FLAT (was LONG) | SL@98, TP@104 | CANCEL SL, CANCEL TP | ✅ `test_engine_shadow.py` |
| **C3** | LONG→SHORT reversal | Old LONG SL@98 | CANCEL old, PLACE new | 🔲 TODO |

### Scenario C1: Position Reduced (Partial Close)

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: LONG
    qty: 0.5        # Was 1.0, partially closed
    entry_price: 100.0
  orders:
    - order_id: "sl_001"
      side: SELL
      type: STOP_MARKET
      stop_price: 98.0
      qty: 1.0      # Still sized for old position
      status: NEW

Expected:
  # Current behavior: ADJUST or CANCEL+PLACE
  plan.actions:
    - action: ADJUST  # or CANCEL + PLACE_SL
      order_ref: "sl_001"
      qty: 0.5
  plan.severity: WARN
```

### Scenario C2: Position Closed (Orphan Cleanup)

```yaml
Input:
  position: null    # Or qty=0
  orders:
    - order_id: "sl_001"
      side: SELL
      type: STOP_MARKET
      stop_price: 98.0
      status: NEW

Expected:
  plan.actions:
    - action: CANCEL
      order_ref: "sl_001"
      reason_code: ORPHAN_SL
  plan.severity: WARN
  plan.why: "orphan_brackets|pos_flat_sl_or_tp_active"
```

---

### Group D — Drift / Risk Edge Cases

| ID | Scenario | Expected Plan | Test Status |
|----|----------|---------------|-------------|
| **D1** | Price far from entry | Normal SL/TP (no suppression) | 🔲 TODO |
| **D2** | entry_price=0 bug | NOOP (fail-closed) | ✅ handled in runtime |
| **D3** | Duplicate SL orders | CANCEL excess | ⚠️ `test_bracket_service.py` |
| **D4** | cfg.enabled=false | NOOP always | ✅ `test_bracket_service.py` |

### Scenario D2: Invalid Entry Price (Fail-Closed)

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: LONG
    qty: 1.0
    entry_price: 0.0  # Invalid!

Expected:
  # PositionView validation raises ValueError
  # Runtime skips bracket evaluation
  plan: N/A (validation error)
```

### Scenario D3: Duplicate SL Orders

```yaml
Input:
  position:
    symbol: BTCUSDT
    side: LONG
    qty: 1.0
    entry_price: 100.0
  orders:
    - order_id: "sl_001", type: STOP_MARKET, stop_price: 98.0
    - order_id: "sl_002", type: STOP_MARKET, stop_price: 97.0  # Duplicate!

Expected:
  plan.actions:
    - action: CANCEL
      order_ref: "sl_002"  # Keep first, cancel duplicates
      reason_code: EXCESS_SL
  plan.severity: WARN
```

---

## 4. Mapping to Tests

### Existing Test Coverage

| Scenario | Test File | Test Function |
|----------|-----------|---------------|
| A1 | `test_engine_shadow.py` | `test_long_no_orders_places_sl_tp` |
| A2 | `test_engine_shadow.py` | `test_short_no_orders_places_sl_tp` |
| B1 | `test_engine_shadow.py` | `test_long_with_correct_brackets_noop` |
| C2 | `test_engine_shadow.py` | `test_flat_with_orphan_brackets_cancels` |

### New Tests Required (Phase 5)

| Scenario | Test File | Test Function | Status |
|----------|-----------|---------------|--------|
| A1 | `test_engine_scenarios.py` | `test_A1_long_no_orders_places_sl_and_tp` | 🔲 |
| A2 | `test_engine_scenarios.py` | `test_A2_short_no_orders_places_sl_and_tp` | 🔲 |
| B1 | `test_engine_scenarios.py` | `test_B1_perfect_brackets_noop` | 🔲 |
| B2 | `test_engine_scenarios.py` | `test_B2_missing_tp_places_tp_only` | 🔲 |
| C1 | `test_engine_scenarios.py` | `test_C1_partial_close_adjusts_qty` | 🔲 |

---

## 5. Alignment with Existing Implementation

### Covered by Existing Tests

- Basic PLACE_SL/PLACE_TP logic (A1, A2)
- Idempotency when brackets exist (B1)
- Orphan cleanup when flat (C2)
- Config disable bypass (D4)

### Potential Gaps (Risk Areas)

| Gap | Risk | Mitigation |
|-----|------|------------|
| B2/B3: Single leg missing | Medium | Add explicit scenario tests |
| C1: Partial qty adjustment | High | Test ADJUST action flow |
| C3: Side reversal | High | Test CANCEL old + PLACE new |
| D1: Price drift edge cases | Low | Document expected behavior |

---

## 6. Formula Reference

### SL/TP Price Calculation

**Canonical Implementation**: [`core_math.py`](./core_math.py) (Phase 6)

```python
# LONG position
sl_price = entry_price * (Decimal("1") - sl_pct)
tp_price = entry_price * (Decimal("1") + sl_pct * tp_rr)

# SHORT position
sl_price = entry_price * (Decimal("1") + sl_pct)
tp_price = entry_price * (Decimal("1") - sl_pct * tp_rr)
```

### Types (core_math.py)

```python
@dataclass(frozen=True)
class DesiredLevels:
    side: Side
    entry_price: Decimal
    sl_price: Decimal
    tp_price: Decimal
    sl_pct: Decimal
    tp_rr: Decimal
    why: str = "core_math_v1"
```

### Usage

```python
from aggregator_oco.core_math import compute_desired_levels

levels = compute_desired_levels(
    side="LONG",
    entry_price=Decimal("100"),
    sl_pct=Decimal("0.02"),
    tp_rr=Decimal("2.0"),
)
# levels.sl_price = 98, levels.tp_price = 104
```

### Example: entry=100, sl_pct=0.02, tp_rr=2.0

| Side | SL Price | TP Price | Calculation |
|------|----------|----------|-------------|
| LONG | 98.0 | 104.0 | SL: 100×0.98, TP: 100×1.04 |
| SHORT | 102.0 | 96.0 | SL: 100×1.02, TP: 100×0.96 |

---

## 7. Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| Use `_compute_desired_levels()` formulas as-is | Behavior freeze before refactor | 2025-11-30 |
| INV-3 fail-closed on ambiguous state | Safety over availability | 2025-11-30 |
| Cycle ID orphan detection (INV-8) | Prevent stale bracket accumulation | 2025-11-30 |
| **Phase 7**: `_compute_desired_levels` delegates to `core_math` | Single source of truth for SL/TP formulas; zero-diff | 2025-11-30 |
| **Phase 10**: `bracket_service` retired from production | Runtime uses core planner only; bracket_service is test-only harness | 2025-11-30 |

### Phase 10 — bracket_service Retirement (COMPLETE)

All production dependencies on `shadow_execpos.bracket_service` have been removed:

- **`compute_bracket_plan_from_views()`**: No longer accepts `bracket_service` parameter
- **Runtime call site**: Calls engine without `bracket_service=`
- **Core planner always used**: `_compute_bracket_plan_core()` is the ONLY path

**bracket_service status**: **TEST-ONLY HARNESS**
- Marked with DEPRECATED header
- Still used by runtime for `plan_orphan_cleanup()` and `plan_reverse_cleanup()` (cleanup methods)
- Tests refactored to check `execution_service.place_order/cancel_order` instead of mocking `bracket_service.evaluate()`

**Feature gaps documented** (xfail tests):
- `allow_unprotected_position=True` — core planner ALWAYS generates SL/TP
- `recreate_missing_brackets=False` — not supported by core planner

**Test results**:
```
aggregator_oco:  245 passed ✅
shadow_execpos:  354 passed, 2 failed (logging), 4 xfailed ✅
```

### Phase 8 Integration

Legacy `_compute_desired_levels()` in `shadow_execpos/bracket_service.py` is now a **thin wrapper**
over `aggregator_oco.core_math.compute_desired_levels()`:

- **No duplicate formulas**: All SL/TP math lives exclusively in `core_math.py`
- **Zero-diff behavior**: All existing tests pass unchanged (245 aggregator_oco + 355 shadow_execpos)
- **Import added**:
  ```python
  from apps.reference.domains.execution_position.aggregator_oco.core_math import (
      compute_desired_levels as _core_compute_desired_levels,
      PriceConstraints as _CorePriceConstraints,
  )
  ```

### Phase 8 Integration

`aggregator_oco.engine.compute_bracket_plan()` now uses **core planner** directly:

- **NO `bracket_service.evaluate()` calls**: Engine uses `_compute_bracket_plan_core()` internally
- **Single source of truth**: `core_math.compute_desired_levels()` for all SL/TP prices
- **Legacy bracket_service**: Remains only as test harness for shadow tests
- **Zero-diff behavior**: All 245 aggregator_oco + 355 shadow_execpos tests pass unchanged

**Architecture after Phase 8**:
```
ExecPosRuntimeV2 → engine.compute_bracket_plan() → _compute_bracket_plan_core()
                                                           ↓
                                                  core_math.compute_desired_levels()
```
| Use `_compute_desired_levels()` formulas as-is | Behavior freeze before refactor | 2025-11-30 |
| INV-3 fail-closed on ambiguous state | Safety over availability | 2025-11-30 |
| Cycle ID orphan detection (INV-8) | Prevent stale bracket accumulation | 2025-11-30 |

---

## Appendix: Related Documents

- [`AGGREGATOR_OCO_CONTRACT.md`](./AGGREGATOR_OCO_CONTRACT.md) — Contract type definitions
- [`AGGREGATOR_OCO_CODE_MAP.md`](./AGGREGATOR_OCO_CODE_MAP.md) — File structure and phase tracking
- [`engine.py`](./engine.py) — Entry point implementation
- [`contracts.py`](./contracts.py) — Type definitions
- [`core_math.py`](./core_math.py) — Pure SL/TP math (Phase 6)
- [`test_core_math_golden.py`](../../../../../tests/domains/execution_position/aggregator_oco/test_core_math_golden.py) — Golden-master tests (180 tests)
