#  î æ º µ Ω Execution Position ( í ∏ ∫ æ Ω   Ω Ω è  ü æ ∑ ∏ Ü ñ π)

##  ó   ≥   ª å Ω    ñ Ω Ñ æ   º   Ü ñ è

** Ü ¥ µ Ω Ç ∏ Ñ ñ ∫   Ç æ    ¥ æ º µ Ω É:** `execution_position`  
** í µ     ñ è:** FSMP-P1-T02  
** † æ ª å  ≤    ∏   Ç µ º ñ:**  í ∏ ∫ æ Ω   Ω Ω è  Ç æ   ≥ æ ≤ ∏ Ö  æ   µ     Ü ñ π  Ç    É       ≤ ª ñ Ω Ω è    æ ∑ ∏ Ü ñ è º ∏

##  ê   Ö ñ Ç µ ∫ Ç É   Ω      æ ª å

 î æ º µ Ω `execution_position`  î  ≤ ∏ ∫ æ Ω   ≤ á ∏ º  è ¥   æ º  Ç æ   ≥ æ ≤ æ ó    ∏   Ç µ º ∏ Aurora.  í ñ Ω    µ   ª ñ ∑ É î    ∫ ª   ¥ Ω É FSM      Ö ñ Ç µ ∫ Ç É   É  ∑  Ç   å æ º    æ ∫   µ º ∏ º ∏    æ Ç æ ∫   º ∏ (Open, Manage, Close)  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ    ∏ º ≤ æ ª É,  ∑   ± µ ∑   µ á É é á ∏  Ω   ¥ ñ π Ω µ  ≤ ∏ ∫ æ Ω   Ω Ω è  æ   ¥ µ   ñ ≤  Ç    É       ≤ ª ñ Ω Ω è  ∂ ∏ Ç Ç î ≤ ∏ º  Ü ∏ ∫ ª æ º    æ ∑ ∏ Ü ñ π.

###  í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å
-  í ∏ ∫ æ Ω   Ω Ω è  Ç æ   ≥ æ ≤ ∏ Ö  ñ Ω Ç µ Ω Ç ñ ≤  á µ   µ ∑ Binance API
-  £       ≤ ª ñ Ω Ω è  ∂ ∏ Ç Ç î ≤ ∏ º  Ü ∏ ∫ ª æ º    æ ∑ ∏ Ü ñ π ( ≤ ñ ¥ ∫   ∏ Ç Ç è/ É       ≤ ª ñ Ω Ω è/ ∑   ∫   ∏ Ç Ç è)
-  ó   ± µ ∑   µ á µ Ω Ω è  ñ ¥ µ º   æ Ç µ Ω Ç Ω æ   Ç ñ  Ç    ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    ñ   ª è  ∑ ± æ ó ≤
-  Ü Ω Ç µ ≥     Ü ñ è  ∑    ∏   Ç µ º æ é WAL  ¥ ª è disaster recovery

##  ° Ç   É ∫ Ç É      ¥ æ º µ Ω É

###  û   Ω æ ≤ Ω ñ  ∫ æ º   æ Ω µ Ω Ç ∏

#### ExecPosFSM ( ≥ æ ª æ ≤ Ω ∏ π  æ   ∫ µ   Ç     Ç æ  )
 ì æ ª æ ≤ Ω ∏ π  ∫ ª      ¥ æ º µ Ω É,  â æ  É       ≤ ª è î  Ç   å æ º   FSM    æ Ç æ ∫   º ∏  Ω      ∏ º ≤ æ ª.

** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è:**
-  ù   ª   à Ç É ≤   Ω Ω è BinanceAdapter  ∑   ª µ ∂ Ω æ  ≤ ñ ¥  ¥ æ º µ Ω Ω æ ≥ æ    µ ∂ ∏ º É
-  Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è  ∫ æ ª µ ∫ Ü ñ π FSM    æ Ç æ ∫ ñ ≤  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ    ∏ º ≤ æ ª É
-  ù   ª   à Ç É ≤   Ω Ω è  ª æ ≥ É ≤   Ω Ω è  Ç    º µ Ç   ∏ ∫

