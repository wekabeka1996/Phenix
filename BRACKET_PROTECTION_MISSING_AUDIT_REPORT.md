# BRACKET PROTECTION-MISSING REMEDIATION — INDEPENDENT ACCEPTANCE AUDIT REPORT

**Auditor:** Antigravity (Claude Sonnet 4.6 Thinking)  
**Date:** 2026-04-25  
**Scope:** EVT:BRACKET_PLACEMENT_FAILED + ManageState.PROTECTION_MISSING + _handle_bracket_protection_missing remediation package  
**Verdict:** **ACCEPTED_WITH_RESIDUAL_RISK**

---

## 1. Problem Framing

Before this patch, all bracket placement failures in `ManageFlowFSM._place_brackets` fell through silently to normal `TRACKING` state. The system had no structured event, no explicit remediation, and no way to distinguish "position live with no brackets" from "placement legitimately not needed." The patch aims to:

1. Add `ManageState.PROTECTION_MISSING` as a named terminal-like FSM state for bracket placement failures.
2. Add `EVT:BRACKET_PLACEMENT_FAILED` as a canonical observable bus event.
3. Add `_handle_bracket_protection_missing` on `ExecPosFSM` to emit the event and conditionally force-close.
4. Wire `BracketManager`, `OpenExecutor`, `CloseExecutor` into the helper.

---

## 2. FACTS (Code-evidence-backed)

### 2A. Contract Validation

| Check | Result |
|---|---|
| `EVT:BRACKET_PLACEMENT_FAILED` in `verb_registry_v1.yaml` | ✅ Present at line 587–592, owner=`execution_position`, status=`active`, schema path correctly set |
| Schema file exists | ✅ `schemas/bracket_placement_failed_v1.json` — 37 lines, all required fields defined |
| `domain_dict.json` export | ✅ Present at line 51 with `target_domains: [monitoring]` |
| Schema required fields | `ts_ms, symbol, source_path, failure_class, reason, why_code, remediation_action` |
| Actual emitted payload (fsm.py L2449–2467) | Contains all 7 required fields plus optional extensions — ✅ COMPLIANT |
| Actual emitted payload (fsm_manage.py via `_bracket_failure_payload`) | Contains all 7 required fields — ✅ COMPLIANT |
| BracketManager fallback emit (no handler) | Contains all 7 required fields — ✅ COMPLIANT |
| CloseExecutor fallback emit (no handler) | Hardcodes `remediation_action: "force_reduce_only_close"` — ⚠️ **DEFECT D1** (see below) |
| `since:` date on registry entry | 2026-04-25 — correct |
| `additionalProperties: true` in schema | ✅ Appropriate for extension fields |

### 2B. ManageState.PROTECTION_MISSING

- Declared at `fsm_manage.py:63` alongside `TRACKING`, `BRACKETS_PENDING`, `BRACKETS_PLACED`.
- `_handle_bracket_placement_failure` (line 756) sets `self.state = ManageState.PROTECTION_MISSING` unconditionally before emitting the event.
- State is included in the multi-state fill guard at line 984: `ManageState.PROTECTION_MISSING` is in the set that blocks entry-like fills over an active lifecycle.

### 2C. _place_brackets Cannot Fall Through to TRACKING

All 7 explicit early-return paths in `_place_brackets`:

| Condition | Line | Route |
|---|---|---|
| `not self._should_place_brackets()` | 1171–1178 | → `_handle_bracket_placement_failure` |
| `position_qty/entry_price/side` is None | 1181–1193 | → `_handle_bracket_placement_failure` |
| `sl_price or tp1_price` is None | 1197–1208 | → `_handle_bracket_placement_failure` |
| `current_mark` is None (entry_price proxy) | 1218–1225 | → `_handle_bracket_placement_failure` |
| SL validation fails | 1237–1246 | → `_handle_bracket_placement_failure` |
| TP1 validation fails | 1255–1264 | → `_handle_bracket_placement_failure` |
| TP2 validation fails | 1274–1283 | → `_handle_bracket_placement_failure` |
| `except (ValueError, TypeError, KeyError)` | 1426–1437 | → `_handle_bracket_placement_failure` |

**The anti-race closing_flag path (line 1138) still routes to `ManageState.TRACKING`.** This is pre-existing intentional behavior (position is closing; brackets are deliberately skipped), NOT a protection-missing scenario. This is correct and must not be changed.

**Successful path (line 1413–1424):** Returns `DEC:BATCH` message — state is never explicitly set to TRACKING by `_place_brackets` itself. State transitions happen upstream via `_on_bracket_placed` → `BRACKETS_PLACED` when confirmation arrives.

