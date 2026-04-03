# ORPHANED_TTL Forensic Investigation Report — Revised

> Scope Note (2026-04-01 narrow Bucket D re-investigation)
>
> FACT: Bucket D conclusions in this report are superseded by `reports/BUCKET_D_DOGEUSDT_NARROW_FORENSIC_2026-04-01.md`.
>
> FACT: Broader runtime artifacts now prove websocket `status=FILLED` and later watchdog `POLLING DETECTED FILL` for all 7 Bucket D DOGEUSDT `mean_reversion` rows.
>
> FACT: Keep this report for the broader B / D / E inventory only; do not use Section 6 as the current Bucket D terminal-truth conclusion.

## 1. Executive Verdict
FACT: After contradiction audit and source-of-truth re-resolution, the RID inventory remains `22` rows with bucket counts `B=14`, `D=7`, `E=1`.

FACT: The revised report no longer conflicts with the shared Aurora SHORT-under-TREND_UP matrix on the seven shared Aurora RIDs. The authoritative side for all seven shared rows is `SELL`, not a mixed `BUY`/`SELL` set.

FACT: `ORPHANED_TTL` is written by `apps/reference/telemetry/trade_lifecycle_logger.py` inside `sweep_expired()` when a tracked record remains non-terminal past `orphan_ttl_sec`; it is not itself authoritative execution truth.

FACT: Bucket `B` proves `filled -> later lifecycle TTL collapse`. It does not, by itself, prove `filled -> definitely still-live position merely held > 1h`.

FACT: Bucket `D` proves `ORDER_PLACED -> no later proven execution event in inspected logs -> later lifecycle TTL collapse`. It does not, by itself, prove the precise watchdog branch that caused the gap.

FACT: Bucket `E` proves one explicit execution cancel chain that later ended as `ORPHANED_TTL` in lifecycle.

INFERENCE: The cleanest evidence-bounded conclusion is that `ORPHANED_TTL` currently conflates at least three different realities: fill-without-later-lifecycle-resolution, placed-without-later-proven-execution-truth, and cancel-without-lifecycle-cancel-resolution.

## 2. Detected Contradictions in Prior Report
FACT: The prior report contained seven side contradictions against the current inventory and execution-boundary logs:
- `aurora_BTCUSDT_1774907700267`
- `aurora_ETHUSDT_1774914001604`
- `aurora_SOLUSDT_1774956301297`
- `aurora_SOLUSDT_1774971900901`
- `aurora_ETHUSDT_1774982101125`
- `aurora_BTCUSDT_1774986900860`
- `aurora_ETHUSDT_1775013603304`

FACT: Three of those seven rows also contradicted the current shared Aurora RID matrix directly:
- `aurora_ETHUSDT_1774982101125`
- `aurora_BTCUSDT_1774986900860`
- `aurora_ETHUSDT_1775013603304`

FACT: No bucket-count contradiction was found. The corrected report preserves the bucket counts `B=14`, `D=7`, `E=1`.

FACT: No filled-versus-non-filled contradiction was found in the old table once authoritative fill truth was resolved from `order_log_v1.jsonl`, `aurora_events.jsonl`, and lifecycle fallback only where needed.

FACT: The prior report used a weaker event taxonomy for 15 of 22 rows. In practice, it often used `TRADE_EXECUTED` where a stronger execution-side source proved `ORDER_STATE_CHANGED:FILLED`, and it used `ORDER_CANCELLED` where the stronger venue-state source proved `ORDER_STATE_CHANGED:CANCELED`.

FACT: The prior report also overstated several mechanisms as facts even though the supporting evidence was only code-path plausibility.

INFERENCE: The main problem in the prior report was not the RID inventory itself. The main problem was source-of-truth selection and over-strong mechanism language.

## 3. Source-of-Truth Resolution Rules
FACT: For this revision, authoritative `side` is taken from the earliest `ORDER_INTENT` or `ORDER_PLACED` row in `logs/order_log_v1.jsonl` when present.

FACT: For this revision, authoritative `filled_yes_no` is taken from the strongest proven execution state in `logs/aurora_events.jsonl` or `logs/order_log_v1.jsonl`. Lifecycle `fill_ts_ms` is used only as fallback when no stronger execution event exists.

