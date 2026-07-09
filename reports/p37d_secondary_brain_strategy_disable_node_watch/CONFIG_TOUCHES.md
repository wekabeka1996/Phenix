# CONFIG_TOUCHES.md
# P37D — Config Surfaces and Code Touch Points for agent_arena_testnet Mode

## Scope
Static discovery only. No config was mutated. These are the exact config keys and code surfaces
that a future implementation must touch to activate `agent_arena_testnet` mode.

---

## 1. SSOT Config Keys (YAML / Pydantic)

### 1.1 Strategies — All Internal Strategies Disabled

**File context**: YAML config loaded by `apps/reference/config_models.py` → `AuroraConfig.strategies`

```yaml
strategies:
  aurora:
    enabled: false        # Killswitch → _DisabledAuroraHandlerWrapper returned
    mode: disabled        # authority.py L33: resolve_strategy_mode → "disabled"
    shadow_mode_enabled: false  # aurora.py L394: scoring shadow comparison disabled
  mean_reversion:
    enabled: false
    mode: disabled
  alpha_mr_s01:
    enabled: false
    mode: disabled
  alpha_ta_ensemble:
    enabled: false
    mode: disabled
  md_amr:
    enabled: false
    mode: disabled
```

### 1.2 Strategies Registry — Empty Assignments

**File context**: `AuroraConfig.strategies_registry.assignments`

```yaml
strategies_registry:
  assignments: {}
```

This is the fail-closed surface. `StrategyRuntime.start()` in `strategies/registry.py` L198 returns `{}`.

### 1.3 Decision Making — Strictest Operational Mode

**File context**: `config/domains/decision_making.py` L1233

```yaml
domains:
  decision_making:
    operational_mode: paranoid
```

`OperationalMode.PARANOID` = `"paranoid"` (enums.py L7). This applies the strictest
memory shield multipliers (default 1.0 not inflated by CURIOUS relaxation).

### 1.4 AlphaSearch — Shadow Mode Enforced

**File context**: `bootstrap/domain_builder.py` L154

```python
# domain_builder.py — already hardcoded shadow_mode=True
AlphaSearchPlugin(shadow_mode=True, ...)
```

This is already enforced in the bootstrap. No YAML change needed for the current codebase;
verify it does not get changed when agent_arena_testnet boots.

### 1.5 Execution Adapter — Testnet Only, No Live Execution

**File context**: `agent_bridge/execution_readiness.py` L98-101

Runtime flags that must be verified (not YAML, but runtime state):

```
runtime.shadow_mode = True
runtime.is_live_execution = False
runtime.no_order_observation_mode = True  (when agent observes only)
runtime.adapter = <testnet_binance_adapter | None>
```

---

## 2. Code Touch Points for Future Implementation

| File | Line(s) | What to verify / touch |
|------|---------|------------------------|
| `strategies/plugins/aurora_builtin.py` | L204, L212 | `aurora_cfg.enabled` check: must be `False` |
| `strategies/registry.py` | L198-248 | `StrategyRuntime.start()`: `assignments` must be `{}` or empty |
| `strategies/authority.py` | L32-35 | `resolve_strategy_mode`: all strategies default to `"disabled"` |
| `strategies/runtimes/*/handler.py` | vary | Each handler checks `.enabled` and `.mode` at `register()` |
| `config/shared/enums.py` | L6-8 | `OperationalMode`: `PARANOID` = `"paranoid"` |
| `config/domains/decision_making.py` | L1233 | `operational_mode` field; must be `paranoid` |
| `config/strategies/aurora.py` | L394 | `shadow_mode_enabled` field |
| `bootstrap/domain_builder.py` | L154 | AlphaSearch `shadow_mode=True` |
| `agent_bridge/execution_readiness.py` | L98-102 | `no_order_observation_mode` flag verification |

---

## 3. No-Code-Change Path

If all strategies are disabled via YAML SSOT and `strategies_registry.assignments: {}`,
**no code changes are required**. The existing fail-closed infrastructure in:
- `aurora_builtin.py` (`_DisabledAuroraHandlerWrapper`)
- `registry.py` (`start()` returns `{}` on empty assignments)
- `authority.py` (`AUTHORITY_MODE_DISABLED` blocker)

...ensures zero autonomous decision emissions without any new code.

---

## 4. Optional Additive Profile (If Implemented)

A minimal additive profile YAML file could be added at:
```
apps/reference/config/profiles/agent_arena_testnet.yaml
```

This profile would be loaded by the existing config resolver on top of the base config,
without modifying any existing YAML files. **This would be a purely additive change.**

No fallbacks. No hidden constants. SSOT: YAML + Pydantic only.

---

## 5. UNPROVEN Areas (Static Discovery Only)

- Whether a `profiles/` directory or layered config loading mechanism already exists in the codebase for runtime profile selection.
- Whether `md_amr` handler checks `enabled` at register time (assumed from pattern; not inspected directly).
- Whether `llm_microstructure` strategy (found in plugins listing) has an authority surface — this plugin was discovered but not inspected.
- Whether `neocortex` domain (found at `domains/neocortex/config_models.py`) contributes to autonomous decision signals — not inspected.
