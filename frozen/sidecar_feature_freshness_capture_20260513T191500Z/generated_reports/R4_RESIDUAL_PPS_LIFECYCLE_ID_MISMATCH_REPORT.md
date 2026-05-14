# AGENT_REPORT_V1

## Executive Summary
Residual PPS close lifecycle mismatch is localized to active_lifecycle_cache_missing_before_close: when the canonical entry lifecycle is absent from runtime cache at close time, the close-fill path can downgrade lifecycle authority to the PPS request id and skip FINAL lifecycle stats emission. The mediator patch is now in place and focused unit validation passed, but no fresh post-patch runtime replay was run.

## Proven Facts
- The root-log sample contains exactly 10 PPS close requests in scope, spanning logs/order_log_v1.jsonl:33-322 and matching PPS request-state records in logs/trade_lifecycle.jsonl:14072-91007.
- Exactly 3 of those 10 cases wrote the PPS request id as the lifecycle_id on both ORDER_FILLED and POSITION_CLOSED, and those 3 cases have no matching FINAL row in logs/execution_lifecycle_stats_v1.jsonl.
- The remaining 7 of 10 cases wrote the canonical aurora_* lifecycle_id on both ORDER_FILLED and POSITION_CLOSED, and each of those 7 cases has a matching FINAL row in logs/execution_lifecycle_stats_v1.jsonl.
- In all 10 PPS cases, the PPS close-command record did not carry a lifecycle_id in the serialized policy context or fill_correlation snapshot. Representative close_command_emitted records are at logs/trade_lifecycle.jsonl:14072, logs/trade_lifecycle.jsonl:17637, logs/trade_lifecycle.jsonl:18543, logs/trade_lifecycle.jsonl:24365, logs/trade_lifecycle.jsonl:38018, logs/trade_lifecycle.jsonl:53551, logs/trade_lifecycle.jsonl:54367, logs/trade_lifecycle.jsonl:55968, logs/trade_lifecycle.jsonl:63323, and logs/trade_lifecycle.jsonl:90990.
- Because rows 3-9 are canonical despite the same empty serialized lifecycle fields, sidecar payload omission is not sufficient to explain the bad rows.
- The ORDER_FILLED write path resolves lifecycle_id from _last_lifecycle_ikey_by_symbol first, then falls back to OrderIndex.ref.idempotent_key when the cache is empty; that happens before the ORDER_FILLED write itself in apps/reference/domains/execution_position/orchestration/event_handlers.py:1008-1023.
- PositionPolicyMediator emits CMD:CLOSE with idempotent_key=request.request_id, so a CLOSE OrderIndex ref naturally carries the PPS request id unless another lifecycle source overrides it. The emission is in apps/reference/domains/execution_position/sidecar/position_policy_mediator.py:286-299.
- POSITION_CLOSED finalization uses close_truth.lifecycle_id or _last_lifecycle_ikey_by_symbol[symbol], then ledger.finalize_close(...) returns fail-closed on KeyError. That seam is in apps/reference/domains/execution_position/orchestration/event_handlers.py:130-180 and apps/reference/domains/execution_position/orchestration/event_handlers.py:254-390.
- The applied patch adds mediator-owned recovery and reseeding of the canonical entry lifecycle from ENTRY refs in OrderIndex before CMD:CLOSE is emitted. The recovery and reseed helpers are in apps/reference/domains/execution_position/sidecar/position_policy_mediator.py:46-152, and the pre-submit invocation is in apps/reference/domains/execution_position/sidecar/position_policy_mediator.py:272-280.
- The focused regression test now proves that, with an empty lifecycle cache but recoverable ENTRY correlation in OrderIndex, the mediator emits policy_context.lifecycle_id, reseeds _last_lifecycle_ikey_by_symbol, and marks the ledger row close_requested. That coverage is in tests/domains/execution_position/test_close_producer_bridge_package6.py:389-465.

