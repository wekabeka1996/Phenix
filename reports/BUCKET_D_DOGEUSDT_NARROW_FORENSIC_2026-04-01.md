# Bucket D DOGEUSDT Narrow Forensic Report — 2026-04-01

## 0. Scope And Conflict Note
FACT: This report covers only the 7 Bucket D DOGEUSDT `mean_reversion` rows from `reports/ORPHANED_TTL_FORENSIC_REPORT.md`.

FACT: The earlier Bucket D statement `ORDER_PLACED -> no later proven execution event in inspected logs` is contradicted by broader runtime evidence gathered here.

FACT: This report does not reclassify Bucket B or Bucket E. It only resolves the post-`ORDER_PLACED` truth for the 7 Bucket D rows.

## 1. Executive Verdict
FACT: For all 7 Bucket D rows, the first proven terminal execution truth after `ORDER_PLACED` is websocket `ORDER_TRADE_UPDATE ... status=FILLED` in `logs/aurora_core.log.*`.

FACT: For all 7 Bucket D rows, the last proven terminal execution truth after `ORDER_PLACED` is watchdog `POLLING DETECTED FILL ... status=FILLED` in `logs/domain_execution_position.log*` and `logs/aurora_core.log.*`.

FACT: For all 7 Bucket D rows, the first proven place where websocket terminal truth is lost is the immediately adjacent warning `No correlation found for order ..., skipping` in `logs/aurora_core.log.*`.

FACT: For all 7 Bucket D rows, watchdog REST polling later recovers fill truth via `HTTP/1.1 200 OK` followed by `POLLING DETECTED FILL`.

FACT: For these same 7 rows, no later `EVT:TRADE_EXECUTED`, no later `EVT:ORDER_STATE_CHANGED`, and no later lifecycle `FILLED` or `CANCELLED` truth is proven in `logs/shadow_critical_event_journal_v1.jsonl`, `logs/aurora_events.jsonl`, or `logs/trade_lifecycle.jsonl`.

INFERENCE: Bucket D is not a `placed-with-no-later-execution-truth` family. The strongest evidence-bounded common family is `websocket fill truth observed -> websocket correlation miss -> watchdog fill recovery -> no later durable journal/lifecycle terminal truth`.

## 2. Bucket D RID-By-RID Matrix
| rid | order_id | ORDER_PLACED anchor | first proven terminal truth | last proven terminal truth | first proven seam | lifecycle outcome |
|---|---|---|---|---|---|---|
| rid-4c44c9b4e85b0009 | 762701737 | `logs/order_log_v1.jsonl:41` | `logs/aurora_core.log.35:1881` websocket `status=FILLED` at `2026-03-31 00:25:04,323` | `logs/domain_execution_position.log.2:4735` watchdog `status=FILLED` at `2026-03-31 00:25:04,680` | `logs/aurora_core.log.35:1882` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:2` -> `ORPHANED_TTL` |
| rid-2aec3be5c5b62d7d | 762784661 | `logs/order_log_v1.jsonl:52` | `logs/aurora_core.log.34:29699` websocket `status=FILLED` at `2026-03-31 02:05:05,379` | `logs/domain_execution_position.log.2:6764` watchdog `status=FILLED` at `2026-03-31 02:05:06,562` | `logs/aurora_core.log.34:29701` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:4` -> `ORPHANED_TTL` |
| rid-d866f7ca1e390571 | 762849386 | `logs/order_log_v1.jsonl:76` | `logs/aurora_core.log.32:19904` websocket `status=FILLED` at `2026-03-31 03:50:01,650` | `logs/domain_execution_position.log.2:8805` watchdog `status=FILLED` at `2026-03-31 03:50:02,278` | `logs/aurora_core.log.32:19906` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:6` -> `ORPHANED_TTL` |
| rid-9e015bd410455284 | 762995235 | `logs/order_log_v1.jsonl:87` | `logs/aurora_core.log.29:3353` websocket `status=FILLED` at `2026-03-31 06:25:05,340` | `logs/domain_execution_position.log.2:10882` watchdog `status=FILLED` at `2026-03-31 06:25:05,797` | `logs/aurora_core.log.29:3355` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:8` -> `ORPHANED_TTL` |
| rid-e5adcc2a7d67ffcb | 763146229 | `logs/order_log_v1.jsonl:116` | `logs/aurora_core.log.26:4653` websocket `status=FILLED` at `2026-03-31 09:25:05,982` | `logs/domain_execution_position.log.2:14426` watchdog `status=FILLED` at `2026-03-31 09:25:06,402` | `logs/aurora_core.log.26:4654` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:11` -> `ORPHANED_TTL` |
| rid-d8cebaa4f1499864 | 763184591 | `logs/order_log_v1.jsonl:122` | `logs/aurora_core.log.26:26028` websocket `status=FILLED` at `2026-03-31 09:55:03,131` | `logs/domain_execution_position.log.2:15059` watchdog `status=FILLED` at `2026-03-31 09:55:03,563` | `logs/aurora_core.log.26:26030` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:12` -> `ORPHANED_TTL` |
| rid-cc0c2230ed591c29 | 763343279 | `logs/order_log_v1.jsonl:151` | `logs/aurora_core.log.24:20492` websocket `status=FILLED` at `2026-03-31 11:45:04,428` | `logs/domain_execution_position.log.1:1955` watchdog `status=FILLED` at `2026-03-31 11:45:05,360` | `logs/aurora_core.log.24:20495` `No correlation found ... skipping` | `logs/trade_lifecycle.jsonl:13` -> `ORPHANED_TTL` |

