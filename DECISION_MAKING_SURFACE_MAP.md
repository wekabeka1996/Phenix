# Decision Making Surface Map

## Scope

Read-only forensic map of the decision_making domain in Aurora/Phenix.

This document records codebase evidence gathered in this audit session. No runtime execution, replay, or live validation was performed for this deliverable.

## Evidence Discipline

- FACT: directly supported by inspected code, config, registry, startup wiring, or existing guardrail tests.
- INFERENCE: conclusion derived from multiple facts.
- ASSUMPTION: not used unless explicitly stated.
- UNKNOWN: cannot be proven from inspected artifacts alone.

## FACTS

### 1. SSOT and bootstrap chain

- The typed Pydantic owner for domains.decision_making is [apps/reference/config/domains/decision_making.py](apps/reference/config/domains/decision_making.py).
- That typed model is aggregated into [apps/reference/config/domains/_aggregator.py](apps/reference/config/domains/_aggregator.py), where DomainsConfig.decision_making is DecisionMakingDomainConfig.
- The YAML source for the domain lives in [config/aurora/domains.yaml](config/aurora/domains.yaml).
- Runtime startup registers strategy plugins in [apps/reference/main.py](apps/reference/main.py), then starts them through [apps/reference/domains/strategies/registry.py](apps/reference/domains/strategies/registry.py).
- Strategy runtime activation is keyed by strategies_registry.assignments, not by handler presence alone, per [apps/reference/domains/strategies/registry.py](apps/reference/domains/strategies/registry.py).

### 2. Active general-domain owner surfaces

| Surface | Runtime status | Proven role | Main inbound surfaces | Main outbound surfaces |
| --- | --- | --- | --- | --- |
| [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) | Active owner | Thin facade that composes DMState, DMConfigSpec, ReadinessGates, IntentEmitter, FlipOrchestrator, RegimeLossEmbargo, IntentBuilder, DMEventHandlers, StrategyGateway | EVT:FEATURES_CALCULATED, EVT:RISK_ASSESSMENT_COMPLETED, EVT:PORTFOLIO_STATE_UPDATED, EVT:REGIME_DETECTED, EVT:POSITION_CLOSED, EVT:EXPOSURE_SUMMARY_UPDATED, EVT:STRATEGY_SIGNAL_PRODUCED, EVT:SYSTEM_STRESS_STATE_UPDATED | TRADE_INTENT_PROPOSED path, TRADE_INTENT_REJECTED path, DECISION_TRACE_EMITTED path, regime-flip close path |
| [apps/reference/domains/decision_making/event_handlers.py](apps/reference/domains/decision_making/event_handlers.py) | Active owner | Owns ingress/caching for features, risk, portfolio, regime, exposure, and close facts | EVT:FEATURES_CALCULATED, EVT:RISK_ASSESSMENT_COMPLETED, EVT:PORTFOLIO_STATE_UPDATED, EVT:REGIME_DETECTED, EVT:POSITION_CLOSED, EVT:EXPOSURE_SUMMARY_UPDATED | EVT:DECISION_BLOCKED, EVT:ALPHA_SCORE_CALCULATED, reject WAL rows for invalid feature/timeframe payloads |
| [apps/reference/domains/decision_making/strategy_gateway.py](apps/reference/domains/decision_making/strategy_gateway.py) | Active owner | Canonical gate-chain owner for EVT:STRATEGY_SIGNAL_PRODUCED, including direct close and partial-close path handling | EVT:STRATEGY_SIGNAL_PRODUCED | Reject, defer, block, or TRADE_INTENT_PROPOSED dispatch |
| [apps/reference/domains/decision_making/intent_builder.py](apps/reference/domains/decision_making/intent_builder.py) | Active owner | Builds TRADE_INTENT_PROPOSED payloads, performs WAL append, commits arbitration, emits decision trace | Post-gateway passed intent proposals | EVT:TRADE_INTENT_PROPOSED, EVT:DECISION_TRACE_EMITTED |
| [apps/reference/domains/decision_making/intent_emitter.py](apps/reference/domains/decision_making/intent_emitter.py) | Active owner | Canonical helper for INTENT_DEFERRED, TRADE_INTENT_REJECTED, risk-gate alerting, and regime-flip close handling | Facade/helper calls | EVT:INTENT_DEFERRED, EVT:TRADE_INTENT_REJECTED, reduce-only close dispatch |
| [apps/reference/domains/decision_making/flip_orchestration.py](apps/reference/domains/decision_making/flip_orchestration.py) | Active owner | Resolves position_mode and routes reduce-only flip closes through the regular intent pipeline | Regime flip and position context | Reduce-only close proposal path |
| [apps/reference/domains/decision_making/regime_loss_embargo.py](apps/reference/domains/decision_making/regime_loss_embargo.py) | Active owner | Stateful embargo policy keyed by regime transitions and closed-position outcomes | Regime updates and position-closed facts | Gate state consumed by decision logic |

### 3. Strategy-local runtime owner surfaces

