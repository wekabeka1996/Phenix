# STRATEGIES PASSPORT
## Aurora / Phenix — strategy registry, profile loading, and runtime activation SSOT

> AUDIT SUMMARY
> - Document path: config/docs/strategies_passport.md
> - Audit date: 2026-03-13
> - Audit mode: code-driven sync
> - Total claims checked: 24
> - Confirmed: 11
> - Corrected: 9
> - Removed as stale: 4
> - Added as missing: 8
> - Major drifts found:
>   1. Runtime activation is assignment-first through `strategies_registry.assignments`; old generic wording around profile ownership was too loose.
>   2. Strategy profile loading is registry-driven: only assigned strategy IDs cause `config/aurora/strategies/<id>.yaml` to be loaded.
>   3. `llm_microstructure` is allowlisted and assigned, but its plugin is a sentinel handler; actual behavior is bridge-driven via shadow telemetry.
>   4. `strategies_registry.arbitration.logging.log_level` is typed but no consumer was found in runtime arbitration logic.
>   5. `aurora.enabled` is not the hard activation SSOT; Aurora runtime checks registry first and only falls back to per-asset enablement when registry lacks the symbol.
>   6. Mean Reversion and MD-AMR handlers enforce stricter assignment/config consistency than the old passport described.
> - Overall confidence: HIGH

---

## 1. Scope

This passport covers exactly one configuration surface: strategy registry and strategy profile activation.

It traces:

