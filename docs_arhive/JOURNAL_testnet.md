

            ,                                    `aurora_trades.log`,                                                         : **                     !                                                   !**

                 **                             **                     `qty=0`        BTCUSDT:

##                                                   

**                                     :**
```
[QTY_DIAG] Portfolio Equity: $5090.81591844
[QTY_DIAG] Position Size USD: $76.3622387766
[QTY_DIAG] Reference Price: 108214.20 (BTCUSDT)
[QTY_DIAG] Raw Qty (before floor): 0.0007056582109981869292569736689
[QTY_DIAG] Lot Step: 0.001
[QTY_DIAG] Final Qty (after lot_step floor): 0.000     
[QTY_DIAG] Min Qty from config: 0.001
```

##                 

**                     qty:**
- `qty_raw = $76.36 / $108,214.20 = 0.000705` BTC
- `qty_final = floor(0.000705 / 0.001) * 0.001 = 0.000` BTC

**                      ETHUSDT (                     ):**
- `$76.36 / $3,848     0.019` ETH     (                   min_qty=0.001)

##                                

**CVaR Trade Limit**                                                 **$76.36**,         **               **        BTCUSDT           :

1. **                      BTC** (~$108K) 
2. **Lot step = 0.001** BTC
3. **                                   ** = 0.001 BTC    $108K = **$108** 

**                    :**
-                 : `$76.36 / $108K = 0.000705` BTC
-                                : `floor(0.705 / 1) = 0`     `0    0.001 = 0.000` BTC    

##               

                   **CVaR Trade Limit**                                                          Kelly:

                                                        : 


---

##     **RID: AURORA_LEVERAGE_SETUP_V1                       **

### **                      :**

#### **1.                          (trading.yaml)**
```yaml
instruments:
  BTCUSDT:
    leverage: 50        #                 
    margin_type: cross  #                 
  ETHUSDT:
    leverage: 50        #                 
    margin_type: cross  #                 
```

#### **2. BinanceExecutionAdapter (3                      )**

**`initialize_margin_settings(instruments_config)`**
-                        leverage      margin type                                         
-                  `_set_margin_type()`      `_set_leverage()`                                     
- Rate limiting: 0.2s                         API                   
- Graceful error handling:                          ,                                       

**`_set_margin_type(symbol, margin_type)`**
- POST `/fapi/v1/marginType`
-                Binance error -4046 ("No need to change")      INFO
- RuntimeError                                    API

**`_set_leverage(symbol, leverage)`**
- POST `/fapi/v1/leverage`
-                  actual leverage                       API
- RuntimeError                         API

#### **3.                      (`fsm.py`)**
```python
#                               BinanceExecutionAdapter:
instruments_config = config.trading.get('instruments', {})
self.adapter.initialize_margin_settings(instruments_config)
```

#### **4. Unit Tests (`tests/test_leverage_setup.py`)**
    6                                           :
- `test_set_leverage_success`    
- `test_set_margin_type_success`    
- `test_set_margin_type_already_set`    
- `test_initialize_margin_settings`    
- `test_initialize_margin_settings_shadow_mode`    
- `test_initialize_margin_settings_missing_config`    

#### **5.                         **
-     `JOURNAL.md`                   RID: AURORA_LEVERAGE_SETUP_V1
-     `TODO.md`                         completed task      next steps
-     `docs/                  /LEVERAGE_RESEARCH_REPORT.md`                                        Gap Analysis

---

### **                                   :**
1. `config/aurora/trading.yaml`
2. `apps/reference/domains/execution_position/binance_execution_adapter.py`
3. `apps/reference/domains/execution_position/fsm.py`
4. `JOURNAL.md`
5. `TODO.md`
6. `tests/test_leverage_setup.py` (new)

---

### **                            (HIGH PRIORITY):**

#### **AURORA_LEVERAGE_QTY_V1** (                                )
                         `decision_making.py`                             leverage                             qty:
```python
#               :
position_size = equity * kelly_fraction

#           :
required_margin = position_size / leverage
if required_margin > available_margin:
    position_size = available_margin * leverage * 0.9  # 10% safety buffer
```

