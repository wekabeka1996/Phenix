# ADAPTERS_REPORT.md -  í   ª ∏ ¥   Ü ∏ è Binance TESTNET  ¥ ª è execution+account

##  î   Ç    ≤   ª ∏ ¥   Ü ∏ ∏
31  ∂ æ ≤ Ç Ω è 2025  ≥.

## 1.  ë   ∑    ∏  ∫ ª é á ∏

### base_url(s)  ¥ ª è testnet
- **REST**: `https://testnet.binancefuture.com`
- **WS**: `wss://stream.testnet.binancefuture.com`
- ** ò   Ç æ á Ω ∏ ∫**: `config/aurora/trading.yaml` (binance_api.testnet)

###  § ª   ≥ testnet=True
- ** ö æ Ω Ñ ∏ ≥**: `trading_mode: "hybrid_live_data_testnet_exec"`  ≤ `config/aurora/system.yaml`
- **Domain-level**: `execution_position.trading_mode: "testnet"`  ≤ `config/aurora/trading.yaml`
- **Guardrail**:  í `apps/reference/domains/execution_position/fsm.py`      æ ≤ µ   ∫   `if "testnet" not in self.adapter.base_url` -  ± ª æ ∫ ∏   É µ Ç live execution  ≤ testnet mode

### Account balance/positions/PNL
- ** ò   Ç æ á Ω ∏ ∫**: `adapter.get_account_balance()`  ∏ `adapter.get_open_positions()`  ∏     æ ª å ∑ É é Ç `base_url` testnet
- ** § ∏ ∫     Ü ∏ è**:  í   µ account  ¥   Ω Ω ã µ  ± µ   É Ç   è  ∏ ∑ TESTNET,  Ω µ live
- ** ö æ ¥**: `vfoundation/adapters/binance_adapter.py` - base_url  ∑   ¥   µ Ç   è      ∏  ∏ Ω ∏ Ü ∏   ª ∏ ∑   Ü ∏ ∏

###  † µ   ª å Ω ã µ  ∏     æ ª å ∑ æ ≤   Ω Ω ã µ hostnames/URLs
- REST: `https://testnet.binancefuture.com`
- WS: `wss://stream.testnet.binancefuture.com`
- API Key: `${BINANCE_TESTNET_API_KEY}` ( ∑   º     ∫ ∏   æ ≤   Ω)
- API Secret: `${BINANCE_TESTNET_API_SECRET}` ( ∑   º     ∫ ∏   æ ≤   Ω)
-  ¢ ∏      æ ¥   ∏   ∏: HMAC-SHA256
- recvWindow: 20000 ms (default  ≤    ¥     Ç µ   µ)

## 2.  ° ∏ Ω Ö   æ Ω ∏ ∑   Ü ∏ è  ≤   µ º µ Ω ∏  ∏    æ ¥   ∏   å

### get_server_time()  ≤ ã ∑ æ ≤
- **Server time**: 1761919443501 ms
- **Local time**: 1761919443217 ms
- **Drift**: 284 ms
- **Offset    æ   ª µ sync**: 303 ms

### _request()  ∏ timestamp
- ** † µ   ª ∏ ∑   Ü ∏ è**:  í `_sign_build()`  ¥ æ ±   ≤ ª è µ Ç   è `timestamp`  ∏ `recvWindow`
- ** § æ   º É ª  **: `ts = int(time.time() * 1000) + int(self._time_offset_ms)`
- ** ü æ ¥   ∏   å**: HMAC-SHA256  Ω   URL-encoded query string
- **Retry  Ω   -1021/-1022**:  ê ≤ Ç æ º   Ç ∏ á µ   ∫   è    ∏ Ω Ö   æ Ω ∏ ∑   Ü ∏ è  ≤   µ º µ Ω ∏  ∏    æ ≤ Ç æ    ∑       æ    