1. Registry loading from config/aurora/strategies.yaml.
2. Registry validation in Pydantic.
3. Registry-driven profile loading from config/aurora/strategies/*.yaml.
4. Plugin allowlist and handler startup.
5. Assignment SSOT and multi-strategy arbitration.
6. Strategy profile contract shapes for `aurora`, `mean_reversion`, `md_amr`, and `llm_microstructure`.
7. Order-policy and safety-gate ownership at the strategy profile level.

Authoritative sources traced for this passport:

- YAML: config/aurora/strategies.yaml, config/aurora/strategies/aurora.yaml, config/aurora/strategies/mean_reversion.yaml, config/aurora/strategies/md_amr.yaml, config/aurora/strategies/llm_microstructure.yaml.
- Pydantic: apps/reference/config_models.py.
- Runtime: apps/reference/config_loader.py, apps/reference/main.py, apps/reference/domains/strategies/registry.py, apps/reference/domains/decision_making/config_resolver.py, apps/reference/domains/decision_making/decision_making.py, apps/reference/domains/decision_making/aurora_handler.py, apps/reference/domains/decision_making/mean_reversion_handler.py, apps/reference/domains/decision_making/md_amr_handler.py.
- Plugins: apps/reference/domains/strategies/plugins/*.py.

---

## 2. Loader and namespace wiring

### config/aurora/strategies.yaml
- Type: root strategy registry SSOT
- Logic Owner: config_loader + StrategiesRegistryConfig
- Runtime Role: defines active strategy assignments per symbol and the arbitration policy for conflicts.
- Actual Runtime Semantics:
  - Config loader requires this file.
  - Missing or empty strategies.yaml is a hard config error.
  - File is loaded under `config.strategies_registry`.
- Constraints / Invariants:
  - Unknown fields are forbidden by Pydantic.
- Status: ACTIVE

### registry-driven strategy profile loading
- Type: config assembly rule
- Logic Owner: apps/reference/config_loader.py
- Runtime Role: loads only the strategy profile YAMLs that are actually assigned in `strategies_registry.assignments`.
- Actual Runtime Semantics:
  - Loader collects the unique set of assigned `strategy_id` values.
  - For each assigned strategy ID, loader requires the corresponding file:

    `config/aurora/strategies/<strategy_id>.yaml`

  - Missing assigned profile file is a hard startup error.
  - Loaded profile data is attached under:

    `config.strategies.<strategy_id>`

- Constraints / Invariants:
  - Unassigned profiles are not required for startup.
  - The runtime namespace for strategy profiles is `config.strategies`, not `config.strategies_registry`.
- Status: ACTIVE

### strategies namespace
- Type: canonical runtime namespace
- Logic Owner: StrategiesConfig
- Runtime Role: holds typed profiles for `aurora`, `mean_reversion`, `md_amr`, and `llm_microstructure`.
- Actual Runtime Semantics:
  - Current typed namespace supports exactly those four strategy profiles.
- Status: ACTIVE

---

## 3. Registry contract

### strategies_registry.version
- Type: string metadata
- Logic Owner: StrategiesRegistryConfig
- Runtime Role: version marker for the registry contract.
- Actual Runtime Semantics:
  - Typed and validated.
  - No runtime branching consumer was found beyond loading/validation.
- Status: METADATA ONLY

### strategies_registry.assignments
- Type: `Dict[str, List[str]]`
- Logic Owner: StrategiesRegistryConfig + StrategyRuntime + DMConfigResolver
- Runtime Role: hard SSOT for which strategy IDs are allowed to exist on each symbol.
- Actual Runtime Semantics:
  - Current assignments:
    - `ETHUSDT -> [aurora]`
    - `SOLUSDT -> [aurora]`
    - `DOGEUSDT -> [mean_reversion]`
    - `XRPUSDT -> [md_amr]`
    - `BTCUSDT -> [aurora]`
    - `BNBUSDT -> [md_amr]`
    - `1000PEPEUSDT -> [llm_microstructure]`
  - StrategyRuntime starts handlers only for strategy IDs that appear somewhere in assignments.
  - DecisionMaking arbitration fail-closes when a symbol is missing from assignments or when a strategy is not assigned to that symbol.
  - Aurora handler checks assignments first in `_is_symbol_enabled()`.
  - Mean Reversion and MD-AMR handlers derive their enabled symbol set from assignments and then cross-check profile config.
- Constraints / Invariants:
  - Assigned strategy IDs must have allowlisted plugins.
  - Assigned strategy IDs must have corresponding profile YAML files.
- Status: ACTIVE

### assignments as activation SSOT
- Type: activation synthesis
- Logic Owner: StrategyRuntime + DMConfigResolver + strategy handlers
- Runtime Role: determines which strategy handlers boot and which symbols they may act on.
- Actual Runtime Semantics:
  - Assignment is the first and strongest activation layer.
  - Per-strategy `enabled` flags do not replace assignments; they only further constrain already assigned strategies.
  - A strategy not assigned to a symbol is blocked even if its profile and asset config exist.
- Status: ACTIVE

---

## 4. Arbitration

### strategies_registry.arbitration.mode
- Type: literal enum
- Logic Owner: StrategiesArbitrationConfig + DMConfigResolver.check_strategy_arbitration
- Runtime Role: selects the conflict-resolution algorithm for symbols with multiple assigned strategies.
- Actual Runtime Semantics:
  - Typed contract supports only `priority`.
  - Runtime rejects any other mode fail-closed with `ARBITRATION_REJECT:unknown_mode_*`.
  - Current YAML value is `priority`.
- Status: ACTIVE

### strategies_registry.arbitration.window_ms
- Type: integer milliseconds
- Logic Owner: StrategiesArbitrationConfig + DMConfigResolver
- Runtime Role: defines the arbitration window within which competing intents are compared.
- Actual Runtime Semantics:
  - Current YAML value is `1000` ms.
  - Invalid or non-positive values are rejected fail-closed.
  - If a previous intent is still inside the same window, lower-rank strategies can be dropped.
- Status: ACTIVE

### strategies_registry.arbitration.priority
- Type: `Dict[str, int]`
- Logic Owner: StrategiesArbitrationConfig + StrategiesRegistryConfig validator + DMConfigResolver
- Runtime Role: assigns lower-is-higher ranks for `priority` arbitration.
- Actual Runtime Semantics:
  - Current YAML ranks:
    - `aurora: 1`
    - `mean_reversion: 2`
    - `md_amr: 3`
    - `llm_microstructure: 4`
  - Pydantic validates that every hybrid symbol assignment has all required priorities.
  - Runtime still fail-closes if the acting strategy or any competing assigned strategy is missing a rank.
- Status: ACTIVE

### arbitration behavior
- Type: deterministic arbitration synthesis
- Logic Owner: DMConfigResolver.check_strategy_arbitration
- Runtime Role: decides whether an incoming strategy intent may proceed for a symbol.
- Actual Runtime Semantics:
  - If symbol is unregistered: reject.
  - If strategy is not in that symbol’s assignment list: reject.
  - If only one strategy is assigned: allow.
  - If multiple strategies are assigned and mode is `priority`:
    - compare ranks inside `window_ms`
    - lower rank overrides higher rank within the active window
    - equal or worse rank loses the window
  - When `commit=True`, runtime stores the current winner in arbitration buffers.
- Constraints / Invariants:
  - Arbitration is symbol-local.
  - Current runtime does not expose alternate modes like `regime` or `round_robin`.
- Status: ACTIVE

### strategies_registry.arbitration.logging.rejected_why_prefix
- Type: string
- Logic Owner: StrategiesArbitrationLoggingConfig + DMConfigResolver
- Runtime Role: prefix for arbitration rejection reasons.
- Actual Runtime Semantics:
  - Current YAML value is `ARBITRATION_REJECT`.
  - Runtime uses it when lower-priority strategies lose an active arbitration window.
- Status: ACTIVE

### strategies_registry.arbitration.logging.log_level
- Type: string
- Logic Owner: StrategiesArbitrationLoggingConfig
- Runtime Role: none in traced arbitration logic.
- Actual Runtime Semantics:
  - Field is typed and present in YAML.
  - No runtime consumer was found in StrategyRuntime, DMConfigResolver, or DecisionMaking arbitration calls.
- Status: DECLARED BUT NOT USED

---

## 5. Plugin allowlist and startup

### StrategyPluginRegistry
- Type: in-process allowlist
- Logic Owner: apps/reference/domains/strategies/registry.py
- Runtime Role: restricts bootable strategy IDs to explicitly registered plugins.
- Actual Runtime Semantics:
  - Duplicate strategy IDs are rejected.
  - Missing plugin for an assigned strategy ID is a hard config error during startup.
- Status: ACTIVE

### StrategyRuntime.start
- Type: handler bootstrapper
- Logic Owner: apps/reference/domains/strategies/registry.py
- Runtime Role: starts one handler per assigned strategy ID.
- Actual Runtime Semantics:
  - Reads `config.strategies_registry.assignments`.
  - Computes unique assigned strategy IDs.
  - Verifies all assigned strategy IDs have allowlisted plugins.
  - Calls `plugin.create_handler(...).register()` once per assigned strategy ID.
  - Current main composition root registers these plugins:
    - AuroraBuiltinPlugin
    - MeanReversionPlugin
    - MDAMRPlugin
    - LlmMicrostructurePlugin
- Status: ACTIVE

### llm_microstructure plugin
- Type: sentinel plugin
- Logic Owner: apps/reference/domains/strategies/plugins/llm_microstructure.py
- Runtime Role: satisfies StrategyRuntime allowlist/start contract for an externally driven strategy.
- Actual Runtime Semantics:
  - The plugin returns a sentinel handler that only logs on `register()`.
  - No strategy FSM listeners are registered here.
  - Actual intent injection is bridge-driven via the shadow telemetry ingress path.
- Constraints / Invariants:
  - Assigned strategy ID is real for registry purposes.
  - The plugin is not a full autonomous strategy handler like Aurora, MR, or MD-AMR.
- Status: ACTIVE

---

## 6. Strategy profile contracts

### strategies.aurora
- Type: AuroraStrategyConfig
- Logic Owner: aurora profile + Aurora handler/runtime
- Runtime Role: bar-driven multi-signal strategy profile with decision config and per-symbol overrides.
- Actual Runtime Semantics:
  - Current profile exists and is loaded because `aurora` is assigned.
  - Global activation in runtime is assignment-first.
  - `aurora.enabled` is typed but not the hard startup activation source.
  - Aurora handler checks registry first and only falls back to `assets.<SYM>.enabled` when registry has no explicit assignment for that symbol.
- Status: ACTIVE

### strategies.mean_reversion
- Type: MeanReversion1mStrategyConfig
- Logic Owner: mean_reversion profile + MeanReversionHandler
- Runtime Role: bar-based Bollinger/%B strategy profile.
- Actual Runtime Semantics:
  - Current profile exists and is loaded because `mean_reversion` is assigned.
  - Handler derives assigned symbols from registry.
  - If MR is assigned but profile is missing: fail-closed error.
  - If MR is assigned but `mean_reversion.enabled=false`: fail-closed error.
  - If assigned symbols are missing from `mean_reversion.assets` or have `enabled=false`: fail-closed error.
- Status: ACTIVE

### strategies.md_amr
- Type: MDAMRStrategyConfig
- Logic Owner: md_amr profile + MDAMRHandler
- Runtime Role: multi-dimensional asymmetric mean reversion strategy profile.
- Actual Runtime Semantics:
  - Current profile exists and is loaded because `md_amr` is assigned.
  - Handler derives assigned symbols from registry.
  - If MD-AMR is assigned but profile is missing: fail-closed error.
  - If assigned and `md_amr.enabled=false`: fail-closed error.
  - Assigned symbols are checked for live contract completeness, including asset existence, `enabled=true`, required `exit`, and required `allowed_regimes`.
- Status: ACTIVE

### strategies.llm_microstructure
- Type: LLMMicrostructureStrategyConfig
- Logic Owner: llm_microstructure profile + sentinel plugin + shadow telemetry bridge
- Runtime Role: contract profile for bridge-driven external intents.
- Actual Runtime Semantics:
  - Current profile exists and is loaded because `llm_microstructure` is assigned.
  - Boot path is allowlisted through StrategyRuntime, but the actual behavior is not implemented as a normal in-process trading handler.
- Status: ACTIVE

---

## 7. Order policy ownership

### strategies.<id>.execution
- Type: StrategyExecutionConfig
- Logic Owner: strategy profile + intent_builder.py
- Runtime Role: defines entry/exit order policy for emitted trade intents.
- Actual Runtime Semantics:
  - Typed fields include:
    - `entry_order_type`
    - `entry_tif`
    - `exit_order_type`
    - `exit_tif`
    - GTX retry policy fields
  - IntentBuilder reads `entry_order_type` and `entry_tif` from the strategy execution config.
  - Missing `entry_order_type` is fail-closed.
  - Unsupported order type is fail-closed.
  - `LIMIT` requires explicit TIF.
  - `MARKET` requires `tif = null`.
- Current profile values:
  - `aurora`: `LIMIT + GTX`
  - `mean_reversion`: `MARKET + null`
  - `md_amr`: `LIMIT + GTX` for entries, `MARKET + null` for exits
  - `llm_microstructure`: `LIMIT + GTC` for entries, `MARKET + null` for exits
- Status: ACTIVE

---

## 8. Safety gates ownership

### strategies.<id>.safety_gates
- Type: SafetyGatesConfig
- Logic Owner: strategy profile + DecisionMaking._propose_trade_intent + apply_safety_gates
- Runtime Role: controls whether strategy-level directional sanity and price-motion safety checks are applied before intent emission.
- Actual Runtime Semantics:
  - DecisionMaking applies safety gates before building/emitting the trade intent.
  - Missing/invalid safety-gates config produces a fail-closed reject with `CONFIG_SAFETY_GATES_MISSING`.
  - A deny outcome from safety gates emits a blocked/rejected path.
- Current profile values:
  - `aurora.safety_gates.enabled: true`
  - `mean_reversion.safety_gates.enabled: false`
  - `md_amr.safety_gates.enabled: true`
  - `llm_microstructure.safety_gates.enabled: true`
- Status: ACTIVE

---

## 9. Mode overrides and per-strategy cooldowns

### strategies.aurora.decision.testnet / production overrides
- Type: DecisionModeOverrideConfig
- Logic Owner: config_loader._resolve_mode_overrides
- Runtime Role: copies mode-specific Aurora decision overrides onto `decision.*` at load time.
- Actual Runtime Semantics:
  - Current loader resolves `decision.<trading_mode>.* -> decision.*`.
  - `signal_threshold` is the currently confirmed typed override field.
  - Original mode blocks remain present for documentation, but effective runtime values are merged into the live decision block.
- Status: ACTIVE

### per-symbol cooldown ownership
- Type: strategy/profile-specific override rule
- Logic Owner: DMConfigResolver.get_symbol_cooldown
- Runtime Role: resolves symbol cooldown for QoS/rate-control.
- Actual Runtime Semantics:
  - Confirmed Aurora chain:

    `strategies.aurora.assets.<SYM>.cooldown_sec -> domains.decision_making.qos.symbol_cooldown_sec -> safe default 3s`

  - Mean Reversion has its own strategy-level cooldown path inside its profile/runtime.
- Status: ACTIVE

---

## 10. Legacy and drift ledger

### strategies_registry.arbitration.logging.log_level
- Type: typed registry field
- Status: DECLARED BUT NOT USED

### aurora.enabled as hard activation switch
- Type: stale assumption
- Actual Runtime Semantics:
  - Aurora activation is assignment-first.
  - `aurora.enabled` is not the primary runtime boot filter.
- Status: PARTIAL

### unassigned strategy profile files
- Type: config-side possibility
- Actual Runtime Semantics:
  - They are not required for startup because profile loading is assignment-driven.
- Status: ACTIVE

### llm_microstructure as full in-process handler
- Type: stale assumption
- Actual Runtime Semantics:
  - Plugin is sentinel-only.
  - Runtime behavior is bridge-driven, not a regular stateful handler loop.
- Status: LEGACY

---

## 11. Final verdict

Current strategy SSOT is centered on one chain:

1. `config/aurora/strategies.yaml` is the hard registry for symbol-to-strategy assignment and arbitration.
2. Assigned strategy IDs drive profile loading from `config/aurora/strategies/<id>.yaml`.
3. Assigned strategy IDs also drive plugin startup via StrategyRuntime.
4. Strategy profiles own execution policy and safety-gate policy.
5. Strategy handlers then apply stricter strategy-specific validity checks on top of assignments.

This passport supersedes the older narrative that treated strategy profiles as loosely wired metadata. In current Aurora/Phenix runtime, assignments, allowlisted plugins, and typed profile presence form a strict fail-closed activation contract.
