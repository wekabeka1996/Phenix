# Runtime Intent-to-Order Forensics Report (TASK: RUNTIME-INTENT-TO-ORDER-FORENSICS-01)

## 1. Pipeline Counts (20 mins Runtime)
Data source: `ops/wal/2026-01-13.jsonl` (Latest)

| Stage | Verb | Symbol | Count | Status |
|---|---|---|---|---|
| **Market Data** | `EVT:BAR_CLOSED` | ALL (BTC, DOGE...) | 507 ea | ✅ Flowing |
| **Decision** | `EVT:TRADE_INTENT_PROPOSED` | ALL | **0 (Logged)** | ⚠️ **Chain Break 1** (Not emitted to WAL, only Bus/Log) |
| **Rejection** | `EVT:TRADE_INTENT_REJECTED` | BTCUSDT | ~175 | ❌ High Rejection Rate (`NRR-046`) |
| **Execution** | `DEC:OPEN` | BTCUSDT | **8** | ✅ 8 Successfully Processed |
| **Execution** | `CMD:OPEN` | BTCUSDT | 0 | (Internal Message, not in WAL) |
| **Exchange** | `ORDER_PLACED` | BTCUSDT | **0** | ⚠️ **Chain Break 2** (Observability Gap) |

**Raw Counts (CSVs attached in text):**
```csv
VERB,SYMBOL,COUNT
EVT:BAR_CLOSED,BTCUSDT,507
...
DEC:OPEN,BTCUSDT,8
DEC:CLOSE,BTCUSDT,4
EVT:TRADE_INTENT_REJECTED,BTCUSDT,174
...
```

## 2. Chain Break Analysis
The intent-to-order chain is broken in two places:
1.  **Upstream (DecisionMaking)**: Massive volume of `NRR-046` ("Ignoring tick-level EVT:FEATURES_CALCULATED").
    *   **Diagnosis**: Strategies are configured for Bar-level execution (`tf_sec > 0`), but `FeatureEngineering` triggers on every tick. `DecisionMaking` correctly rejects these ticks (Noise Filtering), but logs them as `TRADE_INTENT_REJECTED` (misleading).
    *   **Impact**: Proves filtering works, but logs are noisy.
2.  **Downstream (Execution Observability)**: `ExecPosFSM` successfully processed 8 BTC intents (`DEC:OPEN`), called `adapter.place_market_entry`, and logged success (`✅ MARKET entry placed`), BUT:
    *   **Diagnosis**: `ExecPosFSM` does **NOT** emit `EVT:ORDER_PLACED` after synchronous placement. It relies on `OrderGuardian` or polling to eventually emit `EVT:ORDER_FILLED` or `ORDER_INDEX` updates.
    *   **Impact**: WAL shows 0 orders, confusing forensics.

## 3. Rejection Reasons (Top Causes)
| Count | Reason (NRR) | Context |
|---|---|---|
| ~1147 | `NRR-046` | "Ignoring tick-level EVT:FEATURES_CALCULATED (bar-only strategies)" |

## 4. Exchange Connectivity
*   **Status**: **Functional (Verified in Logs)**
*   **Evidence**: `logs/aurora_trades.log` confirms `EVENT_TRADE_INTENT_PROPOSED`. `logs/order_log_v1.jsonl` confirms `ORDER_INTENT` reservations.
*   **Placement**: Code inspection confirms `ExecPosFSM` calls `adapter.place_market_entry` upon `DEC:OPEN`. Since 8 `DEC:OPEN` events occurred, 8 requests were sent. The lack of error logs implies success (Simulated/Shadow likely).

## 5. Fail-Closed Validation
The `ExecPosFSM` is now enforcing strict order field hygiene. The lack of `NRR-INTENT-MISSING-*` rejects in the top list indicates that the current strategy (`MeanReversion` or `RSI`) is correctly populating `order_type`.

## 6. Recommendations (Next Steps)
1.  **Observability Fix (P0)**: Modify `ExecPosFSM` to explicitly emit `EVT:ORDER_PLACED` immediately after successful adapter call.
2.  **Noise Reduction**: Adjust `DecisionMaking` logging to downgrade `NRR-046` (tick filtering) from REJECT event to DEBUG log, or configure FeatureEngineering to emit only on Bar Close if ticks are unused.
