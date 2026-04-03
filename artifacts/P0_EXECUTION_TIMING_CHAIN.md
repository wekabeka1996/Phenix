# P0 Execution Timing Chain

Status standard:
- PROVEN: full config -> loader -> composition -> consumer chain observed in current workspace.
- PARTIALLY PROVEN: config or storage observed, but material consumer not proven.
- UNPROVEN: no audited live consumer.

## Chain A. Internal strategy LIMIT lifetime

Verdict: PROVEN

1. Config owner: domains.execution_position.pending_entry_ttl.ttl_by_tf_sec is declared in config at config/aurora/domains.yaml:479-487 and typed in apps/reference/config_models.py:3695-3721.
2. Resolution: decision_making resolves LIMIT order policy in apps/reference/domains/decision_making/intent_builder.py:518-523 by reading ttl_by_tf_sec[tf_sec] and converting it to valid_for_ms.
3. Guardrail: if tf_sec is absent and reject_unknown_tf is true, the request is rejected in apps/reference/domains/decision_making/intent_builder.py:523-539.
4. Transport: valid_for_ms is attached to the trade intent payload in apps/reference/domains/decision_making/intent_builder.py:234-282 and carried into execution_position via apps/reference/domains/execution_position/intent_router.py:161.
5. Execution contract: LIMIT opens require valid_for_ms in apps/reference/domains/execution_position/fsm_open.py:90-91 and again in apps/reference/domains/execution_position/open_executor.py:457-458.
6. Watchdog materiality: open_executor forwards valid_for_ms as fill_ttl_override_ms in apps/reference/domains/execution_position/open_executor.py:623-633.
7. Runtime timeout: watchdog switches from ACK timeout to FILL timeout and uses the per-order override in apps/reference/domains/execution_position/watchdog.py:325-347.

Fact:
- Internal LIMIT lifetime is not owned by trading.execution.orders.default_ttl_seconds.

Inference:
- Any remediation that touches shadow timeout aliases must preserve this valid_for_ms -> fill_ttl_override_ms chain unchanged.

## Chain B. External / LLM LIMIT lifetime

Verdict: PROVEN

1. Bridge boundary: the LLM mapper emits CMD:EXTERNAL_OPEN_REQUEST_V1 with valid_for_ms set to None in apps/reference/domains/shadow_telemetry/main_bridge.py:203-223.
2. Config fallback owner: strategies.llm_microstructure.pending_entry_ttl_ms is declared in config/aurora/strategies/llm_microstructure.yaml:6 and typed in apps/reference/config_models.py:4797-4806.
3. Resolution precedence: intent_router first accepts explicit payload valid_for_ms when >= 1000, else falls back to llm_microstructure.pending_entry_ttl_ms, else rejects in apps/reference/domains/execution_position/intent_router.py:393-429.
4. Command build: the resolved TTL is written into CMD:OPEN in apps/reference/domains/execution_position/intent_router.py:443.
5. Execution contract: the same LIMIT guards as the internal path apply in apps/reference/domains/execution_position/fsm_open.py:90-91 and apps/reference/domains/execution_position/open_executor.py:457-458.
6. Watchdog materiality: resolved valid_for_ms becomes the per-order fill timeout override in apps/reference/domains/execution_position/open_executor.py:623-633 and apps/reference/domains/execution_position/watchdog.py:341-347.
7. Validation proof: tests confirm config fallback and payload precedence in tests/domains/execution_position/test_external_open_request.py:124-142 and listener-to-CMD:OPEN wiring in tests/domains/execution_position/test_external_open_request_wiring.py:106-147.

Fact:
- External LIMIT lifetime is execution-owned at the router boundary, not at shadow_telemetry.

Inference:
- Removing or changing router fallback precedence is not part of the safest first timeout cleanup slice.

## Chain C. Orphan / cleanup cadence and adjacent false-control fields

Verdict: MIXED

