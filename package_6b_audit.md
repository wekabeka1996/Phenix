# Package 6B Audit — Forensic Pre-Implementation Report
# Date: 2026-04-19 | Status: AUDIT ONLY | NO CODE CHANGES

---

## Problem Framing

Package 6B is defined in the roadmap as the *mutating authoritative apply owner* — the contour
that takes a parsed `ExecutionPositionRestoreLifecycleRecord` from 6A and writes it into live
FSM state (ManageFlow, CloseFlow, bracket truth, manage truth source). The 0R package explicitly
documented the temporary 6A→6B seam. This audit determines the exact boundary, whether a
standalone module is justified, what must move, what must not, and what implementation readiness
looks like.

---

## FACTS

### F1 — Methods currently in `fsm.py` with restore/truth/apply signatures

| Method | Lines | Nature |
|--------|-------|--------|
| `_restore_artifact_mode` | L959–965 | Config gate (mode reader) |
| `_manage_truth_source_for` | L969–978 | Truth source reader |
| `_set_manage_truth_source` | L980–987 | Truth source mutator |
| `_clear_manage_truth_source` | L989–993 | Truth source mutator |
| `_apply_authoritative_local_close_reset` | L1065–1142 | **Non-startup mutator used at runtime too** |
| `_symbol_bracket_truth_source_for` | L1144–1153 | Bracket truth source reader |
| `_resolve_restore_artifact_bracket_snapshot` | L1161–1215 | Read-only snapshot builder |
| `_startup_reconstruct_runtime_bracket_truth` | L1231–1432 | **6C** — guardian order index reconstruction |
| `_apply_authoritative_restore_record` | L1500–1601 | **6B core mutator** |
| `_persist_restore_artifact_snapshot` (delegator) | L2069–2083 | FSM-level delegator → 6A |
| `restore_startup_from_snapshot_positions` | L2210–2230 | **6C** — heuristic hydrate entry point |
| `_startup_order_guardian_reconcile` | L2868–3032 | **6C** — orchestrates full startup sequence |

### F2 — What `_apply_authoritative_restore_record` (L1500–1601) actually mutates

Direct mutations on FSM state:
1. `manage_flow.state = manage_state` — via `_get_or_create_manage_flow`
2. `manage_flow.symbol = symbol_key`
3. `self._set_manage_truth_source(symbol_key, TRUTH_SOURCE_RESTORE_ARTIFACT)`
4. `close_flow.state = close_state` — via `_get_or_create_close_flow`
5. `close_flow.position_active = (close_state not in {FLAT, DONE})`
6. `self._clear_symbol_brackets(symbol_key)` — clears `_symbol_brackets` and `_symbol_bracket_truth_source`
7. Reads `self._pending_brackets` for deferred WAL cross-check (read-only, no mutation)

Helpers called: `_get_or_create_manage_flow`, `_get_or_create_close_flow`,
`_set_manage_truth_source`, `_clear_symbol_brackets`.

### F3 — What `_apply_authoritative_local_close_reset` (L1065–1142) actually mutates

1. `manage_flow.state = ManageState.FLAT`
2. `manage_flow._clear_lifecycle_tracking(reason, clear_symbol=True)`
3. `close_flow.reset()`
4. `self._clear_symbol_brackets(symbol_key)` — clears both `_symbol_brackets` and `_symbol_bracket_truth_source`
5. `self._pending_brackets.pop(entry_order_id, None)` — WAL mutation
6. `write_pending_brackets_cleared(...)` — WAL persistence side-effect

### F4 — Callers of `_apply_authoritative_restore_record`

- `startup_truth_orchestrator.py` L717: the 0R-3 SEAM call inside `_run_restore_artifact_authoritative_read`
- **No other callers.** Zero calls in `event_handlers.py`, `bracket_health.py`, `bracket_ownership.py`, `order_guardian.py`.

### F5 — Callers of `_apply_authoritative_local_close_reset`

- `fsm.py` L1983: inside `_on_execution_close_reconciled` — **runtime event handler, not startup-specific**
- `event_handlers.py` L376: on `position_closed_detected` — **runtime event handler, not startup-specific**

### F6 — `_restore_artifact_mode` duplication

