# AGENT_REPORT_V1

## Executive Summary
Residual R4 PPS lifecycle-id recovery is not fully validated on fresh post-patch runtime logs. There were 17 PPS sidecar closes and 16 of them used canonical aurora lifecycle ids, matched FINAL rows, and matched order-log economics, but one PPS close still wrote the ppsreq close request id into both ORDER_FILLED and POSITION_CLOSED and produced no FINAL lifecycle_stats row.

## Final Verdict
R4_RESIDUAL_PPS_PATCH_FAILED_LIFECYCLE_ID_MISMATCH

## Proven Facts
- Scope inspected, read-only: logs/order_log_v1.jsonl, logs/execution_lifecycle_stats_v1.jsonl, logs/trade_lifecycle.jsonl, logs/shadow_critical_event_journal_v1.jsonl, logs/domain_execution_position.log*.
- Active order log contains 31 post-patch POSITION_CLOSED events.
- 17 of those 31 closes are PPS sidecar closes identified by request ids with prefix ppsreq:pps:.
- Active execution_lifecycle_stats contains 30 FINAL rows total.
- Active execution_lifecycle_stats contains no rows at all with lifecycle_id containing ppsreq:pps:, so there is no FINAL row using a PPS request id as lifecycle_id.
- 16 of 17 PPS closes satisfy the intended post-patch contract:
  - POSITION_CLOSED.lifecycle_id is canonical aurora_SYMBOL_ts.
  - Matching close ORDER_FILLED.lifecycle_id is the same canonical aurora_SYMBOL_ts.
  - A matching FINAL execution_lifecycle_stats row exists for the same canonical lifecycle_id.
  - FINAL gross_pnl, fees, and net_pnl match the order_log POSITION_CLOSED economics.
- One PPS close still violates the contract:
  - request_id: ppsreq:pps:BTCUSDT:1778622610290:109168
  - logs/order_log_v1.jsonl:563 records ORDER_FILLED.lifecycle_id = ppsreq:pps:BTCUSDT:1778622610290:109168.
  - logs/order_log_v1.jsonl:564 records POSITION_CLOSED.lifecycle_id = ppsreq:pps:BTCUSDT:1778622610290:109168.
  - Active execution_lifecycle_stats has no row for that lifecycle_id, so there is no matching FINAL row.
  - This same rid is the only POSITION_CLOSED in the active order log without any FINAL lifecycle_stats row.
- A passing post-patch PPS close does exist, so the patch is partially effective but not complete:
  - request_id: ppsreq:pps:ETHUSDT:1778513401254:5867
  - logs/order_log_v1.jsonl:32 ORDER_FILLED.lifecycle_id = aurora_ETHUSDT_1778512203285
  - logs/order_log_v1.jsonl:34 POSITION_CLOSED.lifecycle_id = aurora_ETHUSDT_1778512203285
  - logs/execution_lifecycle_stats_v1.jsonl:157 FINAL.lifecycle_id = aurora_ETHUSDT_1778512203285
  - order-log and FINAL economics match: gross -27.55977, fees 2.5700507200000002, net -30.12982072
- The failing rid has corroborating active runtime evidence outside order_log:
  - logs/trade_lifecycle.jsonl:152160 shows POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE request_state=close_command_emitted for the same request_id, with policy_context.lifecycle_id = null and fill_correlation.rid = aurora_BTCUSDT_1778613004676.
  - logs/trade_lifecycle.jsonl:152167 shows EXECUTION_FILL_INGRESS for the same rid with result_op = ERR and result_verb = TRADE_EXECUTED.
  - logs/shadow_critical_event_journal_v1.jsonl:49733, 49735, 49736, and 49738 all carry lifecycle_id = ppsreq:pps:BTCUSDT:1778622610290:109168 through DEC:CLOSE, CMD:CLOSE, ExecPosFSM handling, and ORDER_INDEX:UPSERT_OPEN.
  - logs/domain_execution_position.log.2:8164 emits EXECUTION_GUARD_BLOCKED with block_reason = stale_local_lifecycle_conflict for the same rid.
- No explicit fail-closed reason explaining an intentional FINAL omission was found for the failing PPS close. The emitted runtime blocker is EXECUTION_GUARD_BLOCKED stale_local_lifecycle_conflict, not an explicit fail-closed finalization reason.

