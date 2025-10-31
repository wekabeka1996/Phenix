#  ó ≤ ñ Ç      æ    É ¥ ∏ Ç  ≥ ñ ±   ∏ ¥ Ω æ ≥ æ    µ ∂ ∏ º É

##  † µ ∑ é º µ

 ê É ¥ ∏ Ç    ñ ¥ Ç ≤ µ   ¥ ∏ ≤,  â æ    ∏   Ç µ º    Ω   ª   à Ç æ ≤   Ω    ¥ ª è    æ ± æ Ç ∏  ≤  ≥ ñ ±   ∏ ¥ Ω æ º É    µ ∂ ∏ º ñ (`hybrid_live_data_testnet_exec`),  è ∫  ∑   ∑ Ω   á µ Ω æ  ≤ `system.yaml`.  ¶ µ π    µ ∂ ∏ º  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î    ∏ Ω ∫ æ ≤ ñ  ¥   Ω ñ  ≤    µ   ª å Ω æ º É  á     ñ  ¥ ª è      ∏ π Ω è Ç Ç è    ñ à µ Ω å  Ç    É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫   º ∏,    ª µ  Ω         ≤ ª è î  ≤   ñ  Ç æ   ≥ æ ≤ ñ  æ   µ     Ü ñ ó  ¥ æ  Ç µ   Ç æ ≤ æ ó  º µ   µ ∂ ñ Binance.

 û   Ω æ ≤ Ω    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  ∫ µ   É î Ç å   è  Ñ   π ª   º ∏ `system.yaml`  Ç   `trading.yaml`,  è ∫ ñ  ∑   ≤   Ω Ç   ∂ É é Ç å  æ ± ª ñ ∫ æ ≤ ñ  ¥   Ω ñ  Ç    ñ Ω à ñ    µ ∫   µ Ç ∏  ∑ ñ  ∑ º ñ Ω Ω ∏ Ö    µ   µ ¥ æ ≤ ∏ â  ,  ≤ ∏ ∑ Ω   á µ Ω ∏ Ö  É  Ñ   π ª ñ `.env`.

 ë É ª    ≤ ∏ è ≤ ª µ Ω      æ Ç µ Ω Ü ñ π Ω    Ω µ ≤ ñ ¥   æ ≤ ñ ¥ Ω ñ   Ç å:  ¥ æ º µ Ω `risk_management`        Ü é î  ≤    µ ∂ ∏ º ñ `live`,  â æ  º æ ∂ µ      ∏ ∑ ≤ µ   Ç ∏  ¥ æ    æ ∑     Ö É Ω ∫ ñ ≤    ∏ ∑ ∏ ∫ ñ ≤  Ω    æ   Ω æ ≤ ñ    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö  É    µ   ª å Ω æ º É  á     ñ,  Ç æ ¥ ñ  è ∫  Ñ   ∫ Ç ∏ á Ω ñ    æ ∑ ∏ Ü ñ ó  Ç   PnL  ≥ µ Ω µ   É é Ç å   è  ≤  Ç µ   Ç æ ≤ ñ π  º µ   µ ∂ ñ.

##  † µ ∑ É ª å Ç   Ç ∏

### 1.  ö æ Ω Ñ ñ ≥ É     Ü ñ è    µ   µ ¥ æ ≤ ∏ â  

*   ** §   π ª `.env.example`:**
    *   `USE_TESTNET=true` ( ∑    ∑   º æ ≤ á É ≤   Ω Ω è º)
    *    í ∏ ∑ Ω   á   î  ∑ º ñ Ω Ω ñ  ¥ ª è  ∫ ª é á ñ ≤ API  è ∫  ¥ ª è  Ç µ   Ç æ ≤ æ ó,  Ç   ∫  ñ  ¥ ª è  æ   Ω æ ≤ Ω æ ó  º µ   µ ∂ ñ.
*   **`vfoundation/config.py`:**
    *    ó   ≤   Ω Ç   ∂ É î  ∫ æ Ω Ñ ñ ≥ É     Ü ñ é  ∑ ñ  ∑ º ñ Ω Ω ∏ Ö    µ   µ ¥ æ ≤ ∏ â  .
    *    ö ª é á æ ≤ ∏ π          º µ Ç  : `EXECUTION_MODE` (`dry_run`, `paper`, `live`).
