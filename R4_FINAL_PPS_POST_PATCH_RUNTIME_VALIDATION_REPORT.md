# R4 Final PPS Post-Patch Runtime Validation Report

## 1. Executive verdict

R4_FINAL_PPS_PATCH_VALIDATED

Fresh post-patch runtime evidence exists after the latest startup boundary at [logs/domain_execution_position.log](logs/domain_execution_position.log#L20). That fresh window contains 1 PPS sidecar close, and that close preserves the canonical aurora lifecycle end-to-end across [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38118), [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L87), [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L88), and [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L1099), with exact gross, fees, and net parity.

This capture does not include a post-boundary PPS close where policy_context.lifecycle_id is null and fill_correlation.rid is the only canonical candidate. The observed runtime window therefore validates the canonical PPS close outcome, but does not directly exercise the null-to-fill_correlation recovery branch in live runtime.

## 2. FACTS

- The latest runtime start boundary is [logs/domain_execution_position.log](logs/domain_execution_position.log#L20), timestamped 2026-05-18 00:42:07.393 +03:00, which corresponds to 2026-05-17 21:42:07.393Z.
- The first relevant post-boundary event in the inspected artifacts occurs at 2026-05-17 21:42:07.395Z.
- The last relevant post-boundary event in the inspected artifacts occurs at 2026-05-18 07:46:13.856Z.
- The post-boundary runtime window duration is 10:04:06.461.
- The post-boundary window contains 5 POSITION_CLOSED rows in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl), 1 PPS sidecar close, and 4 FINAL rows in [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl).
- The single post-boundary PPS sidecar close is request_id ppsreq:pps:ETHUSDT:1779080404039:38019 in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L88).
- The PPS close request was recommended at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38117), requested at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38119), emitted at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38118), submitted at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38136), ingressed at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38138), and reconciled at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38154).
- At [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38118), policy_context.lifecycle_id is aurora_ETHUSDT_1779074700809 and fill_correlation.rid is aurora_ETHUSDT_1779074700809.
- The corresponding close ORDER_FILLED row is [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L87), where lifecycle_id is aurora_ETHUSDT_1779074700809.
- The corresponding POSITION_CLOSED row is [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L88), where lifecycle_id is aurora_ETHUSDT_1779074700809, close_reason is CLOSE, gross_pnl is -3.91437, fees are 2.40691774, net_pnl is -6.32128774, and close_ts_ms is 1779080406255.
- The matching FINAL row is [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L1099), where lifecycle_id is aurora_ETHUSDT_1779074700809, close_ts_ms is 1779080406253, close_reason is CLOSE, gross_pnl is -3.91437, fees are 2.40691774, and net_pnl is -6.32128774.
- The runtime close actor is POSITION_POLICY_SIDECAR in the provisional close_requested lifecycle_stats row at [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L1098). The order_log POSITION_CLOSED row itself does not expose a dedicated close_actor field.
- No post-boundary identity_recovery_failed event was found in [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl) or [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl).
- The 5 versus 4 count gap between POSITION_CLOSED and FINAL is explained by [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L122), a non-PPS POSITION_CLOSED_DETECTED row with pnl_status unresolved and accounting_unresolved_reason missing_close_fill_truth.

## 3. INFERENCES

- The final mediator patch is effective in the observed fresh runtime window for the only PPS close that occurred after the latest startup boundary.
- The runtime no longer demotes the observed PPS close to the PPS request id on the authoritative closure surfaces, even though the trade lifecycle ingress RID at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38138) still uses the PPS request id as the fill ingress correlation key.
- The absence of a post-boundary FINAL gap for the PPS close indicates that the authoritative lifecycle ledger remained consistent for the observed sidecar close.
- The missing fifth FINAL row is unrelated to the PPS identity patch target because it belongs to a separate non-PPS unresolved close-detected path at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L122).

## 4. ASSUMPTIONS

