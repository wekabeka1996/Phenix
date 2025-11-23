# Aggregated OCO Bracket Analysis – EP-PORT-BRACKETS-S1

**Status**: PHASE 0 Discovery Complete
**Date**: 2025-11-19
**RID**: EP-PORT-BRACKETS-S1
**Owner**: Execution Position Domain

---

## 1. Executive Summary

**Purpose**: Document desired bracket invariants, historical behaviors from legacy implementation, and gaps in current ExecPosRuntimeV2 to guide BracketService contract design.

**Key Findings**:
- **Bracket Aggregator** (`bracket_aggregator.py`): Pure functional module for computing TP/SL levels from `(avg_entry_price, position_amt, side, risk_cfg)` → exists and works correctly.
- **OrderGuardian** (`order_guardian.py`): Comprehensive bracket lifecycle manager (2086 LOC, frozen contract v1.0) → exists, well-tested, but NOT actively integrated into V2.
- **AggOcoWatchdogService** (`watchdog.py`): Detect-only invariant checker → exists in V2 but **does NOT auto-heal** (recommendations-only).
- **ManageFlowFSM**: Historical recalc logic (`recalc_on_partial_close`, `recalc_on_scale_in`) exists in legacy docs but **NOT ported to V2**.

**Critical Gap**: V2 has all building blocks (aggregator, guardian, watchdog) but lacks **canonical BracketService API** that orchestrates:
1. **Build state** from current position + open orders
2. **Evaluate** invariants and produce typed BracketActions
3. **Explain** violations with XAI why-chains (≤80 chars)
4. **No live side effects** (recommendations only, caller decides to execute)

---

## 2. Desired Bracket Invariants

### 2.1. One Bracket Set per (Symbol, Side)

**Definition**: At any time, for a non-zero position on `(symbol, side)`, exactly **one** bracket set (SL + TP pair) should be registered in OrderGuardian.

**Rationale**:
- Simplifies state management (no version conflicts)
- Prevents duplicate TP/SL orders that confuse risk calculations
- Ensures OrderGuardian metadata uniquely identifies protection orders

**Enforcement Points**:
- `OrderGuardian.register_bracket_set()`: Overwrites previous metadata (version++)
- `OrderGuardian.ensure_single_bracket_set_for_position()`: Cancels extra brackets on exchange
- Watchdog: Detects `MULTIPLE_META_SETS` and recommends cleanup

**Violations**:
- Multiple SL orders with different `clientOrderId` prefixes for same `(symbol, side)`
- Scale-in or recalc places new brackets without canceling old ones
- DR/restart finds duplicate bracket sets (conflict resolution: choose latest timestamp)

---

### 2.2. Position Amount == 0 → No Brackets

**Definition**: When `position_amt` ≈ 0 for `(symbol, side)`, **no** reduceOnly/closePosition brackets should remain active on exchange.

**Rationale**:
- Orphan brackets can trigger unexpected position flips if filled
- Wastes exchange rate limits and clutters open orders
- Violates clean separation: position lifecycle controls bracket lifecycle

**Enforcement Points**:
- `OrderGuardian.cleanup_orphans(symbol, hard=True)`: Cancels all brackets after DEC:CLOSE
- `OrderGuardian.ensure_single_bracket_set_for_position(position_amt=0)`: Clears metadata and cancels
- Watchdog: Detects `ORPHAN_SL_FOR_ZERO_POSITION` and recommends cleanup

**Violations**:
- DEC:CLOSE execution succeeds but cleanup step skipped
- Exception during reconcile_symbol() leaves orphans
- Race condition: TP fill closes position, but ManageFlowFSM doesn't clear SL order

---

### 2.3. Position Amount > 0 → Exactly One SL (if allow_unprotected_position=false)

**Definition**: Open position must have exactly **one active SL order** protecting downside risk.

**Rationale**:
- Core risk management requirement (no naked positions)
- Aggregated OCO architecture assumes SL always exists for open positions
- TP is optional (pure upside), but SL is mandatory

**Configuration**:
```yaml
aggregated_oco:
  allow_unprotected_position: false  # Strict mode (default)
```

**Enforcement Points**:
- ManageFlowFSM: Places SL immediately after entry fill
- Watchdog: Detects `NO_SL_FOR_OPEN_POSITION` if missing
- Config validation: `aggregated_only_mode=true` requires `allow_unprotected_position=false`

