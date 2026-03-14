# MEAN REVERSION STRATEGY - FORENSIC AUDIT REPORT

## SECTION 1 — EXECUTIVE SUMMARY
- **Total `mean_reversion` Intents:** 5
- **Total Orders Placed:** 3
- **Orders Blocked by Risk/Pyramiding Guard:** 2
- **System Logic Correctness:** `SYSTEM-CORRECT` (Entries fully complied with algorithmic parameters).
- **Quant Logic Correctness:** `BAD-READ` / `WEAK-EDGE`. The strategy aggressively shorted into a low-volatility squeeze breakout (volatility expansion), repeatedly fighting an emerging uptrend.
- **Exit Logic Integrity:** `CRITICAL EXECUTION FAILURE`. The market price breached the Stop Loss (SL) levels for at least two of the orders, yet the local brackets failed to execute or synchronize. One order was ultimately garbage-collected by a 3600s TTL timeout 70 minutes after open, at a price far worse than its SL.

**Top Actionable Findings:**
1. **Critical SL Failure:** Investigate `STOP_MARKET` bracket sync with Binance Testnet. SL levels are being breached without position closure.
2. **Vol-Expansion Blindspot:** `mean_reversion` requires a filter against narrow Bollinger Band breakouts (`bb_width < 0.01`). Shorting these setups catches "knives" during regime transitions.

---

## SECTION 2 — DATA COVERAGE AND LIMITS
- **Data Sources:** `logs/order_log_v1.jsonl`, `logs/trade_lifecycle.jsonl`, `logs/aurora_core.log.5`, `logs/domain_execution_position.log.1`, `logs/event_chain.log.1`.
- **Market Data:** Inferred from `FeatureEngineering` periodic state logs, as granular ticks were unavailable for the specific execution window (2026-03-13 10:35 - 11:45 UTC+2).
- **Limitations:** Intrabar sequence (tick-level) is unprovable. Counterfactuals are constructed using the 5-minute snapshot intervals present in the logs.

---

## SECTION 3 — SCHEMA / FIELD MAPPING
- **Orders:** Mapped via `rid` (e.g., `rid-a30db165502be7a4`).
- **Strategy ID:** Passed from `mean_reversion_handler` and confirmed via `STRATEGY_SIGNAL_GATEWAY` logs.
- **Market State:** Reconstructed from `FeatureEngineering` emitted JSON payloads tied to the exact timestamps of the decisions.

---

## SECTION 4 — FULL ORDER INVENTORY TABLE

| Trade Index | Order ID | RID | Symbol | Side | Open TS | Close TS | Entry Price | Raw Close Reason | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 736300548 | rid-a30db165502be7a4 | DOGEUSDT | SELL | 10:35:02 | 11:45:02 | 0.096995 | TTL_EXPIRED_3600s | ORPHANED_TTL |
| 2 | 736322119 | rid-29d4c71e2d273a76 | DOGEUSDT | SELL | 10:50:03 | N/A | 0.097315 | N/A | OPEN / UNKNOWN |
| 3 | 736400063 | rid-e273872e3955074b | DOGEUSDT | SELL | 11:45:02 | N/A | 0.098465 | N/A | OPEN / UNKNOWN |

*(Note: Two additional intents `rid-f57eea4eeb584229` and `rid-6734784db070fd64` were correctly blocked by `FLIP_ORCHESTRATION: BLOCK - Same-side pyramiding not allowed`)*

---

## SECTION 5 — PER-TRADE FORENSIC DOSSIER

### TRADE 1: `rid-a30db165502be7a4`
- **Symbol / Side:** DOGEUSDT / SELL (Short)
- **Open TS:** 10:35:02
- **Entry Price:** 0.096995
- **Brackets:** TP = 0.096220, SL = 0.097377
- **Raw Close Reason:** `TTL_EXPIRED_3600s` at 11:45:02

**Entry Evidence:**
- `why`: `price_above_upper_bb:pct_b=1.142;regime:FLAT_LOW`
- `bb_width`: 0.00879
- `confidence`: 0.88

**System-Logic Validation:** `SYSTEM-CORRECT`
The signal strictly adhered to the strategy's entry constraints (price > Upper BB in a FLAT_LOW regime).

**Independent Quant Validation:** `BAD-READ`
The `bb_width` of `0.00879` (sub 1%) in a FLAT_LOW regime indicates a tight consolidation squeeze. A breakout to `pct_b = 1.142` is highly indicative of volatility expansion and the birth of a new directional trend. Fading this breakout is probabilistically flawed.

