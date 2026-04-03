# Bucket D DOGEUSDT Post-Watchdog Durable Truth Gap — 2026-04-01

## 0. Scope And Method
FACT: This report covers only the 7 Bucket D DOGEUSDT `mean_reversion` rows already proven to have websocket `status=FILLED`, websocket correlation miss, watchdog `POLLING DETECTED FILL`, and later lifecycle `ORPHANED_TTL`.

FACT: This report investigates only the path after watchdog `POLLING DETECTED FILL`.

FACT: Out of scope: strategy correctness, websocket-miss root cause before watchdog recovery, broad ORPHANED_TTL taxonomy outside these 7 rows, and code fixes.

FACT: Code anchors inspected for the post-watchdog path:
- `apps/reference/domains/execution_position/watchdog.py`
- `apps/reference/domains/execution_position/fsm.py`
- `vfoundation/core/fsm_emit_compat.py`
- `vfoundation/core/fsm_core.py`
- `apps/reference/domains/execution_position/event_handlers.py`
- `apps/reference/domains/position_tracking/position_tracking.py`
- `apps/reference/telemetry/shadow_journal.py`
- `apps/reference/domains/execution_position/open_executor.py`
- `apps/reference/domains/execution_position/bracket_manager.py`
- `apps/reference/domains/execution_position/order_guardian.py`

FACT: Runtime artifacts inspected by RID, `order_id`, and `client_order_id`:
- `logs/aurora_core.log.24`
- `logs/aurora_core.log.26`
- `logs/aurora_core.log.29`
- `logs/aurora_core.log.32`
- `logs/aurora_core.log.34`
- `logs/aurora_core.log.35`
- `logs/domain_execution_position.log.1`
- `logs/domain_execution_position.log.2`
- `logs/shadow_critical_event_journal_v1.jsonl`
- `logs/aurora_events.jsonl`
- `logs/trade_lifecycle.jsonl`
- `logs/order_guardian.log`

FACT: In the matrix below, `No` means `not proven in inspected runtime artifacts`. It is only a proof of absence where the artifact contract guarantees a record would exist if the hop had been reached.

## 1. Executive Verdict
FACT: For all 7 Bucket D DOGEUSDT rows, watchdog recovery is proven by `HTTP/1.1 200 OK` immediately followed by `POLLING DETECTED FILL`.

FACT: For all 7 rows, no post-watchdog `EVT:TRADE_EXECUTED` bus-ingress artifact exists in `logs/shadow_critical_event_journal_v1.jsonl` for the relevant `rid`, `order_id`, or `client_order_id`.

FACT: For all 7 rows, no post-watchdog consumer-receipt artifact exists in the relevant runtime windows: no `Handling EVT:TRADE_EXECUTED...`, no `Emitting EVT:PORTFOLIO_STATE_UPDATED...`, no lifecycle `FILLED`, and no `EVT:ORDER_STATE_CHANGED` terminal truth.

FACT: For all 7 rows, `logs/order_guardian.log` shows post-watchdog bracket registration, but the static call graph proves those registrations belong to the open/bracket-registration path and are not proof that watchdog `EVT:TRADE_EXECUTED` reached the event bus or consumers.

INFERENCE: The earliest shared missing downstream hop is no longer `somewhere after watchdog`. The strongest evidence-bounded boundary is `watchdog fill recovered -> event-bus ingress for EVT:TRADE_EXECUTED`.

UNKNOWN: The inspected artifacts do not prove whether the loss occurred because `self.emit_fn` was skipped, because the watchdog wrapper failed before `FSMCore.emit`, or because some unobserved branch bypassed the expected call.

## 2. Static Post-Watchdog Contract
FACT: `apps/reference/domains/execution_position/watchdog.py:set_hooks()` assigns `get_order_fn` and `emit_fn` together.

FACT: `apps/reference/domains/execution_position/watchdog.py` builds `fill_payload` with `orderId`, `clientOrderId`, `client_order_id`, `rid`, `side`, `quantity`, `price`, `ts`, `ts_ms`, and `venue`, then calls `await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)` on REST-detected fills.

FACT: `apps/reference/domains/execution_position/fsm.py` wires watchdog `emit_fn` to `emit_trade_executed()`, which wraps a `Message(op="EVT", verb="TRADE_EXECUTED", why="polling_fill")` and calls `emit_compat(self.fsm, msg, logger=LOG)`.