FACT: For this revision, `last_proven_execution_event` is chosen by semantic rank, not by raw timestamp order alone. Terminal or filled states outrank later asynchronous `ORDER_PLACED` logging. The ranking used is: `CANCELED/REJECTED/EXPIRED > TIMEOUT > FILLED > PARTIALLY_FILLED > ORDER_PLACED > ORDER_INTENT`.

FACT: For this revision, `lifecycle_terminal_label` is authoritative only from `logs/trade_lifecycle.jsonl`.

FACT: The following source table records the authoritative source used for every RID.

| rid | side_source | fill_source | last_event_source | lifecycle_source |
|---|---|---|---|---|
| rid-4c44c9b4e85b0009 | order_log_v1.jsonl:40 | order_log_v1.jsonl:41 | order_log_v1.jsonl:41 | trade_lifecycle.jsonl:2 |
| aurora_BTCUSDT_1774907700267 | order_log_v1.jsonl:44 | aurora_events.jsonl:1 | aurora_events.jsonl:1 | trade_lifecycle.jsonl:3 |
| rid-2aec3be5c5b62d7d | order_log_v1.jsonl:51 | order_log_v1.jsonl:52 | order_log_v1.jsonl:52 | trade_lifecycle.jsonl:4 |
| aurora_ETHUSDT_1774914001604 | order_log_v1.jsonl:61 | aurora_events.jsonl:4 | aurora_events.jsonl:4 | trade_lifecycle.jsonl:5 |
| rid-d866f7ca1e390571 | order_log_v1.jsonl:75 | order_log_v1.jsonl:76 | order_log_v1.jsonl:76 | trade_lifecycle.jsonl:6 |
| rid-d652490152b41863 | order_log_v1.jsonl:83 | aurora_events.jsonl:6 | aurora_events.jsonl:6 | trade_lifecycle.jsonl:7 |
| rid-9e015bd410455284 | order_log_v1.jsonl:86 | order_log_v1.jsonl:87 | order_log_v1.jsonl:87 | trade_lifecycle.jsonl:8 |
| aurora_BTCUSDT_1774931703505 | order_log_v1.jsonl:102 | aurora_events.jsonl:7 | aurora_events.jsonl:7 | trade_lifecycle.jsonl:9 |
| rid-d38a93e3c667b0d7 | order_log_v1.jsonl:108 | aurora_events.jsonl:8 | aurora_events.jsonl:8 | trade_lifecycle.jsonl:10 |
| rid-e5adcc2a7d67ffcb | order_log_v1.jsonl:115 | order_log_v1.jsonl:116 | order_log_v1.jsonl:116 | trade_lifecycle.jsonl:11 |
| rid-d8cebaa4f1499864 | order_log_v1.jsonl:121 | order_log_v1.jsonl:122 | order_log_v1.jsonl:122 | trade_lifecycle.jsonl:12 |
| rid-cc0c2230ed591c29 | order_log_v1.jsonl:150 | order_log_v1.jsonl:151 | order_log_v1.jsonl:151 | trade_lifecycle.jsonl:13 |
| aurora_BTCUSDT_1774956301701 | order_log_v1.jsonl:160 | aurora_events.jsonl:9 | aurora_events.jsonl:9 | trade_lifecycle.jsonl:14 |
| aurora_SOLUSDT_1774956301297 | order_log_v1.jsonl:158 | aurora_events.jsonl:10 | aurora_events.jsonl:10 | trade_lifecycle.jsonl:15 |
| aurora_SOLUSDT_1774971900901 | order_log_v1.jsonl:170 | aurora_events.jsonl:11 | aurora_events.jsonl:11 | trade_lifecycle.jsonl:16 |
| aurora_ETHUSDT_1774978202964 | order_log_v1.jsonl:186 | aurora_events.jsonl:12 | aurora_events.jsonl:12 | trade_lifecycle.jsonl:17 |
| aurora_ETHUSDT_1774982101125 | order_log_v1.jsonl:193 | aurora_events.jsonl:13 | aurora_events.jsonl:13 | trade_lifecycle.jsonl:18 |
| aurora_BTCUSDT_1774986900860 | order_log_v1.jsonl:201 | aurora_events.jsonl:14 | aurora_events.jsonl:14 | trade_lifecycle.jsonl:19 |
| aurora_SOLUSDT_1774991109696 | order_log_v1.jsonl:229 | aurora_events.jsonl:15 | aurora_events.jsonl:15 | trade_lifecycle.jsonl:20 |
| aurora_BTCUSDT_1774992000648 | order_log_v1.jsonl:239 | aurora_events.jsonl:16 | aurora_events.jsonl:16 | trade_lifecycle.jsonl:21 |
| aurora_BTCUSDT_1774994703487 | order_log_v1.jsonl:249 | aurora_events.jsonl:46 | aurora_events.jsonl:46 | trade_lifecycle.jsonl:22 |
| aurora_ETHUSDT_1775013603304 | order_log_v1.jsonl:253 | aurora_events.jsonl:47 | aurora_events.jsonl:47 | trade_lifecycle.jsonl:23 |

