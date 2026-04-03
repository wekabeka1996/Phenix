# P0 SSOT Runtime Drift Remediation Plan Report

## 1. Executive verdict

Facts:
- The workspace still contains multiple operator-facing config fields whose live runtime consumer is absent, split, or only partially proven.
- The highest-risk drift is concentrated on execution-critical surfaces: request TTL metadata in hardening.ttl_config.*, the miswired default order TTL override, duplicate exposure TTL ownership, and split trailing ownership.
- Several passports were already repaired to state the current truth. The main remaining document-level drift in the audited set is aurora_math_passport.md overstating OBI as a direct quadratic scoring essential.

Inference:
- The safest remediation strategy is not a broad refactor. It is an owner-collapse program that first stabilizes execution timeout and exposure surfaces, then unifies freshness semantics, then cleans up strategy-specific inert knobs, and only then rewrites passports.

Bottom line:
- YAML + Pydantic are not yet the sole operational truth for the audited surfaces. Some fields are typed but inert, some are documented but compatibility-only, and some are split across multiple ownership stories. The package in artifacts/ is intended to drive a bounded owner-by-owner cleanup, not a redesign.

## 2. Evidence base

This report is based on current workspace code, current config, and existing forensic artifacts already present in the repository.

Primary inputs:
- artifacts/P0_NEGATIVE_FINDINGS.md
- artifacts/P0_DRIFT_AND_CONTRADICTION_LEDGER.md
- artifacts/P0_TIMER_TTL_CENSUS.csv
- artifacts/P0_DECISION_CRITICAL_FEATURE_MAP.csv
- reports/OBI_TFI_RUNTIME_INFLUENCE_RESEARCH.md
- reports/P0_RUNTIME_INFLUENCE_AND_TIMING_FORENSIC_REPORT.md

Runtime/code anchors used for this package:
- apps/reference/domains/execution_position/fsm.py
- apps/reference/domains/execution_position/fsm_open.py
- apps/reference/domains/execution_position/fsm_manage.py
- apps/reference/domains/execution_position/watchdog.py
- apps/reference/domains/execution_position/order_index.py
- apps/reference/domains/execution_position/exposure_guard.py
- apps/reference/domains/regime_detector/regime_detector.py
- apps/reference/domains/decision_making/readiness_gates.py
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_holding_period.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/strategies/plugins/llm_microstructure.py
- apps/reference/domains/shadow_telemetry/main_bridge.py
- apps/reference/telemetry/trade_lifecycle_logger.py
- apps/reference/main.py
- apps/reference/config_models.py

Supporting config/passport anchors:
- config/aurora/system.yaml
- config/aurora/trading.yaml
- config/aurora/domains.yaml
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/md_amr.yaml
- config/aurora/strategies/llm_microstructure.yaml
- config/docs/system_passport.md
- config/docs/trading_passport.md
- config/docs/aurora_math_passport.md
- config/docs/AURORA_STRATEGY_CONFIG_PASSPORT.md
- config/docs/md_amr_strategy_passport.md
- config/docs/llm_microstructure_strategy_passport.md
- config/docs/strategies_passport.md

## 3. Facts by drift class

### 3.1 Proven dead or inert config

Proven:
- hardening.ttl_config.entry_place_ttl_ms has no proven Python runtime consumer.
- hardening.ttl_config.bracket_place_ttl_ms has no proven Python runtime consumer.
- hardening.ttl_config.cancel_ttl_ms has no proven Python runtime consumer.
- trading.execution.exposure.pending_ttl_sec is not the active ExposureGuard owner.
- trading.execution.exposure.post_fill_hold_ttl_sec is not the active ExposureGuard owner.
- system.trailing.min_update_interval_sec has no proven live consumer in execution_position.
- domains.decision_making.entry_plan.obi_missing_policy is typed but hard-overridden to neutral in AuroraConfigLoader.
- system.market_data.tick_ttl_ms does not affect the standard RegimeDetector bar-mode path because tf_sec == 0 returns before freshness logic.

Operational implication:
- These are the most dangerous forms of SSOT drift because they invite deliberate tuning while guaranteeing no corresponding runtime change.

### 3.2 Proven miswires and partial wiring

Proven:
- trading.execution.orders.default_ttl_seconds is read from the wrong namespace in ExecPosFSM.
- trading.execution.watchdog.check_interval_ms exists in watchdog code but is not injected into the live constructor path.
- trading.execution.watchdog.rps_limit exists in watchdog code but is not injected into the live constructor path.

Partially proven:
- strategies.md_amr.reconciliation.interval_sec has local reconciliation code nearby, but no direct interval owner was proven in the inspected handler path.
- strategies.llm_microstructure.enabled has no confirmed direct bridge/startup gate in the inspected path.

Operational implication:
- These surfaces are especially likely to create "I changed the config and nothing happened" incidents, because the field is not fully dead. It is merely disconnected from the live owner path.

### 3.3 Split ownership and compatibility drift

