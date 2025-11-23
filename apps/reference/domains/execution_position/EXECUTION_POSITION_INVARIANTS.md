# Execution Position Invariants

Safety invariants for ExecPosRuntimeV2 and execution position domain.

## Core Invariants

### I1: Single Position Per Symbol
- **Rule**: At most one active position per symbol at any time
- **Rationale**: Prevents split position tracking and inconsistent PnL calculation
- **Enforcement**: Runtime state uses `Dict[symbol, position]` (inherently unique keys)

### I2: SL Requirement for Open Positions
- **Rule**: If position is open (qty ≠ 0) and strategy requires SL → exactly one active SL order with correct side/qty
- **Rationale**: Risk management - every open position must be protected
- **Enforcement**: Watchdog detects `NO_SL_FOR_OPEN_POSITION`, logs warning
- **Exception**: Positions in process of closing (closing_flag=True) may temporarily lack SL

### I3: No Orphan Brackets
- **Rule**: Closed position (qty = 0) must not have active SL/TP orders
- **Rationale**: Prevents erroneous fills from stale orders
- **Enforcement**: Watchdog detects `ORPHAN_SL`/`ORPHAN_TP`, triggers cleanup

### I4: Finite Position Values
- **Rule**: No negative, NaN, or infinite position size/exposure/PnL values
- **Rationale**: Data integrity - invalid values indicate corruption
- **Bounds**:
  - position_size: finite, |size| < 1e12
  - exposure_usdt: finite, 0 ≤ exposure < 1e15
  - realized/unrealized_pnl: finite, |pnl| < 1e15

### I5: Idempotency
- **Rule**: Duplicate `TRADE_EXECUTED` events (same trade_id) must not double-count position/PnL
- **Rationale**: Network/exchange may send duplicate fills
- **Enforcement**: `FillIdempotency` tracks trade_id, skips duplicates, increments `fills_duplicate` metric

### I6: Out-of-Order Event Consistency
- **Rule**: Out-of-order `CANCEL`/`ORDER`/`FILL` events must not create inconsistent state
- **Rationale**: Async event delivery from WebSocket/REST may arrive out-of-order
- **Enforcement**:
  - Event timestamps recorded
  - State machine handles late events gracefully
  - Idempotency catches duplicates

---

## Automatic Enforcement

These invariants are automatically verified by:

**Tests**: `tests/domains/execution_position/shadow_execpos/test_runtime_concurrency_edge_cases.py`

**Task**: [EP-RUNTIME-CONCURRENCY-SAFETY-S1]

**Helpers**: `tests/domains/execution_position/shadow_execpos/invariant_helpers.py`
- `assert_single_position_per_symbol()`
- `assert_no_double_close()`
- `assert_no_orphan_brackets()`
- `assert_no_impossible_exposure()`
- `assert_idempotency_respected()`
- `assert_all_invariants()` (runs all checks)

---

## Historical Context

These invariants address issues found in historical audits:

- **Double-close risk**: Race conditions during rapid open/close sequences
- **Orphan SL**: SL orders remaining after position closed (JOURNAL 2025-11-19)
- **Race conditions**: Position tracking without locks (AUDIT_VERIFICATION_LOG.md)
- **Idempotency gaps**: Duplicate fills causing double-counted PnL

---

**Version**: 1.0  
**Last Updated**: 2025-11-21  
**Related**: behavior_execpos.md, EP-RUNTIME-CONCURRENCY-SAFETY-S1