** ú µ Ç æ ¥ ∏  ∂ ∏ Ç Ç î ≤ æ ≥ æ  Ü ∏ ∫ ª É:**
- `hydrate()` -  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É  ∑ snapshot
- `handle()` -  º     à   É Ç ∏ ∑   Ü ñ è    æ ≤ ñ ¥ æ º ª µ Ω å  ¥ æ  ≤ ñ ¥   æ ≤ ñ ¥ Ω ∏ Ö FSM

####  ¢   ∏ FSM    æ Ç æ ∫ ∏  Ω      ∏ º ≤ æ ª

##### OpenFlowFSM (`fsm_open.py`)
** í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å:**  í ñ ¥ ∫   ∏ Ç Ç è  Ω æ ≤ ∏ Ö    æ ∑ ∏ Ü ñ π  
** ° Ç   Ω ∏:** IDLE ‚Üí OPENING ‚Üí OPENED  
** ü æ ¥ ñ ó:** OPEN ‚Üí DEC:ORDER_OPEN

##### ManageFlowFSM (`fsm_manage.py`)
** í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å:**  £       ≤ ª ñ Ω Ω è  ≤ ñ ¥ ∫   ∏ Ç ∏ º ∏    æ ∑ ∏ Ü ñ è º ∏  
** ° Ç   Ω ∏:** MANAGING ‚Üí ADJUSTING ‚Üí MANAGED  
** ü æ ¥ ñ ó:** PARTIAL_FILL, FILL, TRADE_EXECUTED ‚Üí DEC:ORDER_ADJUST

##### CloseFlowFSM (`fsm_close.py`)
** í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å:**  ó   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ π  
** ° Ç   Ω ∏:** CLOSING ‚Üí CLOSED  
** ü æ ¥ ñ ó:** CLOSE ‚Üí DEC:ORDER_CLOSE

###  í Ω É Ç   ñ à Ω è      Ö ñ Ç µ ∫ Ç É    

####  ú     à   É Ç ∏ ∑   Ü ñ è  ∫ æ º   Ω ¥
```
handle(msg) -> route to appropriate flow
    ‚îú‚î ‚î  OPEN ‚Üí open_flow.handle()
    ‚îú‚î ‚î  TRADE_EXECUTED/FILL ‚Üí manage_flow.handle() + close_flow.handle()
    ‚îú‚î ‚î  CLOSE ‚Üí close_flow.handle()
    ‚îî‚î ‚î   ñ Ω à ñ ‚Üí manage_flow.handle()
```

####  ê   ∏ Ω Ö   æ Ω Ω µ  ≤ ∏ ∫ æ Ω   Ω Ω è
```
DECISION made ‚Üí _execute_decision()
    ‚îú‚î ‚î  Safety guardrail    µ   µ ≤ ñ   ∫  
    ‚îú‚î ‚î   í ∏ ∫ ª ∏ ∫ adapter.create_order()
    ‚îú‚î ‚î   û ±   æ ± ∫   feedback
    ‚îî‚î ‚î   ï º ñ   ñ è EVT:ORDER_ACCEPTED    ± æ ERR:EXECUTION_FAILED
```

## FSM    æ ¥ ñ ó

###  ì µ Ω µ   æ ≤   Ω ñ    æ ¥ ñ ó

#### DEC:ORDER_OPEN
** î ∂ µ   µ ª æ:** OpenFlowFSM  
** ¢   ∏ ≥ µ  :**  ö æ º   Ω ¥   OPEN  ∑  ≤   ª ñ ¥ Ω ∏ º ∏          º µ Ç     º ∏  
**Payload:**  ü       º µ Ç   ∏  æ   ¥ µ      ¥ ª è  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó

#### DEC:ORDER_ADJUST
** î ∂ µ   µ ª æ:** ManageFlowFSM  
** ¢   ∏ ≥ µ  :**  ü æ ¥ ñ ó FILL/PARTIAL_FILL  ¥ ª è  É       ≤ ª ñ Ω Ω è    æ ∑ ∏ Ü ñ î é  
**Payload:**  ü       º µ Ç   ∏  ∫ æ   ∏ ≥ É ≤   ª å Ω æ ≥ æ  æ   ¥ µ    

#### DEC:ORDER_CLOSE
** î ∂ µ   µ ª æ:** CloseFlowFSM  
** ¢   ∏ ≥ µ  :**  ö æ º   Ω ¥   CLOSE    ± æ  É º æ ≤ ∏  ∑   ∫   ∏ Ç Ç è  
**Payload:**  ü       º µ Ç   ∏  æ   ¥ µ      ¥ ª è  ∑   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó

#### EVT:ORDER_ACCEPTED
** î ∂ µ   µ ª æ:** ExecPosFSM    ñ   ª è  ≤ ∏ ∫ æ Ω   Ω Ω è  
** ¢   ∏ ≥ µ  :**  £     ñ à Ω µ    Ç ≤ æ   µ Ω Ω è  æ   ¥ µ      á µ   µ ∑ adapter  
**Payload:**  ü ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω Ω è  ≤ ñ ¥  ± ñ   ∂ ñ

#### ERR:EXECUTION_FAILED
** î ∂ µ   µ ª æ:** ExecPosFSM      ∏    æ º ∏ ª Ü ñ  
** ¢   ∏ ≥ µ  :**  ü æ º ∏ ª ∫    ≤ ∏ ∫ æ Ω   Ω Ω è  á µ   µ ∑ adapter  
**Payload:**  î µ Ç   ª ñ    æ º ∏ ª ∫ ∏  Ç    æ   ∏ ≥ ñ Ω   ª å Ω   decision

###  °   æ ∂ ∏ ≤   Ω ñ    æ ¥ ñ ó

#### CMD:OPEN
** î ∂ µ   µ ª æ:** Execution Management  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  Ü Ω ñ Ü ñ   Ü ñ è  ≤ ñ ¥ ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó  
** û ±   æ ± ∫  :**  ü µ   µ ¥   á    ¥ æ OpenFlowFSM

#### CMD:ADJUST
** î ∂ µ   µ ª æ:** Execution Management  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  ö æ   ∏ ≥ É ≤   Ω Ω è  ñ   Ω É é á æ ó    æ ∑ ∏ Ü ñ ó  
** û ±   æ ± ∫  :**  ü µ   µ ¥   á    ¥ æ ManageFlowFSM

#### CMD:CLOSE
** î ∂ µ   µ ª æ:** Execution Management  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  ó   ∫   ∏ Ç Ç è    æ ∑ ∏ Ü ñ ó  
** û ±   æ ± ∫  :**  ü µ   µ ¥   á    ¥ æ CloseFlowFSM

#### EVT:TRADE_EXECUTED
** î ∂ µ   µ ª æ:** Account Observer  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  ü ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω Ω è  ≤ ∏ ∫ æ Ω   Ω Ω è  Ç   µ π ¥ É  
** û ±   æ ± ∫  :**  û Ω æ ≤ ª µ Ω Ω è    Ç   Ω É  ≤ ManageFlowFSM

##  í ∑   î º æ ¥ ñ è  ∑  ñ Ω à ∏ º ∏  ¥ æ º µ Ω   º ∏

###  ° ∏ Ω Ö   æ Ω Ω ñ  ∑ ≤' è ∑ ∫ ∏

#### Execution Management
- ** í Ö ñ ¥:** CMD:OPEN, CMD:ADJUST, CMD:CLOSE
- ** í ∏ Ö ñ ¥:** DEC:ORDER_OPEN, DEC:ORDER_ADJUST, DEC:ORDER_CLOSE
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  ∫ æ º   Ω ¥  Ω    ≤ ∏ ∫ æ Ω   Ω Ω è  æ   µ     Ü ñ π
- ** ß     Ç æ Ç  :**  ü æ ¥ ñ î ≤ æ

#### Account Observer
- ** í Ö ñ ¥:** EVT:TRADE_EXECUTED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  ü ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω Ω è  ≤ ∏ ∫ æ Ω   Ω Ω è  Ç   µ π ¥ ñ ≤
- ** ß     Ç æ Ç  :**  ü æ ¥ ñ î ≤ æ      ∏  Ω æ ≤ ∏ Ö  Ç   µ π ¥   Ö

#### Position Tracking
- ** í ∏ Ö ñ ¥:** EVT:POSITION_UPDATED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  Ü Ω Ñ æ   º É ≤   Ω Ω è      æ  ∑ º ñ Ω ∏    æ ∑ ∏ Ü ñ π
- ** ß     Ç æ Ç  :**  ü ñ   ª è  ∫ æ ∂ Ω æ ≥ æ  ≤ ∏ ∫ æ Ω   Ω Ω è