**Violations**:
- Scale-in fill processed, but recalc fails → old SL cancelled, new SL not placed
- Partial close with `recalc_on_partial_close=false` → SL remains at old level (wrong qty)
- DR/restart finds position but no SL orders in open_orders

---

### 2.4. Bracket Levels Match Aggregated Position State

**Definition**: TP/SL prices must be computed from **current aggregated position** (`avg_entry_price`, `position_amt`), not individual entries.

**Rationale**:
- Aggregated OCO v1 design: one bracket set per side, not per entry
- Scale-in changes avg_entry → requires TP/SL recalc
- Partial close changes qty → may require TP/SL recalc (if `recalc_on_partial_close=true`)

**Computation**:
```python
# bracket_aggregator.py:compute_aggregated_brackets()
if side == "LONG":
    sl_price = avg_entry * (1 - sl_pct)
    tp_price = avg_entry * (1 + sl_pct * tp_rr)
elif side == "SHORT":
    sl_price = avg_entry * (1 + sl_pct)
    tp_price = avg_entry * (1 - sl_pct * tp_rr)
```

**Enforcement Points**:
- `bracket_aggregator.compute_aggregated_brackets()`: Pure function, zero deps
- ManageFlowFSM: Calls aggregator after scale-in/recalc events
- BracketService (new): Encapsulates aggregator call + constraints validation

**Violations**:
- Old brackets remain at stale levels after scale-in (if `recalc_on_scale_in=false`)
- TP/SL prices violate exchange `tick_size` or `min_price` constraints
- Race condition: position updates during bracket placement → stale avg_entry used

---

### 2.5. TTL Protection for New Brackets

**Definition**: Newly placed brackets (within `ttl_protect_new_bracket_ms`) are **protected** from cleanup/cancellation.

**Configuration**:
```yaml
aggregated_oco:
  ttl_protect_new_bracket_ms: 5000  # 5 seconds
```

**Rationale**:
- Prevents race: new brackets placed just before watchdog cleanup cycle
- Gives exchange time to process orders before validation
- Fail-safe: if cleanup accidentally targets new brackets, TTL prevents premature cancel

**Enforcement Points**:
- `OrderGuardian.ensure_single_bracket_set_for_position()`: Checks `(now - created_ts) < ttl_ms`
- Protected brackets skipped during cleanup (logged as "protected by TTL")

**Violations**:
- Cleanup logic ignores `created_ts` field → new brackets cancelled immediately
- TTL window too short (< 1s) → race conditions still occur
- TTL window too long (> 30s) → stale duplicates persist

---

## 3. Historical Behaviors (Legacy Implementation)

### 3.1. recalc_on_partial_close (Legacy Feature)

**Config**:
```yaml
aggregated_oco:
  recalc_on_partial_close: bool  # Default: false in legacy, true in V2-only mode
```

**Behavior**:
- **When `true`**: Partial TP/SL fill triggers **bracket recalc** → cancel old brackets, place new ones at updated levels.
- **When `false`**: Partial fill does NOT trigger recalc → old brackets remain (potentially at wrong qty/levels).

**Historical Context** (from `INVESTIGATION_AGGREGATED_OCO.md`):
```python
# fsm_manage.py L1411 (legacy)
if agg_cfg.recalc_on_partial_close:
    return self._recalc_aggregated_brackets(msg, reason="partial_close_fill")
# ❌ BUG: If false, _clear_guardian_bracket_set() NOT called → orphan old order IDs
```

**Design Flaw**:
- Setting to `false` creates **orphan bracket metadata** (old order IDs lost, but orders still live on exchange).
- Watchdog cannot detect orphans because Guardian metadata overwritten without cleanup.

**Recommendation for V2**:
- **Always `true` in aggregated_only mode** (enforced by config validator).
- BracketService should assume recalc on partial close (V2 invariant).

---

### 3.2. recalc_on_scale_in (Legacy Feature)

**Config**:
```yaml
aggregated_oco:
  recalc_on_scale_in: bool  # Default: true
```

**Behavior**:
- **When `true`**: Scale-in (entry fill while position open) triggers **bracket recalc** → avg_entry changes, TP/SL updated.
- **When `false`**: Scale-in does NOT trigger recalc → brackets remain at old avg_entry levels.

**Historical Bug** (from `INVESTIGATION_AGGREGATED_OCO.md`):
```python
# fsm_manage.py L1422 (legacy)
if was_open and agg_cfg.recalc_on_scale_in:
    return self._recalc_aggregated_brackets(msg, reason="scale_in_fill")
# ❌ BUG: _clear_guardian_bracket_set() NOT called before recalc → old order IDs overwritten
```

