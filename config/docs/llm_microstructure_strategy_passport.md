# LLM MICROSTRUCTURE STRATEGY PASSPORT
## Aurora / Phenix — external-intent profile, shadow ingress policy, and direct external-open runtime

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/llm_microstructure_strategy_passport.md`
> - **Audit date:** 2026-04-04
> - **Audit mode:** Code-driven sync
> - **Major drifts found:** Previous passport text still described the live external LLM route as a normal strategy-signal / DecisionMaking / safety-gates chain. Current code routes accepted LLM commands through `CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1 -> execution_position IntentRouter`, while `llm_microstructure.safety_gates.enabled` remains disabled in the profile and is not the active owner for the current live external path.
> - **Overall confidence:** HIGH
> - **Governance SSOT:** bounded verdicts for already-closed surfaces live in `reports/GOVERNANCE_BOUNDED_VERDICTS_AND_NEXT_PACKAGES_2026-04-04.md`; this passport should not reopen them.

---

## 1. Scope

This passport covers exactly one strategy profile: config/aurora/strategies/llm_microstructure.yaml.

It traces:

1. Typed profile contract in `config.strategies.llm_microstructure`.
2. Registry assignment and load preconditions.
3. Plugin startup behavior.
4. Shadow telemetry ingress and external-open command mapping.
5. Global LLM orchestration policy in trading config.
6. Current live execution owner chain and non-owner legacy surfaces.

Authoritative sources traced for this passport:

- YAML: config/aurora/strategies/llm_microstructure.yaml, config/aurora/strategies.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/domains/strategies/plugins/llm_microstructure.py, apps/reference/domains/strategies/registry.py, apps/reference/domains/shadow_telemetry/main.py, apps/reference/domains/shadow_telemetry/main_bridge.py, apps/reference/domains/execution_position/intent_router.py, apps/reference/domains/execution_position/fsm.py.
- Wiring: apps/reference/main.py.
- Tests: tests/config/test_llm_strategy_contract_fail_closed.py, tests/domains/shadow_telemetry/test_main_bridge.py, tests/unit/llm/test_llm_command_mapper_emits_strategy_signal.py, tests/domains/execution_position/test_external_open_request.py.

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
    - `safety_gates.enabled: false`
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
  - No traced live consumer was found in the current external-open route.
  - The current command mapper does not emit `EVT:STRATEGY_SIGNAL_PRODUCED`; it emits `CMD:EXTERNAL_OPEN_REQUEST_V1`.
- Status: DECLARED / NO LIVE CONSUMER CONFIRMED

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
- Type: bridge-to-execution mapper
- Logic Owner: apps/reference/domains/shadow_telemetry/main_bridge.py
- Runtime Role: maps `CMD:LLM_INTENT_SUBMIT_V1` to `CMD:EXTERNAL_OPEN_REQUEST_V1`.
- Actual Runtime Semantics:
  - Emits a flat external-open payload with:
    - `rid = intent_id`
    - `symbol`, `side`, `qty`
    - `order_type`, `price`, `tif`
    - `stop_price`, `target_price`
    - `snapshot_ref`, `why_short`
    - `source = external_llm`
- Constraints / Invariants:
  - The mapper does not route through `EVT:STRATEGY_SIGNAL_PRODUCED` on the current live path.
- Status: ACTIVE

### IntentRouter.on_external_open_request()
- Type: execution intake owner
- Logic Owner: apps/reference/domains/execution_position/intent_router.py
- Runtime Role: validates `CMD:EXTERNAL_OPEN_REQUEST_V1`, resolves LIMIT-order lifetime, builds `CMD:OPEN`, and delegates to execution_position.
- Actual Runtime Semantics:
  - Enforces `source=external_llm`.
  - Enforces `order_type=LIMIT`.
  - Enforces explicit valid TIF.
  - Resolves `valid_for_ms` from the request, else from `strategies.llm_microstructure.pending_entry_ttl_ms`.
  - Builds `CMD:OPEN` directly with `strategy=llm_microstructure` and execution metadata.
- Constraints / Invariants:
  - Current live external route enters execution_position here, not through StrategyGateway / DecisionMaking.
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

## 7. Current live execution and safety ownership

### strategies.llm_microstructure.execution
- Type: StrategyExecutionConfig
- Logic Owner: declared strategy profile surface; not the active owner for the current live external-open route.
- Runtime Role: stores configured execution defaults for the strategy profile, but does not own the live external order-type / TIF path.
- Actual Runtime Semantics:
  - Current profile values:
    - `entry_order_type = LIMIT`
    - `entry_tif = GTC`
    - `exit_order_type = MARKET`
    - `exit_tif = null`
    - `gtx_retry_max = 0`
    - `gtx_retry_offset_bps = 2.0`
    - `emit_market_fallback_marker_on_retry_exhaustion = false`
  - The current live external route does not call StrategyGateway or IntentBuilder before execution_position.
  - `IntentRouter.on_external_open_request()` requires LIMIT and explicit TIF from the bridge payload.
  - The only proven llm profile field consumed in the current live external route is `pending_entry_ttl_ms` as the fallback owner for `valid_for_ms`.
- Constraints / Invariants:
  - Do not treat `execution.entry_order_type`, `execution.entry_tif`, or `execution.emit_market_fallback_marker_on_retry_exhaustion` as the live owner of the current external LLM path.
- Status: DECLARED / NOT ACTIVE OWNER FOR LIVE EXTERNAL PATH

### strategies.llm_microstructure.safety_gates.enabled
- Type: bool
- Logic Owner: strategy profile + generic DecisionMaking safety-gates code for synthetic strategy-signal paths.
- Runtime Role: optional pre-trade gate flag for DecisionMaking-owned strategy signals, not for the current live external-open route.
- Actual Runtime Semantics:
  - `_resolve_safety_gates_flag()` reads the strategy config by strategy_id.
  - Missing safety-gates config is fail-closed with `CONFIG_SAFETY_GATES_MISSING`.
  - Current profile disables safety gates.
  - Generic consumers still exist in `decision_making/safety_gates.py`, but the current live external route bypasses DecisionMaking entirely.
- Status: BYPASSED FOR CURRENT LIVE EXTERNAL PATH

---

## 8. Current behavioral snapshot

Current runtime chain for LLM microstructure is:

1. Registry assignment declares symbol ownership for `llm_microstructure`.
2. ConfigLoader loads the profile into `config.strategies.llm_microstructure`.
3. StrategyRuntime starts a sentinel plugin only.
4. Shadow telemetry API validates the external request against `trading.llm_orchestration.intent_policy`.
5. LLMIntentIngressBridge accepts or rejects the command.
6. Accepted requests are emitted as `CMD:LLM_INTENT_SUBMIT_V1`.
7. Command mapper converts them into `CMD:EXTERNAL_OPEN_REQUEST_V1`.
8. execution_position IntentRouter validates the external-open contract, resolves `valid_for_ms`, and builds `CMD:OPEN` directly.
9. execution_position continues through its normal open-execution chain.

The current live external route does not pass through `EVT:STRATEGY_SIGNAL_PRODUCED`, StrategyGateway, DecisionMaking safety gates, or IntentBuilder before execution_position intake.

---

## 9. Legacy and drift ledger

### llm_microstructure as normal in-process strategy handler
- Type: stale assumption
- Actual Runtime Semantics:
  - Plugin is sentinel-only; actual strategy behavior is bridge-driven.
- Status: LEGACY

### register_llm_command_mapper as strategy-signal producer
- Type: stale assumption
- Actual Runtime Semantics:
  - Current mapper emits `CMD:EXTERNAL_OPEN_REQUEST_V1`, not `EVT:STRATEGY_SIGNAL_PRODUCED`.
- Status: LEGACY

### llm_microstructure.safety_gates.enabled as live external control
- Type: stale assumption
- Actual Runtime Semantics:
  - Generic DecisionMaking safety-gates consumers exist, but the current live external path bypasses that chain.
- Status: LEGACY

### llm_microstructure.enabled as hard runtime switch
- Type: unsupported assumption
- Actual Runtime Semantics:
  - No traced consumer was found that blocks bridge startup or signal mapping solely from this flag.
- Status: DECLARED / NO DIRECT CONSUMER FOUND

### profile-only ownership of LLM behavior
- Type: stale assumption
- Actual Runtime Semantics:
  - Runtime ownership is dominated by `trading.llm_orchestration`, shadow telemetry ingress, `CMD:LLM_INTENT_SUBMIT_V1`, `CMD:EXTERNAL_OPEN_REQUEST_V1`, and execution_position IntentRouter.
- Status: LEGACY

---

## 10. Final verdict

The live contract for LLM Microstructure is not “one strategy YAML and one handler”, and it is not the normal in-process strategy-signal plus safety-gates path. It is a split contract across:

1. registry assignment in strategies.yaml,
2. the typed strategy profile in strategies/llm_microstructure.yaml,
3. global LLM orchestration policy in trading.yaml,
4. shadow telemetry ingress,
5. `CMD:LLM_INTENT_SUBMIT_V1 -> CMD:EXTERNAL_OPEN_REQUEST_V1` mapping,
6. execution_position external-open intake and CMD:OPEN delegation.

The most important correction is architectural: `llm_microstructure` is currently an external-intent bridge strategy with a sentinel plugin, not a self-contained in-process strategy engine. The most important operator-facing correction is ownership: the active live path is `trading.llm_orchestration` plus shadow telemetry ingress plus `CMD:EXTERNAL_OPEN_REQUEST_V1` intake, not the normal `EVT:STRATEGY_SIGNAL_PRODUCED -> StrategyGateway -> DecisionMaking safety-gates -> IntentBuilder` chain.