FACT: `vfoundation/core/fsm_core.py:emit()` normalizes `EVT:TRADE_EXECUTED`, then calls `shadow_journal.record_bus_emit(...)` before hardening and before listener callbacks.

FACT: `apps/reference/domains/position_tracking/position_tracking.py:on_trade_executed()` logs `Handling EVT:TRADE_EXECUTED...` before processing and writes portfolio-side durable truth afterward.

FACT: `apps/reference/domains/execution_position/event_handlers.py:on_trade_executed()` mirrors fill truth into `trade_lifecycle.on_fill(...)` on the execution hot path.

FACT: `apps/reference/telemetry/shadow_journal.py:record_bus_emit()` stores `EVT:TRADE_EXECUTED` with the payload identities extracted from `orderId`, `clientOrderId`, `client_order_id`, and `rid`.

FACT: `apps/reference/domains/execution_position/trade_executed_contracts.py:normalize_trade_executed_payload()` retains `orderId`, `clientOrderId`, `client_order_id`, and lower-cases side before listener processing.

FACT: `apps/reference/domains/execution_position/open_executor.py`, `apps/reference/domains/execution_position/bracket_manager.py`, and `apps/reference/domains/execution_position/order_guardian.py` show that `Entry registered` and `Bracket registered` belong to the entry/bracket placement path, not to the `EVT:TRADE_EXECUTED` consumer path.

INFERENCE: If watchdog fill recovery had reached `FSMCore.emit("EVT:TRADE_EXECUTED", ...)`, the shadow journal should show at least one `record_type="event"` `EVT:TRADE_EXECUTED` record for these identities even if later listeners failed.

## 3. Seven-Row Post-Watchdog Gap Matrix
| rid | order_id | watchdog_fill_anchor | runtime_emit_proven | bus_ingress_proven | consumer_receipt_proven | shadow_journal_terminal_persistence_proven | lifecycle_fill_update_proven | first_proven_missing_hop | key_post_watchdog_artifacts |
|---|---|---|---|---|---|---|---|---|---|
| rid-4c44c9b4e85b0009 | 762701737 | `logs/aurora_core.log.35:1891` at `2026-03-31 00:25:04,680` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:5-6` brackets only |
| rid-2aec3be5c5b62d7d | 762784661 | `logs/aurora_core.log.34:29717` at `2026-03-31 02:05:06,562` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:6095-6096` brackets only |
| rid-d866f7ca1e390571 | 762849386 | `logs/aurora_core.log.32:19915` at `2026-03-31 03:50:02,278` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:11767-11768` brackets only |
| rid-9e015bd410455284 | 762995235 | `logs/aurora_core.log.29:3362` at `2026-03-31 06:25:05,797` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:19509-19510` brackets only |
| rid-e5adcc2a7d67ffcb | 763146229 | `logs/aurora_core.log.26:4664` at `2026-03-31 09:25:06,402` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:29362-29363` brackets only |
| rid-d8cebaa4f1499864 | 763184591 | `logs/aurora_core.log.26:26040` at `2026-03-31 09:55:03,563` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:31182-31183` brackets only |
| rid-cc0c2230ed591c29 | 763343279 | `logs/aurora_core.log.24:20572` at `2026-03-31 11:45:05,360` | No | No | No | No | No | `watchdog fill -> EVT:TRADE_EXECUTED bus ingress` | `logs/order_guardian.log:37510-37511` brackets only |

## 4. Recovery Windows A
RID `rid-4c44c9b4e85b0009` / order `762701737`
FACT: `logs/aurora_core.log.35:1881` proves websocket `status=FILLED` at `2026-03-31 00:25:04,323`.
FACT: `logs/aurora_core.log.35:1882` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.35:1883-1884` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.35:1890-1891` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.35:1901-1902` and `logs/order_guardian.log:5-6` show bracket registration after the watchdog fill.
FACT: Targeted searches of `logs/shadow_critical_event_journal_v1.jsonl`, `logs/aurora_events.jsonl`, and the relevant `aurora_core` window show no `EVT:TRADE_EXECUTED`, no `Handling EVT:TRADE_EXECUTED`, and no lifecycle fill truth for this identity.

RID `rid-2aec3be5c5b62d7d` / order `762784661`
FACT: `logs/aurora_core.log.34:29699` proves websocket `status=FILLED` at `2026-03-31 02:05:05,379`.
FACT: `logs/aurora_core.log.34:29701` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.34:29702-29703` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.34:29716-29717` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.34:29722-29723` and `logs/order_guardian.log:6095-6096` show bracket registration after the watchdog fill.
FACT: No post-watchdog `EVT:TRADE_EXECUTED` bus, consumer, shadow, or lifecycle artifact is proven for this identity.

