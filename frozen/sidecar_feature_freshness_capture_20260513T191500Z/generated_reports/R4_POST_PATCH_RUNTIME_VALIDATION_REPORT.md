# AGENT_REPORT_V1

## 1. Executive verdict

R4_RUNTIME_PATCH_FAILED_SAME_LIFECYCLE_ID_MISMATCH

Current root runtime logs contain post-R4 proof that FINAL row generation now works for many closes, including sidecar PPS closes and all observed bracket SL/TP closes. The patch is therefore partially effective.

The same runtime also contains 3 POSITION_CLOSED events that still do not produce FINAL rows, and all 3 expose the same pre-R4 symptom: non-canonical ppsreq:pps:... lifecycle identity on the close event and no matching FINAL row in execution_lifecycle_stats_v1.

## 2. FACTS

- Validation scope used current root logs only: logs/order_log_v1.jsonl, logs/execution_lifecycle_stats_v1.jsonl, logs/trade_lifecycle.jsonl, logs/shadow_critical_event_journal_v1.jsonl, logs/domain_execution_position.log, and the pre-patch reference report R4_LIFECYCLE_FINALIZATION_COMPLETENESS_AUDIT.md.
- Runtime window, anchored to POSITION_CLOSED events in current root logs, is 2026-05-10T21:25:06.827Z to 2026-05-11T11:05:06.774Z, duration 13h 39m 59.947s.
- Current runtime contains 15 POSITION_CLOSED events.
- execution_lifecycle_stats_v1 current root log contains 12 FINAL rows, 6801 PROVISIONAL rows, and 20 unique lifecycle_id values.
- Close mix is 10 sidecar PPS closes, 5 bracket SL/TP closes, 0 manual/lifecycle CLOSE closes, 0 POSITION_CLOSED_DETECTED closes.
- 12 of 15 POSITION_CLOSED events have an unambiguous matching FINAL row by symbol plus close_ts_ms proximity plus exact gross/fees/net economics.
- All 12 matched FINAL rows use canonical aurora_SYMBOL_ts lifecycle_id values.
- None of the 12 matched FINAL rows use ppsreq:pps:..., UUID, CLOSE-..., or position_close:... lifecycle identities.
- All 12 matched FINAL rows preserve non-null path stats: mfe_usdt, mae_usdt, peak_edge_usd, peak_giveback_usd, peak_giveback_pct.
- All 12 matched FINAL rows match authoritative close truth from order_log for close_reason, gross_pnl, fees, and net_pnl.
- Current domain_execution_position.log contains no direct runtime evidence of KeyError, missing lifecycle_id, finalize_close, lifecycle_stats_ledger, or explicit finalization-skip logging.
- All 10 sidecar PPS requests have available runtime chain evidence for POSITION_POLICY_SIDECAR_RECOMMENDED, POSITION_POLICY_SIDECAR_CLOSE_REQUESTED, close_command_emitted, execution_submitted, reconciled, and POSITION_CLOSED.
- 3 sidecar PPS closes still have no FINAL row.

## 3. INFERENCES

- The R4 guard improved behavior on a large subset of close paths, because 12 closes now finalize correctly and 7 of those 12 are sidecar PPS closes.
- The patch did not eliminate the lifecycle identity corruption problem on all close paths, because 3 sidecar closes still expose the same non-canonical ppsreq:pps lifecycle identity pattern that caused the original R4 gap.
- The residual gap is sidecar-biased: 3 of 10 sidecar PPS closes are missing FINAL, while 5 of 5 bracket closes finalize correctly.
- Because the missing rows are concentrated in the sidecar subset, lifecycle_stats FINAL rows are not yet safe as a complete dataset for sidecar effectiveness or calibration analysis.
- The lack of explicit error logs does not disprove failure. The observed behavior is still consistent with fail-closed finalization on an unseeded or mismatched lifecycle identity.

## 4. ASSUMPTIONS

