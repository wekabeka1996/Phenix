# PLAN: Services & Core Domain Remediation
**Branch:** `backtest_1`
**Date:** 2026-02-24
**Status:** UPDATED — reflects actual codebase state after live investigation

> ⚠️ Original plan was written on stale assumptions. This revision supersedes it.

---

## STEP 1 — TRIAGE FINDINGS

> **CORRECTION (live file inspection, 2026-02-24):** The original triage below was written on stale assumptions. The migration is already complete. See corrected snapshot.

### 1.1 Codebase Snapshot (CORRECTED)

| File | Path | LOC | Actual Status |
|------|------|-----|---------------|
| `order_guardian.py` | `apps/reference/services/` | 19 | Shim only — re-exports from `execution_position` |
| `limit_order_monitor.py` | `apps/reference/services/` | 10 | Shim only — re-exports from `execution_position` |
| `ledger_store_adapter.py` | `apps/reference/services/` | 7 | Shim only — re-exports from `execution_position/infra` |
| `order_guardian.py` | `apps/reference/domains/execution_position/` | 1360 | ✅ CANONICAL implementation (SSOT) |
| `limit_order_monitor.py` | `apps/reference/domains/execution_position/` | 311 | ✅ Canonical, uses per-order timers (no polling) |
| `ledger_store_adapter.py` | `apps/reference/domains/execution_position/infra/` | 159 | ✅ Canonical, SQLite SSOT with soft-delete |
| `shared/types.py` | `apps/reference/shared/` | 33 | ✅ Correct — re-export facade |
| `core/types/regime_types.py` | `apps/reference/core/` | 57 | ✅ Correct — SSOT for regime types |

**All `services/` files are deprecation shims. No code to merge or move.**

---

### 1.2 OrderGuardian Line-by-Line Delta

The two `order_guardian.py` files are **NOT true duplicates**. They have distinct roles:

#### `services/order_guardian.py` (SSOT Implementation)
- Contains `AdapterProtocol`, `StoreProtocol`, `OrderInfo`, `InMemoryStore` — all data types
- Full `OrderGuardian` class: registration, bracket tracking, orphan cleanup, polling loop, metrics
- Has no config-parsing logic; accepts raw `store=` and `poll_interval_ms=` args
- **This is the real implementation. It is the SSOT.**

#### `domains/execution_position/order_guardian.py` (Delegation Wrapper)
- Imports `from apps.reference.services.order_guardian import OrderGuardian as ServicesGuardian`
- Does **not implement** any cleanup or registration logic
- Contains `_resolve_guardian_cfg()` — a factory that parses `AuroraConfig` to decide:
  - `unified=True` → instantiates `OrderLedger` + `LedgerStoreAdapter` → passes as `store=`
  - `unified=False` → passes `store=None` (falling back to `InMemoryStore` in services impl)
- Exposes full API via `__getattr__`-style delegation

**Merge Decision:** The domain wrapper's config-resolution factory (`_resolve_guardian_cfg`, `__init__`) must be pulled UP into the merged canonical file. The underlying logic stays unchanged. The wrapper is eliminated.

---

### 1.3 LedgerStoreAdapter Analysis

`services/ledger_store_adapter.py` implements `StoreProtocol` over `OrderLedger` (SQLite):

| Operation | Behaviour | Risk |
|-----------|-----------|------|
| `get("order:{id}")` | Reads from SQLite | ✅ Correct |
| `get("client:{id}")` | Reads from SQLite | ✅ Correct |
| `get("entry:{id}")` | Reads + reconstructs brackets | ✅ Correct |
| `put("order:{id}", meta)` | Writes to SQLite via `register_order()` | ⚠️ Always marks `status=ACTIVE`; never updates |
| `put("client:{id}", ...)` | **Silent no-op** | ⚠️ Client mappings not written |
| `put("entry:{id}", ...)` | **Silent no-op** | ✅ Acceptable — derived from order rows |
| `delete(key)` | **Silent no-op** | 🔴 **SPLIT-BRAIN GAP** — cancelled orders remain `ACTIVE` in SQLite forever |

**Split-Brain Risk:** When `unified=True`, the `LedgerStoreAdapter` is the sole store.
The `InMemoryStore` is NOT active in parallel — so classic split-brain (two live mirrors diverging) does **not exist** today.
However, the `delete()` no-op creates **stale ACTIVE records** that never get purged. This causes:
1. Disk growth (minor — SQLite, bounded by order volume)
2. `get("order:{id}")` returning stale metadata for cancelled/filled orders
3. `cleanup_orphans()` potentially re-acting on already-closed orders on restart

---

### 1.4 LimitOrderMonitor Polling Analysis

`_monitoring_loop()` (line 219) runs:
```python
while self._running:
    await asyncio.sleep(self._poll_interval_sec)   # blind N-second poll
    await self._check_expired_orders()             # scans ALL tracked orders
```

