# Package 6C — Forensic Pre-Implementation Audit
**Date:** 2026-04-19  
**Status:** AUDIT ONLY — NO CODE CHANGES  
**Scope:** Startup Reconstruction / Guardian Reconcile extraction boundary

---

## Problem Framing

Packages 6A and 6B are complete:
- **6A** (`startup_truth_orchestrator.py`): owns artifact read/compare/persist — no runtime mutation.
- **6B** (`authoritative_restore_apply.py`): owns mutating apply of parsed records into manage_flow/close_flow/bracket state.

The remaining question: should the `_startup_order_guardian_reconcile` / `_startup_reconstruct_runtime_bracket_truth` / `restore_startup_from_snapshot_positions` contour be extracted into a new peer module, and if so what exactly moves?

---

## FACTS

Proven by direct code inspection. Source lines cited.

### F-1: The exact three methods in scope

| Method | Location | Lines | Size |
|--------|----------|-------|------|
| `_startup_order_guardian_reconcile` | `fsm.py` | L2772–2939 | 168L |
| `_startup_reconstruct_runtime_bracket_truth` | `fsm.py` | L1225–1426 | 202L |
| `restore_startup_from_snapshot_positions` | `fsm.py` | L2114–2134 | 21L |

### F-2: Caller map for each method

| Method | Callers | File |
|--------|---------|------|
| `_startup_order_guardian_reconcile` | `async_scheduling.py:94` via `_schedule_guardian_start` | domain-internal |
| `_startup_reconstruct_runtime_bracket_truth` | `fsm.py:2886` inside `_startup_order_guardian_reconcile` only | domain-internal |
| `restore_startup_from_snapshot_positions` | `main.py:605` (composition root, DR hydration path) | composition root |

`_startup_reconstruct_runtime_bracket_truth` is **called exclusively** from within `_startup_order_guardian_reconcile`. It has no independent caller.

### F-3: `_startup_order_guardian_reconcile` dependency map (proven by AST)

All `self.*` call sites inside `_startup_order_guardian_reconcile`:
```
self._collect_guardian_symbols()                              ← ConfigResolverMixin (already extracted)
self._startup_reconstruct_runtime_bracket_truth(fresh_orders) ← 6C core (co-located)
self._startup_truth_orchestrator._append_startup_truth_artifact_record(...)  ← 6A write sink
self._startup_truth_orchestrator._execution_truth_cache_status()             ← 6A read
self._startup_truth_orchestrator._finalize_restore_authoritative_status(...) ← 6A finalize
self._startup_truth_orchestrator._persist_restore_artifact_snapshot(...)     ← 6A persist
self._startup_truth_orchestrator._run_restore_artifact_authoritative_read()  ← 6A read → triggers 6B apply via FSM delegator
self._startup_truth_orchestrator._run_restore_artifact_dark_read_comparison() ← 6A dark-read
self.adapter.get_open_orders()  ← REST call (x2)
self.adapter.get_open_positions() ← REST call
self.order_guardian.cleanup_orphans() ← OrderGuardian library call
self.order_guardian.link_existing_from_rest(symbol) ← OrderGuardian library call
```

### F-4: `_startup_reconstruct_runtime_bracket_truth` dependency map (proven by AST)

```
self._clear_symbol_brackets(symbol_key)      ← generic shell helper (fsm.py L1052)
self._emit_observability_event(...)          ← generic shell helper (fsm.py L2721)
self._manage_state_value(manage_flow)        ← generic shell helper (fsm.py L935)
self._manage_truth_source_for(symbol_key)    ← generic shell helper (fsm.py L963)
self._runtime_order_index()                  ← generic shell accessor (fsm.py L1149)
self._set_symbol_brackets_snapshot(...)      ← generic shell helper (fsm.py L1023)
self._startup_truth_orchestrator._append_restart_truth_record(...)  ← 6A write sink
self._symbol_bracket_truth_source_for(...)   ← generic shell helper (fsm.py L1138)
self.manage_flows.get(symbol_key)            ← FSM live state dict (direct)
self.order_guardian.resolve_terminal_bracket_context(...)  ← OrderGuardian library call
```

### F-5: `restore_startup_from_snapshot_positions` dependency map