## PPS Close Matrix

| Request ID | Symbol | Side | POSITION_CLOSED.lifecycle_id | ORDER_FILLED.lifecycle_id | FINAL row | FINAL lifecycle_id | Econ match vs order_log |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ppsreq:pps:ETHUSDT:1778513401254:5867 | ETHUSDT | SELL | aurora_ETHUSDT_1778512203285 | aurora_ETHUSDT_1778512203285 | Yes | aurora_ETHUSDT_1778512203285 | Yes |
| ppsreq:pps:BTCUSDT:1778513402113:5871 | BTCUSDT | SELL | aurora_BTCUSDT_1778512203705 | aurora_BTCUSDT_1778512203705 | Yes | aurora_BTCUSDT_1778512203705 | Yes |
| ppsreq:pps:BNBUSDT:1778517906055:11669 | BNBUSDT | BUY | aurora_BNBUSDT_1778512805536 | aurora_BNBUSDT_1778512805536 | Yes | aurora_BNBUSDT_1778512805536 | Yes |
| ppsreq:pps:BTCUSDT:1778526301803:22450 | BTCUSDT | BUY | aurora_BTCUSDT_1778516106187 | aurora_BTCUSDT_1778516106187 | Yes | aurora_BTCUSDT_1778516106187 | Yes |
| ppsreq:pps:XRPUSDT:1778576704983:49660 | XRPUSDT | BUY | aurora_XRPUSDT_1778575504391 | aurora_XRPUSDT_1778575504391 | Yes | aurora_XRPUSDT_1778575504391 | Yes |
| ppsreq:pps:BTCUSDT:1778586004223:61631 | BTCUSDT | SELL | aurora_BTCUSDT_1778573705308 | aurora_BTCUSDT_1778573705308 | Yes | aurora_BTCUSDT_1778573705308 | Yes |
| ppsreq:pps:BTCUSDT:1778600103545:79763 | BTCUSDT | SELL | aurora_BTCUSDT_1778595004078 | aurora_BTCUSDT_1778595004078 | Yes | aurora_BTCUSDT_1778595004078 | Yes |
| ppsreq:pps:BTCUSDT:1778608517097:90561 | BTCUSDT | SELL | aurora_BTCUSDT_1778600705231 | aurora_BTCUSDT_1778600705231 | Yes | aurora_BTCUSDT_1778600705231 | Yes |
| ppsreq:pps:BTCUSDT:1778622610290:109168 | BTCUSDT | SELL | ppsreq:pps:BTCUSDT:1778622610290:109168 | ppsreq:pps:BTCUSDT:1778622610290:109168 | No | - | No |
| ppsreq:pps:BNBUSDT:1778628302334:116586 | BNBUSDT | BUY | aurora_BNBUSDT_1778620205221 | aurora_BNBUSDT_1778620205221 | Yes | aurora_BNBUSDT_1778620205221 | Yes |
| ppsreq:pps:BTCUSDT:1778663400121:5462 | BTCUSDT | SELL | aurora_BTCUSDT_1778662804871 | aurora_BTCUSDT_1778662804871 | Yes | aurora_BTCUSDT_1778662804871 | Yes |
| ppsreq:pps:ETHUSDT:1778668502133:12107 | ETHUSDT | BUY | aurora_ETHUSDT_1778662804339 | aurora_ETHUSDT_1778662804339 | Yes | aurora_ETHUSDT_1778662804339 | Yes |
| ppsreq:pps:BTCUSDT:1778669103598:12894 | BTCUSDT | BUY | aurora_BTCUSDT_1778663701052 | aurora_BTCUSDT_1778663701052 | Yes | aurora_BTCUSDT_1778663701052 | Yes |
| ppsreq:pps:XRPUSDT:1778681706064:29235 | XRPUSDT | SELL | aurora_XRPUSDT_1778679600656 | aurora_XRPUSDT_1778679600656 | Yes | aurora_XRPUSDT_1778679600656 | Yes |
| ppsreq:pps:BNBUSDT:1778682301256:30111 | BNBUSDT | SELL | aurora_BNBUSDT_1778682001038 | aurora_BNBUSDT_1778682001038 | Yes | aurora_BNBUSDT_1778682001038 | Yes |
| ppsreq:pps:BTCUSDT:1778729103417:43120 | BTCUSDT | BUY | aurora_BTCUSDT_1778727301200 | aurora_BTCUSDT_1778727301200 | Yes | aurora_BTCUSDT_1778727301200 | Yes |
| ppsreq:pps:XRPUSDT:1778731801705:46723 | XRPUSDT | SELL | aurora_XRPUSDT_1778730600357 | aurora_XRPUSDT_1778730600357 | Yes | aurora_XRPUSDT_1778730600357 | Yes |