Proven:
- ExposureGuard TTL ownership lives under domains.execution_position.exposure_guard.*, not trading.execution.exposure.*.
- Similar names do not always mean duplicate owners: domains.position_tracking.positions_stale_ttl_sec and domains.execution_position.exposure_guard.stale_ttl_sec govern different behaviors.

Partially proven but high risk:
- execution_position trailing reads strategies.aurora.assets.<SYMBOL>.trailing_stop.* while AuroraConfigLoader still performs a compatibility probe against config.instruments.* before building ExitManager.

Operational implication:
- A split owner is riskier than a dead field because different components can behave "correctly" according to different sources at the same time.

### 3.4 Hidden defaults and silent fallbacks

Proven:
- bar_ttl_ms silently defaults to 10000 ms in RegimeDetector and readiness gates.
- OpenFlowFSM can inherit a 1000 ms compatibility fallback from its creator path.
- OrderIndex.entry_guard_ttl_sec is a constructor default with no proven YAML owner.
- TradeLifecycleLogger.orphan_ttl_sec and auto_sweep_interval_sec are singleton defaults with no proven YAML owner.
- strategies.aurora.decision.reentry_cooldown_sec falls back to 60.0 s if missing, though the current live YAML sets it explicitly.

Partially proven:
- bar_event_age_mode semantics are not evidently uniform across all stale-data consumers.

Operational implication:
- Silent fallbacks are not only a documentation problem. They erase the difference between "configured on purpose" and "running on accident," which makes incident response and drift debugging materially harder.

## 4. Mandatory surface verdicts

### 4.1 Execution/order TTL surfaces

Proven problematic:
- hardening.ttl_config.entry_place_ttl_ms
- hardening.ttl_config.bracket_place_ttl_ms
- hardening.ttl_config.cancel_ttl_ms
- trading.execution.orders.default_ttl_seconds
- trading.execution.watchdog.check_interval_ms
- trading.execution.watchdog.rps_limit

Healthy baseline:
- watchdog ack_ttl_ms and fill_ttl_ms are still live constructor inputs in the inspected path.

### 4.2 Exposure duplicates and stale-position surfaces

Proven problematic:
- trading.execution.exposure.pending_ttl_sec
- trading.execution.exposure.post_fill_hold_ttl_sec

Important non-goal:
- domains.position_tracking.positions_stale_ttl_sec should not be auto-merged with exposure_guard.stale_ttl_sec until semantics are proven equivalent. Current evidence says they serve different purposes.

### 4.3 Watchdog/open-flow/defaults

Proven problematic or implicit:
- watchdog.check_interval_ms is not wired from YAML.
- watchdog.rps_limit is not wired from YAML.
- OpenFlowFSM cooldown still depends on compatibility defaults when owner data is absent.
- OrderIndex.entry_guard_ttl_sec is an implicit code policy.
- TradeLifecycleLogger orphan and sweep timings are implicit code policies.

### 4.4 Market-data freshness surfaces

Proven problematic:
- tick_ttl_ms is inert in the standard RegimeDetector bar-mode path.
- bar_ttl_ms has a silent fallback.

Partially proven:
- bar_event_age_mode may produce domain-specific freshness semantics that are not consistently shared by RegimeDetector.

### 4.5 Strategy drift surfaces

Proven problematic:
- domains.decision_making.entry_plan.obi_missing_policy is inert.

Partially proven:
- strategies.md_amr.reconciliation.interval_sec lacks a proven schedule owner in the inspected runtime.
- strategies.llm_microstructure.timeframe_sec and strategies.llm_microstructure.enabled remain split-semantic surfaces under a bridge-driven runtime.

### 4.6 Passport/doc drift surfaces

Proven drift:
- config/docs/aurora_math_passport.md still overstates OBI as a current global essential in the active quadratic story.

Already-corrected passports that should not be regressed:
- trading_passport.md for default_ttl_seconds, exposure TTL duplicates, watchdog partial wiring.
- system_passport.md for tick_ttl_ms caveat and hardening.ttl_config.* metadata-only status.
- md_amr_strategy_passport.md for reconciliation caution.
- llm_microstructure_strategy_passport.md and strategies_passport.md for sentinel/bridge-driven ownership.

## 5. Severity summary

P0:
- hardening.ttl_config.* dead safety surfaces
- trading.execution.orders.default_ttl_seconds miswire
- trading.execution.exposure.* duplicate ownership
- trailing ownership split across Aurora handler compatibility probe and execution_position per-symbol config

P1:
- watchdog.check_interval_ms and watchdog.rps_limit partial wiring
- bar_ttl_ms hidden fallback
- system.trailing.min_update_interval_sec dead global default
- obi_missing_policy inert override
- md_amr.reconciliation.interval_sec partial wiring

P2:
- tick_ttl_ms inert in standard RegimeDetector path
- OpenFlowFSM cooldown compatibility defaults
- OrderIndex.entry_guard_ttl_sec hidden constant
- TradeLifecycleLogger orphan/sweep timings hidden constants
- llm_microstructure timeframe and enabled semantics remain split and only partially proven

