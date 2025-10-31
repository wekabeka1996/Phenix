#                                                             

##             

                               ,                                                                                                     (`hybrid_live_data_testnet_exec`),                            `system.yaml`.                                                                                                                                                                                    ,                                                                                                     Binance.

                                                                          `system.yaml`      `trading.yaml`,                                                                                                                                ,                                    `.env`.

                                                                             :            `risk_management`                              `live`,                                                                                                                                                         ,                                                    PnL                                                        .

##                     

### 1.                                              

*   **         `.env.example`:**
    *   `USE_TESTNET=true` (                               )
    *                                                     API                             ,                                               .
*   **`vfoundation/config.py`:**
    *                                                                                         .
    *                                    : `EXECUTION_MODE` (`dry_run`, `paper`, `live`).
*   **`apps/reference/config_loader.py`:**
    *                        `.env`                         `dotenv`.
    *                                `system.yaml`      `trading.yaml`.
    *                                                                          `${VAR_NAME}`.
    *                                            : `trading_mode`.

### 2.                                                 

*   **`config/aurora/system.yaml`:**
    *   `trading_mode: "hybrid_live_data_testnet_exec"`
*   **`config/aurora/trading.yaml`:**
    *   **                        (live):**
        ```yaml
        domain_configuration:
          market_data:
            trading_mode: "live"
          feature_engineering:
            trading_mode: "live"
          decision_making:
            trading_mode: "live"
          risk_management:
            trading_mode: "live"
        ```
    *   **                   (testnet):**
        ```yaml
        domain_configuration:
          execution_position:
            trading_mode: "testnet"
        ```
    *   **                         :**
        ```yaml
        binance_api:
          live:
            rest_url: "${BINANCE_FUTURES_BASE_URL_LIVE}"
            ws_url: "wss://fstream.binance.com"
          testnet:
            rest_url: "https://testnet.binancefuture.com"
            ws_url: "wss://stream.testnet.binancefuture.com"
        ```

### 3.                                      

*   **                                                                       :**            `risk_management`                              `live`,                                               ,                                          (                  ,                                       )                                                                                             ,                                                       PnL                                 .                                                                                  ,                                           ,                                           (                                      )                                                            ,                                                                                          .

##                                                 

                                                         ,                                                              ,                                                  ,   :

1.  **                                                          API                                     :**          `.env`                                                  `BINANCE_TESTNET_API_KEY`      `BINANCE_TESTNET_API_SECRET`.
2.  **                                                                               :**                                                                                                               Binance.
3.  **                                                  :**                                                                       ,                                                    (                                    `live`)                                                                                                                                           .

##                            

1.  **                              `.env`:**                           ,      `BINANCE_TESTNET_API_KEY`      `BINANCE_TESTNET_API_SECRET`                                          .
2.  **                                           :**                   ,                           `https://testnet.binancefuture.com`.
3.  **                                                        :**                            ,                 `risk_management`                       `execution_position`,                                                                  .               ,                                                                                                                                        .
