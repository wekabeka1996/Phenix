#                                                                                          

##             

                               ,                                                                                       ,                                                                                                                            **testnet**                                                                     .

**                                 :**                                                              (              , PnL,               )                     `risk_management`               `position_tracking`.                       , `position_tracking`                                                                   `account_observer`,                                                                                  **testnet**,          `trading_mode`                             `hybrid_live_data_testnet_exec`.

                   ,      **                                      (            ,                 )                                       testnet**,                                                                                                .

##                     

### 1.                                                       

1.  **`AccountObserver`**:
    *                                   `trading_mode`.
    *                               `hybrid_live_data_testnet_exec`         `"live"`,                                        **testnet** API.
    *                                            (`get_my_trades`).
    *                                                                       `EVT:TRADE_EXECUTED`.

2.  **`PositionTracking`**:
    *                             `EVT:TRADE_EXECUTED`.
    *                                                testnet.
    *                                                                               PnL.
    *                             `EVT:PORTFOLIO_STATE_UPDATED`                                                      .

3.  **`RiskManagement`**:
    *                             `EVT:PORTFOLIO_STATE_UPDATED`.
    *                                           ,                                                testnet.
    *                                                                                                                                  .

### 2.                                      

*   **`config/aurora/system.yaml`**:                      `trading_mode: "hybrid_live_data_testnet_exec"`.
*   **`config/aurora/trading.yaml`**:                                                    : `market_data`                              `live`,    `execution_position`                     `testnet`.
*   **`apps/reference/domains/account_observer/account_observer.py`**:                                                (live/testnet)                                                `trading_mode`,                                                                                                                    (testnet).

### 3.                                     

*   **                                 :**                                                                               . `RiskManagement`                                                                         `AccountObserver`,                                                                   .                                                    `AccountObserver`,                                                                                                .
*   **                                         :**                                                                                                                                .

##                                                           

                                            **C)                                       (`explicit override`)**.

                                                                                                  ,                   ,    `trading.yaml`:

```yaml
risk_management:
  data_sources:
    market_data: "live"  #                                               
    portfolio_state: "testnet" #           ,                            
```

                                                                        ,                                                             .

##                       (                                                  )

                                             C,                                                                       :

1.  **`apps/reference/config_loader.py`**:
    *   **        :**                                                                         `risk_management.data_sources`.
    *   **                     diff:**                                                                                                     .

2.  **`apps/reference/domains/position_tracking/position_tracking.py`**:
    *   **        :**                                      ,                                                                                                                                                                                    .       ,                      ,                         ,                                                              ,                                             `AccountObserver`.
    *   **                     diff:**               ,                                     ,                                                                             .

3.  **`apps/reference/domains/account_observer/account_observer.py`**:
    *   **        :**                            ,                                                                                                              (`live`        `testnet`),                                                         `trading_mode`.
    *   **                     diff:**                                      ,                                               `environment`                                                                                         `python-binance`.

4.  **`apps/reference/main.py` (                                                     )**:
    *   **        :**                                                                                                           `AccountObserver` (live        testnet)                            ,      `PositionTracking`                                                        .
    *   **                     diff:**                                                              '                                                                            ,                                    .