RID `rid-d866f7ca1e390571` / order `762849386`
FACT: `logs/aurora_core.log.32:19904` proves websocket `status=FILLED` at `2026-03-31 03:50:01,650`.
FACT: `logs/aurora_core.log.32:19906` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.32:19905-19907` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.32:19914-19915` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.32:19923-19924` and `logs/order_guardian.log:11767-11768` show bracket registration after the watchdog fill.
FACT: No post-watchdog `EVT:TRADE_EXECUTED` bus, consumer, shadow, or lifecycle artifact is proven for this identity.

## 5. Recovery Windows B
RID `rid-9e015bd410455284` / order `762995235`
FACT: `logs/aurora_core.log.29:3353` proves websocket `status=FILLED` at `2026-03-31 06:25:05,340`.
FACT: `logs/aurora_core.log.29:3355` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.29:3354-3356` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.29:3361-3362` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.29:3372-3373` and `logs/order_guardian.log:19509-19510` show bracket registration after the watchdog fill.
FACT: No post-watchdog `EVT:TRADE_EXECUTED` bus, consumer, shadow, or lifecycle artifact is proven for this identity.

RID `rid-e5adcc2a7d67ffcb` / order `763146229`
FACT: `logs/aurora_core.log.26:4653` proves websocket `status=FILLED` at `2026-03-31 09:25:05,982`.
FACT: `logs/aurora_core.log.26:4654` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.26:4655-4656` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.26:4663-4664` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.26:4706-4707` and `logs/order_guardian.log:29362-29363` show bracket registration after the watchdog fill.
FACT: No post-watchdog `EVT:TRADE_EXECUTED` bus, consumer, shadow, or lifecycle artifact is proven for this identity.

## 6. Recovery Windows C
RID `rid-d8cebaa4f1499864` / order `763184591`
FACT: `logs/aurora_core.log.26:26028` proves websocket `status=FILLED` at `2026-03-31 09:55:03,131`.
FACT: `logs/aurora_core.log.26:26030` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.26:26029-26031` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.26:26039-26040` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.26:26050-26051` and `logs/order_guardian.log:31182-31183` show bracket registration after the watchdog fill.
FACT: No post-watchdog `EVT:TRADE_EXECUTED` bus, consumer, shadow, or lifecycle artifact is proven for this identity.

RID `rid-cc0c2230ed591c29` / order `763343279`
FACT: `logs/aurora_core.log.24:20492` proves websocket `status=FILLED` at `2026-03-31 11:45:04,428`.
FACT: `logs/aurora_core.log.24:20495` immediately drops that truth via `No correlation found ... skipping`.
FACT: `logs/aurora_core.log.24:20496-20505` then show open-path placement completion and `Entry registered`.
FACT: `logs/aurora_core.log.24:20571-20572` prove `HTTP/1.1 200 OK` then watchdog `POLLING DETECTED FILL`.
FACT: `logs/aurora_core.log.24:20577-20578` and `logs/order_guardian.log:37510-37511` show bracket registration after the watchdog fill.
FACT: No post-watchdog `EVT:TRADE_EXECUTED` bus, consumer, shadow, or lifecycle artifact is proven for this identity.

## 7. Emit vs Dispatch vs Consumer vs Persistence vs Lifecycle
FACT: Runtime emit call-site exists in code, but there is no dedicated runtime line immediately before or after `await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)` for these 7 rows.

FACT: `vfoundation/core/fsm_core.py:emit()` records `shadow_journal.record_bus_emit(...)` before any listener callback.

FACT: Targeted searches by `rid`, `order_id`, and `client_order_id` show no `record_type="event"` `EVT:TRADE_EXECUTED` in `logs/shadow_critical_event_journal_v1.jsonl` for any of the 7 rows.

FACT: Targeted searches in the relevant `aurora_core` windows show no `Handling EVT:TRADE_EXECUTED...` and no `Emitting EVT:PORTFOLIO_STATE_UPDATED...` for these 7 rows.

