# Binance Endpoints Usage Map

**Status:** Active
**Last Updated:** 2025-11-26
**Source of Truth:** This document maps all *actual* Binance REST and WebSocket API usages in the Phenix/Aurora codebase.

## Overview

This project interacts with Binance Futures (USDM) via:
1.  **REST API**: For order execution, account snapshots, and polling market data (hybrid mode).
2.  **WebSocket (User Data)**: For real-time order updates and position changes.
3.  **WebSocket (Market Data)**: *Currently simulated via high-frequency REST polling in `MarketDataConnector`, feeding into `WebSocketAggregator`.*

## REST Endpoints

| Method | Path | Module(s) | Domain | Triggered by (Events / DEC / CMD) | Payload Summary | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **POST** | `/fapi/v1/algoOrder` | `binance_execution_adapter.py` | `execution_position` | `DEC:PLACE_BRACKETS`<br>`DEC:PLACE_SLTP` | `symbol`, `side`, `type`, `quantity`, `reduceOnly`, `stopPrice` | Feature-flagged Algo Service endpoint for conditional orders. |
| **POST** | `/fapi/v1/order` | `binance_execution_adapter.py`<br>`binance_adapter.py` | `execution_position` | `DEC:OPEN`<br>`DEC:PLACE_ORDER`<br>`DEC:CLOSE` | `symbol`, `side`, `type`, `quantity`, `price`, `stopPrice`, `reduceOnly`, `timeInForce`, `newClientOrderId` | Primary execution endpoint. Handles MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET. |
| **DELETE** | `/fapi/v1/order` | `binance_execution_adapter.py`<br>`binance_adapter.py` | `execution_position` | `DEC:CANCEL_ORDER` | `symbol`, `orderId`, `origClientOrderId` | Idempotent cancellation logic handles -2011 (Unknown Order) as success. |
| **GET** | `/fapi/v1/order` | `binance_execution_adapter.py`<br>`binance_adapter.py` | `execution_position` | `DEC:CANCEL_ORDER` (pre-check)<br>Idempotency checks | `symbol`, `orderId`, `origClientOrderId` | Used to verify order status before cancellation or to recover from -4116 (Duplicate ClientOrderId). |
| **GET** | `/fapi/v1/openOrders` | `binance_execution_adapter.py`<br>`binance_adapter.py` | `execution_position` | `CMD:SYNC_ORDERS`<br>Startup checks | `symbol` (optional) | Returns list of active orders. Used for reconciliation and "cancel all" fallbacks. |
| **GET** | `/fapi/v2/positionRisk` | `binance_execution_adapter.py`<br>`binance_adapter.py`<br>`account_connector.py` | `execution_position`<br>`account_balance`<br>`position_tracking` | `EVT:PORTFOLIO_STATE_UPDATED`<br>Periodic Polling | `symbol` (optional) | **Critical**: Source of truth for open positions. Used by `AccountConnector` to emit `EVT:ACCOUNT_UPDATE_RECEIVED`. |
| **GET** | `/fapi/v2/balance` | `binance_adapter.py`<br>`account_connector.py` | `account_balance` | Periodic Polling | None | Fetches wallet balance, crossWalletBalance, and unrealizedPnL for all assets. |
| **GET** | `/fapi/v1/premiumIndex` | `binance_execution_adapter.py`<br>`binance_adapter.py` | `execution_position` | `DEC:OPEN` (Guard checks) | `symbol` | Fetches **Mark Price**. Used for `PERCENT_PRICE` filter validation and `MIN_NOTIONAL` checks. |
| **GET** | `/fapi/v1/ticker/bookTicker` | `binance_adapter.py`<br>`market_data_connector.py` | `market_data` | Periodic Polling (Market Data) | `symbol` | Fetches Best Bid/Ask Price & Qty. Feeds `WebSocketAggregator` to calculate OBI (Order Book Imbalance). |
| **GET** | `/fapi/v1/trades` | `binance_adapter.py`<br>`market_data_connector.py` | `market_data` | Periodic Polling (Market Data) | `symbol`, `limit` | Fetches recent trades. Feeds `WebSocketAggregator` to calculate TFI (Trade Flow Imbalance). |
| **GET** | `/fapi/v1/klines` | `binance_adapter.py`<br>`market_data_connector.py` | `market_data` | Periodic Polling (Market Data) | `symbol`, `interval`, `limit` | Used for `delta_price` feature calculation. |
| **GET** | `/fapi/v1/ticker/price` | `binance_adapter.py` | `execution_position` | Fallback logic | `symbol` | Fallback for "Last Price" if Mark Price is unavailable. |
| **GET** | `/fapi/v1/exchangeInfo` | `binance_adapter.py` | `execution_position` | Startup / Lazy Load | `symbol` | Fetches filters (`LOT_SIZE`, `PRICE_FILTER`, `MIN_NOTIONAL`) for local validation. |
| **GET** | `/fapi/v1/time` | `binance_execution_adapter.py`<br>`binance_adapter.py` | `execution_position` | Time Sync | None | Synchronizes local time with server to prevent `-1021 Timestamp for this request is outside of the recvWindow`. |
| **POST** | `/fapi/v1/listenKey` | `binance_execution_adapter.py` | `execution_position` | Startup (WS Connection) | None | Generates `listenKey` for User Data Stream. |
| **PUT** | `/fapi/v1/listenKey` | `binance_execution_adapter.py` | `execution_position` | Periodic Keep-alive | `listenKey` | Extends validity of `listenKey` (valid for 60 mins). |

