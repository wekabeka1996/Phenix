# Config Contract Map — SSOT v1.0

> Canonical resolver inventory for trading configuration. Additive-only. Direct YAML reads forbidden.

## Overview

This document maps configuration files to their sanctioned resolvers and consuming domains. All runtime config access must go through these resolvers to maintain contract integrity.

**Sources:**
- Full key inventory: `docs/config_analysis/config_inventory.md` and `docs/config_analysis/config_inventory_raw.json`
- Schema validation: `config_schema_v1.py`
- Freeze notes: `CONFIG_CONTRACT_FROZEN.md`

## Config Files → Resolvers → Domains (snapshot v0.1)

| Config File | Main Resolvers | Consuming Domains | Status |
|-------------|----------------|-------------------|--------|
| `config/aurora/trading.yaml` | `resolve_execution_manage_config`, `resolve_brackets_config`, `resolve_exposure_policy`, `get_trade_cooldown_sec_for_symbol`, `compute_effective_trading_modes`, `get_domain_mode_from_mapping` | `decision_making`, `risk_management`, `execution_position`, `feature_engineering`, `market_data`, `position_tracking`, `regime_detector` | active |
| `config/aurora/system.yaml` | `ConfigLoader` (general), `resolve_exposure_policy` (exposure caps), `DailyRiskState` (daily limits) | `bootstrap`, `monitoring`, `orchestrator`, `system`, `execution_position` | active |
| `config/aurora/regime.yaml` | `resolve_regime_detector_config` | `regime_detector`, `risk_management`, `execution_position` | active |
| `configs/master_config_v1.yaml` | `tools/verify_config.py`, `ConfigLoader` (frozen generation) | `pipeline_overview`, `docs/PRICE_SERVICE_CONTRACT`, `config_contract_map` | active |
| `config/aurora/trading_v0.2.yaml` | Legacy resolvers (same as trading.yaml, but deprecated) | Same as trading.yaml | legacy |
| `config/aurora/trading.staging.override.yaml` | `ConfigLoader` (overrides applied post-load) | Staging-specific domains | active |

## Resolver Contracts

### resolve_execution_manage_config
- **Inputs:** `trading.execution.manage.*` from `trading.yaml`
- **Outputs:** Brackets enable, orphan monitor settings, quick profit config
- **Domains:** `execution_position`, `order_guardian`

#### execution.manage.brackets.aggregated_oco

Contract `AggregatedOcoConfig`:

- `enabled: bool` (default: `false`)
- `recalc_on_scale_in: bool` (default: `true`)
- `recalc_on_partial_close: bool` (default: `false`)
- `ttl_protect_new_bracket_ms: int` (default: `3000`)
- `allow_unprotected_position: bool` (default: `false`)

Consumers:

- `apps/reference/domains/execution_position/fsm_manage.py` — визначає, коли перераховувати aggregated OCO.
- `apps/reference/domains/execution_position/order_guardian.py` — застосовує `ttl_protect_new_bracket_ms` та `allow_unprotected_position` до cleanup-поведінки.

Особливості:

- При `aggregated_oco.enabled=true` OrderGuardian переходить у режим position-level aggregated cleanup.
- За відсутності секції `aggregated_oco` діє legacy (`keep_single_bracket_set`, поточний OrderGuardian).

### resolve_brackets_config
- **Inputs:** `trading.execution.manage.brackets.*` from `trading.yaml`
- **Outputs:** SL/TP bps, retry policies, atomic close flags
- **Domains:** `execution_position`

### resolve_exposure_policy
- **Inputs:** `trading.execution.exposure.*` from `trading.yaml` + `system.yaml`
- **Outputs:** Max utilization %, leverage defaults, fallback sequences
- **Domains:** `execution_position`, `position_tracking`

### get_trade_cooldown_sec_for_symbol
- **Inputs:** `trading.instruments.{symbol}.trade_cooldown_sec` from `trading.yaml`
- **Outputs:** Per-symbol cooldown seconds
- **Domains:** `decision_making`, `execution_position`

### compute_effective_trading_modes
- **Inputs:** `trading.domain_configuration.*` from `trading.yaml`
- **Outputs:** Domain-specific mode mappings with fallbacks
- **Domains:** All domains (via `ConfigLoader`)

### get_domain_mode_from_mapping
- **Inputs:** Domain mode mappings
- **Outputs:** Effective mode for a given domain
- **Domains:** All

### DailyRiskState
- **Inputs:** `trading.risk.daily.*` from `trading.yaml`
- **Outputs:** Daily loss/drawdown trackers
- **Domains:** `risk_management`

