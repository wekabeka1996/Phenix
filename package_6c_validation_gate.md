# Package 6C — Validation Gate Report

**Date:** 2026-04-19  
**Scope:** Startup Reconstruction extraction — validation only  
**Prior status:** STRUCTURALLY LANDED (no runtime proof)

---

## Problem Framing

Package 6C extracted `_startup_reconstruct_runtime_bracket_truth` (202 lines) from `fsm.py` into `startup_reconstruction.py`. A prior implementation report claims completion but explicitly states that all `pytest`, `ruff`, and `mypy` commands were blocked by a `Windows sandbox` infrastructure error. This validation gate attempts to convert the claim to repository-proven evidence.

---

## FACTS

### F-1: Command execution is blocked on this host

Every `run_command` invocation — including `python script.py`, `pytest`, `ruff`, and even subprocess-based workarounds — returns:

```
error executing cascade step: CORTEX_STEP_TYPE_RUN_COMMAND:
failed to set up sandbox: sandboxing is not supported on Windows
```

This was reproduced across **7 distinct attempts** in this session and the prior session:
1. `pytest tests/.../test_startup_reconstruction.py -v` — BLOCKED
2. `python -m pytest ...` — BLOCKED
3. `python _6c_validate.py` (subprocess wrapper) — BLOCKED
4. `ruff check ...` — BLOCKED
5. `python -m ruff check ...` — BLOCKED
6. `python -m mypy ...` — BLOCKED
7. `python _6c_validate.py` (inline pytest.main approach) — BLOCKED

**FACT: No Python process can be executed on this host through the available tooling.** This is an infrastructure limitation, not a code defect.

### F-2: `startup_reconstruction.py` exists and contains the extracted logic

File: `apps/reference/domains/execution_position/startup_reconstruction.py` — 244 lines.  
Class: `StartupReconstruction` with single method `reconstruct(open_orders)`.  
Verified by direct `view_file` read of all 244 lines.

### F-3: `fsm.py` delegator is correctly wired

**Import** (L87):
```python
from apps.reference.domains.execution_position.startup_reconstruction import StartupReconstruction
```

**`__init__` wiring** (L377):
```python
self._startup_reconstruction = StartupReconstruction(self)  # Package 6C
```

**Delegator** (L1227-1233):
```python
# --- 0R: Sanctioned FSM-level delegator for 6C (startup_reconstruction.py) ---
def _startup_reconstruct_runtime_bracket_truth(
    self,
    open_orders: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Thin delegator — routes to StartupReconstruction (Package 6C owner)."""
    return self._startup_reconstruction.reconstruct(open_orders)
```

All verified by direct `view_file`.

### F-4: `_startup_order_guardian_reconcile` remains in `fsm.py` as orchestration shell

Location: `fsm.py` L2579–L2743 (165 lines).  
Calls `self._startup_reconstruct_runtime_bracket_truth(fresh_orders)` at L2693 — which delegates to 6C.  
Verified by direct `view_file` of L2570–L2746.

### F-5: `restore_startup_from_snapshot_positions` remains in `fsm.py`

Location: `fsm.py` L1921–L1941 (21 lines).  
Heuristic hydration gate called from `main.py`.  
Verified by direct `view_file`.

### F-6: `start_order_guardian` remains in `fsm.py`

Location: `fsm.py` L1755–L1769 (15 lines).  
FSM startup entry point.  
Verified by direct `view_file`.

### F-7: Startup ordering is preserved

Verified from `_startup_order_guardian_reconcile` body (L2579-2743):

| Step | Line | Operation | Owner |
|------|------|-----------|-------|
| 1 | L2613 | `_run_restore_artifact_authoritative_read()` | 6A (→6B apply) |
| 2 | L2623 | `adapter.get_open_positions()` | REST |
| 3 | L2641 | `adapter.get_open_orders()` | REST pre-cleanup |
| 4 | L2664 | `order_guardian.link_existing_from_rest(symbol)` | Guardian |
| 5 | L2676 | `order_guardian.cleanup_orphans()` | Guardian |
| 6 | L2679 | `adapter.get_open_orders()` | REST post-cleanup |
| **7** | **L2693** | **`_startup_reconstruct_runtime_bracket_truth(fresh)`** | **6C delegator** |
| 8 | L2695 | `_finalize_restore_authoritative_status(...)` | 6A |
| 9 | L2700 | `_run_restore_artifact_dark_read_comparison()` | 6A |
| 10 | L2702 | `_persist_restore_artifact_snapshot(...)` | 6A |
| 11 | L2711 | `_append_startup_truth_artifact_record(...)` | 6A (finally) |

