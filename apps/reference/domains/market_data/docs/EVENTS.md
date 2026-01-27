# Market Data Events

## Overview

The `market_data` domain is primarily an **Event Producer**. It ingests raw data from the outside world and emits normalized, time-ordered events to the internal Event Bus. It does **not** consume business events from other domains, acting strictly as a Source.

**Event Types:**
1.  **`EVT:MARKET_TICK_RECEIVED`**: High-frequency snapshot of market state.
2.  **`EVT:BAR_CLOSED`**: Aggregated OHLCV candlesticks (Strategic Signal).
3.  **`EVT:ANCHOR_UPDATED`**: Macro-market context updates.

---

## Event Specifications

### 1. EVT:MARKET_TICK_RECEIVED

**Purpose:** Real-time market data emission with calculated features (OBI, TFI) for trading decisions.
**Source:** `MarketDataProxy` (via `worker.py`).
**Frequency:** Burst (up to 1000/sec) or Batched (1/sec), configurable.

**Payload Schema:**
```json
{
  "event_type": "EVT:MARKET_TICK_RECEIVED",
  "timestamp": 1703123456789,
  "payload": {
    "ts": 1703123456789,        // Exchange Timestamp (ms) - SSOT
    "symbol": "SOLUSDT",
    "price": "123.45",          // Last Traded Price
    "bid": "123.40",            // Best Bid
    "ask": "123.50",            // Best Ask
    "mid": "123.45",            // (Bid + Ask) / 2
    "bid_size": "150.5",        // Qty at Best Bid
    "ask_size": "200.3",        // Qty at Best Ask
    "buy_volume": "45",         // Aggressive Buy Volume (Windowed)
    "sell_volume": "32",        // Aggressive Sell Volume (Windowed)
    "data_type": "market_tick_aggregated",
    "data_source": "websocket_live",
    "debug_info": "BID/ASK: 150/200, Trades: BUY=45 SELL=32"
  },
  "metadata": {
    "domain": "market_data",
    "component": "MarketDataProxy"
  }
}
```

**Consumers:**
-   **Feature Engineering**: Accumulates raw ticks for volatility calculations.
-   **Execution**: Validates "Last Look" price before submitting orders.
-   **Risk**: Monitors real-time mark prices for PnL estimation.

---

### 2. EVT:BAR_CLOSED

**Purpose:** The canonical signal that a time bucket (candle) is finalized. This is the **Primary Trigger** for most strategy logic (e.g. Mean Reversion).
**Source:** `BarAggregator`.
**Frequency:** Determined by Configured Timeframes (e.g., 1m, 5m).

**Payload Schema:**
```json
{
  "event_type": "EVT:BAR_CLOSED",
  "timestamp": 1703123460000,
  "payload": {
    "symbol": "BTCUSDT",
    "timeframe_sec": 60,        // Bar Duration (1 minute)
    "bar": {
        "t_start": 1703123400000,
        "open": 42000.0,
        "high": 42100.0,
        "low": 41950.0,
        "close": 42050.0,
        "volume": 15.4,
        "trades": 120,
        "closed": true
    },
    "gap_bars_skipped": 0       // >0 indicates data loss/gap
  }
}
```

**Consumers:**
-   **Feature Engineering**: Calculates technical indicators (RSI, Bollinger Bands) on the closed bar.
-   **Decision Making**: Evaluates entry/exit signals based on the finalized bar features.

**Constraints:**
-   Only emitted when a tick *crosses* the time boundary.
-   Strictly monotonic time ordering.

---

### 3. EVT:ANCHOR_UPDATED

**Purpose:** Updates the price of a macro "Anchor" asset (e.g., Bitcoin) to synchronize correlation models across different trading pairs.
**Source:** `MarketDataProxy`.

**Payload Schema:**
```json
{
  "event_type": "EVT:ANCHOR_UPDATED",
  "timestamp": 1703123456789,
  "payload": {
    "anchor": "BTCUSDT",
    "price": 42000.50,
    "ts_ms": 1703123456789
  }
}
```

**Consumers:**
-   **Feature Engineering**: Updates the Global Correlation Matrix.
-   **Regime Detector**: Checks for broad market trend shifts (e.g., "BTC Crashing").

---

## Event Processing Model

### Synchronous vs Asynchronous
-   **Emission**: Events are emitted asynchronously (`fire_and_forget`) to avoid blocking the Proxy orchestrator.
-   **Buffering**: The `BarAggregator` buffers ticks internally until the bar closes.
-   **Error Handling**: If a consumer fails, the event is lost (Real-time data preference: Freshness > Reliability).

### Flow Architecture
```
[Binance WS] 
    | (Raw JSON)
    v
[Worker Process]
    | (Batched Dicts)
    v
[IPC Queue]
    |
    v
[MarketDataProxy] ---> Emits EVT:MARKET_TICK_RECEIVED
    |
    v
[BarAggregator] -----> Emits EVT:BAR_CLOSED (on boundary)
```
