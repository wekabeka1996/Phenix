#            Execution Position (                                 )

##

**                                       :** `execution_position`
**            :** FSMP-P1-T02
**                          :**

##

           `execution_position`                                                                    Aurora.                                        FSM                                                                          (Open, Manage, Close)                                     ,                                                                                                                                                 .

###
-                                                                 Binance API
-                                                                   (                  /                    /                )
-
-                                          WAL        disaster recovery

##

###

#### ExecPosFSM (                                       )
                                      ,                                    FSM                                   .

**                          :**
-                          BinanceAdapter
-                                             FSM
-

**                                          :**
- `hydrate()` -                                      snapshot
- `handle()` -                                                                               FSM

####        FSM

##### OpenFlowFSM (`fsm_open.py`)
**                                :**
**          :** IDLE     OPENING     OPENED
**          :** OPEN     DEC:ORDER_OPEN

##### ManageFlowFSM (`fsm_manage.py`)
**                                :**
**          :** MANAGING     ADJUSTING     MANAGED
**          :** PARTIAL_FILL, FILL, TRADE_EXECUTED     DEC:ORDER_ADJUST

##### CloseFlowFSM (`fsm_close.py`)
**Purpose:** handles manual `CMD:CLOSE` requests only; legacy auto-close timers now live in `ManageFlowFSM`.
**States:** IDLE     CLOSING     DONE
**Events:** CLOSE     DEC:ORDER_CLOSE (manual path)

###

####
```
handle(msg) -> route to appropriate flow
              OPEN     open_flow.handle()
              TRADE_EXECUTED/FILL     manage_flow.handle()
              CLOSE     close_flow.handle()
```

####
```
DECISION made     _execute_decision()
              Safety guardrail
                           adapter.create_order()
                             feedback
                           EVT:ORDER_ACCEPTED        ERR:EXECUTION_FAILED
```

## FSM

###

#### DEC:ORDER_OPEN
**              :** OpenFlowFSM
**            :**                OPEN
**Payload:**

#### DEC:ORDER_ADJUST
**              :** ManageFlowFSM
**            :**            FILL/PARTIAL_FILL
**Payload:**

#### DEC:ORDER_CLOSE
**Emitted by:** ManageFlowFSM (automatic rules) / CloseFlowFSM (manual CMD:CLOSE)
**Triggers:**    TRACKING/WAIT_MODE rule hits or explicit CLOSE command
**Payload:**

#### EVT:ORDER_ACCEPTED
**              :** ExecPosFSM
**            :**                                                           adapter
**Payload:**

#### ERR:EXECUTION_FAILED
**              :** ExecPosFSM
**            :**                                              adapter
**Payload:**                                                         decision

###

#### CMD:OPEN
**              :** Execution Management
**                        :**
**              :**                       OpenFlowFSM

#### CMD:ADJUST
**              :** Execution Management
**                        :**
**              :**                       ManageFlowFSM

#### CMD:CLOSE
**              :** Execution Management
**                        :**
**              :**                       CloseFlowFSM

#### EVT:TRADE_EXECUTED
**              :** Account Observer
**                        :**
**              :**                                  ManageFlowFSM

##

###                        '

#### Execution Management
- **        :** CMD:OPEN, CMD:ADJUST, CMD:CLOSE
- **          :** DEC:ORDER_OPEN, DEC:ORDER_ADJUST, DEC:ORDER_CLOSE
- **                        :**
- **              :**

#### Account Observer
- **        :** EVT:TRADE_EXECUTED
- **                        :**
- **              :**

#### Position Tracking
- **          :** EVT:POSITION_UPDATED
- **                        :**
- **              :**

###
                        Execution Management                          Account Observer                                .

## Safety Guardrails

### Hybrid Mode Protection
```python
if mode == "hybrid_live_data_testnet_exec":
    if "testnet" not in adapter.base_url:
        # BLOCK ORDER EXECUTION
        emit ERR:FATAL_CONFIG_MISMATCH
```

**        :**                                                                                                             .

### Shadow Mode
                              API                                                             shadow mode (                                            ).

##

###
```yaml
domain_configuration:
  execution_position:
    trading_mode: "testnet"  #                  testnet

binance_api:
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"

trading:
  execution:
    cooldown_ms: 1000
    guard_enabled: true
```

###
- **live:**
- **testnet:**
- **shadow:**                                              (                              API             )

## WAL      Disaster Recovery

### WAL Integration
```python
if result and result.op == "DEC":
    wal.append(result.model_dump())
```

**        :**                                                                                           .

### Hydration
```python
hydrate(position_data) -> restore FSM states
```

**        :**                                                                                   .

##

###
-                                      /
- Success rate
-
-                    guardrail triggers

###
- **                        :**                    FSM,
- **                        :** Guardrail triggers, shadow mode
- **              :** Execution failures, API errors

##

###
1. **API               :**                                                   shadow mode
2. **FSM               :**
3. **Config               :** Fallback      shadow mode

### Graceful degradation
                                                                                                                .

##

###
-                                        FSM
-                    safety guardrails
-                      WAL integration

###
-                                   FSM
-
-                      error handling

##

### Per-Symbol FSM Instances
                                                            3 FSM,                          :
-
-
-

### Command Routing Pattern
                                                                                                 FSM                  :
-                           (OPEN/MANAGE/CLOSE)
-
-

### Async Execution
                                                           :
-
-                                             multiple
-              responsiveness
