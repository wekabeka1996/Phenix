# P0 Execution Timeout / TTL Deep Forensic Report

Package ID: P0_EXECUTION_TIMEOUT_TTL_DEEP_FORENSIC

Date: 2026-04-02

Scope:
- Execution-critical timeout / TTL / cooldown / fallback surfaces affecting order lifetime, open request lifetime, ACK waiting, fill waiting, one-open-entry suppression, post-close cooldown, anti-race close behavior, orphan cleanup cadence, and downstream boundary audit.

Non-goals:
- No implementation.
- No refactor.
- No schema rewrite.
- No deletions.
- No docs rewrite as the final outcome.

Evidence standard:
- PROVEN: full config -> typed model -> loader -> composition -> consumer chain observed in the current workspace.
- PARTIALLY PROVEN: config/storage observed, but material consumer not proven.
- UNPROVEN: no audited live consumer.

Process caveat:
- .github/copilot-instructions.md references docs/ai reporting protocol files under docs/ai/*. Those paths were not present in the current workspace at authoring time, so this package follows the repo instructions that were present plus runtime-first forensic rules.

## Executive Findings

### Facts

1. trading.execution.orders.default_ttl_seconds is not the live runtime owner for order lifetime today.
2. The real internal LIMIT lifetime owner is domains.execution_position.pending_entry_ttl.ttl_by_tf_sec, materialized as valid_for_ms and then as watchdog fill_ttl_override_ms.
3. The real external LIMIT lifetime owner is payload valid_for_ms when supplied, else strategies.llm_microstructure.pending_entry_ttl_ms.
4. trading.execution.watchdog.ack_ttl_ms and trading.execution.watchdog.fill_ttl_ms are fully wired.
5. trading.execution.watchdog.check_interval_ms and trading.execution.watchdog.rps_limit are typed and configured but not wired into the live watchdog instance.
6. system.hardening.ttl_config.entry_place_ttl_ms, bracket_place_ttl_ms, and cancel_ttl_ms have no proven Python execution_position consumer in the audited path.
7. trading.execution.cooldown_after_close_ms and trading.execution.anti_race_close_ms are live close-side protections.
8. trading.execution.cooldown_ms is not a proven canonical operator-owned field; the current open-repeat cooldown survives through a compatibility/default path.
9. OrderIndex.entry_guard_ttl_sec is a live hidden code policy with no proven canonical YAML owner.
10. orphan_monitor.periodic_interval_sec is live, but orphan_monitor.min_order_age_sec, batch_cancel_limit, and rate_limit_per_min are only partially proven.
11. guardian.cleanup_ttl_ms and guardian.symbol_cooldown_ms are live entry-reopen guards.
12. TradeLifecycleLogger orphan_ttl_sec and auto_sweep_interval_sec are live but default-only singleton cleanup policies.
13. intent_boundary_audit.route_ttl_ms and downstream_ttl_ms are live downstream forensic boundaries.

### Inference

1. The safest first implementation slice is not a general timeout cleanup; it is a narrow truth-restoration slice.
2. That slice should remove shadow default_ttl_seconds alias behavior and wire watchdog cadence/throttle fields into the live constructor.
3. Any larger slice would unnecessarily mix proven execution owners, unproven cleanup consumers, and already-live close-side protections.

## End-to-End Timing Chains

The detailed chain artifact is artifacts/P0_EXECUTION_TIMING_CHAIN.md. The shortest accurate summary is below.

### Chain 1. Internal strategy LIMIT lifetime

1. domains.execution_position.pending_entry_ttl.ttl_by_tf_sec is declared at config/aurora/domains.yaml:479-487 and typed at apps/reference/config_models.py:3695-3721.
2. intent_builder resolves tf_sec -> valid_for_ms in apps/reference/domains/decision_making/intent_builder.py:518-523.
3. LIMIT requests reject if valid_for_ms is missing in apps/reference/domains/execution_position/fsm_open.py:90-91 and apps/reference/domains/execution_position/open_executor.py:457-458.
4. open_executor passes valid_for_ms as fill_ttl_override_ms in apps/reference/domains/execution_position/open_executor.py:623-633.
5. watchdog uses that per-order override at apps/reference/domains/execution_position/watchdog.py:341-347.

Verdict:
- PROVEN

### Chain 2. External / LLM LIMIT lifetime

1. shadow_telemetry emits CMD:EXTERNAL_OPEN_REQUEST_V1 with valid_for_ms=None in apps/reference/domains/shadow_telemetry/main_bridge.py:203-223.
2. intent_router resolves payload valid_for_ms first, else strategies.llm_microstructure.pending_entry_ttl_ms, else reject in apps/reference/domains/execution_position/intent_router.py:393-429.
3. Tests prove config fallback and payload precedence in tests/domains/execution_position/test_external_open_request.py:124-142.
4. Tests prove the event reaches CMD:OPEN in tests/domains/execution_position/test_external_open_request_wiring.py:106-147.

Verdict:
- PROVEN

### Chain 3. Cleanup / orphan timing

1. orphan_monitor.periodic_interval_sec is stored in ExecPosFSM at apps/reference/domains/execution_position/fsm.py:411-417.
2. lifecycle.py uses that interval to run cleanup_orphans at apps/reference/domains/execution_position/lifecycle.py:106-108.
3. cleanup_orphans owns a local batch_limit default at apps/reference/domains/execution_position/order_guardian.py:887-891.
4. No proven forwarding from min_order_age_sec, batch_cancel_limit, or rate_limit_per_min was found.
5. guardian cleanup_ttl_ms and symbol_cooldown_ms are live in entry_tidy_gate_allow at apps/reference/domains/execution_position/event_handlers.py:752-767.
6. TradeLifecycleLogger orphan_ttl_sec and auto_sweep_interval_sec are singleton defaults at apps/reference/telemetry/trade_lifecycle_logger.py:122-130 and 393.

Verdict:
- MIXED

### Chain 4. Post-close anti-repeat and downstream audit

1. cooldown_after_close_ms is loaded fail-closed in apps/reference/domains/execution_position/fsm.py:298-309 and enforced in apps/reference/domains/execution_position/fsm.py:1622-1634.
2. anti_race_close_ms is loaded in apps/reference/domains/execution_position/fsm_manage.py:141-153 and enforced in apps/reference/domains/execution_position/fsm_manage.py:866-869.
3. wait_mode_bars is loaded in apps/reference/domains/execution_position/fsm_manage.py:131-139 and applied when emergency WAIT_MODE is entered in apps/reference/domains/execution_position/fsm_manage.py:1377-1392.
4. intent_boundary_audit route/downstream TTLs are loaded in apps/reference/domains/execution_position/intent_boundary_audit.py:54-59 and enforced in apps/reference/domains/execution_position/intent_boundary_audit.py:145-159.

Verdict:
- PROVEN

## Ten Defect Answers

### 1. Is trading.execution.orders.default_ttl_seconds the live execution timeout owner?

Fact:
- No. The typed field exists at apps/reference/config_models.py:1905, but the runtime probe in ExecPosFSM reads trading.orders.default_ttl_seconds or root orders.default_ttl_seconds at apps/reference/domains/execution_position/fsm.py:555-592.

Verdict:
- PROVEN defect.

### 2. Do the shadow alias paths still affect runtime?

Fact:
- Yes. If a shadow alias appears, ExecPosFSM can still derive candidate_ms and may assign fill_ttl_ms = candidate_ms at apps/reference/domains/execution_position/fsm.py:580-590.

Verdict:
- PROVEN defect.

### 3. What is the real owner of internal LIMIT lifetime?

Fact:
- domains.execution_position.pending_entry_ttl.ttl_by_tf_sec, through valid_for_ms, through open_executor fill_ttl_override_ms, through watchdog override.

Verdict:
- PROVEN active owner.

### 4. What is the real owner of external LIMIT lifetime?

Fact:
- Payload valid_for_ms when present; otherwise strategies.llm_microstructure.pending_entry_ttl_ms.

Verdict:
- PROVEN active owner.

### 5. Are all watchdog knobs live-config-driven?

Fact:
- No. ack_ttl_ms and fill_ttl_ms are live. check_interval_ms and rps_limit are not wired through the live constructor.

Verdict:
- PROVEN half-wiring defect.

### 6. Are system.hardening.ttl_config.* fields live in the audited Python path?

Fact:
- No proven Python execution_position consumer was found for entry_place_ttl_ms, bracket_place_ttl_ms, or cancel_ttl_ms.

Verdict:
- PROVEN no-consumer finding for the audited path.

### 7. Is trading.execution.cooldown_ms a proven canonical config owner?

Fact:
- No. ExecutionConfig has no cooldown_ms field, the current trading.yaml has no canonical live key, and ExecPosFSM uses a fallback read at apps/reference/domains/execution_position/fsm.py:1535-1537.

Verdict:
- PROVEN fallback-only behavior.

### 8. Is OrderIndex.entry_guard_ttl_sec operator-controlled today?

Fact:
- No. OrderIndexConfig exposes only ttl_sec at apps/reference/config_models.py:3544-3548, main.py wires only ttl_sec at apps/reference/main.py:239-265, and OrderIndex keeps entry_guard_ttl_sec=120 in code at apps/reference/domains/execution_position/order_index.py:43-52.

Verdict:
- PROVEN hidden code policy.

### 9. Are orphan and cleanup timing fields consistently operator-owned?

Fact:
- No. periodic_interval_sec is live; guardian cleanup_ttl_ms and symbol_cooldown_ms are live; min_order_age_sec, batch_cancel_limit, and rate_limit_per_min are only stored/not fully proven; telemetry cleanup timings are default-only.

Verdict:
- MIXED / PARTIALLY PROVEN.

### 10. Are close-side suppression and downstream audit timings live?

Fact:
- Yes for cooldown_after_close_ms, anti_race_close_ms, route_ttl_ms, and downstream_ttl_ms. wait_mode_bars is live in code but currently inactive because emergency.enabled=false.

Verdict:
- PROVEN active protections.

## False-Control And Hidden-Default Surfaces

The detailed inventory is artifacts/P0_EXECUTION_HIDDEN_DEFAULTS.md.

Highest-risk false-control surfaces:

1. trading.execution.orders.default_ttl_seconds because the typed canonical field does not match the live runtime read path.
2. trading.execution.watchdog.check_interval_ms because it looks operator-controlled but is currently constructor-default-owned.
3. trading.execution.watchdog.rps_limit for the same reason.
4. orphan_monitor.batch_cancel_limit because the stored value matches OrderGuardian's local default 50, which can hide the missing wiring.
5. OrderIndex.entry_guard_ttl_sec because one-open-entry suppression is live but not operator-owned.

Highest-risk hidden defaults:

1. OpenFlowFSM.cooldown_sec default 1.0s.
2. TradeLifecycleLogger.orphan_ttl_sec default 3600s.
3. TradeLifecycleLogger.auto_sweep_interval_sec default 60s.
4. fsm_manage wait_mode_bars fallback 2 in degraded config path.

## What Is Safe To Touch Next

### Facts

1. Removing shadow alias probes for default_ttl_seconds does not require changing valid_for_ms semantics.
2. Wiring check_interval_ms and rps_limit into the watchdog constructor does not require changing timeout decisions, callback behavior, or state transitions.

### Recommended minimum slice

1. Remove or quarantine shadow reads of trading.orders.default_ttl_seconds and root orders.default_ttl_seconds from ExecPosFSM.
2. Pass check_interval_ms and rps_limit into the live OrderTimeoutWatchdog constructor.
3. Add focused regression tests for those two changes only.

### What must not be touched in that slice

1. valid_for_ms generation for internal LIMIT orders.
2. valid_for_ms fallback precedence for external LIMIT orders.
3. cooldown_after_close_ms, anti_race_close_ms, wait_mode_bars, guardian cleanup timing, and intent boundary audit TTLs.
4. OrderIndex.entry_guard_ttl_sec.
5. orphan_monitor.min_order_age_sec, batch_cancel_limit, and rate_limit_per_min.
6. TradeLifecycleLogger orphan/sweep defaults.

## Required Validation Before Any Change

1. Re-run the focused pytest subset that already validated the current chain:
   - tests/domains/execution_position/test_external_open_request.py
   - tests/domains/execution_position/test_external_open_request_wiring.py
   - tests/domains/execution_position/test_fill_pipeline_fix.py
2. Add one focused test proving the live watchdog instance receives check_interval_ms and rps_limit from canonical config.
3. Add one focused test proving shadow default_ttl_seconds aliases no longer influence runtime.
4. Confirm no new reads of trading.orders.default_ttl_seconds or root orders.default_ttl_seconds remain in apps/reference/domains/execution_position.
5. Re-check passports after runtime validation and document any runtime/doc conflict before editing docs.

## Validation Evidence Collected During This Audit

1. Focused pytest subset executed successfully in the configured virtual environment.
2. Result: 41 tests passed.
3. Files executed:
   - tests/domains/execution_position/test_external_open_request.py
   - tests/domains/execution_position/test_external_open_request_wiring.py
   - tests/domains/execution_position/test_fill_pipeline_fix.py
4. Static trace plus tests jointly prove:
   - external valid_for_ms fallback behavior;
   - external request -> CMD:OPEN wiring;
   - fill_ttl_ms >= max pending_entry_ttl expectation;
   - intended deprecation direction for default_ttl_seconds.

## Unproven Or Bounded Findings

1. This audit proves no Python execution_position consumer for system.hardening.ttl_config.* in the audited path. It does not prove the fields are unused outside that path.
2. This audit proves storage, but not material consumption, for orphan_monitor.min_order_age_sec, batch_cancel_limit, and rate_limit_per_min.
3. This audit does not claim that trade_lifecycle_logger cleanup timings are canonical SSOT fields; it only proves they are active default-only singleton policies.

## Deliverables

1. reports/P0_EXECUTION_TIMEOUT_TTL_DEEP_FORENSIC_REPORT.md
2. artifacts/P0_EXECUTION_TIMEOUT_SURFACE_MAP.csv
3. artifacts/P0_EXECUTION_TIMEOUT_DEFECT_MATRIX.csv
4. artifacts/P0_EXECUTION_TIMING_CHAIN.md
5. artifacts/P0_EXECUTION_HIDDEN_DEFAULTS.md
6. artifacts/P0_EXECUTION_IMPLEMENTATION_BOUNDARY.md
7. artifacts/P0_WATCHDOG_WIRING_TRACE.md
8. artifacts/P0_ORDER_TTL_NAMESPACE_TRACE.md
9. artifacts/P0_ORPHAN_AND_CLEANUP_TIMING_TRACE.md

## REPORT

STATUS: COMPLETE

PACKAGE_ID: P0_EXECUTION_TIMEOUT_TTL_DEEP_FORENSIC

OUTCOME:
- Forensic package created.
- No runtime code changed.
- No schema changed.

TOP CONCLUSIONS:
- default_ttl_seconds canonical field is miswired.
- check_interval_ms and rps_limit are half-wired.
- pending_entry_ttl and external pending_entry_ttl_ms chains are the real LIMIT lifetime owners.
- close-side protections are live and should stay out of the first cleanup slice.

SAFE NEXT SLICE:
- Remove shadow default_ttl_seconds alias reads.
- Wire watchdog check_interval_ms and rps_limit into the live constructor.
- Validate with focused tests only.