1. Config block: orphan_monitor.enabled/run_on_startup/periodic_interval_sec/min_order_age_sec/batch_cancel_limit/rate_limit_per_min exist at config/aurora/trading.yaml:103-109 and are typed in apps/reference/config_models.py:1498-1514.
2. Storage: ExecPosFSM copies these values into self._orphan_cfg in apps/reference/domains/execution_position/fsm.py:411-417.
3. Live cadence: lifecycle cleanup uses periodic_interval_sec to sleep and then invoke cleanup_orphans in apps/reference/domains/execution_position/lifecycle.py:106-108.
4. Startup path: lifecycle also calls cleanup_orphans on startup in apps/reference/domains/execution_position/lifecycle.py:165.
5. Cleanup worker: OrderGuardian.cleanup_orphans defines its own batch_limit parameter default at apps/reference/domains/execution_position/order_guardian.py:887-891 and enforces it at apps/reference/domains/execution_position/order_guardian.py:1042.
6. Missing proof: no audited forwarding from _orphan_cfg.min_order_age_sec, _orphan_cfg.batch_cancel_limit, or _orphan_cfg.rate_limit_per_min into cleanup_orphans was found.
7. Adjacent live guard: guardian.cleanup_ttl_ms and guardian.symbol_cooldown_ms are used by entry_tidy_gate_allow in apps/reference/domains/execution_position/event_handlers.py:752-767.
8. Telemetry-adjacent cleanup: TradeLifecycleLogger carries orphan_ttl_sec and auto_sweep_interval_sec as constructor defaults and instantiates a singleton without YAML injection in apps/reference/telemetry/trade_lifecycle_logger.py:122-130 and apps/reference/telemetry/trade_lifecycle_logger.py:393.

Fact:
- periodic_interval_sec is live.
- guardian.cleanup_ttl_ms and guardian.symbol_cooldown_ms are live.
- min_order_age_sec, batch_cancel_limit, and rate_limit_per_min are only partially proven.
- TradeLifecycleLogger cleanup timings are live but default-only.

Inference:
- Cleanup timing remediation must stay split across three owners: orphan loop cadence, guardian tidy-entry gating, and telemetry stale-record sweeping.

## Chain D. Post-close anti-repeat and downstream boundary protection

Verdict: PROVEN

1. Global post-close cooldown owner: trading.execution.cooldown_after_close_ms is declared in config/aurora/trading.yaml:117 and typed in apps/reference/config_models.py:1928.
2. Init: ExecPosFSM fail-closes if this value is missing and stores _cooldown_after_close_sec in apps/reference/domains/execution_position/fsm.py:298-309.
3. Timestamp source: close events update _last_position_closed_ts and _last_any_position_closed_ts in apps/reference/domains/execution_position/event_handlers.py:205-206.
4. Guard: new CMD:OPEN requests are rejected while now - last_close is below the cooldown in apps/reference/domains/execution_position/fsm.py:1622-1634.
5. Anti-race owner: trading.execution.anti_race_close_ms is declared at config/aurora/trading.yaml:118, typed in apps/reference/config_models.py:1932, loaded in apps/reference/domains/execution_position/fsm_manage.py:141-153, and enforced in apps/reference/domains/execution_position/fsm_manage.py:866-869.
6. Emergency owner: trading.execution.manage.emergency.wait_mode_bars is declared at config/aurora/trading.yaml:112-113, typed at apps/reference/config_models.py:1484-1492, loaded in apps/reference/domains/execution_position/fsm_manage.py:131-139, and applied when emergency WAIT_MODE is entered in apps/reference/domains/execution_position/fsm_manage.py:1377-1392.
7. Boundary audit owner: domains.execution_position.intent_boundary_audit.route_ttl_ms/downstream_ttl_ms are declared at config/aurora/domains.yaml:597-600, typed at apps/reference/config_models.py:3937-3951, loaded in apps/reference/domains/execution_position/intent_boundary_audit.py:54-59, and enforced in apps/reference/domains/execution_position/intent_boundary_audit.py:145-159.

Fact:
- These protections are already materially live and should be treated as out-of-scope for the first cleanup slice.

Inference:
- Combining shadow-timeout cleanup with close-side guard changes would enlarge blast radius without improving forensic certainty.