## Inferred Findings
- The mediator-owned recovery patch improved behavior for most PPS closes, but it did not eliminate the residual R4 path.
- The failing BTCUSDT close is best classified as a lifecycle-id mismatch first and a missing FINAL second, because the wrong ppsreq lifecycle_id is already present at ORDER_FILLED and POSITION_CLOSED.
- The missing FINAL row for the failing close appears to be downstream of that wrong lifecycle identity rather than evidence of a separate, fully new finalization problem.

## Contradictions / Evidence Gaps
- Runtime logs prove the residual failure exists, but they do not by themselves prove the precise code branch where mediator reseeding was skipped or later overwritten.
- trade_lifecycle and domain_execution_position both show policy_context.lifecycle_id = null for the failing request, but prior memory for this bug indicates that null policy_context.lifecycle_id alone is not sufficient to explain success vs failure.
- The observed EXECUTION_GUARD_BLOCKED stale_local_lifecycle_conflict is real, but runtime evidence alone does not prove whether it is the primary cause of the wrong lifecycle_id or a downstream symptom of the same identity drift.

## Root Cause Candidates
- A residual close path still allows the PPS request id to remain the active lifecycle key through CloseFlowFSM, OrderIndex, and legacy fill ingress handling for some sidecar closes.
- The failing chain may be interacting with stale local lifecycle state, evidenced by EXECUTION_GUARD_BLOCKED stale_local_lifecycle_conflict immediately after execution_submitted.
- The canonical entry lifecycle is still visible in failing-request context via fill_correlation.rid = aurora_BTCUSDT_1778613004676, so the failure is not loss of all canonical evidence; it is failure to carry that canonical identity through close accounting.

## Operational Risk
- Silent Corruption

## Files / Areas Touched
- Added this report only: R4_RESIDUAL_PPS_POST_PATCH_RUNTIME_VALIDATION_REPORT.md
- No code, config, or runtime log files were modified.

## Validation Performed
- Parsed active logs/order_log_v1.jsonl and counted all POSITION_CLOSED rows.
- Isolated PPS closes by request_id prefix ppsreq:pps: and built a per-close matrix.
- Matched each PPS POSITION_CLOSED to close ORDER_FILLED rows via trade_id and/or close_fill_client_order_id.
- Matched each PPS close lifecycle_id to FINAL rows in active logs/execution_lifecycle_stats_v1.jsonl.
- Compared FINAL gross_pnl, fees, and net_pnl against order_log POSITION_CLOSED economics.
- Verified that active logs/execution_lifecycle_stats_v1.jsonl contains no ppsreq:pps lifecycle ids.
- Cross-checked the failing residual rid in active logs/trade_lifecycle.jsonl, logs/shadow_critical_event_journal_v1.jsonl, and logs/domain_execution_position.log.2.

## Residual Risk
- PPS close accounting is still not fail-closed with respect to authoritative lifecycle identity: one live path can still close economically while dropping canonical lifecycle identity and skipping FINAL ledger materialization.
- Downstream forensic, calibration, or audit consumers that rely on FINAL execution_lifecycle_stats rows will undercount or misclassify affected PPS closes.

## What Remains Unproven
- The exact implementation seam that let ppsreq:pps:BTCUSDT:1778622610290:109168 bypass or overwrite canonical reseeding during close handling.
- Whether stale_local_lifecycle_conflict is the direct trigger for the identity regression or merely the first visible downstream blocker.

## Minimal Safe Verdict
R4_RESIDUAL_PPS_PATCH_FAILED_LIFECYCLE_ID_MISMATCH
