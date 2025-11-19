# ExecPosFSM / ManageFlowFSM Dead-Code Audit (2025-11-19)

Objective: highlight lines inside pps/reference/domains/execution_position/fsm.py
and sm_manage.py that are no longer referenced anywhere in the repository and can
be safely deleted without affecting runtime behaviour.

## 1. pps/reference/domains/execution_position/fsm.py

| Location | Symbol | Why removal is safe |
| --- | --- | --- |
| *(removed)* | _build_live_position_provider() | Deleted in the 2025-11-19 cleanup; no call sites remained after the ExecPosFSM refactor. ManageFlowFSM instances now operate without injected providers. |
| *(removed)* | _call_reduce_only_order() | Deleted in the cleanup; adapter invocations now call dapter.place_* directly while relying on _is_qty_rounding_error for guardrails. |
| *(removed)* | _is_cancel_success_response() | Deleted in the cleanup; timeout/cancel flows now interpret adapter responses inline, making the helper redundant. |
| *(removed)* | _is_unknown_order_error() | Deleted in the cleanup; unknown-order detection lives directly inside the timeout handler. |
| *(removed)* | _preflight_position_check_nonzero() | Deleted in the cleanup; _preflight_position_check() already provided the required semantics. |

## 2. pps/reference/domains/execution_position/fsm_manage.py

The current sm_manage.py does not contain standalone functions that lack call sites.
Every ManageFlowFSM method is referenced either by ExecPosFSM or by the dedicated
test suites (verified via g -n "<method_name>" -g"*.py"). Therefore there are no
safe deletions in this file at this time.

---

**Verification method**: for each candidate symbol above, g across the repository
returns only the definition line (no self.<symbol> usages), proving the code is
orphaned. Deleting these helpers affects no import, test, or runtime path. All other
methods in sm.py/sm_manage.py still have live call sites, so they must stay.