Both `fsm.py` (L959–965) and `startup_truth_orchestrator.py` (L72–78) define identical method bodies.
The FSM copy is **never called** from anywhere in `fsm.py` directly (confirmed: zero callers of `self._restore_artifact_mode()` in fsm.py body).
The orchestrator copy is called at L82 (`_authoritative_restore_enabled`) and L602 (`_run_restore_artifact_authoritative_read`).

### F7 — `_set_manage_truth_source` callers beyond apply

- `_apply_authoritative_restore_record` L1534: startup apply (sets `TRUTH_SOURCE_RESTORE_ARTIFACT`)
- `_wire_manage_flow` L2104: flow wiring helper (preserves existing or defaults to runtime local)
- `_get_or_create_manage_flow` L2136: flow creation (sets `TRUTH_SOURCE_RUNTIME_LOCAL`)
- `_get_or_create_flows` L2167: flow creation (sets `TRUTH_SOURCE_RUNTIME_LOCAL`)
- `handle()` L2254: every incoming message resets to `TRUTH_SOURCE_RUNTIME_LOCAL`

This confirms `_set_manage_truth_source` is a **generic shell helper** used far beyond 6B scope.

### F8 — Runtime state surfaces mutated by `_apply_authoritative_restore_record`

| Surface | Object | Mutation type |
|---------|-----------|--------------|
| `ExecPosFSM.manage_flows[symbol]` (`ManageFlowFSM`) | `manage_flow.state` | Write (`ManageState`) |
| `ExecPosFSM.manage_flows[symbol]` | `manage_flow.symbol` | Write (str) |
| `ExecPosFSM._symbol_manage_truth_source` | via `_set_manage_truth_source` | Write (str) |
| `ExecPosFSM.close_flows[symbol]` (`CloseFlowFSM`) | `close_flow.state` | Write (`CloseState`) |
| `ExecPosFSM.close_flows[symbol]` | `close_flow.position_active` | Write (bool) |
| `ExecPosFSM._symbol_brackets` | via `_clear_symbol_brackets` | Delete |
| `ExecPosFSM._symbol_bracket_truth_source` | via `_clear_symbol_brackets` | Delete |

All 7 mutation surfaces are initialized in `ExecPosFSM.__init__` (L349–371).

### F9 — `_startup_reconstruct_runtime_bracket_truth` (L1231–1432)

202-line method that uses `self.order_guardian.resolve_terminal_bracket_context(...)` to rebuild bracket truth from post-cleanup open orders. Calls `self._set_symbol_bracket_order`, `self._bracket_ownership.append_bracket_ownership_record`, `self._startup_truth_orchestrator._append_restart_truth_record`. This is not 6B — it is purely 6C.

### F10 — `_startup_order_guardian_reconcile` sequence (L2868–3032)

Proven call sequence:
1. L2902: `self._startup_truth_orchestrator._run_restore_artifact_authoritative_read()` → **triggers 6B apply via 0R-3 seam**
2. L2953: `self.order_guardian.link_existing_from_rest(symbol)` → 6C guardian link
3. L2965: `self.order_guardian.cleanup_orphans()` → 6C guardian cleanup
4. L2982: `self._startup_reconstruct_runtime_bracket_truth(fresh_orders)` → 6C bracket reconstruction
5. L2984: `self._startup_truth_orchestrator._finalize_restore_authoritative_status(...)` → 6A finalization
6. L2989: `self._startup_truth_orchestrator._run_restore_artifact_dark_read_comparison()` → 6A dark-read
7. L2991: `self._startup_truth_orchestrator._persist_restore_artifact_snapshot(...)` → 6A persist
8. L3000: `self._startup_truth_orchestrator._append_startup_truth_artifact_record(...)` → 6A truth log

### F11 — `resolve_restore_artifact_bracket_snapshot` (L1161–1215)

Read-only method. Reads `_pending_brackets` and `_symbol_brackets` to produce a classification dict used for artifact building. No mutations. Currently called from 6A (`startup_truth_orchestrator._build_execution_restore_artifact_record`). This is a **6A supply** method — a read-only helper that 6A calls.

### F12 — Imports required by 6B candidate methods

From `restore_artifact.py`: `ExecutionPositionRestoreLifecycleRecord`, `ExecutionPositionRestoreAuthoritativeSymbolStatus`, `BRACKET_STATE_DEFERRED_PENDING_WAL`, `BRACKET_STATE_LINKED_ACTIVE`, `BRACKET_STATE_PARTIAL_LINKAGE`, `BRACKET_STATE_UNKNOWN`, `RESTORE_PHASE_UNKNOWN`, `TRUTH_SOURCE_RESTORE_ARTIFACT`, `TRUTH_SOURCE_UNKNOWN`.

