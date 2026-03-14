# Documentation Forensics Audit Report: LLM Microstructure Strategy Passport

**Date:** 2026-03-13
**Target Document:** config/docs/llm_microstructure_strategy_passport.md
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope

This audit re-traced exactly one document: config/docs/llm_microstructure_strategy_passport.md.

The trace covered:

1. Strategy profile contract in strategies/llm_microstructure.yaml.
2. Registry and cross-config validation preconditions.
3. Plugin startup behavior.
4. Shadow telemetry API policy and ingress bridge.
5. Command mapping into strategy signals.
6. Downstream execution-policy and safety-gates consumers.

## 2. Files traced

### YAML
- config/aurora/strategies/llm_microstructure.yaml
- config/aurora/strategies.yaml

### Pydantic / config contracts
- apps/reference/config_models.py

### Runtime consumers
- apps/reference/main.py
- apps/reference/domains/strategies/registry.py
- apps/reference/domains/strategies/plugins/llm_microstructure.py
- apps/reference/domains/shadow_telemetry/main.py
- apps/reference/domains/shadow_telemetry/main_bridge.py
- apps/reference/domains/decision_making/strategy_gateway.py
- apps/reference/domains/decision_making/intent_builder.py
- apps/reference/domains/decision_making/safety_gates.py

### Tests
- tests/config/test_llm_strategy_contract_fail_closed.py
- tests/domains/shadow_telemetry/test_main_bridge.py

## 3. Confirmed claims

1. The profile is typed and loaded under `config.strategies.llm_microstructure`.
2. Profile loading depends on registry assignment.
3. Non-baseline LLM orchestration requires a non-empty `symbols_llm` list and matching registry assignment.
4. The plugin exists only as a sentinel allowlist handler.
5. The actual runtime path is bridge-driven through shadow_telemetry.
6. Upstream ingress policy rejects invalid symbol ownership, allowlist, TIF, TP/SL, telemetry, and quantity conditions.
7. Downstream execution order policy is resolved from strategy config in IntentBuilder.
8. Safety gates are resolved by strategy_id from the strategy profile.

## 4. Corrected claims

1. The old passport implied a more direct strategy-profile-to-runtime path than currently exists.
2. The old passport did not distinguish sentinel plugin startup from actual strategy behavior.
3. The old passport did not document the split authority between strategy profile and trading.llm_orchestration policy.
4. The old passport described `timeframe_sec` too literally without acknowledging the bridge mapper hardcode.
5. The old passport did not note that `enabled` lacks a traced direct runtime consumer in the bridge path.
6. The old passport did not capture that external order requests are upstream-filtered but final order policy is still re-resolved from strategy execution config.
7. The old passport omitted the fail-closed validator linking `symbols_llm` to registry assignment and profile presence.

## 5. Removed stale claims

1. LLM Microstructure as a normal in-process strategy handler.
2. Single-document ownership of all runtime behavior by the strategy YAML alone.

## 6. Added missing sections

1. Registry and llm_orchestration cross-validation.
2. Sentinel plugin behavior.
3. Shadow API / ingress bridge gating.
4. Command mapper semantics.
5. Downstream execution-policy resolution.
6. Safety-gates ownership.
7. Drift around `timeframe_sec` and `enabled`.

## 7. Dead / drifted / declared-but-unused fields

1. `llm_microstructure.type` behaves as metadata only in the traced runtime.
2. `llm_microstructure.description` behaves as metadata only in the traced runtime.
3. `llm_microstructure.enabled` is typed but no direct runtime consumer was found in the traced bridge/startup flow.
4. `llm_microstructure.timeframe_sec` drifts from the bridge-emitted `tf_sec=300`.

## 8. Final verdict

The LLM Microstructure passport is now synchronized to current runtime reality.

The main correction is architectural: this strategy is implemented as an external-intent ingress pipeline with a sentinel plugin, not as a conventional in-process strategy handler. The second correction is contract-splitting: the effective runtime is governed jointly by the strategy profile and the global `trading.llm_orchestration` policy, while bridge-emitted signal semantics currently drift from the profile on timeframe.

**Status: DONE**