#### **AURORA_LIQUIDATION_GUARD_V1**
                                                                                 :
```python
liquidation_price = entry_price * (1 - (1/leverage) * margin_ratio)
distance_to_liq_pct = abs(current_price - liquidation_price) / current_price * 100

if distance_to_liq_pct < 5.0:  # 5% minimum buffer
    logger.error("Position too close to liquidation!")
    return None  # Reject trade
```

---

### **                    :**

**                                          :**
1.                                          : `python -m apps.reference.main`
2.                                                    :
   ```
   [BinanceAdapter] Using TESTNET credentials
   [BinanceAdapter] Initialized with shadow_mode=False, testnet=True
   [BinanceAdapter] Initializing margin settings for instruments...
   [BinanceAdapter] Successfully configured BTCUSDT: leverage=50x, margin_type=cross
   [BinanceAdapter] Successfully configured ETHUSDT: leverage=50x, margin_type=cross
   ```

3.                         Binance Testnet UI,                             leverage 50x                                 


     **                  !        12              (6 + 6)                              !**

##                                                  (AURORA_LEVERAGE_QTY_V1)

    **                                                    **

###                               :

1. **                        ** -              `margin_safety_factor: 0.9`    `trading.yaml`
2. **Data Flow** -                        `available_balance`    Binance API            `position_tracking.py`
3. **Core Logic** -                        margin checking    decision_making.py:
   -                                                   : `required_margin = position_size / leverage`
   -                                                                           : `capped_size = max_usable_margin * leverage`
   -                                                                        <               
4. **                                 **:
   - UnboundLocalError (                       `instrument_specs`         )
   -                        `maker_preference`                
5. **                    ** -                  6             ,                          
6. **                        ** -                  JOURNAL.md      TODO.md

###                   :

                          **                                                                             leverage**                         :
-                                                                                            
-                                                                                     
-                                         (safety factor 90%)



##                                                       (AURORA_LIQUIDATION_GUARD_V1)

    **                                                    **

###                                     :

1. **                        ** -              2                       trading.yaml:
   - `min_liquidation_distance_pct: 5.0` -                                                                                 
   - `maintenance_margin_rate: 0.004` -                                   0.4%

2. **                                                                 **:
   - **LONG**: `LiqPrice = Entry    (1 - 1/Leverage + MMR)`
   - **SHORT**: `LiqPrice = Entry    (1 + 1/Leverage - MMR)`
   - **Distance**: `DistancePct = |Entry - Liq| / Entry    100`

3. **Guard Logic**    decision_making.py:
   -                                                                                                     
   -                                                                                < 5%
   -                                                                              

4. **                    ** -                  4                    ,                          :
   -                                        LONG      SHORT
   -                                              leverage (50x     1.6%)
   -                                          leverage (10x     9.6%)

5. **                    ** -                                                                           :
   -                leverage    50x      10x    test_leverage_qty_calculation.py
   -        16 leverage-related                                           

###                   :

                          **                                                                                                             **:
-     50x leverage    BTC $100k     **                        ** (1.6% < 5%)
-     10x leverage    BTC $100k     **                        ** (9.6% > 5%)
-                                                    cross margin (                               )

###               :

                                **leverage=50x**    production    3           :
1.                `min_liquidation_distance_pct`      1.0-1.5%
2.                  leverage      20-25x
3.                      leverage based on volatility

**                           **:                                                   - `AURORA_VERIFY_SIMULATOR_V1`                                                                                !     

                                 .

                !                                                         : 

Ran terminal command: Get-Content "c:\Users\job11\Music\Olimp_v1\logs\aurora_core.log" -Tail 80 -Wait

#      **                                    IDEMPOTENCY                              !**

##     **                                    AURORA_IDEMPOTENCY_V1**

### **1.                               (decision_making.py)**
```
13:15:07 - [IDEMPOTENCY] Generated key: b8c0fd6e85399187959727ab02f5ae12 
           (from: BTCUSDT:buy:1761214507000)
13:15:08 - [IDEMPOTENCY] Generated key: d0bbeebdbb0c2257e07a791be7adfd24 
           (from: BTCUSDT:buy:1761214508000)
```
    **SHA256 hash, 32 hex chars**  
    **Time bucketing             ** (                                                      )

