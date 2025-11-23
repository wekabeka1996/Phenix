# Execution Position Domain: Group Analysis & Audit

---
**HISTORICAL NOTE (2025-11-21 - EP-LEGACY-PURGE-S1)**

This document was written before legacy ExecPosFSM was removed.
ExecPosRuntimeV2 is now the only active execution runtime.
This document is preserved for historical context.

See: `docs/EXEC_POS_RUNTIME_STATE.md` for current state.
---

**Date:** 2025-05-20 (Updated 2025-11-21)
**Scope:** pps/reference/domains/execution_position
**Status:** Phase 1 (Analysis) REVISED following Critical Audit

## 1. Executive Summary: The "Legacy vs. Shadow" Split

The Execution Position domain is currently in a **transitional state**. It features two distinct, parallel runtime architectures:

1.  **Legacy FSM Runtime (sm_*.py)**: The currently active, monolithic state machine architecture. It handles live trading, state management, and decision execution.
2.  **Shadow V2 Runtime (shadow_execpos/)**: A modern, modular re-implementation designed to replace the legacy FSMs.

**Critical Finding (REVISED):** There is **Partial Overlap (~60%)** between these two systems, NOT 100% duplication.
*   **Entry Logic**: High parity (~95%). Gatekeeper is a clean port of sm_open.py.
*   **Execution**: High parity. Both use BinanceExecutionAdapter.
*   **Bracket/Close Logic**: **Major Divergence**. Shadow V2 is missing Aggregated OCO, Close Flow, and Trailing Stop logic entirely.

**Risk Assessment:**
*   **Critical**: Attempting to switch to Shadow V2 now would result in **loss of critical features** (Aggregated OCO, Auto-heal, Trailing Stops).
*   **High**: The "Watchdog" in Shadow V2 is semantically different from the Legacy Watchdog (Invariant Checker vs Timeout Monitor).

---

## 2. Group A: Runtime & State (Deep Dive)

This group contains the core business logic.

| Feature | Legacy Component (Active) | Shadow V2 Component (Future) | Status |
| :--- | :--- | :--- | :--- |
| **Orchestration** | sm_manage.py (God Object) | shadow_execpos/runtime.py | **Divergent** (Shadow is event-driven) |
| **Entry Logic** | sm_open.py | shadow_execpos/gatekeeper.py | **Parity Verified** |
| **Bracket Logic** | sm_manage._place_brackets_aggregated |  **MISSING** | **Critical Gap** |
| **Close Logic** | sm_close.py |  **MISSING** | **Critical Gap** |
| **Trailing Stops** | sm_manage._check_rules |  **MISSING** | **Critical Gap** |
| **Watchdog** | watchdog.py (Timeouts) | shadow_execpos/watchdog.py (Invariants) | **Different Purpose** |

### Key Files Analysis

*   **sm_manage.py**: A 2600+ LOC monolithic state machine. It couples state tracking, config resolution, and complex OCO logic.
*   **shadow_execpos/runtime.py**: A clean but incomplete skeleton. It lacks the "business rules" for managing open positions.
*   **shadow_execpos/gatekeeper.py**: The success story. It correctly implements the fail-closed guards from sm_open.py.

---

## 3. Group B: Adapters & Ports

This group handles external connectivity.

*   **inance_execution_adapter.py**: The shared foundation.
*   **shadow_execpos/event_adapter.py**: A translation layer specific to V2.

---

## 4. Missing Critical Components

The initial scan missed these dependencies which are vital for the Legacy system:

*   **pps/reference/services/order_guardian.py**: Manages bracket set registration and safety.
*   **racket_aggregator.py** (Location TBD): Core logic for computing OCO levels.
*   **gg_oco_watchdog.py**: The likely inspiration for the Shadow Watchdog.

---

## 5. Test Footprint & Coverage

*   **Legacy Tests**: Extensive coverage of the complex FSM logic (	est_fsm_manage.py).
*   **Shadow Tests**: Good coverage of the *ported* components (	est_gatekeeper_ported_logic.py), but **zero coverage** for the missing features (obviously).

---

## 6. Recommendations (Revised)

1.  **Do NOT Freeze Legacy Yet**: It is the only functional runtime for complex strategies.
2.  **Incremental Extraction**:
    *   Adopt Gatekeeper (it's ready).
    *   Adopt ExecutionService (it's ready).
3.  **Feature Porting Required**:
    *   Port Aggregated OCO logic to a standalone service.
    *   Port Close Flow logic to Shadow V2.
4.  **Dead Code**:
    *   	est_no_execpos_legacy_runtime.py is confirmed orphan.
