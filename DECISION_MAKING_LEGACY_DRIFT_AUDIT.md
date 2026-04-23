# Decision Making Legacy Drift Audit

## Scope

Read-only legacy/drift audit for the decision_making namespace.

This document separates proven dead/residue surfaces from active migration seams and from surfaces that were initially suspicious but are not dead on code evidence.

## Evidence Discipline

- FACT: directly inspected in code, startup wiring, registry, local metadata, or guardrail tests.
- INFERENCE: derived from grouped facts.
- ASSUMPTION: explicitly marked if used.
- UNKNOWN: cannot be closed from inspected artifacts alone.

## FACTS

### 1. Surfaces that looked suspicious but are not dead

| Surface | Classification | Fact |
| --- | --- | --- |
| [apps/reference/config/domains/decision_making.py](apps/reference/config/domains/decision_making.py) | Active SSOT | decision_making is owned by a typed DecisionMakingDomainConfig, not by a generic DomainModeConfig placeholder |
| [apps/reference/domains/decision_making/gates/risk_skew_gate.py](apps/reference/domains/decision_making/gates/risk_skew_gate.py) | Active runtime consumer | until_refresh_max_hold_sec is consumed in the risk_skew gate |
| [apps/reference/main.py](apps/reference/main.py) | Active startup-only consumer | portfolio_warmup_timeout_sec is consumed by startup portfolio guarantee logic |
| [apps/reference/domains/decision_making/dm_config_spec.py](apps/reference/domains/decision_making/dm_config_spec.py) + [apps/reference/domains/decision_making/readiness_gates.py](apps/reference/domains/decision_making/readiness_gates.py) | Active migration seam | degraded_context_contracts_by_strategy is preferred; degraded_context_critical_keys_by_strategy and degraded_context_critical_keys remain fallback surfaces |
| [apps/reference/domains/strategies/plugins/mean_reversion.py](apps/reference/domains/strategies/plugins/mean_reversion.py) + [apps/reference/domains/strategies/plugins/md_amr.py](apps/reference/domains/strategies/plugins/md_amr.py) | Active runtime wiring | mean_reversion and md_amr handlers are still wired via StrategyRuntime; they are not package-dead merely because they live under decision_making |

### 2. Strongest proven residue / legacy candidates

| Surface | Classification | Fact | Audit weight |
| --- | --- | --- | --- |
| [apps/reference/domains/decision_making/deferred_scheduler.py](apps/reference/domains/decision_making/deferred_scheduler.py) | Strong legacy/dead candidate | Instantiation logs TOMBSTONE_HIT; workspace search found no runtime consumer outside local file, package export, and tests | High |
| [apps/reference/domains/decision_making/__init__.py](apps/reference/domains/decision_making/__init__.py) | Stale public surface | Exports DeferredIntentScheduler and describes QuadraticScoringKernel in module docstring even though DeferredIntentScheduler has no runtime consumer and QuadraticScoringKernel is not exported there | High |
| [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) DecisionMakingLogic alias | Compatibility residue | DecisionMakingLogic = DecisionMaking is kept for backward compatibility; workspace search found only a test import using the alias | Medium |
| [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py) handle_tick | Compatibility residue | Method emits periodic status only and no longer owns market-tick processing | Medium |
| [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json) | Metadata drift surface | Local metadata still lists DeferredIntentScheduler and exports verbs that diverge from central registry/runtime truth | High |

### 3. Process and documentation drift

| Surface | Classification | Fact |
| --- | --- | --- |
| [\.agent/skills/AGENTS.md](.agent/skills/AGENTS.md) vs repository docs tree | Process drift | AGENTS.md requires docs/ai policy artifacts, but docs/ai is absent on disk |
| [apps/reference/domains/decision_making/__init__.py](apps/reference/domains/decision_making/__init__.py) | Documentation drift | Module docstring still presents decision_making as one central decision engine and mentions components that are not clearly aligned with active runtime use |
| [apps/reference/domains/decision_making/domain_dict.json](apps/reference/domains/decision_making/domain_dict.json) | Metadata drift | Local domain metadata mixes active surfaces, residue, and undeclared/dormant verbs |

### 4. Active migration seams that should not be misclassified as dead

| Surface | Why it is a migration seam, not dead code |
| --- | --- |
| degraded_context_contracts_by_strategy vs degraded_context_critical_keys_by_strategy vs degraded_context_critical_keys | New strategy-scoped contracts are authoritative when present; older key bundles are still used as compatibility fallback in ReadinessGates |
| Strategy-local reject handling in Aurora, MeanReversion, and MD-AMR | The implementations differ, but they are still active runtime paths, not unreachable code |
| portfolio_warmup_timeout_sec | Startup-only consumption makes it non-dead even though it is not used inside DM runtime files |

## INFERENCES

- The strongest dead/residue signal in the namespace is DeferredIntentScheduler. It is exported, documented, locally tested, and explicitly tombstoned, but not wired into inspected runtime startup.
- The second major drift layer is public-surface drift: __init__.py and domain_dict.json preserve a wider, older picture of the domain than the currently proven runtime wiring.
- Some suspicious config fields are not dead code at all; they are startup-only or compatibility-fallback surfaces. Treating them as dead would be a false positive.
- The namespace has accumulated both runtime owners and compatibility residue in one folder, which makes grep-level “dead code” judgments unreliable without wiring checks.

## ASSUMPTIONS

- None used for the strong classifications above.

## UNKNOWNS

- No external package consumers outside the workspace were inspected, so DecisionMakingLogic and package-export compatibility may still be needed for imports not visible here.
- No live runtime telemetry was used to prove that DeferredIntentScheduler is never instantiated in production. The current classification is “strong legacy/dead candidate,” not absolute removal proof.
- No broad README or docs audit beyond inspected files was performed, so additional stale references may exist outside the files cited here.