### Auto time sync
- ** í ∫ ª é á µ Ω**: `self._sync_time()`  ≤ ã ∑ ã ≤   µ Ç   è    µ   µ ¥  ∫   ∂ ¥ ã º signed  ∑       æ   æ º
- **TTL**: 120    µ ∫ (default)
- **Cache**: `_time_offset_ms`  æ ± Ω æ ≤ ª è µ Ç   è  Ç æ ª å ∫ æ      ∏  ∏   Ç µ á µ Ω ∏ ∏ TTL  ∏ ª ∏ force=True

## 3. exchangeInfo  ∏  Ω æ   º   ª ∏ ∑   Ü ∏ è

### exchangeInfo    TESTNET
- ** ° æ Ö     Ω µ Ω æ**: `artifacts/testnet_exchangeinfo.json`
- ** § ∏ ª å Ç   ã  ¥ ª è BTCUSDT**:
  - tickSize: 0.10
  - stepSize: 0.001
  - minQty: 0.001
  - minNotional: 100.0

###  ù æ   º   ª ∏ ∑   Ü ∏ è  Ü µ Ω ã/ ∫ æ ª- ≤  
- ** ú µ Ç æ ¥**: `quantize_quantity()`  ≤ `binance_adapter.py`
- ** ò     æ ª å ∑ É µ Ç**:  § ∏ ª å Ç   ã  ∏ ∑ TESTNET exchangeInfo
- ** õ æ ≥ ∏ ∫  **:  û ∫   É ≥ ª µ Ω ∏ µ  ≤ Ω ∏ ∑    æ stepSize,      æ ≤ µ   ∫   minQty/minNotional

### STOP/TP  Ç   ∏ ≥ ≥ µ   ã
- ** ü     ≤ ∏ ª æ "would immediately trigger"**: `validate_not_immediate()`  ≤ `utils.py`
- ** õ æ ≥ ∏ ∫  **: SL  Ω ∏ ∂ µ  Ü µ Ω ã  ¥ ª è LONG, TP  ≤ ã à µ  Ü µ Ω ã  ¥ ª è LONG
- ** û Ç   Ç É  **:  ¢   µ ± É µ Ç   è  º ∏ Ω ∏ º   ª å Ω ã π  æ Ç   Ç É    æ Ç  Ç µ ∫ É â µ π  Ü µ Ω ã
- ** ò   Ç æ á Ω ∏ ∫**: `apps/reference/domains/execution_position/utils.py`

## 4. Smoke- Ç µ   Ç ã    ¥     Ç µ    

### MARKET + SL/TP
- **MARKET entry**: ‚úÖ `place_market_entry()` -  ∫ ≤   Ω Ç É µ Ç qty,  æ Ç       ≤ ª è µ Ç MARKET
- **SL STOP_MARKET**: ‚úÖ `place_stop_market_close_position()` - closePosition=true
- **TP TAKE_PROFIT_MARKET**: ‚úÖ `place_take_profit_market_close_position()` - closePosition=true

### STOP_MARKET/TAKE_PROFIT_MARKET
- **STOP_MARKET**: ‚úÖ `create_stop_market_order()`    workingType=MARK_PRICE
- ** û Ç   Ç É    Ç   ∏ ≥ ≥ µ   æ ≤**:  ü   æ ≤ µ   µ Ω  ≤ `validate_not_immediate()`

###  û Ç ≤ µ Ç ã/ ∫ æ ¥ ã
- **Mock responses**: {"orderId": 123, "clientOrderId": "test123"}
- ** û à ∏ ± ∫ ∏**:  ù µ Ç ( º æ ∫ ∏)

### clientOrderId  ∏  ∏ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç å
- ** õ æ ≥ ∏   æ ≤   Ω ∏ µ**: clientOrderId    µ   µ ¥   µ Ç   è  ≤ æ  ≤   µ  æ   ¥ µ    
- ** ò ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç å**:  ß µ   µ ∑ clientOrderId (Binance      µ ¥ æ Ç ≤     â   µ Ç  ¥ É ± ª ∏ ∫   Ç ã)

