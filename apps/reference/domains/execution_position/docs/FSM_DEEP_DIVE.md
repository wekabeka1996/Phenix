# FSM.py Deep Dive Analysis (4440 lines)

## 🏗️ Architecture: Orchestrator & Wrapper
`fsm.py` (ExecPosFSM) is the central nervous system of the `execution_position` domain. It acts as a wrapper that routes commands to three specific sub-flows on a per-symbol basis:
- `fsm_open.py`: Logic for entering positions.
- `fsm_manage.py`: Logic for TP/SL and bracket maintenance.
- `fsm_close.py`: Logic for exit orchestration.

## 🛡️ Critical Safety Mechanisms

### 1. Fail-Closed Principles (NRR Strategy)
- **Zero-Invention Configuration**: Instrument specifications (`tick_size`, `step_size`, `min_qty`, `min_notional`) MUST be in the YAML SSOT. If a symbol is missing, the order is rejected immediately.
- **Explicit Constraints**: No silent defaults for `order_type`, `tif`, or `price`. MARKET orders with `tif` are rejected. LIMIT orders without `valid_for_ms` are rejected.
- **Quantization**: All prices and quantities are strictly normalized via `qty_normalizer.py` and `quantize_stop_price` before sending to the exchange.

### 2. Race Condition Mitigation
- **Manual Close Gate**: When `CMD:CLOSE` is received, a `_closing_position` flag is set immediately. This blocks the `ManageFlowFSM` from placing or updating any automated brackets that might compete with the manual exit.
- **Supersede Queue (EP-01.3)**: if a new `OPEN` decision arrives while an old entry is still being canceled, the new order is queued until cancellation is confirmed (or a 5s timeout expires), preventing overlapping entries. Also triggers cancellations on **Regime Change**.
- **Pre-flight Check (PHASE A3)**: Before placing SL/TP brackets, the FSM performs a REST-based position check with exponential backoff. This ensures brackets are only placed when a position is confirmed, even in high-latency REST/Polling environments.

### 3. Error Recovery & Self-Healing
- **TP-2021 Backoff & Fallback**:
  - `Retry 1`: Widening TP by 20bps + 200ms backoff.
  - `Retry 2`: Widening TP by 50bps + 400ms backoff.
  - `Final Fallback`: If still failing, places a `LIMIT reduceOnly` order at the adjusted price to ensure the exit exists.
- **Startup Reconciliation (TASK47c-P3)**: Pulls all positions and orders from the exchange on restart. Runs `LeverageBootstrapper` to sync margin mode and leverage. `OrderGuardian` re-links parent-child relationships using `CorrelationStore`.
- **Shadow Check**: Every 10 requests, the FSM verifies that the internal portfolio notional matches the exchange-reported notional within a 1% tolerance.

### 4. Deterministic Infrastructure (DET-BT-13)
- Uses a `Clock` abstraction instead of system time to ensure 100% reproducible backtests.
- **Quiet Hours**: Enforces configurable trading blackouts (e.g., `["22:00-06:00"]` wrapping midnight) where no new positions can be opened.

## ⚙️ Core Logic Flows

### Trade Intent Pipeline (The Bridge)
Handles `TRADE_INTENT_PROPOSED` from DecisionMaking. It performs strict validation and routes to `CMD:OPEN` or `CMD:CLOSE`. It is the SSOT for the Strategy-Execution contract.

### Intent Injection (PHASE A2)
The FSM captures `stop_price` and `target_price` from the original `DEC:OPEN` decision and caches them. They are only "injected" into the `ManageFlowFSM` when the `FILL` event for the entry order arrives.

### Deferred Brackets (PHASE 4)
For **LIMIT** entries, brackets are not placed immediately. They are stored in `_pending_brackets` and persisted to WAL. They are placed only upon the entry fill, ensuring we don't have hanging brackets for unfilled limits.

## 🚨 Circuit Breakers
- **Execution Breaker**: 2+ adapter errors in 10 minutes leads to a 10min block.
- **Timeout Breaker**: 3+ watchdog timeouts in 5 minutes leads to a 5min block.

## 📊 Observability
- Emits structured events like `EXPOSURE_SUMMARY_UPDATED`, `EXPOSURE_MISMATCH`, and `DEC_CLOSE_COMPLETED`.
- Detailed forensic logging via `AuroraLogAdapter` and `order_logger`.

---
**Verdict**: `fsm.py` is a highly complex, battle-hardened component designed for "Unattended High-Reliability Trading". Its primary mission is to ensure that for every entry, there is a guaranteed (and correctly sized) exit, regardless of exchange errors or network lag.
