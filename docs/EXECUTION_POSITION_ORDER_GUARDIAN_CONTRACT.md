# OrderGuardian Service Contract

**Version**: 1.0
**Status**: Frozen for EP-STAB phase
**Owner**: Execution Position Domain
**Last Updated**: 2025-11-19

---

## 1. Overview

`OrderGuardian` is the centralized service responsible for tracking, protecting, and cleaning up bracket orders (SL/TP) in the aggregated OCO architecture. It acts as the **single source of truth** for bracket lifecycle management, ensuring ExecPosFSM and ManageFlowFSM delegate cleanup responsibilities rather than implementing their own.

**Key Responsibilities**:
- Maintain mapping of `(symbol, side)` → active `BracketSetMeta`
- Track entry orders and their associated bracket orders
- Perform safe cleanup of orphaned brackets when position closes
- DR/restart: rehydrate bracket state from live open orders
- Enforce aggregated OCO invariants (one bracket set per position side)

**Architecture Position**:
```
ExecPosFSM / ManageFlowFSM
         ↓
    OrderGuardian (this contract)
         ↓
    BinanceAdapter (transport layer)
```

---

## 2. Public API

### 2.1. `register_entry(...)`

**Purpose**: Register a new entry order after successful placement on exchange.

**Signature**:
```python
def register_entry(
    self,
    *,
    symbol: str,
    order_id: str,
    client_order_id: str,
    side: str,  # "BUY" or "SELL"
    qty: float,
    corr_id: Optional[str] = None,
    rid: Optional[str] = None,
    ts: Optional[float] = None
) -> None
```

**Arguments**:
- `symbol`: Trading symbol (e.g., "BTCUSDT")
- `order_id`: Exchange-assigned order ID
- `client_order_id`: Client-assigned order ID for tracking
- `side`: "BUY" or "SELL" (normalized to LONG/SHORT internally)
- `qty`: Order quantity
- `corr_id`: Optional correlation ID for tracing
- `rid`: Optional request ID for WHY-chain
- `ts`: Optional timestamp (defaults to `clock.time()`)

**Side Effects**:
- Stores entry metadata in `InMemoryStore` under key `entry:{order_id}`
- Creates bidirectional mapping: `client:{client_order_id}` ↔ `order:{order_id}`
- Logs `register_entry` event to `logs/order_guardian.log`
- Updates known symbols set via `update_known_symbols([symbol])`

**Invariants**:
- After registration, `store.get(f"entry:{order_id}")` returns entry metadata
- Entry remains in store until explicitly removed by `on_fill()` or manual cleanup
- Entry `filled_qty` starts at 0.0, updated incrementally by `on_fill()`

**Usage Context**:
- Called by `ExecPosFSM` after successful `DEC:OPEN` execution
- Must be called **before** registering brackets for the entry

---

### 2.2. `register_bracket_set(...)`

**Purpose**: Register or update the aggregated bracket set metadata for `(symbol, side)`.

**Signature**:
```python
def register_bracket_set(
    self,
    *,
    bracket_set_id: str,
    symbol: str,
    side: str,  # "LONG" or "SHORT"
    sl_order_id: Optional[str],
    tp_order_id: Optional[str],
    created_ts: float,
) -> BracketSetMeta
```

**Arguments**:
- `bracket_set_id`: Unique identifier for this bracket set (e.g., "RID_XYZ")
- `symbol`: Trading symbol
- `side`: Position side ("LONG" or "SHORT", normalized from BUY/SELL)
- `sl_order_id`: Stop-loss order ID (None if no SL)
- `tp_order_id`: Take-profit order ID (None if no TP)
- `created_ts`: Timestamp of bracket set creation

**Side Effects**:
- Stores `BracketSetMeta` in `_bracket_sets` dict under key `(symbol, side)`
- Increments `version` field if updating existing bracket set
- Returns the created/updated `BracketSetMeta` object

**Invariants**:
- **One bracket set per `(symbol, side)`**: Overwrites previous metadata
- After registration, `get_active_bracket_set(symbol, side)` returns this metadata
- `version` increments on each update (starts at 0 for new registrations)

