# POSITION_CLOSED_EMISSION_FLOW

Package: 03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR

## Flow Reconstruction

1. Close fills populate per-symbol economic truth in EPEventHandlers._remember_close_accounting_truth().
2. Historically, canonical POSITION_CLOSED parity depended on EPEventHandlers.on_portfolio_state_updated() observing abs(prev_amt) >= epsilon and abs(now_amt) < epsilon.
3. When that portfolio edge was missed, trade_lifecycle rows could still later appear terminal because ORPHANED_TTL records carry close_ts_ms and therefore count as terminal-close evidence in the 03R audit.
4. Separately, guardian/order ownership logic could emit EVT:EXECUTION_CLOSE_RECONCILED and ExecPosFSM._on_execution_close_reconciled() would reset local execution state without writing canonical POSITION_CLOSED.
5. 03T adds a bounded reuse of the canonical emission helper on EXECUTION_CLOSE_RECONCILED, but only when cached close-fill truth already exists.

## Explicit Answers

| question | answer |
| --- | --- |
| What closes the position? | Execution-side fills and guardian reconciliation. The portfolio path only detects closure after the fact. |
| What writes trade_lifecycle terminal close? | The portfolio edge path and, after 03T, the reconcile parity path both call trade_lifecycle.on_close. Terminal non-fill paths call trade_lifecycle.on_cancel/on_reject instead. |
| What writes order_log POSITION_CLOSED? | Historically only the portfolio edge path. After 03T, the reconcile path can also write it via the shared helper when close truth is cached. |
| Are they the same path? | Not historically. That split was the core observability defect. |
| What suppresses order_log emission? | Missing portfolio edge, reset-only reconcile handling, and best-effort exception swallowing around trade_lifecycle/order_logger writes. |
| What emits ORDER_CANCELLED / ORDER_TIMEOUT instead? | close_executor teardown/reconcile cancel helpers and terminal non-fill contract-layer routing. |
| Are economics, rid, and lifecycle_id available? | Yes on the helper path if close-fill truth and lifecycle caches were populated first. No in the bare EXECUTION_CLOSE_RECONCILED payload alone. |
| Can schema validation block the write? | Not in the helper itself. The main failure mode is best-effort logging that swallows exceptions. |

## Minimal Safe Verdict

The proved 03T defect was not a builder bridge problem. It was a runtime split where authoritative close reconciliation could end the lifecycle locally without emitting the same canonical close truth that the portfolio-edge path emitted.
