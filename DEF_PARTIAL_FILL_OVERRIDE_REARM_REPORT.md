AGENT_REPORT_V1

task: DEF_PARTIAL_FILL_OVERRIDE_REARM
verdict: ROOT_CAUSE_LOCALIZED_AND_FIXED
report_path: DEF_PARTIAL_FILL_OVERRIDE_REARM_REPORT.md

problem:
- T5E RCA showed that order 8718122009 kept fill_ttl_source=per_order_override and fill_ttl_override_ms=1200000 at placement, but after PARTIALLY_FILLED the live deadline drifted toward the 1800000 global watchdog backstop and timed out at age_to_timeout_ms=1817440.
- This package had to preserve the per-order override across PARTIALLY_FILLED retention without changing any TTL config values, valid_for_ms calculation, or wider lifecycle semantics.

facts:
- RCA order: 8718122009, placed 2026-05-20T21:55:01.457000Z, timeout 2026-05-20T22:25:18.897000Z, age_to_timeout_ms=1817440, fill_ttl_source=per_order_override, fill_ttl_override_ms=1200000, terminal_state=timeout.
- exact faulty code path in event_handlers.py: _apply_fill_bookkeeping PARTIALLY_FILLED branch previously rewrote the retained watchdog deadline as get_clock().now_ms() + self._fsm.watchdog.fill_ttl_ms, which ignored any existing OrderDeadline.fill_ttl_override_ms.
- exact faulty code path in watchdog.py: _poll_order_statuses PARTIALLY_FILLED branch previously rewrote the retained watchdog deadline as current_time_ms + self.fill_ttl_ms, which ignored any existing OrderDeadline.fill_ttl_override_ms.
- existing OrderDeadline fields: order_id, client_order_id, symbol, deadline_ms, timeout_type, corr_id, rid, side, fill_ttl_override_ms.
- open_executor still registers fill_ttl_override_ms=valid_for_ms through track_order_placed, and on_order_ack already honored that override before this package.
- existing tests before edit already encoded: override wins on ACK, no override falls back to global TTL, PARTIALLY_FILLED remains retained/non-terminal, and FILLED deregisters.
- both live re-arm sites already computed deadline from now/current_time_ms + ttl, so current runtime semantics are extend-from-current-time rather than preserve-original-deadline.
- report research inputs read before editing: AURORA_TIMER_GOVERNANCE_T5E_RCA_REPORT.md, AURORA_TIMER_GOVERNANCE_T5E_RCA_CASEBOOK.csv, AURORA_TIMER_GOVERNANCE_T5E_POST_CALIBRATION_MONITOR_REPORT.md, AURORA_TIMER_GOVERNANCE_T5E_ORDER_LIFECYCLES.csv.

inferences:
- The defect was not in initial metadata capture or ACK-time conversion; it was loss of override strength during later PARTIALLY_FILLED deadline re-arm.
- Because both partial-fill retention branches used the same global-only recomputation, either live path could recreate the observed near-30m timeout behavior.
- The smallest safe repair is to derive an effective TTL from the existing OrderDeadline instead of changing any timer constants or branching rules.

assumptions:
- fill_ttl_override_ms should keep the repo's current truthy semantics, so 0 continues to fall back to the global TTL because existing code and tests already encode that behavior.
- Re-arming from current time is intentional current behavior and should remain unchanged in this package.

unknowns:
- Static code and retained logs do not uniquely prove which of the two partial-fill branches wrote the final buggy deadline last on 8718122009; both were faulty pre-fix and both are repaired now.
- Live post-fix runtime confirmation is still pending.

root_cause_vs_symptom:
- symptom: per-order-override entry orders could linger until near the 30-minute global watchdog backstop after PARTIALLY_FILLED.
- root cause: both partial-fill retention branches recomputed deadline using global fill_ttl_ms instead of using the effective TTL from the existing OrderDeadline.
- contributing factor: placement and ACK already preserved the override, which hid the defect until a partial fill occurred.
- masking factor: the wider execution_position suite currently has unrelated baseline failures, so full-folder green status is noisy and can obscure localized timer regressions.