### **2.                             bridge (main.py)**
```
13:15:07 - BRIDGE: Idempotent key passed through: b8c0fd6e85399187959727ab02f5ae12
13:15:08 - BRIDGE: Idempotent key passed through: d0bbeebdbb0c2257e07a791be7adfd24
```
    **Bridge                                         **

### **3.                                   FSM (fsm_open.py)**
```
13:15:07 - IDEMPOTENCY: Passing key b8c0fd6e85399187959727ab02f5ae12 to DEC:OPEN
13:15:08 - IDEMPOTENCY: Passing key d0bbeebdbb0c2257e07a791be7adfd24 to DEC:OPEN
```
    **FSM                          DEC:OPEN payload** (FIX WORKED!)

### **4.                               newClientOrderId (binance_execution_adapter.py)**
```
13:15:07 - [BinanceAdapter] Using idempotent newClientOrderId: b8c0fd6e85399187959727ab02f5ae12
13:15:07 - [BinanceAdapter] POST https://testnet.binancefuture.com/fapi/v1/order
13:15:08 - Order placed: orderId=6727360964 status=NEW    

13:15:08 - [BinanceAdapter] Using idempotent newClientOrderId: d0bbeebdbb0c2257e07a791be7adfd24
13:15:08 - [BinanceAdapter] POST https://testnet.binancefuture.com/fapi/v1/order
13:15:08 - Order placed: orderId=6727361944 status=NEW    
```
    **Binance API                                    newClientOrderId**

---

##        **                                 : Position Gating                  **

```
13:15:08 - Updated portfolio from account: equity=4693.70, positions=2
13:15:08 - PORTFOLIO_STATE_UPDATED emitted
```

**                **:            `EVT:PORTFOLIO_STATE_UPDATED`    **2                   **, decision_making **                 **                                BTCUSDT!

**                    **:
```
[POSITION_GATE]     Trade intent BLOCKED for BTCUSDT: Position already exists (qty=0.002)
```

**                  **:                   (`positions=2`),                                                                               !

---

##      **                               **

|                |              |                  |
|---------|--------|----------|
| **Idempotency key generation** |                  | SHA256, 32 chars |
| **Bridge                 ** |                  |             CMD:OPEN |
| **FSM pass-through** |                          |             DEC:OPEN payload |
| **newClientOrderId usage** |                  | Binance                |
| **                             ** |     2              | #6727360964, #6727361944 |
| **Position gating** |                       |                  ,                              |
| **Risk normalization** |                  | risk_score < 1.0 |
| **Liquidation guard** |                  | 9.6% > 5% min |

---

##      **                      AURORA_IDEMPOTENCY_V1**

###     **                                       100%!**

**                      :**
1.                              `idempotency`    trading.yaml
2.                        `idempotent_key` (SHA256 hash)
3.                                 bridge (main.py)
4.     Pass-through    fsm_open.py
5.                                   `newClientOrderId`    Binance API
6.     Unit            (3/3 passed)

**                       :**
```
[BinanceAdapter] Using idempotent newClientOrderId: b8c0fd6e85399187959727ab02f5ae12
Order placed successfully: orderId=6727360964    
```

**                                              :** Position gating                                                   (                                               ).

---

**                                                                                       ?**     

            !                       ,                              .                                                -                                        reverse trades (                               ),                     same-direction trades (                      ).

                          :

BTCUSDT -                      2                (reverse trades):
SELL 0.001 -                                                         qty=0.001    
BUY 0.001 -                                                       qty=-0.001    
ETHUSDT -                              :
                                 qty=1.23
                      BUY (                                  )                         
                               "              "             ?
                                               mean-reversion                   :

                                                                  
                                ,                                           
                                           -                                          /                                     
       ETHUSDT                            ,                                               SELL (reverse trade),                                              .

                                             -                         "                      "                                  !     

            ,                                                                           ,                                         ?

