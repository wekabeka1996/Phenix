## 2025-01-XX | RID: AURORA_TESTNET_PREP_V1 |                                               Binance Testnet

**WHY**:                               hardening                                                                                                                                                                       Aurora Core      Binance Futures Testnet                                                                                                                .

**      **:
1. **                                                testnet**:
   -                                        :                                  `https://testnet.binancefuture.com`        REST API
   -              hardening                               `system.yaml`: TTL (5s/3s/2s), retry (3             ), circuit breaker (5               , 30s timeout), market data lag (1000ms), WAL integrity
   -                                  `trading.yaml`: risk_budgets                     200/500 bps                                                              
   -                                          : INFO             , JSON             ,                10MB

2. **                         API             ** (`docs/secrets.md`):
   -                                                                        testnet API             
   -                                                                                     `.env`           
   -                                                     : `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`
   -                                                               troubleshooting

3. **                   Runbook** (`docs/runbook/RUN_TESTNET.md`):
   -              Prerequisites:                     , API           ,                          
   -              Starting the Daemon:                                   venv,               ,                            
   -              Monitoring:         , debug API, Binance dashboard,                              
   -              Troubleshooting:                                                             
   -              Emergency Procedures: graceful shutdown, emergency stop

4. **                                                        ** (`docs/TESTNET_MONITORING.md`):
   - Activity Metrics: orders, fills, intents, API calls
   - Performance Metrics: latency, resources, throughput
   - Reliability Metrics: error rates, circuit breaker, connectivity
   - Financial Metrics: PnL, win rate, drawdown, risk metrics
   - Alert Thresholds: critical/warning/info alerts                                           

5. **                   Pre-launch Checklist** (`docs/TESTNET_LAUNCH_CHECKLIST.md`):
   - Code & Environment: git status, dependencies, Python version
   - Configuration Files: YAML           , .env, environment variables
   - API Credentials: testnet account, keys, permissions, test funds
   - System Configuration: hardening params, risk limits, logging
   - Network & Security: connectivity, firewall, 2FA, key security
   - Risk Assessment: financial risk, emergency procedures
   - Success Criteria: startup, API connection, monitoring

6. **                   TODO**:
   - AURORA_TESTNET_PREP_V1                                           
   -                                          AURORA_TESTNET_RUN_V1

**                    **:
-                                                                                                          testnet
-     Hardening                                                                                                                 
-                                                                                  (leverage 10x, conservative risk limits)
-                                                                                                 alert'    
-     Pre-launch checklist                                                                                     
-     Runbook                                                         troubleshooting                                   
-     AURORA_TESTNET_PREP_V1                                                                                            

**                           **:
-                  pre-launch checklist
-                    Aurora      testnet                                                        
-                                          logs                  24+           
-                                                           fine-tuning                         

## 2025-01-XX | RID: AURORA_SCENARIO_TESTING_V1 |                                                            (Order Lifecycle + Resilience)

**WHY**:                               hardening                                                                           end-to-end                    order lifecycle      failure recovery mechanisms                                    testnet.

**      **:
1. **                                                                **:
   -                       pytest               : `ws_rest`        WebSocket/REST             , `scen`                                           
   -                  MockAuroraSystem                                                                            
   -                        pytest fixtures        mock               

2. **                           order lifecycle             ** (`test_order_lifecycle_scenarios.py`):
   - **                 3**: Entry     Fill     Bracket placement -                           order flow
   - **                 4**: Partial fill storm - placeholder        WS event mocking
   - **                 5**: TP fill     peer cancel - placeholder        race condition testing
   - **                 6**: SL fill during replace race - placeholder        concurrent event handling
   - **                 8**: Force market close idempotent -                                                     

3. **                           resilience             ** (`test_resilience_scenarios.py`):
   - **                 9**: Reconnect warm reconcile - placeholder        adapter restart testing
   - **                 10**: Metrics/Debug API validation - placeholder        API endpoint testing
   - **                 11**: TTL entry timeout - placeholder        timeout mechanism testing
   - **                 12**: Idempotent operations -                                         DEC:ADJUST             

4. **Mock                             **:
   - Mock adapter    place_order, close_position, adjust_position                 
   - Mock Message                                                        
   - Mock                                                   execution feedback schema

5. **                                    **:
   -     9                                            (2                         , 7 placeholder)
   -                                                                         
   -     Pytest                                                                             
   -                                                                                                                

6. **                                           **:
   - TODO.md                                                           AURORA_SCENARIO_TESTING_V1
   - JOURNAL_Aurora.md                                         

**                    **:
-                      framework                                                                              
-                                                           order lifecycle                                    
-                              placeholders                 TEST_PLAN                    (3-12)
-     Mock                                                                                             WS events
-                                                        ,                                                                     
-     AURORA_SCENARIO_TESTING_V1                                                                                            

**                           **:
-                                                         WS event simulation
-                         debug API        metrics validation
-                           AURORA_TESTNET_PREP_V1

## 2025-01-XX | RID: AURORA_OBSERVABILITY_V1 |                                                         (WHY-        ,                     )

**WHY**:                                                                                                                                               WHY-          ,                                   (RID)      debug API                                                                            .

**      **:
1. **                             WHY-          ** (`why_codes.py`):
   -                  50+                                  WHY                                                                 
   -                   : SPREAD, RISK, LIQ, MARGIN, REGIME, GUARD, SIGNAL, VALIDATION
   -              SIGNAL_NEUTRAL                                               
   -                `format_why_with_details()`                                                                               

2. **                                                                ** (`decision_making.py`):
   -                    RID (uuid4)                       trade intent
   -                          RID            event payload      command payload
   - RID                                                debug             

3. **                     WHY-                                  ** (`decision_making.py`):
   - MARGIN_INSUFFICIENT:        insufficient equity (    0)
   - RISK_NOT_ALLOWED:          risk manager                    trading
   - SIGNAL_NEUTRAL:                                 signal score
   - REGIME_TREND_UP_BLOCK_SELL/REGIME_TREND_DOWN_BLOCK_BUY:        counter-trend                   
   - LIQ_POSITION_TOO_SMALL:        insufficient position size/quantity
   - GUARD_LIQ_DIST_TOO_CLOSE:        liquidation distance guard

4. **Debug API                        ** (`debug_api.py`, `decision_making.py`):
   - `add_debug_log()`        RID-based tracing    thread-safe storage
   - `get_debug_logs_for_rid()`                                           RID
   - Debug                                           rejection      approval events
   - Thread-safe in-memory storage                             cleanup

5. **                                         **:
   -     test_decision_making_contract.py                                  
   -     test_p1_001_precision_preservation.py                                  
   -                                                          
   -     WHY                                           rejection paths

6. **                                       **:
   -                             why_codes.py      debug_api.py    apps/reference/domains/decision_making/

**                    **:
-                                    WHY                          rejection                   
-     RID tracing        decision            execution
-     Debug API        inspection system behavior      RID
-     Thread-safe debug logging    cleanup
-                                                              WHY                                                    
-                                                                                            
-     AURORA_OBSERVABILITY_V1                                                                                            

## 2025-01-XX | RID: AURORA_HARDENING_V1_TTL_RETRY |                      TTL/Retry                (               1)

**WHY**:                                                                                    TTL                       retry                     exponential backoff                                    API                 ,                  Binance Futures API.

**      **:
1. **                         TTL      Retry** (`config/aurora/trading.yaml`):
   -              `execution.ttl`                                     :
     - `entry_place_ttl_ms: 5000` (5               entry               )
     - `bracket_place_ttl_ms: 3000` (3               bracket               ) 
     - `cancel_ttl_ms: 2000` (2               cancel                 )
   -              `execution.retry`                 retry                     :
     - `max_tries: 3` (                 3             )
     - `backoff_ms: 1000` (               backoff 1       )
     - `jitter: true` (                     jitter                           thundering herd)

2. **                                                       Adapter** (`binance_execution_adapter.py`):
   -              `ttl_config`      `retry_config`                                                              
   -                  `initialize_ttl_retry_config()`                                                 config
   -                                                    `fsm.py`            margin settings