**Usage Context**:
- Called by `ManageFlowFSM` after successful aggregated OCO placement
- Called during DR/startup by `rehydrate_bracket_set_for_position()` for existing positions

---

### 2.3. `rehydrate_bracket_set_for_position(...)`

**Purpose**: Reconstruct aggregated bracket metadata from live open orders (DR/restart scenario).

**Signature**:
```python
def rehydrate_bracket_set_for_position(
    self,
    *,
    symbol: str,
    side: str,
    position_amt: float,
    open_orders: Sequence[Any],
    now_ts: Optional[float] = None,
) -> Optional[BracketSetMeta]
```

**Arguments**:
- `symbol`: Trading symbol
- `side`: Position side ("LONG" or "SHORT")
- `position_amt`: Current position quantity (must be non-zero)
- `open_orders`: List of live orders from `adapter.get_open_orders()`
- `now_ts`: Optional timestamp for bracket set creation

**Side Effects**:
- **If position_amt ≤ 0**: Returns `None`, no rehydration
- **If existing metadata found**: Returns existing `BracketSetMeta` without changes
- **If brackets found in open_orders**:
  - Groups by `bracket_set_id` (extracted from `clientOrderId`)
  - Selects "best" group (most recent timestamp)
  - Calls `register_bracket_set()` internally
  - Returns newly created `BracketSetMeta`
- **If no brackets found**: Returns `None`

**Invariants**:
- **Idempotent**: Re-running with same inputs returns same result
- **Conflict resolution**: Chooses bracket set with latest timestamp among duplicates
- **No cancellations**: Only reads open orders, does not modify exchange state
- **Requires aggregated OCO enabled**: Returns `None` if `_aggregated_oco_cfg.enabled == False`

**Usage Context**:
- Called by `ExecPosFSM._ensure_brackets_for_existing_positions()` during startup
- Called by ManageFlowFSM during recovery after watchdog detects missing brackets

---

### 2.4. `ensure_single_bracket_set_for_position(...)`

**Purpose**: Enforce the "one bracket set per (symbol, side)" invariant by canceling extra brackets.

**Signature**:
```python
def ensure_single_bracket_set_for_position(
    self,
    *,
    symbol: str,
    side: str,
    position_amt: float,
    open_orders: Sequence[Any],
    now_ts: Optional[float] = None,
) -> int  # Returns count of cancelled orders
```

**Arguments**:
- `symbol`: Trading symbol
- `side`: Position side ("LONG" or "SHORT")
- `position_amt`: Current position quantity
- `open_orders`: List of live orders from exchange
- `now_ts`: Optional timestamp for TTL protection

**Side Effects**:
- **If position_amt == 0**: Cancels **all** brackets for this `(symbol, side)`, clears metadata, returns count
- **If no metadata registered**: Returns 0 (no cleanup)
- **If metadata exists**:
  - Identifies "protected" orders (current `sl_order_id`, `tp_order_id`)
  - Cancels all other reduceOnly/closePosition brackets for this symbol/side
  - Respects TTL protection: skips cancellation if protected order created within `ttl_protect_new_bracket_ms`
- Emits `agg_oco_ensure_single` observability event

**Invariants**:
- **Post-condition (position_amt > 0)**: Only orders in current `BracketSetMeta` remain active
- **Post-condition (position_amt == 0)**: All brackets cancelled, metadata cleared
- **TTL guard**: New brackets (within TTL window) are protected from cancellation
- **Idempotent**: Safe to call multiple times with same inputs

**Usage Context**:
- Called by ManageFlowFSM after placing new aggregated OCO brackets
- Called by watchdog after detecting duplicate bracket sets
- Called during scale-in / partial close to clean up old brackets

---

### 2.5. `cleanup_orphans(...)`

**Purpose**: Cancel bracket orders when position is closed or parent entry missing.

**Signature**:
```python
async def cleanup_orphans(
    self,
    symbol: Optional[str] = None,
    hard: bool = False,
    batch_limit: int = 50
) -> int  # Returns count of cancelled orders
```