| # | request_id | expected canonical lifecycle | ORDER_FILLED lifecycle | POSITION_CLOSED lifecycle | FINAL row | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ppsreq:pps:XRPUSDT:1778448304894:3785 | aurora_XRPUSDT_1778446507671 @ order_log:9 | ppsreq:pps:XRPUSDT:1778448304894:3785 @ order_log:35 | ppsreq:pps:XRPUSDT:1778448304894:3785 @ order_log:36 | none | BAD |
| 2 | ppsreq:pps:BNBUSDT:1778451004884:7250 | aurora_BNBUSDT_1778447104052 @ order_log:29 | ppsreq:pps:BNBUSDT:1778451004884:7250 @ order_log:61 | ppsreq:pps:BNBUSDT:1778451004884:7250 @ order_log:63 | none | BAD |
| 3 | ppsreq:pps:XRPUSDT:1778451601075:8100 | aurora_XRPUSDT_1778450704254 @ order_log:57 | aurora_XRPUSDT_1778450704254 @ order_log:79 | aurora_XRPUSDT_1778450704254 @ order_log:81 | stats:529 | GOOD |
| 4 | ppsreq:pps:XRPUSDT:1778453703082:5117 | aurora_XRPUSDT_1778452801472 @ order_log:91 | aurora_XRPUSDT_1778452801472 @ order_log:102 | aurora_XRPUSDT_1778452801472 @ order_log:103 | stats:863 | GOOD |
| 5 | ppsreq:pps:BTCUSDT:1778461804918:8459 | aurora_BTCUSDT_1778459104860 @ order_log:158 | aurora_BTCUSDT_1778459104860 @ order_log:180 | aurora_BTCUSDT_1778459104860 @ order_log:181 | stats:2321 | GOOD |
| 6 | ppsreq:pps:XRPUSDT:1778473504414:23866 | aurora_XRPUSDT_1778471106715 @ order_log:186 | aurora_XRPUSDT_1778471106715 @ order_log:231 | aurora_XRPUSDT_1778471106715 @ order_log:232 | stats:2816 | GOOD |
| 7 | ppsreq:pps:ETHUSDT:1778474104765:24647 | aurora_ETHUSDT_1778473203408 @ order_log:226 | aurora_ETHUSDT_1778473203408 @ order_log:238 | aurora_ETHUSDT_1778473203408 @ order_log:239 | stats:2939 | GOOD |
| 8 | ppsreq:pps:BTCUSDT:1778475301709:26206 | aurora_BTCUSDT_1778473203744 @ order_log:202 | aurora_BTCUSDT_1778473203744 @ order_log:246 | aurora_BTCUSDT_1778473203744 @ order_log:247 | stats:3174 | GOOD |
| 9 | ppsreq:pps:ETHUSDT:1778480704703:33393 | aurora_ETHUSDT_1778479502991 @ order_log:286 | aurora_ETHUSDT_1778479502991 @ order_log:291 | aurora_ETHUSDT_1778479502991 @ order_log:292 | stats:4603 | GOOD |
| 10 | ppsreq:pps:BNBUSDT:1778497504627:3623 | aurora_BNBUSDT_1778472302897 @ order_log:191 | ppsreq:pps:BNBUSDT:1778497504627:3623 @ order_log:321 | ppsreq:pps:BNBUSDT:1778497504627:3623 @ order_log:322 | none | BAD |