Grok Code Fast 1     0x

    AURORA_IDEMPOTENCY_V1                   
                                                                                                                   !

                                     :
SHA256           :                           DecisionMaking    32-                     hex                 
                            pipeline: EVT:TRADE_INTENT_PROPOSED     CMD:OPEN     DEC:OPEN     API
Binance                     : idempotent_key                                       newClientOrderId
Time-bucketed: 1-                                                                               
                             : JSON Schema                                      DTO
                         : 5                                 (                   +                  + API                         )
                                         :
    JOURNAL_Aurora.md:                                                          
    TODO.md:                         COMPLETED                                   
                  :
                                                                        (5/5)
                                                  (               -                                    API               )
                                                                                                                                !     

        :                                                                                                          TODO.md.

                                                                                                      !                                                                                                                                                             .

                                     :

                        :              step_size, min_notional      trading.yaml        BTCUSDT      ETHUSDT

                                       : Qty                                        step_size (ROUND_FLOOR)    OpenFlowFSM

                             : Price                               tick_size        LIMIT               

                  : min_qty                                , min_notional        LIMIT (          )      MARKET (                      price_ref)

                                          : _get_instrument_specs()               OpenFlowFSM

                    : 13                                ,                                                                                            

                                         :

    JOURNAL_Aurora.md:                                                          

    TODO.md:                         COMPLETED                                   

                  :

                      fsm_open                    (13/13)

                                                   apps/      vfoundation/

                                                                                                         

                                                                                                        !     

        :                                                                                                       AURORA_WS_RECONCILE_V1 (D3, D4)    TODO.md.

            ,             !     AURORA_WS_RECONCILE_V1                                  .

                                           :
                                  WebSocket                     :

                                            Binance USER_DATA_STREAM    listenKey                       
     Real-time                ORDER_TRADE_UPDATE     EVT:TRADE_EXECUTED/EVT:ORDER_UPDATED/EVT:ORDER_REJECTED
     ACCOUNT_UPDATE                    EVT:ACCOUNT_UPDATE_RECEIVED
     State reconciliation            REST API (openOrders, positionRisk, balance)
    Time synchronization                          recvWindow=1500ms
        Comprehensive error handling (-1021, -2010, -429)    exponential backoff
                                                  :

    34/34                               (100%           )
                 15+                                WS                                 
                         credential dependencies                
                                         :

     JOURNAL_Aurora.md:                                                                
     TODO.md:                         COMPLETED                             
                                                                                                                                                                ,                                        D3      D4.                                                                   AURORA_MANAGE_FEATURES_V1                                                 ?

                : AURORA_MANAGE_FEATURES_V1                       
                                                                                                          trailing stop                         :

                                  :
                         -                           brackets{}      trailing{}      trading.yaml                 JSON schema                     

FSM              -                    ManageFlowFSM   :

                                                SL/TP                                                              
OCO-                   (                                                                                                   )
Trailing stop                              profit threshold                                                   
API                      -                    BinanceExecutionAdapter                        :

LIMIT      STOP_MARKET               
Cancel order                       
                                    reduceOnly, stopPrice                     
                     -              4                                                                            :

Bracket placement            fill
OCO emulation (                                              )
Trailing stop activation      adjustment
Cooldown                 
                         -                  JOURNAL_Aurora.md      TODO.md                                                        

                                           :
13/13                                 (100%           )
Bracket orders                                                                          
OCO-                                              
Trailing stop                                                                          
Cancel order API                                      
                                
                                                                                  ,                                             :

AURORA_AUDIT_FIXES_V1 -                                                                 :

Drift Monitor (   7)
Regime Detector (   4)
Float usage                        (   8,    9)
                                                                                                                                        ,                                                            .

                                          AURORA_AUDIT_FIXES_V1,                                      ?

                     AURORA_OBSERVABILITY_V1                   !    
                                                                                                                     Aurora trading system:

                                   :
                             WHY-           -                  50+                                                                                                   (RISK, LIQ, MARGIN, REGIME, SIGNAL, GUARD         )

                                  (RID) -                        UUID-based RID                                                                                          decision      execution