3. **                     TTL/Retry             ** (`binance_execution_adapter.py`):
   -                  `_execute_with_ttl_retry_sync()`                                        HTTP               
   -                        exponential backoff    jitter: `backoff_ms * (2 ** attempt) + random_jitter`
   - Threading-based TTL                                                                      
   -                                 TTL                                                 (entry/bracket/cancel)

4. **                        HTTP             ** (`binance_execution_adapter.py`):
   - `_place_binance_order()`:              TTL                                  order type
   - `_cancel_binance_order()`:              TTL        cancel                 
   -                             retry                     timestamp                (-1021) -                       TTL/retry
   -                                                             insufficient balance (-2010)      rate limits (-429)

5. **                                            **:
   -                              TTL                     retry attempts
   - Thread-safe                         proper exception handling
   -                                  timeout      retry                   

**                    **:
-                              TTL/retry                   trading.yaml
-     Adapter                        TTL/retry    config
-                        TTL/retry                                        exponential backoff + jitter
-                               place_order      cancel_order             
-     Thread-safe                         proper error handling
-                                                debugging timeout/retry                   
-     AURORA_HARDENING_V1_TTL_RETRY (               1)                                          

## 2025-01-XX | RID: AURORA_HARDENING_V1_MARKETDATA_WAL |                               MarketData      WAL Integrity (               2)

**WHY**:                                                                                                                                                                                             WAL                                                                                               data integrity.

**      **:
1. **MarketData Quality Control** (`market_data_connector.py`):
   - **Lag Control**:                                            event timestamp                                   
     - `max_allowed_lag_ms: 45`    trading.yaml
     -                                                lag > 45ms    WARNING             
     -                                                         : bookTicker, trade, depthUpdate
   - **Sequence Control        Order Book**:                        sequence numbers    depthUpdate
     -                      `last_final_update_id`                                     
     -                    continuity: `event['U'] <= last_final_update_id + 1`
     -                  gap'                                 `CMD:RESYNC_ORDERBOOK`                                      
     -                        stale                        (final_update_id <= last_final_update_id)

2. **WAL Hash-Chain Integrity** (`wal.py`, `replay.py`):
   - **Enhanced Append**: SHA256 hash-chain    `_prev`      `_hash`             
     - `_calculate_record_hash()`                                                    hashing
     -                                      hash                                      
     - Atomic writes    file locking        integrity
   - **Integrity Verification        Replay**:                    hash-chain                             
     - `_verify_wal_hash_chain_integrity()`        chronological                   
     -                    `record['_prev'] == expected_previous_hash`
     -                    `record['_hash'] == calculated_hash(record_content)`
     - CRITICAL                                    corruption
   - **Merkle Root**:                             integrity                   

3. **                    **:
   - **MarketData Tests** (`test_market_data.py`):
     - `test_lag_control_discards_stale_data`:                                         stale           
     - `test_sequence_control_depth_update`: gap detection      resync triggering
     - `test_depth_update_stale_sequence_ignored`:                        stale sequences
   - **WAL Tests** (`test_wal_replay.py`):
     - `test_wal_hash_chain_integrity_append`:                    hash-chain structure
     - `test_wal_hash_chain_integrity_verification`:                                       valid chain
     - `test_wal_hash_chain_corruption_detection`:                  _prev hash corruption
     - `test_wal_record_hash_mismatch_detection`:                  content corruption

4. **                        ** (`trading.yaml`):
   -              `market_data.max_allowed_lag_ms: 45`
   -              `market_data.websocket_streams: ['bookTicker', 'trade']`
   -              `market_data.keep_alive_interval: 1.0`

**                    **:
-     Lag control                                                             (>45ms)                                     
-     Sequence control                  gaps    order book updates                                                   
-     WAL hash-chain                      tamper-evident storage    SHA256 integrity
-     Replay                    hash-chain integrity    CRITICAL                     corruption
-                             unit                                      edge cases
-                                                        trading.yaml                       defaults
-     AURORA_HARDENING_V1_MARKETDATA_WAL (               2)                                          

## 2025-01-XX | RID: AURORA_HARDENING_V1_CIRCUIT_BREAKER |                      Circuit Breaker        Failure Isolation (               3)

**WHY**:                                                                                                                      API Binance                                                                 circuit breaker                                                                                .

**      **:

1. **                                                          Circuit Breaker**:
   -                `pybreaker`                                                                asyncio      advanced features
   -                        pybreaker==1.4.1            pip
   -                           BinanceExecutionAdapter      circuit_breaker               

2. **                         Circuit Breaker** (`trading.yaml`):
   ```yaml
   execution:
     circuit_breaker:
       fail_max: 5                    #                                                            
       reset_timeout_sec: 30          #           OPEN                       HALF_OPEN
       exclude:                       #                     ,                                                  
         - 'binance.error.ClientError:.*-2010'  # Insufficient balance
         - 'binance.error.ClientError:.*-1021'  # Timestamp out of window
       open_threshold_pct: 20         #                         >20%                             
       error_rate_window_sec: 60      #                                        error rate
       half_open_attempts: 3          #                                  HALF_OPEN           
   ```
   -                  `aurora_trading.schema.json`                                                      

3. **                                        API                 **:
   - `place_order`     `_place_binance_order()`                       `circuit_breaker.call()`
   - `cancel_order`     `_cancel_binance_order()`                                        
   - API calls                           RuntimeError                                circuit breaker counting
   - CircuitBreakerError                                                                                                    

4. **                                                       **:
   -                  `CircuitBreakerListener`                              `state_change()`
   -            WARNING                            OPEN         
   -            INFO                            HALF_OPEN      CLOSED           
   -                                                                             circuit breaker

5. **                                                      **:
   - `initialize_circuit_breaker_config()`                   runtime config updates
   -                           `fsm.py`            TTL/retry                           
   - Graceful fallback      defaults                                                       

6. **Unit                     **:
   -     `test_circuit_breaker_initialization`:                    default config
   -     `test_initialize_circuit_breaker_config`: config update functionality
   -     `test_circuit_breaker_blocks_after_failures`: OPEN                     5               
   -     `test_circuit_breaker_cancel_blocks_after_failures`:                      cancel    OPEN
   -     `test_circuit_breaker_excludes_insufficient_balance`:                      -2010               
   -     `test_circuit_breaker_half_open_recovery`:                                                                
   -     `test_circuit_breaker_state_logging`:                                         

**                    **:
-     Circuit breaker                                Binance API            5                              
-                                                              30                                                      
-                                                                (-2010 insufficient balance)    counting
-                unit                         7               ,                          
-                                                        trading.yaml    JSON schema                     
-                                                                         
-     AURORA_HARDENING_V1_CIRCUIT_BREAKER (               3)                                          
-     **AURORA_HARDENING_V1                                    !**               

**                           **:
- AURORA_SCENARIO_TESTING_V1:                                                           
- AURORA_TESTNET_PREP_V1:                                               testnet
- Performance benchmarking                 hardening features

**                           **:
- MarketData quality control (lag detection, sequence validation)
- WAL integrity verification (SHA256 hash-chain)
- Circuit breaker implementation
- Unit/integration                   TTL/retry             

## 2025-01-XX | RID: AURORA_MANAGE_FEATURES_V1 |                                                                                       Trailing Stop

**WHY**:                                                                                                                                      SL/TP                     OCO-                        trailing stop                         ,                                        D5 (                       bracket management)      D6 (no trailing stops).

**      **:
1. **                                           ** (`trading.yaml`, `aurora_trading.schema.json`):
   -                           `brackets` (enable, reduce_only, oco_emulation, sl/tp modes, ATR/bps calculation)
   -                           `trailing` (enable, activation_profit_atr_k, step_bps, cooldown_sec)
   -                                 JSON                                                