**Exit Evidence & Counterfactual (+1h):**
- **SL Reached?:** YES. By 10:50, price was 0.097315 (approaching SL of 0.09737). By 11:05, price was 0.097570 (SL explicitly breached).
- **First Event:** SL breached.
- **Premature Close?:** No, the close was actually *delayed*. The local system failed to process the SL fill. It was forcefully purged 70 minutes later by a TTL watchdog when the price was at 0.098465, causing a much larger realized loss than intended.
- **Final Trade Verdict:** `GOOD SYSTEM ENTRY / CRITICAL EXECUTION FAILURE`

---

### TRADE 2: `rid-29d4c71e2d273a76`
- **Symbol / Side:** DOGEUSDT / SELL (Short)
- **Open TS:** 10:50:03
- **Entry Price:** 0.097315
- **Brackets:** TP = 0.096130, SL = 0.097780
- **Raw Close Reason:** NONE (Left Open in logs)

**Entry Evidence:**
- `why`: `price_above_upper_bb:pct_b=1.053;rsi_overbought:73.7;regime:FLAT_LOW`
- `bb_width`: 0.01457
- `confidence`: 0.91

**System-Logic Validation:** `SYSTEM-CORRECT`

**Independent Quant Validation:** `WEAK-EDGE`
The system is doubling down on a short position against an active uptrend (price moved from 0.0969 to 0.0973 in 15 mins). While RSI was 73.7, momentum was aggressively working against the mean.

**Exit Evidence & Counterfactual (+1h):**
- **SL Reached?:** YES. By 11:45, the market price was `0.098465`, heavily breaching the SL of `0.097780`.
- **First Event:** SL breached.
- **Premature Close?:** N/A (Order failed to close).
- **Final Trade Verdict:** `SYSTEM-RULE COMPLIANT / EXECUTION FAILURE`

---

### TRADE 3: `rid-e273872e3955074b`
- **Symbol / Side:** DOGEUSDT / SELL (Short)
- **Open TS:** 11:45:02
- **Entry Price:** 0.098465
- **Brackets:** TP = 0.095964, SL = 0.098997
- **Raw Close Reason:** NONE (Left Open in logs)

**Entry Evidence:**
- `why`: `price_above_upper_bb:pct_b=1.037;rsi_overbought:80.5;regime:FLAT_LOW`
- `bb_width`: 0.0311
- `confidence`: 0.87

**System-Logic Validation:** `SYSTEM-CORRECT`

**Independent Quant Validation:** `QUANT-VALID` (borderline)
With RSI > 80 and a significantly wider BB (`0.0311`), this is a much more standard mean reversion stretch setup compared to the first trade. However, it is still fighting a massive 1-hour trend impulse.

**Exit Evidence & Counterfactual (+1h):**
- **Data Insufficient:** Logging simulation terminates shortly after this timestamp. Cannot conclusively determine if TP or SL was reached first.

---

## SECTION 6 — CROSS-TRADE SYNTHESIS
1. **Trend Blindness:** `mean_reversion` fired three consecutive SELL signals on DOGEUSDT as the price rose persistently from 0.0969 to 0.0984. 
2. **Pyramiding Guards Work:** Two intermediate signals were correctly killed by `FLIP_ORCHESTRATION` preventing catastrophic over-exposure.
3. **Execution Desync:** Zero of the mathematically proven SL breaches were executed by the local position manager. The position FSM is structurally losing sync with exchange trigger states.

---

## SECTION 7 — ROOT CAUSES
1. **Strategy Logic Issues:** Fading ultra-low volatility breakouts (`bb_width < 0.01`) is a fundamental error. The strategy misclassifies squeeze expansions as mean-reverting deviations.
2. **Execution / Infrastructure Issues:** Brackets submitted as `STOP_MARKET` and `TAKE_PROFIT_MARKET` to Testnet are not routing back fill events. The `watchdog` relies on `TTL_EXPIRED_3600s` to clean up heavily submerged positions, resulting in unbounded risk profiles in live execution.

---

## SECTION 8 — FINAL VERDICT
The `mean_reversion` strategy correctly follows its programmed rules, but its **quant logic is critically flawed during regime transitions**, repeatedly shorting into volatility expansions. 

Furthermore, the **underlying exit execution infrastructure is broken**. The failure to process explicit Stop Loss triggers poses an absolute catastrophic risk to portfolio capital. The immediate priority must be fixing the `bracket_manager` and websocket sync for `STOP_MARKET` orders, followed by adding a `min_bb_width` threshold filter to the strategy to prevent knife-catching.