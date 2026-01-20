# Forensic Investigation Report: SL/TP Silent Fallbacks

## Executive Summary
We have confirmed "Silent Fallbacks" (Architectural Violation) where the system overrides Strategy-generated Stop Loss (SL) and Take Profit (TP) prices with hardcoded configuration values. This explains the tight SL (~0.4%) and "strange" TP behavior observed in backtests.

## 1. Fallback Source Located
The overrides occur in two places, forming a "double barrier" against strategy intent:

1.  **`DecisionMaking` Domain (`decision_making.py`)**:
    *   **Location**: `_on_strategy_signal_gateway` (lines 876-1068).
    *   **Mechanism**: The handler extracts `entry_price` from the strategy's signal payload (`price_ctx`) but **ignores** `stop_price` and `target_price`. It then optionally runs `EntryPlan` to calculate new keys, or leaves them as `None`. The strategy's calculated prices are discarded here.

2.  **`ExecutionPosition` Domain (`fsm.py`)**:
    *   **Location**: `_execute_trade` (lines 2247-2348).
    *   **Mechanism**: The FSM **unconditionally** loads `sl_pct` and `tp_low_ratio` from `strategies.aurora.assets.<SYMBOL>` and re-calculates SL/TP from the execution price. It completely ignores any `stop_price` or `target_price` passed in the `DEC:OPEN` command.
    *   **Config Trace**: This `sl_pct` (likely set to 0.4% or similar in config) is the source of the "fixed_bps: 40" behavior. The code comment explicitly notes: `# SSOT: strategies.aurora.assets.<SYMBOL>.exit.sl_pct (NOT brackets.fixed_bps!)`, confirming `sl_pct` is the active fallback mechanism replacing legacy `fixed_bps`.

## 2. MeanReversion Strategy Audit
*   **File**: `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
*   **Findings**:
    *   The strategy **correctly calculates** `stop_price` (ATR-based) and `target_price`.
    *   It supports `tp_to_mid` logic (setting target to Bollinger Band mid).
    *   It emits these values in the `MRSignal` -> `price_ctx`.
    *   **Root Cause**: These values are emitted but never propagated by `DecisionMaking` nor respected by `ExecutionPosition`.

## 3. tp_to_mid Investigation
*   **Logic**: `target_price = bb.mid` (in `MeanReversion1mStrategy`).
*   **Failure**: Since `DecisionMaking` drops this value and `ExecutionPosition` re-calculates TP based on `tp_low_ratio` * `sl_pct`, the dynamic "return to Mean" logic is replaced by a fixed ratio calculation. This explains why TP is placed "very far away" or at unexpected levels (it's purely math-based on entry price, ignoring Bollinger Bands).

## Remediation Plan (Explicit Configuration) - ✅ IMPLEMENTED

### A. Fix `DecisionMaking` Propogation ✅ DONE
**File**: `apps/reference/domains/decision_making/decision_making.py`
**Location**: `_on_strategy_signal_gateway` (lines ~982-1100)

**Changes Applied:**
1. Added STEP 1: Extract `stop_price` and `target_price` from `price_ctx` FIRST
2. Added STEP 2: Initialize with Strategy values (Primacy)
3. Added STEP 3: EntryPlan only fills in MISSING values (not overwrites)
4. Added logging for Strategy Primacy usage
5. Preserved strategy prices even if EntryPlan fails

### B. Fix `ExecutionPosition` Respect ✅ DONE
**File**: `apps/reference/domains/execution_position/fsm.py`
**Location**: `_execute_trade` (lines ~2247-2400)

**Changes Applied:**
1. Added STEP 1: Check for explicit `stop_price`/`target_price` from DEC:OPEN payload
2. Added STEP 2: Config-based fallback ONLY if Strategy did not provide prices
3. Added STEP 3: Strategy Primacy logic with explicit source tracking
4. Added proper logging distinguishing STRATEGY vs CONFIG_FALLBACK sources
5. Fail-closed: If neither Strategy nor Config provide prices → REJECT order

### C. Test Suite ✅ CREATED
**File**: `tests/domains/test_strategy_primacy_sl_tp.py`
- 10 comprehensive tests covering:
  - Strategy prices extracted from price_ctx
  - Strategy prices take precedence over EntryPlan
  - EntryPlan used only when strategy missing
  - Explicit SL/TP extracted from decision payload
  - Strategy SL takes priority over config
  - Config fallback when strategy missing
  - Fail-closed when neither available
  - Mixed sources (Strategy SL + Config TP)
  - MR signal price_ctx format
  - MR dynamic SL not overwritten

### Test Results
```
============================== 70 passed in 0.08s ==============================
```

All 70 tests pass (10 new Strategy Primacy + 60 existing execution position tests)