**Root Cause**:
- `register_bracket_set()` OVERWRITES metadata without cleanup of old order IDs.
- Old brackets remain on exchange (orphans).

**Recommendation for V2**:
- **Always cleanup before recalc**: `clear_bracket_set_for_position(symbol, side)` before placing new brackets.
- BracketService should provide explicit `prepare_for_recalc()` method that clears old metadata.

---

### 3.3. allow_unprotected_position (Legacy Config)

**Config**:
```yaml
aggregated_oco:
  allow_unprotected_position: bool  # Default: false
```

**Behavior**:
- **When `false`**: Position without SL triggers watchdog alert `NO_SL_FOR_OPEN_POSITION` + auto-heal attempt.
- **When `true`**: Position may exist temporarily without SL (scale-in window, or manual testing).

**Historical Context**:
- Used during DR/restart when position rehydrated but brackets not yet rehydrated.
- Permissive mode for testing (bypass SL requirement).

**Recommendation for V2**:
- **Keep `false` as default** (strict risk management).
- Config validator enforces: `aggregated_only_mode=true` requires `allow_unprotected_position=false`.

---

### 3.4. OrderGuardian Cleanup Patterns

**Entry Registration** (`register_entry`):
- Called by ExecPosFSM after `DEC:OPEN` execution.
- Stores entry metadata: `{order_id, client_order_id, symbol, side, qty, filled_qty=0}`.
- Entry persists until position fully closed (no auto-cleanup).

**Bracket Registration** (`register_bracket_set`):
- Called by ManageFlowFSM after placing SL/TP orders.
- Stores `BracketSetMeta` under key `(symbol, side)`.
- **OVERWRITES** previous metadata (version++) → old order IDs lost.

**Cleanup on Close** (`cleanup_orphans`):
- Called by ExecPosFSM after `DEC:CLOSE`.
- Cancels **all** reduceOnly/closePosition brackets for symbol (if `hard=True`).
- Batch limit: 50 orders per call (rate limit protection).

**Reconciliation** (`reconcile_symbol`):
- Called after close to double-check FLAT state.
- If `position_amt ≈ 0`: calls `cleanup_orphans(symbol, hard=True)`.
- Safe to call on active positions (no-op).

**Rehydration** (`rehydrate_bracket_set_for_position`):
- Called during DR/restart for existing positions.
- Reconstructs `BracketSetMeta` from live open orders.
- Conflict resolution: chooses bracket set with **latest timestamp**.
- **Does NOT cancel duplicates** (requires explicit `ensure_single_bracket_set_for_position` call).

---

## 4. Gaps in Current V2 Implementation

### 4.1. No Canonical BracketService API

**Current State**:
- `bracket_aggregator.py`: Pure function, works correctly.
- `OrderGuardian`: Lifecycle manager, frozen contract v1.0.
- `AggOcoWatchdogService`: Detect-only, no auto-heal.
- **ManageFlowFSM**: Ported to V2 but recalc logic **NOT IMPLEMENTED** (no scale-in/partial-close recalc).

**Gap**:
- V2 has no **single entry point** for bracket state evaluation.
- FSMs call components individually: error-prone, duplicates logic.
- No typed BracketAction contracts (cancel/place/adjust).

**Impact**:
- ManageFlowFSM would need to reimplement recalc logic (risk of bugs like legacy).
- Watchdog produces recommendations but no structured API to convert them to FSM events.
- No XAI why-chain for bracket decisions.

**Proposed Solution (BracketService)**:
```python
class BracketService:
    def build_state(symbol, side) -> BracketState:
        """Reconstruct current state from position + orders + guardian metadata."""
        pass

    def evaluate(state: BracketState) -> BracketPlan:
        """Analyze state, detect violations, recommend actions."""
        pass

    def evaluate_all(positions, orders) -> List[BracketPlan]:
        """Batch evaluation for all (symbol, side) pairs."""
        pass
```

---

### 4.2. Watchdog Recommendations Not Actionable

**Current Watchdog Contract**:
```python
@dataclass
class WatchdogRecommendation:
    kind: str  # "NO_SL", "ORPHAN_SL", "TOO_MANY_SL", "MULTIPLE_META_SETS"
    symbol: str
    side: str
    position_qty: float
    sl_count: int
    action: WatchdogAction  # "PLACE_MISSING_SL", "CLEANUP_ORPHAN", "CLEANUP_EXTRA"
    why: str
```

