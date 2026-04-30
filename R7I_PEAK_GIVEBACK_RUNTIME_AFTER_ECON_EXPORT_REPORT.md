# R7I Peak-Giveback Runtime Observation After Symbol Economics Export

## Problem Framing
R7H was supposed to extend the portfolio-state boundary with per-symbol economics so Sidecar could reconstruct peak giveback from live runtime data. This package does not change code or thresholds. It only checks whether the fresh runtime slice actually carries those fields into snapshot payloads and whether Sidecar consumes them.

## Observation Window
- Snapshot basis: `logs/trade_lifecycle.jsonl`, `logs/order_log_v1.jsonl`, `logs/shadow_critical_event_journal_v1.jsonl`, `logs/domain_execution_position.log`
- Earliest observed runtime row: `2026-04-29T22:51:22.422Z` (`1777503082422`)
- Latest observed runtime row: `2026-04-30T08:37:10.408Z` (`1777538230408`)
- XRP timeout lifecycle window: `2026-04-30T00:40:05.735Z` to `2026-04-30T01:00:07.426Z`
- XRP filled lifecycle window: `2026-04-30T01:50:02.460Z` to `2026-04-30T08:37:10.403Z`
- The filled XRP position itself closed at `2026-04-30T01:57:13.687Z`

## FACTS
- `logs/trade_lifecycle.jsonl` contains 49,035 lines, 0 parse errors, 60 `POSITION_POLICY_SIDECAR_MODE_ACTIVE` rows, 48,959 `POSITION_POLICY_SIDECAR_SUPPRESSED` rows, and 2 lifecycle snapshot rows with no `event_type`.
- All 60 `POSITION_POLICY_SIDECAR_MODE_ACTIVE` rows carry `sidecar_config_snapshot`. The loaded values are `mode=enable`, `peak_giveback_close.enabled=true`, `edge_arm_usd=25.0`, `giveback_trigger_pct=50.0`, `portfolio_max_age_ms=60000`, `features_max_age_ms=15000`, `regime_max_age_ms=30000`, and `order_state_max_age_ms=15000`.
- `logs/trade_lifecycle.jsonl` has 48,959 Sidecar suppressions in the current slice, and 4,483 of those rows carry `fill_correlation.rid=aurora_XRPUSDT_1777513802272`. The remaining rows are no-lifecycle suppressions spread across symbols.
- The overall Sidecar state distribution is `peak_giveback_not_ready=48,957` and `peak_giveback_suppressed_close_in_progress=2`.
- The named states `peak_giveback_armed`, `peak_giveback_below_trigger`, `peak_giveback_threshold_met`, `peak_giveback_suppressed_stale_inputs`, and `peak_giveback_unavailable_economics_missing` do not appear in this slice.
- No stale-mark-specific reason code appeared in the inspected rows. The economics-related null reason was `missing_mark_price`, not `stale_mark`.
- `logs/shadow_critical_event_journal_v1.jsonl` contains 6,093 `EVT:PORTFOLIO_STATE_UPDATED` rows and 6,094 `EVT:EXPOSURE_SUMMARY_UPDATED` rows from `position_tracking`.
- Every `EVT:PORTFOLIO_STATE_UPDATED` row in the inspected slice has an empty `payload_fragment`.
- 6,093 of the `EVT:EXPOSURE_SUMMARY_UPDATED` rows carry a non-empty `payload_fragment.portfolio_state`; only 3 of those rows include a `positions` array.
- The 3 position-bearing exposure-summary rows are timestamp-aligned with the filled XRP lifecycle at `2026-04-30T01:57:01.482Z`, `2026-04-30T01:57:02.051Z`, and `2026-04-30T01:57:02.944Z`.
- In those 3 rows, the position object carries the exact R7H field names `markPrice`, `unrealizedPnl`, and `unrealizedPnlPct`, but all three values are `null`.
- `logs/domain_execution_position.log` contains 6,093 `portfolio_keys` debug lines, with 3 unique key sets. All 3 key sets are account-level only and omit `markPrice`, `unrealizedPnl`, and `unrealizedPnlPct`.
- `logs/order_log_v1.jsonl` shows two XRP lifecycles. The timeout lifecycle ended with `ORDER_TIMEOUT` and `ORDER_CANCELLED`. The filled lifecycle emitted `CloseExecutor` close submission, then `POSITION_CLOSED`.
- The filled XRP lifecycle has no Sidecar recommendation row, no Sidecar close-request row, and no downstream direct Sidecar execution row.
- No malformed Sidecar payloads were found in `logs/trade_lifecycle.jsonl`.

## INFERENCES
- The R7H field names have reached the runtime snapshot layer, but the inspected slice does not prove any fresh non-null symbol economics.
- Sidecar is consuming the available position context and explicit null-reasons, but it is not consuming usable `markPrice` / `unrealizedPnl` / `unrealizedPnlPct` values because none were emitted in this slice.
- The runtime remains fail-closed. `peak_edge_usd` stays `0.0`, `is_armed` stays `false`, and `threshold_crossed` stays `null`, so the 25 USD arm threshold is never approached.
- The filled XRP close path is owned by the incumbent execution-position path, not by Sidecar. Sidecar only observes suppressions around the close and after close reconciliation.
- The absence of recommendation and close-request rows is not a defect by itself here because the economics never became usable enough to arm or trigger.