2. **                       Bracket Management    ManageFlowFSM** (`fsm_manage.py`):
   -                        : BRACKETS_PENDING     BRACKETS_PLACED
   -                      SL/TP                          entry_price + ATR/bps                         
   - Immediate placement            FILL: DEC:PLACE_ORDER        STOP_MARKET (SL)      LIMIT (TP)
   - OCO-                : SL fill     DEC:CANCEL_ORDER        TP, TP fill     cancel SL
   -                partial fills    quantity adjustment (cancel + replace)

3. **                       Trailing Stop** (`fsm_manage.py`):
   -                                                profit threshold (activation_profit_atr_k * ATR)
   -                                           SL: cancel                + place                 step_bps
   - Cooldown mechanism                                                      adjust
   - ATR-based        fixed BPS trailing modes

4. **                   BinanceExecutionAdapter** (`binance_execution_adapter.py`):
   -              `cancel_order()`               DELETE /fapi/v1/order API
   -                    `place_order()`        LIMIT/STOP_MARKET               
   -                    reduceOnly, stopPrice, newClientOrderId                     
   - Error handling        cancel operations

5. **                                                      ** (`test_fsm_manage.py`):
   -            bracket placement            fill
   -            OCO emulation (SL fill cancels TP)
   -            trailing stop activation      adjustment
   -            cooldown      edge cases
   -     13/13                                                (100% success rate)

6. **                                       **:
   -                                           `apps/`      `vfoundation/`

**                    **:
-     Bracket orders                                                                                             
-     OCO-                             :                       fill                                        
-     Trailing stop                               profit threshold                                                   
-     Partial fill handling    quantity adjustment
-     Cancel order API                           BinanceExecutionAdapter
-     13/13                                                (100% success rate)
-     AURORA_MANAGE_FEATURES_V1                                                                                        

**                  **:
- FSM: `apps/reference/domains/execution_position/fsm_manage.py`
- Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py`
- Config: `config/aurora/trading.yaml`, `config/_schemas/aurora_trading.schema.json`
- Tests: `tests/test_fsm_manage.py`

---

## 2025-01-XX | RID: AURORA_SYMBOL_SPECS_FIX_V1 |                        DecisionMaking                                                                          

**WHY**:                                 AURORA_SYMBOL_SPECS_V1                                                                              `lot_step`                `step_size`    DecisionMaking,                           NameError                                                                .

**      **:
1. **                                     DecisionMaking** (`decision_making.py`):
   -            377: `lot_step`     `step_size`                                                   
   -            452: `lot_step`     `step_size`    qty                             volatility sizing
   -            478: `lot_step`     `step_size`    qty                             mean reversion sizing
   -                                    : "Floor to lot step"     "Floor to step size"

2. **                                       **:
   -                                              `apps/`      `vfoundation/`

**                    **:
-            23                                                                            
-            36              (                               +                                          )                                  
-                                                                                                                                                
-     AURORA_SYMBOL_SPECS_V1                                                                                                   

**                  **:
- Decision: `apps/reference/domains/decision_making/decision_making.py`
- Tests: `tests/test_idempotency_*.py`, `tests/test_fsm_open.py`

---

## 2025-01-XX | RID: AURORA_FSM_TEST_FIX_V1 |                                     FSM Lifecycle

**WHY**: 4                  pytest                                 TDD                 ,                                                                                              AURORA_FSM_LIFECYCLE_V1.

**      **:
1. **                                                    ** (`conftest.py`):
   -                          sys.path: apps/     vfoundation/                                                    FSM
   -                                                apps/      vfoundation/

2. **                                          ExecPosFSM** (`test_fsm_close.py`, `test_fsm_manage.py`):
   -                  MockConfig             trading                         get()               
   -              required src/dst               Message     '                  recovery             

3. **                     payload             ** (`test_fsm_close.py`):
   -              `filled_qty > 0`               FILL/PARTIAL_FILL                       
   -                      test_manage_flow_on_fill_opens_position: OPENED     TRACKING

4. **                     FSM             **:
   - CloseFlowFSM: FLAT     OPENED        filled_qty > 0
   - ManageFlowFSM: FLAT     TRACKING        FILL/PARTIAL_FILL (immediate activation)
   - Portfolio state recovery:                    fill events                                         

**                    **:
-            20              FSM                                  
-                                                     PARTIAL_FILL                     immediate activation
-                          portfolio state recovery                 
-     AURORA_FSM_LIFECYCLE_V1                                                                                                   

**                  **:
- Tests: `tests/test_fsm_close.py`, `tests/test_fsm_manage.py`
- Config: `conftest.py`
- FSM: `vfoundation/apps/reference/domains/execution_position/fsm_*.py`

---

## 2025-10-23 | RID: AURORA_ACCOUNT_BALANCE_TEST_V1 |                                     AccountConnector

**WHY**:                                                                                             AccountConnector                                                   ,                         polling,                                              .

**      **:
1. **                                                    ** (`tests/integration/test_account_connector.py`):
   - `test_account_connector_initialization`:                                                                   config
   - `test_account_connector_polling_and_event_emission`:                    polling API                         EVT:ACCOUNT_UPDATE_RECEIVED
   - `test_account_connector_error_handling`:                    graceful handling                API
   - `test_account_connector_graceful_shutdown`:                                   polling thread
   - `test_account_connector_config_defaults`:                                             defaults

2. **                                 **:
   -                        pytest fixtures        mock config      Binance client
   - Mock FSMCore                                         
   -                poll_interval (1       )                    
   -                    fail-closed                                           

**                    **:
-                                                          : init, polling, events, errors, shutdown
-                                                                 account_balance domain
-                       ,      AccountConnector                                                      

**                  **:
- Test: `tests/integration/test_account_connector.py`

---

## 2025-10-23 | RID: AURORA_ACCOUNT_BALANCE_FIX_V1 |                                                 Account Balance

**WHY**:                                                 account_balance                                                          AccountConnector,                                                                                                                                           .

**      **:
1. **AuroraConfig** (`config_loader.py`):
   -                       `account_balance: Dict[str, Any]`
   -                  `to_dict()`                           account_balance
   -                                       `account_balance_config = trading_config.get('account_balance', {})`

2. **Trading Config** (`trading.yaml`):
   -                           `account_balance`:
     ```yaml
     account_balance:
       poll_interval_seconds: 15
       symbols: ["BTCUSDT", "ETHUSDT"]
     ```

3. **AccountConnector** (`account_connector.py`):
   -              `self.account_balance_config = config.account_balance`
   -                `self.update_interval = self.account_balance_config.get('poll_interval_seconds', 30)`

**                    **:
- AccountConnector                                              poll_interval=15       
- Portfolio                                          ,                                           intents                                         
- POSITION_GATE                                                                 

**                  **:
- Config: `apps/reference/config_loader.py`, `config/aurora/trading.yaml`
- Logic: `apps/reference/domains/account_balance/account_connector.py`

---

## 2025-10-23 | RID: AURORA_IDEMPOTENCY_V1 |                                              

**WHY**:                                                                                                             `idempotent_key`                                             `newClientOrderId`    Binance API.

**      **:
1. **                        **:                           `idempotency`    `trading.yaml`:
   ```yaml
   idempotency:
     enabled: true
     key_template: "{symbol}:{side}:{ts_bucket_ms}"
     ts_bucket_ms: 1000  # 1-second buckets
     ttl_sec: 120  # 2-minute TTL
   ```

2. **                             ** (`decision_making.py`):
   -                            : `hashlib`, `time`
   -                    `idempotent_key`                                 : `{symbol}:{side}:{ts_bucket}`
   -                    SHA256                32 hex                (                     Binance                    36 chars)
   -                       `idempotent_key`      payload `EVT:TRADE_INTENT_PROPOSED`
   - Fallback:          `enabled=False`,                                  `{symbol}_{timestamp_ms}`

3. **                            Bridge** (`main.py`):
   -                  `on_trade_intent_proposed()`:                      `idempotent_key`    event payload    `CMD:OPEN`
   -                                                                     

4. **                                            ** (`binance_execution_adapter.py`):
   -                  `place_order()`:            `idempotent_key`    payload
   -                  `_place_binance_order()`:                  `idempotent_key: Optional[str]`
   -                                                                  `newClientOrderId`      Binance API request
   -                   : `"Using idempotent newClientOrderId: {key}"`

5. **          ** (`test_idempotency_key_generation.py`):
   -     `test_idempotent_key_generated_when_enabled`:                                       SHA256 hash (32 chars)
   -     `test_idempotent_key_fallback_when_disabled`:                    fallback              `{symbol}_{ts}`
   -     `test_idempotent_key_uniqueness_across_symbols`:                              BTCUSDT/ETHUSDT
   - **                  **: 3/3 passed

**                    **:
- **                                               Binance**:                  POST                       `newClientOrderId`                                             
- **                                   **: SHA256 hash                      collision-free            (birthday paradox: ~2^128                       )
- **Time bucketing**: 1-second buckets                                                                                      
- **Backward compatibility**:        `enabled=false`                                  fallback                                      

**                  **:
-             : `config/aurora/trading.yaml` (+             idempotency)
-                                : `apps/reference/domains/decision_making/decision_making.py` (lines 503-536)
- Bridge: `apps/reference/main.py` (line 107)
- Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py` (lines 226, 260, 349-382)
-           : `tests/test_idempotency_key_generation.py` (3 tests, all passed)

