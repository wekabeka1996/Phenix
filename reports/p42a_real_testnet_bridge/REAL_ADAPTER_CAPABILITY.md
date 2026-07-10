# REAL_ADAPTER_CAPABILITY — Binance Futures Testnet Integration

This document proves that the system employs a real REST exchange adapter for the Binance Futures Testnet and outlines its capability characteristics.

---

## 1. Environment & Venue Integration

- **Target Venue**: Binance Futures (USDS-M Futures).
- **Testnet Base URL**: `https://testnet.binancefuture.com`
- **Configuration Path**: `config.binance_api.testnet` properties.
- **Client Library**: REST requests are executed using the `httpx.AsyncClient` package in `BinanceAdapter._request()`.

---

## 2. API Endpoints and Mappings

| Action | HTTP Method | Endpoint | Request Details |
| :--- | :--- | :--- | :--- |
| **Market Entry** | `POST` | `/fapi/v1/order` | Submits `symbol`, `side`, `type=MARKET`, and `quantity` with signed signature payload. |
| **Limit Entry** | `POST` | `/fapi/v1/order` | Submits `symbol`, `side`, `type=LIMIT`, `price`, `quantity`, and `timeInForce` (e.g. `GTC`, `GTX`). |
| **Order Cancel** | `DELETE` | `/fapi/v1/order` | Cancels orders using `symbol`, `orderId`, and signature signature payload. |
| **Query Order** | `GET` | `/fapi/v1/order` | Pulls order status by `symbol` and `clientOrderId` / `orderId`. |
| **Account Info** | `GET` | `/fapi/v2/account` | Queries balances, positions, and margin assets on testnet. |

---

## 3. Response Model Shapes

Responses are normalized at the Anti-Corruption Layer into standard classes:

```python
# REST response shape from POST /fapi/v1/order
{
    "orderId": 999888777,
    "clientOrderId": "cmd-5",
    "symbol": "XRPUSDT",
    "status": "NEW",
    "side": "BUY",
    "price": "0.5500",
    "origQty": "10",
    "executedQty": "0",
    "avgPrice": "0.0000",
    "timeInForce": "GTC",
    "type": "LIMIT",
    ...
}
```

---

## 4. Idempotency Key Routing

Idempotency is protected by mapping the unique `command_id` to the exchange parameter `newClientOrderId`. If the exchange encounters a repeat `newClientOrderId`, it rejects the request natively with `-2015` or returns the previously accepted status, preventing double-fills.