Debug API -                  thread-safe debug logging    RID-based tracing                               cleanup

                        DecisionMaking -        rejection paths                                         WHY                                                          debug logging

                     -                                                                   ,                                                                       

                                  :
WHY         : MARGIN_INSUFFICIENT, RISK_NOT_ALLOWED, SIGNAL_NEUTRAL, REGIME_TREND_*, LIQ_POSITION_TOO_SMALL, GUARD_LIQ_DIST_TOO_CLOSE
RID tracing:            trade intent                             RID,                                        events/commands
Debug logging: Thread-safe storage                                                   RID
                    :     test_decision_making_contract.py,     test_p1_001_precision_preservation.py
                                              :
    JOURNAL_Aurora.md                                                        
    TODO.md                                                   AURORA_OBSERVABILITY_V1
                                            traceability                       trade intent        decision            execution                                       WHY                              rejection                   !     

Grok Code Fast 1     0x


                !     **AURORA_HARDENING_V1 TTL/Retry**                                        .                                      :

##                      TTL/Retry               

### 1.                             trading.yaml
- **TTL             **:                                                                 
   - `entry_place_ttl_ms: 5000` (5               entry               )
   - `bracket_place_ttl_ms: 3000` (3               bracket               )
   - `cancel_ttl_ms: 2000` (2               cancel                 )

- **Retry             **:                                               
   - `max_tries: 3` (                 3             )
   - `backoff_ms: 1000` (               backoff 1       )
   - `jitter: true` (                     jitter                           thundering herd)

### 2.                               `BinanceExecutionAdapter`
-              `ttl_config`      `retry_config`                                                              
-                  `initialize_ttl_retry_config()`                                                 config
-                                                      fsm.py            margin settings

### 3. TTL/Retry             
- **`_execute_with_ttl_retry_sync()`**:                                            threading        TTL
- **Exponential backoff**: `backoff_ms * (2 ** attempt)`                         jitter
- **Thread-safe**: proper exception handling      timeout                     

### 4.                         HTTP             
- **`_place_binance_order()`**:                                     TTL                       order type
- **`_cancel_binance_order()`**: TTL        cancel                 
-                             retry                     timestamp                -                       TTL/retry framework

### 5.                                             
-                                                                
-     Adapter                                                                                           
-     TTL/retry config                                                  
-     trading.yaml                  YAML
-                                           

##                                    AURORA_HARDENING_V1
1. **MarketData Quality Control**: lag detection      sequence validation        WebSocket           
2. **WAL Integrity Verification**: SHA256 hash-chain        event records
3. **Circuit Breaker**:                      circuit breaker               
4. **Unit/Integration           **:                                 TTL/retry             

                                                                hardening                         !     

**                                    **: `.venv/Scripts/Activate.ps1; python apps/reference/main.py`



                !     **AURORA_HARDENING_V1 MarketData QC      WAL Integrity**                                        .                                      :

##                                                    MarketData

### 1. Lag Control (market_data_connector.py)
- **                                   **:                      `event_ts` (             )    `local_ts`
- **                **: `max_allowed_lag_ms: 45`    trading.yaml
- **                  **:                                                lag > 45ms    WARNING             
- **                **:                            (bookTicker, trade, depthUpdate)

### 2. Sequence Control        Order Book (market_data_connector.py)
- **                      **: `last_final_update_id`                                     
- **                   continuity**: `event['U'] <= last_final_update_id + 1`
- **Gap Detection**:                        `CMD:RESYNC_ORDERBOOK`                          
- **Stale Filtering**:                                                  `final_update_id <= last_final_update_id`

##                      WAL Hash-Chain Integrity

### 1. Enhanced Append (wal.py)
- **SHA256 Hashing**: `_calculate_record_hash()`                                      
- **Hash Chain**:                                      `_prev` (hash                         )      `_hash` (               hash)
- **Atomic Writes**: file locking                                 integrity