**                           **:
-                                    :                                                                                          `CMD:OPEN`
-                     :                `duplicate_order_attempts_count` (         Binance                     `newClientOrderId` collision)

---

## 2025-10-15 | RID: FSMP-P2-T01 |                                      feature_engineering

**WHY**:                                                                            feature_engineering                                          -             aurora/features.

**      **:
-                              aurora/features/builder.py:                             obi, tfi, delta_price, absorption
-                              aurora/features/sol_crosslink.py:                          -            SOL returns
-                  domain_dict.json                     EVT:MARKET_TICK_RECEIVED                         EVT:FEATURES_CALCULATED
-                  JSON            features_calculated_v1.json                 ts, symbol, features (obi, tfi, delta_price, absorption)

**                    **:
-                                  : apps/reference/domains/feature_engineering/domain_dict.json
-                            : apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json
-                                                                     aurora/features/builder.py

**                  **:
-                 : apps/reference/domains/feature_engineering/domain_dict.json
-           : apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json

---

## 2025-10-15 | RID: FSMP-P2-T02 |                                            feature_engineering

**WHY**:                                                     ,                                               EVT:MARKET_TICK_RECEIVED                         EVT:FEATURES_CALCULATED.

**      **:
-                  tests/domains/test_feature_engineering.py                 test_feature_engineering_consumes_tick_and_emits_features
-                                                   FSMCore, mock listener,                       EVT:FEATURES_CALCULATED
-                                           FeatureEngineering (                     ,                          )
-                  fake_market_tick_payload              market_tick_v1.json
-                EVT:MARKET_TICK_RECEIVED                                        mock listener

**                                       **:
-                          ,                       pytest               ModuleNotFoundError        FeatureEngineering

**                  **:
-         : tests/domains/test_feature_engineering.py

---

## 2025-10-15 | RID: FSMP-P2-T03 |                                           FeatureEngineering

**WHY**:                           FeatureEngineering,                                                                   aurora/features/                        vFoundation.

**      **:
-                              aurora/features/builder.py:                                   obi, tfi, delta_price, absorption
-                  apps/reference/domains/feature_engineering/feature_engineering.py                 FeatureEngineering
-                        __init__                            EVT:MARKET_TICK_RECEIVED
-                                                          : obi=(bid-ask)/(bid+ask), tfi=(buy-sell)/(buy+sell), absorption=(buy+sell)/(bid+ask), delta_price=price-prev_price
-                         on_market_tick                                                            EVT:FEATURES_CALCULATED
-                                             payload                           RawFeed                   

**                                       **:
-          tests/domains/test_feature_engineering.py                                  
-                           ruff      mypy                   
-                           feature_engineering.py    89%

**                    **:
-                                 (3 passed)
-     ruff check: All checks passed
-     mypy --strict: Success: no issues found
-                        : 82% (                              -                           FSMCore,                                                100%)
-                                                          vFoundation                       .

**                  **:
-       : apps/reference/domains/feature_engineering/feature_engineering.py
-           : tests/domains/test_feature_engineering.py (3           )

---

## 2025-10-15 | RID: FSMP-P1-T03 |                      MarketDataConnector

**WHY**:                        MarketDataConnector                                             Binance WebSocket                                               FSM           .

**      **:
-                           `MarketDataConnector`    `apps/reference/domains/market_data/market_data_connector.py`                     `__init__`, `start()`, `stop()`, `_ws_loop()`, `_process_message()`.
-                        WebSocket                                   `unicorn_binance_websocket_api`    fallback                 .
-                                                   Binance bookTicker                           FSM            `EVT:MARKET_TICK_RECEIVED`    payload                         `market_tick_v1.json`.
-                                                                                        .
-                                     unit                                                                                  .

**                    **:
-                                 (13 passed)
-     ruff check: All checks passed
-     mypy --strict: Success: no issues found
-                        : 87% (         89%,                     12                                              )
-                                                        vFoundation                       .

**                  **:
-       : `apps/reference/domains/market_data/market_data_connector.py`
-           : `tests/domains/test_market_data.py` (13             )

---

## 2025-10-15 | RID: FSMP-P1-T02 |                                                         market_data

**WHY**:                                                             MarketDataConnector                                               .

**      **:
-                           `tests/domains/test_market_data.py`                 `TestMarketDataConnector`.
-                                 `test_connector_emits_market_tick_event`                                 FSMCore, mock listener, mocking BinanceWebSocketApiManager,                               MarketDataConnector      assertions                                     .

**                    **:
-                                                                                                   (MarketDataConnector                ).

**                  **:
-         : `tests/domains/test_market_data.py`

---

## 2025-10-15 | RID: FSMP-P1-T02 |                                                         market_data

**WHY**:                                                             MarketDataConnector                                               .

**      **:
-                           `tests/domains/test_market_data.py`                 `TestMarketDataConnector`.
-                                 `test_connector_emits_market_tick_event`                                 FSMCore, mock listener, mocking BinanceWebSocketApiManager,                               MarketDataConnector      assertions                                     .

**                    **:
-                                                                                                   (MarketDataConnector                ).

**                  **:
-         : `tests/domains/test_market_data.py`

---

## 2025-10-15 | RID: FSMP-P1-T01 |                                      market_data

**WHY**:                                                                                           market_data                           vFoundation.

**      **:
-                                    -           `apps/obs/binance_ws.py`:                                                `market_ticks.jsonl`    payload `{"ts": int, "symbol": str, "bid": float, "ask": float, "mid": float}`.
-                  `domain_dict.json`                     market_data                                  `EVT:MARKET_TICK_RECEIVED`.
-                  JSON-           `market_tick_v1.json` (Draft 7)                                           required           .

**                    **:
-                            : `vfoundation/apps/reference/domains/market_data/domain_dict.json`, `schemas/market_tick_v1.json`.
-                                                                            binance_ws.py.

**                  **:
-                 : `vfoundation/apps/reference/domains/market_data/domain_dict.json`
-           : `vfoundation/apps/reference/domains/market_data/schemas/market_tick_v1.json`

---

## 2025-10-15 | RID: FSMP-P3-T01 |                                      risk_management

**WHY**:                                                                            risk_management                                          -             aurora/risk.

**      **:
-                              aurora/risk/caps.py:                      notional caps      position limits (final_size, capped, why)
-                              aurora/risk/cvar_guard.py: CVaR                                       (session_cvar, trade_cvar)
-                              aurora/risk/kelly.py:                                                                (kelly_fraction)
-                              aurora/risk/portfolio.py:                                   (                    ,                 )
-                  domain_dict.json                     EVT:FEATURES_CALCULATED                         EVT:RISK_ASSESSMENT_COMPLETED
-                  JSON            risk_assessment_v1.json                 symbol, timestamp, risk_parameters (kelly_fraction, cvar_limit_usd, max_drawdown_percent, is_trading_allowed)

