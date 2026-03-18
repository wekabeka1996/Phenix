# LLM MICROSTRUCTURE STRATEGY PASSPORT
## Aurora / Phenix — external-intent profile, shadow ingress policy, and bridge-driven runtime

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/llm_microstructure_strategy_passport.md`
> - **Audit date:** 2026-03-18
> - **Audit mode:** Code-driven sync
> - **Major drifts found:** No structural drifts since the previous 2026-03-13 audit. The configuration in `llm_microstructure.yaml` perfectly matches the documented execution policies and safety gates. The registry assignment (`1000PEPEUSDT`) remains accurate.
> - **Overall confidence:** HIGH

---

## 1. Scope

This passport covers exactly one strategy profile: config/aurora/strategies/llm_microstructure.yaml.

It traces:

1. Typed profile contract in `config.strategies.llm_microstructure`.
2. Registry assignment and load preconditions.
3. Plugin startup behavior.
4. Shadow telemetry ingress and command mapping.
5. Global LLM orchestration policy in trading config.
6. Downstream execution-policy and safety-gates consumers.

Authoritative sources traced for this passport:

- YAML: config/aurora/strategies/llm_microstructure.yaml, config/aurora/strategies.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/domains/strategies/plugins/llm_microstructure.py, apps/reference/domains/strategies/registry.py, apps/reference/domains/shadow_telemetry/main.py, apps/reference/domains/shadow_telemetry/main_bridge.py, apps/reference/domains/decision_making/strategy_gateway.py, apps/reference/domains/decision_making/intent_builder.py, apps/reference/domains/decision_making/safety_gates.py.
- Wiring: apps/reference/main.py.
- Tests: tests/config/test_llm_strategy_contract_fail_closed.py, tests/domains/shadow_telemetry/test_main_bridge.py.

---

## 2. Profile contract

### strategies.llm_microstructure
- Type: LLMMicrostructureStrategyConfig
- Logic Owner: config_models + shadow_telemetry / decision_making integration
- Runtime Role: typed strategy profile for externally generated intents.
- Actual Runtime Semantics:
  - Loaded only when `llm_microstructure` appears in registry assignments.
  - Current profile fields are:
    - `enabled: true`
    - `type: external_intent`
    - `description: External LLM intent strategy (contract-first ingress, fail-closed gates)`
    - `timeframe_sec: 60`
    - `execution.*`
    - `safety_gates.enabled: true`
- Constraints / Invariants:
  - Pydantic is strict with `extra='forbid'`.
- Status: ACTIVE

### strategies.llm_microstructure.enabled
- Type: bool
- Logic Owner: LLMMicrostructureStrategyConfig
- Runtime Role: typed profile flag with no confirmed direct runtime gate in the traced bridge/startup flow.
- Actual Runtime Semantics:
  - Field is required and validated.
  - No traced consumer was found in StrategyRuntime, shadow_telemetry ingress, or command mapper that aborts runtime behavior purely because this flag is false.
  - Actual activation authority is dominated by registry assignment plus llm_orchestration mode/policy.
- Status: DECLARED / NO DIRECT CONSUMER FOUND

### strategies.llm_microstructure.type
- Type: string
- Logic Owner: LLMMicrostructureStrategyConfig
- Runtime Role: descriptive strategy type marker.
- Actual Runtime Semantics:
  - Current value is `external_intent`.
  - No traced branch logic was found using the value as a discriminator after validation.
- Status: METADATA ONLY

### strategies.llm_microstructure.description
- Type: string
- Logic Owner: LLMMicrostructureStrategyConfig
- Runtime Role: documentation metadata.
- Actual Runtime Semantics:
  - No traced runtime consumer beyond typed loading.
- Status: METADATA ONLY

### strategies.llm_microstructure.timeframe_sec
- Type: int
- Logic Owner: LLMMicrostructureStrategyConfig
- Runtime Role: nominal strategy timeframe declaration.
- Actual Runtime Semantics:
  - Typed and validated in the profile.
  - No traced bridge consumer was found that propagates this field into emitted LLM strategy signals.
  - The command mapper currently emits `tf_sec=300` hardcoded in EVT:STRATEGY_SIGNAL_PRODUCED.
  - Strategy gateway TTL logic therefore operates on the emitted signal `tf_sec`, not on the profile value.
- Status: PARTIAL / DRIFTED

---

## 3. Registry and load contract

### strategies_registry.assignments -> llm_microstructure
- Type: registry activation contract
- Logic Owner: ConfigLoader + AuroraConfig validator + StrategyRuntime
- Runtime Role: determines whether the profile is loaded and whether the strategy is allowlisted for specific symbols.
- Actual Runtime Semantics:
  - Current live registry assignment is:
    - `1000PEPEUSDT -> [llm_microstructure]`
  - ConfigLoader loads strategies/llm_microstructure.yaml only when that assignment exists.
  - StrategyRuntime starts the plugin only when `llm_microstructure` appears in assignments.
- Status: ACTIVE

### llm_orchestration contract validation
- Type: cross-config fail-closed contract
- Logic Owner: AuroraConfig model validator
- Runtime Role: prevents partially configured LLM mode.
- Actual Runtime Semantics:
  - If `trading.llm_orchestration.mode == baseline`, no extra LLM contract enforcement runs.
  - If mode is not `baseline` and `llm_microstructure` is assigned anywhere:
    - `trading.llm_orchestration.symbols_llm` must be non-empty
    - `strategies.llm_microstructure` profile must exist
    - every symbol in `symbols_llm` must be assigned `llm_microstructure` in registry
  - Tests explicitly cover missing profile and unassigned symbol failures.
- Status: ACTIVE

---

## 4. Plugin startup reality

### LlmMicrostructurePlugin
- Type: allowlist sentinel plugin
- Logic Owner: apps/reference/domains/strategies/plugins/llm_microstructure.py
- Runtime Role: satisfies StrategyRuntime plugin registration for an external-intent strategy.
- Actual Runtime Semantics:
  - `create_handler()` returns `_LlmMicrostructureSentinelHandler`.
  - The sentinel handler only logs on `register()`.
  - No FSM listeners are registered here.
- Constraints / Invariants:
  - This is not a stateful strategy engine like Aurora, Mean Reversion, or MD-AMR.
- Status: ACTIVE

### StrategyRuntime.start()
- Type: plugin bootstrapper
- Logic Owner: apps/reference/domains/strategies/registry.py
- Runtime Role: starts one handler per assigned strategy ID.
- Actual Runtime Semantics:
  - Because `llm_microstructure` is assigned in registry, StrategyRuntime will start its plugin.
  - Startup success here means only that the sentinel handler registered, not that strategy logic is self-contained in-process.
- Status: ACTIVE

---

## 5. Shadow ingress and command mapping

### LLMIntentIngressBridge
- Type: IPC ingress bridge
- Logic Owner: apps/reference/domains/shadow_telemetry/main_bridge.py
- Runtime Role: receives validated LLM commands from shadow telemetry and emits main-process events.
- Actual Runtime Semantics:
  - Enabled only when shadow_telemetry domain, API, and write ingress are enabled.
  - Validates payload through `CmdLlmIntentSubmitV1`.
  - Emits `EVT:LLM_INTENT_REJECTED_V1` on schema or policy rejection.
  - Emits `EVT:LLM_INTENT_ACCEPTED_V1` then `CMD:LLM_INTENT_SUBMIT_V1` on acceptance.
- Status: ACTIVE

### register_llm_command_mapper()
- Type: bridge-to-strategy mapper
- Logic Owner: apps/reference/domains/shadow_telemetry/main_bridge.py
- Runtime Role: maps `CMD:LLM_INTENT_SUBMIT_V1` to `EVT:STRATEGY_SIGNAL_PRODUCED`.
- Actual Runtime Semantics:
  - Emits a synthetic strategy signal with:
    - `strategy_id = llm_microstructure`
    - `intent_kind = ENTRY`
    - `score = 1.0`
    - `price_ctx.entry_price = cmd.order.limit_price`
    - `price_ctx.stop_price = cmd.brackets.sl_price`
    - `price_ctx.target_price = cmd.brackets.tp_price`
    - `order.type = LIMIT`
    - `order.time_in_force = cmd.order.time_in_force`
    - `order.qty = cmd.order.qty`
    - `llm_meta.*`
  - The mapper currently hardcodes `tf_sec = 300`.
- Constraints / Invariants:
  - The emitted strategy signal is bridge-synthesized, not produced by a handler-local trading model.
- Status: ACTIVE

---

## 6. Global LLM orchestration policy

### trading.llm_orchestration
- Type: global orchestration config
- Logic Owner: TradingConfig + shadow_telemetry API/main bridge
- Runtime Role: top-level gatekeeper for whether external LLM intents may be admitted.
- Actual Runtime Semantics:
  - Key fields:
    - `mode`: `baseline | hybrid_advisory | llm_primary`
    - `llm_role`
    - `require_telemetry`
    - `symbols_llm`
    - `allowlist_symbols`
    - `intent_policy.*`
  - If mode is `baseline`, ingress bridge rejects with `LLM_MODE_DISABLED`.
  - If `symbols_llm` is set and symbol is absent, bridge rejects with `SYMBOL_NOT_OWNED_BY_LLM`.
  - If `allowlist_symbols` is set and symbol is absent, bridge rejects with `SYMBOL_NOT_ALLOWED`.
- Status: ACTIVE

### trading.llm_orchestration.intent_policy
- Type: shadow ingress policy
- Logic Owner: shadow_telemetry main API
- Runtime Role: validates external request shape and exposure bounds before the main-process bridge accepts the command.
- Actual Runtime Semantics:
  - Enforces policy such as:
    - limit-only requests
    - allowed TIF values
    - TP/SL required
    - telemetry snapshot requirement if configured
    - max price deviation from telemetry reference price
    - quantity / notional cap
  - Policy can reject or clamp effective quantity before IPC submission.
- Constraints / Invariants:
  - This policy is not stored in strategies/llm_microstructure.yaml.
  - Ownership is split: profile governs downstream execution policy and safety-gates, while ingress policy governs upstream admission.
- Status: ACTIVE

---

## 7. Downstream execution and safety ownership

### strategies.llm_microstructure.execution
- Type: StrategyExecutionConfig
- Logic Owner: strategy profile + IntentBuilder
- Runtime Role: final downstream order-policy SSOT for trade-intent emission.
- Actual Runtime Semantics:
  - Current profile values:
    - `entry_order_type = LIMIT`
    - `entry_tif = GTC`
    - `exit_order_type = MARKET`
    - `exit_tif = null`
    - `gtx_retry_max = 0`
    - `gtx_retry_offset_bps = 2.0`
    - `gtx_fallback_to_market = false`
  - IntentBuilder resolves `entry_order_type` and `entry_tif` from `config.strategies.llm_microstructure.execution`, not from the external request directly.
  - Missing/unsupported order policy fail-closes in IntentBuilder.
- Constraints / Invariants:
  - External request `order.time_in_force` is filtered upstream, but final trade intent order policy is still re-resolved from the strategy profile.
- Status: ACTIVE

### strategies.llm_microstructure.safety_gates.enabled
- Type: bool
- Logic Owner: strategy profile + safety_gates.py + DecisionMaking
- Runtime Role: decides whether pre-trade safety gates apply to this strategy.
- Actual Runtime Semantics:
  - `_resolve_safety_gates_flag()` reads the strategy config by strategy_id.
  - Missing safety-gates config is fail-closed with `CONFIG_SAFETY_GATES_MISSING`.
  - Current profile enables safety gates.
- Status: ACTIVE

---

## 8. Current behavioral snapshot

Current runtime chain for LLM microstructure is:

1. Registry assignment declares symbol ownership for `llm_microstructure`.
2. ConfigLoader loads the profile into `config.strategies.llm_microstructure`.
3. StrategyRuntime starts a sentinel plugin only.
4. Shadow telemetry API validates the external request against `trading.llm_orchestration.intent_policy`.
5. LLMIntentIngressBridge accepts or rejects the command.
6. Command mapper synthesizes `EVT:STRATEGY_SIGNAL_PRODUCED` with `strategy_id=llm_microstructure`.
7. Strategy gateway applies flip, QoS, sizing, TTL, and warmup checks.
8. DecisionMaking applies strategy safety gates and IntentBuilder resolves final order policy from the strategy profile.

---

## 9. Legacy and drift ledger

### llm_microstructure as normal in-process strategy handler
- Type: stale assumption
- Actual Runtime Semantics:
  - Plugin is sentinel-only; actual strategy behavior is bridge-driven.
- Status: LEGACY

### llm_microstructure.timeframe_sec as emitted signal timeframe
- Type: stale assumption
- Actual Runtime Semantics:
  - Bridge mapper emits `tf_sec=300` hardcoded, while the profile says `60`.
- Status: DRIFTED

### llm_microstructure.enabled as hard runtime switch
- Type: unsupported assumption
- Actual Runtime Semantics:
  - No traced consumer was found that blocks bridge startup or signal mapping solely from this flag.
- Status: DECLARED / NO DIRECT CONSUMER FOUND

### profile-only ownership of LLM behavior
- Type: stale assumption
- Actual Runtime Semantics:
  - Runtime ownership is split between the strategy profile and `trading.llm_orchestration` global policy.
- Status: PARTIAL

---

## 10. Final verdict

The live contract for LLM Microstructure is not “one strategy YAML and one handler”. It is a split contract across:

1. registry assignment in strategies.yaml,
2. the typed strategy profile in strategies/llm_microstructure.yaml,
3. global LLM orchestration policy in trading.yaml,
4. shadow telemetry ingress and command mapping,
5. downstream strategy-gateway, safety-gates, and intent-builder enforcement.

The most important correction is architectural: `llm_microstructure` is currently an external-intent bridge strategy with a sentinel plugin, not a self-contained in-process strategy engine. The second important correction is semantic: the profile timeframe and the emitted signal timeframe currently drift, with the bridge path hardcoding `tf_sec=300` despite `timeframe_sec=60` in the profile.