## 3. Post-ORDER_PLACED Lineage Findings
FACT: `logs/order_log_v1.jsonl` shows only `ORDER_INTENT` and `ORDER_PLACED` for these 7 RIDs: `40-41`, `51-52`, `75-76`, `86-87`, `115-116`, `121-122`, `150-151`.

FACT: `logs/aurora_core.log.*` proves `ORDER_TRADE_UPDATE ... status=NEW` and later `ORDER_TRADE_UPDATE ... status=FILLED` for all 7 orders.

FACT: For all 7 orders, the `status=FILLED` websocket truth is immediately followed by `No correlation found for order ..., skipping`:
- `762701737` -> `logs/aurora_core.log.35:1882`
- `762784661` -> `logs/aurora_core.log.34:29701`
- `762849386` -> `logs/aurora_core.log.32:19906`
- `762995235` -> `logs/aurora_core.log.29:3355`
- `763146229` -> `logs/aurora_core.log.26:4654`
- `763184591` -> `logs/aurora_core.log.26:26030`
- `763343279` -> `logs/aurora_core.log.24:20495`

FACT: `logs/domain_execution_position.log*` separately proves both market placement and watchdog REST fill recovery for all 7 orders, with exactly 14 order-id hits total: one `MARKET entry placed` and one `POLLING DETECTED FILL` per order.

FACT: `logs/event_chain.log` proves downstream order-guardian activity for all 7 RIDs: one `Entry registered` and two later `Bracket registered` events per RID.

FACT: Targeted searches of `logs/shadow_critical_event_journal_v1.jsonl` by RID and by exchange `order_id` return only pre-fill and placement-side records for these 7 orders: `ORDER_INDEX:RESERVE_ENTRY`, `ORDER_INDEX:UPSERT_OPEN`, `ORDER_INDEX:ATTACH_EXCHANGE_ID`, and `EVT:ORDER_PLACED`.

FACT: No `EVT:TRADE_EXECUTED` or `EVT:ORDER_STATE_CHANGED` is proven for these 7 RIDs or order_ids in `logs/shadow_critical_event_journal_v1.jsonl`.

FACT: `logs/aurora_events.jsonl` contains no matches for these 7 RIDs or these 7 exchange `order_id` values.

FACT: `logs/trade_lifecycle.jsonl` still ends all 7 rows as `ORPHANED_TTL` with `TTL_EXPIRED_3600s`.

## 4. Watchdog Hypothesis Assessment
FACT: All 7 orders reached watchdog REST polling success via `HTTP/1.1 200 OK` and later `POLLING DETECTED FILL`.

FACT: No inspected runtime line for these 7 order_ids proves watchdog `not found`, watchdog `cancel`, watchdog `expired`, or `ORDER_TIMEOUT` as the common execution-side explanation.

FACT: The earlier Bucket D interpretation `placed -> no later proven execution truth -> probably watchdog silent drop` is contradicted for these 7 rows by direct runtime evidence.

INFERENCE: The watchdog `not-found` branch is not the strongest proven common pattern for these 7 rows.

UNKNOWN: A later watchdog-side propagation failure after `POLLING DETECTED FILL` is still possible, but it is not directly proven in the inspected logs.

## 5. FSM State-Leak Assessment
FACT: `apps/reference/domains/execution_position/fsm.py` wires watchdog `emit_fn` through `emit_trade_executed`, and `apps/reference/domains/execution_position/watchdog.py` calls `await self.emit_fn("EVT:TRADE_EXECUTED", fill_payload)` on REST-detected fills when `emit_fn` is set.

FACT: `apps/reference/domains/execution_position/event_handlers.py:on_trade_executed()` calls `_trade_lifecycle.on_fill(...)` on the hot path when `EVT:TRADE_EXECUTED` reaches the handler.

FACT: Despite that static contract, no later `EVT:TRADE_EXECUTED`, no later `EVT:ORDER_STATE_CHANGED`, and no lifecycle `FILLED` record is proven for these 7 orders in the inspected runtime artifacts.

FACT: `apps/reference/telemetry/trade_lifecycle_logger.py:sweep_expired()` later marks any still-non-terminal record as `ORPHANED_TTL`.

INFERENCE: The durable state seam for these 7 rows lies downstream of raw exchange truth and downstream of watchdog fill recovery, but the inspected runtime artifacts do not prove the exact missing hop.

UNKNOWN: The inspected evidence cannot prove whether the missing durable state was never emitted, emitted and dropped later, emitted under another identity, or emitted outside the inspected artifacts.