- The relevant validation window is the span of POSITION_CLOSED events in current root logs, not the full lifetime of execution_lifecycle_stats_v1, because lifecycle_stats contains earlier seeded rows and at least one obvious synthetic/test-looking row outside the close-validation surface.
- A FINAL join is considered authoritative when symbol matches, close_ts_ms is within 30 seconds, and gross/fees/net exactly match order_log economics.
- For matched closes, final close_actor is taken from execution_lifecycle_stats_v1.
- For sidecar chain validation, recommended and close_requested are taken from shadow journal policy_context, while close_command_emitted, execution_submitted, and reconciled are taken from trade_lifecycle request_state records.

## 5. UNKNOWNS

- The exact remaining code path that still emits ppsreq:pps lifecycle identity on the 3 missing sidecar closes was not localized in this read-only runtime audit.
- The last missing BNBUSDT sidecar close is also the terminal close in the captured window, so runtime-tail timing cannot be fully excluded as a contributing factor there.
- The audit does not prove whether the residual defect is limited to specific symbols, specific position-side combinations, or a narrower sidecar branch variant.
- The audit does not prove whether the failure occurs at cache write, close-truth capture, or finalization lookup; it proves only that the runtime symptom remains the same on a subset of closes.

## 6. Runtime inventory

| Metric | Value |
|---|---:|
| First relevant event timestamp | 1778448306827 |
| First relevant event UTC | 2026-05-10T21:25:06.827Z |
| Last relevant event timestamp | 1778497506774 |
| Last relevant event UTC | 2026-05-11T11:05:06.774Z |
| Duration | 13h 39m 59.947s |
| POSITION_CLOSED events | 15 |
| FINAL rows | 12 |
| PROVISIONAL rows | 6801 |
| Unique lifecycle_id values | 20 |
| Sidecar PPS closes | 10 |
| Bracket SL/TP closes | 5 |
| Manual/lifecycle CLOSE closes | 0 |
| POSITION_CLOSED_DETECTED closes | 0 |

## 7. POSITION_CLOSED x FINAL join table