## Inferred Findings
- The discriminating condition between the 7 GOOD rows and the 3 BAD rows is not serialized payload shape; that field is empty in both populations.
- The discriminating condition is whether a canonical lifecycle remained recoverable in runtime state when the close-fill path executed.
- When _last_lifecycle_ikey_by_symbol still contains the active entry lifecycle, ORDER_FILLED and POSITION_CLOSED remain canonical and lifecycle_stats finalization succeeds.
- When the cache is empty at close-fill time, the early ORDER_FILLED write path can fall back to OrderIndex.ref.idempotent_key. Because the CLOSE ref was pre-registered with request.request_id, that fallback promotes ppsreq:pps:... into lifecycle authority for ORDER_FILLED and then POSITION_CLOSED.
- Once POSITION_CLOSED is stamped with ppsreq:pps:..., lifecycle_stats finalization looks up the wrong lifecycle key and no FINAL row is emitted.
- Row 10 proves the defect is intermittent rather than startup-only: several canonical PPS closes succeed before the residual cache-missing case recurs.

## Contradictions / Evidence Gaps
- Historical logs do not directly show the exact instruction that cleared or failed to seed _last_lifecycle_ikey_by_symbol before rows 1, 2, and 10; the missing-cache condition is inferred from the code path plus the resulting downgrade pattern.
- The trade_lifecycle log has a small number of malformed lines unrelated to these 10 PPS cases. During parsing, 6 malformed lines were skipped, but all 10 target PPS request ranges remained parseable.
- No fresh post-patch runtime replay or live capture was executed, so patched runtime behavior is still unproven in logs.

## Root Cause Candidates
- active_lifecycle_cache_missing_before_close: PositionPolicyMediator and the downstream close-fill writer depended on lifecycle hints from request payload, fill_correlation, or _last_lifecycle_ikey_by_symbol. When those hints were absent, the early ORDER_FILLED fallback in event_handlers.py adopted the CLOSE OrderIndex ref.idempotent_key, which was request.request_id, causing lifecycle authority to downgrade to ppsreq:pps:... and FINAL lifecycle_stats emission to fail closed.

## Operational Risk
- Silent Corruption

## Files / Areas Touched
- apps/reference/domains/execution_position/sidecar/position_policy_mediator.py
- tests/domains/execution_position/test_close_producer_bridge_package6.py
- logs/order_log_v1.jsonl
- logs/trade_lifecycle.jsonl
- logs/execution_lifecycle_stats_v1.jsonl
- R4_RESIDUAL_PPS_LIFECYCLE_ID_MISMATCH_REPORT.md

## Validation Performed
- Focused unit validation: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest c:/Users/user/Music/Phenix/tests/domains/execution_position/test_close_producer_bridge_package6.py
- Result: 10 passed in 1.54s.
- Static validation: get_errors reported no errors in apps/reference/domains/execution_position/sidecar/position_policy_mediator.py and tests/domains/execution_position/test_close_producer_bridge_package6.py after the patch.
- Historical forensic validation: a 10-row PPS close matrix was assembled from logs/order_log_v1.jsonl, logs/trade_lifecycle.jsonl, and logs/execution_lifecycle_stats_v1.jsonl.

## Residual Risk
- If ENTRY correlation is absent from both request payload / manage_flow context and OrderIndex, the mediator still cannot reconstruct a canonical lifecycle id. That branch remains fail-closed and is not proven by runtime evidence here.
- The patch is unit-validated, but runtime-sensitive evidence for the exact residual row-10 style case is still missing.

## What Remains Unproven
- That a fresh cache-missing PPS close now writes canonical aurora_* lifecycle_id on ORDER_FILLED and POSITION_CLOSED after the mediator patch.
- That the previously failing residual case now emits a FINAL row in logs/execution_lifecycle_stats_v1.jsonl under runtime or replay conditions.
- That no adjacent close path regresses when OrderIndex-based lifecycle recovery is exercised in a larger runtime sweep.

## Minimal Safe Verdict
The residual PPS lifecycle mismatch was localized to a missing canonical lifecycle cache before close, and the narrow mediator patch addresses that root seam by recovering and reseeding the entry lifecycle from OrderIndex before CMD:CLOSE. The change is bounded and focused tests are green, but the task is only minimally verified until a fresh runtime replay or live capture demonstrates canonical lifecycle_id and FINAL emission for a previously failing cache-missing PPS close.
