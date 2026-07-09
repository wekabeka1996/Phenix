# AUTHORITY_DISABLE_MATRIX.md
# P37D — Brain/Strategy Autonomous Authority Disable Matrix

## Legend
- **DISABLE** — Must be disabled / set to `disabled` mode for agent-arena-testnet profile
- **SHADOW** — May be left in shadow mode (observe-only; no real orders)
- **PRESERVE** — Must remain active (FSM, execution accounting, logging, event bus)
- **UNKNOWN** — Authority surface found; full scope not confirmed from static discovery alone
- **DANGEROUS_TO_TOUCH** — Touching this field has known blast radius; flag for senior review

---

## 1. Autonomous Strategy Decision Authority

| Surface | File | Config Key / Mode Value | Action | Evidence |
|---------|------|------------------------|--------|----------|
| Aurora strategy handler | `strategies/plugins/aurora_builtin.py` | `strategies.aurora.enabled = False` | **DISABLE** | `_DisabledAuroraHandlerWrapper` returned; no FSM listeners registered |
| Aurora strategy mode | `strategies/authority.py` L33 | `strategies.aurora.mode = "disabled"` | **DISABLE** | `resolve_strategy_mode` defaults to `"disabled"` |
| mean_reversion strategy | `strategies/runtimes/mean_reversion/handler.py` L393 | `strategies.mean_reversion.enabled = False` + `mode = "disabled"` | **DISABLE** | Handler exits immediately when disabled |
| alpha_mr_s01 strategy | `strategies/runtimes/alpha_mr_s01/handler.py` L47 | `strategies.alpha_mr_s01.enabled = False` + `mode = "disabled"` | **DISABLE** | Handler logs warning, no listeners registered |
| alpha_ta_ensemble strategy | `strategies/runtimes/alpha_ta_ensemble/handler.py` L48 | `strategies.alpha_ta_ensemble.enabled = False` + `mode = "disabled"` | **DISABLE** | Handler logs warning, no listeners registered |
| md_amr strategy | `strategies/runtimes/md_amr/handler.py` | `strategies.md_amr.enabled = False` + `mode = "disabled"` | **DISABLE** | Pattern identical to alpha_mr_s01 |
| Alpha-search judge (policy_cortex) | `alpha_search/judge/policy_cortex/cortex_evaluator.py` | shadow mode only; do not wire to decision bus | **SHADOW** | Judge produces verdicts; disabling trade-intent downstream is sufficient |
| AlphaSearch scenario_manager | `alpha_search/runtime/scenario_manager.py` | `shadow_mode=True` in `domain_builder.py` L154 | **SHADOW** | `shadow_book` records only; no real orders when shadow_mode=True |
| strategies_registry.assignments | YAML/config | Remove all strategy_id entries from assignments | **DISABLE** | `StrategyRuntime.start()` returns `{}` when `assignments` is empty |
| StrategyRuntime plugin launch | `strategies/registry.py` L198 | Remove assignments OR set all strategies disabled | **DISABLE** | `start()` raises ConfigContractError if financially active strategies are unassigned |

---

## 2. Arbitration / Decision Gate Authority

| Surface | File | Notes | Action |
|---------|------|-------|--------|
| decision_making `arbitration_gate.py` | `decision_making/gates/arbitration_gate.py` | Reads SSOT gates; does not initiate autonomous trades | **PRESERVE** (passive gate) |
| strategy_gateway chain | `decision_making/gateway/strategy_gateway.py` | Routes intent after strategy emits it | **PRESERVE** (pass-through; disable at strategy layer) |
| `trade_intent` emitter | `decision_making/intent/emitter.py` | Emits `TRADE_INTENT_PROPOSED` only when strategy emits signal | **PRESERVE** (no autonomous authority; driven by strategy) |

---

## 3. Shadow / Live / Observation Toggles

| Toggle | File | Config Key | Disable Action |
|--------|------|------------|----------------|
| `shadow_mode_enabled` (Aurora) | `config/strategies/aurora.py` L394 | `strategies.aurora.shadow_mode_enabled = True` | **SHADOW** — Force to True when not fully disabled |
| `shadow_mode` (AlphaSearch plugin) | `bootstrap/domain_builder.py` L154 | `shadow_mode=True` passed at DomainBuilder init | **PRESERVE** — Already enforced in bootstrap |
| `no_order_observation_mode` | `domains/agent_bridge/execution_readiness.py` L101 | `runtime.no_order_observation_mode = True` | **DISABLE execution path** — Safe no-order isolation mode |
| `is_live_execution` | `domains/agent_bridge/execution_readiness.py` L99 | must be `False` | **PRESERVE** — Testnet only; never True in agent_arena_testnet |

---

## 4. Scheduler / Loop Authority

| Surface | File | Notes | Action |
|---------|------|-------|--------|
| `alpha_search/runtime/launcher.py` | launcher | Boots AlphaSearch scenario workers | **SHADOW** — launch with shadow_mode=True; no real orders |
| `snapshot_scheduler` | `domains/snapshot_scheduler/snapshot_scheduler.py` | Generates data snapshots, non-trading | **PRESERVE** |
| `observe_order_lifecycle` | `adapters/binance_ws_client.py` L35 | Passive observation; no order emission | **PRESERVE** |

---

## 5. Config-Level Disable Surfaces (SSOT, Additive)

For an `agent_arena_testnet` profile the following YAML keys must be set:

```yaml
# agent_arena_testnet profile — additive, no fallback overrides
strategies:
  aurora:
    enabled: false
    mode: disabled
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

strategies_registry:
  assignments: {}  # empty — no financially active strategies

domains:
  decision_making:
    operational_mode: paranoid  # strictest gate posture
```

No fallbacks. Setting `strategies_registry.assignments: {}` is the fail-closed surface.
`StrategyRuntime.start()` returns empty dict; no plugin handlers registered; no autonomous signals to FSM.

---

## 6. Dangerous to Touch

| Surface | Risk |
|---------|------|
| `execution_position` domain config | Controls real order submission lifecycle; do not modify reconciliation or bracket config |
| `domains.decision_making.exit` config | Manages open position close paths; disabling exit config may leave open positions unmanaged |
| `observe_order_lifecycle` | Passive — touching would break order state sync |
| `CsvRecorder` / `data_recorder` | Do not disable; needed for FSM/execution logging |