## Config v2 Mapping (design snapshot)

This section outlines the planned migration from legacy config paths to modular config v2 structure. Config v2 introduces separation by domains, instruments, and overrides for better modularity and additive evolution.

| Legacy path | Config v2 file | Config v2 path | Resolver | Notes |
|-------------|---------------|----------------|----------|-------|
| `trading.execution.manage` (quick_profit, brackets, orphan_monitor) | `domains/execution.yaml` | `execution.manage.*` | `resolve_execution_manage_config` | Migrated to domain-specific file; quick_profit and orphan_monitor settings preserved. v2 primary, legacy fallback. |
| `trading.execution.brackets` (SL/TP bps, offset_bps) | `domains/execution.yaml` | `execution.brackets.*` | `resolve_brackets_config` | TP/SL brackets separated into execution domain. v2 primary, legacy fallback. |
| `trading.execution.exposure` | `domains/execution.yaml` | `execution.exposure.*` | `resolve_exposure_policy` | v2 primary, legacy fallback (trading.execution.exposure.* + trading.execution.fallback.*). |
| `trading.decision.qos`, `trading.decision.signals` | `domains/decision.yaml` | `decision.qos.*`, `decision.signals.*` | `resolve_decision_config` (planned) | QoS thresholds and signal parameters separated into decision domain. |
| `trading.risk.daily_limits`, `trading.risk.soft_limits` | `domains/risk.yaml` | `risk.daily.*`, `risk.soft.*` | `resolve_risk_limits` (planned) | Daily and soft limits consolidated in risk domain config. |
| `trading.risk.daily_limits.*` | `config/domains/risk.yaml: daily_limits.*` | `resolve_daily_risk_state` | Unified daily risk limits with config v2 support; replaces scattered definitions. Primary: config v2; Fallback: legacy. |
| `trading.decision.position_sizing.*`, `trading.decision.kelly.*`, `trading.decision.sizing_modifiers.*` | `config/domains/sizing.yaml: defaults.*, symbols.*, regimes.*` | `resolve_sizing_policy` | Position sizing parameters with config v2 support; includes risk fraction, kelly, regime multipliers. Primary: config v2; Fallback: legacy. |
| `trading.decision.signal_threshold`, `trading.decision.neutral_threshold`, `trading.decision.qos.*` | `config/domains/decision.yaml: thresholds.*, qos.*` | `resolve_decision_policy` | Decision making thresholds and QoS parameters with config v2 support. Primary: config v2; Fallback: legacy. |
| `trading.feature_engineering.*`, `trading.market_data.macro_sync.*` | `config/domains/features.yaml: global.*, windows.*, features.*, macro_sync.*` | `resolve_feature_engineering_config` | Feature engineering parameters with config v2 support; includes EMA, volume, volatility, liquidity, macro_sync. Primary: config v2; Fallback: legacy. |
| `trading.trading_mode`, `trading.domain_configuration.*` | `config/modes.yaml` | `modes.profiles.{profile}.trading_mode`, `modes.profiles.{profile}.domains.*` | `compute_effective_trading_modes`, `get_domain_mode_from_mapping` | Trading modes and domain configurations centralized in modes.yaml. Primary: config v2; Fallback: legacy. |

### New meta-resolvers (planned)

These resolvers will handle config v2 structure, reading from multiple files and applying overrides.

- **resolve_instrument_profile(symbol)**: Reads `instruments.yaml` (base profiles) and `overrides.yaml` (per-symbol/per-regime overrides). Outputs unified instrument profile with invariants (precision, limits, tp_sl, etc.). Used by: `execution_position` (step_size, tick_size), `decision_making` (min_notional), `risk_management` (risk_fraction), `regime_detector` (regime_multipliers).

- **resolve_effective_sizing(symbol)**: Reads `instruments.yaml` (risk settings), `overrides.yaml` (sizing overrides), `modes.yaml` (mode-specific multipliers). Outputs effective sizing parameters. Used by: `risk_management`, `execution_position`.

- **resolve_trading_modes()**: Reads `modes.yaml` (global modes and domain mappings). Outputs effective mode configurations with fallbacks. Used by: All domains (via `ConfigLoader`).

## Phase 1 — Status

- Config v2 specification created (`docs/config_v2/specification.md`).
- Instrument profile spec created (`docs/config_v2/instrument_profile.md`).
- Config v2 mapping documented in this file.
- Execution domain migrated to config v2 (exposure, manage, brackets) with dual-mode resolvers.
- Next step: Implementation of dual-mode resolvers (Phase 2).