## 6. Exchange / WS Gap Assessment
FACT: Exchange truth is not silent for these 7 rows. Both websocket and REST polling prove `FILLED`.

FACT: The websocket gap is a correlation gap, not a venue-silence gap. `apps/reference/adapters/binance_ws_client.py` looks up `order_ref` by `clientOrderId` or `exchangeOrderId`, logs `No correlation found for order ..., skipping`, and returns early when lookup fails.

FACT: The first proven truth-loss event after `ORDER_PLACED` is therefore the websocket correlation miss, not missing exchange terminal truth.

INFERENCE: `websocket gap` is the correct high-level family label only if it is understood as `websocket correlation / identity gap`, not `websocket transport silence`.

## 7. First Proven Seam Per RID
| rid | first proven seam | seam anchor | classification |
|---|---|---|---|
| rid-4c44c9b4e85b0009 | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.35:1882` | `websocket correlation miss after FILLED` |
| rid-2aec3be5c5b62d7d | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.34:29701` | `websocket correlation miss after FILLED` |
| rid-d866f7ca1e390571 | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.32:19906` | `websocket correlation miss after FILLED` |
| rid-9e015bd410455284 | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.29:3355` | `websocket correlation miss after FILLED` |
| rid-e5adcc2a7d67ffcb | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.26:4654` | `websocket correlation miss after FILLED` |
| rid-d8cebaa4f1499864 | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.26:26030` | `websocket correlation miss after FILLED` |
| rid-cc0c2230ed591c29 | websocket FILLED truth dropped on correlation | `logs/aurora_core.log.24:20495` | `websocket correlation miss after FILLED` |

## 8. Strongest Proven Common Pattern
FACT: All 7 rows fit the same evidence-bounded sequence:
1. `ORDER_INTENT` in `logs/order_log_v1.jsonl`.
2. `ORDER_PLACED` in `logs/order_log_v1.jsonl`.
3. Websocket `ORDER_TRADE_UPDATE ... status=NEW` in `logs/aurora_core.log.*`.
4. Websocket `No correlation found for order ..., skipping`.
5. Websocket `ORDER_TRADE_UPDATE ... status=FILLED` in `logs/aurora_core.log.*`.
6. Another websocket `No correlation found for order ..., skipping`.
7. REST `GET /fapi/v1/order ... HTTP/1.1 200 OK`.
8. Watchdog `POLLING DETECTED FILL ... status=FILLED`.
9. Order guardian `Entry registered` and later both bracket registrations.
10. No later durable terminal event found in `shadow_critical_event_journal_v1.jsonl` or `aurora_events.jsonl`.
11. Lifecycle later collapses to `ORPHANED_TTL`.

INFERENCE: The strongest proven common pattern is `terminal execution truth exists twice` (WS and REST watchdog) but is not preserved as later durable journal/lifecycle truth for these 7 rows.

## 9. Plausible But Unproven Mechanisms
PLAUSIBLE BUT UNPROVEN: `OrderIndex` state existed in one component but was unavailable to the websocket handler instance at the time of `ORDER_TRADE_UPDATE`, producing the correlation miss.

PLAUSIBLE BUT UNPROVEN: Watchdog emitted `EVT:TRADE_EXECUTED`, but the message was dropped, de-duplicated, or failed before it became durable shadow-journal or lifecycle truth.

PLAUSIBLE BUT UNPROVEN: Watchdog filled the order and performed local `on_order_fill(order_id)` cleanup, but durable event propagation failed afterward.

PLAUSIBLE BUT UNPROVEN: Durable events were emitted under a different identity that cannot be recovered from the inspected RID / order_id / client_order_id anchors.

PLAUSIBLE BUT UNPROVEN: Guardian bracket registration may rely on local fill handling that is not sufficient, by itself, to guarantee lifecycle `FILLED` durability.

UNKNOWN: The inspected evidence does not prove an explicit FSM state removal, an explicit FSM stuck state, or an explicit object deletion point for these 7 rows.

## 10. What Additional Artifacts Are Required For Closure
FACT: The current evidence is sufficient to overturn the old Bucket D claim and sufficient to place the first seam at websocket correlation miss.

FACT: The current evidence is not sufficient to prove the exact downstream hop where watchdog-recovered fill truth stopped becoming durable lifecycle truth.

Closure requires at least one of the following additional artifacts:
- runtime bus emission trace around watchdog `emit_trade_executed()` for these exact 7 order_ids;
- point-in-time `OrderIndex` snapshot or trace at each websocket `status=FILLED` timestamp;
- shadow-journal instrumentation or emit-compat trace around the watchdog fill window for these order_ids;
- consumer-side traces from `position_tracking` / monitoring for `EVT:TRADE_EXECUTED` keyed by these order_ids or client order ids;
- any raw adapter or middleware error logs that would show watchdog emit failure or journal write failure in the same windows.

INFERENCE: Without one of those artifact classes, the exact downstream loss point after watchdog recovery remains unresolved.
