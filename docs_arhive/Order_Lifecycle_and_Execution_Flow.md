#                                                                                             Aurora

**            :** 1.0
**        :** 2025-10-26

## 1.                            

                                                                                                                                                                            .                                                                 , **                     **                                 , **                                                                            **, **                              **                       ,      **                            **                                                      .

## 2.          1:                                   (Signal Generation)

                                                                       ,                                                                                                            .

**                     :**
-                                                          (           `MarketDataConnector`):
    -   `bookTicker`:                                                          (bid)                     (ask)                       .
    -   `trade`:                                                   ,                                        .

**             (                `FeatureEngineering`):**
1.  **                     OBI (Order Book Imbalance):**
    -   **              :** `(bid_volume - ask_volume) / (bid_volume + ask_volume)`
    -   **                          :**                                                                   .                                                                                ,                                                        .
2.  **                     TFI (Trade Flow Imbalance):**
    -   **            :**                                     ,                                               ,                                                        (                                 )                                  (                                 ).
    -   **                          :**                                                .                                                                                             ,                                                         .
3.  **                     `delta_price`:**
    -   **            :**                                                                    .
    -   **                          :**                                                                                     .
4.  **                     `absorption`:**
    -   **            :**             ,                               "                "                                                                                   .
    -   **                          :**                                                                                                                                   ,                                 .

**          :**
-              `EVT:FEATURES_CALCULATED`                                                   (features)                                                      (        ., ETHUSDT).

## 3.          2:                                   (Decision Making)

                                                                                                                                                     .

**                      (                `DecisionMaking`):**
1.  `EVT:FEATURES_CALCULATED` (   `FeatureEngineering`)
2.  `EVT:RISK_ASSESSMENT_COMPLETED` (   `RiskManagement`)
3.  `EVT:PORTFOLIO_STATE_UPDATED` (   `PositionTracking`)
4.  `EVT:REGIME_DETECTED` (   `RegimeDetector`)

**            :**
1.  **                     `signal_score`:**
    -   **            :**                                                 (OBI, TFI, absorption).          (`signal_weights`)                                              (`trading.yaml`).
    -   **              :** `signal_score = (obi * 0.4) + (tfi * 0.4) + (absorption * 0.2)`
2.  **                                      (`side`):**
    -            `signal_score > signal_threshold` (        ., 0.2)     `side = "buy"` (LONG).
    -            `signal_score < -signal_threshold`     `side = "sell"` (SHORT).
    -                    **                                           (                                   ).**
3.  **                                                   (Regime Filter):**
    -                                                                                  (        ., `TREND_UP`, `TREND_DOWN`).
    -   **            :**                                                               .                   ,                 `TREND_UP`              `side = "sell"`                                  .
4.  **                                                   (Position Sizing):**
    -   **                           :**                                                **                     **,                                                                           (`kelly_alpha`, `kelly_conservative_factor`).
    -   **                   (Caps):**                                                   USD    **                      **                                     :
        1.              ,                                         .
        2.                                            (`trade_cvar95_max_bps`                                             ).
        3.                                    (`liquidity_based_cap_usd`).
    -   **                                                          :**                                             USD                   `min_position_size_usd`,                                    .
5.  **                                                          (`qty`):**
    -   **              :** `qty_raw = final_pos_size_usd / current_price`
    -   **                    :** `qty`                          **        **                                             ,                  `step_size`                        (        ., 0.001        BTC).                                               `Decimal.quantize`,                                                        .
    -   **                  :**                                          `qty`                          ,                                    .
6.  **                                                     (`Trade Intent`):**
    -                                                      ,                                   '       `TradeIntent`.

**          :**
-              `EVT:TRADE_INTENT_PROPOSED`                          ,                                      `trade_intent.schema.json`.

## 4.          3:                                 (Order Execution)

                                                                                                                                            .

**                     :**
-              `EVT:TRADE_INTENT_PROPOSED`.

**            :**
1.  **                           (Bridge):**
    -                    `on_trade_intent_proposed`    `main.py`                                             `EVT:TRADE_INTENT_PROPOSED`                                        `CMD:OPEN`.
    -                           (            ,               ,                   ,         )                     .
2.  **                  `ExecPosFSM`:**
    -                  `CMD:OPEN`                         `OpenFlowFSM`                                               .
    -   **                              :**                            `idempotent_key`.                                                                                                    ,                                  .
    -   **           (Guards):**                                                           :
        -   **Cooldown:**                                                                      ?
        -   **Min Notional:**                                                         (`qty * price`)                                                 ?
3.  **                                                   :**
    -                                              , `OpenFlowFSM`                `DEC:OPEN`.
    -                                                             **                ** (`BinanceExecutionAdapter`).
    -                                                                             Binance API           .

**           (                                           ):**

                                                           **                                             **                                    :

-   **                   :** `LIMIT` (                           )
    -   **         `LIMIT`?**                                                                                                                                "              " (maker fee).
    -   **         (`price`):**                                                `price_ref`    `TradeIntent`,       ,                       ,                              `price`    `features`.     ,              ,                                                    .
    -   **                   (`timeInForce`):** `GTC` (Good-Till-Cancel) -                                     ,                                                                      .

**                                                (                      `DEC:OPEN`):**
-   **                                          :**
    ```json
    {
      "op": "DEC",
      "verb": "OPEN",
      "pld": {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "qty": "0.123",
        "price": "4000.98",
        "order_type": "LIMIT",
        "tif": "GTC",
        "idempotent_key": "..."
      }
    }
    ```
-   **                Binance API (                ):**
    ```
    POST /fapi/v1/order
    {
      "symbol": "ETHUSDT",
      "side": "BUY",
      "type": "LIMIT",
      "quantity": "0.123",
      "price": "4000.98",
      "timeInForce": "GTC",
      "newClientOrderId": "..."
    }
    ```

**              :**                                                     (Stop Loss, Take Profit),                                  `ManageFlowFSM`,                                         `LIMIT` (       Take Profit)      `STOP_MARKET` (       Stop Loss)                     `reduceOnly=true`,                              ,                                                                                          ,                                  .

## 5.                 

                                                                                                                      ,                                                                     ,                                               -                                                     ,                                                                              ,                        **                           **,                                                      .                                                                                         "                           "                                           .
