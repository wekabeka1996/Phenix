AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5F_POST_FIX_MONITOR
verdict: POST_FIX_HEALTHY
report_path: AURORA_TIMER_GOVERNANCE_T5F_POST_FIX_MONITOR_REPORT.md

facts:
- post_fix_boundary: 2026-05-26T13:00:02.753000Z
- boundary_basis: latest_change_evidence=git_commit_ts:last_touch_patch_or_report:2026-05-22T07:46:31Z; wrapper_paths_are_forwarders_to_owner_files; owner_mtimes=apps/reference/domains/execution_position/adapters/watchdog.py=2026-05-21T09:12:42.753000Z, apps/reference/domains/execution_position/orchestration/event_handlers.py=2026-05-21T09:12:43.524000Z; wrapper_mtimes=apps/reference/domains/execution_position/watchdog.py=2026-05-07T02:23:52.367000Z, apps/reference/domains/execution_position/event_handlers.py=2026-05-07T02:23:52.329000Z; git_commit_ts=2026-05-22T07:46:31Z; def_report_mtime=unavailable_in_worktree; first_runtime_startup_after_change=2026-05-26T11:50:01.187000Z; first_order_after_startup=2026-05-26T13:00:02.753000Z; chosen_boundary_source=first_order_placed_after_post_fix_startup
- logs_inspected: 60 files across logs/aurora_core.log*, logs/domain_execution_position.log*, logs/event_chain.log*, logs/order_guardian.log*, logs/order_log_v1.jsonl*, logs/shadow_critical_event_journal_v1.jsonl*, logs/trade_lifecycle.jsonl*
- runtime_windows: W01 2026-05-26T13:00:02.753000Z -> 2026-05-26T13:22:39.384000Z orders=1 partial_fill=1 joins=1.000 | W02 2026-05-26T13:22:39.385000Z -> 2026-05-26T16:00:02.752000Z orders=4 partial_fill=0 joins=0.750 | W03 2026-05-26T16:00:02.753000Z -> 2026-05-28T11:22:27.358000Z orders=13 partial_fill=6 joins=0.923 | W04 2026-05-28T11:22:27.359000Z -> 2026-05-28T11:40:00.922000Z orders=0 partial_fill=0 joins=0.000 | W05 2026-05-28T11:40:00.923000Z -> 2026-05-28T14:21:54.418000Z orders=0 partial_fill=0 joins=0.000 | W06 2026-05-28T14:21:54.419000Z -> 2026-05-28T14:22:43.686000Z orders=0 partial_fill=0 joins=0.000
- total_order_placed: 18
- metadata_order_placed: 16
- aurora_limit_gtx_entries: 16
- partial_fill_cases: 7
- terminal_joins: 16/18 rate=0.889
- symbols: BTCUSDT, DOGEUSDT, ETHUSDT
- strategies: aurora, close_executor

override_preservation:
- partial_fill_with_override: 7
- timeout_near_30m_after_partial_fill: 0
- timeout_near_20m_or_effective_override: 2
- override_not_applied_flags: 0

timing_distributions:
- age_to_first_fill_ms: count=14 min=275 p50=19123 p75=92109 p90=192544 p95=242860 p99=285335 max=295954
- age_to_partial_fill_ms: count=7 min=1085 p50=10312 p75=17110 p90=50084 p95=70228 p99=86343 max=90372
- age_to_timeout_ms: count=2 min=1200349 p50=1200540 p75=1200636 p90=1200693 p95=1200712 p99=1200728 max=1200732
- partial_fill_to_timeout_ms: count=0

regression_checks:
- override_rearm_regression: PASS partial_fill_override_cases=7 near_effective=0/0
- global_watchdog_cases: total=0 suspicious=0
- stale_watchdog_check: NO_STALE_WATCHDOG_AFTER_FIX

runtime_behavior_change:
- NONE

config_changes:
- NONE

unproven:
- DEF report file is absent in the worktree, so report filesystem timestamp could not be used directly

risks:
- no material residual runtime risk surfaced in retained T5F evidence

next_recommended_package:
- close the T5 timer-governance line or move to the next timer family