From `fsm_manage.py`: `ManageState`.
From `fsm_close.py`: `CloseState`.

These are all existing imports in `fsm.py` — they can be shared to the new module.

### F13 — Tests already exercising `_apply_authoritative_restore_record` path

Via `_run_restore_artifact_authoritative_read` (6A seam), the following tests exercise the 6B apply:
- `test_authoritative_read_restores_exact_manage_and_close_fields_from_envelope`
- `test_authoritative_read_keeps_linked_bracket_state_unknown_without_lineage`
- `test_authoritative_read_restores_deferred_pending_only_when_pending_wal_matches`
- `test_authoritative_read_handles_not_readable_without_applying_truth`
- `test_authoritative_read_handles_stale_artifact_without_applying_truth`
- `test_authoritative_read_handles_mixed_certainty_without_promoting_unknown_fields`
- `test_startup_reconcile_preserves_restored_exact_phase_when_portfolio_absent`
- `test_startup_reconcile_surfaces_positive_runtime_override_after_authoritative_restore`

Plus the `test_restart_runtime_truth_reconstruction.py` suite.

---

## INFERENCES

### I1 — `_apply_authoritative_restore_record` is the only true 6B method to extract

It is the single method whose sole purpose is: given a parsed lifecycle record from the authorized artifact, write that record's truth into the live FSM runtime state. It has exactly one caller and no runtime non-startup callers.

### I2 — `_apply_authoritative_local_close_reset` is NOT 6B

It has dual callers: `_on_execution_close_reconciled` (runtime event) and `event_handlers.py` (runtime portfolio update). Moving it to a 6B startup module would require event_handlers.py to import the 6B module — creating a runtime dependency on what should be a startup-only contour. It must stay in FSM or eventually move to a generic runtime reset utility. **Do not extract in 6B.**

### I3 — `_set_manage_truth_source` / `_clear_manage_truth_source` are generic shell helpers, NOT 6B

They have 5+ call sites spanning runtime message handling, flow creation, and flow wiring — not just authoritative apply. Moving them to 6B would create a cross-dependency between the runtime flow lifecycle and the startup-only 6B module.

### I4 — `_restore_artifact_mode` in `fsm.py` is dead code in its current FSM location

Zero callers in `fsm.py`. The orchestrator copy is the live one. The FSM copy should be **deleted** in 6B as a narrow cleanup, replacing it with `return self._startup_truth_orchestrator._restore_artifact_mode()` if any FSM internal needs the gate — but actually no FSM internal calls it, so deletion only is correct.

### I5 — The 6A→6B seam is architecturally inverted but acceptable as a temporary state

The correct future shape is: 6C calls 6B apply directly, not via 6A. Currently 6C (`_startup_order_guardian_reconcile`) calls 6A (`_run_restore_artifact_authoritative_read`) which internally calls 6B (the apply seam). After 6B extraction, the preferred call graph is:
- 6A: read + parse → returns `ExecutionPositionRestoreLifecycleRecord` list
- 6B: receives records → applies each → returns `ExecutionPositionRestoreAuthoritativeStatus`
- 6C: calls 6A, then 6B, then reconstruction

This means 6B extraction also requires `_run_restore_artifact_authoritative_read` in 6A to be refactored: the apply loop (L711–731 in orchestrator) should move to 6B, and the read/parse portion stays in 6A returning parsed records.

### I6 — `_resolve_restore_artifact_bracket_snapshot` is a 6A supply method, not 6B

Called from `startup_truth_orchestrator._build_execution_restore_artifact_record`. It is a read-only snapshot builder that supports artifact writing. It belongs in FSM as a generic shell helper for 6A consumption. Not 6B.

### I7 — 6B is a genuine, separate bounded contour

The mutation surface (7 distinct state writes across ManageFlow, CloseFlow, and truth source caches) is semantically different from 6A (no mutations) and 6C (bracket reconstruction via guardian). A standalone module is justified.

### I8 — The 6B extraction requires a surgical change to the 6A orchestrator