## 4. Corrected RID-by-RID ORPHAN Matrix
FACT: The matrix below was rebuilt from scratch from `trade_lifecycle.jsonl`, `order_log_v1.jsonl`, and `aurora_events.jsonl` using the source-of-truth rules above.

| rid | strategy_id | symbol | authoritative_side | authoritative_filled_yes_no | last_proven_execution_event | lifecycle_terminal_label | bucket | proof_grade | contradictions_found_yes_no | corrected_from_previous_report_yes_no | remaining_unknowns |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rid-4c44c9b4e85b0009 | mean_reversion | DOGEUSDT | SELL | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| aurora_BTCUSDT_1774907700267 | aurora | BTCUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| rid-2aec3be5c5b62d7d | mean_reversion | DOGEUSDT | BUY | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| aurora_ETHUSDT_1774914001604 | aurora | ETHUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| rid-d866f7ca1e390571 | mean_reversion | DOGEUSDT | SELL | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| rid-d652490152b41863 | mean_reversion | DOGEUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| rid-9e015bd410455284 | mean_reversion | DOGEUSDT | BUY | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| aurora_BTCUSDT_1774931703505 | aurora | BTCUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| rid-d38a93e3c667b0d7 | mean_reversion | DOGEUSDT | BUY | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| rid-e5adcc2a7d67ffcb | mean_reversion | DOGEUSDT | BUY | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| rid-d8cebaa4f1499864 | mean_reversion | DOGEUSDT | SELL | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| rid-cc0c2230ed591c29 | mean_reversion | DOGEUSDT | BUY | No | ORDER_PLACED | ORPHANED_TTL / TTL_EXPIRED_3600s | D | MEDIUM | No | No | no proven terminal execution event after ORDER_PLACED; no per-RID runtime proof tying symptom to watchdog not-found branch |
| aurora_BTCUSDT_1774956301701 | aurora | BTCUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_SOLUSDT_1774956301297 | aurora | SOLUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_SOLUSDT_1774971900901 | aurora | SOLUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_ETHUSDT_1774978202964 | aurora | ETHUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_ETHUSDT_1774982101125 | aurora | ETHUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_BTCUSDT_1774986900860 | aurora | BTCUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_SOLUSDT_1774991109696 | aurora | SOLUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_BTCUSDT_1774992000648 | aurora | BTCUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs |
| aurora_BTCUSDT_1774994703487 | aurora | BTCUSDT | SELL | Yes | ORDER_STATE_CHANGED:FILLED | ORPHANED_TTL / TTL_EXPIRED_3600s | B | MEDIUM | Yes | Yes | no proven post-fill close/cancel event in inspected logs; multi-fill order; lifecycle fill_qty reflects only 0.0024 in final row |
| aurora_ETHUSDT_1775013603304 | aurora | ETHUSDT | SELL | No | ORDER_STATE_CHANGED:CANCELED | ORPHANED_TTL / TTL_EXPIRED_3600s | E | HIGH | Yes | Yes | no direct proof which cancel propagation path failed to update trade_lifecycle |