*   **`apps/reference/config_loader.py`:**
    *    ó   ≤   Ω Ç   ∂ É î `.env`  ∑    ¥ æ   æ º æ ≥ æ é `dotenv`.
    *    ß ∏ Ç   î  Ç    ∑ ª ∏ ≤   î `system.yaml`  Ç   `trading.yaml`.
    *    † æ ∑   ñ ∑ Ω   î  ∑ º ñ Ω Ω ñ    µ   µ ¥ æ ≤ ∏ â    É  Ñ æ   º   Ç ñ `${VAR_NAME}`.
    *    ¶ µ Ω Ç     ª å Ω ∏ π    µ   µ º ∏ ∫   á: `trading_mode`.

### 2.  ê Ω   ª ñ ∑  ≥ ñ ±   ∏ ¥ Ω æ ó      æ ≤ æ ¥ ∫ ∏

*   **`config/aurora/system.yaml`:**
    *   `trading_mode: "hybrid_live_data_testnet_exec"`
*   **`config/aurora/trading.yaml`:**
    *   ** † ∏ Ω ∫ æ ≤ ñ  ¥   Ω ñ (live):**
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
    *   ** í ∏ ∫ æ Ω   Ω Ω è (testnet):**
        ```yaml
        domain_configuration:
          execution_position:
            trading_mode: "testnet"
        ```
    *   ** ö ñ Ω Ü µ ≤ ñ  Ç æ á ∫ ∏:**
        ```yaml
        binance_api:
          live:
            rest_url: "${BINANCE_FUTURES_BASE_URL_LIVE}"
            ws_url: "wss://fstream.binance.com"
          testnet:
            rest_url: "https://testnet.binancefuture.com"
            ws_url: "wss://stream.testnet.binancefuture.com"
        ```

### 3.  ü æ Ç µ Ω Ü ñ π Ω ñ      æ ± ª µ º ∏

*   ** ù µ ≤ ñ ¥   æ ≤ ñ ¥ Ω ñ   Ç å  É    æ ∑     Ö É Ω ∫   Ö    ∏ ∑ ∏ ∫ ñ ≤:**  î æ º µ Ω `risk_management`        Ü é î  ≤    µ ∂ ∏ º ñ `live`,  â æ  º æ ∂ µ      ∏ ∑ ≤ µ   Ç ∏  ¥ æ  Ç æ ≥ æ,  â æ    æ ∑     Ö É Ω ∫ ∏    ∏ ∑ ∏ ∫ ñ ≤ ( Ω       ∏ ∫ ª   ¥,  ¥ µ Ω Ω ñ  ª ñ º ñ Ç ∏  ∑ ± ∏ Ç ∫ ñ ≤)  ±   ∑ É ≤   Ç ∏ º É Ç å   è  Ω      ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö  É    µ   ª å Ω æ º É  á     ñ,     Ω µ  Ω    Ñ   ∫ Ç ∏ á Ω ∏ Ö    æ ∑ ∏ Ü ñ è Ö  Ç   PnL  É  Ç µ   Ç æ ≤ ñ π  º µ   µ ∂ ñ.  ¶ µ  º æ ∂ µ      ∏ ∑ ≤ µ   Ç ∏  ¥ æ  Ω µ æ á ñ ∫ É ≤   Ω æ ó    æ ≤ µ ¥ ñ Ω ∫ ∏,  ∫ æ ª ∏    ∏   Ç µ º    ≤ ≤   ∂   Ç ∏ º µ,  â æ  ≤ æ Ω    ∑   ∑ Ω   î  ∑ ± ∏ Ç ∫ ñ ≤ (   ± æ  æ Ç   ∏ º É î      ∏ ± É Ç æ ∫)  Ω    æ   Ω æ ≤ ñ  ¥   Ω ∏ Ö  É    µ   ª å Ω æ º É  á     ñ,  Ç æ ¥ ñ  è ∫  É  Ç µ   Ç æ ≤ ñ π  º µ   µ ∂ ñ  Ω ñ á æ ≥ æ  Ω µ  ≤ ñ ¥ ± É ≤   î Ç å   è.

