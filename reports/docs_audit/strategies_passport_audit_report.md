# Documentation Forensics Audit Report: Strategies Passport

**Date:** 2026-03-13
**Target Document:** config/docs/strategies_passport.md
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope

This audit re-traced exactly one document: config/docs/strategies_passport.md.

The trace covered:

1. Registry loading and validation.
2. Registry-driven profile loading.
3. Plugin allowlist and strategy runtime startup.
4. Assignment SSOT and arbitration.
5. Strategy profile ownership for execution and safety gates.
6. Strategy-specific activation semantics for Aurora, Mean Reversion, MD-AMR, and llm_microstructure.

## 2. Files traced

### YAML
- config/aurora/strategies.yaml
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/mean_reversion.yaml
- config/aurora/strategies/md_amr.yaml
- config/aurora/strategies/llm_microstructure.yaml

### Pydantic / config contracts
- apps/reference/config_models.py

### Runtime consumers
- apps/reference/config_loader.py
- apps/reference/main.py
- apps/reference/domains/strategies/registry.py
- apps/reference/domains/decision_making/config_resolver.py
- apps/reference/domains/decision_making/decision_making.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/mean_reversion_handler.py
- apps/reference/domains/decision_making/md_amr_handler.py
- apps/reference/domains/decision_making/intent_builder.py
- apps/reference/domains/strategies/plugins/aurora_builtin.py
- apps/reference/domains/strategies/plugins/mean_reversion.py
- apps/reference/domains/strategies/plugins/md_amr.py
- apps/reference/domains/strategies/plugins/llm_microstructure.py

## 3. Critical runtime consumers

1. ConfigLoader._merge_config_fragments()
2. ConfigLoader._resolve_mode_overrides()
3. StrategyRuntime.start()
4. DMConfigResolver.is_strategy_assigned()
5. DMConfigResolver.check_strategy_arbitration()
6. AuroraHandler._is_symbol_enabled()
7. MeanReversionHandler._parse_config()
8. MDAMRHandler assignment/config validation path
9. DecisionMaking._propose_trade_intent()
10. IntentBuilder.build_and_emit()

## 4. Confirmed claims

1. `config/aurora/strategies.yaml` is a mandatory startup file.
2. Registry content is loaded into `config.strategies_registry`.
3. Only assigned strategy IDs cause strategy profile YAMLs to be loaded.
4. StrategyRuntime starts handlers only for assigned strategy IDs.
5. Assigned strategy IDs must have allowlisted plugins.
6. DecisionMaking fail-closes when a strategy is not assigned to a symbol.
7. Priority arbitration is the only supported runtime arbitration mode.
8. IntentBuilder enforces strategy execution policy fail-closed.
9. DecisionMaking enforces safety-gates presence and deny outcomes before intent emission.
10. Mean Reversion validates assignment/profile consistency fail-closed.
11. MD-AMR validates assignment/profile/live-contract consistency fail-closed.

## 5. Corrected claims

1. The old passport overstated the role of generic profile metadata and understated assignment-first activation.
2. The old passport used stale file anchors around config loading and decision-making consumers.
3. The old passport did not state clearly that only assigned strategies trigger profile loading.
4. The old passport treated `aurora.enabled` too strongly; current Aurora activation is registry-first.
5. The old passport did not capture the stricter MR and MD-AMR assignment/config consistency checks.
6. The old passport did not distinguish `llm_microstructure` as a sentinel plugin plus external bridge path.
7. The old passport did not identify `arbitration.logging.log_level` as unused.
8. The old passport was missing the strategy-execution-policy consumer in intent_builder.
9. The old passport blurred together runtime registry and profile namespaces.

## 6. Removed stale claims

1. Strategy profiles as loosely consumed metadata.
2. `aurora.enabled` as the primary activation SSOT.
3. Generic references to unsupported arbitration modes as if they were runtime options.
4. `llm_microstructure` as a normal in-process handler strategy.

## 7. Added missing sections

1. Registry-driven profile loading.
2. Plugin allowlist and StrategyRuntime startup.
3. Order-policy ownership in strategy profiles.
4. Safety-gates ownership in strategy profiles.
5. Strategy-specific activation semantics for MR and MD-AMR.
6. Sentinel/bridge-driven status of llm_microstructure.
7. Declared-but-unused registry logging field.
8. Mode-override ownership for Aurora decision config.

## 8. Dead / legacy / declared-but-unused fields

1. `strategies_registry.arbitration.logging.log_level` is declared but not used.
2. Treating `aurora.enabled` as the hard activation switch is a stale assumption.
3. Treating llm_microstructure as a normal in-process handler is a stale assumption.

## 9. Open questions

No open questions remain for the current passport sync. Remaining issues are cleanup tasks, not evidence gaps.

## 10. Final verdict

The strategies passport is synchronized to current registry/profile runtime behavior.

The main correction is architectural: strategy activation in Aurora/Phenix is not a soft documentation layer around profile YAMLs. It is a strict fail-closed contract spanning registry assignments, Pydantic validation, registry-driven profile loading, allowlisted plugin startup, and downstream arbitration checks.

**Status: DONE**