**Arguments**:
- `symbol`: Optional symbol filter (if None, checks all symbols)
- `hard`: If `True`, cancels all reduceOnly/closePosition brackets regardless of position state
- `batch_limit`: Maximum orders to cancel per call (default 50)

**Side Effects**:
- Fetches current positions via `adapter.get_open_positions()`
- Fetches open orders via `adapter.get_open_orders(symbol)`
- **If hard=False and position exists**: Returns 0 (no cleanup)
- **If hard=True or position_amt ≈ 0**: Cancels Guardian-owned brackets (reduceOnly/closePosition)
- Emits `cleanup_start` and per-order cancellation events
- Respects `batch_limit` to avoid rate limit issues

**Invariants**:
- **hard=False + position exists**: No cancellations (safe mode)
- **hard=True**: Cancels all Guardian brackets for symbol regardless of position
- **Ownership check**: Only cancels orders with Guardian-like `clientOrderId` pattern
- **Idempotent**: Safe to call multiple times (already-cancelled orders return success)

**Usage Context**:
- Called by `ExecPosFSM` after `DEC:CLOSE` execution (with `hard=True`)
- Called by `reconcile_symbol()` for post-CLOSE cleanup
- Called by periodic orphan detection background task

---

### 2.6. `clear_bracket_set_for_position(...)`

**Purpose**: Remove tracked bracket set metadata for `(symbol, side)`.

**Signature**:
```python
def clear_bracket_set_for_position(
    self,
    *,
    symbol: str,
    side: str
) -> None
```

**Arguments**:
- `symbol`: Trading symbol
- `side`: Position side ("LONG" or "SHORT")

**Side Effects**:
- Removes `BracketSetMeta` from `_bracket_sets` dict for key `(symbol, side)`
- **Does NOT cancel orders on exchange** (only internal state cleanup)
- Safe no-op if metadata doesn't exist

**Invariants**:
- Post-condition: `get_active_bracket_set(symbol, side)` returns `None`
- Does not affect other symbols or opposite side
- Idempotent: calling multiple times has same effect as once

**Usage Context**:
- Called by `ExecPosFSM` after `DEC:CLOSE` completion and position confirmed FLAT
- Called by `ensure_single_bracket_set_for_position()` when position_amt == 0
- Called by watchdog when detecting stale metadata with no live position

---

### 2.7. `reconcile_symbol(...)`

**Purpose**: Reconcile orders for symbol by canceling orphaned brackets if no position exists.

**Signature**:
```python
async def reconcile_symbol(
    self,
    symbol: str,
    rid: Optional[str] = None
) -> None
```

**Arguments**:
- `symbol`: Trading symbol to reconcile
- `rid`: Optional request ID for tracing

**Side Effects**:
- Fetches current positions via `adapter.get_open_positions()`
- **If position exists**: Returns early (no action)
- **If position_amt ≈ 0**: Calls `cleanup_orphans(symbol, hard=True)` to cancel all brackets
- Logs `reconcile_symbol` event with cancellation count

**Invariants**:
- Only cancels brackets when position is confirmed FLAT
- Safe to call on symbols with active positions (no-op)
- Delegates to `cleanup_orphans()` for actual cancellation logic

**Usage Context**:
- Called by `ExecPosFSM` after `DEC:CLOSE` execution
- Called by watchdog when detecting FLAT position with active brackets
- Called during DR/startup after confirming FLAT positions

---

### 2.8. `get_active_bracket_set(...)`

**Purpose**: Retrieve the current `BracketSetMeta` for `(symbol, side)`.

**Signature**:
```python
def get_active_bracket_set(
    self,
    symbol: str,
    side: str
) -> Optional[BracketSetMeta]
```

**Arguments**:
- `symbol`: Trading symbol
- `side`: Position side ("LONG" or "SHORT")

**Returns**:
- `BracketSetMeta` object if registered, else `None`

**Side Effects**: None (pure query)

**Usage Context**:
- Called by FSMs to check if brackets exist for a position
- Called during DR/startup to avoid duplicate rehydration
- Called by watchdog to validate bracket state

---

### 2.9. `list_all_bracket_sets(...)`

**Purpose**: Return list of all known bracket set metadata objects.