**Exact audit-required ordering is preserved:**  
6A read/apply → REST → guardian link → guardian cleanup → fresh REST → **6C reconstruct** → 6A finalize/dark-read/persist.

### F-8: No 6A/6B logic leaked into `startup_reconstruction.py`

From full read of all 244 lines:
- `_run_restore_artifact_dark_read` — **NOT present**
- `_run_restore_artifact_authoritative_read` — **NOT present**
- `_apply_authoritative_restore_record` — **NOT present**
- `_persist_restore_artifact_snapshot` — **NOT present**
- `_finalize_restore_authoritative_status` — **NOT present**
- `adapter.get_open_orders` — **NOT present**
- `adapter.get_open_positions` — **NOT present**
- `link_existing_from_rest` — **NOT present**
- `cleanup_orphans` — **NOT present**

The only cross-boundary calls in `startup_reconstruction.py` are:
- `self._fsm.order_guardian.resolve_terminal_bracket_context(...)` — guardian library consumer (correct)
- `self._fsm._startup_truth_orchestrator._append_restart_truth_record(...)` — 6A write-sink (correct)
- FSM shell helpers: `_set_symbol_brackets_snapshot`, `_clear_symbol_brackets`, `_runtime_order_index`, `_manage_truth_source_for`, `_manage_state_value`, `_symbol_bracket_truth_source_for`, `_emit_observability_event`, `manage_flows` — all correct

**No full startup orchestration leaked into 6C.**

### F-9: Test file exists with 6 test functions

File: `tests/domains/execution_position/test_startup_reconstruction.py` — 233 lines, 6 tests:
1. `test_reconstruct_returns_zero_when_guardian_none`
2. `test_reconstruct_skips_orders_missing_symbol_or_id`
3. `test_reconstruct_skips_unsupported_bracket_roles`
4. `test_reconstruct_sl_tp_correctly_for_resolved_symbol`
5. `test_reconstruct_marks_unresolved_on_duplicate_roles`
6. `test_reconstruct_observability_event_emitted`

### F-10: JOURNA.md was correctly appended

- `JOURNA.md` pre-existed (788 lines after append).
- Package 6C entry appended at L761 under heading `## 2026-04-19` with `**Task / package id:** Package 6C -- Startup Reconstruction extraction`.
- Prior entries preserved intact.

---

## INFERENCES

- The extraction is structurally consistent with the 6A and 6B patterns (back-ref + delegator).
- The test file is well-structured and covers the audit-required cases with MagicMock-based FSM stubs.
- The `_note_unresolved` nested closure moved intact inside `reconstruct()` (confirmed at L55-56 of `startup_reconstruction.py`).
- Return type annotation was corrected from `Dict[str, int]` (old) to `Dict[str, Any]` (new delegator), which is more accurate for the actual return shape `{"summary": ..., "records": ...}`.

---

## ASSUMPTIONS

- None. All findings are based on direct file reads.

---

## UNKNOWNS

1. **Whether the code actually imports and runs without error** — no Python process could be executed.
2. **Whether all 6 new tests pass** — pytest could not be executed.
3. **Whether the 48+ existing restore tests still pass** — pytest could not be executed.
4. **Whether ruff reports any lint issues** — ruff could not be executed.
5. **Whether mypy reports type errors** — mypy could not be executed.

---

## Exact Commands Run

| Command | Result |
|---------|--------|
| `pytest tests/.../test_startup_reconstruction.py -v` | BLOCKED — sandbox error |
| `python -m pytest tests/.../test_startup_reconstruction.py -v` | BLOCKED — sandbox error |
| `python _6c_validate.py` (subprocess wrapper) | BLOCKED — sandbox error |
| `ruff check .../startup_reconstruction.py .../fsm.py` | BLOCKED — sandbox error |
| `python -m ruff check ...` | BLOCKED — sandbox error |
| `python -m mypy .../startup_reconstruction.py` | BLOCKED — sandbox error |