- The startup marker at [logs/domain_execution_position.log](logs/domain_execution_position.log#L20) is the correct freshness boundary for all inspected JSONL artifacts.
- Matching the PPS close ORDER_FILLED row by close trade_id and matching the FINAL row by canonical lifecycle_id is the correct authoritative join strategy for this runtime window.
- The system local timezone associated with the startup log is UTC+03:00, consistent with the embedded UTC timestamps recorded elsewhere in the same startup sequence.

## 5. UNKNOWNS

- This capture does not show a post-boundary PPS close where policy_context.lifecycle_id is null and fill_correlation.rid is the only available canonical lifecycle candidate.
- This capture does not show a post-boundary expected fail-closed identity_recovery_failed case, so that fail-closed branch remains runtime-unproven here.
- Only one PPS sidecar close occurred after the boundary, so sample size is small.

## 6. Runtime boundary

| Metric | Value |
| --- | --- |
| Latest startup boundary | [logs/domain_execution_position.log](logs/domain_execution_position.log#L20) |
| Boundary local time | 2026-05-18 00:42:07.393 +03:00 |
| Boundary UTC time | 2026-05-17 21:42:07.393Z |
| First relevant timestamp | 2026-05-17 21:42:07.395Z |
| Last relevant timestamp | 2026-05-18 07:46:13.856Z |
| Runtime duration | 10:04:06.461 |
| POSITION_CLOSED rows | 5 |
| PPS sidecar closes | 1 |
| FINAL lifecycle_stats rows | 4 |

The POSITION_CLOSED versus FINAL count gap is not a PPS failure. It is the separate unresolved non-PPS close-detected row at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L122).

## 7. PPS close matrix

| request_id | symbol | side | close_reason | close_actor | close_ts_ms | policy_context.lifecycle_id at emitted | fill_correlation.rid at emitted | ORDER_FILLED.lifecycle_id | POSITION_CLOSED.lifecycle_id | FINAL row | FINAL.lifecycle_id | FINAL.close_ts_ms | gross_pnl | fees | net_pnl | classification |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| ppsreq:pps:ETHUSDT:1779080404039:38019 | ETHUSDT | SELL | CLOSE | POSITION_POLICY_SIDECAR | 1779080406255 | aurora_ETHUSDT_1779074700809 | aurora_ETHUSDT_1779074700809 | aurora_ETHUSDT_1779074700809 | aurora_ETHUSDT_1779074700809 | yes | aurora_ETHUSDT_1779074700809 | 1779080406253 | -3.91437 | 2.40691774 | -6.32128774 | none |

Event chain for the only post-boundary PPS close:

- POSITION_POLICY_SIDECAR_RECOMMENDED: [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38117)
- POSITION_POLICY_SIDECAR_CLOSE_REQUESTED: [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38119)
- close_command_emitted: [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38118)
- execution_submitted: [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38136)
- EXECUTION_FILL_INGRESS: [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38138)
- ORDER_FILLED: [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L87)
- POSITION_CLOSED: [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L88)
- reconciled: [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38154)
- FINAL lifecycle_stats: [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L1099)

## 8. fill_correlation.rid recovery validation

- The observed PPS close did not require recovery from a null policy_context.lifecycle_id. At [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38118), policy_context.lifecycle_id and fill_correlation.rid were already aligned to the same canonical aurora lifecycle.
- The runtime still matters because the fill ingress correlation RID remains the PPS request id at [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl#L38138), yet the authoritative closure surfaces remain canonical aurora ids in [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L87), [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L88), and [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L1099).
- No post-boundary identity_recovery_failed event was observed in [logs/trade_lifecycle.jsonl](logs/trade_lifecycle.jsonl) or [logs/shadow_critical_event_journal_v1.jsonl](logs/shadow_critical_event_journal_v1.jsonl).
- Required check 7 is therefore not directly exercised in this capture. The observed runtime proves canonical preservation for a PPS close, not the live null-to-fill_correlation fallback branch.

## 9. FINAL lifecycle_stats validation

- A matching FINAL row exists for the observed PPS close at [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L1099).
- FINAL.lifecycle_id is the same canonical aurora_ETHUSDT_1779074700809 value used by ORDER_FILLED and POSITION_CLOSED.
- FINAL.close_reason is CLOSE, matching the order_log POSITION_CLOSED row at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L88).
- FINAL.close_ts_ms is 1779080406253, which is 2 ms earlier than the order_log POSITION_CLOSED timestamp 1779080406255 and consistent with the same close finalization chain.
- FINAL gross_pnl, fees, and net_pnl exactly match the order_log POSITION_CLOSED economics for the PPS close.
- No post-boundary FINAL row in [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl) uses a lifecycle_id starting with ppsreq:pps:.

## 10. Failures, if any

No PPS lifecycle identity failures were observed in the fresh post-boundary runtime window.

The only post-boundary closure without a FINAL row is the non-PPS unresolved row at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L122). Its classification is outside the PPS patch target and should not be counted as a PPS validation failure.

## 11. Bracket sanity check

- One post-boundary bracket TP close is present at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L12), with matching close ORDER_FILLED at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L11).
- The matching FINAL row exists at [logs/execution_lifecycle_stats_v1.jsonl](logs/execution_lifecycle_stats_v1.jsonl#L244).
- The bracket close preserves canonical lifecycle_id aurora_XRPUSDT_1779057303544 across ORDER_FILLED, POSITION_CLOSED, and FINAL.
- The bracket TP economics match exactly: gross_pnl 9.30177, fees 1.67534772, net_pnl 7.62642228.
- No post-boundary bracket SL close was observed in this runtime window.

## 12. Calibration impact

- No PPS close in this fresh window is missing from FINAL lifecycle_stats.
- No PPS close in this fresh window writes ppsreq:pps as ORDER_FILLED.lifecycle_id or POSITION_CLOSED.lifecycle_id.
- No calibration denominator repair, threshold retuning, YAML change, sidecar-mode change, or historical backfill is justified by this evidence.

## 13. Residual risks

- The sample contains only one PPS sidecar close after the final patch boundary.
- The specific null policy_context.lifecycle_id to canonical fill_correlation.rid recovery branch remains runtime-unobserved in this capture.
- The separate non-PPS unresolved close-detected path at [logs/order_log_v1.jsonl](logs/order_log_v1.jsonl#L122) remains outside this report and still deserves independent tracking.

## 14. Required next action

No corrective action is required for the R4 PPS identity patch based on this runtime window.

The required next action is passive observation only: continue collecting fresh runtime evidence and rerun this same audit when either another PPS sidecar close occurs or a PPS close emits close_command_emitted with policy_context.lifecycle_id null, so the live null-to-fill_correlation recovery branch can be directly observed.