Currently `_run_restore_artifact_authoritative_read` in 6A owns the apply loop (calling `_apply_authoritative_restore_record` per record). After 6B extraction, the split must be:
- 6A: read artifact → parse envelope → return `List[ExecutionPositionRestoreLifecycleRecord]` + status scaffolding
- 6B: apply each record → return completed `ExecutionPositionRestoreAuthoritativeStatus`
- The call from `_startup_order_guardian_reconcile` (6C) should call 6A-read then 6B-apply directly.

Or: 6A's `_run_restore_artifact_authoritative_read` remains but delegates the apply loop to the 6B owner. Both approaches work; the second is less disruptive to 6C.

---

## ASSUMPTIONS

- `ManageFlowFSM.state` is writable (Python attribute assignment) — assumed from direct assignment evidence at L1532.
- `_get_or_create_manage_flow` and `_get_or_create_close_flow` will remain FSM shell methods (not part of 6B) since they are widely used for runtime flow management.
- `write_pending_brackets_cleared` (called in `_apply_authoritative_local_close_reset`) is a WAL persistence function — unrelated to 6B.

---

## UNKNOWNS

- Whether `CloseFlowFSM.reset()` called in `_apply_authoritative_local_close_reset` also clears `position_active` or only state. Not verified in `fsm_close.py`.
- Whether any test directly unit-tests `_apply_authoritative_restore_record` in isolation (not through the 6A seam). If not, 6B implementation validation requires new direct unit tests.
- Whether `_startup_reconstruct_runtime_bracket_truth` (6C, L1231) has any implicit ordering dependency on the output of `_apply_authoritative_restore_record` that could break if they are separated. Visual reading of 6C code shows it uses `self.order_guardian` (independent of manage_flows state) but does call `_set_symbol_bracket_order` which writes `_symbol_brackets` — the same dict `_apply_authoritative_restore_record` clears via `_clear_symbol_brackets`. If 6B apply runs before 6C reconstruction, and 6C reconstruction also writes bracket state, there is a potential order-sensitivity.

---

## Current Package 6B Contour Map

### Methods that belong in 6B (MOVE to new module)

| Method | Current file | Lines | Justification |
|--------|-------------|-------|---------------|
| `_apply_authoritative_restore_record` | `fsm.py` | L1500–1601 | sole mutating apply method for authoritative restore, one caller |

### Methods that belong to 6B scope but need surgical split first

| Method | Current owner | Action needed |
|--------|--------------|---------------|
| `_run_restore_artifact_authoritative_read` (apply loop portion, L711–731 in orchestrator) | `startup_truth_orchestrator.py` | Split: keep read/parse in 6A, move apply loop to 6B |

### Methods to delete/resolve in 6B (not move)

| Method | Current file | Action |
|--------|-------------|--------|
| `_restore_artifact_mode` | `fsm.py` L959–965 | DELETE — has zero callers; orchestrator copy is live |

### Methods that must NOT move in Package 6B

| Method | Reason to stay |
|--------|---------------|
| `_apply_authoritative_local_close_reset` | Dual runtime callers (event_handlers, `_on_execution_close_reconciled`); not startup-only |
| `_set_manage_truth_source` | 5+ runtime call sites; generic shell helper |
| `_clear_manage_truth_source` | Runtime lifecycle cleanup helper |
| `_manage_truth_source_for` | Read-only accessor; used in flow wiring |
| `_symbol_bracket_truth_source_for` | Read-only accessor; used by 6A and observability |
| `_resolve_restore_artifact_bracket_snapshot` | 6A supply method; read-only |
| `_startup_reconstruct_runtime_bracket_truth` | 6C — uses order_guardian + bracket truth reconstruction |
| `_startup_order_guardian_reconcile` | 6C — orchestrates full startup sequence |
| `restore_startup_from_snapshot_positions` | 6C — heuristic hydrate entry point |
| `_get_or_create_manage_flow` | Generic shell helper; used everywhere |
| `_get_or_create_close_flow` | Generic shell helper; used everywhere |
| `_clear_symbol_brackets` | Generic shell helper; called by 6B and runtime reset |

---

## Part A — Current Ownership in `fsm.py`

### Authoritative apply owner
- `_apply_authoritative_restore_record` (L1500–1601) — the sole 6B body

### Local truth reset helper (runtime, NOT startup-specific)
- `_apply_authoritative_local_close_reset` (L1065–1142) — used at runtime, not just startup