##  ö   Ω ¥ ∏ ¥   Ç ∏  Ω      µ   à æ     ∏ á ∏ Ω É

 ù    æ   Ω æ ≤ ñ    Ω   ª ñ ∑ É  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó,  Ω   π ± ñ ª å à  ñ º æ ≤ ñ   Ω æ é      ∏ á ∏ Ω æ é  Ç æ ≥ æ,  â æ  æ   ¥ µ   ∏  Ω µ  ≤ ñ ¥ ∫   ∏ ≤   é Ç å   è,  î:

1.  ** ù µ       ≤ ∏ ª å Ω ñ    ± æ  ≤ ñ ¥   É Ç Ω ñ  ∫ ª é á ñ API  ¥ ª è  Ç µ   Ç æ ≤ æ ó  º µ   µ ∂ ñ:**  §   π ª `.env`    æ ≤ ∏ Ω µ Ω  º ñ   Ç ∏ Ç ∏        ≤ ∏ ª å Ω ñ `BINANCE_TESTNET_API_KEY`  Ç   `BINANCE_TESTNET_API_SECRET`.
2.  ** ü   æ ± ª µ º ∏  ∑    ñ ¥ ∫ ª é á µ Ω Ω è º  ¥ æ  Ç µ   Ç æ ≤ æ ó  º µ   µ ∂ ñ:**  ú æ ∂ ª ∏ ≤ ñ      æ ± ª µ º ∏  ∑  º µ   µ ∂ µ é    ± æ  ¥ æ   Ç É   Ω ñ   Ç é  Ç µ   Ç æ ≤ æ ó  º µ   µ ∂ ñ Binance.
3.  ** õ æ ≥ ñ ∫    É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫   º ∏:**  ù   ≤ ñ Ç å  è ∫ â æ  ≤   µ  Ω   ª   à Ç æ ≤   Ω æ        ≤ ∏ ª å Ω æ,  ª æ ≥ ñ ∫    É       ≤ ª ñ Ω Ω è    ∏ ∑ ∏ ∫   º ∏ ( è ∫          Ü é î  ≤    µ ∂ ∏ º ñ `live`)  º æ ∂ µ  ∑     æ ± ñ ≥   Ç ∏  ≤ ñ ¥ ∫   ∏ Ç Ç é    æ ∑ ∏ Ü ñ π  Ω    æ   Ω æ ≤ ñ    ∏ Ω ∫ æ ≤ ∏ Ö  É º æ ≤  É    µ   ª å Ω æ º É  á     ñ.

##  ù     Ç É   Ω ñ  ∫   æ ∫ ∏

1.  ** ü µ   µ ≤ ñ   ∏ Ç ∏  Ñ   π ª `.env`:**  ü µ   µ ∫ æ Ω   π Ç µ   è,  â æ `BINANCE_TESTNET_API_KEY`  Ç   `BINANCE_TESTNET_API_SECRET`        ≤ ∏ ª å Ω æ  ≤   Ç   Ω æ ≤ ª µ Ω ñ.
2.  ** ü µ   µ ≤ ñ   ∏ Ç ∏    ñ ¥ ∫ ª é á µ Ω Ω è:**  ü µ   µ ≤ ñ   Ç µ,  á ∏  î  ¥ æ   Ç É    ¥ æ `https://testnet.binancefuture.com`.
3.  ** ü   æ   Ω   ª ñ ∑ É ≤   Ç ∏  ª æ ≥ ñ ∫ É    ∏ ∑ ∏ ∫ ñ ≤:**  £ ≤   ∂ Ω æ  ≤ ∏ ≤ á ñ Ç å,  è ∫  ¥ æ º µ Ω `risk_management`  ≤ ∑   î º æ ¥ ñ î  ∑ `execution_position`,  ∫ æ ª ∏  ≤ æ Ω ∏        Ü é é Ç å  É    ñ ∑ Ω ∏ Ö    µ ∂ ∏ º   Ö.  ú æ ∂ ª ∏ ≤ æ,  ∑ Ω   ¥ æ ± ∏ Ç å   è  Ç ∏ º á     æ ≤ æ  ≤ ∏ º ∫ Ω É Ç ∏  ¥ µ è ∫ ñ    µ   µ ≤ ñ   ∫ ∏    ∏ ∑ ∏ ∫ ñ ≤  ¥ ª è  Ω   ª   ≥ æ ¥ ∂ µ Ω Ω è.
