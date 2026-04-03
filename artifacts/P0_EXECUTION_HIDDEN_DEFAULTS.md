# P0 Execution Hidden Defaults

This artifact is intentionally narrow: only execution-critical timeout, TTL, cooldown, cleanup, and fallback surfaces uncovered during the audit are listed.

Status standard:
- PROVEN: direct code evidence for active default/fallback.
- PARTIALLY PROVEN: default or storage exists, but live effect is not fully proven.

## Hidden defaults and fallback surfaces

| Surface | Effective hidden/default value | Why it is hidden | Runtime effect | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| ExecPosFSM compatibility probe for trading.orders.default_ttl_seconds | None today; live if alias appears | Canonical typed field is trading.execution.orders.default_ttl_seconds, but fsm.py probes trading.orders and root orders instead | Can silently compete with watchdog fill_ttl_ms | PROVEN | apps/reference/domains/execution_position/fsm.py:555-592 |
| OpenFlowFSM cooldown_sec constructor default | 1.0s | Constructor default exists even though composition normally passes cooldown_sec | Suppresses rapid-repeat CMD:OPEN if composition stops providing explicit value | PROVEN | apps/reference/domains/execution_position/fsm_open.py:119-127; 438-440 |
| ExecPosFSM fallback for trading.execution.cooldown_ms | 1000ms | No typed ExecutionConfig.cooldown_ms field; fallback is read through aget(exec_config, cooldown_ms, 1000) | Current workspace still gets a live open-repeat cooldown despite no canonical YAML owner | PROVEN | apps/reference/domains/execution_position/fsm.py:1535-1537; apps/reference/config_models.py:1908-1932 |
| OrderTimeoutWatchdog check_interval_ms | 1000ms | YAML + typed model exist, but live constructor call does not pass the value | Poll loop cadence stays default-owned | PROVEN | apps/reference/domains/execution_position/fsm.py:594-596; apps/reference/domains/execution_position/watchdog.py:62; 69; 378 |
| OrderTimeoutWatchdog rps_limit | 10 | YAML + typed model exist, but live constructor call does not pass the value | REST poll throttle stays default-owned | PROVEN | apps/reference/domains/execution_position/fsm.py:594-596; apps/reference/domains/execution_position/watchdog.py:98; 190-205 |
| OrderIndex entry_guard_ttl_sec | 120s | OrderIndexConfig exposes only ttl_sec; main.py wires only ttl_sec | One-open-entry suppression horizon is code-owned, not operator-owned | PROVEN | apps/reference/domains/execution_position/order_index.py:43-52; apps/reference/main.py:239-265; apps/reference/config_models.py:3544-3548 |
| TradeLifecycleLogger orphan_ttl_sec | 3600s | Module-level singleton is created without YAML injection | Stale open telemetry cleanup horizon is default-owned | PROVEN | apps/reference/telemetry/trade_lifecycle_logger.py:122-130; 206-220; 393 |
| TradeLifecycleLogger auto_sweep_interval_sec | 60s | Module-level singleton is created without YAML injection | Sweep cadence for stale telemetry records is default-owned | PROVEN | apps/reference/telemetry/trade_lifecycle_logger.py:122-130; 193; 393 |
| orphan_monitor.min_order_age_sec | 0 stored in _orphan_cfg | Typed and stored, but no audited consumer was proven | Appears controllable but may not change cleanup behavior | PARTIALLY PROVEN | apps/reference/domains/execution_position/fsm.py:415; apps/reference/domains/execution_position/order_guardian.py:887-1042 |
| orphan_monitor.batch_cancel_limit | 50 stored in _orphan_cfg; OrderGuardian also has batch_limit=50 default | Matching numbers hide missing wiring | May look live even if cleanup_orphans uses only its own default argument | PARTIALLY PROVEN | apps/reference/domains/execution_position/fsm.py:416; apps/reference/domains/execution_position/order_guardian.py:887-891; 1042 |
| orphan_monitor.rate_limit_per_min | 120 stored in _orphan_cfg | Typed and stored, but no audited consumer was proven | False-control risk for cleanup pacing | PARTIALLY PROVEN | apps/reference/domains/execution_position/fsm.py:417; apps/reference/domains/execution_position/order_guardian.py:887-1042 |
| fsm_manage wait_mode_bars fallback | 2 bars in exception path | Code keeps a fallback for degraded config loading even though comment says fail-closed | Emergency WAIT_MODE still has a residual default path if config load errors | PROVEN | apps/reference/domains/execution_position/fsm_manage.py:131-139 |

## Hidden defaults that are not safe to reinterpret as dead code

1. OpenFlowFSM cooldown_sec and OrderIndex.entry_guard_ttl_sec are live execution policies, not harmless leftovers.
2. TradeLifecycleLogger orphan cleanup defaults are not execution-order timeout owners, but they can distort lifecycle forensics if treated as operator-configured surfaces.
3. watchdog.check_interval_ms and watchdog.rps_limit are not dead fields; they are half-wired fields with live constructor defaults.

## Hidden defaults that are safest to clean up first

1. Shadow alias reads for default_ttl_seconds in ExecPosFSM.
2. Missing propagation of watchdog.check_interval_ms into the live watchdog constructor.
3. Missing propagation of watchdog.rps_limit into the live watchdog constructor.

## Hidden defaults that should stay untouched in the first slice

1. valid_for_ms resolution for both internal and external LIMIT paths.
2. OrderIndex.entry_guard_ttl_sec, because it needs a contract decision, not just wiring.
3. TradeLifecycleLogger cleanup timings, because they sit in observability cleanup rather than the core order timeout chain.
4. orphan_monitor.min_order_age_sec, batch_cancel_limit, and rate_limit_per_min, because they need a dedicated consumer audit before any schema or runtime change.