| # | ts_utc | symbol | side | kind | rid | order_log lifecycle_id | close_reason | close_actor | gross | fees | net | FINAL lifecycle_id | classification |
|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|
| 1 | 2026-05-10T21:25:06.827Z | XRPUSDT | BUY | SIDECAR_PPS | ppsreq:pps:XRPUSDT:1778448304894:3785 | ppsreq:pps:XRPUSDT:1778448304894:3785 | CLOSE | n/a | -11.47500 | 1.33513920 | -12.81013920 | n/a | FINAL_MISSING |
| 2 | 2026-05-10T21:39:51.275Z | XRPUSDT | SELL | BRACKET | aurora_XRPUSDT_1778448901024:TP | aurora_XRPUSDT_1778448901024 | TP | EXECUTION_POSITION | 0.00000 | 1.98149043 | -1.98149043 | aurora_XRPUSDT_1778448901024 | FINAL_MATCHED |
| 3 | 2026-05-10T21:59:20.243Z | XRPUSDT | SELL | BRACKET | aurora_XRPUSDT_1778449502540:TP | aurora_XRPUSDT_1778449502540 | TP | EXECUTION_POSITION | 13.77380 | 1.97412424 | 11.79967576 | aurora_XRPUSDT_1778449502540 | FINAL_MATCHED |
| 4 | 2026-05-10T22:10:07.240Z | BNBUSDT | BUY | SIDECAR_PPS | ppsreq:pps:BNBUSDT:1778451004884:7250 | ppsreq:pps:BNBUSDT:1778451004884:7250 | CLOSE | n/a | -19.03660 | 2.66691567 | -21.70351567 | n/a | FINAL_MISSING |
| 5 | 2026-05-10T22:20:03.536Z | XRPUSDT | SELL | SIDECAR_PPS | ppsreq:pps:XRPUSDT:1778451601075:8100 | aurora_XRPUSDT_1778450704254 | CLOSE | EXECUTION_POSITION | -9.31438 | 1.99423146 | -11.30861146 | aurora_XRPUSDT_1778450704254 | FINAL_MATCHED |
| 6 | 2026-05-10T22:55:04.808Z | XRPUSDT | SELL | SIDECAR_PPS | ppsreq:pps:XRPUSDT:1778453703082:5117 | aurora_XRPUSDT_1778452801472 | CLOSE | EXECUTION_POSITION | -5.04551 | 1.93475564 | -6.98026564 | aurora_XRPUSDT_1778452801472 | FINAL_MATCHED |
| 7 | 2026-05-10T23:00:08.276Z | BTCUSDT | BUY | BRACKET | aurora_BTCUSDT_1778453101930:TP | aurora_BTCUSDT_1778453101930 | TP | EXECUTION_POSITION | 11.89320 | 2.16216528 | 9.73103472 | aurora_BTCUSDT_1778453101930 | FINAL_MATCHED |
| 8 | 2026-05-10T23:56:13.282Z | ETHUSDT | BUY | BRACKET | aurora_ETHUSDT_1778456400832:SL | aurora_ETHUSDT_1778456400832 | SL | EXECUTION_POSITION | -17.37420 | 3.58327011 | -20.95747011 | aurora_ETHUSDT_1778456400832 | FINAL_MATCHED |
| 9 | 2026-05-11T00:53:05.347Z | ETHUSDT | BUY | BRACKET | aurora_ETHUSDT_1778459104635:SL | aurora_ETHUSDT_1778459104635 | SL | EXECUTION_POSITION | -4.83060 | 3.51584016 | -8.34644016 | aurora_ETHUSDT_1778459104635 | FINAL_MATCHED |
| 10 | 2026-05-11T01:10:06.887Z | BTCUSDT | BUY | SIDECAR_PPS | ppsreq:pps:BTCUSDT:1778461804918:8459 | aurora_BTCUSDT_1778459104860 | CLOSE | EXECUTION_POSITION | -18.06860 | 2.10115372 | -20.16975372 | aurora_BTCUSDT_1778459104860 | FINAL_MATCHED |
| 11 | 2026-05-11T04:25:06.374Z | XRPUSDT | SELL | SIDECAR_PPS | ppsreq:pps:XRPUSDT:1778473504414:23866 | aurora_XRPUSDT_1778471106715 | CLOSE | EXECUTION_POSITION | -13.60782 | 3.47855901 | -17.08637901 | aurora_XRPUSDT_1778471106715 | FINAL_MATCHED |
| 12 | 2026-05-11T04:35:06.485Z | ETHUSDT | SELL | SIDECAR_PPS | ppsreq:pps:ETHUSDT:1778474104765:24647 | aurora_ETHUSDT_1778473203408 | CLOSE | EXECUTION_POSITION | -6.92967 | 2.67027094 | -9.59994094 | aurora_ETHUSDT_1778473203408 | FINAL_MATCHED |
| 13 | 2026-05-11T04:55:03.687Z | BTCUSDT | SELL | SIDECAR_PPS | ppsreq:pps:BTCUSDT:1778475301709:26206 | aurora_BTCUSDT_1778473203744 | CLOSE | EXECUTION_POSITION | -9.94680 | 3.92494409 | -13.87174409 | aurora_BTCUSDT_1778473203744 | FINAL_MATCHED |
| 14 | 2026-05-11T06:25:06.599Z | ETHUSDT | SELL | SIDECAR_PPS | ppsreq:pps:ETHUSDT:1778480704703:33393 | aurora_ETHUSDT_1778479502991 | CLOSE | EXECUTION_POSITION | -8.64421 | 2.61808289 | -11.26229289 | aurora_ETHUSDT_1778479502991 | FINAL_MATCHED |
| 15 | 2026-05-11T11:05:06.774Z | BNBUSDT | BUY | SIDECAR_PPS | ppsreq:pps:BNBUSDT:1778497504627:3623 | ppsreq:pps:BNBUSDT:1778497504627:3623 | CLOSE | n/a | -23.77160 | 2.32287560 | -26.09447560 | n/a | FINAL_MISSING |