**                    **:
-                                  : apps/reference/domains/risk_management/domain_dict.json
-                            : apps/reference/domains/risk_management/schemas/risk_assessment_v1.json
-                                                                     aurora/risk/

**                  **:
-                 : apps/reference/domains/risk_management/domain_dict.json
-           : apps/reference/domains/risk_management/schemas/risk_assessment_v1.json

---

## 2025-10-15 | RID: FSMP-P3-T03 |                                           RiskManagement

**WHY**:                           RiskManagement,                                                                                        aurora/risk/        vFoundation.

**      **:
-                              risk_manager.py:                                  providers,                                                            
-                  apps/reference/domains/risk_management/risk_management.py                 RiskManagement
-                        __init__                            EVT:FEATURES_CALCULATED
-                              : kelly_fraction    aurora/risk/kelly.py, cvar_limit_usd    cvar_guard.py, max_drawdown_percent      is_trading_allowed                   features
-                         on_features_calculated                                                            EVT:RISK_ASSESSMENT_COMPLETED
-                                             payload                           providers

**                                       **:
-          tests/domains/test_risk_management.py                                  
-                           ruff      mypy                   
-                           risk_management.py    89%

**                    **:
-                                 (1 passed)
-     ruff check: All checks passed
-     mypy --strict: Success: no issues found
-                        : 78% (                              -                           FSMCore,                                                100%)
-                                                          vFoundation                       .

**                  **:
-       : apps/reference/domains/risk_management/risk_management.py
-           : apps/reference/domains/risk_management/schemas/risk_assessment_v1.json (                     ts                timestamp)
-         : tests/domains/test_risk_management.py (                            ts)
-                                    : tests/domains/test_integration_three_domains.py

---

## 2025-10-15 | RID: FSMP-P3-T03-INT |                                               

**WHY**:                                                    market_data     feature_engineering     risk_management.