## 5. Bucket B Findings
FACT: Bucket `B` contains 14 rows.

FACT: Every Bucket `B` row has authoritative `filled_yes_no = Yes`.

FACT: In every Bucket `B` row, the strongest proven execution-side event is `ORDER_STATE_CHANGED:FILLED` from `aurora_events.jsonl`.

FACT: In every Bucket `B` row, lifecycle later records `ORPHANED_TTL / TTL_EXPIRED_3600s`.

INFERENCE: Bucket `B` proves a fill-to-lifecycle-divergence pattern. It does not, by itself, prove what happened after the fill.

INFERENCE: The most defensible Bucket `B` statement is: `the order filled, but no later close or cancel event was proven in the inspected execution artifacts before lifecycle TTL collapse`.

UNKNOWN: Whether each Bucket `B` position remained legitimately open, later closed through a path not captured in the inspected logs, or lost its close/cancel propagation into lifecycle.

FACT: The prior statement `14 records were live positions merely held >1h` was stronger than the runtime evidence supports.

## 6. Bucket D Findings
FACT: Bucket `D` contains 7 rows.

FACT: All 7 Bucket `D` rows are `mean_reversion` `DOGEUSDT` rows with authoritative `filled_yes_no = No`.

FACT: In every Bucket `D` row, the strongest proven execution-side event is `ORDER_PLACED` from `order_log_v1.jsonl`.

FACT: No later fill, cancel, reject, timeout, or venue terminal state is proven for these 7 rows in the inspected `order_log_v1.jsonl` and `aurora_events.jsonl` artifacts.

INFERENCE: This symptom class is consistent with the `watchdog.py` path where `get_order_fn` returns no order and the watchdog removes tracking through `on_order_cancel(order_id)` without emitting `EVT:ORDER_STATE_CHANGED`.

UNKNOWN: Whether that watchdog not-found branch actually executed for any of these 7 RIDs.

UNKNOWN: Whether these 7 rows represent websocket loss, simulator/exchange loss, watchdog not-found behavior, or another missing terminal-state path outside the inspected evidence.

FACT: The prior statement `watchdog silent drop defect is the root cause of the 7 Market orders` was stronger than the current runtime evidence supports.

## 7. Bucket E Findings
FACT: Bucket `E` contains exactly one RID: `aurora_ETHUSDT_1775013603304`.

FACT: The authoritative side for this RID is `SELL` from `order_log_v1.jsonl:253`.

FACT: The strongest proven execution chain for this RID is `ORDER_PLACED -> ORDER_TIMEOUT -> ORDER_CANCELLED -> ORDER_STATE_CHANGED:CANCELED`, sourced from `order_log_v1.jsonl:255`, `order_log_v1.jsonl:257`, `order_log_v1.jsonl:258`, and `aurora_events.jsonl:47`.

FACT: The lifecycle row for the same RID still ends as `ORPHANED_TTL / TTL_EXPIRED_3600s` from `trade_lifecycle.jsonl:23`.

FACT: Bucket `E` is the one row where execution-side cancel truth and lifecycle terminal label directly diverge in the inspected evidence.

INFERENCE: A cancellation propagation failure occurred somewhere between execution-side cancellation truth and lifecycle update.

UNKNOWN: The inspected evidence does not prove whether the failure was specifically inside `event_handlers.py`, `exposure_manager.handle_cancel_event()`, the watchdog emit path, or another cancel propagation seam.