###  ê   ∏ Ω Ö   æ Ω Ω ñ  ∑   ª µ ∂ Ω æ   Ç ñ
 ó   ª µ ∂ ∏ Ç å  ≤ ñ ¥ Execution Management  ¥ ª è  ∫ æ º   Ω ¥  Ç   Account Observer  ¥ ª è    ñ ¥ Ç ≤ µ   ¥ ∂ µ Ω å.

## Safety Guardrails

### Hybrid Mode Protection
```python
if mode == "hybrid_live_data_testnet_exec":
    if "testnet" not in adapter.base_url:
        # BLOCK ORDER EXECUTION
        emit ERR:FATAL_CONFIG_MISMATCH
```

** ú µ Ç  :**  ó     æ ± ñ ≥   Ω Ω è  ≤ ∏ ∫ æ Ω   Ω Ω é  ± æ π æ ≤ ∏ Ö  æ   ¥ µ   ñ ≤  ≤  ≥ ñ ±   ∏ ¥ Ω æ º É    µ ∂ ∏ º ñ.

### Shadow Mode
 ü   ∏  ≤ ñ ¥   É Ç Ω æ   Ç ñ API  ∫ ª é á ñ ≤    ≤ Ç æ º   Ç ∏ á Ω æ    µ   µ Ö æ ¥ ∏ Ç å  ≤ shadow mode ( ª æ ≥ É ≤   Ω Ω è  ± µ ∑  ≤ ∏ ∫ æ Ω   Ω Ω è).

##  ö æ Ω Ñ ñ ≥ É     Ü ñ è

###  û   Ω æ ≤ Ω ñ          º µ Ç   ∏
```yaml
domain_configuration:
  execution_position:
    trading_mode: "testnet"  #  ó   ∑ ≤ ∏ á   π testnet  ≤  ≥ ñ ±   ∏ ¥ Ω æ º É    µ ∂ ∏ º ñ

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

###  † µ ∂ ∏ º ∏    æ ± æ Ç ∏
- **live:**  í ∏ ∫ æ Ω   Ω Ω è  Ω    ± æ π æ ≤ æ º É      Ö É Ω ∫ É
- **testnet:**  í ∏ ∫ æ Ω   Ω Ω è  Ω    Ç µ   Ç æ ≤ æ º É      Ö É Ω ∫ É
- **shadow:**  õ æ ≥ É ≤   Ω Ω è  ± µ ∑  ≤ ∏ ∫ æ Ω   Ω Ω è (     ∏  ≤ ñ ¥   É Ç Ω æ   Ç ñ API  ∫ ª é á ñ ≤)

## WAL  Ç   Disaster Recovery

### WAL Integration
```python
if result and result.op == "DEC":
    wal.append(result.model_dump())