**Gap**:
- `action` is string-based, not typed enum with parameters.
- No `order_ids` field → caller cannot know which orders to cancel.
- No `bracket_levels` field → caller cannot know what prices to place.
- `why` is free-form text, not structured XAI.

**Impact**:
- FSM receives recommendation but must re-query Guardian/adapter to get order details.
- No idempotency: re-evaluating same state produces duplicate actions.

**Proposed BracketAction** (typed contract):
```python
@dataclass
class BracketAction:
    action_type: Literal["CANCEL", "PLACE_SL", "PLACE_TP", "ADJUST"]
    order_id: Optional[str]  # For CANCEL/ADJUST
    price: Optional[Decimal]  # For PLACE/ADJUST
    qty: Optional[Decimal]   # For PLACE
    why: str  # XAI (≤80 chars)
```

---

### 4.3. No Explicit Recalc Workflow in V2

**Current V2 Runtime** (`shadow_execpos/runtime.py`):
- ManageFlowFSM ported but **recalc logic NOT IMPLEMENTED**.
- No `_recalc_aggregated_brackets()` method.
- No `_clear_guardian_bracket_set()` method.

**Gap**:
- Scale-in fill does NOT trigger bracket recalc (stale avg_entry).
- Partial TP fill does NOT trigger bracket recalc (stale qty).
- No cleanup before placing new brackets → risk of orphan old order IDs.

**Impact**:
- V2 cannot handle scale-in/partial-close scenarios correctly.
- Watchdog will detect violations but ManageFlowFSM has no code to fix them.

**Proposed Workflow** (via BracketService):
1. **FSM detects scale-in/partial-close event** → calls `BracketService.evaluate(state)`.
2. **BracketService returns BracketPlan** with actions: `[CANCEL(old_sl), CANCEL(old_tp), PLACE_SL(new_level), PLACE_TP(new_level)]`.
3. **FSM iterates actions** and executes via adapter (or delegates to ManageFlowFSM).
4. **FSM calls** `OrderGuardian.register_bracket_set()` with new order IDs.

---

### 4.4. DR/Restart: Duplicate Bracket Cleanup Not Automatic

**Current Rehydration Flow**:
1. `OrderGuardian.rehydrate_bracket_set_for_position()` → selects one bracket set (latest timestamp).
2. **Old brackets remain on exchange** (not cancelled).
3. Caller must explicitly call `ensure_single_bracket_set_for_position()` to cleanup.

**Gap**:
- ExecPosFSM does NOT call `ensure_single_bracket_set_for_position()` during startup.
- Watchdog eventually detects duplicates, but delay can be 30-60s.

**Impact**:
- Duplicate brackets remain active after restart until watchdog cycle.
- Risk: both old and new TP hit simultaneously → position flips unexpectedly.

**Proposed Solution**:
- BracketService `build_state()` method should:
  1. Call `rehydrate_bracket_set_for_position()` to get best bracket set.
  2. Automatically detect duplicates (compare open orders vs registered metadata).
  3. Return `BracketPlan` with `CANCEL` actions for extra brackets.
- FSM executes plan → duplicates cleaned immediately.

---

### 4.5. No XAI Why-Chain for Bracket Decisions

**Current Observability**:
- `bracket_aggregator.compute_aggregated_brackets()` accepts `why` parameter (≤80 chars).
- Watchdog emits `why` field in recommendations.
- OrderGuardian logs events with basic context.

**Gap**:
- No **structured why-chain** linking: position event → bracket recalc → order placement.
- No RID propagation from FSM → BracketService → Adapter.
- Logs scattered across multiple files (`aurora_core.log`, `domain_execution_management.log`, `order_guardian.log`).

**Impact**:
- Hard to debug bracket issues (no trace from fill event to bracket action).
- No audit trail for "why was this SL cancelled?"

**Proposed Solution** (BracketService):
- Every `BracketAction` has `why` field (≤80 chars) with structured format: `"recalc_scale_in|avg_entry_1.23→1.45"`.
- BracketService accepts `rid` parameter → propagates to all actions.
- Actions logged to `logs/bracket_service.log` with RID + parent_why.

---

## 5. Recommendations for BracketService Design

### 5.1. Core Responsibilities

