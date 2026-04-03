# P0 Execution Implementation Boundary

Package ID: P0_EXECUTION_TIMEOUT_TTL_DEEP_FORENSIC

Purpose:
- Define the smallest safe next implementation slice after the timeout / TTL / cooldown forensic audit.
- Explicitly separate safe cleanup from high-blast-radius timing semantics.

## Facts

1. The live global watchdog timeout owners are trading.execution.watchdog.ack_ttl_ms and trading.execution.watchdog.fill_ttl_ms.
2. Internal LIMIT lifetime is owned by domains.execution_position.pending_entry_ttl.ttl_by_tf_sec and materialized as valid_for_ms.
3. External LIMIT lifetime is owned by payload valid_for_ms when present, else strategies.llm_microstructure.pending_entry_ttl_ms.
4. trading.execution.orders.default_ttl_seconds is typed but miswired; ExecPosFSM probes trading.orders.default_ttl_seconds and root orders.default_ttl_seconds instead.
5. watchdog.check_interval_ms and watchdog.rps_limit are typed and present in YAML, but they are not passed into the live watchdog constructor.
6. cooldown_after_close_ms, anti_race_close_ms, wait_mode_bars, guardian cleanup timing, and intent boundary audit TTLs are already materially live.
7. OrderIndex.entry_guard_ttl_sec and TradeLifecycleLogger orphan/sweep timings are live code policies with no proven canonical YAML owner.
8. orphan_monitor.min_order_age_sec, batch_cancel_limit, and rate_limit_per_min are only partially proven because storage was observed but material consumers were not.

## WHAT IS SAFE TO TOUCH NEXT

1. Remove or quarantine the shadow alias reads for default_ttl_seconds inside apps/reference/domains/execution_position/fsm.py:555-592.
2. Pass check_interval_ms and rps_limit from canonical watchdog config into the live OrderTimeoutWatchdog constructor in apps/reference/domains/execution_position/fsm.py:594-596.
3. Add narrow regression tests that prove the above two changes without touching order lifetime semantics.
4. Update passport/docs only after runtime behavior is changed and revalidated.

## WHAT MUST NOT BE TOUCHED YET

1. Do not change the internal valid_for_ms chain from domains.execution_position.pending_entry_ttl.ttl_by_tf_sec through intent_builder, fsm_open, open_executor, and watchdog override.
2. Do not change the external fallback precedence between payload valid_for_ms and strategies.llm_microstructure.pending_entry_ttl_ms.
3. Do not change cooldown_after_close_ms, anti_race_close_ms, wait_mode_bars, guardian cleanup_ttl_ms, guardian symbol_cooldown_ms, or intent boundary audit TTL semantics in the same slice.
4. Do not reinterpret OrderIndex.entry_guard_ttl_sec as dead code; it needs a dedicated contract decision.
5. Do not rewire orphan_monitor.min_order_age_sec, batch_cancel_limit, or rate_limit_per_min until a real audited consumer is proven.
6. Do not modify TradeLifecycleLogger orphan_ttl_sec or auto_sweep_interval_sec in the first slice; they are observability-cleanup policies, not the core execution timeout chain.
7. Do not delete or repurpose system.hardening.ttl_config.* based only on this audit; the audited claim is limited to no proven Python execution_position consumer.

## MINIMUM IMPLEMENTATION SLICE

1. In ExecPosFSM initialization, stop probing trading.orders.default_ttl_seconds and root orders.default_ttl_seconds.
2. Keep watchdog ack_ttl_ms and fill_ttl_ms semantics exactly as they are today.
3. Extend the OrderTimeoutWatchdog construction call so the live instance also receives check_interval_ms and rps_limit from canonical config.
4. Add focused tests that prove:
   - shadow default_ttl_seconds paths no longer influence runtime;
   - watchdog.check_interval_ms reaches watchdog.check_interval_ms;
   - watchdog.rps_limit reaches watchdog._rps_limit;
   - existing fill_ttl / pending_entry_ttl and external valid_for_ms tests remain green.
5. Defer every other timing contract question to later slices.

## REQUIRED VALIDATION BEFORE ANY CHANGE

1. Keep the existing focused pytest subset green:
   - tests/domains/execution_position/test_external_open_request.py
   - tests/domains/execution_position/test_external_open_request_wiring.py
   - tests/domains/execution_position/test_fill_pipeline_fix.py
2. Add at least one focused watchdog wiring test that instantiates the live composition path and asserts configured check_interval_ms and rps_limit reach the watchdog instance.
3. Add or update one regression test that proves shadow default_ttl_seconds aliases are ignored or removed from the execution path.
4. Confirm no new reads of trading.orders.default_ttl_seconds or root orders.default_ttl_seconds remain in apps/reference/domains/execution_position.
5. Confirm startup/runtime logging still reports the intended watchdog settings after wiring changes.
6. Re-check passports after runtime validation; if docs and runtime diverge, document the conflict before editing docs.

## Why This Slice Is Safe

1. It collapses two false-control surfaces without changing the true LIMIT lifetime owners.
2. It improves operator truthfulness for watchdog cadence/throttle without changing timeout callbacks or order-state transitions.
3. It keeps close-side and guardian protections outside the blast radius.

## Why Larger Slices Are Unsafe Right Now

1. Combining shadow alias cleanup with valid_for_ms changes would mix global timeout policy and per-order LIMIT lifetime semantics.
2. Combining watchdog wiring with orphan monitor rewiring would mix proven and unproven cleanup consumers.
3. Combining timeout cleanup with close-side guards would risk regressions in already-live protections that are not broken.