## 8. PPS sidecar close validation

Observed sidecar chain coverage is complete for all 10 PPS requests.

| rid | recommended | close_requested | close_command_emitted | execution_submitted | reconciled | POSITION_CLOSED | FINAL row | FINAL lifecycle_id |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| ppsreq:pps:XRPUSDT:1778448304894:3785 | Y | Y | Y | Y | Y | Y | N | n/a |
| ppsreq:pps:BNBUSDT:1778451004884:7250 | Y | Y | Y | Y | Y | Y | N | n/a |
| ppsreq:pps:XRPUSDT:1778451601075:8100 | Y | Y | Y | Y | Y | Y | Y | aurora_XRPUSDT_1778450704254 |
| ppsreq:pps:XRPUSDT:1778453703082:5117 | Y | Y | Y | Y | Y | Y | Y | aurora_XRPUSDT_1778452801472 |
| ppsreq:pps:BTCUSDT:1778461804918:8459 | Y | Y | Y | Y | Y | Y | Y | aurora_BTCUSDT_1778459104860 |
| ppsreq:pps:XRPUSDT:1778473504414:23866 | Y | Y | Y | Y | Y | Y | Y | aurora_XRPUSDT_1778471106715 |
| ppsreq:pps:ETHUSDT:1778474104765:24647 | Y | Y | Y | Y | Y | Y | Y | aurora_ETHUSDT_1778473203408 |
| ppsreq:pps:BTCUSDT:1778475301709:26206 | Y | Y | Y | Y | Y | Y | Y | aurora_BTCUSDT_1778473203744 |
| ppsreq:pps:ETHUSDT:1778480704703:33393 | Y | Y | Y | Y | Y | Y | Y | aurora_ETHUSDT_1778479502991 |
| ppsreq:pps:BNBUSDT:1778497504627:3623 | Y | Y | Y | Y | Y | Y | N | n/a |

PPS sidecar verdict:

- 7 of 10 PPS closes finalized correctly with canonical aurora_SYMBOL_ts FINAL lifecycle_id.
- 3 of 10 PPS closes still did not finalize.
- The 3 failing PPS closes are exactly the closes where POSITION_CLOSED still carries ppsreq:pps:... as lifecycle_id instead of canonical aurora_SYMBOL_ts.
- Because all upstream sidecar chain stages exist for those 3 requests, the gap is downstream of recommendation/request/submission/reconcile and remains in close identity propagation or finalization lookup.

## 9. SL/TP bracket close validation

| rid | close_reason | FINAL row | FINAL lifecycle_id | economics match | duplicate residual close evidence |
|---|---|:---:|---|:---:|:---:|
| aurora_XRPUSDT_1778448901024:TP | TP | Y | aurora_XRPUSDT_1778448901024 | Y | N |
| aurora_XRPUSDT_1778449502540:TP | TP | Y | aurora_XRPUSDT_1778449502540 | Y | N |
| aurora_BTCUSDT_1778453101930:TP | TP | Y | aurora_BTCUSDT_1778453101930 | Y | N |
| aurora_ETHUSDT_1778456400832:SL | SL | Y | aurora_ETHUSDT_1778456400832 | Y | N |
| aurora_ETHUSDT_1778459104635:SL | SL | Y | aurora_ETHUSDT_1778459104635 | Y | N |

Bracket verdict:

- All 5 observed bracket closes finalize correctly.
- FINAL lifecycle_id remains canonical aurora_SYMBOL_ts in all 5 cases.
- FINAL close_reason matches authoritative close truth in all 5 cases.
- No current-runtime POSITION_CLOSED_DETECTED double-close or duplicate residual close evidence was found.

