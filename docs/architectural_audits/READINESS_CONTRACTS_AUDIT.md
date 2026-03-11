# Phenix Systems Readiness Contracts Audit

**Date:** 2026-03-02
**Auditor:** Principal Systems Contract Auditor
**Scope:** Deep Audit of Readiness, Warmup, Hydration, and Restart Semantics.
**Methodology:** Read-Only Code-First Analysis.

---

## 1. Executive Summary

This document synthesizes the implicit and explicit readiness contracts currently distributed across the Aurora/Phenix codebase. The system operates on a highly distributed "fail-closed" paradigm where multiple components track their own warmup states independently. However, a lack of unified orchestration leads to **False-Ready conditions** at the execution layer and **partial-ready** execution loops.

## 2. Startup to First Trade-Eligible Cycle (The Exact Path)

A trade cannot be legally executed until this exact sequence is completed:

1. **Disaster Recovery (Analytics Hydration):** `position_tracking` loads JSON snapshots and replays the WAL.
2. **Execution FSM Hydration:** `execution_position.hydrate()` rebuilds `OpenPositionFSM` instances from the recovered portfolio state.
3. **Exchange Sync (Leverage Bootstrap):** `execution_position` makes REST API calls to set margin mode and leverage parameters via `LeverageBootstrapper`.
4. **Order Reconciliation:** `sync_open_orders_and_positions()` binds remote execution states and starts the `OrderGuardian`.
5. **Feed Connection:** Websocket market data streams commence.
6. **HTF Pillar Backfill:** `FeatureEngineering` asynchronously calls REST APIs to fetch HTF (e.g., D1, H4) history (`warmup_pillars()`).
7. **Basis Bar Warmup:** Incoming data fills `RegimeDetector` buffers (e.g., `sma_long_period`, `atr`).
8. **Feature Readiness:** FE triggers `full_ready = True` and starts emitting `CMD:PROCESS_STRATEGY` and `EVT:FEATURES_CALCULATED`.
9. **Risk Readiness:** `RiskManagement` evaluates the live data stream, calculates `risk_score`, and emits `EVT:RISK_ASSESSMENT_COMPLETED`.
10. **Strategy Live Warmup:** For specific strategies (e.g., `md_amr`), an explicit clock starts (e.g., 2 hours).
11. **First Trade Intent:** `DecisionMaking` validates `warmup.full_ready`, `risk_missing`, live warmup clocks, and execution gates, allowing the first intent to pass to Execution.

---

## 3. Existing Readiness States (Code-First Analysis)

### 3.1 Feature Engineering (FE) Warmup / `full_ready`
- **Type:** Explicit / Bar-Only.
- **Location:** `apps/reference/domains/feature_engineering/feature_engineering.py`, `regime_detector.py`.
- **Contract:** Collects component readiness (`sma_short`, `sma_long`, `atr`, `atr_baseline`). Sets `warmup.full_ready` bool in the `EVT:FEATURES_CALCULATED` payload.
- **Blocking Target:** Upstream. Blocks emission of `CMD:PROCESS_STRATEGY` entirely if missing, or downstream `DecisionMaking` gates block if `full_ready` is false (unless overridden via `warmup_enforcement_mode="warn_only"`).

### 3.2 Regime Readiness
- **Type:** Explicit / Sub-component of FE Warmup.
- **Contract:** Defined purely by the lengths of `sma_short_period` and `sma_long_period`. Emits `UNCERTAIN` until mathematical buffers are filled.
- **Blocking Target:** `DecisionMaking` arming. If `arming_require_regime_warmup=True`, Strategy processing is deferred.

### 3.3 HTF Pillar Readiness (Quadratic/Aurora v2)
- **Type:** Explicit / REST Replay required.
- **Location:** `pillar_backfill.py` & `quadratic_scoring_kernel.py`.
- **Contract:** `warmup_pillars()` fetches missing HTF bars to prime multi-timeframe matrices.
- **Blocking Target:** Scoring calculation. If a pillar returns `NOT_READY`, the Kernel gracefully defers the signal (`defer_reason="PILLAR_WARMUP"`).