### Mode / config gate
- `_restore_artifact_mode` (L959–965) — duplicated; dead in FSM (zero callers); orchestrator copy is live. Should be deleted.

### Read-only loaders / snapshot helpers
- `_manage_truth_source_for` (L969–978)
- `_symbol_bracket_truth_source_for` (L1144–1153)
- `_resolve_restore_artifact_bracket_snapshot` (L1161–1215)

### Startup reconstruction (6C, not 6B)
- `_startup_reconstruct_runtime_bracket_truth` (L1231–1432)
- `restore_startup_from_snapshot_positions` (L2210–2230)

### Guardian reconcile (6C, not 6B)
- `_startup_order_guardian_reconcile` (L2868–3032)

### Generic shell mutators (stay in FSM)
- `_set_manage_truth_source` (L980–987)
- `_clear_manage_truth_source` (L989–993)
- `_clear_symbol_brackets` (L1058–1063)
- `_set_symbol_bracket_order` (L1009–1027)

---

## Part B — What `startup_truth_orchestrator.py` Actually Owns

The apply loop inside `_run_restore_artifact_authoritative_read` (currently at orchestrator L710–731) calls `self._fsm._apply_authoritative_restore_record(record)` inside a for-loop over `envelope.active_lifecycles`. The read/parse portion (L596–709 of the orchestrator) is legitimately 6A. The apply loop at L711–731 is the 6A→6B seam that will need to be re-routed after 6B extraction.

After 6B extraction, the orchestrator's apply loop should be changed to call `self._fsm._authoritative_restore_apply.apply_record(record)` (or equivalent) instead of calling `self._fsm._apply_authoritative_restore_record(record)` directly.

---

## Part C — What Still Belongs to 6C

The following remain clearly 6C (not to be touched in 6B):
- `_startup_order_guardian_reconcile` — the startup coordination shell
- `_startup_reconstruct_runtime_bracket_truth` — bracket truth reconstruction via guardian
- `restore_startup_from_snapshot_positions` — heuristic snapshot hydrate entry point
- `order_guardian.link_existing_from_rest()`, `cleanup_orphans()` — guardian library calls

---

## Part D — Mutation Surface Mapping

| Mutated Surface | Object | 6B classification |
|----------------|--------|------------------|
| `ManageFlowFSM.state` | Flow write | **Core 6B — directly applied** |
| `ManageFlowFSM.symbol` | Flow write | **Core 6B — directly applied** |
| `_symbol_manage_truth_source[symbol]` | Via `_set_manage_truth_source` | **Core 6B — applies truth source** |
| `CloseFlowFSM.state` | Flow write | **Core 6B — directly applied** |
| `CloseFlowFSM.position_active` | Flow write | **Core 6B — directly applied** |
| `_symbol_brackets[symbol]` (delete) | Via `_clear_symbol_brackets` | **Core 6B — pre-apply bracket clear** |
| `_symbol_bracket_truth_source[symbol]` (delete) | Via `_clear_symbol_brackets` | **Core 6B — pre-apply bracket clear** |
| `_pending_brackets` (read only) | Read for WAL cross-check | **6B consumer** (reads, does not write) |
| `ManageFlowFSM._clear_lifecycle_tracking` | Via `_apply_authoritative_local_close_reset` | **NOT 6B** — runtime non-startup helper |
| `_pending_brackets.pop(...)` | Via `_apply_authoritative_local_close_reset` | **NOT 6B** — runtime non-startup helper |

---

## Part E — Ordering and Truth-Risk

### Ordering contract

1. 6A: `_run_restore_artifact_authoritative_read` reads and parses artifact → returns records
2. 6B: `_apply_authoritative_restore_record` per record → writes ManageFlow/CloseFlow/bracket truth
3. 6C: `_startup_reconstruct_runtime_bracket_truth` → uses `order_guardian` index to rebuild bracket truth (writes `_symbol_brackets` via `_set_symbol_bracket_order`)

**Critical ordering constraint**: 6B applies `_clear_symbol_brackets` before setting DEFERRED_PENDING_WAL state. 6C then writes `_symbol_brackets` via `_set_symbol_bracket_order`. This means 6C always overwrites what 6B wrote into bracket state — this is the intended design (6C produces fresher bracket truth from guardian proof). This ordering must be preserved explicitly in any 6B extraction.

### If 6B is shaped incorrectly — failure modes

