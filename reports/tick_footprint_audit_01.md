# TICK-FOOTPRINT-AUDIT-01: Forensic Data Analysis

**Date:** 2026-01-12
**Status:** AUDIT COMPLETE
**Type:** Forensic / No Code Changes

## 1. Executive Summary
The system relies on "Ticks" (live market data updates) as the fundamental atom of information, but the **decision and execution layers are successfully decoupled** from raw ticks.
- **Ingress:** Ticks enter via Binance WebSocket streams (`aggTrade`, `bookTicker`) in `binance_ws_client.py`.
- **Distribution:** Normalized into `EVT:MARKET_TICK_RECEIVED` events by `MarketData` domain.
- **Consumption:** Ticks are directly consumed by **Feature Engineering** (calculation), **Bar Aggregator** (resampling), and **Position Tracking** (mark-to-market).
- **Execution Safety:** Crucially, `ExecutionPosition` does **not** listen to ticks. Strategies are gated by `CMD:PROCESS_STRATEGY` (Bar-driven), preventing "tick-chasing" logic in the core strategy loop, although Feature Engineering runs on a tick loop.

## 2. Tick Ingress Map

| Source Stream | Producer File:Line | Normalization | Output Event |
| :--- | :--- | :--- | :--- |
| `wss://fstream.binance.com` | `binance_ws_client.py:196` | `BinanceWSClient` | Raw WS Message |
| `bookTicker`, `aggTrade` | `market_data_connector.py` | `_normalize_tick` | `Tick` (Dict) |
| Internal FSM | `market_data_connector.py:426` | `emit("EVT:MARKET_TICK_RECEIVED")` | `EVT:MARKET_TICK_RECEIVED` |

**Evidence:**
- `config/aurora/trading.yaml:6`: `ws_url: wss://fstream.binance.com`
- `apps/reference/main.py:1657`: `fsm.listen("EVT:MARKET_TICK_RECEIVED", bar_aggregator.on_market_tick)`

## 3. Consumers Map (by Domain)

| Domain | Consumer File:Line | Consumes Tick? | Purpose | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **Feature Engineering** | `feature_engineering.py:155` | **YES** | Calculate features (`price`, `obi`, `volatility`) on every update. | **Medium**: FE runs at tick speed. Strategies must explicitly filter/gate this stream. |
| **Market Data** | `bar_aggregator.py:22` | **YES** | Accumulate High/Low/Volume for Bar formatting. | **Low**: Standard resampling. |
| **Position Tracking** | `position_tracking.py:73` | **YES** | Mark-to-market (MtM) valuation of open positions. | **Low**: Observability only. |
| **Execution** | `execution_position` | **NO** | N/A (Uses `CMD:OPEN` or timer loops). | **None**: Decoupled. |
| **Decision Making** | `mean_reversion_handler.py:1002` | NO (Stub) | Explicitly deprecated (`_on_market_tick` is pass). | **None**: Correctly migrated to Bar-driven. |

## 4. Logging & Observability Map

| What Logged | Path | Format | Rate | Who Writes |
| :--- | :--- | :--- | :--- | :--- |
| **Raw Ticks** | *None Found* | N/A | N/A | No active raw tick logger (likely for performance). |
| **Features** | `logs/features/*.log` | JSON Lines | Tick/Update | `FeatureEngineering` |
| **Tick Counts** | `logs/aurora_market_data.log` | Text (Info) | Periodic | `MarketDataWorker` |
| **Executions** | `logs/order_log_v1.jsonl` | JSONL | Event | `OrderGuardian`/Execution |

## 5. Residual Tick-Driven Loops

While `ExecutionPosition` is not event-driven by ticks, it contains **sub-second timer loops** that act as high-frequency consumers:

1.  **Order Chasing / Retry Loops:**
    - `apps/reference/domains/execution_position/fsm.py:1171`: `await asyncio.sleep(0.5)`
    - `apps/reference/domains/execution_position/fsm.py:2556`: `await asyncio.sleep(0.2)`
    - *Observation:* These loops poll for order status or retry logic. They operate independently of bar closing times.

2.  **Feature Engineering Loop:**
    - `apps/reference/domains/feature_engineering/feature_engineering.py:451`: `on_market_tick` -> `emit("EVT:FEATURES_CALCULATED")`
    - *Observation:* This runs at full market speed (~10-100Hz on crypto). Downstream consumers (Strategies) MUST have gates (like `tf_sec` checks) to avoid running logic 100 times/sec.

## 6. Risk Notes

1.  **Implicit Tick Dependency in FE:**
    `FeatureEngineering` calculates complex features like `depth_imbalance` on every tick. If a strategy were to listen to `EVT:FEATURES_CALCULATED` *without* checking `tf_sec` or `bar_closed`, it would revert to High-Frequency Trading (HFT) behavior, which might be unintended.
    - *Mitigation:* `MeanReversionHandler` explicitly checks `if tf_sec != self.timeframe_sec: return`.

2.  **Warmup Gating:**
    Since ticks drive the Warmup state in FE, a lack of ticks (e.g. broken WS) means `full_ready` never becomes True, acting as a natural (and correct) kill-switch.

3.  **Conflict Potential:**
    The `timer` loops in Execution (0.2s) vs `bar` loops in Strategy (60s+). This is generally safe, as Execution handles the "micro-management" of filling an order, while Strategy handles the "macro-decision" of placing it.
