# MD-AMR Testnet Smoke Activation Report

## Objective
The objective was to run a bounded, evidence-first smoke-proof showing that `md_amr` becomes runtime-active on the real testnet startup path, properly registers itself, and receives live, unblocked event flows.

## 1. Environment & Setup
- **Mode:** `hybrid_live_data_testnet_exec`
- **Symbols Verified:** `BNBUSDT`, `XRPUSDT`
- **Config Enabled:** Yes (Confirmed uncommented in `strategies.yaml`)

## 2. Activation Proofs (Q1 - Q4)
### ✅ Q1. Strategy Load and Integrity
**Result:** Passed  
The initial sanity checks and exchange filters verified both `BNBUSDT` and `XRPUSDT` successfully against testnet exchange rules. `md_amr` configuration structure correctly passed strict Pydantic parsing.
```log
2026-04-10 20:56:08,492 - apps.reference.domains.exchange_filters.validator - INFO - ✅ XRPUSDT: filters match exchange
2026-04-10 20:56:08,851 - apps.reference.domains.exchange_filters.validator - INFO - ✅ BNBUSDT: filters match exchange
```

### ✅ Q2 & Q3. Strategy Initialization, Enablement, and Registration
**Result:** Passed  
The `MDAMRHandler` component successfully initialized and reported hydration success (Hydration Planner allocated exactly 96 basis_bars for 900s timeframe required by `md_amr`). It successfully registered listeners for domain-events:
```log
2026-04-10 20:56:18,735 - apps.reference.domains.decision_making.md_amr_handler.MDAMRHandler - INFO - MD_AMR registered events=['CMD:PROCESS_STRATEGY', 'EVT:FEATURES_CALCULATED', 'EVT:REGIME_DETECTED', 'EVT:TRADE_EXECUTED', 'EVT:ORDER_REJECTED', 'EVT:PORTFOLIO_STATE_UPDATED', 'EVT:EXPOSURE_SUMMARY_UPDATED', 'EVT:ORDER_STATE_CHANGED', 'EVT:TRADE_INTENT_REJECTED'] symbols=['BNBUSDT', 'XRPUSDT'] tf=900
```
Furthermore, the canonical positions startup correctly processed the cold start upgrade:
```log
2026-04-10 20:56:20,350 - ... - INFO - [CLEAN_START_UPGRADE] XRPUSDT execution restore upgraded COLD->RESTORED via canonical position-tracking zero-positions confirmation (ts_ms=1775843780344)
```

### ✅ Q4. Signal Pathway Arrival
**Result:** Passed (Handler Entry)  
Live tick arrival generated `EVT:FEATURES_CALCULATED` and reached the DecisionMaking domain for `BNBUSDT`, successfully generating `on_risk()` processing (proving data path up to DecisionMaking is alive):
```log
2026-04-10 20:56:48,738 - apps.reference.domains.decision_making.decision_making.DecisionMaking - INFO - on_risk() called for BNBUSDT. Risk params: {'symbol': 'BNBUSDT', 'ts': 1775758499999, 'risk_parameters': {'is_trading_allowed': True...}}
```

## 3. Decision Proof (Q5 Blocked Path)
### ❌ Q5 Blocker Encountered: Feature Engineering Imposes Global Aurora Warmup Constraints
**Result:** Blocked (Zero Signals Reached `MDAMRStrategy` path)

**Symptom:**
The strategy core `md_amr` logic never fired, and `CMD:PROCESS_STRATEGY` was never routed to DecisionMaking for `BNBUSDT` and `XRPUSDT`.

**Root Cause & Mechanism:**
`FeatureEngineering` statically filters internal `CMD:PROCESS_STRATEGY` emitting utilizing a monolithic `fail_fast` global requirement evaluating whether a symbol is `full_ready`. Even though the Startup Hydration Planner correctly only pulled 96 M15 bars for `md_amr`, `FeatureEngineering` requires Aurora-native deep pillars (`macro_resid` demanding 60+ samples, `volatility_state:insufficient_history` demanding D1 arrays):

```log
2026-04-10 20:56:48,745 - apps.reference.domains.feature_engineering.feature_engineering.FeatureEngineering - WARNING - [BNBUSDT] CMD:PROCESS_STRATEGY warmup not full_ready (full_ready=False, reasons=['volatility_state:insufficient_history', 'macro_sync:insufficient_bins', 'macro_resid:insufficient_samples:5<60'], enforcement_mode=fail_fast) -> rejected
```
Because of this rejection, `md_amr` receives `EVT:FEATURES_CALCULATED` (used to update risk), but **never receives the fundamental `CMD:PROCESS_STRATEGY` trigger.** 

This global tightness in `FeatureEngineering` protects `Aurora`, but completely silences decoupled logic like `md_amr`.

## Recommendation for Minimal Corrective Patch
According to the rules of Phase 1 / Phase 2, we shouldn't attempt a massive global restructuring. A possible minimal corrective patch:
Provide a config override (or symbol-level logic) in `FeatureEngineering` to conditionally bypass strict standard `full_ready` enforcements if the active strategy doesn't rely on `macro` or deep pillars. Alternatively, adjust `FeatureEngineering` to emit `CMD:PROCESS_STRATEGY` with degraded metadata so `DecisionMaking` handlers can make their own logic choices rather than discarding the command upstream.

**Status:** FAILED / BLOCKED. Awaiting instructions for the minimal corrective patch to fix runtime enablement.