implementation:
- files changed:
  - apps/reference/domains/execution_position/adapters/watchdog.py
  - apps/reference/domains/execution_position/orchestration/event_handlers.py
  - tests/domains/execution_position/test_watchdog_partial_fill_override_rearm.py
  - DEF_PARTIAL_FILL_OVERRIDE_REARM_REPORT.md
- fix summary:
  - added OrderDeadline.effective_fill_ttl_ms(fallback_fill_ttl_ms)
  - used that helper in watchdog.on_order_ack for consistent effective TTL resolution
  - used that helper in watchdog._poll_order_statuses PARTIALLY_FILLED retention
  - used that helper in event_handlers._apply_fill_bookkeeping PARTIALLY_FILLED retention
- behavior changed:
  - PARTIALLY_FILLED retained deadlines still extend from current time, but now preserve per-order fill_ttl_override_ms when present.
  - When no override exists, global fill_ttl_ms remains the fallback.
  - Existing OrderDeadline objects are mutated in place, so identity fields are preserved and no synthetic deadline object is invented.
- config changes: NONE
- TTL value changes: NONE

tests_added:
- test_rest_poll_partial_fill_preserves_override_ttl
- test_rest_poll_partial_fill_without_override_uses_global_ttl
- test_event_handler_partial_fill_preserves_override_ttl
- test_rest_poll_partial_fill_keeps_order_tracked_until_terminal_fill
- test_event_handler_partial_fill_does_not_trigger_terminal_cleanup
- test_event_handler_final_fill_still_deregisters
- test_timeout_fires_at_override_horizon_after_partial_rearm

validation:
- pytest tests/domains/execution_position/test_watchdog_partial_fill_override_rearm.py -q: PASS (7 passed)
- pytest tests/domains/execution_position/test_watchdog_ttl_governance.py -q: PASS (18 passed)
- pytest tests/domains/execution_position/test_watchdog_observability_t5c.py -q: PASS (12 passed)
- pytest tests/domains/execution_position/test_watchdog_dereg_after_fill.py -q: PASS (7 passed)
- pytest tests/domains/execution_position -k "watchdog or timeout" -q: PASS (102 passed, 1550 deselected)
- pytest tests/domains/execution_position -q: FAIL with 5 unrelated baseline failures after 593 passed and 1 skipped; failing files are test_emitted_surface_audit.py, test_execpos_fsm_recovery_ordering_v2.py (3 failures), and test_execution_position_boundary_policy_ast.py.
- git diff --stat: full workspace is already dirty and currently reports 81 files changed, 6813 insertions, 1329 deletions, mostly unrelated to this package. Scoped tracked diff for this package shows apps/reference/domains/execution_position/adapters/watchdog.py and apps/reference/domains/execution_position/orchestration/event_handlers.py with 78 insertions and 6 deletions.
- git diff --name-only: full workspace includes many unrelated files. Scoped tracked names for this package are apps/reference/domains/execution_position/adapters/watchdog.py and apps/reference/domains/execution_position/orchestration/event_handlers.py. The new test file and this report remain untracked until added, so they do not appear in git diff output.
- diagnostics: PASS for apps/reference/domains/execution_position/adapters/watchdog.py, apps/reference/domains/execution_position/orchestration/event_handlers.py, and tests/domains/execution_position/test_watchdog_partial_fill_override_rearm.py.

runtime_behavior_change:
- PARTIALLY_FILLED retained deadlines now preserve per-order fill_ttl_override_ms.
- Global fallback unchanged when no override exists.

config_changes:
- NONE

unproven:
- live runtime confirmation pending
- whether deadline should extend from current time vs original placement remains unchanged unless proven otherwise

risks:
- orders with override may timeout earlier than the buggy global-rearm path, but that matches the intended per-order TTL semantics already encoded at placement and ACK.
- fill_ttl_override_ms=0 still falls back to global because current code and tests treat zero as falsy; this package intentionally preserves that pre-existing behavior.

next_recommended_package:
- T5F post-fix runtime monitor for partial-fill override preservation
