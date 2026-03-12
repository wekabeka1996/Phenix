# Documentation Forensics Audit Report: Scoring Passport

**Date:** 2026-03-12
**Target Document:** `config/docs/scoring_passport.md`
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope
The scope of this audit was to deeply trace the scoring logic of the Phenix Aurora Trading System by comparing the `config/docs/scoring_passport.md` against current YAML configs, Pydantic models, runtime components, and schema contracts.

## 2. Files Traced
- **Configs:** `config/aurora/strategies/aurora.yaml`, `config/aurora/strategies/mean_reversion.yaml`, `config/aurora/domains.yaml`
- **Pydantic Models:** `apps/reference/config_models.py`
- **Runtime Consumers:**
  - `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`
  - `apps/reference/domains/decision_making/aurora_scoring_kernel.py`
  - `apps/reference/domains/decision_making/aurora_config_loader.py`
  - `apps/reference/domains/decision_making/aurora_decision.py`
  - `apps/reference/domains/risk_management/risk_management.py`
  - `apps/reference/contracts/quadratic_rollout.py`
- **Other Entities:** Shield cascade (`apps/reference/domains/decision_making/shields/`)

## 3. Critical Runtime Consumers
- `QuadraticScoringKernel.compute` (Phase 9 scoring)
- `AuroraScoringKernel.compute` (v2 fallback scoring)
- `RiskManagement._calculate_risk_parameters` (L2 Instrument risk score)
- `DailyGate.can_open` (L1 Portfolio risk)

## 4. Confirmed Claims
- **Fail-Closed Principle:** Signals defer if essential features are missing or invalid.
- **L1 Portfolio Risk Gate:** Still effectively active and blocks on drawdown/loss thresholds.
- **Hysteresis & Side Bias:** Still effectively implemented in the runtime logic to prevent flip-flopping and overexposure to one direction.
- **Net-Zero Normalization:** Linear mode (`v2`) accurately utilizes `signed_v2` stretches.

## 5. Corrected Claims
- **Scoring Kernel Identity:** The primary document previously described `AuroraScoringKernel` as the single SSOT. It has been updated to reflect the routing logic that splits into the Phase 9 `QuadraticScoringKernel` (non-linear `Exposure = sign(Σ) × Σ² × shield_multiplier`) and the `v2` linear fallback.
- **Absorption Penalty in L2 Risk:** The previous document claimed `toxicity = |tfi| * clip(delta_price_pct / cap)`. The runtime was updated to dynamically split absorption into a directionless proxy (`toxicity`) and a feature-based applied value, configurable via `absorption_penalty_source`.
- **Mean Reversion Defaults:** The parameters for Mean Reversion (DOGE, XRP, BTC, SOL) were updated to match the active `mean_reversion.yaml` configurations.

## 6. Removed Stale Claims
- `macro_sync` removed as an active driver of signal weight in the document (it's legally 0.0 and marked as telemetry/deprecated in code).
- The assumption that L3 purely consists of linear math was lifted in favor of the new Phase 9 reality.

## 7. Added Missing Sections
- **Phase 9: Quadratic Brain:** Added a full explanation of `pillar_sum`, quadratic exposure conversion, and the Shield Cascade logic (`MemoryShield`, `DangerZone`).

## 8. Dead/Legacy Fields
- `macro_sync` (weight 0.0, marked legacy telemetry).
- Unused regimes inside `regime_thresholds` blocks are now documented as usually set to 99.0 (absolute block).

## 9. Final Verdict
The document `config/docs/scoring_passport.md` has been fully rewritten and synchronized. It represents the accurate state of the `v2` linear engine and the heavily requested Phase 9 Quadratic brain integration. 
**Status: DONE**
