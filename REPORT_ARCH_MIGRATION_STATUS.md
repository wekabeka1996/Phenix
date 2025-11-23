# Execution Position Domain: Migration Status Report

**Date:** 21 November 2025
**Auditor:** GitHub Copilot (Principal Software Architect)
**Subject:** Forensic Audit of `ExecPosFSM` to `ExecPosRuntimeV2` Migration

## 1. Executive Summary

The migration from the monolithic `ExecPosFSM` to the modular `ExecPosRuntimeV2` is **structurally complete but functionally regressed**. While the "God Object" `fsm.py` has been successfully purged, the legacy components (`fsm_manage.py`, `fsm_close.py`, `fsm_open.py`) remain in the codebase as "Zombie Logic"—dead in the hot path but alive in the repository and tests.

**Critical Finding:** The "Close Flow" migration is incomplete. The V2 runtime lacks the time-based exit logic ("Max Hold Time") that existed in the legacy `fsm_close.py`.

## 2. Migration Truth Table

| Feature | Documented Status | Actual Code Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Legacy FSM (`fsm.py`)** | Purged / Replaced | **PURGED**. File does not exist in domain folder. | ✅ **SUCCESS** |
| **Legacy Components** | `LEGACY_DOC_ONLY` | **ZOMBIE**. `fsm_manage.py` (~2400 LOC), `fsm_close.py`, `fsm_open.py` exist and are used in tests. | ⚠️ **PARTIAL** |
| **Runtime V2** | Active / Autonomous | **ACTIVE**. `ExecPosRuntimeV2` operates independently without importing legacy FSMs. | ✅ **SUCCESS** |
| **Close Flow** | "Not Ported" | **REGRESSED**. `CloseFlowService` exists but is passive. Auto-close on time (Max Hold) is **MISSING** in V2. | ❌ **FAILURE** |
| **Factory Switch** | V2 Default | **ENFORCED**. `runtime_factory.py` raises `ValueError` for "legacy" mode. | ✅ **SUCCESS** |

## 3. Zombie Logic Analysis

The following files are effectively dead code in production but remain in the repository, creating confusion and maintenance burden. They are marked `LEGACY_DOC_ONLY` in external documentation but lack code-level deprecation warnings.

| Component | File Path | LOC | Status |
| :--- | :--- | :--- | :--- |
| **Manage Flow** | `apps/reference/domains/execution_position/fsm_manage.py` | ~2400 | **Dead**. Not used by V2 Runtime. Used heavily in `tests/`. |
| **Open Flow** | `apps/reference/domains/execution_position/fsm_open.py` | ~320 | **Dead**. Not used by V2 Runtime. |
| **Close Flow** | `apps/reference/domains/execution_position/fsm_close.py` | ~167 | **Dead**. Not used by V2 Runtime. Contains missing "Max Hold" logic. |

**Recommendation:** Add `@deprecated` decorators to these classes immediately and schedule for deletion after porting tests to V2.

## 4. Close Flow Gap Investigation

The documentation states "Close Flow FSM is not ported". This is confirmed and represents a functional gap.

-   **Legacy (`fsm_close.py`):** Implements active monitoring of `UPD:TICK` events to enforce `max_hold_sec`.
    ```python
    # fsm_close.py
    if msg.op == "UPD" and msg.verb == "TICK":
        if elapsed > self.max_hold_sec:
            return self._emit_close(...)
    ```
-   **V2 (`shadow_execpos/runtime.py`):**
    -   Uses `CloseFlowService` (`shadow_execpos/close_flow.py`) which is **pure logic** (passive).
    -   `ExecPosRuntimeV2.handle()` **ignores** `UPD:TICK` events.
    -   `Watchdog` (`shadow_execpos/watchdog.py`) is **detect-only** and does not trigger closes.

**Impact:** Positions in V2 will **NEVER** auto-close based on time limits, unlike in the legacy system.

## 5. Blocking Dependencies

There are no code-level blocking dependencies preventing the deletion of `fsm_manage.py` and `fsm_open.py`. `ExecPosRuntimeV2` is fully decoupled.

However, `fsm_close.py` cannot be deleted until the "Max Hold Time" feature is ported to a V2 component (likely a new `TimeExitService` or an active loop in `ExecPosRuntimeV2`).

## 6. Conclusion

The architecture has successfully shifted to V2, but the migration left behind a significant amount of dead code and dropped a production feature (Time-based Exit).

**Immediate Actions Required:**
1.  **Port Time-based Exit:** Implement `UPD:TICK` handling in `ExecPosRuntimeV2` or a dedicated background task to restore `max_hold_sec` functionality.
2.  **Deprecate Zombies:** Add `@deprecated` to all `fsm_*.py` classes.
3.  **Cleanup Tests:** Refactor tests to target `ExecPosRuntimeV2` instead of legacy FSMs, then delete the legacy files.