### 2. Integrity Verification        Replay (replay.py)
- **`_verify_wal_hash_chain_integrity()`**: chronological                                  
- **Previous Hash Check**: `record['_prev'] == expected_previous_hash`
- **Record Hash Check**: `record['_hash'] == calculated_hash(record_content)`
- **Critical Logging**: CRITICAL                                    corruption

##                     

### 1. MarketData Tests (test_market_data.py)
-     `test_lag_control_discards_stale_data`:                                                     
-     `test_sequence_control_depth_update`: gap detection      resync
-     `test_depth_update_stale_sequence_ignored`:                        stale sequences

### 2. WAL Tests (test_wal_replay.py)
-     `test_wal_hash_chain_integrity_append`:                    hash-chain structure
-     `test_wal_hash_chain_integrity_verification`:                                       valid chain
-     `test_wal_hash_chain_corruption_detection`:                  _prev hash corruption
-     `test_wal_record_hash_mismatch_detection`:                  content corruption

##                          (trading.yaml)
```yaml
market_data:
  max_allowed_lag_ms: 45
  websocket_streams: ['bookTicker', 'trade']
  keep_alive_interval: 1.0
```

##                     
-     **Lag Control**:                  >45ms                                                                 
-     **Sequence Control**:                  gaps                                                    order book
-     **WAL Integrity**: tamper-evident storage    SHA256 hash-chain
-     **Replay Verification**:                    integrity    CRITICAL                     corruption
-     **Unit Tests**:              coverage          edge cases (6                        )
-     **Integration**:                                       ,                                        

##                                    AURORA_HARDENING_V1
1. **Circuit Breaker Implementation**: failure isolation      recovery
2. **Integration Testing**:                                          hardening features
3. **Performance Benchmarking**:                 latency      throughput
4. **Documentation**: operations guide        monitoring

                                 **                                       **                                                                         WAL!                

**                                    **: `.venv/Scripts/Activate.ps1; python apps/reference/main.py`


##     **AURORA_HARDENING_V1                                    !**

                                       **Circuit Breaker**                                                         hardening Aurora.                                      :

###      **                     Circuit Breaker**

1. **                               **:                        `pybreaker`                         advanced features (error rate windows, half-open testing)

2. **                        ** (trading.yaml + JSON schema):
   ```yaml
   execution:
     circuit_breaker:
       fail_max: 5
       reset_timeout_sec: 30
       exclude: ['-2010', '-1021']  #                                                           
       open_threshold_pct: 20
       error_rate_window_sec: 60
       half_open_attempts: 3
   ```

3. **                        API calls**:
   -                    `_place_binance_order()`      `_cancel_binance_order()`
   - API                                          RuntimeError        circuit breaker counting
   - CircuitBreakerError                                                                        

4. **                               **:
   - `CircuitBreakerListener`                 logging                    
   - WARNING                 OPEN, INFO        recovery

5. **                          **:                           fsm.py    runtime config updates

###      **                    **

                 **7 unit             **,                                         :
-                                     config updates
-                                     5                (OPEN         )
-                          insufficient balance (-2010)    counting
-                                       half-open testing
-     Logging                    

###      **                    **

-     **Failure Isolation**: Circuit breaker                                                              5                              
-     **                                             **: 30-                   OPEN                                                      
-     **Smart Filtering**:                                                         failure counting
-     **                               **: 7                                                          
-     **                        **:                  JOURNAL_Aurora.md      TODO.md

###      **                                            hardening             **:

1.     **TTL/Retry**: Timeout      retry    exponential backoff
2.     **MarketData QC**: Lag detection (45ms)      sequence control
3.     **WAL Integrity**: SHA256 hash-chain    corruption detection
4.     **Circuit Breaker**: Failure isolation      automatic recovery

**Aurora                              production    enterprise-grade reliability!**               