Control surface:
- aurora.decision.reentry_cooldown_sec appears healthy and should be used as a regression guard during cleanup.

## 6. Root-cause classes

1. Declared-but-not-used fields survived schema evolution.
2. Compatibility probing preserved old paths instead of failing closed.
3. Duplicate YAML ownership was left in place after consumer migration.
4. Some docs were repaired, but other docs still summarize old architecture rather than current runtime truth.
5. Several defaults are code-local rather than SSOT-owned, which hides behavior during incident response.

## 7. Duplicate and split ownership map

### 7.1 True duplicate ownership that should collapse

- trading.execution.exposure.pending_ttl_sec vs domains.execution_position.exposure_guard.pending_ttl_sec
- trading.execution.exposure.post_fill_hold_ttl_sec vs domains.execution_position.exposure_guard.post_fill_ttl_sec
- trailing ownership between strategies.aurora.assets.<SYMBOL>.trailing_stop.* and AuroraConfigLoader compatibility probing of config.instruments.*

### 7.2 Similar names that should not be auto-merged

- domains.position_tracking.positions_stale_ttl_sec
- domains.execution_position.exposure_guard.stale_ttl_sec

Reason:
- The first governs position freshness / flip deferral logic.
- The second governs exposure cleanup logic.

### 7.3 Split runtime ownership stories

- llm_microstructure profile semantics are split across the strategy profile, strategies registry, trading.llm_orchestration, and the bridge path.
- Market-data freshness semantics are split across RegimeDetector and DecisionMaking readiness gates.

## 8. Hidden defaults and fallback inventory

See artifacts/P0_HIDDEN_DEFAULTS_AND_FALLBACKS.md for the full list.

Most important items:
- silent 10000 ms bar freshness fallback
- unwired watchdog cadence and RPS fields falling back to constructor behavior
- OpenFlowFSM cooldown compatibility defaults
- hidden OrderIndex and TradeLifecycleLogger timing constants
- hardcoded OBI missing policy neutralization

## 9. Recommended remediation order

See artifacts/P0_REMEDIATION_SEQUENCE.md for the ordered phase plan.

Condensed recommendation:
1. Clean execution timeout surfaces first.
2. Collapse exposure and trailing ownership second.
3. Unify freshness semantics third.
4. Clean strategy-specific inert knobs fourth.
5. Rewrite passports last.

Rationale:
- Execution and exposure surfaces are the highest blast-radius drift class.
- Freshness cleanup is important, but it should not block urgent execution SSOT repair.
- Passport rewrites before owner collapse are likely to be wrong again.

## 10. Validation gates for future implementation work

Every remediation PR should include:
- a static owner trace showing the canonical config path and the exact consumer file/line,
- a config-load assertion that fails closed when the chosen owner is absent, unless a fallback is explicitly part of the contract,
- a focused runtime or integration trace proving the chosen owner changes live behavior,
- a passport update only after the runtime proof exists.

Minimum targeted validation by cluster:
- execution_position timeout surfaces: watchdog, default_ttl_seconds, open-flow cooldown, order index guard
- exposure ownership: ExposureGuard tests plus position/flip deferral tests
- freshness semantics: stale tick and stale bar replay across RegimeDetector and DecisionMaking
- strategy surfaces: Aurora entry-plan tests, MD-AMR reconciliation trace, LLM bridge trace

## 11. What remains unproven

Partially proven:
- Whether bar_event_age_mode should intentionally differ between DecisionMaking and RegimeDetector.
- The real schedule owner for strategies.md_amr.reconciliation.interval_sec.
- The exact live owner of llm_microstructure timeframe and enabled semantics beyond the already-proven sentinel/bridge split.
- The full runtime severity of the trailing ownership split on every active symbol under strict config.

Unproven by design in this package:
- Whether any of the candidate fixes improve profitability or execution quality. This is a contract and wiring remediation plan, not a tuning result.

## 12. Deliverables produced

Artifacts written by this package:
- artifacts/P0_DRIFT_SURFACE_INVENTORY.csv
- artifacts/P0_SEVERITY_AND_BLAST_RADIUS_MATRIX.csv
- artifacts/P0_REMEDIATION_SEQUENCE.md
- artifacts/P0_DOC_DRIFT_MATRIX.csv
- artifacts/P0_HIDDEN_DEFAULTS_AND_FALLBACKS.md
- reports/P0_SSOT_RUNTIME_DRIFT_REMEDIATION_PLAN_REPORT.md

## 13. Final recommendation

Do not attempt a single "make YAML the SSOT everywhere" change.

The safer path is:
- remove false execution safety surfaces first,
- collapse duplicate risk-control owners second,
- standardize stale-data semantics third,
- then clean strategy-specific drift,
- and only after that regenerate operator documentation.

That order minimizes blast radius while moving the repository toward a real single-source-of-truth model.