**      **:
-                                                      test_integration_three_domains.py
-                                   -    -       flow: market_tick     features     risk_assessment
-                                                    : risk_management                              timestamp                ts
-                                 risk_assessment_v1.json: timestamp     ts                                      
-                             RiskManagement: timestamp     ts    payload
-                               test_risk_management.py: timestamp     ts    assertions
-                                                   :                           edge case (                   '      )

**                                       **:
-                                                                      
-              event flow                              
-                                                                          (                                    ts)

**                    **:
-                                                            (2/2 passed)
-     Event flow: market_tick     features     risk_assessment             
-                                                                  (                                    ts)
-     Risk parameters                                                                 features

**                  **:
-                                    : tests/domains/test_integration_three_domains.py

---

## 2025-10-15 | RID: FSMP-P3-T02 |                                            risk_management

**WHY**:                                                     ,                                               EVT:FEATURES_CALCULATED                         EVT:RISK_ASSESSMENT_COMPLETED.

**      **:
-                  tests/domains/test_risk_management.py                 test_risk_management_consumes_features_and_emits_assessment
-                                                   FSMCore, mock listener,                       EVT:RISK_ASSESSMENT_COMPLETED
-                                           RiskManagement (                     ,                          )
-                  fake_features_payload              features_calculated_v1.json
-                EVT:FEATURES_CALCULATED                                        mock listener

**                                       **:
-                          ,                       pytest               ModuleNotFoundError        RiskManagement

**                  **:
-         : tests/domains/test_risk_management.py

---

## 2025-10-15 | RID: FSMP-P4-T01 |                                      position_tracking

**WHY**:                                                                                         position_tracking                                  aurora/positions/.

**      **:
-                              aurora/positions/account.py:                             (notional, leverage)
-                              aurora/positions/inventory.py: InstrumentPosition (symbol, quantity, average_price, venues), InventorySnapshot
-                              aurora/positions/pnl.py: PnLBreakdown (realized_usd, unrealized_usd),                                     P&L
-                  domain_dict.json                     EVT:TRADE_EXECUTED                         EVT:PORTF        _STATE_UPDATED
-                             trade_executed_v1.json                                  (symbol, side, price, quantity, ts, fees, venue)
-                             portfolio_state_v1.json                                    (ts, equity, realized_pnl, unrealized_pnl, positions[])

**                    **:
-                                  : apps/reference/domains/position_tracking/domain_dict.json
-                                     : apps/reference/domains/position_tracking/schemas/trade_executed_v1.json
-                                       : apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json
-        JSON                                                                         aurora/positions/

**                  **:
-                 : apps/reference/domains/position_tracking/domain_dict.json
-                                     : apps/reference/domains/position_tracking/schemas/trade_executed_v1.json
-                                       : apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json

---

## 2025-10-15 | RID: FSMP-P4-T02 |                                            position_tracking

**WHY**:                                                     ,                                               EVT:TRADE_EXECUTED                         EVT:PORT          _STATE_UPDATED.

**      **:
-                  tests/domains/test_position_tracking.py                 test_position_tracking_consumes_trade_and_updates_portfolio
-                                                   FSMCore, mock listener,                       EVT:PORTF        _STATE_UPDATED
-                                           PositionTracking (                     ,                          )
-                  fake_trade_payload              trade_executed_v1.json (               0.1 BTC      50000)
-                EVT:TRADE_EXECUTED                                        mock listener
-                                         payload              portfolio_state_v1.json
-                                         BTC                   net_position=0.1      avg_entry_price=50000

**                                       **:
-                          ,                       pytest               ModuleNotFoundError        PositionTracking

**                  **:
-         : tests/domains/test_position_tracking.py

---

## 2025-10-15 | RID: FSMP-P4-T03 |                                           PositionTracking

**WHY**:                           PositionTracking,                                                                     P&L                         aurora/positions/        vFoundation.

**      **:
-                              aurora/positions/inventory.py:              record_fill                                             weighted average
-                              aurora/positions/pnl.py:                                                                P&L                            /                                              
-                  apps/reference/domains/position_tracking/position_tracking.py                 PositionTracking
-                        __init__                            EVT:TRADE_EXECUTED
-                              : _update_position                                                                 ,                            P&L,                                        
-                         on_trade_executed                                                            EVT:PORTF        _STATE_UPDATED
-                                             payload                           providers
-                           _calculate_unrealized_pnl      _get_positions_snapshot

**                                       **:
-          tests/domains/test_position_tracking.py                                  
-                           ruff      mypy                   
-                           position_tracking.py    89%

**                    **:
-                                 (1 passed)
-     ruff check: All checks passed
-     mypy --strict: Success: no issues found
-                        : 71% (                              -                           FSMCore,                                                100%)
-                                                          vFoundation                       .

**                  **:
-       : apps/reference/domains/position_tracking/position_tracking.py

---

## 2025-01-15 | RID: FSMP-P4-T03-COMPLETED |                                                           position_tracking

**WHY**:                                                     71%         89%                                                     edge cases                                                 .

**      **:
-              6                              tests/domains/test_position_tracking.py:
  - test_position_tracking_multiple_trades:                                                                           
  - test_position_tracking_complete_position_close:                                                                        P&L
  - test_position_tracking_short_position:                                                      
  - test_position_tracking_position_flip:                                    (flip               )
  - test_position_tracking_multiple_venues:                                            
  - test_position_tracking_invalid_side:                                                              
  - test_position_tracking_short_to_long_flip: flip                                                 
  - test_position_tracking_partial_close:                                                 
-                                           : ruff check    , mypy --strict    

**                    **:
-             : 9/9                       
-                 : 86% (                      71%,                               -                           FSMCore)
- Ruff:                                               
- MyPy:                          
-             : 100%                              

**                  **:
-           : tests/domains/test_position_tracking.py (9             )
-       : apps/reference/domains/position_tracking/position_tracking.py

---

## 2025-01-15 | RID: FSMP-P5-T01 |                                                           decision_making

**WHY**:                                                                                                 decision_making,                                                            ,                                   .

**      **:
-                              aurora/decision/assembler.py:                    trade_intent                 instrument, side, p, payoff_ratio_r, tca_budget, risk_budget, size, valid_for_ms, why
-                              aurora/decision/entry_rules.py:                                                 threshold, regime_gate, risk_sizing
-                              aurora/signal/scorer.py:                                                                                     
-                                  : EVT:FEATURES_CALCULATED, EVT:RISK_ASSESSMENT_COMPLETED, EVT:PORTF        _STATE_UPDATED
-                                  : EVT:TRADE_INTENT_PROPOSED
-                  domain_dict.json                                             /                    
-                  trade_intent_v1.json                              aurora assembler.py                   

**                    **:
-                                  : apps/reference/domains/decision_making/domain_dict.json
-                            : apps/reference/domains/decision_making/schemas/trade_intent_v1.json
-                                                    aurora trade_intent DTO

**                  **:
-                 : apps/reference/domains/decision_making/domain_dict.json
-           : apps/reference/domains/decision_making/schemas/trade_intent_v1.json

---

## 2025-01-15 | RID: FSMP-P5-T02 |                                            decision_making

**WHY**:                                                     ,                                                                                                         EVT:TRADE_INTENT_PROPOSED.

**      **:
-                  tests/domains/test_decision_making.py                 test_decision_making_aggregates_events_and_proposes_intent
-                                                   FSMCore, mock listener,                       EVT:TRADE_INTENT_PROPOSED
-                                           DecisionMaking (                     ,                          )
-                                 payload                                                     : features_calculated, risk_assessment, portfolio_state
-                                                                                                                           
-              assertions                                              trade_intent_v1.json: required         ,                    , nested     '        

**                                       **:
-                          ,                       pytest               ModuleNotFoundError        DecisionMaking

**                  **:
-         : tests/domains/test_decision_making.py

---

## 2025-01-15 | RID: FSMP-P5-T03 |                                           DecisionMaking

**WHY**:                                     DecisionMaking,                                                                                                                             .

**      **:
-                  apps/reference/domains/decision_making/decision_making.py                 DecisionMaking
-                        __init__                            EVT:FEATURES_CALCULATED, EVT:RISK_ASSESSMENT_COMPLETED, EVT:PORTF        _STATE_UPDATED
-                                                latest_features, latest_risk, latest_portfolio
-                                  aurora/decision/: signal_score = weighted sum of obi, tfi, absorption
-                                               : buy (>0.1), sell (<-0.1), neutral (         - no trade)
-                    risk constraints: is_trading_allowed      kelly_fraction > 0
-                      trade_intent_v1.json payload                                                  
-                      EVT:TRADE_INTENT_PROPOSE                                 
-              3                                      edge cases: neutral signal, risk not allowed, zero kelly

**                    **:
-              tests/domains/test_decision_making.py                    (4/4 passed)
-     ruff check: All checks passed
-     mypy --strict: Success: no issues found
-                     : 93% (                   89%,                       edge cases)
-                                                          vFoundation FSM

**                  **:
-       : apps/reference/domains/decision_making/decision_making.py
-           : tests/domains/test_decision_making.py (4           )

---

## 2025-01-XX | RID: FSMP-P1-T08 |                                     Aurora Core Flow

**WHY**:                                                                          ,                                                        market tick      trade intent                   5                FSM.

**      **:
-                  tests/integration/test_aurora_core_flow.py                              end-to-end
-                        FSMCore                                                     event listening/emitting
-                                                            5               : TestMarketDataConnector, TestFeatureEngineering, TestRiskManagement, TestPositionTracking, TestDecisionMaking
-                        event flow: MARKET_TICK_RECEIVED     FEATURES_CALCULATED     RISK_ASSESSMENT_COMPLETED     PORTFOLIO_STATE_UPDATED     TRADE_INTENT_PROPOSED
-                                 Message                   , payload                             -            
-                      apps/reference/domains/market_data/market_data_connector.py (                                                   stream_type)
-                          : pytest                                  

**                    **:
-                                :              Aurora Core flow                     
-     Event flow                                                 5               
-     Trade intent                                                                                      
-                          API                   market_data_connector.py

**                  **:
-                                    : tests/integration/test_aurora_core_flow.py
-                       : apps/reference/domains/market_data/market_data_connector.py

---

## 2025-01-XX | RID: FSMP-RUNNER-T02 |                                                            Aurora Core

**WHY**:                                            main.py                                                             Aurora Core        market data      trade intents.

**      **:
-                  apps/reference/main.py                                 FSMCore               5               
-              event listener                                 trade intents
-                        graceful shutdown
-                      MarketDataConnector                        trade                             bookTicker
-                                                                                                                                                    

**                    **:
-     main.py                                               
-                                     Binance WebSocket    trade               
-                                                          
-                                                                                               
-                    trade intents                                 

**                  **:
-                              : apps/reference/main.py
-                       : apps/reference/domains/market_data/market_data_connector.py (trade data processing)
-                                                       

---

## 2025-10-23 | RID: AURORA_ACCOUNT_CONNECTOR_TESTS_SUCCESS_V1 |                                                                              

**WHY**:                                                                  AccountConnector                                                                                                  .

**      **:
-             : `pytest tests/integration/test_account_connector.py -v`
-                   : 5/5                                           

**                    **:
-     **test_account_connector_initialization**:                                                AuroraConfig
-     **test_account_connector_polling_and_event_emission**:                      polling      EVT:ACCOUNT_UPDATE_RECEIVED
-     **test_account_connector_error_handling**: fail-closed        API                 
-     **test_account_connector_graceful_shutdown**:                                 polling thread
-     **test_account_connector_config_defaults**:                          default               

**                  **:
- Test Results: 5 passed, 0 failed
- Coverage: init, polling, events, errors, shutdown, defaults

**                **: AccountConnector                                                      ,                                                                                                                                                     .

---

## 2025-01-15 | RID: AURORA_FSM_LIFECYCLE_V1 |                                                                                FSM

**WHY**:                                                        PARTIAL_FILL           ,                                                                                                            FSM                                             .

**      **:
1. **CloseFlowFSM** (`apps/reference/domains/execution_position/fsm_close.py`):
   -                                                 "FILL"      ("FILL", "PARTIAL_FILL")
   -                                 filled_qty > 0                          
   -                                                                 (FILL vs PARTIAL_FILL)

2. **ManageFlowFSM** (`apps/reference/domains/execution_position/fsm_manage.py`):
   -                               FLAT     OPENED      FLAT     TRACKING                                           
   -                                              OPENED                   UPD           
   -                                            _check_rules()            fill           

3. **ExecPosFSM** (`apps/reference/domains/execution_position/fsm.py`):
   -                             EVT:PORTFOLIO_STATE_UPDATED                                         
   -                        _handle_portfolio_state_recovery()           
   -                                              fill                                          FSM             

4. **                    **:
   -              test_close_flow_on_partial_fill_opens_position()
   -              test_manage_flow_on_partial_fill_immediate_activation()
   -                                                                                  

**                    **:
-     PARTIAL_FILL                                                                      CloseFlowFSM
-                                                                                                                           
-     FSM                                                                                PORTFOLIO_STATE_UPDATED
-                                                                                ,                                                            pytest

---

## 2025-01-XX | RID: AURORA_IDEMPOTENCY_V1 |                                                                   

**WHY**:                                                                                                                                                 ,                                                                                .

**      **:
1. **                                                            **:
   -                          SHA256                                    DecisionMaking                     `symbol:side:timestamp`
   -                                       `idempotent_key`            EVT:TRADE_INTENT_PROPOSED     CMD:OPEN    main.py
   -                                               `newClientOrderId`    binance_execution_adapter.py

2. **                                              **:
   -                    `aurora_trading.schema.json`                   `idempotency` (enabled, key_template, ts_bucket_ms, ttl_sec)
   -                  `trade_intent.schema.json`                           TradeIntent DTO    `idempotent_key` (32-char string)

3. **                                            **:
   - `test_idempotency_key_generation.py`:                                         , fallback                              ,                         
   - `test_decision_to_execution_flow.py`:                                                                 bridge
   - `test_binance_execution_adapter.py`:                                   `idempotent_key`      `newClientOrderId`

**                    **:
-     SHA256                                      32-                     hex                         Binance                     
-                                                               EVT   CMD   DEC   API pipeline
-     Time-bucketed            (1-                                   )                                            
-                                         :                    +                  + API                          (5                                )
-     AURORA_IDEMPOTENCY_V1                                                                                        

---

## 2025-01-XX | RID: AURORA_SYMBOL_SPECS_V1 |                                                               

**WHY**:                                                                                              (tick_size, step_size, min_qty, min_notional)                                                                                                                                                     .

**      **:
1. **                                         ** (`config/aurora/trading.yaml`):
   -              `step_size`                `lot_step`        BTCUSDT      ETHUSDT
   -              `min_notional`                                                                                 

2. **                         OpenFlowFSM** (`fsm_open.py`):
   -              `_get_instrument_specs()`                                                                                          
   -                                                                                                 config
   -                                             `qty`               `step_size` (ROUND_FLOOR)
   -                                             `price`      `tick_size`        LIMIT               
   -                                 `min_qty`                                
   -                                 `min_notional`        LIMIT                (                             )
   -                                 `min_notional`        MARKET                (                                         `price_ref`)

3. **                 DecisionMaking** (`decision_making.py`):
   -                  `lot_step`      `step_size`                                                        

4. **                 Bridge** (`main.py`):
   -                  `price_ref`    EVT:TRADE_INTENT_PROPOSED      CMD:OPEN        MARKET notional                   

5. **                           ** (`test_fsm_open.py`):
   - `test_open_flow_qty_rounding`:                                         qty      step_size
   - `test_open_flow_qty_below_min`:                             qty < min_qty
   - `test_open_flow_market_min_notional`:                                                    notional        MARKET

**                    **:
-                                                                                                                           
-     Qty                                        step_size                                
-     Price                               tick_size        LIMIT               
-                        min_qty                                
-                        min_notional        LIMIT (          )      MARKET (                      price_ref)
-            13              fsm_open                                  
-                                                    apps/      vfoundation/

**                  **:
- Config: `config/aurora/trading.yaml` (             step_size, min_notional)
- FSM: `apps/reference/domains/execution_position/fsm_open.py`
- Decision: `apps/reference/domains/decision_making/decision_making.py`
- Bridge: `apps/reference/main.py`
- Tests: `tests/test_fsm_open.py` (                                         )

---

## 2025-01-XX | RID: AURORA_AUDIT_FIXES_V1 |                                                                 

**WHY**:                                                                                                             ,                  "                                     ",                                                 ,                                                              .

**      **:
1. **                                                                 (`drift_monitor.py` -                     7):**
   - **                :** DEC:CLOSE                                              -           FILL               ,                        ,                                               
   - **                      :**                                 `reduceOnly=True`        FILL                   DEC:CLOSE                       
   - **            :** DEC:CLOSE     TP                       `evt_verb == "FILL"`      `reduceOnly=True`,                  FN
   - **          :**              `test_close_decision_with_reduce_only_fill()`      `test_close_decision_with_cancelled()`

2. **                                                       (`decision_making.py` -                     4):**
   - **                :** UNCERTAIN                                                                             ,                                                                                       
   - **                      :**              regime-based sizing    `regime_size_multiplier = 0.5`        UNCERTAIN             
   - **            :** UNCERTAIN                        position size      50%                                                   
   - **                        :**                                              sizing config    `position_sizing`                `sizing`

3. **                                          `float` (`fsm.py` -                     8):**
   - **                :** `safe_float`                              `float()`                                                                      
   - **                      :**                  `safe_float`      `safe_decimal`    `Decimal`                                     
   - **            :**                          `Decimal(str(val))`                `float(val)`                                           
   - **            :**              `from decimal import Decimal`

4. **                                            :**
   -     11/11              drift_monitor                    (                                       reduceOnly)
   -                                                          
   -                                                    apps/      vfoundation/

**                    **:
-     Drift Monitor                                     position-closing                       FILL           
-     UNCERTAIN                           position size                                                   
-                              Decimal                float                                                   
-                           unit                                                                                        
-     AURORA_AUDIT_FIXES_V1                                                                                        

**                  **:
- Drift Monitor: `apps/reference/domains/execution_position/drift_monitor.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- FSM: `apps/reference/domains/execution_position/fsm.py`
- Tests: `tests/test_drift_unit.py` (                    reduceOnly)

---

## 2025-10-XX | RID: AURORA_CLOSE_LOGIC_AUDIT_V1 |                                                                                    

**WHY**:                                                                                                                                                 ,                                                                ,                                                                                     .

**                                             :**

### 1. **                                                                    ?**

**                             :**                                                                                                   :
- **                                            ** (max_hold_sec)                     
- **                                 **        REJECTED/EXPIRED               
- **                                   ** (UPD:TICK           )

**                                                  :**
- `apps/reference/domains/execution_position/fsm_close.py`,            75-95: `_check_close_conditions()`
-                1: `if elapsed > self.max_hold_sec:` (           79)
-                2: `if msg.verb in ("REJECTED", "EXPIRED"):` (           85)
-                3: `if msg.op == "UPD" and msg.verb == "TICK":` (           91)

**                                          :**
```python
# Rule 1: Max hold time (stub)
now = time.time()
elapsed = now - self.position_open_ts
if elapsed > self.max_hold_sec:
    return self._emit_close(msg, "CLOSE_RULE", {"rule": "max_hold_time", "elapsed_sec": elapsed})

# Rule 2: Emergency close on REJECTED/EXPIRED
if msg.verb in ("REJECTED", "EXPIRED"):
    return self._emit_close(msg, "CLOSE_EMERGENCY", {"trigger": msg.verb})
```

**                                          :** 
- `test_close_flow_max_hold_time_triggers()`    `tests/test_fsm_close.py`
- `test_close_flow_rejected_triggers_emergency_close()`    `tests/test_fsm_close.py`
- `test_close_flow_timer_check_triggers()`    `tests/test_fsm_close.py`

### 2. **                                                   ?**

**                             :**                                                     SL/TP                             .                                   **                                FSM** (`fsm_close.py`),                       `DEC:CLOSE`                   `reduceOnly=true`,                                                   MARKET                         `binance_execution_adapter.py`.

**                                                  :**
- `apps/reference/domains/execution_position/fsm_close.py`,            107-125: `_emit_close()`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`,            872-950: `place_order()`

**                                          :**
```python
# fsm_close.py -                    DEC:CLOSE
dec = Message(
    op="DEC",
    verb="CLOSE",
    src=msg.dst,
    dst="execution_position",
    rid=msg.rid,
    why=why[:80],
    idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
    pld={
        "reduce_only": True,  #              true                        
        **details,
    },
)
```

**                       :** `DEC:CLOSE`                                   MARKET               `reduceOnly=true`                    .

**                                       :**                                                      -                                               `DEC:CLOSE`     MARKET           .

**                                          :** 
- `test_close_flow_emits_dec_close_with_reduce_only()`    `tests/test_fsm_close.py`
-                                                             DEC:CLOSE    MARKET               `test_binance_execution_adapter.py`

### 3. **                                                                                       ?**

**                             :**                                         **POSITION_GATE             **    `decision_making.py`,                                                                                                         ,                                      ,                                                    (                    )             .

**                                                  :**
- `apps/reference/domains/decision_making/decision_making.py`,            339-381: POSITION_GATE         

**                                          :**
```python
# POSITION_GATE: Prevent position accumulation
if existing_position:
    current_qty = decimal.Decimal(str(existing_position.get("net_position", 0)))
    
    # Check if position is effectively zero
    if abs(current_qty) < decimal.Decimal('1e-9'):
        # Allow new position
    else:
        # Determine if this is a reverse trade
        if current_qty > decimal.Decimal('1e-9') and intended_side == "sell":
            # Allow SELL (closing LONG)
        elif current_qty < -decimal.Decimal('1e-9') and intended_side == "buy":
            # Allow BUY (closing SHORT)
        else:
            # Same direction trade - BLOCK
            self.logger.warning(f"[POSITION_GATE]     Trade intent BLOCKED for {symbol}: Same direction as existing position")
            self.clear_internal_state()
            return
```

**                                          :**
- `existing_position`                                 
- `abs(current_qty) >= 1e-9` (                                  )
- `intended_side`                                                                          (BUY        LONG, SELL        SHORT)

**                                          :**                                    POSITION_GATE                 `test_decision_making*.py`.

**                                 :**
-     **                               :**                               -                                                                      ,                              `DEC:CLOSE`    `reduceOnly=true`
-     **SL/TP             :**                                               -                                                                  FSM
-     **                                     :** POSITION_GATE                                    ,                                                            
-        **                               :**                                                                                                                               

**                  :**
- Close FSM: `apps/reference/domains/execution_position/fsm_close.py`
- Manage FSM: `apps/reference/domains/execution_position/fsm_manage.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- Binance Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py`

---

## 2025-10-XX | RID: AURORA_CLOSE_LOGIC_AUDIT_V1 |                                                                                    

**WHY**:                                                                                                                                                 ,                                                                ,                                                                                     .

**                                             :**

### 1. **                                                                    ?**

**                             :**                                                                                                   :
- **                                            ** (max_hold_sec)                     
- **                                 **        REJECTED/EXPIRED               
- **                                   ** (UPD:TICK           )

**                                                  :**
- `apps/reference/domains/execution_position/fsm_close.py`,            75-95: `_check_close_conditions()`
-                1: `if elapsed > self.max_hold_sec:` (           79)
-                2: `if msg.verb in ("REJECTED", "EXPIRED"):` (           85)
-                3: `if msg.op == "UPD" and msg.verb == "TICK":` (           91)

**                                          :**
```python
# Rule 1: Max hold time (stub)
now = time.time()
elapsed = now - self.position_open_ts
if elapsed > self.max_hold_sec:
    return self._emit_close(msg, "CLOSE_RULE", {"rule": "max_hold_time", "elapsed_sec": elapsed})

# Rule 2: Emergency close on REJECTED/EXPIRED
if msg.verb in ("REJECTED", "EXPIRED"):
    return self._emit_close(msg, "CLOSE_EMERGENCY", {"trigger": msg.verb})
```

**                                          :**                                                                                           `tests/domains/test_*_close*.py`.

### 2. **                                                   ?**

**                             :**                                                     SL/TP                             .                                   **                                FSM** (`fsm_close.py`),                       `DEC:CLOSE`                   `reduceOnly=true`,                                                   MARKET                         `binance_execution_adapter.py`.

**                                                  :**
- `apps/reference/domains/execution_position/fsm_close.py`,            107-125: `_emit_close()`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`,            872-950: `place_order()`

**                                          :**
```python
# fsm_close.py -                    DEC:CLOSE
dec = Message(
    op="DEC",
    verb="CLOSE",
    src=msg.dst,
    dst="execution_position",
    rid=msg.rid,
    why=why[:80],
    idempotent_key=f"{msg.rid}_{why}_{int(time.time())}",
    pld={
        "reduce_only": True,  #              true                        
        **details,
    },
)
```

**                       :** `DEC:CLOSE`                                   MARKET               `reduceOnly=true`                    .

**                                       :**                                                      -                                               `DEC:CLOSE`     MARKET           .

**                                          :**                                           `DEC:CLOSE`    `test_binance_execution_adapter.py`.

### 3. **                                                                                       ?**

**                             :**                                         **POSITION_GATE             **    `decision_making.py`,                                                                                                         ,                                      ,                                                    (                    )             .

**                                                  :**
- `apps/reference/domains/decision_making/decision_making.py`,            339-381: POSITION_GATE         

**                                          :**
```python
# POSITION_GATE: Prevent position accumulation
if existing_position:
    current_qty = decimal.Decimal(str(existing_position.get("net_position", 0)))
    
    # Check if position is effectively zero
    if abs(current_qty) < decimal.Decimal('1e-9'):
        # Allow new position
    else:
        # Determine if this is a reverse trade
        if current_qty > decimal.Decimal('1e-9') and intended_side == "sell":
            # Allow SELL (closing LONG)
        elif current_qty < -decimal.Decimal('1e-9') and intended_side == "buy":
            # Allow BUY (closing SHORT)
        else:
            # Same direction trade - BLOCK
            self.logger.warning(f"[POSITION_GATE]     Trade intent BLOCKED for {symbol}: Same direction as existing position")
            self.clear_internal_state()
            return
```

**                                          :**
- `existing_position`                                 
- `abs(current_qty) >= 1e-9` (                                  )
- `intended_side`                                                                          (BUY        LONG, SELL        SHORT)

**                                          :**                                           POSITION_GATE                 `test_decision_making*.py`.

**                                 :**
-     **                               :**                               -                                                                      ,                              `DEC:CLOSE`    `reduceOnly=true`
-     **SL/TP             :**                                               -                                                                  FSM
-     **                                     :** POSITION_GATE                                    ,                                                            
-        **                               :**                                                                                                                               

**                  :**
- Close FSM: `apps/reference/domains/execution_position/fsm_close.py`
- Manage FSM: `apps/reference/domains/execution_position/fsm_manage.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- Binance Adapter: `apps/reference/domains/execution_position/binance_execution_adapter.py`

---

## 2025-01-XX | RID: AURORA_GRANULAR_LOGGING_V1 |                                                                                                      

**WHY**:                                                                                                             Aurora Core                                                                                                                                                                                                               RID (Request ID)                                                            .

**      **:
1. **                                                                                     ** (`aurora/aur_main.py`):
   -                       JSONFormatter                                                         
   -                               FileHandler                                   : feature_engineering.log, risk_management.log, decision_making.log, execution_management.log
   -                                                                                                                                  
   -              event_chain.log    JSON                                                                

2. **                   feature_engineering             ** (`apps/reference/domains/feature_engineering/feature_engineering.py`):
   -                           chain_logger      uuid
   -                                           RID                 on_market_tick
   -                                                                                                ,                                       
   -                                   RID,                  ,           ,             ,                            

3. **                   risk_management             ** (`apps/reference/domains/risk_management/risk_management.py`):
   -                           chain_logger      uuid
   -                                           RID                 on_features_calculated
   -                                                                                 /                                                     
   -                                                                                                                    

4. **                   decision_making             ** (`apps/reference/domains/decision_making/decision_making.py`):
   -                           chain_logger      uuid
   -                                           RID                                                      (on_features, on_risk, on_portfolio, on_regime)
   -                                                                                                                 
   -                                                                                           (insufficient_equity, risk_not_allowed, signal_neutral, position_block, regime_filters, liquidation_guard,         )
   -                                                                                                                         

5. **                   execution_management             ** (`apps/reference/domains/execution_management/execution_management.py`):
   -                                                                                                                       
   -                                                                                      EVT:TRADE_INTENT_PROPOSED
   -                                                  execution_position FSM                                               

**                    **:
-                                               -                                                                                              
-                            JSON-                                                     event_chain.log                         RID
-                                                                                                                                                    
-                  WHY-                                                                                                  
-                                                                                                      
-                              execution_management                                execution_position FSM

**                  **:
- Main Logging: `aurora/aur_main.py` (JSONFormatter, domain handlers, event chain)
- Feature Engineering: `apps/reference/domains/feature_engineering/feature_engineering.py`
- Risk Management: `apps/reference/domains/risk_management/risk_management.py`
- Decision Making: `apps/reference/domains/decision_making/decision_making.py`
- Execution Management: `apps/reference/domains/execution_management/execution_management.py`
- Event Chain Log: `logs/event_chain.log` (JSON format with RID correlation)

---