# POSITION_CLOSED_PRODUCER_MAP

Package: 03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR

## Summary

| path | symbol | classification | runtime surface | note |
| --- | --- | --- | --- | --- |
| apps/reference/domains/execution_position/orchestration/event_handlers.py | EPEventHandlers.on_portfolio_state_updated | canonical_POSITION_CLOSED_producer | trade_lifecycle.on_close, order_log POSITION_CLOSED, EVT:POSITION_CLOSED | Fires only on the portfolio edge abs(prev_amt) >= epsilon and abs(now_amt) < epsilon. |
| apps/reference/domains/execution_position/fsm.py | ExecPosFSM._on_execution_close_reconciled | canonical_POSITION_CLOSED_producer | trade_lifecycle.on_close, order_log POSITION_CLOSED, EVT:POSITION_CLOSED | Added in 03T for closes that reconcile without a visible portfolio edge, gated by cached close-fill truth. |
| apps/reference/domains/execution_position/guardian/order_guardian.py | _emit_close_reconciled_event | authoritative_close_reconcile_trigger | EVT:EXECUTION_CLOSE_RECONCILED | Trigger only; no canonical close write by itself. |
| apps/reference/domains/execution_position/contract_layer/terminal_order_contracts.py | sync_trade_lifecycle_terminal_order_event | trade_lifecycle_producer_only | trade_lifecycle.on_cancel, trade_lifecycle.on_reject | Terminal non-fill lifecycle sync only. |
| apps/reference/domains/execution_position/flows/close/close_executor.py | _tracked_teardown_log_success, _reconcile_cancel_log_success | alternative_terminal_event_producer | ORDER_CANCELLED, ORDER_CANCELLATION_FAILED | Close-related cancellation observability, not realized close truth. |
| apps/reference/domains/execution_position/sidecar/position_policy_mediator.py | _emit_position_policy_close_request_state | trade_lifecycle_producer_only | append_trade_lifecycle_record(POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE) | Sidecar request-state logging only. |
| apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py | on_execution_close_reconciled | trade_lifecycle_adjacent_non_producer | sidecar state evaluation | Consumes reconciliation without canonical close emission. |
| apps/reference/domains/execution_position/state/startup_truth_orchestrator.py | _append_restart_truth_record | trade_lifecycle_producer_only | append_trade_lifecycle_record(execution_restart_truth) | Restart observability only. |
| apps/reference/domains/execution_position/fsm_manage.py | module shim | compatibility_shim_non_producer | none | Re-export only. |
| apps/reference/domains/execution_position/schemas/position_closed_v1.json | schema | schema_only | none | Contract only. |

## Local Verdict

The runtime had one historical canonical producer for POSITION_CLOSED parity: the portfolio non-zero to zero detector in event_handlers.py. The authoritative close reconcile path in fsm.py already reset local execution state but did not emit canonical close truth. 03T adds parity only to that reconcile seam and only when cached close-fill truth already exists.

## SSOT Note

Copilot_Master_Roadmap.md did not contain an explicit 03T entry. The package boundary was therefore anchored to verified execution_position runtime evidence and the existing 03R close-surface artifacts.