## ASSUMPTIONS
- The snapshot copy used for analysis is representative of the live runtime state at the moment it was copied.
- `EVT:EXPOSURE_SUMMARY_UPDATED` is the relevant payload-carrying portfolio snapshot carrier in this slice, while `EVT:PORTFOLIO_STATE_UPDATED` is a shell event in the shadow journal.
- The Sidecar JSONL snapshot is the authoritative proof surface for peak-giveback state and null-reason handling.

## UNKNOWNS
- Whether another runtime surface outside these inspected logs emitted a fresh non-null mark after the snapshot point.
- Whether the empty `EVT:PORTFOLIO_STATE_UPDATED` payloads are intentional shells or simply an intermediate transport form.
- Whether a later market slice will populate `markPrice` while the position is still open.

## Portfolio Economics Export Proof
- `EVT:PORTFOLIO_STATE_UPDATED`: 6,093 rows, all with empty `payload_fragment`. No symbol economics are visible there in the current slice.
- `EVT:EXPOSURE_SUMMARY_UPDATED`: 6,094 rows total, 6,093 with a portfolio snapshot payload, 3 with a position array.
- The 3 position-bearing rows all show `symbol=XRPUSDT`, `net_position=2967.7`, `avg_entry_price=1.3795`, `venues=["binance"]`, and the exact keys `markPrice`, `unrealizedPnl`, `unrealizedPnlPct` set to `null`.
- The same rows also show aggregate account-level `unrealized_pnl` values in the portfolio state, but that is portfolio-level data and must not be treated as symbol PnL.
- There are 0 rows in the inspected snapshot where `markPrice`, `unrealizedPnl`, or `unrealizedPnlPct` is non-null.
- Conclusion: the runtime proves the field names exist in the snapshot payload, but it does not prove a populated symbol-economics export.

## Sidecar Consumption Proof
- Sidecar rows total: 48,959.
- Rows with a lifecycle rid: 4,483, all for `aurora_XRPUSDT_1777513802272`.
- Rows with `position_snapshot.portfolio_snapshot_status=present`: 5.
- Rows with `peak_giveback_snapshot.mark_price` non-null: 0.
- Rows with `peak_giveback_snapshot.unrealized_pnl_usdt` non-null: 0.
- Rows with `peak_giveback_snapshot.unrealized_pnl_pct` non-null: 0.
- Rows with `peak_giveback_snapshot.current_edge_usd` non-null: 0.
- Rows with explicit `null_reasons`: 48,959.
- In the XRP lifecycle, 4,477 rows carry the full null-reason set, including `entry_price`, `position_qty`, and `side` missing.
- In the same lifecycle, 6 later rows have `entry_price=1.3795`, `position_qty=2967.7`, and `side=BUY`, and the null-reasons shrink to economics-only misses: `mark_price`, `unrealized_pnl_usdt`, `unrealized_pnl_pct`, `current_edge_usd`, `giveback_pct`, and `threshold_crossed`.
- `peak_edge_usd` stays `0.0` on every Sidecar row.
- `is_armed` stays `false` on every Sidecar row.
- `threshold_crossed` stays `null` on every Sidecar row.

## Peak-Giveback State Distribution
- `peak_giveback_not_ready`: 48,957 overall.
- `peak_giveback_suppressed_close_in_progress`: 2 overall.
- `peak_giveback_armed`: 0.
- `peak_giveback_below_trigger`: 0.
- `peak_giveback_threshold_met`: 0.
- `peak_giveback_suppressed_stale_inputs`: 0.
- `peak_giveback_unavailable_economics_missing`: 0.
- No malformed or missing snapshot row was observed in the Sidecar stream.
- By symbol, the Sidecar rows are distributed across `XRPUSDT=7,258`, `BTCUSDT=7,160`, `BNBUSDT=7,159`, `SOLUSDT=7,158`, `ETHUSDT=7,157`, `DOGEUSDT=6,534`, and `1000PEPEUSDT=6,533`.

## Lifecycle Case Split
- `aurora_XRPUSDT_1777509605601`: CASE E. This lifecycle timed out before fill, then cancelled. No Sidecar lifecycle formed, so there was nothing to arm or trigger.
- `aurora_XRPUSDT_1777513802272`: CASE F. This lifecycle filled, but symbol economics stayed unavailable in the Sidecar snapshot. The runtime shows explicit null-reason handling, not a threshold defect.

## Trigger, Routing, And Safety Analysis
- `POSITION_POLICY_SIDECAR_RECOMMENDED`: 0.
- `POSITION_POLICY_SIDECAR_CLOSE_REQUESTED`: 0.
- `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`: 0.
- No threshold-met row was observed.
- No armed lifecycle was observed.
- No duplicate close storm was observed.
- No direct exchange action from Sidecar was observed.
- No bracket mutation from Sidecar provenance was observed.
- The filled XRP close is clearly owned by `CloseExecutor` and the incumbent execution-position path: the order log shows `CloseExecutor` close submit intent, `CloseExecutor` close placement, and `POSITION_CLOSED`.
- The Sidecar tail after close is safe suppression: `manage_flow_close_in_progress` appears twice, then `manage_flow_has_no_active_lifecycle` takes over after the position is flat.

## Final Verdict
The slice is observable and fail-closed, but the economics export is still not runtime proven because the runtime never shows a non-null `markPrice`, `unrealizedPnl`, or `unrealizedPnlPct` in the inspected snapshot payloads.

ECONOMICS_EXPORT_STILL_NOT_RUNTIME_PROVEN