| Failure mode | Risk level |
|-------------|------------|
| `_apply_authoritative_local_close_reset` accidentally moved to 6B, causing runtime event handlers to import startup module | **HIGH** — import cycle / startup concern at runtime |
| `_set_manage_truth_source` moved to 6B, breaking runtime `handle()` path | **HIGH** — every OPEN/CLOSE message would fail |
| 6B apply executed after 6C reconstruction (wrong ordering) | **HIGH** — authoritative apply would overwrite fresh guardian bracket truth |
| `_clear_symbol_brackets` not called before setting deferred WAL state | **MEDIUM** — stale bracket state from prior session survives into new session |
| `_restore_artifact_mode` duplicate in FSM not deleted → silent config gate split | **MEDIUM** — future caller might use wrong copy, leading to mode gate discrepancy |
| Apply loop NOT moved from 6A to 6B, leaving the seam in place indefinitely | **LOW** — functional but architecturally incorrect; seam call becomes permanent |

---

## Part F — Placement and Naming Verdict

### File location
`apps/reference/domains/execution_position/authoritative_restore_apply.py`
Rationale: it lives at the same level as all other extracted peer modules. Root-level within the domain — no subfolder.

### Preferred module name
**`authoritative_restore_apply.py`** — name is:
- Truthful about scope (authoritative restore, not all restore)
- Truthful about action (apply, not read or compare)
- Not confused with `restore_artifact.py` (schemas/IO) or `startup_truth_orchestrator.py` (read/compare/persist)

Alternatives rejected:
- `startup_truth_apply.py` — misleading; implies coupling with startup truth artifact which is 6A/6C concern
- `restore_apply.py` — ambiguous; could be confused with the WAL/local close reset path
- `authoritative_apply.py` — acceptable but less specific; 6B context is the artifact restore context

### Class name
`AuthoritativeRestoreApply` with `__init__(self, fsm: "ExecPosFSM")` (same back-ref pattern).

### Future neighbors
- True neighbor: `startup_truth_orchestrator.py` (reads; 6B applies what 6A parsed)
- True neighbor: `restore_artifact.py` (owns the Pydantic schemas consumed by 6B)
- Future neighbor: 6C module (will call 6B apply directly after 6A read)
- False neighbor: `bracket_health.py` (health loop; unrelated to restore path)
- False neighbor: `bracket_ownership.py` (ownership truth; different lifecycle concern)
- False neighbor: `fill_ingress_coordinator.py` (fill ingress; no connection to restore path)

---

## Part G — 6A / 6B Seam Analysis

### Current seam
In `startup_truth_orchestrator._run_restore_artifact_authoritative_read` (L710–731):
```python
for record in envelope.active_lifecycles:
    # 0R-3 SEAM (6A→6B): ...
    symbol_status = self._fsm._apply_authoritative_restore_record(record)
    status.symbol_statuses.append(symbol_status)
    status.applied_record_count += 1
    ...
```

### Is this seam structurally correct as a temporary bridge?
**Yes, with one caveat.** The seam is architecturally inverted: 6A is driving 6B apply. After 6B extraction, the preferred inversion is: `_startup_order_guardian_reconcile` (6C) should call 6A read and 6B apply separately. However, the current shape can be kept during 6B extraction if 6A's apply loop is simply re-routed to call `self._fsm._authoritative_restore_apply.apply_record(record)` (the new 6B module method) instead of `self._fsm._apply_authoritative_restore_record(record)`.

### Remaining seam problems
1. The orchestrator's apply loop (lines 711–731) is logically the 6B body, not 6A. This code belongs in the 6B module, not in the read/parse method.
2. The `_restore_artifact_mode` duplicate in `fsm.py` is dead code and must be deleted in 6B.
3. The FSM delegator `_persist_restore_artifact_snapshot` added in 0R correctly routes to 6A — no seam problem there.

### How to resolve `_restore_artifact_mode` duplication
During 6B: **delete the FSM copy** (`fsm.py` L959–965). The orchestrator copy is the authoritative one. If any FSM internal method needs the mode gate, it should call `self._startup_truth_orchestrator._restore_artifact_mode()` via the orchestrator. Evidence: zero callers of the FSM copy — so deletion alone is correct, no re-routing needed.

---

## Package 6B Readiness Verdict

### READY — with preconditions

**Preconditions before coding:**