## WebSocket Endpoints (User Data)

| WS URL | Streams | Module | Domain | Used for |
| :--- | :--- | :--- | :--- | :--- |
| `wss://fstream.binance.com/ws/{listenKey}`<br>(or `stream.binancefuture.com` for Testnet) | **User Data Stream** | `binance_execution_adapter.py` | `execution_position`<br>`account_balance` | Real-time updates for Orders and Account Balance/Positions. |

### User Data Events Processing

| Raw Event | Internal Event | Logic / Description |
| :--- | :--- | :--- |
| `ORDER_TRADE_UPDATE` | `EVT:TRADE_EXECUTED`<br>`EVT:ORDER_STATE_CHANGED` | Detects fills (`FILLED`, `PARTIALLY_FILLED`) and status changes (`CANCELED`, `REJECTED`). Updates `OrderIndex` and triggers lifecycle metrics. |
| `ACCOUNT_UPDATE` | `EVT:ACCOUNT_UPDATE_RECEIVED` | Real-time position and balance updates. Pushed to `AccountConnector` / `PositionTracking` to update portfolio state. |

## WebSocket Endpoints (Market Data)

| WS URL | Streams | Module | Domain | Used for |
| :--- | :--- | :--- | :--- | :--- |
| `wss://fstream.binance.com/stream?streams=...` | `<symbol>@bookTicker`, `<symbol>@aggTrade` | `market_ws_client.py` | `market_data` | `OBI`, `TFI`, low-latency pricing. |

## Open Questions / TODO

### Algo Service migration (conditional orders)

*   **Status**: **PARTIAL** (AURORA_EXEC_ALGO_SERVICE_MIGRATION)
*   **Description**: The current implementation uses `/fapi/v1/order` for all order types. However, for full support of advanced conditional orders (STOP, TAKE_PROFIT, TRAILING_STOP) as per latest Binance documentation, the Algo Service endpoints should be used.
*   **Implemented (Feature Flagged)**:
    *   `POST /fapi/v1/algoOrder`
*   **Missing Endpoints (Tech Debt)**:
    *   `DELETE /fapi/v1/algoOrder`
    *   `DELETE /fapi/v1/algoOpenOrders`
    *   `GET /fapi/v1/openAlgoOrders`
    *   `GET /fapi/v1/allAlgoOrders`
*   **Impact**: Potential limitations in handling complex conditional orders or future deprecation of legacy behavior on the main order endpoint.

### Other
1.  **Market Data WS**: Migration blueprint and skeleton implemented (`MARKET_WS_MIGRATION.md`). Feature flag `use_ws_market_data` available.
2.  **Legacy Adapters**: `apps/reference/adapters/sdk_adapter_binance.py` appears unused or legacy. Confirm and deprecate if needed.
3.  **Testnet URLs**: Ensure `binance_execution_adapter.py` and `binance_adapter.py` consistently use the same base URL logic (currently both handle testnet/live switching).