✅ **_place_brackets cannot silently enter TRACKING on any required SL/TP failure.**

### 2D. ExecPosFSM._handle_bracket_protection_missing (fsm.py L2417–2491)

- Signature: async, keyword-only args with `live_position_proven: bool = False`.
- Payload built with all 7 required schema fields.
- Emits via `_emit_execution_bus_event` which writes to both bus and `_emit_observability_event`.
- `if not live_position_proven: return remediation_action` — no blind close.
- When `live_position_proven=True`: constructs `DEC:CLOSE` with `trigger=BRACKET_PROTECTION_MISSING`, `close_guard_prevalidated=True`, and calls `self._close_exec.execute_close(close_msg)` directly.
- The `execute_close` path passes through truth-hardening duplicate-close guard (fsm.py L2136–2174), which will suppress if the same close is already in flight.

### 2E. Event Emission Deduplication

The current implementation does **not** implement explicit deduplication of `EVT:BRACKET_PLACEMENT_FAILED` within a single lifecycle. Multiple failure paths can independently call the helper. This is acceptable because:
- The state transitions to `PROTECTION_MISSING` on the first call from `_handle_bracket_placement_failure` (in fsm_manage).
- Subsequent calls from other callers (BracketManager, OpenExecutor, CloseExecutor) bypass the ManageFlowFSM path and call `ExecPosFSM._handle_bracket_protection_missing` directly.
- No architectural deduplication exists in the ExecPosFSM helper — this is **RESIDUAL RISK R1**.

---

## 3. INFERENCES

- The two emission paths (ManageFlowFSM via observability hook vs ExecPosFSM via bus emit) can produce the same event for the same failure if both are triggered. In practice, ManageFlowFSM emits via the observability hook; the ExecPosFSM path emits via the event bus. These are different channels — a single failure in `_place_brackets` goes only through one path.
- The `_protection_missing_close_decision` gate in `fsm_manage.py` (checks `position_qty/entry_price/side`) is a **proxy for `live_position_proven`** in the synchronous ManageFlowFSM context. It is weaker than an exchange REST confirmation but reasonable: by the time `_place_brackets` executes, `_on_fill` has already hydrated these fields.

---

## 4. ASSUMPTIONS

- The observability hook on ManageFlowFSM is wired to the event bus in production (not verified by static inspection alone — the wiring happens in fsm.py initialization code not audited here).
- `close_guard_prevalidated=True` is honored by the close execution path to skip normal guard checks.

---

## 5. UNKNOWNS

- Whether the observability hook is actually connected to the event bus vs. only to logging in all deployment configurations.
- Whether `_handle_bracket_protection_missing` is idempotent under concurrent async calls for the same symbol (no mutex around the emit or close dispatch).

---

## 6. live_position_proven Caller Matrix

| Caller | `live_position_proven` value | Proof basis | Classification |
|---|---|---|---|
| `ManageFlowFSM._handle_bracket_placement_failure` | Implicit via `_protection_missing_close_decision`: True only if `position_qty/entry_price/side` are all non-None | Local state hydrated by `_on_fill` **before** `_place_brackets` is called | **WEAK** — local state, not exchange-confirmed, but hydrated from a fill event which represents real exchange data |
| `BracketManager.place_brackets_parallel` — final_error path (line 290) | `live_position_proven=True` | Entry accepted (has `entry_resp.orderId`), parallel bracket placement failed entirely after sequential fallback also failed | **STRONG** — market entry was accepted by exchange (entry_resp present), position is live |
| `BracketManager.place_brackets_parallel` — response_missing path (line 311) | `live_position_proven=True` | Same — entry_resp exists | **STRONG** |
| `BracketManager.place_deferred_brackets` — preflight_false (line 570) | `live_position_proven=False` | Position check failed REST poll | **CORRECT** — not proven, no close |
| `BracketManager.place_deferred_brackets` — guardian_veto (line 589) | `live_position_proven=False` | Guardian rejected but position not confirmed | **CORRECT** |
| `BracketManager.place_deferred_brackets` — existing_live_synced (line 606) | `live_position_proven=False` + `remediation_action_override="existing_exchange_brackets_synced"` | Already protected | **CORRECT** — remediation override used appropriately |
| `BracketManager.place_deferred_brackets` — incomplete placement (line 860) | `live_position_proven=False` | Partial placement (one of SL/TP succeeded) | ⚠️ **DEFECT D2** — if SL succeeded but TP failed (or vice versa), position is half-protected; no close is emitted |
| `OpenExecutor.execute_open` — preflight_false (line 629) | `live_position_proven=False` | Market entry accepted, but preflight REST check returned False | **CORRECT** — ambiguous state, no blind close |
| `OpenExecutor.execute_open` — guardian_blocked (line 648) | `live_position_proven=False` | Guardian veto, position not confirmed | **CORRECT** |
| `CloseExecutor._record_auxiliary_bracket_failure` (line 334) | `live_position_proven=bool(manage_flow is not None and _manage_flow_allows_bracket_sync(manage_flow))` | ManageFlow state != FLAT/empty | **WEAK-ACCEPTABLE** — ManageFlow being non-FLAT is a reasonable proxy for "position is live"; stronger than nothing |

