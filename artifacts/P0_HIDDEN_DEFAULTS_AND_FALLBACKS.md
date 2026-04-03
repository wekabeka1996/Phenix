# P0 Hidden Defaults And Fallbacks

This file lists the defaulted behaviors that can change runtime semantics without an explicit SSOT decision.

## 1. Silent fallback from missing config

| surface | evidence | hidden default | risk | confidence |
|---|---|---|---|---|
| system.market_data.bar_ttl_ms | apps/reference/domains/regime_detector/regime_detector.py:377; apps/reference/domains/decision_making/readiness_gates.py:337 | 10000 ms | stale-bar behavior remains live even when the intended config owner is absent | PROVEN |
| system.market_data.bar_event_age_mode | apps/reference/domains/decision_making/readiness_gates.py:339 | received | age semantics can silently drift to received-time mode | PARTIALLY_PROVEN |
| trading.execution.watchdog.rps_limit | apps/reference/domains/execution_position/watchdog.py:98 | 10 RPS | REST polling throttle becomes implicit because ExecPosFSM does not pass config | PROVEN |
| trading.execution.cooldown_ms | apps/reference/domains/execution_position/fsm.py:1533-1538; apps/reference/domains/execution_position/fsm_open.py:117-128 | 1000 ms in creator path; 1.0 s in constructor | open-flow throttle can remain live under compatibility-style defaults | PROVEN |
| strategies.aurora.decision.reentry_cooldown_sec | apps/reference/domains/decision_making/aurora_config_loader.py:328-332 | 60.0 s | a missing owner silently becomes a 60-second anti-ping-pong policy | PROVEN |
| strategies.aurora.assets.<SYMBOL>.trailing_stop.min_update_interval_sec | apps/reference/domains/execution_position/fsm_manage.py:300-306 | 5 s | missing per-symbol field still yields a live cadence | PROVEN |

## 2. Constructor defaults with no canonical YAML owner

| surface | evidence | constructor default | risk | confidence |
|---|---|---|---|---|
| execution_position.order_index.entry_guard_ttl_sec | apps/reference/domains/execution_position/order_index.py:43-52; apps/reference/main.py:264-265 | 120 s | one-open-order guard age is not operator-configurable and is easy to overlook in audits | PROVEN |
| telemetry.trade_lifecycle.orphan_ttl_sec | apps/reference/telemetry/trade_lifecycle_logger.py:121-131; apps/reference/telemetry/trade_lifecycle_logger.py:393 | 3600 s | stale-open cleanup timing is implicit | PROVEN |
| telemetry.trade_lifecycle.auto_sweep_interval_sec | apps/reference/telemetry/trade_lifecycle_logger.py:123-131; apps/reference/telemetry/trade_lifecycle_logger.py:393 | 60 s | telemetry sweep cadence is implicit | PROVEN |
| trading.execution.watchdog.check_interval_ms | apps/reference/domains/execution_position/watchdog.py:56-68; apps/reference/domains/execution_position/fsm.py:593-597 | 1000 ms | timeout polling interval looks configurable but stays fixed in the live constructor path | PROVEN |

## 3. Hardcoded policy overrides that shadow typed fields

| surface | evidence | hardcoded behavior | risk | confidence |
|---|---|---|---|---|
| domains.decision_making.entry_plan.obi_missing_policy | apps/reference/domains/decision_making/aurora_config_loader.py:445; apps/reference/config_models.py:2336 | ObiMissingPolicy.NEUTRAL is forced at load time | operator-selected policy is not honored | PROVEN |
| strategies.llm_microstructure.enabled | config/docs/llm_microstructure_strategy_passport.md:55-58,286-288; apps/reference/domains/strategies/plugins/llm_microstructure.py:27-42 | no direct consumer proven in the bridge path | disable semantics remain split across profile, registry, and llm orchestration | PARTIALLY_PROVEN |

## 4. Compatibility probes that hide ownership drift

| surface | evidence | hidden compatibility behavior | risk | confidence |
|---|---|---|---|---|
| trailing ownership | apps/reference/domains/decision_making/aurora_config_loader.py:400-431; apps/reference/domains/execution_position/fsm_manage.py:300-306,1632-1705 | Aurora handler probes config.instruments while execution_position reads strategies.aurora.assets.<SYMBOL>.trailing_stop | different components can disagree about trailing enablement and source-of-truth | PARTIALLY_PROVEN |
| hardening.ttl_config.* | config/docs/system_passport.md:602-640; artifacts/P0_NEGATIVE_FINDINGS.md:21-25 | fields remain typed and documented but act as metadata-only | operators can mistake metadata for enforced runtime behavior | PROVEN |

## 5. Planning implication

Defaults are not automatically wrong. The problem is hidden ownership. A default is safe only when:

- the canonical owner is explicit,
- the runtime consumer is proven,
- the fallback is intentionally documented, and
- tests assert the fallback contract.

Any surface failing one of those checks should be treated as SSOT debt, not as a harmless convenience.