## 10. Missing FINAL classification

| rid | symbol | ts_utc | classification | root cause | task-6 category | disposition |
|---|---|---|---|---|---|---|
| ppsreq:pps:XRPUSDT:1778448304894:3785 | XRPUSDT | 2026-05-10T21:25:06.827Z | FINAL_MISSING | POSITION_CLOSED.lifecycle_id remained ppsreq:pps:..., no FINAL row, later runtime continued normally | lifecycle_id mismatch | same R4 defect persists |
| ppsreq:pps:BNBUSDT:1778451004884:7250 | BNBUSDT | 2026-05-10T22:10:07.240Z | FINAL_MISSING | POSITION_CLOSED.lifecycle_id remained ppsreq:pps:..., no FINAL row, later runtime continued normally | lifecycle_id mismatch | same R4 defect persists |
| ppsreq:pps:BNBUSDT:1778497504627:3623 | BNBUSDT | 2026-05-11T11:05:06.774Z | FINAL_MISSING | POSITION_CLOSED.lifecycle_id remained ppsreq:pps:..., no FINAL row; same mismatch symptom observed, but runtime-tail timing cannot be fully excluded because this is the terminal close in the captured window | lifecycle_id mismatch with runtime-tail uncertainty | same R4 defect persists with residual timing uncertainty |

Silent failure check:

- No explicit current-runtime log lines were found for KeyError, missing lifecycle_id, lifecycle_stats finalization skipped, finalize_close, or lifecycle_stats_ledger.
- This does not clear the system. The runtime still exhibits silent non-finalization on the 3 missing closes.

## 11. R4 patch effectiveness verdict

R4_RUNTIME_PATCH_FAILED_SAME_LIFECYCLE_ID_MISMATCH

Minimal safe reading:

- The patch improved runtime behavior enough to produce 12 correct FINAL rows, including 7 PPS closes and all 5 bracket closes.
- The patch did not fully fix the original gap, because at least 2 non-terminal sidecar PPS closes still reproduce the same missing-FINAL symptom with the same non-canonical ppsreq lifecycle identity pattern.
- The last missing BNBUSDT close adds a runtime-tail uncertainty, but it is not needed to establish failure because the earlier two misses already prove persistence of the same defect class in current runtime.

## 12. PnL/calibration impact

- Not safe yet for sidecar usefulness analysis across the full runtime window. The missing rows are sidecar-biased (3 missing of 10 PPS closes), which introduces selection bias.
- Not safe yet for MFE/MAE/giveback calibration across all closed trades, because lifecycle_stats FINAL is incomplete for sidecar closes even though matched rows retain correct path stats.
- Not safe yet for neocortex reward/outcome join across the full runtime window, because 3 closed trades have no FINAL lifecycle_stats record.
- Not safe yet for accepted closed trade economics as a complete authoritative ledger for the full runtime window.
- Safe only for the matched subset and for bracket-close-only analysis in this captured window, where 5 of 5 bracket closes finalized correctly with canonical lifecycle identity and matching economics.

## 13. Residual risks

- Silent corruption risk remains on a subset of PPS close paths.
- Sidecar analytics are currently undercounted in FINAL lifecycle_stats rows.
- Any downstream consumer that assumes FINAL completeness will bias against sidecar closes.
- The absence of explicit error logs means the defect can continue to fail closed without operator-visible alarms.
- The terminal BNBUSDT missing close retains some runtime-tail ambiguity, but does not explain the two earlier non-terminal misses.

## 14. Required next action

Trace the remaining PPS close branch variants that still emit ppsreq:pps:... as POSITION_CLOSED.lifecycle_id, isolate where canonical aurora_SYMBOL_ts identity is lost after sidecar reconcile, then rerun the same runtime validation and require 0 missing FINAL rows across multiple PPS closes before declaring R4 fixed.