### Race Condition Analysis

| Scenario | Handled? |
|---|---|
| Entry accepted but fill not confirmed | ✅ OpenExecutor preflight=False → no blind close |
| Fill confirmed but local position not hydrated | ✅ ManageFlow gate (qty/price/side == None) → no close from FSM path |
| Exchange brackets exist but local IDs missing | ✅ `_has_live_synced_brackets` check in deferred path returns True → suppress duplicate |
| Adapter rejection after entry placement | ✅ BracketManager parallel path: entry_resp present → live_position_proven=True → force close |
| Market preflight false after accepted entry | ✅ live_position_proven=False → record only, no close |
| Deferred LIMIT pending bracket case | ✅ Separate WAL path; preflight and guardian guard apply |

---

## 7. BracketManager / OpenExecutor / CloseExecutor Path Audit

| Scenario | Evented? | Remediated? | Verdict |
|---|---|---|---|
| Market entry accepted + both brackets fail (parallel) | ✅ | ✅ force_close (live_position_proven=True) | OK |
| Market entry accepted + preflight false | ✅ | ✅ record only (no blind close) | OK |
| Deferred LIMIT preflight false | ✅ | ✅ record only (no blind close) | OK |
| Deferred LIMIT guardian veto | ✅ | ✅ record only | OK |
| Deferred LIMIT partial placement (SL OK, TP fail or v.v.) | ✅ | ⚠️ live_position_proven=False — no close emitted | **DEFECT D2** |
| Already-live synced SL+TP | ✅ (with override) | ✅ no duplicate close | OK |
| Auxiliary DEC:PLACE_ORDER failure | ✅ | ✅ via `_record_auxiliary_bracket_failure` | OK — no longer log-only |
| CloseExecutor fallback (no handler) emits hardcoded `remediation_action: "force_reduce_only_close"` regardless of live_position_proven | ⚠️ | ⚠️ payload field incorrect | **DEFECT D1** |

---

## 8. Regression Risk Assessment

| Component | Risk | Status |
|---|---|---|
| `bracket_health.py` | Uses `state != FLAT` checks; PROTECTION_MISSING is not FLAT → correctly included in active lifecycle | ✅ No regression |
| `orphan_cleanup` / `order_guardian` | Not state-dependent; unaffected | ✅ No regression |
| `reconciliation` path | Not state-dependent | ✅ No regression |
| Startup restore/hydration | `_clear_lifecycle_tracking` does not explicitly restore PROTECTION_MISSING — after restart, FSM begins at FLAT. Position may be live but FSM won't know to close. | ⚠️ Pre-existing gap, not introduced by patch |
| `has_active_lifecycle()` | `state != FLAT` returns True for PROTECTION_MISSING — correctly prevents new open intent | ✅ OK |
| `_local_open_guard` | PROTECTION_MISSING is non-FLAT → blocks new entries | ✅ Correct |
| Existing tests around bracket algo client IDs | All 65 pass | ✅ No regression |
| Auxiliary bracket registration | Tested and passing | ✅ No regression |
| Open submission closure | Tested and passing | ✅ No regression |
| tpsl placement | Tested and passing | ✅ No regression |

---

## 9. Defects Found

### D1 — CloseExecutor Fallback Emit Has Hardcoded `remediation_action: "force_reduce_only_close"` (LOW)

**Location:** `close_executor.py` lines 351 (fallback emit when `_handle_bracket_protection_missing` not callable)

**Problem:** The fallback `_emit_execution_bus_event` path in `_record_auxiliary_bracket_failure` hardcodes `remediation_action: "force_reduce_only_close"` even if the manage_flow is FLAT (i.e., position not actually live). The primary code path (handler callable) is correct; only the defensive fallback is wrong.

**Severity:** LOW — the primary path (handler callable) always runs in production; the fallback is defensive dead code in practice since `_handle_bracket_protection_missing` is always present on `ExecPosFSM`.

**Suggested fix:** Mirror the same `live_position_proven` conditional in the fallback emit as in the primary path. No immediate action required.

### D2 — Partial Deferred Bracket Placement (SL placed, TP fails) Uses `live_position_proven=False` (MEDIUM)

**Location:** `bracket_manager.py` lines 843–861

