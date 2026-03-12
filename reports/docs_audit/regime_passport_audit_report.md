# Documentation Forensics Audit Report: Regime Passport

**Date:** 2026-03-12
**Target Document:** `config/docs/regime_passport.md`
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope
The scope of this audit was to perform a deep code-trace and verification of the `config/docs/regime_passport.md` against current YAML configurations, Pydantic models, and runtime components associated with Regime Detection and System Stress.

## 2. Files Traced
- **Configs:** `config/aurora/regime.yaml`
- **Pydantic Models:** `apps/reference/config_models.py` (specifically `RegimeDetectorConfig`, `SystemStressConfig`, `VolatilityRegimeModelConfig`, `SMARegimeModelConfig`, etc.)
- **Runtime Consumers:**
  - `apps/reference/domains/regime_detector/regime_detector.py`
  - `apps/reference/domains/decision_making/aurora_handler.py`
  - `apps/reference/domains/decision_making/aurora_decision.py`
  - `apps/reference/domains/system_stress/system_stress_overlay.py`

## 3. Critical Runtime Consumers
- `RegimeDetector.handle_event` (core priority logic and gate enforcement)
- `AuroraHandler._check_regime_liveness` (liveness timeout guard)
- `SystemStressOverlay` (secondary protection layer computation)

## 4. Confirmed Claims
- **Bar-only SSOT:** `basis_tf_sec` dictates the operational resolution; tick-level feature events are discarded.
- **Fail-Closed Logic:** Liveness guard effectively halts trading via `NRR-REGIME-DETECTOR-DEAD` if regimes are missing.
- **Confidence Cutoff:** `uncertain_cutoff` demotes weak regimes to `UNCERTAIN`.
- **Hysteresis:** Anti-churn logic delays regime switches until confirmed over consecutive periods.
- **Volatility Dominance:** Volatility (ATR) maintains Priority 1 in logic over MR and Trend.

## 5. Corrected Claims
- Explicitly documented the `system_stress` block, which was present in code and yaml but largely neglected in the old regime passport structure despite being a parallel FSM actuator.

## 6. Removed Stale Claims
- The deprecated `hmm` and `features` fields from the original config were previously noted as dead but have now been entirely removed from the documentation matching their scorched-earth removal from configs.

## 7. Added Missing Sections
- Added detailed documentation for the `system_stress` overlay configurations: `thresholds`, `aggregation`, and `state_mapping` (Actuator FSM).
- Added clarification on conflict resolution between Volatility, Mean Reversion, and Trend.

## 8. Major Drifts Found
- `models.sma_trend.sma_short_period` is `48` (was `10` or `24`).
- `models.sma_trend.sma_long_period` is `192` (was `50` or `96`).
- `models.volatility.atr_sma_length` is `288` (was `100`).
These parameters have been dynamically tuned per recent Phase R2 optimizations and the passport now acknowledges these R2-Winner settings.

## 9. Final Verdict
The document `config/docs/regime_passport.md` has been successfully rewritten and fully synchronized with the Phase 0.x/R2 codebase updates. It accurately details the robust multi-model priority cascade and the secondary `system_stress` overlay.
**Status: DONE**