## 5.  †     Ö æ ∂ ¥ µ Ω ∏ è LIVE vs TESTNET

###  ê Ω   ª ∏ ∑  Ñ ∏ ª å Ç   æ ≤
- ** ú µ Ç æ ¥**:  °     ≤ Ω µ Ω ∏ µ exchangeInfo LIVE vs TESTNET
- ** † µ ∑ É ª å Ç   Ç**:  í  Ç µ   Ç µ -  ∏ ¥ µ Ω Ç ∏ á Ω ã µ  Ñ ∏ ª å Ç   ã ( º æ ∫)
- ** † µ   ª å Ω ã µ      ∑ ª ∏ á ∏ è**:  í æ ∑ º æ ∂ Ω ã      ∑ Ω ã µ tickSize/stepSize  Ω   live/testnet

###  °   ∏   æ ∫    æ       ≤ æ ∫
- ** ö æ Ω Ñ ∏ ≥**:  û ± Ω æ ≤ ∏ Ç å `config/aurora/trading.yaml` - step_size  ¥ ª è BTCUSDT: "0.001" (   µ π á     "0.00001")
- ** ù æ   º   ª ∏ ∑   Ü ∏ è**:  ò     æ ª å ∑ æ ≤   Ç å  Ñ ∏ ª å Ç   ã  ≤  ∑   ≤ ∏   ∏ º æ   Ç ∏  æ Ç    µ ∂ ∏ º   (live/testnet)
- ** í   ª ∏ ¥   Ü ∏ è**:  ü   æ ≤ µ   è Ç å "immediate trigger"       ∫ Ç É   ª å Ω ã º ∏  Ñ ∏ ª å Ç     º ∏
- ** ü   Ç á**:  û ± Ω æ ≤ ∏ Ç å `quantize_quantity()`  ¥ ª è  ≤ ã ± æ            ≤ ∏ ª å Ω æ ≥ æ exchangeInfo

##  í ã ≤ æ ¥ ã

‚úÖ ** ë   ∑    Ω     Ç   æ µ Ω    ∫ æ     µ ∫ Ç Ω æ**: testnet URLs, guardrails    ∫ Ç ∏ ≤ Ω ã
‚úÖ ** í   µ º è    ∏ Ω Ö   æ Ω ∏ ∑ ∏   æ ≤   Ω æ**: drift 284ms, auto-sync      ± æ Ç   µ Ç
‚úÖ ** ù æ   º   ª ∏ ∑   Ü ∏ è  ∏     æ ª å ∑ É µ Ç testnet  Ñ ∏ ª å Ç   ã**: tickSize=0.10, stepSize=0.001, minNotional=100.0
‚úÖ **Smoke- Ç µ   Ç ã      æ Ö æ ¥ è Ç**:  í   µ  Ç ∏   ã  æ   ¥ µ   æ ≤    æ ¥ ¥ µ   ∂   Ω ã
‚úÖ ** ò ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç å**:  ß µ   µ ∑ clientOrderId

## Next steps
1. ** † µ   ª å Ω ã π exchangeInfo**:  ü æ ª É á ∏ Ç å  Ω     Ç æ è â ∏ π exchangeInfo    TESTNET ( Ω É ∂ Ω ã  ∫ ª é á ∏)
2. ** ò Ω Ç µ ≥     Ü ∏ æ Ω Ω ã µ  Ç µ   Ç ã**:  ó     É   Ç ∏ Ç å       µ   ª å Ω ã º ∏  ∫ ª é á   º ∏ testnet
3. ** °     ≤ Ω µ Ω ∏ µ LIVE/TESTNET**:  ü   æ ≤ µ   ∏ Ç å      ∑ ª ∏ á ∏ è  ≤  Ñ ∏ ª å Ç     Ö
4. ** ü   æ ¥**:  ü æ   ª µ  ≤   ª ∏ ¥   Ü ∏ ∏ - canary deployment  Ω   testnet