```
self._startup_truth_orchestrator._authoritative_restore_enabled() ← 6A gate check
self.hydrate(data)                                                 ← generic FSM hydrate
```
This is the **only** method that is a guard gate before heuristic hydration; it DOES NOT drive guardian reconcile.

### F-6: Generic helpers that are used OUTSIDE 6C scope

| Helper | Other callers beyond 6C scope |
|--------|-------------------------------|
| `_clear_symbol_brackets` | `authoritative_restore_apply.py`, `fsm.py` (runtime event paths) |
| `_set_symbol_brackets_snapshot` | `fsm.py:1346` only (inside `_startup_reconstruct_runtime_bracket_truth`) |
| `_runtime_order_index` | `close_executor.py:86,192,1208` — runtime use |
| `_manage_state_value` | `fsm.py` runtime paths |
| `_manage_truth_source_for` | `fsm.py` runtime paths, `startup_truth_orchestrator._append_restart_truth_record` |
| `_emit_observability_event` | many runtime callers |
| `_symbol_bracket_truth_source_for` | multiple callers |

**FACT:** `_set_symbol_brackets_snapshot` is called ONLY inside `_startup_reconstruct_runtime_bracket_truth`. All other helpers are used by runtime paths.

### F-7: Scheduling chain (proven by code)

```
main.py:807 → execution_position.start_order_guardian()
  → fsm.py:1958 → self._schedule_guardian_start()
  → async_scheduling.py:94 → self._submit_async(self._startup_order_guardian_reconcile(), loop)
```

`_startup_order_guardian_reconcile` executes asynchronously on the guardian loop. It is not called from any synchronous runtime path.

### F-8: Exact ordering inside `_startup_order_guardian_reconcile`

```
Line 2806: 6A → _run_restore_artifact_authoritative_read()
             ↳ internally calls FSM._apply_authoritative_restore_record()
             ↳ which delegates to 6B → AuthoritativeRestoreApply.apply_record()
Line 2816: REST → adapter.get_open_positions()
Line 2834: REST → adapter.get_open_orders() [pre-cleanup]
Line 2849: CONFIG → _collect_guardian_symbols()
Line 2857: GUARDIAN → order_guardian.link_existing_from_rest(symbol) [loop]
Line 2869: GUARDIAN → order_guardian.cleanup_orphans()
Line 2872: REST → adapter.get_open_orders() [post-cleanup, fresh]
Line 2886: 6C → _startup_reconstruct_runtime_bracket_truth(fresh_orders)
Line 2888: 6A → _finalize_restore_authoritative_status(...)
Line 2893: 6A → _run_restore_artifact_dark_read_comparison()
Line 2895: 6A → _persist_restore_artifact_snapshot(...)
Line 2904: 6A → _append_startup_truth_artifact_record(...) [finally block]
```

### F-9: `_note_unresolved` is a LOCAL nested function

```python
def _note_unresolved(symbol_key: str, reason: str) -> None:
    unresolved_reasons.setdefault(symbol_key, []).append(reason)
```
Defined at `fsm.py:1247` inside `_startup_reconstruct_runtime_bracket_truth`. It is a closure over local `unresolved_reasons` dict. Not a method — it moves with the containing method if extracted.

### F-10: `start_order_guardian` is the FSM public entry point for all guardian startup

```python
async def start_order_guardian(self):  # fsm.py:1948
    self._startup_truth_orchestrator._schedule_restore_artifact_loop()
    if not self.order_guardian: return
    self._schedule_guardian_start()
    self._schedule_fsm_cleanup_loop()
    self._bracket_health.schedule_bracket_health_check()
```
This is an FSM-level operation orchestrator. It delegates to already-extracted collaborators. It coordinates multiple startup systems and is architecturally in the right place (FSM).

### F-11: `restore_startup_from_snapshot_positions` role

Called from `main.py:605` in the DR (snapshot restore) path, **before** `start_order_guardian`. It is a guard + heuristic hydration path; it checks `_authoritative_restore_enabled()` and exits early if authoritative mode is on.  
The real runtime truth is written by 6B apply (authoritative) or by this method's `self.hydrate()` (legacy heuristic).  
This is a **standalone startup entry point** with a single external caller. It is not subordinate to `_startup_order_guardian_reconcile`.

### F-12: Boundary between OrderGuardian and FSM

