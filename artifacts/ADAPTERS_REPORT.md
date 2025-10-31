# ADAPTERS_REPORT.md -                    Binance TESTNET        execution+account

##                            
31              2025   .

## 1.                       

### base_url(s)        testnet
- **REST**: `https://testnet.binancefuture.com`
- **WS**: `wss://stream.testnet.binancefuture.com`
- **                **: `config/aurora/trading.yaml` (binance_api.testnet)

###          testnet=True
- **            **: `trading_mode: "hybrid_live_data_testnet_exec"`    `config/aurora/system.yaml`
- **Domain-level**: `execution_position.trading_mode: "testnet"`    `config/aurora/trading.yaml`
- **Guardrail**:    `apps/reference/domains/execution_position/fsm.py`                  `if "testnet" not in self.adapter.base_url` -                    live execution    testnet mode

### Account balance/positions/PNL
- **                **: `adapter.get_account_balance()`    `adapter.get_open_positions()`                      `base_url` testnet
- **                **:        account                                  TESTNET,      live
- **      **: `vfoundation/adapters/binance_adapter.py` - base_url                                                   

###                                               hostnames/URLs
- REST: `https://testnet.binancefuture.com`
- WS: `wss://stream.testnet.binancefuture.com`
- API Key: `${BINANCE_TESTNET_API_KEY}` (                        )
- API Secret: `${BINANCE_TESTNET_API_SECRET}` (                        )
-                      : HMAC-SHA256
- recvWindow: 20000 ms (default                    )

## 2.                                                            

### get_server_time()           
- **Server time**: 1761919443501 ms
- **Local time**: 1761919443217 ms
- **Drift**: 284 ms
- **Offset            sync**: 303 ms

### _request()    timestamp
- **                    **:    `_sign_build()`                        `timestamp`    `recvWindow`
- **              **: `ts = int(time.time() * 1000) + int(self._time_offset_ms)`
- **              **: HMAC-SHA256      URL-encoded query string
- **Retry      -1021/-1022**:                                                                                                      

### Auto time sync
- **              **: `self._sync_time()`                                              signed                 
- **TTL**: 120        (default)
- **Cache**: `_time_offset_ms`                                                               TTL        force=True

## 3. exchangeInfo                            

### exchangeInfo    TESTNET
- **                  **: `artifacts/testnet_exchangeinfo.json`
- **                      BTCUSDT**:
  - tickSize: 0.10
  - stepSize: 0.001
  - minQty: 0.001
  - minNotional: 100.0

###                                  /      -    
- **          **: `quantize_quantity()`    `binance_adapter.py`
- **                    **:                     TESTNET exchangeInfo
- **            **:                                    stepSize,                  minQty/minNotional

### STOP/TP                 
- **               "would immediately trigger"**: `validate_not_immediate()`    `utils.py`
- **            **: SL                          LONG, TP                          LONG
- **            **:                                                                                    
- **                **: `apps/reference/domains/execution_position/utils.py`

## 4. Smoke-                           

### MARKET + SL/TP
- **MARKET entry**:     `place_market_entry()` -                  qty,                      MARKET
- **SL STOP_MARKET**:     `place_stop_market_close_position()` - closePosition=true
- **TP TAKE_PROFIT_MARKET**:     `place_take_profit_market_close_position()` - closePosition=true

### STOP_MARKET/TAKE_PROFIT_MARKET
- **STOP_MARKET**:     `create_stop_market_order()`    workingType=MARK_PRICE
- **                               **:                     `validate_not_immediate()`

###             /        
- **Mock responses**: {"orderId": 123, "clientOrderId": "test123"}
- **            **:        (        )

### clientOrderId                                  
- **                      **: clientOrderId                                              
- **                              **:            clientOrderId (Binance                                              )

## 5.                        LIVE vs TESTNET

###                              
- **          **:                    exchangeInfo LIVE vs TESTNET
- **                  **:               -                                     (      )
- **                                 **:                               tickSize/stepSize      live/testnet

###                              
- **            **:                  `config/aurora/trading.yaml` - step_size        BTCUSDT: "0.001" (             "0.00001")
- **                        **:                                                                                     (live/testnet)
- **                  **:                    "immediate trigger"                                             
- **        **:                  `quantize_quantity()`                                            exchangeInfo

##             

    **                                              **: testnet URLs, guardrails               
    **                                           **: drift 284ms, auto-sync                 
    **                                              testnet               **: tickSize=0.10, stepSize=0.001, minNotional=100.0
    **Smoke-                           **:                                                    
    **                              **:            clientOrderId

## Next steps
1. **                 exchangeInfo**:                                     exchangeInfo    TESTNET (                     )
2. **                                       **:                                                         testnet
3. **                   LIVE/TESTNET**:                                                        
4. **        **:                               - canary deployment      testnet