## 8. Claims Downgraded / Confirmed
| Claim | Classification | Evidence-bounded resolution |
|---|---|---|
| `watchdog silent drop defect is the root cause of the 7 Market orders` | PLAUSIBLE BUT UNPROVEN | FACT: `watchdog.py` contains a not-found branch that removes tracking without emitting a terminal event. FACT: all 7 Bucket `D` rows stop at `ORDER_PLACED`. UNKNOWN: no per-RID runtime proof ties any of the 7 rows to that specific branch. |
| `14 records were live positions merely held >1h` | PARTIALLY PROVEN | FACT: 14 rows were filled and later TTL-swept. UNKNOWN: the evidence does not prove they were merely long-held live positions rather than later-resolved positions whose terminal lifecycle update was missing from the inspected artifacts. |
| `logger ignored cancellation` | CONTRADICTED | FACT: `trade_lifecycle_logger.py` has `on_cancel()` and would flush `CANCELLED` if called. FACT: the evidence only proves that lifecycle was not updated to `CANCELLED`; it does not prove the logger received a cancel and ignored it. |
| `event_handlers entirely fails to call on_cancel` | PROVEN | FACT: inspected `apps/reference/domains/execution_position/event_handlers.py` contains `_trade_lifecycle.on_fill(...)` callsites and no `_trade_lifecycle.on_cancel(...)` callsite. INFERENCE: this is a file-scoped fact, not a system-wide statement, because `entry_manager.py` does call `_trade_lifecycle.on_cancel(...)`. |
| `on_fill overwrite causes semantic loss` | PROVEN | FACT: `trade_lifecycle_logger.py:on_fill()` overwrites `fill_qty`. FACT: `aurora_BTCUSDT_1774994703487` ends with lifecycle `fill_qty = 0.0024` in `trade_lifecycle.jsonl:22` while `aurora_events.jsonl:46` proves final `FILLED` with `filled_qty = 0.146`. |

## 9. Proven Defects
FACT: `apps/reference/telemetry/trade_lifecycle_logger.py:sweep_expired()` can label a record `ORPHANED_TTL` solely because it remained non-terminal past TTL. This makes lifecycle terminal labeling weaker than execution truth by design.

FACT: `aurora_ETHUSDT_1775013603304` proves that a record can reach execution-side cancel truth and still end as `ORPHANED_TTL` in lifecycle.

FACT: `apps/reference/domains/execution_position/event_handlers.py` has no `_trade_lifecycle.on_cancel(...)` callsite.

FACT: `apps/reference/domains/execution_position/exposure_manager.py:handle_cancel_event()` performs cancel-related cleanup and exposure emission but does not call `_trade_lifecycle.on_cancel(...)`.

FACT: `apps/reference/domains/execution_position/watchdog.py` contains a not-found branch that removes order tracking through `on_order_cancel(order_id)` without emitting `EVT:ORDER_STATE_CHANGED`.

FACT: `apps/reference/telemetry/trade_lifecycle_logger.py:on_fill()` overwrites `fill_qty` and therefore loses cumulative fill semantics for at least one proven multi-fill order.

## 10. Plausible but Unproven Mechanisms
PLAUSIBLE BUT UNPROVEN: The seven Bucket `D` rows were caused by the watchdog not-found branch rather than by another unobserved venue or simulator failure.

PLAUSIBLE BUT UNPROVEN: Some or all Bucket `B` rows represent legitimately open positions that simply exceeded the lifecycle TTL window.

PLAUSIBLE BUT UNPROVEN: Some or all Bucket `B` rows represent positions that later closed but lost close propagation into lifecycle.

PLAUSIBLE BUT UNPROVEN: The `orphan_ttl_sec = 3600` value is operationally incompatible with the true hold times of the affected strategies. Current evidence proves TTL collapse after fill, but it does not yet prove the intended strategy hold horizon for every affected RID.

PLAUSIBLE BUT UNPROVEN: The overwrite semantics in `on_fill()` may affect more rows than `aurora_BTCUSDT_1774994703487`. This row proves the defect exists; it does not prove global prevalence.

## 11. What Remains Unknown
UNKNOWN: The exact venue-side or simulator-side truth for the 7 Bucket `D` rows after `ORDER_PLACED`.

UNKNOWN: The exact post-fill lifecycle of the 14 Bucket `B` rows after their proven `FILLED` event.

UNKNOWN: Whether any Bucket `B` row later reached a close or cancel path outside the inspected `order_log_v1.jsonl` and `aurora_events.jsonl` artifacts.

UNKNOWN: The exact cancel propagation seam that failed for `aurora_ETHUSDT_1775013603304`.

UNKNOWN: The full extent of cumulative fill semantic loss beyond the proven multi-fill row `aurora_BTCUSDT_1774994703487`.

UNKNOWN: Whether additional artifacts outside the inspected evidence set would split Bucket `B` into multiple sub-families.