```

** ú µ Ç  :**  § ñ ∫     Ü ñ è  ≤   ñ Ö    ñ à µ Ω å  ¥ ª è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    ñ   ª è  ∑ ± æ ó ≤.

### Hydration
```python
hydrate(position_data) -> restore FSM states
```

** ú µ Ç  :**  í ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É    æ ∑ ∏ Ü ñ π    ñ   ª è    µ   µ ∑     É   ∫ É.

##  ú æ Ω ñ Ç æ   ∏ Ω ≥  Ç    ¥ ñ   ≥ Ω æ   Ç ∏ ∫  

###  ú µ Ç   ∏ ∫ ∏
-  ö ñ ª å ∫ ñ   Ç å  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö/ ∑   ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π
- Success rate  ≤ ∏ ∫ æ Ω   Ω Ω è  æ   ¥ µ   ñ ≤
-  ° µ   µ ¥ Ω ñ π  á      ≤ ∏ ∫ æ Ω   Ω Ω è
-  ö ñ ª å ∫ ñ   Ç å guardrail triggers

###  õ æ ≥ É ≤   Ω Ω è
- ** Ü Ω Ñ æ   º   Ü ñ π Ω ñ:**  ° Ç ≤ æ   µ Ω Ω è FSM,  ≤ ∏ ∫ æ Ω   Ω Ω è    ñ à µ Ω å
- ** ü æ   µ   µ ¥ ∂ µ Ω Ω è:** Guardrail triggers, shadow mode
- ** ü æ º ∏ ª ∫ ∏:** Execution failures, API errors

##  û ±   æ ± ∫      æ º ∏ ª æ ∫

###  ° Ç     Ç µ ≥ ñ ó  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è
1. **API    æ º ∏ ª ∫ ∏:**  õ æ ≥ É ≤   Ω Ω è  Ç        æ ¥ æ ≤ ∂ µ Ω Ω è  ≤ shadow mode
2. **FSM    æ º ∏ ª ∫ ∏:**  Ü ∑ æ ª è Ü ñ è      æ ± ª µ º Ω æ ≥ æ    ∏ º ≤ æ ª É
3. **Config    æ º ∏ ª ∫ ∏:** Fallback  ¥ æ shadow mode

### Graceful degradation
 ü   ∏      æ ± ª µ º   Ö  ∑  æ ∫   µ º ∏ º ∏    ∏ º ≤ æ ª   º ∏      æ ¥ æ ≤ ∂ É î    æ ± æ Ç É  ∑  ñ Ω à ∏ º ∏.

##  ¢ µ   Ç É ≤   Ω Ω è

###  Ü Ω Ç µ ≥     Ü ñ π Ω ñ  Ç µ   Ç ∏
-  í   ª ñ ¥   Ü ñ è  ≤   ñ Ö  Ç   å æ Ö FSM    æ Ç æ ∫ ñ ≤
-  ü µ   µ ≤ ñ   ∫   safety guardrails
-  ¢ µ   Ç É ≤   Ω Ω è WAL integration

###  ú æ ¥ É ª å Ω ñ  Ç µ   Ç ∏
-  ü µ   µ ≤ ñ   ∫    ∫ æ ∂ Ω æ ≥ æ FSM  æ ∫   µ º æ
-  í   ª ñ ¥   Ü ñ è  º     à   É Ç ∏ ∑   Ü ñ ó  ∫ æ º   Ω ¥
-  ¢ µ   Ç É ≤   Ω Ω è error handling

##  ê   Ö ñ Ç µ ∫ Ç É   Ω ñ  æ   æ ± ª ∏ ≤ æ   Ç ñ

### Per-Symbol FSM Instances
 ö æ ∂ µ Ω    ∏ º ≤ æ ª  º   î  ≤ ª     Ω ∏ π  Ω   ± ñ    ∑ 3 FSM,  â æ  ∑   ± µ ∑   µ á É î:
-  Ü ∑ æ ª è Ü ñ é    Ç   Ω É  º ñ ∂    ∏ º ≤ æ ª   º ∏
-  ù µ ∑   ª µ ∂ Ω µ  º     à Ç   ± É ≤   Ω Ω è
-  °     æ â µ Ω Ω è  ª æ ≥ ñ ∫ ∏  É       ≤ ª ñ Ω Ω è

### Command Routing Pattern
 ¶ µ Ω Ç     ª ñ ∑ æ ≤   Ω    º     à   É Ç ∏ ∑   Ü ñ è  ∫ æ º   Ω ¥  ¥ æ  ≤ ñ ¥   æ ≤ ñ ¥ Ω ∏ Ö FSM  Ω    æ   Ω æ ≤ ñ:
-  ¢ ∏   É  æ   µ     Ü ñ ó (OPEN/MANAGE/CLOSE)
-  ü æ Ç æ á Ω æ ≥ æ    Ç   Ω É    æ ∑ ∏ Ü ñ ó
-  Ü   Ç æ   ñ ó  ≤ ∏ ∫ æ Ω   Ω Ω è

### Async Execution
 ê   ∏ Ω Ö   æ Ω Ω µ  ≤ ∏ ∫ æ Ω   Ω Ω è    ñ à µ Ω å  ¥ ª è:
-  ù µ ± ª æ ∫ É é á æ ó    æ ± æ Ç ∏  æ   Ω æ ≤ Ω æ ≥ æ    æ Ç æ ∫ É
-  ü       ª µ ª å Ω æ ≥ æ  ≤ ∏ ∫ æ Ω   Ω Ω è multiple    ∏ º ≤ æ ª ñ ≤
-  ö     â æ ó responsiveness    ∏   Ç µ º ∏