**Problem:** When a deferred LIMIT bracket placement partially succeeds (e.g., SL placed, TP rejected), the failure record uses `live_position_proven=False`. However, at this point:
- `preflight_position_check` already passed (position confirmed by REST).
- SL was accepted by the exchange.
- Position is half-protected: SL exists but TP is missing, or TP exists but SL is missing.

A half-protected position is still an unprotected-TP or unprotected-SL scenario and arguably warrants active remediation or at least an escalated alert.

**Severity:** MEDIUM — the event is correctly emitted, the `live_position_proven=False` argument means no force-close is issued. The position remains alive with partial protection. This is arguably safe (better than a premature close on ambiguous state), but the why_code `BRACKET_DEFERRED_PLACEMENT_INCOMPLETE` does not capture which leg failed.

**Note:** The details dict does capture `sl_response_present` and `tp_response_present`, which partially mitigates the lack of action.

**Suggested action (follow-up patch):** After `preflight_position_check` passes in the deferred path, if both SL and TP placement fail, set `live_position_proven=True`. If only one fails, emit with enhanced `details` and escalate to monitoring; do not blind-close.

---

## 10. Tests Run

```
tests/domains/execution_position/test_bracket_protection_missing_remediation.py
tests/domains/execution_position/test_bracket_algo_client_id_correlation.py
tests/domains/execution_position/test_auxiliary_bracket_registration_hardening.py
tests/domains/execution_position/test_open_submission_adapter.py
tests/domains/execution_position/test_open_submission_closure_package3.py
tests/test_tpsl_placement.py
```

**Result: 65 passed, 0 failed, 1.93s**

**py_compile:** PASSED for all 5 changed files:
- `fsm.py`, `fsm_manage.py`, `bracket_manager.py`, `open_executor.py`, `close_executor.py`

---

## 11. Behavior Before / After Summary

| Scenario | Before | After |
|---|---|---|
| `sl_pct` missing from config | Silent fall-through → TRACKING (unprotected) | PROTECTION_MISSING + EVT emitted + local close if qty/price/side hydrated |
| `tp_low_ratio` missing from config | Silent fall-through → TRACKING (unprotected) | PROTECTION_MISSING + EVT emitted |
| SL/TP validation fails | Silent fall-through → TRACKING | PROTECTION_MISSING + EVT emitted |
| Quantization/tick_size error | ValueError logged → TRACKING | PROTECTION_MISSING + EVT emitted |
| Market entry + bracket fail (parallel) | Log only | EVT emitted + force_close (live_position_proven=True) |
| Market entry + preflight false | Log only | EVT emitted, no blind close |
| Deferred LIMIT + partial placement | Log only | EVT emitted, no blind close (see D2) |
| Auxiliary DEC:PLACE_ORDER bracket fail | Log only | EVT emitted + conditional close |

---

## 12. Verdict

**ACCEPTED_WITH_RESIDUAL_RISK**

### Acceptance rationale
- All 7 `_place_brackets` failure paths correctly route to `PROTECTION_MISSING` state + `EVT:BRACKET_PLACEMENT_FAILED` emission.
- `EVT:BRACKET_PLACEMENT_FAILED` is correctly registered in the verb registry with a schema, exported in domain_dict.json, and the emitted payload matches the schema's required fields.
- `live_position_proven` boundary is respected: no blind closes occur without evidence of a live exchange position.
- The DEC:CLOSE remediation goes through the existing truth-hardening duplicate-close guard.
- All 65 focused tests pass. All 5 changed files pass py_compile.
- No critical defects that would block acceptance.

### Residual risks requiring follow-up (not blocking)
1. **R1:** No explicit deduplication of `EVT:BRACKET_PLACEMENT_FAILED` within a single lifecycle — multiple callers can emit for the same failure scenario if wired independently.
2. **D1:** CloseExecutor fallback emit hardcodes `remediation_action: "force_reduce_only_close"` in dead-code defensive path — LOW severity.
3. **D2:** Partial deferred bracket placement uses `live_position_proven=False` even after preflight passed — MEDIUM severity; follow-up patch recommended.
4. **R2:** PROTECTION_MISSING state is not persisted or restored across restarts — pre-existing gap; position with no brackets after restart is not automatically detected.

### Follow-up patch required?
**Optional, not blocking.** D2 is the highest priority for a targeted follow-up.

### Docs / passports update required before closure?
- `domain_dict.json` — ✅ already updated (EVT:BRACKET_PLACEMENT_FAILED exported)
- `verb_registry_v1.yaml` — ✅ already updated
- `README.md` or domain boundary docs — not updated; consider adding note about PROTECTION_MISSING state semantics in a follow-up.
