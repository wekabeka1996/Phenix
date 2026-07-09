# VALIDATION.md
# P37D — Validation Summary

## Validation Type
VALIDATION_STATIC_DISCOVERY_ONLY

No code or config was changed. All findings are from static file inspection.

---

## Commands Run

```powershell
# 1. Git startup sequence
pwd
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git fetch --all --prune
git switch agent-hub-integrated-2026-07-09
git pull --ff-only

# 2. Branch creation
git switch -c p37d-secondary-brain-strategy-disable-node-watch-20260709

# 3. Domain discovery
cmd /c "dir /s /b apps\reference\domains\decision_making"
cmd /c "dir /s /b apps\reference\domains\alpha_search"
cmd /c "dir /s /b apps\reference\domains"

# 4. File content inspections (view_file)
apps/reference/domains/strategies/authority.py
apps/reference/domains/strategies/registry.py
apps/reference/domains/alpha_search/shadow/authority_guard.py
apps/reference/domains/strategies/plugins/aurora_builtin.py
apps/reference/domains/strategies/runtimes/aurora/handler.py  (lines 1-800)
apps/reference/domains/decision_making/primitives/operational_mode.py
apps/reference/config/shared/enums.py
apps/reference/domains/agent_bridge/execution_readiness.py
apps/reference/config/strategies/aurora.py  (lines 385-406)
apps/reference/config/domains/decision_making.py  (lines 1225-1240)

# 5. Pattern searches (PowerShell / Python)
python -c "... search for: no_order_observation_mode, OperationalMode, agent_arena, shadow_book, DISABLE|disable_strategy"
python -c "... search for: OperationalMode, event_bus, recorder, reconcili, order_lifecycle, position_sync, shadow_mode"
Select-String pattern searches for: OperationalMode, class.*Mode, CURIOUS, shadow, TRADE_INTENT, emit, _is_enabled
```

---

## Files Inspected

| File | Lines | Purpose |
|------|-------|---------|
| `strategies/authority.py` | 180 | Strategy mode resolution, blockers |
| `strategies/registry.py` | 312 | StrategyRuntime.start(), plugin registration |
| `strategies/plugins/aurora_builtin.py` | 242 | Aurora killswitch: `_DisabledAuroraHandlerWrapper` |
| `strategies/runtimes/aurora/handler.py` | 800+ | AuroraHandler, `_is_enabled`, Gate 0 disable |
| `alpha_search/shadow/authority_guard.py` | 135 | Shadow boundary enforcement |
| `decision_making/primitives/operational_mode.py` | 52 | `ModeManager`, `OperationalMode` CURIOUS/PARANOID |
| `config/shared/enums.py` | 30 | `OperationalMode` enum: PARANOID, CURIOUS |
| `agent_bridge/execution_readiness.py` | 241 | `no_order_observation_mode`, `shadow_mode`, `is_live_execution` |
| `config/strategies/aurora.py` (L385-406) | — | `shadow_mode_enabled` field |
| `config/domains/decision_making.py` (L1225-1240) | — | `operational_mode` field |

---

## Key Evidence Confirmed

1. **Aurora killswitch**: `aurora_builtin.py` L204-222: `is_enabled = getattr(aurora_cfg, "enabled", True)`. When `False` and no assignments, `_DisabledAuroraHandlerWrapper()` returned — no FSM listeners.
2. **Mode resolution**: `authority.py` L33: `getattr(strategy_cfg, "mode", "disabled")` — default is `"disabled"` when not set.
3. **Registry fail-closed**: `registry.py` L220-248: Empty `assignments` dict returns `{}` from `start()` without registering any handlers.
4. **no_order_observation_mode**: `execution_readiness.py` L101: `runtime.no_order_observation_mode` is a first-class safe isolation flag.
5. **AlphaSearch shadow**: `domain_builder.py` L154: Already passes `shadow_mode=True` — shadow_book only, no real orders.
6. **OperationalMode**: `enums.py` L6-8: Two values: `PARANOID` = strict; `CURIOUS` = relaxed shields.

---

## No Live/Mainnet Confirmation

- No exchange adapter credentials were read, called, or accessed.
- No trading runtime was started.
- No FSM was booted.
- No YAML/config files were modified.
- All findings are read-only static file inspection.
- No live or mainnet operations occurred.

---

## Unproven Areas

- `llm_microstructure` plugin authority surface — found in plugin listing but not inspected.
- `neocortex` domain autonomous decision role — discovered but not inspected.
- Whether `md_amr` handler checks `enabled` at `register()` (assumed by pattern; not directly confirmed).
- Whether a layered profiles loader exists for `agent_arena_testnet` YAML profile activation.
- Whether `strategies_registry.assignments: {}` is a valid SSOT form (empty dict) or requires omission — assumed valid from registry.py L220 check.
