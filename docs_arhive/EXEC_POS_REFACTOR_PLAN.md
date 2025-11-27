# Execution Position Refactor & Cleanup Plan (REVISED)

> **ARCHIVED (historical):** Pre-V2 migration plan. ExecPosRuntimeV2 is now canonical. For current behavior and runtime contracts see `docs/EXEC_POS_V2_RUNTIME_SPEC.md`. Use this document only for historical context of the extraction/porting effort.

**Date:** 2025-11-21
**Status:** REVISED (Post-Audit)
**Based on:** Critical Audit Review of Legacy vs. Shadow V2

## 1. Context & Objectives

The initial plan to "Switch to Shadow V2" was based on the incorrect assumption that Shadow V2 was a complete port of the Legacy FSM. The Critical Audit revealed that Shadow V2 is missing ~40% of critical features (Aggregated OCO, Close Flow, Trailing Stops).

**New Objective:** Perform an **Incremental Module Extraction** and **Feature Porting** campaign. We will extract stable components (Gatekeeper) first, then port the missing complex logic, and only then attempt a runtime switch.

**Principles:**
- **No Big Bang**: Do not switch runtimes until feature parity is proven via A/B replay.
- **Extract, Don't Rewrite**: Move logic from `fsm_manage.py` to standalone services (`BracketService`) that can be used by *both* runtimes.
- **Safety**: Legacy FSM remains the source of truth for live trading.

---

## 2. Epics & Themes

### Epic 1: Component Extraction (Low Risk)
**Goal**: Validate and adopt the components that *are* ready in Shadow V2.
**Scope**: `Gatekeeper`, `ExecutionService`.

### Epic 2: Missing Feature Porting (High Risk)
**Goal**: Port the complex logic missing from Shadow V2 into modular services.
**Scope**: Aggregated OCO, Close Flow, Trailing Stops.

### Epic 3: Orchestration Rewrite (Highest Risk)
**Goal**: Update Shadow V2 Runtime to use the new services and match Legacy behavior.
**Scope**: `shadow_execpos/runtime.py`.

### Epic 4: Cleanup & Tech Debt
**Goal**: Remove dead code and fix documentation.

---

## 3. Task Backlog

### Epic 1: Component Extraction

| ID | Title | Priority | Risk | Scope | DoD Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EP-EXTRACT-GATEKEEPER-S1** | Adopt Gatekeeper in Legacy | **P1** | Low | `fsm_open.py` | Legacy FSM calls `Gatekeeper.check_entry()` instead of internal guards. |
| **EP-EXTRACT-EXEC-SVC-S1** | Adopt ExecutionService | **P1** | Low | `fsm.py` | Legacy FSM uses `ExecutionService` wrapper instead of direct adapter calls. |

### Epic 2: Missing Feature Porting

| ID | Title | Priority | Risk | Scope | DoD Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EP-PORT-BRACKETS-S1** | Extract Bracket Logic | **P0** | High | `fsm_manage.py` | `_place_brackets_aggregated` moved to `BracketService`. |
| **EP-PORT-CLOSE-S1** | Port Close Flow | **P0** | High | `fsm_close.py` | Close logic ported to `shadow_execpos/close_handler.py`. |
| **EP-PORT-TRAILING-S1** | Port Trailing Stops | **P1** | High | `fsm_manage.py` | Trailing logic moved to `TrailingStopService`. |

### Epic 3: Orchestration Rewrite

| ID | Title | Priority | Risk | Scope | DoD Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EP-RUNTIME-AB-TEST-S1** | A/B Replay Test Suite | **P0** | Medium | `tests/` | Test harness feeding same inputs to both runtimes and comparing outputs. |
| **EP-RUNTIME-WIRING-S1** | Wire New Services to V2 | **P1** | High | `runtime.py` | Shadow V2 uses the new `BracketService` and `CloseHandler`. |

### Epic 4: Cleanup

| ID | Title | Priority | Risk | Scope | DoD Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **EP-TEST-CLEANUP-S1** | Remove Orphan Tests | **P2** | Low | `tests/` | `test_no_execpos_legacy_runtime.py` deleted. |
| **EP-DOC-MAP-S1** | Update Component Map | **P1** | Low | `docs/` | Document `OrderGuardian` and `bracket_aggregator` dependencies. |

---

## 4. Suggested Execution Order

1.  **Immediate**:
    *   `EP-TEST-CLEANUP-S1`: Easy cleanup.
    *   `EP-DOC-MAP-S1`: Fix the documentation gaps.

2.  **Phase 1 (Extraction)**:
    *   `EP-EXTRACT-GATEKEEPER-S1`: Prove that shared components work.

3.  **Phase 2 (Porting)**:
    *   `EP-PORT-BRACKETS-S1`: The hardest task. Extracting the "God Method" `_place_brackets_aggregated`.

4.  **Phase 3 (Verification)**:
    *   `EP-RUNTIME-AB-TEST-S1`: Prove parity before switching.

## 5. Notes for Automation

*   **Copilot** is essential for `EP-PORT-BRACKETS-S1` to safely refactor the large method into a class.
*   **Agents** can handle `EP-TEST-CLEANUP-S1`.