**Anti-pattern:** Every `poll_interval_sec` (default 5s), ALL orders are scanned. This is O(n) per tick and does not scale with order volume. More critically, it violates event-driven principles:
- An order placed with `timeout_sec=30` will be detected between 30–35 seconds late (up to +`poll_interval_sec` jitter).
- Cancellation on fill/cancel depends on external `unregister_order()` calls — no FSM integration.

**Event-Driven Alternative:** Use per-order `asyncio.create_task(asyncio.sleep(timeout))` tasks. Each task fires exactly at expiry, cancels itself when `unregister_order()` is called. Zero polling, zero jitter, O(1) per-order cost.

---

### 1.5 Import Blast Radius

Files that import directly from `apps.reference.services.*` (excluding `.trash/`):

| File | Import Target |
|------|--------------|
| `apps/reference/domains/execution_position/order_guardian.py` | `services.order_guardian`, `services.ledger_store_adapter` |
| `tests/units/test_order_guardian_emit.py` | `services.order_guardian` |
| `tests/order_guardian/test_no_adapter_logic_left.py` | `services.order_guardian` |
| `tests/order_guardian/test_cleanup_before_close_by_parent.py` | `services.order_guardian` |
| `tests/order_guardian/test_fsm_delegation.py` | `services.order_guardian` |
| `tests/order_guardian/test_register_and_link.py` | `services.order_guardian` |
| `tests/test_tpsl_placement.py` | `services.order_guardian` |
| `tests/test_order_guardian_grace_period.py` | `services.order_guardian` |
| `tests/integration/test_guardian_tidy_delivery.py` | `services.order_guardian` |
| `tools/diagnose_execution.py` | `services.order_guardian` |

**Total affected: 10 files** (excluding domain wrapper itself which will be replaced).

---

### 1.6 Type Unification Assessment

| Location | Contents | Status |
|----------|----------|--------|
| `apps/reference/shared/types.py` | Re-exports `Bar`, `NormalizedRejectReasons` | Correct facade pattern |
| `apps/reference/core/types/regime_types.py` | `RegimeLabel`, `ExecutionRegimeBucket`, `map_regime_to_bucket` | Correct SSOT |

These serve different purposes and do NOT need unification. The audit notes cognitive load from having both `shared/` and `core/types/` — but they are not redundant. `shared/` is for cross-domain type re-exports; `core/types/` is for fundamental domain-agnostic types.

**Decision:** No action required on type unification. The two locations are architecturally sound.

---

## STEP 2 — STRATEGIC REMEDIATION PLAN

### 2.1 Deduplication Strategy

**Winner:** `services/order_guardian.py` contains all the real logic and is the SSOT.

**Merge Steps:**
1. Create `domains/execution_position/order_guardian.py` as the **canonical merged file**:
   - Take the full `services/order_guardian.py` implementation verbatim
   - Merge in the `_resolve_guardian_cfg()` class method from the current domain wrapper
   - Merge in the config-aware `__init__` factory logic (ledger path resolution)
   - Keep `AdapterProtocol`, `StoreProtocol`, `OrderInfo`, `InMemoryStore` in the same file
   - Remove the delegation wrapper entirely — the merged class IS the implementation

2. Create `apps/reference/services/order_guardian.py` as a **deprecation shim**:
   ```python
   # DEPRECATED: Import from execution_position directly.
   from apps.reference.domains.execution_position.order_guardian import (
       OrderGuardian, InMemoryStore, AdapterProtocol, StoreProtocol, OrderInfo
   )
   __all__ = ["OrderGuardian", "InMemoryStore", "AdapterProtocol", "StoreProtocol", "OrderInfo"]
   ```
   This keeps all existing imports working with zero test changes.

3. After all imports are updated → delete the shim.

---

### 2.2 Domain Migration Steps

**Target directory layout after migration:**
```
apps/reference/domains/execution_position/
├── order_guardian.py          ← MERGED canonical impl (moved from services + wrapper merged in)
├── limit_order_monitor.py     ← MOVED from services/
├── infra/
│   ├── order_ledger.py        ← unchanged
│   └── ledger_store_adapter.py ← MOVED from services/
```

**Migration order** (dependency-safe):
1. `ledger_store_adapter.py` → `execution_position/infra/ledger_store_adapter.py`
   (no downstream deps except domain wrapper, which is being replaced)
2. Merge `order_guardian.py` into canonical domain file (absorbs ledger adapter import change)
3. `limit_order_monitor.py` → `execution_position/limit_order_monitor.py`
4. Add deprecation shims in `services/` (keeps tests green immediately)
5. Update all 10 direct import sites to new paths
6. Delete shims + `services/` directory

---

### 2.3 Split-Brain Mitigation

**Root cause:** `LedgerStoreAdapter.delete()` is a no-op. Cancelled/filled orders remain in SQLite with `status=ACTIVE`.