FACT: Targeted searches show no post-watchdog `EVT:ORDER_STATE_CHANGED` artifact for these identities in `logs/shadow_critical_event_journal_v1.jsonl` or `logs/aurora_events.jsonl`.

FACT: `logs/trade_lifecycle.jsonl` keeps the original order placement timestamps for these rows and later sweeps them to `ORPHANED_TTL`; no lifecycle `FILLED` update is written.

FACT: `normalize_trade_executed_payload()` lower-cases side before listener processing, so raw watchdog side-case mismatch is not supported as the earliest shared seam.

INFERENCE: The common missing evidence boundary is upstream of consumer receipt, upstream of shadow/journal fill persistence, and upstream of lifecycle `on_fill(...)`.

## 8. Earliest Shared Missing Hop
FACT: For every row, the last proven shared post-watchdog truth is the watchdog line itself:
- `logs/aurora_core.log.35:1891`
- `logs/aurora_core.log.34:29717`
- `logs/aurora_core.log.32:19915`
- `logs/aurora_core.log.29:3362`
- `logs/aurora_core.log.26:4664`
- `logs/aurora_core.log.26:26040`
- `logs/aurora_core.log.24:20572`

FACT: For every row, the first artifact that should exist if the event bus had been reached is a shadow-journal `record_type="event"` `EVT:TRADE_EXECUTED` record, because `FSMCore.emit()` writes that record before listeners.

FACT: No such record exists for any of the 7 watchdog-recovered identities.

FACT: No consumer-start artifact exists either: no `Handling EVT:TRADE_EXECUTED...` in the relevant runtime windows.

INFERENCE: The earliest shared missing hop is `watchdog fill recovered -> event-bus ingress for EVT:TRADE_EXECUTED`.

UNKNOWN: The inspected artifacts do not prove the exact sub-hop inside that boundary:
- watchdog branch skipped `self.emit_fn`;
- watchdog invoked `emit_trade_executed()` but failed before `FSMCore.emit()`;
- some unobserved wrapper path diverted the event before the standard bus.

## 9. Plausible But Unproven Sub-Mechanisms
PLAUSIBLE BUT UNPROVEN: `self.emit_fn` was unexpectedly unset or bypassed at runtime for the watchdog fill branch, even though `get_order_fn` remained active.

PLAUSIBLE BUT UNPROVEN: `emit_trade_executed()` was invoked but an unobserved failure occurred before `FSMCore.emit()` could write `record_bus_emit(...)`.

PLAUSIBLE BUT UNPROVEN: Some alternate execution path handled post-watchdog fill recovery locally without emitting the canonical `EVT:TRADE_EXECUTED` event into the shared bus.

PLAUSIBLE BUT UNPROVEN: The bracket placements are contingent on entry/bracket-side orchestration and exchange position visibility, not on the canonical fill bus path, which is why they can coexist with missing durable truth.

WEAK AND NOT SUPPORTED: `PositionTracking` consumer failure due to uppercase side. The active runtime normalizer lower-cases side before listener callbacks.

WEAK AND NOT SUPPORTED: `shadow_journal` write failure as the common cause. No `Shadow journal emit capture failed` or related failure lines were found for these windows.

## 10. Closure Requirements
FACT: The current evidence is sufficient to answer the user’s narrow question at the boundary level: the durable-truth gap begins before event-bus ingress for watchdog-recovered `EVT:TRADE_EXECUTED`.

FACT: The current evidence is not sufficient to prove the exact internal sub-hop inside `watchdog -> event-bus ingress`.

Closure requires at least one additional artifact from inside that boundary:
- a runtime trace immediately before and after `await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)` in `watchdog.py`;
- a runtime trace at entry to `emit_trade_executed()` in `fsm.py` with the exact `order_id` and `client_order_id`;
- a runtime trace inside `FSMCore.emit()` before `record_bus_emit(...)` for `EVT:TRADE_EXECUTED`;
- a watchdog metric or audit line that explicitly records `emit_fn is None` or `emit_fn invoked` for the order;
- an event-bus middleware trace that can prove `emit_compat()` was called but never reached `FSMCore.emit()`.

INFERENCE: Without one of those artifact classes, the exact sub-hop remains unresolved, but the earliest shared missing downstream boundary is already identified with evidence.
