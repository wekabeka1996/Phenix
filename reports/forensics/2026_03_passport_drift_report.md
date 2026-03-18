# Forensics Report: March 2026 Passport Reconciliations

**Date:** 2026-03-18
**Auditor:** Principal AI Architect / Documentation Forensics Agent
**Scope:** Full codebase/YAML consistency audit against `config/docs/*.md` passports.

## 1. Executive Summary

This cycle completed an end-to-end verification of all configuration and strategy passports against the active code (Python/Pydantic) and the canonical `config/aurora/*.yaml` files. The primary goal was to measure and correct documentary "drift" without deleting historical context.

The major finding across the ecosystem is a **historical shift from declarative-only strategy configurations to strict, runtime-enforced assignment architectures**. Secondary findings involve completed Phase 9 migrations (Quadratic Math, Objective Engine) that older passports had not adequately captured.

## 2. Core Operational Passports

### `system_passport.md` & `trading_passport.md`
- **Removed Modules:** The `account_observer` subsystem is confirmed deleted from the codebase (`system.yaml` no longer references it).
- **Dead/Legacy Risk Rules:** The `trading.risk.daily` gate is explicitly disabled (`enabled: false`) in live config. Numerous soft-limits inside `trading.yaml` exist purely as descriptive metadata or fallback, heavily superseded by downstream `domains.yaml` risk limits.
- **Orchestration:** Integrated `llm_orchestration` policy rules which govern `baseline`, `hybrid_advisory`, or `llm_primary` intents from external upstream sources.

### `domains_passport.md` & `regime_passport.md`
- **Undocumented Domains:** `shadow_telemetry` and `objective_engine` were highly active in Phase 9 code but wholly absent from the auto-generated domain passport. They are now fully documented components.
- **Regime Math Drift:** `regime.yaml` underwent intense R2 parameter tuning. Constants like volatility multipliers and confidence mapping were out-of-sync in the documentation but have now been accurately synchronized. 

## 3. Strategy & Alpha Passports

### `strategies_passport.md` & `mean_reversion_state_machine_passport.md`
- **Assignment-First Activation:** The oldest architectural drift. Passports mistakenly treated `<strategy>.yaml` profile's `enabled: true` flag as the ultimate driver. Codebase actually treats `config/aurora/strategies.yaml` (the registry) as a strict fail-closed boundary. If a strategy isn't assigned to a symbol there, it is dead on arrival.
- **Timeframe Misalignment:** `mean_reversion` class-name holds "1m", old documentation said "3m", but live YAML dictates `timeframe_sec: 300` (5 minutes) mapping exactly to the bar aggregator. Current live assignments confirmed for `DOGEUSDT` only.

### `AURORA_STRATEGY_CONFIG_PASSPORT.md` & `aurora_math_passport.md`
- **Quadratic Math Migration:** `aurora_math_passport.md` accurately captured the end goal—Linear V2 (`aurora_scoring_kernel.py`) is completely dead, and Quadratic Math is the sole entry point. But `aurora.yaml` passport retained old 0.12 signal thresholds and legacy gating logic. We synced `signal_threshold`, `reentry_cooldown_sec` (now 900s), and `anti_fomo_sigma` (now 10.0) with reality.

### `md_amr_strategy_passport.md` & `llm_microstructure_strategy_passport.md`
- **MD AMR Config Constraints:** Confirmed live only for `XRPUSDT` and `BNBUSDT`. End-to-end runtime trace confirmed execution gates but lacks explicit proof of the `reconciliation` block being fully used down the pipe.
- **LLM Microstructure:** Confirmed this is **not** an in-process strategy handler. It uses a sentinel allowlist stub, while actual intent commands are injected via the `shadow_telemetry` IPCS bridge. Profile `timeframe_sec` (60s) has notably drifted from the hardcoded bridge value (300s).

## 4. Conclusion
Overall system health and codebase adherence to config-driven patterns is extremely high (**HIGH confidence**). The drift was mostly linguistic/historical rather than symptomatic of broken engineering. Moving forward, the configuration schemas (`apps/reference/config_models.py`) continue to be the strictest layer of defense against regressions.
