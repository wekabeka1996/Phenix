# Binance Market Data WebSocket Migration Blueprint

## 1. Problem Statement
Current implementation relies on REST polling for market data:
- `GET /fapi/v1/ticker/bookTicker`
- `GET /fapi/v1/trades`
- `GET /fapi/v1/klines`

**Risks:**
- **Rate Limits**: Scaling to 10+ symbols increases risk of hitting 429s.
- **Latency**: Polling interval (e.g., 1s or 5s) is too slow for high-frequency features.
- **Staleness**: Data is always slightly outdated compared to a push-based stream.

## 2. Scope
- **Domains**: `market_data`
- **Components**:
    - `MarketDataConnector`
    - `WebSocketAggregator` (or equivalent layer)
    - Internal event bus / DTOs for book/trades.

## 3. Design Goals
- **Separation**: Keep MarketWS separate from UserWS (different connections).
- **Compatibility**: Minimal changes to downstream consumers (same DTOs/events).
- **Config-driven**: Controlled via feature flag `use_ws_market_data`.
- **Simplicity**: Basic reconnect logic, no complex state machine in Phase 0.

## 4. Endpoint / Streams
- **Base URL**: `wss://fstream.binance.com/stream?streams=...`
- **Streams**:
    - `<symbol>@bookTicker`
    - `<symbol>@aggTrade`
- **Mapping**:
    - `bookTicker` -> Internal `EVT:BOOK_TICKER_UPDATE`
    - `aggTrade` -> Internal `EVT:TRADE_TICK_UPDATE` / TFI-input

## 5. Internal Contract
The WebSocket client will normalize incoming JSON into existing DTOs.

**bookTicker Payload:**
```json
{
  "u":400900217, // order book updateId
  "s":"BNBUSDT", // symbol
  "b":"25.35190", // best bid price
  "B":"31.21000", // best bid qty
  "a":"25.36520", // best ask price
  "A":"40.66000", // best ask qty
  "T":1560925692318, // transaction time
  "E":1560925692321  // event time
}
```
**Mapped to:** `BookTicker` (bid_price, bid_qty, ask_price, ask_qty, timestamp).

**aggTrade Payload:**
```json
{
  "e": "aggTrade",
  "E": 1560925692321, // Event time
  "s": "BNBUSDT",
  "p": "0.001",      // Price
  "q": "100",        // Quantity
  "m": true          // Is the buyer the market maker?
}
```
**Mapped to:** `TradeTick` (price, qty, is_buyer_maker, timestamp).

## 6. Failure Modes & Safety
- **WS Disconnect/Timeout**:
    - Log WARN/ERROR.
    - Backoff and reconnect.
    - **Phase 0**: No automatic fallback to REST (fail-closed behavior if WS is enabled but down).
    - **Future**: Hybrid mode or auto-fallback.

## 7. Rollout Plan
- **Phase 0 (Current)**: Blueprint, Feature Flag, Skeleton Implementation, Tests.
- **Phase 1**: Enable flag on Testnet for 1-2 symbols.
- **Phase 2**: Scale to full watchlist.