**No command executed successfully. All returned:**
```
error executing cascade step: CORTEX_STEP_TYPE_RUN_COMMAND:
failed to set up sandbox: sandboxing is not supported on Windows
```

---

## Test-by-Test Summary

**Cannot provide.** No test was executed.

---

## Static-Check Summary

| Tool | Status |
|------|--------|
| ruff | NOT RUN — sandbox blocked |
| mypy | NOT RUN — sandbox blocked |

---

## Boundary Integrity Check

| Check | Result | Evidence |
|-------|--------|----------|
| `startup_reconstruction.py` contains ONLY 6C logic | ✅ PASS | Full 244-line read: no 6A read/compare/persist, no 6B apply, no REST calls, no guardian orchestration |
| `_startup_order_guardian_reconcile` stays in `fsm.py` | ✅ PASS | Confirmed at L2579–L2743 with all orchestration steps intact |
| `restore_startup_from_snapshot_positions` stays in `fsm.py` | ✅ PASS | Confirmed at L1921–L1941 |
| `start_order_guardian` stays in `fsm.py` | ✅ PASS | Confirmed at L1755–L1769 |
| Shell helpers (`_set_symbol_brackets_snapshot`, `_runtime_order_index`, etc.) stay in `fsm.py` | ✅ PASS | 6C calls them via `self._fsm.*` back-ref |
| Startup ordering preserved | ✅ PASS | 6A→REST→Guardian→6C→6A finalize confirmed at L2613→L2693→L2700 |
| No 6A logic absorbed into 6C | ✅ PASS | No dark-read, auth-read, persist, finalize in 6C |
| No 6B logic absorbed into 6C | ✅ PASS | No `_apply_authoritative_restore_record` in 6C |
| 6C intentional overwrite semantics preserved | ✅ PASS | `TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN` at L162 |

---

## JOURNA.md Update Confirmation

- File existed: YES
- Append (not overwrite): YES — prior entries preserved through L759
- Package 6C entry heading: `## 2026-04-19` / `Package 6C -- Startup Reconstruction extraction`
- Status in journal: `COMPLETED`

---

## Risks / Unproven Areas

1. **CRITICAL — No runtime execution proof exists.** Zero Python processes were executed. The code may contain an import error, a typo, or a runtime exception that static read cannot detect.
2. **MEDIUM — Tests were never executed.** The 6 new tests and 48+ existing restore tests have never run post-6C. A regression cannot be ruled out.
3. **LOW — The structural extraction is clean.** All boundary checks pass via static read. The pattern exactly mirrors 6A and 6B which were proven to work.

**Recommended user action:** Run the following commands manually in a terminal:
```bash
cd c:\Users\user\Music\Phenix
python -m pytest tests/domains/execution_position/test_startup_reconstruction.py -v
python -m pytest tests/domains/execution_position/test_restart_runtime_truth_reconstruction.py -v
python -m pytest tests/domains/execution_position/test_execution_restore_authoritative_read.py -v
```

---

## Final Verdict

### `PACKAGE 6C NOT PROVEN`

**Rationale:**  
The structural extraction is complete and all boundary checks pass via static file reads. However, the task explicitly requires "Real command execution is mandatory" and "No claims without executed evidence." Since **zero commands executed successfully** due to the Windows sandbox infrastructure limitation, the package cannot be promoted to COMPLETE.

**What is proven:**
- Code exists in the right files
- Delegator is wired
- Boundaries are clean (no 6A/6B/orchestration leakage)
- Ordering is preserved
- Tests exist with correct coverage structure
- JOURNA.md is updated

**What is NOT proven:**
- Whether the code actually runs
- Whether imports resolve without circular dependency
- Whether all tests pass
- Whether ruff/mypy are clean

**To convert to COMPLETE:** Execute the pytest commands listed above in a real terminal and confirm 0 failures.
