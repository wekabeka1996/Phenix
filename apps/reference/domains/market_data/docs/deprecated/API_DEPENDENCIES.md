# Market Data API Dependencies

## Overview
This domain acts as the bridge between the **External World** (Binance) and the **Internal World** (Event Bus). It manages complex dependency chains ranging from HTTP/WebSocket I/O to internal IPC mechanisms.

---

## 1. External API Dependencies (Binance)

### Binance Futures WebSocket
-   **URL:** `wss://fstream.binance.com/ws`
-   **Role:** Primary Data Source (Low Latency).
-   **Streams:**
    -   `!bookTicker`: Real-time BBO (Best Bid Offer). High frequency.
    -   `aggTrade`: Real-time trade executions. Used for TFI features.
-   **Reliability:** Subject to 24h disconnection (Force Reconnect Required).

### Binance REST API
-   **URL:** `https://fapi.binance.com`
-   **Role:** Fallback / Snapshot.
-   **Endpoints:**
    -   `GET /fapi/v1/ticker/bookTicker`: Snapshot for initialization.
    -   `GET /fapi/v1/klines`: Historical data for Delta calc/Backfill.
-   **Rate Limits:** 2400 weight/minute. Strict adherence required.

---

## 2. Library Dependencies (Internal & Python)

### Core Stack
-   **`aiohttp`**: Main Async HTTP/WebSocket client used by `worker.py`.
-   **`orjson`**: High-performance JSON parser (Critical for throughput).
-   **`multiprocessing`**: Standard library used for Process/Queue isolation.

### Legacy Conflict (Forensic Finding)
The codebase currently contains **duplicate functionality** due to legacy modules:
-   **`websockets`**: An alternative WS library used by the "Legacy" `market_ws_client.py`.
-   **`aiohttp`**: Used by the modern "Proxy" `worker.py`.

**Risk:** Bloated dependencies.
**Recommendation:** Remove `websockets` dependency once Legacy Connector is deleted.

---

## 3. Internal Component Integration

### vFoundation Framework
-   **FSM Core**: The domain emits events directly into the FSM via `emit_event()`.
-   **Configuration**: Depends on `AuroraConfig` (Pydantic models) for type-safe setup.

### Downstream Consumers
1.  **Feature Engineering**:
    -   Dependency: Strict. Cannot calculate `volatility` or `regime` without `EVT:MARKET_TICK`.
2.  **Execution**:
    -   Dependency: Critical. Will NOT trade if `market_data` is stale or outputting empty events.

---

## 4. Data Schemas

### Incoming (External)
```json
{
  "e": "bookTicker",
  "u": 400900217,
  "s": "BTCUSDT",
  "b": "42000.00",
  "B": "1.500",
  "a": "42001.00",
  "A": "2.400",
  "T": 1703123456789,
  "E": 1703123456790
}
```

### Outgoing (Internal)
Normalized to a flat dictionary structure before emission. See `EVENTS.md` for exact contracts.