`OrderGuardian` owns:
- Order lifecycle store (WAL-based)
- `link_existing_from_rest(symbol)` — REST-based order linking
- `cleanup_orphans()` — orphan detection and cancellation
- `resolve_terminal_bracket_context(...)` — bracket role resolution from its store

FSM 6C owns:
- Orchestration of the above in startup sequence
- Application of guardian proof to `_symbol_brackets` and `order_index`
- Bracket truth reconstruction decision logic

`BracketOwnership` and `BracketHealth` are **not involved in reconstruction**.  
`BracketOwnership` owns bracket strategy assignment (runtime, post-open).  
`BracketHealth` owns periodic health checks (scheduled loop).

### F-13: `_collect_guardian_symbols` is in `ConfigResolverMixin` (already extracted to `config_resolver.py`)

It is not an FSM method — it's a mixin. The 6C module can call `self._fsm._collect_guardian_symbols()` safely through the back-ref.

### F-14: `_set_symbol_brackets_snapshot` is only called by `_startup_reconstruct_runtime_bracket_truth`

However, it also mutates `self._symbol_brackets` and `self._symbol_bracket_truth_source` which are FSM live state dicts. It must remain in FSM as a sanctioned shell helper; 6C calls it through the back-ref.

### F-15: Overwrite proof — 6C intentionally overwrites 6B bracket state

From `authoritative_restore_apply.py` comment (Package 6B):
> "6C (_startup_reconstruct_runtime_bracket_truth) will overwrite bracket state with fresher guardian-proven bracket state."

And from `_startup_reconstruct_runtime_bracket_truth` (FSM L1346):
```python
self._set_symbol_brackets_snapshot(
    symbol_key, sl_order_id=sl_order_id, tp_order_id=tp_order_id,
    truth_source=TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
)
```
6B clears brackets per-symbol (writes `BRACKET_STATE_UNKNOWN`). 6C then writes `TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN` from live exchange proof. This is intentional and correct: guardian proof is fresher than stored restore artifact.

---

## INFERENCES

