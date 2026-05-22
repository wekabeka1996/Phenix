AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5E_RCA
verdict: C_PER_ORDER_OVERRIDE_NOT_APPLIED
report_path: AURORA_TIMER_GOVERNANCE_T5E_RCA_REPORT.md

problem:
- T5E regression localization was required before any rollback or fix because the earlier T5E report simultaneously claimed stale watchdog confirmation, a 30-minute global backstop timeout, and no root cause.
- Corrected T5E artifacts resolve those contradictions: the current monitor now reports any_30min_global_backstop_timeout PASS count=0, stale_watchdog_check NO_STALE_WATCHDOG_AFTER_T5D, and one remaining real timer defect row on order 8718122009.

facts:
- regression flags count: 2
- exact 30min timeout case: order 8718122009, window W06, placed 2026-05-20T21:55:01.457000Z, timeout 2026-05-20T22:25:18.897000Z, age_to_timeout_ms=1817440, terminal_state=timeout.
- exact stale watchdog case: none after corrected audit logic; current monitor says stale_watchdog_check NO_STALE_WATCHDOG_AFTER_T5D.
- identity match level: exact order/client_order_id/rid/lifecycle identity exists for the suspicious case across order log, trade lifecycle, shadow journal, runtime text logs, and current T5E CSVs.
- fill_ttl_source on suspicious rows: 8718122009 retained fill_ttl_source=per_order_override; no corrected global_watchdog row remains.
- fill_ttl_override_ms on suspicious rows: 1200000 on 8718122009; the sample-floor row is not an order-level case.
- Q1: the row that previously caused any_30min_global_backstop_timeout=YES was 8718122009, but corrected guard now removes it from the global bucket because ORDER_PLACED retained fill_ttl_source=per_order_override and fill_ttl_override_ms=1200000, it was not one of the 4 metadata-missing orders, it was entry path, and it was Aurora LIMIT/GTX.
- Q2: timeout_age max 1817440 is explained by runtime re-arming the partially filled order with global fill_ttl_ms after initial registration with per-order override; websocket partial-fill retention does this in event_handlers.py and REST-poll recovery does the same in watchdog.py.
- Q3: stale_watchdog is not lifecycle-confirmed after corrected audit logic; the old stale signal depended on bad terminal inference from partial ORDER_FILLED events. Current monitor correctly shows no confirmed stale watchdog case.
- Q4: T5D 1800000 did create a harmful live behavior, but not as a true global_watchdog order path. The harmful behavior is per-order override not being preserved on partial-fill retention, which drove a live timeout near 30 minutes.
- Q5: rollback should not be automatic. Within the allowed recommendation set, the nearest admissible no-rollback bucket is NO_ROLLBACK_RCA_POINTS_TO_STALE_LEAK, but the actual localized primary class is C_PER_ORDER_OVERRIDE_NOT_APPLIED.

casebook:
- path: AURORA_TIMER_GOVERNANCE_T5E_RCA_CASEBOOK.csv
- rows: 2

root_cause_vs_symptom:
- symptom: the earlier T5E report surfaced a 30-minute timeout and stale-watchdog narrative around 8718122009.
- root cause: after partial fill, the runtime kept the order tracked but re-armed its deadline with global fill_ttl_ms instead of preserving the original per-order 1200000 override.
- contributing factor: the original audit script treated ORDER_FILLED as terminal without cumulative-fill reconciliation, which misclassified 8718122009 as filled and inflated stale/global conclusions.
- masking factor: post-boundary runtime remains below the minimum sample floor, and shadow journal shows cross-origin duplicate fill exposure noise, both of which made the first T5E report harder to interpret.