**Signature**:
```python
def list_all_bracket_sets(self) -> List[BracketSetMeta]
```

**Returns**: Shallow copy list of all `BracketSetMeta` objects in `_bracket_sets`

**Side Effects**: None (pure query)

**Usage Context**:
- Called by observability/debug endpoints for state dump
- Called by CLI tools for bracket set inspection
- Called by watchdog for global invariant checks

---

## 3. Aggregated OCO Invariants

### 3.1. One Active BracketSetMeta per (symbol, side)

**Invariant**: At any given time, `_bracket_sets[(symbol, side)]` contains **at most one** `BracketSetMeta`.

**Enforcement**:
- `register_bracket_set()` overwrites previous metadata
- `ensure_single_bracket_set_for_position()` cancels extra brackets on exchange
- `clear_bracket_set_for_position()` removes metadata when position closes

**Violation Handling**:
- Watchdog detects multiple SL/TP for same `(symbol, side)`
- Triggers auto-heal: calls `ensure_single_bracket_set_for_position()`
- Alerts monitoring system with `MULTIPLE_BRACKET_SETS` event

---

### 3.2. Position Amount == 0 → No Brackets

**Invariant**: When `position_amt` ≈ 0 for `(symbol, side)`, no reduceOnly/closePosition brackets should exist.

**Enforcement**:
- `ensure_single_bracket_set_for_position()` cancels all brackets when `position_amt == 0`
- `cleanup_orphans(hard=True)` removes brackets after `DEC:CLOSE`
- `reconcile_symbol()` double-checks FLAT state after close

**Violation Handling**:
- Watchdog detects brackets with no position: emits `ORPHAN_SL` alert
- Triggers auto-heal: calls `cleanup_orphans(symbol, hard=True)`

---

### 3.3. TTL Protection for New Brackets

**Invariant**: Newly placed brackets (within `ttl_protect_new_bracket_ms`) are protected from cleanup.

**Configuration**:
```python
aggregated_oco:
  ttl_protect_new_bracket_ms: 5000  # 5 seconds protection
```

**Enforcement**:
- `ensure_single_bracket_set_for_position()` checks bracket creation timestamp
- If `(now - created_ts) * 1000 < ttl_protect_new_bracket_ms`, bracket is protected
- Protected brackets are skipped during cleanup, even if duplicates detected

**Rationale**:
- Prevents race condition where new brackets placed just before cleanup cycle
- Gives exchange time to process new orders before cleanup verification

---

### 3.4. allow_unprotected_position Behavior

**Configuration**:
```python
aggregated_oco:
  allow_unprotected_position: false  # Default: require brackets
```

**When `false` (strict mode)**:
- Position without brackets triggers watchdog alert `NO_SL`
- Auto-heal attempts to place missing brackets
- Contract validation rejects `DEC:OPEN` without bracket placement

**When `true` (permissive mode)**:
- Position may exist temporarily without brackets (scale-in window)
- Watchdog logs warning but does not trigger auto-heal
- Used for testing or legacy compatibility

**Enforcement**:
- Checked by ManageFlowFSM before allowing unprotected position open
- Validated by config resolver at startup (aggregated_only mode requires `false`)

---

## 4. DR / Restart Behavior

### 4.1. Rehydration from Open Orders

**Scenario**: System restarts with open positions and active brackets on exchange.

**Process**:
1. `ExecPosFSM._ensure_brackets_for_existing_positions()` called during startup
2. For each position: calls `rehydrate_bracket_set_for_position(symbol, side, position_amt, open_orders)`
3. OrderGuardian:
   - Filters open orders for reduceOnly/closePosition brackets
   - Groups by `bracket_set_id` (extracted from `clientOrderId`)
   - Selects bracket set with latest timestamp (conflict resolution)
   - Calls `register_bracket_set()` to restore metadata
4. Returns `BracketSetMeta` or `None` if no brackets found

**Conflict Resolution**:
- **Multiple bracket sets found**: Chooses one with most recent `updateTime` timestamp
- **Old brackets remain**: NOT cancelled during rehydration (requires explicit `ensure_single_bracket_set_for_position()` call)

