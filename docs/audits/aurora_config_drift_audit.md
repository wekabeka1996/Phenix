# Configuration/Runtime/Registry Drift Audit
**Date:** 2026-03-10
**Target:** Aurora/Phenix Config/Runtime/Registry 

This document outlines a code-first audit for drift across startup, warmup, scoring, regime, strategy activation, and execution lifecycle.

## Methodology
1. **Schema vs YAML:** Analyzed `config/aurora/**/*.yaml` against [apps/reference/config_models.py](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py) Pydantic schemas.
2. **Code Consumers:** Statically analyzed the codebase (`apps/reference/**/*.py`) to find code references to configuration variables.
3. **Drift Identification:** Identified overlapping sets, missing consumers, and dead configuration paths.

## Key Findings (Ranked by Severity)

### CRITICAL: Misleading Operator Expectations
These configurations suggest active functionality but do not alter runtime behavior, leading operators to false assumptions.

- **`liquidity_kappa` (Risk/Position Sizing)**
  - **Evidence:** Defined in old configs as a signal weight, but the code comment explicitly states it was removed. `TASK-ZOMBIE-FIX: Removed dead fields (kappa_mode, liquidity_kappa... never wired to runtime)`. It was replaced by [LiquidityGateConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#279-310).
  - **Impact:** Misleads operators into thinking kappas scale signals, when it's actually a hard pass/fail gate now.
  - **Fix Direction:** Remove `liquidity_kappa`, `kappa_mode`, `liquidity_kappa_mode`, and `risk_fraction_q` from all YAMLs. 

- **`failsafe_qty_check` (Liquidity Gate)**
  - **Evidence:** [LiquidityGateConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#279-310) has `failsafe_qty_check` marked explicitly as `[NOT_IMPLEMENTED]`. The code states: "failsafe_qty_check is parsed but NOT wired to runtime."
  - **Impact:** Misleads operator into thinking that min_qty is double-checked after the gate passes.
  - **Fix Direction:** Remove field `failsafe_qty_check` from [LiquidityGateConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#279-310) and any underlying YAML configurations.

### HIGH: Legacy Aliases and Duplicated Configurations

- **`macro_sync` (Directional Scoring)**
  - **Evidence:** Replaced by `macro_resid` (beta-adjusted residual weight). `macro_sync` is kept for "backward compat" defaulting to `0`. 
  - **Impact:** Causes duplicated configuration and potential ambiguity in scoring tuning.
  - **Fix Direction:** Fully deprecate `macro_sync`, purge from Pydantic and YAMLs, enforcing the usage of `macro_resid`.

- **`absorption` (Directional Scoring)**
  - **Evidence:** Defaulting to `0.0`. Market as: `0.0 = disabled (backward compat). Set >0 after Phase 2 calibration.` 
  - **Impact:** Exists in the schema but appears inactive. If it remains 0.0 in Phase 3 it is dead logic.
  - **Fix Direction:** Ensure weights are actually > 0.0 or remove if Phase 2 calibration failed/abandoned.

### MEDIUM: Orphaned Configurations / Unused Pydantic Models

Numerous Pydantic models appear defined but with no corresponding YAML initialization or limited active code consumers. 
_Note: these require deeper contextual verification as they might be injected programmatically rather than via YAML, but represent potential schema drift._

- **Alerting / Observability Orphans:**
  - `max_alerts_per_hour`
  - `recent_alerts_max_keys`
  - `slack_webhook_url`

- **Shield / Context Orphans:** (Old gating mechanisms)
  - `context_shield`
  - `memory_shield`
  - `danger_zone_shield`
  - `shield_enabled`

- **Regime/Scoring Orphans:**
  - `blocked_regimes`
  - `danger_regimes`
  - `no_regime_multiplier`
  - `stale_mult_danger`
  - `stale_mult_normal`
  - `min_pillar_confidence`

**Fix Direction:** 
1. If these are dynamically injected, ensure `extra='forbid'` does not cause validation failures.
2. If these are from deprecated features, remove the Pydantic models entirely to clean up the SSOT.

### LOW: YAML Keys without Schema / Code Consumers
The python regex script found several literal values or deep nested keys present in YAML configurations that couldn't be cleanly mapped to Pydantic definitions or explicit code access.

- **Examples:** `180`, `300`, `900`, `__default__`, `cvar_threshold_bps`, `decay_half_life_days`, `dynamic_ratio`, `glr`, `hash_algorithm`, `information`, `portfolio_state`.

**Fix Direction:** 
1. Manually audit the specific YAML files (`config/aurora/*`) containing these keys.
2. If they are leftover from A/B tests or old strategy parameters, prune them. 

## Actionable Next Steps
1. **Clean up YAMLs:** Purge `liquidity_kappa` and related legacy scaling variables.
2. **Clean up Pydantic:** Remove `failsafe_qty_check` and `macro_sync`.
3. **Audit Shields:** Investigate if the `*_shield` models are actively hydrated via an alternative code path (e.g. database/API) or if they are dead code.