**Fix options:**

| Option | Description | Chosen? |
|--------|-------------|---------|
| A. Implement `delete()` → mark status=CANCELLED in ledger | Correct semantic — soft delete | ✅ YES |
| B. Drop in-memory mirror (it's already not active when unified=True) | N/A — not the issue | — |
| C. Add TTL via `OrderLedger.cleanup_old_records()` | Already exists in ledger | Complementary |

**Implementation of Option A:**
```python
def delete(self, key: str) -> None:
    if key.startswith("order:"):
        order_id = key.split(":", 1)[1]
        # Soft-delete: mark as CANCELLED to prevent stale ACTIVE reads
        self.ledger.update_order_status(order_id, OrderStatus.CANCELLED)
```

This requires verifying `update_order_status()` exists on `OrderLedger` (it does — line ~250 of `infra/order_ledger.py` based on exploration).

**Also:** Document in `LedgerStoreAdapter` that `client:` and `entry:` key writes are intentional no-ops (derived from order rows on read). This is safe — it's currently ambiguous and looks like neglected functionality.

---

### 2.4 Polling → Event-Driven Refactor for LimitOrderMonitor

**Current (polling):**
```python
while self._running:
    await asyncio.sleep(self._poll_interval_sec)
    await self._check_expired_orders()
```

**Target (per-order timer tasks):**
```python
def register_limit_order(self, order_id, ..., timeout_sec):
    state = LimitOrderState(...)
    self._active_orders[order_id] = state
    # Fire-and-forget timer task for this specific order
    task = asyncio.create_task(self._expire_after(order_id, timeout_sec))
    self._timer_tasks[order_id] = task

async def _expire_after(self, order_id: str, timeout_sec: int):
    await asyncio.sleep(timeout_sec)
    state = self._active_orders.get(order_id)
    if state:  # still active (not filled/cancelled)
        await self._cancel_expired_order(order_id, state, time.time())

def unregister_order(self, order_id, reason):
    # Cancel the timer task → no spurious cancellation
    task = self._timer_tasks.pop(order_id, None)
    if task and not task.done():
        task.cancel()
    self._active_orders.pop(order_id, None)
    ...
```

**Benefits:**
- Exact expiry timing (no +poll_interval jitter)
- O(1) per-order (no scan loop)
- Naturally event-driven: `unregister_order()` is the cancellation signal
- `start()`/`stop()` simplify to managing `_timer_tasks` set

**Scope:** This is a behavioral refactor. It must be gated by tests passing before and after.
The `_monitoring_loop` polling remains as a **fallback** until tests confirm the timer approach is stable, then removed.

---

### 2.5 Type Unification

**Decision:** No changes needed.

- `shared/types.py` = cross-domain re-export facade ✅
- `core/types/regime_types.py` = fundamental execution types SSOT ✅

These serve different layers and are not redundant. Merging them would harm, not help, separation of concerns.

---

## EXECUTION SEQUENCE (Ordered, Dependency-Safe)

```
1. Create execution_position/infra/ledger_store_adapter.py  (move)
2. Merge order_guardian.py canonical into execution_position/  (merge)
3. Move limit_order_monitor.py into execution_position/  (move)
4. Add deprecation shims in services/ (3 files)          (backward compat)
5. RUN PYTEST → confirm green                             (gate)
6. Update 10 import sites to new canonical paths          (fix imports)
7. RUN PYTEST → confirm green                             (gate)
8. Fix LedgerStoreAdapter.delete() split-brain gap        (bug fix)
9. RUN PYTEST → confirm green                             (gate)
10. Refactor LimitOrderMonitor to per-order timers        (event-driven)
11. RUN PYTEST → confirm green                            (gate)
12. Delete services/ directory                            (cleanup)
13. RUN PYTEST → confirm green (final)                    (gate)
14. Update PROGRESS_LOG.md                                (bookkeeping)
```

---

## DEFINITION OF DONE CHECKLIST

- [ ] `apps/reference/services/` directory deleted
- [ ] Only ONE `order_guardian.py` in repository (at `execution_position/`)
- [ ] `LedgerStoreAdapter.delete()` marks orders as CANCELLED (not no-op)
- [ ] `LimitOrderMonitor` uses per-order timer tasks, not blind polling loop
- [ ] `pytest tests/` green (≥ current baseline of 716 passed)
- [ ] `PROGRESS_LOG.md` updated

---

## RISK REGISTER

| Risk | Probability | Mitigation |
|------|-------------|------------|
| Test import breakage during shim period | Low | Shims re-export all public names |
| `update_order_status()` missing from OrderLedger | Low | Verify before writing fix |
| Timer task per-order approach causes event loop pressure | Low | asyncio.create_task overhead is negligible at order volumes |
| `_resolve_guardian_cfg` merge introduces MagicMock test regression | Medium | Domain wrapper already has guard against this; preserve logic exactly |