1. Review `_run_restore_artifact_authoritative_read` in `startup_truth_orchestrator.py` to confirm the apply loop (L710–731 in current file) can be cleanly split from the read/parse body. The boundary is the `for record in envelope.active_lifecycles:` loop — clear and unambiguous.

2. Confirm `_apply_authoritative_restore_record` has no hidden callers beyond `startup_truth_orchestrator.py` — confirmed (grep proves one caller only).

3. Decide on seam re-routing strategy:
   - Option A: leave `_run_restore_artifact_authoritative_read` intact, just re-route the call from `self._fsm._apply_authoritative_restore_record(record)` to `self._fsm._authoritative_restore_apply.apply_record(record)`. Minimal disruption.
   - Option B: split `_run_restore_artifact_authoritative_read` into two methods: a pure reader and the apply loop. More architecturally correct but more invasive.
   
   **Recommendation: Option A for 6B. Option B can be deferred to 6C or a future cleanup.**

4. Add FSM-level thin delegator `apply_authoritative_restore_record` on ExecPosFSM routing to the 6B module instance, so the `startup_truth_orchestrator` back-ref call chain does not need to reach into the 6B module directly.

**Tests required for 6B validation:**

- Re-run: `tests/domains/execution_position/test_execution_restore_authoritative_read.py` (22 tests)
- Re-run: `tests/domains/execution_position/test_restart_runtime_truth_reconstruction.py` (3 tests)
- New required: Direct unit test for `AuthoritativeRestoreApply.apply_record(record)` that:
  - Verifies manage_flow.state is set correctly for exact phases
  - Verifies close_flow.state and position_active are set correctly
  - Verifies `_clear_symbol_brackets` is called before any bracket state evaluation
  - Verifies DEFERRED_PENDING_WAL cross-check with `_pending_brackets`
  - Verifies unknown/unsupported phase handling does not mutate any state
  - Verifies `_set_manage_truth_source` is called with `TRUTH_SOURCE_RESTORE_ARTIFACT`
- Static checks: `ruff`, `mypy --ignore-missing-imports` on new file

**Exact commands for 6B validation:**
```powershell
pytest tests/domains/execution_position/test_execution_restore_authoritative_read.py `
       tests/domains/execution_position/test_restart_runtime_truth_reconstruction.py `
       tests/domains/execution_position/test_execution_restore_dark_read.py `
       tests/domains/execution_position/test_execution_restore_artifact_writer.py -v

ruff check apps/reference/domains/execution_position/authoritative_restore_apply.py `
           apps/reference/domains/execution_position/fsm.py `
           apps/reference/domains/execution_position/startup_truth_orchestrator.py

mypy apps/reference/domains/execution_position/authoritative_restore_apply.py --ignore-missing-imports
```

---

## Final Recommendation

**Package 6B should proceed as a separate extraction.** The contour is real : one mutating method with one caller, clear runtime state ownership, clear import boundary, and a well-defined pre/post position in the startup sequence.

**Exact 6B work:**
1. Create `apps/reference/domains/execution_position/authoritative_restore_apply.py` containing `AuthoritativeRestoreApply` class.
2. Move `_apply_authoritative_restore_record` (L1500–1601) into `AuthoritativeRestoreApply` as `apply_record`.
3. Wire `self._authoritative_restore_apply = AuthoritativeRestoreApply(self)` in `ExecPosFSM.__init__`.
4. Add FSM-level delegator `_apply_authoritative_restore_record` on `ExecPosFSM` that routes to the 6B instance (preserving backward compatibility for the 6A seam call).
5. Delete dead `_restore_artifact_mode` from `fsm.py` (L959–965).
6. The 6A orchestrator seam call (`self._fsm._apply_authoritative_restore_record(record)`) continues to work via the FSM delegator — no change needed to orchestrator.
7. Update tests: patch targets change from `fsm._apply_authoritative_restore_record` to `fsm._authoritative_restore_apply.apply_record` (or the FSM delegator).

**What 6B must NOT do:**
- Move `_apply_authoritative_local_close_reset` (runtime dual-caller)
- Move `_set_manage_truth_source` or `_clear_manage_truth_source` (generic shell helpers)
- Move `_startup_reconstruct_runtime_bracket_truth` (6C)
- Move `_startup_order_guardian_reconcile` (6C)
- Move `_resolve_restore_artifact_bracket_snapshot` (6A supply)
- Change the apply ordering relative to 6C bracket reconstruction
