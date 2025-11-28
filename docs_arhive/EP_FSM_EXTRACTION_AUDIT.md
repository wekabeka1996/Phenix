# EP-FSM-EXTRACTION-AUDIT-S0: Full Extraction & Duplication Audit

**Date:** 2025-11-20  
**Status:** Audit Complete  
**Scope:** `ExecPosFSM` (legacy) vs `shadow_execpos` (new)

---

## 1. Executive Summary

We have successfully established a modular shadow architecture that mirrors the core responsibilities of the monolithic `ExecPosFSM`.

- **Coverage:** ~90% of core logic (Execution, Gatekeeping, Watchdog, Idempotency, Async) has a clear home in `shadow_execpos`.
- **Gaps:** Some legacy-specific logic (WAL integration, complex bracket state management, exposure summaries) remains only in fsm.py, which is acceptable for now.
- **Duplication:** Significant duplication exists in **Watchdog** logic (legacy `agg_oco_watchdog.py` vs shadow `watchdog.py`) and **Gatekeeping** (legacy `fsm_open.py`/`qty_guard.py` vs shadow `gatekeeper.py`). This is intentional during the transition but requires cleanup.

**Conclusion:** The new directory structure is effectively a modular replacement for `ExecPosFSM`, but legacy modules must be explicitly deprecated and removed after the V2 switch to avoid "split brain" logic maintenance.

---

## 2. Responsibility Mapping

| Responsibility | Legacy (`fsm.py` & friends) | New (`shadow_execpos/`) | Status | Notes |
|----------------|-----------------------------|-------------------------|--------|-------|
| **Orchestration** | `ExecPosFSM.handle()` | `ExecPosRuntimeV2.handle()` | ✅ FULL | V2 handles all 6 core event types. |
| **Adapter Interaction** | `_execute_decision`, `_call_adapter_fn` | `ExecutionService` | ✅ FULL | All verbs (place, cancel, close) ported. |
| **Gatekeeping** | `fsm_open.py`, `qty_guard.py`, `soft_clip.py` | `ExecPosGatekeeper` | ⚠️ PARTIAL | Core guards ported. Legacy has complex "soft clip" logic not fully in V2 (V2 uses strict reject/round). |
| **Watchdog** | `_run_agg_oco_watchdog`, `agg_oco_watchdog.py` | `AggOcoWatchdogService` | ⚠️ DUPLICATED | Logic exists in both. Shadow is cleaner but legacy is still wired in prod. |
| **Idempotency** | `_resolve_idempotency_ttl`, `_is_duplicate_fill` | `FillIdempotency`, `EventIdempotency` | ✅ FULL | Shadow has dedicated, testable classes. |
| **Price Enrichment** | `_enrich_fill_price` | `PriceEnricher` | ✅ FULL | Logic ported and unit tested. |
| **Async Tasks** | `_submit_async`, `_shutdown_background_tasks` | `ExecPosAsyncManager` | ✅ FULL | Shadow manager mirrors legacy behavior. |
| **WAL Integration** | `_write_wal` | *None* | ⛔ NONE | V2 currently relies on upstream persistence or needs WAL added. |
| **Exposure Summary** | `_update_exposure_summary` | *None* | ⛔ NONE | Not critical for execution core, likely belongs in Risk domain. |

---

## 3. Duplication & Scattering Analysis

### 3.1 Watchdog Logic (High Risk)

**Legacy:**
- `apps/reference/domains/execution_position/agg_oco_watchdog.py`
- `ExecPosFSM._run_agg_oco_watchdog`
- `ExecPosFSM._confirm_agg_oco_violations`

**Shadow:**
- `apps/reference/domains/execution_position/shadow_execpos/watchdog.py`

**Findings:**
- Both define invariants: `NO_SL_FOR_OPEN_POSITION`, `ORPHAN_SL`, `TOO_MANY_SL`.
- Legacy has complex "suspicion/confirmation" logic (time-based debouncing).
- Shadow has simpler "analyze & recommend" logic.
- **Risk:** If someone updates invariants in legacy, they might forget shadow (and vice versa).

**Recommendation:**
- Make `shadow_execpos/watchdog.py` the **Canonical Owner** of invariants.
- Once V2 is active, delete `agg_oco_watchdog.py`.

### 3.2 Gatekeeping (Medium Risk)

**Legacy:**
- `fsm_open.py` (orchestrates checks)
- `qty_guard.py` (min qty, step size)
- `soft_clip.py` (price clipping)

**Shadow:**
- `shadow_execpos/gatekeeper.py`

**Findings:**
- Shadow `ExecPosGatekeeper` consolidates these checks into a single pipeline.
- Shadow uses "fail-fast" (reject) or "safe-round" approach.
- Legacy `soft_clip` tries to be "smart" about adjusting prices, which is complex and buggy.
- **Recommendation:** Stick to Shadow's strict validation. Deprecate `soft_clip.py`.

### 3.3 Idempotency (Low Risk)

**Legacy:**
- Inline logic in `ExecPosFSM`.

**Shadow:**
- `shadow_execpos/idempotency.py`

**Findings:**
- Shadow implementation is much cleaner and isolated.
- No risk of conflict as they don't share state.

---

## 4. Recommendations & Next Steps

### 4.1 Canonical Owners

| Module | Canonical Owner | Action |
|--------|-----------------|--------|
| Watchdog | `shadow_execpos/watchdog.py` | Deprecate `agg_oco_watchdog.py` |
| Gatekeeping | `shadow_execpos/gatekeeper.py` | Deprecate `qty_guard.py`, `soft_clip.py` |
| Execution | `shadow_execpos/execution_service.py` | Remove `_execute_decision` from fsm.py |
| Async | `shadow_execpos/async_manager.py` | Use this for all new async tasks |

### 4.2 Follow-up Tasks

1. **[EP-FSM-EXTRACTION-CLEANUP-S1]**
   - Once V2 is live in production (Phase M4), delete `agg_oco_watchdog.py`, `qty_guard.py`, `soft_clip.py`.
   - Remove `_execute_decision` and related helpers from `fsm.py`.

2. **[EP-WATCHDOG-CONSOLIDATION-S1]**
   - Ensure `shadow_execpos/watchdog.py` implements any missing "suspicion/confirmation" logic if deemed necessary for production stability (currently it's stateless).

3. **[EP-GATEKEEPER-COVERAGE-S1]**
   - Verify if `soft_clip.py` logic (smart price adjustment) is actually needed. If so, port to `ExecPosGatekeeper`. If not (preferred), confirm strict rejection is acceptable.

---

## 5. Conclusion

The `shadow_execpos` directory is a **viable, modular successor** to `ExecPosFSM`. The "gaps" (WAL, complex legacy guards) are largely intentional simplifications. The primary task now is to switch traffic to V2 (as per `EP-RUNTIME-SWITCH-PLAN-REV-S1`) and then aggressively delete the legacy code to eliminate the duplication risks identified above.