- The `_startup_order_guardian_reconcile` method is a **startup orchestration shell** — it sequences 6A read, REST calls, guardian link/cleanup, 6C reconstruction, 6A finalize, 6A dark-read, 6A persist, and 6A observability append. It is NOT purely a 6C method.
- `_startup_reconstruct_runtime_bracket_truth` is the genuine **6C core** — it takes fresh REST orders and guardian proof and writes bracket truth into FSM state. This is the only method that must move.
- If extracted, `_startup_order_guardian_reconcile` becomes a **delegating shell** in FSM (identical pattern to 6B's thin delegator), not a stub-free move.
- `restore_startup_from_snapshot_positions` is a **legacy heuristic gate**, not a 6C responsibility. It is correctly located in FSM as an entry point called from the composition root.

---

## ASSUMPTIONS

- The back-ref pattern (6C module holds `self._fsm: ExecPosFSM`) continues as established in 6A/6B. No alternative wiring pattern assumed.
- `_collect_guardian_symbols` on `ConfigResolverMixin` is accessible via the back-ref (`self._fsm._collect_guardian_symbols()`).
- Tests that call `_startup_order_guardian_reconcile` on an FSM instance will continue to work through the FSM delegator after extraction, as proven in 6B.

---

## UNKNOWNS

- Whether `_set_symbol_brackets_snapshot` is safe to keep as a pure FSM shell (no behavioral risk confirmed). A future audit could test whether it has concurrent writer overlap with runtime bracket placement.
- Whether `start_order_guardian` itself should become a 6C call target in a future 6C+ refactor. Currently it is the correct FSM entry point.

---

## Current Package 6C Contour Map

```
6C owns:
  _startup_reconstruct_runtime_bracket_truth (L1225-1426, 202L)
    ↳ _note_unresolved [nested closure, moves with parent]
    
6C shell / orchestration coordination (stays in FSM as delegator):
  _startup_order_guardian_reconcile (L2772-2939, 168L)
    — calls 6A, REST, guardian library, 6C core, 6A finalize/persist
    — too coupled to FSM state to extract cleanly without introducing circular coordination
    
6C-adjacent but NOT 6C (stays in FSM, different role):
  restore_startup_from_snapshot_positions (L2114-2134, 21L)
    — heuristic gate, called from main.py composition root
    — NOT a guardian reconcile function
    
Generic helpers (stays in FSM, multi-owner):
  _set_symbol_brackets_snapshot  — only caller is 6C core, but FSM state mutation
  _runtime_order_index           — used by close_executor.py at runtime
  _clear_symbol_brackets         — used by 6B and runtime event paths
  _manage_state_value            — runtime multi-caller
  _manage_truth_source_for       — runtime multi-caller
  _emit_observability_event      — runtime multi-caller
  _symbol_bracket_truth_source_for — runtime multi-caller
```

---

## What `fsm.py` Actually Owns for This Contour

| Method | Classification | Action |
|--------|---------------|--------|
| `_startup_order_guardian_reconcile` | **6C startup orchestration shell** | Stays as **thin delegator** after 6C extraction (calls `self._startup_reconstruction.reconcile()`) |
| `_startup_reconstruct_runtime_bracket_truth` | **6C core** | **Moves** to `startup_reconstruction.py` |
| `restore_startup_from_snapshot_positions` | **Heuristic hydration gate** | Stays in FSM |
| `start_order_guardian` | **FSM startup entry point orchestrator** | Stays in FSM |
| `_set_symbol_brackets_snapshot` | **Generic shell helper** | Stays in FSM |
| `_runtime_order_index` | **Generic shell accessor** (runtime dual-use) | Stays in FSM |
| `_note_unresolved` | **Nested closure** | Moves with `_startup_reconstruct_runtime_bracket_truth` |

---

## What `order_guardian.py` Actually Owns

`OrderGuardian` owns these operations which 6C **consumes, never owns**:
- `link_existing_from_rest(symbol)` — links live REST orders into guardian store
- `cleanup_orphans()` — cancels orphaned tracked orders
- `resolve_terminal_bracket_context(client_order_id, exchange_order_id, symbol)` — resolves bracket role from guardian store

`_startup_relink_known_symbols()` in `order_guardian.py:597` is an internal guardian method that does its own startup link; this is **not** the same as the FSM-driven link in 6C. The FSM 6C explicitly calls `link_existing_from_rest` per symbol — this is intentional (FSM-driven vs guardian-driven startup variants).

---

## What `startup_truth_orchestrator.py` (6A) Still Owns

6A provides these services to 6C (read-only from 6C's perspective):
- `_run_restore_artifact_authoritative_read()` — reads, parses, applies 6B → returns `ExecutionPositionRestoreAuthoritativeStatus`
- `_finalize_restore_authoritative_status(...)` — post-reconcile enrichment
- `_run_restore_artifact_dark_read_comparison()` — dark-read comparison
- `_persist_restore_artifact_snapshot(...)` — final artifact write
- `_append_startup_truth_artifact_record(...)` — observability record write (finally block)
- `_append_restart_truth_record(...)` — per-symbol reconstruction truth record (called by 6C core)
- `_authoritative_restore_enabled()` — gate check

6A does **not** own anything that 6C should absorb. The 6A seam is stable.

---

## What `authoritative_restore_apply.py` (6B) Still Owns

6B runs **inside** 6A's `_run_restore_artifact_authoritative_read()` call. It is not directly called by 6C. The 6A→6B seam via the FSM delegator is stable.

6C reads 6B's effects (bracket state, manage/close flow state) as precondition truths. 6C then intentionally overwrites bracket truth with fresher guardian proof.

---

## Duplicate / Near-Duplicate / Adjacency Findings

1. **`order_guardian._startup_relink_known_symbols`** (L597) vs FSM-driven `link_existing_from_rest` per symbol: These are architecturally distinct. The guardian's internal method relies on `_iter_symbols_for_poll` (config-driven); the FSM 6C drives `link_existing_from_rest` per symbol after merging positions + orders + guardian + authoritative symbol sets. No duplication risk, different symbol set source.

2. **`_startup_reconstruct_runtime_bracket_truth` and `_resolve_restore_artifact_bracket_snapshot`**: These are NOT duplicates. `_resolve_restore_artifact_bracket_snapshot` (L1155) builds a snapshot for writing the restore artifact (6A's preserve path). `_startup_reconstruct_runtime_bracket_truth` applies guardian-proven bracket truth to live state. Different lifecycle phases, different truth sources.

3. No existing file partially owns the 6C bracket reconstruction contour strongly enough to make a new module redundant. `bracket_health.py` is a periodic health loop, not a startup reconstructor.

---

## Boundary Verdict

> **Package 6C is a genuinely separate bounded contour. It should proceed as `startup_reconstruction.py`.**

Evidence:
- `_startup_reconstruct_runtime_bracket_truth` is 202 lines with a specific and narrow purpose: take exchange-proven open orders, resolve bracket roles via guardian, write reconstructed bracket truth into FSM state.
- It is NOT a generic helper — it is only called once in the startup sequence.
- It produces `TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN`, a defined sentinel.
- The back-ref pattern is established and proven to work (6A, 6B both use it).
- The separation makes the "overwrite contract" explicit: 6B writes restore artifact truth → 6C overwrites with guardian-proven truth.

**HOWEVER: `_startup_order_guardian_reconcile` must NOT move wholesale.**

`_startup_order_guardian_reconcile` is a startup orchestration shell that coordinates:
1. 6A read (→ 6B apply)
2. REST adapter calls (not 6C's to own)
3. Guardian library calls
4. 6C reconstruction
5. 6A finalize + dark-read + persist
6. 6A observability append

It is architecturally too coupled to the full startup sequence. Moving it wholesale would require the new module to import 6A, REST adapter, guardian, and FSM shell helpers — creating a broader circular dependency than the established pattern.

**Correct implementation:**
- Extract `_startup_reconstruct_runtime_bracket_truth` → `StartupReconstruction.reconstruct(open_orders)`
- Keep `_startup_order_guardian_reconcile` in FSM as a **thin delegating shell** that:
  - calls `self._startup_truth_orchestrator._run_restore_artifact_authoritative_read()` (6A)
  - calls adapter and guardian directly (FSM adapter/guardian ownership is appropriate here)
  - calls `self._startup_reconstruction.reconstruct(fresh_orders)` (6C)
  - calls 6A finalize/persist/observability

This mirrors exactly what was done for 6B (`_apply_authoritative_restore_record` delegator).

---

## Exact Method-Level Recommendation

### Methods that MOVE to `startup_reconstruction.py`

| Method | New method name | Notes |
|--------|----------------|-------|
| `_startup_reconstruct_runtime_bracket_truth` | `reconstruct(open_orders)` or `reconstruct_bracket_truth(open_orders)` | Primary 6C core |
| `_note_unresolved` (inner function) | Stays nested inside `reconstruct()` | Closure over local dicts |

### Methods that stay in `fsm.py` as delegators / shells

| Method | Action | Reason |
|--------|--------|--------|
| `_startup_order_guardian_reconcile` | **Stays** but slim its body to a delegating shell | Too coupled to 6A, REST, guardian |
| `restore_startup_from_snapshot_positions` | **Stays** | Heuristic gate, composition root entry |
| `start_order_guardian` | **Stays** | FSM startup orchestration entry |

### Methods that stay in `fsm.py` as generic helpers

| Method | Reason |
|--------|--------|
| `_set_symbol_brackets_snapshot` | FSM state mutation, only 6C calls it but semantically FSM shell |
| `_runtime_order_index` | Dual-use runtime (close_executor at runtime) |
| All other generic shell helpers | Multi-owner runtime callers |

---

## What Must Explicitly NOT Move in Package 6C

| Method | Reason must not move |
|--------|---------------------|
| `_startup_order_guardian_reconcile` | Couples 6A, REST, guardian, config — not a pure 6C function |
| `restore_startup_from_snapshot_positions` | External caller in `main.py`; heuristic gate, not reconcile |
| `start_order_guardian` | FSM public startup entry point |
| `_apply_authoritative_local_close_reset` | Runtime dual-use (event_handlers + FSM runtime) |
| `_set_symbol_brackets_snapshot` | FSM live-state mutation, multi-context semantics |
| `_runtime_order_index` | Runtime dual-use (close_executor) |
| `_clear_symbol_brackets` | Runtime multi-owner (6B, event paths) |
| `_resolve_restore_artifact_bracket_snapshot` | 6A artifact preserve path, NOT reconstruction |

---

## Naming / Placement Verdict

### Evaluated options

| Candidate name | Assessment |
|---------------|------------|
| `startup_reconstruction.py` | ✅ **Best** — names the bounded act of bracket reconstruction from guardian proof at startup |
| `startup_guardian_reconcile.py` | ❌ False — "guardian reconcile" is OrderGuardian's job; FSM 6C uses guardian as a proof source |
| `startup_truth_reconstruction.py` | ⚠️ Acceptable but redundant — `startup_truth_orchestrator` already has "truth"; risk of confusion |
| `guardian_bracket_reconstruction.py` | ❌ Too broad — implies ownership of guardian logic |

**Verdict:** `startup_reconstruction.py` in `apps/reference/domains/execution_position/`

### Class name: `StartupReconstruction`

### True future neighbors of 6C
- `startup_truth_orchestrator.py` (6A) — direct upstream
- `authoritative_restore_apply.py` (6B) — upstream truth writer
- `order_guardian.py` — proof source (library consumer)
- `bracket_health.py` (Package 5) — peer periodic maintainer

### False neighbors
- `bracket_ownership.py` — bracket strategy assignment (runtime, not startup)
- `fill_ingress_coordinator.py` — runtime fill ingress (Package 4)

---

## Ordering and Overwrite Risk Analysis

### Exact ordering inside `_startup_order_guardian_reconcile` (enforced today):

```
Step 1: 6A read  → _run_restore_artifact_authoritative_read()
  → internally: 6B apply → sets manage_flow.state, close_flow.state, clears _symbol_brackets
  
Step 2: REST API → get_open_positions() + get_open_orders() [pre-cleanup]

Step 3: GUARDIAN → link_existing_from_rest(symbol) [per symbol]
  → Guardian store now has fresh order mappings

Step 4: GUARDIAN → cleanup_orphans()
  → Guardian store is clean

Step 5: REST API → get_open_orders() [fresh, post-cleanup]

Step 6: 6C → _startup_reconstruct_runtime_bracket_truth(fresh_orders)
  → reads order_guardian.resolve_terminal_bracket_context per order
  → writes _set_symbol_brackets_snapshot (overwrites 6B's UNKNOWN with GUARDIAN_RECONSTRUCTED)
  → registers guardian-proven orders into order_index

Step 7: 6A → _finalize_restore_authoritative_status(...)
Step 8: 6A → _run_restore_artifact_dark_read_comparison()
Step 9: 6A → _persist_restore_artifact_snapshot(...)
Step 10: 6A → _append_startup_truth_artifact_record(...) [finally]
```

**Ordering invariant:** 6A must run before 6C (6A populates manage_flow truth sources that 6C reads via `_manage_truth_source_for`). Guardian link must run before 6C (6C reads guardian store via `resolve_terminal_bracket_context`). 6C must run before 6A finalize (finalize reports on reconstruction results).

### Which 6C writes intentionally overwrite 6B writes:

6B writes to `_symbol_brackets[symbol]` → clears to UNKNOWN.  
6C writes `_set_symbol_brackets_snapshot` → sets SL/TP order IDs with `TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN`.  
This is the intentional freshness upgrade: guardian-proven > artifact-stored.

### Which parts depend on guardian proof being fresher than artifact truth:

The entire `resolve_terminal_bracket_context` path (F-4 above) depends on guardian's store having been freshly linked (Step 3). If guardian is called before `link_existing_from_rest`, the store will be empty and all bracket reconstruction will fall into `unresolved_reasons`. This is the highest-risk ordering constraint.

---

## Highest-Risk Failure Modes

| Risk | Mechanism | Severity |
|------|-----------|----------|
| **Guardian store empty during reconstruction** | If `link_existing_from_rest` is skipped or fails silently for all symbols, `resolve_terminal_bracket_context` returns `None` for all orders → all brackets land in UNRESOLVED → runtime cannot place brackets | **CRITICAL** |
| **6B bracket clear not running before 6C** | If 6C runs without 6B having cleared brackets first, stale restored brackets survive alongside guardian-proven brackets → duplicate bracket truth | **HIGH** |
| **6C reconstructing against pre-cleanup guardian data** | If 6C runs before `cleanup_orphans()`, orphaned brackets could be reconstructed as active → FSM believes brackets exist that have been cancelled | **HIGH** |
| **Reconstruct after finalize** | If `_finalize_restore_authoritative_status` runs before 6C, the finalize result won't include reconstruction evidence → observability gap (not a runtime mutation error) | **MEDIUM** |
| **`_note_unresolved` scoping break** | If `_startup_reconstruct_runtime_bracket_truth` is moved to a new class, the nested `_note_unresolved` function is fine (moves with it). Only risk: if someone accidentally promoted it to a class method and broke the closure | **LOW (implementation discipline)** |
| **Double `link_existing_from_rest` call** | Guardian's internal `_startup_relink_known_symbols` and FSM's per-symbol loop both call `link_existing_from_rest`. Currently these are on separate code paths (guardian start vs FSM reconcile). If ever unified, the bridge logic would need deduplication guard | **LOW (future)** |

---

## Package 6C Readiness Verdict

> **READY for implementation.**

### Preconditions satisfied:
- ✅ 6A and 6B are complete and validated.
- ✅ The 6A→6B seam is stable (FSM delegator pattern).
- ✅ The `_startup_reconstruct_runtime_bracket_truth` body is self-contained enough to move: its only non-generic external dependencies are `order_guardian.resolve_terminal_bracket_context` (library call) and `_startup_truth_orchestrator._append_restart_truth_record` (6A write sink via back-ref back to FSM).
- ✅ The back-ref pattern is established and test-proven.
- ✅ No existing file partially owns this contour.

### Narrow preconditions before 6C coding starts:

1. Confirm that `_set_symbol_brackets_snapshot` remains in FSM (NOT moved to 6C). 6C calls it via back-ref.
2. Confirm that `_startup_order_guardian_reconcile` becomes a thin delegating shell (exactly like 6B's delegator).
3. Confirm that `restore_startup_from_snapshot_positions` does NOT move.

---

## Code Paths / Tests That Must Be Validated in 6C

### Existing tests to run (must all pass after 6C):
```
tests/domains/execution_position/test_restart_runtime_truth_reconstruction.py  (3 tests)
tests/domains/execution_position/test_execution_restore_authoritative_read.py  (48 tests)
tests/domains/execution_position/test_execution_restore_dark_read.py
tests/domains/execution_position/test_execution_restore_artifact_writer.py
```

### New direct unit tests required for `StartupReconstruction.reconstruct()`:
```
test_startup_reconstruction.py
```

Required test cases:
1. `reconstruct()` returns `symbols_reconstructed == 0` when `order_guardian is None`.
2. `reconstruct()` skips orders with missing symbol or exchange_order_id.
3. `reconstruct()` skips orders with unsupported role (not SL/TP/TP1/TP2).
4. `reconstruct()` correctly sets SL and TP bracket for a symbol with both roles.
5. `reconstruct()` marks symbol unresolved when bracket role duplicates detected.
6. `_set_symbol_brackets_snapshot` called with `TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN` for resolved symbol.
7. `_clear_symbol_brackets` called for unresolved symbol.
8. `order_index.register_bracket_child` called for guardian-proven bracket not in order_index.
9. `_startup_truth_orchestrator._append_restart_truth_record` called with correct event_type for each path.
10. `_emit_observability_event` called once with reconstruction summary.
11. Returns correct `{"summary": {...}, "records": [...]}` dict schema.
12. `manage_flow.set_bracket_ids` called only when manage_flow exists and is not FLAT.

---

## Final Recommendation

| Decision | Verdict |
|----------|---------|
| Extract `_startup_reconstruct_runtime_bracket_truth` to new module | ✅ YES |
| New module name | `startup_reconstruction.py` |
| New class name | `StartupReconstruction` |
| New entry method name | `reconstruct(open_orders)` |
| `_startup_order_guardian_reconcile` moves | ❌ NO — stays as thin delegating shell in FSM |
| `restore_startup_from_snapshot_positions` moves | ❌ NO — stays in FSM |
| `start_order_guardian` moves | ❌ NO — stays in FSM |
| `_set_symbol_brackets_snapshot` moves | ❌ NO — FSM shell helper |
| `_runtime_order_index` moves | ❌ NO — runtime dual-use |
| Package 6C ready | ✅ YES — proceed after audit is accepted |

**FSM delegator for 6C:**
```python
def _startup_reconstruct_runtime_bracket_truth(self, open_orders):
    """Thin delegator — routes to StartupReconstruction (Package 6C owner)."""
    return self._startup_reconstruction.reconstruct(open_orders)
```

**`__init__` wiring:**
```python
self._startup_reconstruction = StartupReconstruction(self)  # Package 6C
```