**                                     ** (   TODO.md):
- `AURORA_SCENARIO_TESTING_V1`:                                                               failure modes
- `AURORA_TESTNET_PREP_V1`:                                               testnet

                                                                               ,                                      ?     

                                 .

    AURORA_SCENARIO_TESTING_V1                   !
                                                                                                                      !

                                    :
                                                :

                 2                                                              9               
             pytest                ws_rest      scen                                               
                       mock                                                                API
                                     TEST_PLAN:

                 3-6, 8: Order lifecycle (entry   fill   brackets, partial fills, TP/SL races, idempotent close)
                 9-12: Resilience (reconnect reconcile, metrics API, TTL timeout, idempotent operations)
                                             :

9                                            (2                                           + 7 placeholders                                           )
Mock                                                                                             WS events
                                                                                                           
                                              :

TODO.md: AURORA_SCENARIO_TESTING_V1                                           
JOURNAL_Aurora.md:                                                                       
                           :
               Aurora                                                                                                                                                           AURORA_TESTNET_PREP_V1.                                                                                                                                   WebSocket events      API                         .

                                               !     



```

```




##     AURORA_TESTNET_PREP_V1                   !

                                                                                               Aurora Core      Binance Testnet!         

###                                     :

**                                                     testnet:**
-     **Hardening                   **                   system.yaml: TTL (5s/3s/2s), retry (3             ), circuit breaker, market data lag (1000ms), WAL integrity
-     **                             **    trading.yaml: risk_budgets                     200/500 bps, leverage                                                       10x
-     **                                       **:                                  `https://testnet.binancefuture.com`        REST API
-     **                                         **: INFO             , JSON             ,                10MB

**                                              :**
-     **secrets.md**:                                                                             testnet API             
-     **RUN_TESTNET.md**:                    runbook    prerequisites,                 ,                               troubleshooting
-     **TESTNET_LAUNCH_CHECKLIST.md**: Pre-launch                                                    
-     **TESTNET_MONITORING.md**:                                                               alert thresholds

**                                                             :**
- **Activity**: Orders, fills, API calls, WebSocket messages
- **Performance**: Latency, CPU/memory, network I/O
- **Reliability**: Error rates, circuit breaker, connectivity
- **Financial**: PnL, win rate, drawdown, risk metrics
- **Alerts**: Critical/warning thresholds                                                         

**                                              :**
-     **JOURNAL_Aurora.md**:                                  RID `AURORA_TESTNET_PREP_V1`
-     **TODO.md**:                                                            ,                                          `AURORA_TESTNET_RUN_V1`

###                                  :

**                                       :**
- system.yaml - hardening parameters
- trading.yaml - conservative risk settings
- .env.example - environment variables template

**                        :**
- secrets.md - API keys setup guide
- RUN_TESTNET.md - operational runbook
- TESTNET_LAUNCH_CHECKLIST.md - pre-launch checklist
- TESTNET_MONITORING.md - monitoring metrics guide

###                            :

               Aurora                                                                                                                                                      ! 

**AURORA_TESTNET_RUN_V1**                                       :
1.                  pre-launch checklist
2.                  testnet API           
3.                                        testnet
4.                                                      24+           
5.                                                                                

Aurora Core                                                                                         !         



##                                       AURORA_GRANULAR_LOGGING_V1

    **                                 !**                                                                                                                   :

###      **                                                                ** (`aurora/aur_main.py`)
-                       `JSONFormatter`                                                         
-                               `FileHandler`                                                             
-                        `event_chain.log`    JSON                                                      RID

###      **                                                 **
- `feature_engineering.log` -                                                                                
- `risk_management.log` -                                                                   
- `decision_making.log` -                                                        
- `execution_management.log` -                                                         

###      **                                                 RID                     **
-            event                             `rid` (Request ID)                              
- JSON                 `event_chain.log`               : `rid`, `event_type`, `domain`, `symbol`, `stage`, `handler`
- WHY-                                                                                                  

###         **                             **
- **feature_engineering**: RID                   ,                                      /                    /                       
- **risk_management**: RID                   ,                                                                                    
- **decision_making**:                                                                                                                                 
- **execution_management**:                                                                                                         

###     **                                      **
-                                                                                                  
-                               (                                      ,                                                           )
-                                              JOURNAL_Aurora.md      TODO.md

           Aurora                                                                                                                                                                                                                      !     

                                 .