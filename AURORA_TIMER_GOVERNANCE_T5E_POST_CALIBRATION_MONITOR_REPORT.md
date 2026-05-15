AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR
verdict: NOT_ENOUGH_POST_T5D_RUNTIME
report_path: AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR_REPORT.md

facts:
- post_t5d_boundary: 2026-05-15T13:06:10.321000Z (runtime_1800000_startup; candidates: config_mtime=2026-05-13T20:18:55.924000Z; report_mtime=2026-05-13T23:04:50.646000Z; runtime_1800000_startup=2026-05-15T13:06:10.321000Z; first_order_after_report=2026-05-14T02:55:02.195000Z)
- logs_inspected: json=24 text=84 report=1 config=1 scanned_files=108
- runtime_windows: 6
- total_order_placed: 0
- metadata_order_placed: 0
- aurora_limit_gtx_entries: 0
- terminal_joins: filled=0 timeout=0 canceled=0 unknown=0 rate=0.000
- calibration_relevant_terminal_join_rate: 0.000 (0/0)
- symbols: none
- strategies: none
- source_fsms: none
- post_t5d_runtime_hours: 0.00
- preferred_sample_met: NO

config_truth:
- trading.execution.watchdog.fill_ttl_ms observed/confirmed: SSOT config=1800000; runtime_marker_confirmed=6; post_boundary_old_marker=0
- per_order_override expected: expected=1200000; observed_values=none; relevant_timeout_near_20m=0/0
- global_watchdog observed: observed_cases=0; runtime_ttl_marker=6

runtime_windows:
- W01 2026-05-15T13:06:10.321000Z -> 2026-05-15T13:13:24.500000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W02 2026-05-15T13:13:24.501000Z -> 2026-05-15T13:26:32.947000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W03 2026-05-15T13:26:32.948000Z -> 2026-05-15T13:35:34.075000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W04 2026-05-15T13:35:34.076000Z -> 2026-05-15T13:44:33.232000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W05 2026-05-15T13:44:33.233000Z -> 2026-05-15T13:51:28.513000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000
- W06 2026-05-15T13:51:28.514000Z -> 2026-05-15T13:06:10.321000Z orders=0 metadata=0 aurora_limit_gtx=0 join_rate=0.000

timing_distributions:
- age_to_first_fill_ms: count=0
- age_to_timeout_ms: count=0
- age_to_cancel_ms: count=0
- age_to_terminal_ms: count=0

regression_checks:
- per_order_override_dominates: NO_RELEVANT_ROWS
- accidental_30min_timeout_on_override_path: PASS count=0
- global_watchdog_cases: count=0
- none
- stale_watchdog_check: INSUFFICIENT_EVIDENCE
- none

verdict_rationale:
- minimum post-T5D sample not met: runtime_hours=0.00, post_t5d_order_placed_total=0
- NO_RELEVANT_ROWS
- override timeout distribution near 20m: 0/0 relevant timeout rows
- accidental 30m timeout on override path: NO
- stale watchdog verdict: INSUFFICIENT_EVIDENCE

runtime_behavior_change:
- NONE

config_changes:
- NONE

unproven:
- post-boundary order behavior after the explicit 1800000 runtime startup remains unproven
- global_watchdog order path remains unobserved in post-T5D ORDER_PLACED metadata

risks:
- explicit 1800000 runtime startup is retained, but runtime collected after that boundary is still below the minimum 24h / 30 ORDER_PLACED sample

next_recommended_package:
- continue runtime collection until minimum post-T5D sample is met