| Surface | Runtime status | Proven role | Wiring proof |
| --- | --- | --- | --- |
| [apps/reference/domains/strategies/plugins/aurora_builtin.py](apps/reference/domains/strategies/plugins/aurora_builtin.py) + [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py) | Active owner | Strategy-local Aurora runtime that consumes CMD:PROCESS_STRATEGY and other domain events, emits STRATEGY_SIGNAL_PRODUCED and STRATEGY_DECISION_BLOCKED, and contains additional objective/execution gating | Registered in [apps/reference/main.py](apps/reference/main.py); plugin listens to CMD:PROCESS_STRATEGY, EVT:REGIME_DETECTED, EVT:FEATURES_CALCULATED, EVT:TRADE_INTENT_REJECTED, and other runtime events |
| [apps/reference/domains/strategies/plugins/mean_reversion.py](apps/reference/domains/strategies/plugins/mean_reversion.py) + [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py) | Active owner | Strategy-local mean reversion runtime; emits STRATEGY_SIGNAL_PRODUCED and STRATEGY_DECISION_BLOCKED; performs handler-local gating and reject persistence | Registered in [apps/reference/main.py](apps/reference/main.py) and started by StrategyRuntime |
| [apps/reference/domains/strategies/plugins/md_amr.py](apps/reference/domains/strategies/plugins/md_amr.py) + [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py) | Active owner | Strategy-local md_amr runtime; owns warmup, restore, allowlist, deferred and reject side channels, and STRATEGY_SIGNAL_PRODUCED emission | Registered in [apps/reference/main.py](apps/reference/main.py) and started by StrategyRuntime |

### 4. Sanctioned non-owner and boundary surfaces

- [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py) owns CMD:PROCESS_STRATEGY emission and EVT:PROCESS_STRATEGY_BLOCKED emission.
- [apps/reference/domains/decision_making/strategy_bridge.py](apps/reference/domains/decision_making/strategy_bridge.py) is the sanctioned DM-facing import surface for FE-hosted strategy artifacts.
- [tests/domains/decision_making/test_fe_dm_boundary_guardrails.py](tests/domains/decision_making/test_fe_dm_boundary_guardrails.py) proves that DM production files must not import FE strategy modules directly, except through strategy_bridge.py.
- [tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py](tests/domains/decision_making/test_task32_dm_no_hardcoded_strategy_imports.py) proves that the general DecisionMaking facade is not allowed to hardcode MeanReversionHandler coupling.
- [apps/reference/dictionaries/verb_registry_v1.yaml](apps/reference/dictionaries/verb_registry_v1.yaml) is the central verb contract surface for commands/events.

### 5. Compatibility and residue surfaces inside the namespace

| Surface | Proven status | Fact |
| --- | --- | --- |
| [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) handle_tick | Compatibility seam | handle_tick emits periodic domain status only; it does not process market ticks |
| [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) DecisionMakingLogic alias | Compatibility seam | file ends with DecisionMakingLogic = DecisionMaking; workspace usage found only a legacy-style test import |
| [apps/reference/domains/decision_making/deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py) | Strong residue candidate | Scheduler logs TOMBSTONE_HIT on instantiation; workspace search found only local file, package export, and tests, but no runtime consumers |
| [apps/reference/domains/decision_making/__init__.py](apps/reference/domains/decision_making/__init__.py) | Mixed active+stale public surface | Package export surface still exposes DeferredIntentScheduler and describes QuadraticScoringKernel in the docstring, while inspected runtime wiring does not use DeferredIntentScheduler |
| [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json) | Local metadata surface | Local domain metadata exports QUADRATIC_DECISION_TRACE and HANDLER_READINESS_DIAGNOSTICS and lists DeferredIntentScheduler as a component |

### 6. Config surfaces that are active, not dead

- until_refresh_max_hold_sec is actively consumed by [apps/reference/domains/decision_making/gates/risk_skew_gate.py](apps/reference/domains/decision_making/gates/risk_skew_gate.py).
- portfolio_warmup_timeout_sec is actively consumed by startup logic in [apps/reference/main.py](apps/reference/main.py); it is startup-only, but not dead.
- fail_closed_on_degraded_context, degraded_context_critical_keys_by_strategy, and degraded_context_contracts_by_strategy are actively extracted in [apps/reference/domains/decision_making/dm_config_spec.py](apps/reference/domains/decision_making/dm_config_spec.py) and consumed by [apps/reference/domains/decision_making/readiness_gates.py](apps/reference/domains/decision_making/readiness_gates.py).
- The redesigned degraded-context path prefers strategy-scoped contracts when present, and only falls back to legacy key bundles when contracts are absent.

### 7. Policy/process gap discovered during audit

- [\.agent/skills/AGENTS.md](.agent/skills/AGENTS.md) requires several docs under docs/ai, including LLM_REASONING_CONSTITUTION.md, AURORA_DOMAIN_PROTOCOL.md, AGENT_TASK_PROMPT_STANDARD.md, AGENT_REPORT_SCHEMA.md, DONE_CRITERIA.md, and VERB_EVENT_INSTRUCTIONS.md.
- The repository contains [docs](docs), but docs/ai does not exist on disk.
- This is process evidence only. It is not runtime proof that decision_making is obsolete or incorrect.

## INFERENCES

- decision_making is not a single runtime owner. It is a namespace that currently contains both a general domain facade and multiple strategy-local runtimes.
- Cleanup should distinguish active owners from namespace residue before attempting removal. Removing files only because they live under decision_making would be unsafe.
- The cleanest conceptual boundary is:
  - feature_engineering owns bar-triggered strategy dispatch,
  - strategy-local handlers own strategy-specific scoring/gating,
  - StrategyGateway owns the canonical general-domain gate chain from STRATEGY_SIGNAL_PRODUCED to intent proposal,
  - IntentBuilder/IntentEmitter own canonical intent-truth shaping.

## ASSUMPTIONS

- None used for the ownership classifications above.

## UNKNOWNS

- No live, replay, or backtest execution was run in this audit, so runtime reachability is proven only by startup wiring, code paths, and existing tests.
- The exact production activation set depends on strategies_registry.assignments at runtime.
- No claim is made here about whether every strategy-local handler is still exercised in live operation; only that the startup/runtime wiring still exists.