### 3.4 Microstructure & Live-Stream Readiness
- **Type:** Explicit / Live Microstructure required.
- **Contract 1 (MD_AMR):** `md_amr_handler` defines `_MANDATORY_LIVE_WARMUP_SEC = 7200` (2 hours). `_is_mandatory_live_warmup_active` absolutely blocks intents until the live clock expires.
- **Contract 2 (AuroraScoringKernel):** Requires `essential_features` (e.g., `obi`, `tfi`). If the live stream hasn't aggregated them, the kernel skips scoring (`defer_reason="features_missing"`).
- **Blocking Target:** Trade intent emission.

### 3.5 Risk / Liquidity Readiness
- **Type:** Explicit.
- **Contract:** `DecisionMaking` validates that an `EVT:RISK_ASSESSMENT_COMPLETED` has been received (`risk_missing` check in `readiness_gates.py`).
- **Blocking Target:** Signal processing logic.

### 3.6 Execution-Context Readiness (Leverage Bootstrap)
- **Type:** Implicit.
- **Location:** `apps/reference/domains/execution_position/leverage_config.py`.
- **Contract:** Bootstrapper attempts to set the correct leverage/margin mode via exchange REST endpoints.
- **Blocking Target:** Order Lifecycle only (Or rather, it *should* block).

---

## 4. Mandatory Findings & Mismatches

### 4.1 False-Ready Conditions
- **[CONFIRMED] Leverage Bootstrap is Not enforced.** `main.py` calls `run_leverage_bootstrap()` which returns a set of `blocked_symbols`. However, this set is merely logged (`LOG.warning`) and is **NEVER** injected into `DecisionMaking` or `ExecutionPosition` context. The system will appear "ready" to the strategy despite critical exchange-side leverage mismatches, resulting in severe API rejections on the first trade.

### 4.2 Partial-Ready Conditions
- **[LIKELY] L1/L2 Risk Asymmetry.** `RiskManagement` runs completely decoupled from FE Warmup. While `DecisionMaking` enforces that `RiskManagement` must have responded (`risk_missing`), `RiskManagement` itself doesn't guarantee that the `risk_score` was computed with "warmed up" data, creating a potential mathematical vulnerability on start.

### 4.3 Hidden-Ready Assumptions
- **[CONFIRMED] REST Hydration in Live Loops.** `MD_AMR` implements a silent internal REST fetch for klines on startup (`_REST_HYDRATION_LIMIT`). If this API call fails or times out, it logs a warning but proceeds to enter its mandatory 2-hour live warmup phase.

### 4.4 Restart Asymmetry (Execution vs Analytics)
- **[CONFIRMED]** `position_tracking` relies on an exhaustive and mathematically exact WAL replay mechanism. In contrast, `execution_position` rebuilds in-memory `OpenPositionFSM` instances via a rudimentary `hydrate()` mapping.
- **[CONFIRMED]** Orders currently in-flight during a system crash are handled via a delayed background task (`InFlightReconciler`). The system is marked "ready" before these in-flight state discrepancies are fully resolved, risking duplicate order issues if a strategy immediately outputs an intent.

---

## 5. Proposed Canonical Readiness Scopes

To eliminate edge cases and false-ready telemetry, readiness should be strictly orchestrated as hierarchal, canonical stages:

1. **`execution_context_ready`**
   - Must prove successful API bootstrap (Leverage, Margin Mode).
   - Must guarantee 0 pending `InFlightReconciler` repairs.
2. **`quadratic_htf_ready`**
   - Must guarantee all asynchronous HTF (D1, H4) pillars are backfilled via REST replay.
3. **`basis_bar_ready`**
   - Must guarantee local mathematical validity (`FE full_ready` based on required lengths for SMA, ATR, etc.).
4. **`regime_ready`**
   - Must guarantee trend and volatility models have stabilized out of the `UNCERTAIN` state.
5. **`microstructure_ready`**
   - Must guarantee a statistically significant density of live `obi`/`tfi`/`liquidity` packets have been digested.
6. **`strategy_ready_per_symbol`**
   - A composable boolean derived dynamically from the required states above. For example, `md_amr` requires `microstructure_ready = 7200s`, while `aurora` does not.
7. **`trading_ready`**
   - The absolute master gate. Validates `strategy_ready_per_symbol`, `execution_context_ready`, and L1/L2 `risk_liquidity_ready` presence. No downstream logic is permissible until this is explicitly `True`.