classification:
- primary class: C_PER_ORDER_OVERRIDE_NOT_APPLIED
- evidence: ORDER_PLACED for 8718122009 retained fill_ttl_source=per_order_override and fill_ttl_override_ms=1200000; open_executor passes valid_for_ms into watchdog.track_order_placed; watchdog.on_order_ack honors the override; event_handlers partial-fill retention resets deadline to now + self._fsm.watchdog.fill_ttl_ms; watchdog REST-poll partial-fill retention resets deadline to current_time_ms + self.fill_ttl_ms; the order then timed out at 1817440 ms while still PARTIALLY_FILLED.
- why other classes were rejected: A rejected because corrected monitor shows any_30min_global_backstop_timeout PASS count=0 and no global_watchdog cases; B rejected because no legitimate terminal fill/cancel/position_closed existed before timeout and partial fills totaled only 1.162/1.725; D rejected because metadata was present on ORDER_PLACED; E rejected as primary because there was an audit false positive in the old report, but corrected artifacts still retain a real harmful timeout row; F rejected because evidence is sufficient across order, trade, shadow, runtime text logs, and runtime code.

rollback_decision:
- recommendation: NO_ROLLBACK_RCA_POINTS_TO_STALE_LEAK
- rationale: the allowed recommendation set has no dedicated no-rollback token for class C. Evidence does not support a true global-backstop regression, so rollback is not evidence-based. The next package should fix the partial-fill override rearm defect and rerun T5E/T5F instead of reverting fill_ttl_ms.

runtime_behavior_change:
- NONE

config_changes:
- NONE

script_changes:
- tools/audits/t5e_post_calibration_monitor.py now requires cumulative fills to reach placed quantity before assigning terminal_state=filled, so partial fills remain non-terminal.
- tools/audits/t5e_post_calibration_monitor.py now counts any_30min_global_backstop_timeout only for global_watchdog or metadata-missing rows and emits OVERRIDE_NOT_APPLIED_TIMEOUT_NEAR_30MIN for per_order_override rows that still drift near 1800000.

validation:
- py_compile: PASS
- script rerun: PASS; current monitor verdict is NOT_ENOUGH_POST_T5D_RUNTIME, post_t5d_boundary=2026-05-19T01:40:36.104000Z, post_t5d_order_placed_total=21, metadata_bearing_order_placed=20, aurora_limit_gtx_entries=20, terminal_join_rate=0.952, runtime_global_marker_confirmed=9. Corrected monitor report now shows any_30min_global_backstop_timeout PASS count=0, per_order_override_timeout_near_30m FAIL count=1, and stale_watchdog_check NO_STALE_WATCHDOG_AFTER_T5D.
- CSV parse: PASS; AURORA_TIMER_GOVERNANCE_T5E_ORDER_LIFECYCLES.csv rows=21, AURORA_TIMER_GOVERNANCE_T5E_WINDOW_SUMMARY.csv rows=11, AURORA_TIMER_GOVERNANCE_T5E_REGRESSION_FLAGS.csv rows=2, AURORA_TIMER_GOVERNANCE_T5E_RCA_CASEBOOK.csv rows=2.
- git diff --stat: full workspace diff is dirty and includes unrelated user changes (64 files, 5870 insertions, 1258 deletions). Scoped T5E package tracked diff shows AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR_REPORT.md and tools/audits/t5e_post_calibration_monitor.py with 322 insertions and 115 deletions.
- git diff --name-only: full workspace diff includes many unrelated files. Scoped T5E package tracked names are AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR_REPORT.md and tools/audits/t5e_post_calibration_monitor.py; AURORA_TIMER_GOVERNANCE_T5E_RCA_REPORT.md is untracked and AURORA_TIMER_GOVERNANCE_T5E_RCA_CASEBOOK.csv is ignored by current git rules.

unproven:
- The exact final rearm write that produced the 1817440 deadline cannot be uniquely assigned between websocket partial-fill retention and REST-poll partial-fill retention, because both code paths reset the deadline to the same 1800000 global TTL and both were active on this order.
- Post-boundary runtime breadth is still below the minimum 30 ORDER_PLACED floor, so the whole T5 line remains blocked even though the primary RCA for 8718122009 is sufficient.

next_recommended_package:
- DEF package to preserve per-order fill_ttl_override_ms across PARTIALLY_FILLED retention in watchdog.py and event_handlers.py, add a regression test for partial-fill timeout behavior, then rerun corrected T5E/T5F without changing config until runtime behavior is verified.
