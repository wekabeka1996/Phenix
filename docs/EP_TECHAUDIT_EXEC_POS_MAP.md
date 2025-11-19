# EP-TECHAUDIT-EXEC-POS-MAP: Technical Debt & Duplication Map

**RID:** `EP-TECHAUDIT-EXEC-POS-MAP`
**Date:** 2025-11-19
**Status:** DRAFT

This document maps technical debt, duplicated logic, and async risk points in the `execution_position` domain following the `EP-STAB-*` stabilization phase.

---

## 1. Duplicated Logic

| Priority | Location (`file:line`) | Description | Recommendation |
| :--- | :--- | :--- | :--- |
| **P1** | `apps/reference/domains/execution_position/fsm_manage.py:1450` | **Live Position Parsing Duplication**: `_handle_aggregated_fill_event_aggregated_only` manually parses position snapshots (qty, price, side) instead of using the unified `PositionSnapshot` contract or `ExecPosFSM`'s resolver. | Refactor to use `contracts.PositionSnapshot` or inject a normalized snapshot. |
| **P2** | `apps/reference/domains/execution_position/fsm.py:330` vs `apps/reference/domains/execution_position/contracts.py:50` | **Position Resolution Overlap**: `_resolve_live_position_state` in FSM implements complex fallback logic that partially overlaps with `PositionSnapshot.from_rest_list`. | Consolidate resolution logic into a single helper in `contracts.py` or `utils.py`. |
| **P2** | `apps/reference/domains/execution_position/fsm_manage.py:1200` | **Exit Classification**: `_handle_aggregated_fill_event` manually checks `is_exit_order`. While it uses the contract, the surrounding logic for `is_exit_fill` vs `entry_fill` is scattered across multiple methods (`handle`, `_on_fill`, `_handle_aggregated_fill_event`). | Centralize fill handling logic to a single entry point that classifies the fill once. |

## 2. Legacy / Dead Code

| Status | Location (`file:line`) | Description | Recommendation |
| :--- | :--- | :--- | :--- |
| **Legacy** | `apps/reference/domains/execution_position/fsm_manage.py:650` | `_place_brackets_legacy`: Legacy bracket placement path. Raises `RuntimeError` if `aggregated_only_mode` is enabled. | **Candidate for removal** if `aggregated_only_mode` is permanently enabled. Otherwise, mark as deprecated. |
| **Legacy** | `apps/reference/domains/execution_position/fsm.py:630` | `_legacy_guardian_poll_interval`: Reads legacy config paths. | **Keep** for backward compatibility until config migration is complete. |
| **Deprecated** | `apps/reference/domains/execution_position/agg_oco_watchdog.py:60` | `WatchdogOrder.is_sl`: Marked as deprecated in favor of `exit_kind`. | **Remove** usages and the field itself. |
| **Legacy** | `apps/reference/domains/execution_position/agg_oco_watchdog.py:130` | `validate_agg_oco_invariants_result`: Legacy wrapper returning tuple. | **Inline** or remove if no longer used by external callers. |

## 3. Contract Drift

| Issue | Location | Source of Truth | Deviation |
| :--- | :--- | :--- | :--- |
| **Auto-Heal Logic** | `fsm.py:1150` vs `docs/CENTRAL_FSM_SPEC.md` | `fsm.py` | `_heal_no_sl_for_open_position` sends a fake `TRADE_EXECUTED` event. This is a "hack" to trigger `ManageFlowFSM`. The spec might not explicitly detail this "fake event" mechanism as the standard auto-heal path. |
| **Snapshot Stale Race** | `fsm_manage.py:1500` | `contracts.py` | `_handle_aggregated_fill_event_aggregated_only` detects stale snapshots (0 qty after entry fill) and forces fallback. This critical "anti-race" contract is buried deep in a specific handler rather than being a core FSM property. |

## 4. Async / FSM Risk Points

| Risk | Component | Description | Mitigation Status |
| :--- | :--- | :--- | :--- |
| **Infinite Auto-Heal Loop** | `fsm.py` ↔ `watchdog` | Cycle: `NO_SL` → `watchdog` → `autoheal` → `fake EVT` → `ManageFlow` → `place brackets` → `fail` → `NO_SL`. | **Partial**: `_autoheal_retry_counts` (line 1150) limits retries to 5 per 60s. However, if the failure persists > 60s, it will loop slowly forever. |
| **Pending Decisions Race** | `fsm_manage.py` | `consume_pending_decisions` clears the deque. If `handle` raises an exception *after* queuing decisions but *before* returning, those decisions might be lost or stuck if not carefully managed (though `finally` blocks aren't obvious in `handle`). | Ensure `consume_pending_decisions` is called in a `finally` block or guaranteed path in `ExecPosFSM`. |
| **Guardian Race** | `fsm.py` | `_schedule_guardian_start` is async. If `TRADE_EXECUTED` arrives before Guardian is fully started/reconciled, brackets might be skipped or duplicated. | `_guardian_start_scheduled` flag exists, but race window exists during startup. |