**Watchdog Integration**:
- After rehydration, watchdog runs invariant checks
- If duplicates detected: triggers `ensure_single_bracket_set_for_position()` to cleanup

---

### 4.2. Handling Missing Brackets

**Scenario**: Position exists but no brackets found during rehydration.

**OrderGuardian Behavior**:
- `rehydrate_bracket_set_for_position()` returns `None`
- Does NOT attempt to place brackets (not Guardian's responsibility)

**FSM Responsibility**:
- `ExecPosFSM` logs warning: "Position without brackets after rehydration"
- If `allow_unprotected_position=false`: ManageFlowFSM attempts to place missing brackets
- Watchdog alerts monitoring system with `NO_SL` event

---

### 4.3. Handling Duplicate Brackets

**Scenario**: Multiple SL/TP orders exist for same `(symbol, side)` after restart.

**OrderGuardian Behavior**:
- `rehydrate_bracket_set_for_position()` selects one bracket set (latest timestamp)
- Stores selected metadata, ignores others

**Cleanup Trigger**:
- FSM calls `ensure_single_bracket_set_for_position()` after rehydration
- Guardian cancels all brackets NOT in registered metadata
- Result: Only one bracket set remains

**Edge Case - TTL Protection**:
- If duplicate brackets were created recently (within TTL window): protected from cancellation
- Watchdog will retry cleanup after TTL expires

---

## 5. Contract with ExecPosFSM / ManageFlowFSM

### 5.1. ExecPosFSM Expectations

#### After `DEC:OPEN` Execution

**ExecPosFSM Responsibilities**:
1. Call `OrderGuardian.register_entry(...)` with entry order details
2. Delegate bracket placement to ManageFlowFSM (emits `EVT:ENTRY_FILLED`)
3. Wait for ManageFlowFSM to emit `EVT:AGG_OCO_BRACKETS_PLACED`

**OrderGuardian Guarantees**:
- Entry metadata stored and retrievable via `store.get(f"entry:{order_id}")`
- Entry tracked for fill updates via `on_fill()`
- Entry remains in store until position fully closed

#### After `DEC:CLOSE` Execution

**ExecPosFSM Responsibilities**:
1. Execute reduce-only close order
2. Call `OrderGuardian.cleanup_orphans(symbol, hard=True)` to cancel brackets
3. Call `OrderGuardian.reconcile_symbol(symbol)` for double-check
4. Call `OrderGuardian.clear_bracket_set_for_position(symbol, side)` to clear metadata

**OrderGuardian Guarantees**:
- All reduceOnly/closePosition brackets for symbol cancelled
- BracketSetMeta removed after `clear_bracket_set_for_position()` call
- No orphaned brackets remain on exchange (verified by `reconcile_symbol`)

#### During DR/Startup

**ExecPosFSM Responsibilities**:
1. Fetch open positions via adapter
2. For each position: call `OrderGuardian.rehydrate_bracket_set_for_position(...)`
3. If rehydration succeeds: verify bracket state with watchdog
4. If rehydration fails (no brackets): handle per `allow_unprotected_position` config

**OrderGuardian Guarantees**:
- If brackets found: `BracketSetMeta` registered for `(symbol, side)`
- If duplicates found: selects one bracket set (latest timestamp)
- If no brackets found: returns `None` (does not place brackets)

---

### 5.2. ManageFlowFSM Expectations

#### After Aggregated OCO Placement

**ManageFlowFSM Responsibilities**:
1. Place SL/TP orders on exchange via adapter
2. Call `OrderGuardian.register_bracket_set(...)` with order IDs
3. Call `OrderGuardian.ensure_single_bracket_set_for_position(...)` to cleanup old brackets
4. Emit `EVT:AGG_OCO_BRACKETS_PLACED` event

**OrderGuardian Guarantees**:
- BracketSetMeta stored and retrievable via `get_active_bracket_set()`
- Old brackets (not in new metadata) cancelled by `ensure_single_bracket_set_for_position()`
- TTL protection prevents new brackets from being cancelled prematurely

#### During Scale-In / Partial Close

**ManageFlowFSM Responsibilities**:
1. Calculate new aggregated SL/TP levels
2. Cancel old brackets via adapter (or delegate to Guardian)
3. Place new brackets with updated levels
4. Call `OrderGuardian.register_bracket_set(...)` with new bracket IDs
5. Call `OrderGuardian.ensure_single_bracket_set_for_position(...)` to verify cleanup

**OrderGuardian Guarantees**:
- Metadata updated to reflect new bracket set
- Old brackets cancelled during `ensure_single_bracket_set_for_position()` call
- Version field incremented for observability

#### During Recalc (TP/SL Update)

**ManageFlowFSM Responsibilities**:
1. Cancel old brackets
2. Place new brackets with updated prices
3. Call `OrderGuardian.register_bracket_set(...)` with new bracket IDs

**OrderGuardian Guarantees**:
- Metadata replaced (not merged) with new bracket IDs
- Old bracket IDs forgotten (caller must cancel separately)

---

## 6. EP-STAB Integration Notes

### 6.1. EP-STAB-GUARDIAN-CLOSE-CLEANUP

**Context**: Delegated DEC:CLOSE cleanup to OrderGuardian (RID: EP-STAB-GUARDIAN-CLOSE-CLEANUP).

**Contract Dependency**:
- ExecPosFSM relies on `cleanup_orphans(symbol, hard=True)` contract
- **Guarantee**: All brackets cancelled after CLOSE, regardless of position state
- **Guarantee**: `reconcile_symbol()` provides double-check for FLAT state

**Before EP-STAB**:
- ExecPosFSM had manual `get_open_orders()` + `cancel_order()` loops (59 lines)
- Risk of divergence between ExecPosFSM and Guardian cleanup logic

**After EP-STAB**:
- Single source of truth: `cleanup_orphans()` method
- ExecPosFSM delegates cleanup (3 lines of code)
- No manual loops, no duplication, no divergence risk

---

### 6.2. EP-STAB-POS-SNAPSHOT

**Context**: Centralized position parsing via `PositionSnapshot` dataclass (RID: EP-STAB-POS-SNAPSHOT).

**Contract Dependency**:
- Guardian methods (`cleanup_orphans`, `reconcile_symbol`) parse `positionAmt` from REST responses
- Relies on consistent side detection (LONG/SHORT from BUY/SELL or sign of qty)

**Impact on Contract**:
- Guardian internally normalizes side via `_normalize_side(side)` method
- **BUY** → **LONG**, **SELL** → **SHORT** (canonical form)
- ExecPosFSM uses `PositionSnapshot.from_rest_list()` before calling Guardian APIs
- Ensures consistent side representation across FSM → Guardian boundary

---

### 6.3. EP-STAB-ENTRYEXIT-HELPER

**Context**: Centralized ENTRY/EXIT classification via `is_exit_order()` helper (RID: EP-STAB-ENTRYEXIT-HELPER).

**Contract Dependency**:
- Guardian uses `reduceOnly` and `closePosition` fields to identify brackets
- `cleanup_orphans()` filters orders via:
  ```python
  is_reduce_only = order.get("reduceOnly", False)
  is_close_position = order.get("closePosition", False)
  ```
- Matches contract helper logic for EXIT order detection

**Impact on Contract**:
- Guardian's bracket detection aligns with FSM's exit order classification
- Ensures Guardian only cancels EXIT orders (brackets), never ENTRY orders
- Prevents accidental cancellation of pending entry orders during cleanup

---

### 6.4. EP-STAB-ORDERGUARDIAN-CONTRACT (This Document)

**Purpose**: Formalize OrderGuardian API as a frozen contract for future stability.

**Benefits**:
1. **Single Source of Truth**: Clear specification prevents implementation drift
2. **Safe Refactoring**: Changes require contract update → forces impact analysis
3. **Integration Clarity**: FSMs know exact guarantees and side effects
4. **DR Confidence**: Rehydration behavior explicitly documented
5. **Watchdog Alignment**: Invariants match auto-heal triggers

**Maintenance Process**:
- **Any behavior change**: Update contract first, then code
- **Breaking changes**: Require new contract version (v2.0)
- **Additive changes**: Document in changelog, increment minor version

---

## 7. Observability Events

OrderGuardian emits structured events to `logs/order_guardian.log` for audit and debugging.

### Key Event Types

| Event Type | Trigger | Payload Fields |
|:-----------|:--------|:--------------|
| `register_entry` | Entry order registered | `symbol`, `order_id`, `side`, `qty`, `rid` |
| `register_bracket_set` | Bracket set registered | `symbol`, `side`, `sl_order_id`, `tp_order_id`, `version` |
| `cleanup_start` | Orphan cleanup initiated | `symbol`, `hard`, `position_amt`, `has_position` |
| `agg_oco_ensure_single` | Duplicate cleanup | `symbol`, `side`, `extra_cancelled`, `decision` |
| `reconcile_symbol` | Symbol reconciliation | `symbol`, `position_amt`, `cancelled_count` |
| `agg_oco_zero_position_cleanup` | Zero position cleanup | `symbol`, `side`, `cancelled` |

### Metrics

- `_bracket_sets` size: Number of active bracket sets
- Cancellation counts: Per-method counters (cleanup, ensure_single, reconcile)
- TTL protection hits: Count of brackets protected by TTL guard

---

## 8. Testing Contract Compliance

### Unit Test Coverage (Existing)

- `tests/unit/test_order_guardian_per_entry.py` - Entry registration and fill tracking
- `tests/domains/execution_position/test_order_guardian_bracket_state.py` - BracketSetMeta lifecycle
- `tests/domains/execution_position/test_order_guardian_aggregated_cleanup.py` - cleanup_orphans behavior
- `tests/domains/execution_position/test_guardian_close_cleanup.py` - DEC:CLOSE delegation

### Integration Test Coverage

- `tests/domains/execution_position/test_agg_oco_integration.py` - Full OCO lifecycle
- `tests/domains/execution_position/test_aggregated_oco_multi_entry_flow.py` - Multi-entry scenarios
- `tests/domains/execution_position/test_aggregated_oco_dr_restart.py` - DR/rehydration

### Contract Validation Checklist

- [ ] All public methods have docstrings matching contract signatures
- [ ] Invariants enforced by assertions in tests (one bracket set per side)
- [ ] DR scenarios tested: rehydration, duplicates, missing brackets
- [ ] TTL protection tested: new brackets protected during cleanup window
- [ ] Zero position cleanup tested: all brackets removed when position_amt == 0
- [ ] Hard mode tested: cleanup_orphans(hard=True) cancels regardless of position

---

## 9. Future Evolution

### Planned Extensions (Out of Scope for EP-STAB)

1. **Multi-leg brackets**: Support trailing stops, conditional TP levels
2. **Cross-symbol coordination**: Prevent portfolio-level over-leverage
3. **Adapter-agnostic**: Support non-Binance exchanges via adapter protocol
4. **Persistent store**: Replace `InMemoryStore` with Redis for multi-process coordination

### Breaking Change Policy

- **v1.x**: Additive changes only (new methods, optional parameters)
- **v2.0**: Breaking changes allowed (remove methods, change semantics)
- **Deprecation**: Mark method as `@deprecated` for 2 releases before removal

### Contract Versioning

- **Current**: v1.0 (frozen for EP-STAB phase)
- **Next minor**: v1.1 (planned: async storage protocol)
- **Next major**: v2.0 (planned: multi-exchange support)

---

## 10. References

- **Implementation**: `apps/reference/services/order_guardian.py`
- **Tests**: `tests/domains/execution_position/test_order_guardian_*.py`
- **Integration**: `apps/reference/domains/execution_position/fsm.py`
- **Configuration**: `config/core.yaml` → `execution.position.guardian`

**Related Documents**:
- `docs/oco/AGGREGATED_OCO_SPEC.md` - Aggregated OCO architecture
- `docs/EXECUTION_POSITION_QTY_GUARD_AUDIT.md` - Quantity guard integration
- `JOURNAL.md` - EP-STAB changelog entries

**Maintainers**: Architecture WG, Execution Position Domain Team
**Review Cadence**: Quarterly (or on major feature additions)

---

**End of Contract v1.0**