1. **State Reconstruction**: `build_state(symbol, side)` → query position, open orders, guardian metadata → return `BracketState`.
2. **Invariant Checking**: `evaluate(state)` → detect violations → return `BracketPlan` with typed actions.
3. **Batch Processing**: `evaluate_all(positions, orders)` → iterate all `(symbol, side)` pairs → return `List[BracketPlan]`.
4. **No Side Effects**: Service only computes plans, caller (FSM) executes actions.

### 5.2. Contract Design Principles

- **Typed Actions**: Use `BracketAction` dataclass with `action_type: Literal["CANCEL", "PLACE_SL", "PLACE_TP", "ADJUST"]`.
- **XAI Why**: Every action has `why: str` (≤80 chars) explaining reason (scale-in, partial-close, orphan-cleanup, etc.).
- **RID Propagation**: Accept `rid: Optional[str]` in all methods → propagate to logs.
- **Idempotency**: Same state → same plan (pure function, no hidden state).
- **DR-Safe**: `build_state()` handles missing metadata (rehydrates from orders).

### 5.3. Integration with Existing Components

- **bracket_aggregator.py**: BracketService wraps `compute_aggregated_brackets()` for TP/SL level calculation.
- **OrderGuardian**: BracketService queries `get_active_bracket_set()` and recommends calls to `register_bracket_set()` / `clear_bracket_set_for_position()`.
- **AggOcoWatchdogService**: BracketService can **replace** watchdog for FSM integration (watchdog remains for background monitoring).
- **ManageFlowFSM**: FSM calls `BracketService.evaluate()` after scale-in/partial-close → executes plan → updates guardian.

### 5.4. Phased Rollout (EP-PORT-BRACKETS-S1 Scope)

**Phase 1 (this task)**:
- Define `BracketService` contract (types, methods, invariants).
- Implement core methods (`build_state`, `evaluate`, `evaluate_all`).
- Write unit tests (happy path, missing SL, orphan SL, too many SL, partial close).
- **No active wiring**: Service exists but NOT called by FSM (integration hooks only).

**Phase 2 (future task)**:
- Wire BracketService into ManageFlowFSM (replace manual recalc logic).
- Update ExecPosFSM to call `evaluate()` during DR/restart.
- Migrate watchdog auto-heal to use BracketService plans.

**Phase 3 (future task)**:
- Persistent state: Replace InMemoryStore with Redis for bracket metadata.
- Cross-symbol coordination: Prevent over-leveraged portfolio risk.
- Multi-leg brackets: Support trailing stops, conditional TP levels.

---

## 6. Success Criteria for EP-PORT-BRACKETS-S1

1. ✅ **EXEC_POS_BRACKETS_ANALYSIS.md** created (this document).
2. ✅ **EXEC_POS_BRACKETS_CONTRACT.md** created with typed API (next phase).
3. ✅ **bracket_service.py** implemented with core methods (next phase).
4. ✅ **test_bracket_service.py** covers all scenarios (next phase).
5. ✅ **EXEC_POS_V2_RUNTIME_SPEC.md** updated with BracketService integration points (next phase).
6. ✅ **EXEC_POS_BRACKETS_TODO_WIRING.md** created with future wiring plan (next phase).
7. ✅ **JOURNAL.md** updated with [EP-PORT-BRACKETS-S1] entry (final phase).

**Non-Goals** (out of scope):
- ❌ Active wiring into FSM (recommendations only, no live execution).
- ❌ Replace AggOcoWatchdogService (watchdog remains for background monitoring).
- ❌ Implement auto-heal (caller decides to execute actions).

---

## 7. References

**Source Documents**:
- `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py` (pure functional module)
- `docs/EXECUTION_POSITION_ORDER_GUARDIAN_CONTRACT.md` (OrderGuardian frozen contract v1.0)
- `apps/reference/domains/execution_position/shadow_execpos/watchdog.py` (AggOcoWatchdogService detect-only)
- `INVESTIGATION_AGGREGATED_OCO.md` (historical bugs in legacy recalc logic)
- `JOURNAL.md` (recalc_on_partial_close config changes)

**Related Tasks**:
- `EP-LEGACY-PURGE-S1` (completed: removed all legacy ExecPosFSM references)
- `EP-STAB-GUARDIAN-CLOSE-CLEANUP` (delegated DEC:CLOSE cleanup to OrderGuardian)
- `EP-PORT-BRACKETS-S1` (this task: design BracketService v1)

**Maintainer**: Execution Position Domain
**Review**: Architecture WG

---

**End of PHASE 0 Discovery – Ready for PHASE 1 Contract Design**
