AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR
verdict: NOT_ENOUGH_POST_T5D_RUNTIME
report_path: AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR_REPORT.md

facts:
- post_t5d_boundary: 2026-05-19T01:40:36.104000Z (runtime_1800000_startup; candidates: config_mtime=2026-05-18T22:40:24.904000Z; report_mtime=2026-05-13T23:04:50.646000Z; runtime_1800000_startup=2026-05-19T01:40:36.104000Z; first_order_after_report=2026-05-14T02:55:02.195000Z)
- logs_inspected: json=51 text=404 report=1 config=1 scanned_files=455
- runtime_windows: 11
- total_order_placed: 21
- metadata_order_placed: 20
- aurora_limit_gtx_entries: 20
- terminal_joins: filled=14 timeout=6 canceled=0 unknown=1 rate=0.952
- calibration_relevant_terminal_join_rate: 1.000 (20/20)
- symbols: BTCUSDT, DOGEUSDT, ETHUSDT
- strategies: aurora
- source_fsms: CloseExecutor, ExecPosFSM
- post_t5d_runtime_hours: 53.76
- preferred_sample_met: NO

config_truth:
- trading.execution.watchdog.fill_ttl_ms observed/confirmed: SSOT config=1800000; runtime_marker_confirmed=9; post_boundary_old_marker=0
- per_order_override expected: expected=1200000; observed_values=1200000; relevant_timeout_near_20m=5/6
- global_watchdog observed: observed_cases=0; runtime_ttl_marker=9

runtime_windows:
- W01 2026-05-19T01:40:36.104000Z -> 2026-05-19T03:05:01.741000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W02 2026-05-19T03:05:01.742000Z -> 2026-05-20T00:47:32.195000Z orders=5 metadata=5 aurora_limit_gtx=5 join_rate=1.000
- W03 2026-05-20T00:47:32.196000Z -> 2026-05-20T01:00:04.623000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W04 2026-05-20T01:00:04.624000Z -> 2026-05-20T03:46:54.457000Z orders=1 metadata=1 aurora_limit_gtx=1 join_rate=1.000
- W05 2026-05-20T03:46:54.458000Z -> 2026-05-20T06:15:06.125000Z orders=1 metadata=1 aurora_limit_gtx=1 join_rate=1.000
- W06 2026-05-20T06:15:06.126000Z -> 2026-05-21T07:25:37.024000Z orders=14 metadata=13 aurora_limit_gtx=13 join_rate=0.929
- W07 2026-05-21T07:25:37.025000Z -> 2026-05-21T08:00:07.436000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W08 2026-05-21T08:00:07.437000Z -> 2026-05-21T08:05:21.753000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W09 2026-05-21T08:05:21.754000Z -> 2026-05-21T10:59:33.681000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W10 2026-05-21T10:59:33.682000Z -> 2026-05-21T11:04:48.259000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W11 2026-05-21T11:04:48.260000Z -> 2026-05-21T07:26:00.546000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000

timing_distributions:
- age_to_first_fill_ms: count=15 min=227 p50=170949 p75=408272 p90=571435 p95=649100 p99=747442 max=772028
- age_to_timeout_ms: count=6 min=1200168 p50=1200511 p75=1200900 p90=1509210 p95=1663325 p99=1786617 max=1817440
- age_to_cancel_ms: count=6 min=1200956 p50=1201214 p75=1201607 p90=1509902 p95=1664002 p99=1787282 max=1818103
- age_to_terminal_ms: count=20 min=227 p50=408272 p75=1200175 p90=1200689 p95=1231803 p99=1700312 max=1817440

regression_checks:
- per_order_override_dominates: PASS all 20/20 Aurora LIMIT/GTX rows retained per_order_override=1200000
- any_30min_global_backstop_timeout: PASS count=0
- per_order_override_timeout_near_30m: FAIL count=1
- 8718122009 ETHUSDT terminal=timeout age_to_timeout_ms=1817440 age_to_first_fill_ms=14964 fill_ttl_source=per_order_override fill_ttl_override_ms=1200000
- global_watchdog_cases: count=0
- none
- stale_watchdog_check: NO_STALE_WATCHDOG_AFTER_T5D
- none

verdict_rationale:
- minimum post-T5D sample not met: runtime_hours=53.76, post_t5d_order_placed_total=21
- PASS all 20/20 Aurora LIMIT/GTX rows retained per_order_override=1200000
- override timeout distribution near 20m: 5/6 relevant timeout rows
- any 30m global backstop timeout on calibration path: NO
- per-order override timeout still near 30m: YES
- stale watchdog verdict: NO_STALE_WATCHDOG_AFTER_T5D
- overall unknown joins are isolated to non-calibration CloseExecutor market rows; calibration-relevant join rate remained complete

runtime_behavior_change:
- per_order_override_timeout_near_30m: count=1

config_changes:
- NONE

unproven:
- post-boundary order behavior after the explicit 1800000 runtime startup remains unproven
- global_watchdog order path remains unobserved in post-T5D ORDER_PLACED metadata

risks:
- explicit 1800000 runtime startup is retained, but runtime collected after that boundary is still below the minimum 24h / 30 ORDER_PLACED sample
- per-order override metadata was retained on at least one Aurora LIMIT/GTX row whose timeout still drifted toward 1800000
- overall terminal join rate is diluted by 1 non-calibration CloseExecutor market rows with no retained terminal join

next_recommended_package:
- continue runtime collection until minimum post-T5D sample is met
