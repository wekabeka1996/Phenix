# LIFECYCLE_AUDIT.md -  ê É ¥ ∏ Ç  Ç         ∏   æ ≤ ∫ ∏  ∂ ∏ ∑ Ω µ Ω Ω æ ≥ æ  Ü ∏ ∫ ª    æ   ¥ µ    

## 1.  ¢ µ ∫ É â   è  Ç         ∏   æ ≤ ∫  

###  ì µ Ω µ     Ü ∏ è RID/Corr_ID
- ** ì ¥ µ  ≥ µ Ω µ   ∏   É µ Ç   è**: `vfoundation/core/protocol.py:15` - `rid: str = Field(default_factory=lambda: str(uuid.uuid4()))`
- ** ü µ   µ ¥   á    º µ ∂ ¥ É  ¥ æ º µ Ω   º ∏**: RID  ∫ æ   ∏   É µ Ç   è  ∏ ∑  ≤ Ö æ ¥ è â µ ≥ æ Message  ≤  ∏   Ö æ ¥ è â ∏ µ (`rid=msg.rid`)
- ** ü   ∏ º µ   ã  Ç æ á µ ∫  ≥ µ Ω µ     Ü ∏ ∏**:
  -  ù   á   ª å Ω ã π ASK  æ Ç decision_making
  - EVT  æ Ç market_data/feature_engineering
  - CMD  æ Ç risk_management

###  õ æ ≥ ∏   æ ≤   Ω ∏ µ  º æ º µ Ω Ç æ ≤  ∂ ∏ ∑ Ω µ Ω Ω æ ≥ æ  Ü ∏ ∫ ª  

#### TRADE_INTENT
- ** ì ¥ µ**: `apps/reference/domains/execution_position/aurora_log_adapter.py:log_trade_intent()`
- ** ö æ ≥ ¥  **:  ü æ   ª µ DEC:OPEN  æ Ç execution_position FSM
- ** ü æ ª è**: rid, symbol, side, probability, size_usd, price, quantity, risk_score, features

#### CMD:OPEN
- ** ì ¥ µ**: `apps/reference/domains/execution_position/fsm.py:handle()` ‚Üí `open_flow.handle(msg)`
- ** ö æ ≥ ¥  **:  ü   ∏ Ö æ ¥ ∏ Ç CMD:OPEN  æ Ç decision_making
- ** ü æ ª è**: symbol, side, qty, price, order_type, tif, idempotent_key

#### DEC:OPEN
- ** ì ¥ µ**: `apps/reference/domains/execution_position/fsm_open.py:handle()`
- ** ö æ ≥ ¥  **:  ü æ   ª µ      æ Ö æ ∂ ¥ µ Ω ∏ è guards (min_notional, cooldown, qty/price steps)
- ** ü æ ª è**: symbol, side, qty, order_type, price?, tif?, idempotent_key

#### Exchange ACK
- ** ì ¥ µ**: `apps/reference/domains/execution_position/fsm.py:_execute_decision()`
- ** ö æ ≥ ¥  **:  ü æ   ª µ  É     µ à Ω æ ≥ æ `adapter.place_market_entry()`
- ** ü æ ª è**: order_id  ∏ ∑ Binance response,  Ω æ  Ω µ  ª æ ≥ ∏   É µ Ç   è  è ≤ Ω æ    RID

#### Partial/Full FILL
- ** ì ¥ µ**: `apps/reference/domains/account_observer.py` ‚Üí EVT:FILL/PARTIAL_FILL
- ** ö æ ≥ ¥  **:  ü   ∏    æ ª É á µ Ω ∏ ∏ trade updates  æ Ç Binance WebSocket
- ** ü æ ª è**: symbol, side, qty, price, order_id,  Ω æ  ∫ æ     µ ª è Ü ∏ è    RID  á µ   µ ∑ order_id?

####  ü æ   Ç   Ω æ ≤ ∫   SL/TP
- ** ì ¥ µ**: `apps/reference/domains/execution_position/fsm.py:_execute_decision()`
- ** ö æ ≥ ¥  **:  ü æ   ª µ entry order, `adapter.place_stop_market_close_position()`  ∏ `adapter.place_take_profit_market_close_position()`
- ** ü æ ª è**: sl_id, tp_id  ≥ µ Ω µ   ∏   É é Ç   è  á µ   µ ∑ `generate_client_order_id()`,  Ω æ  Ω µ    ≤ è ∑ ã ≤   é Ç   è    entry order_id

###  ° Ö µ º    ∫ æ     µ ª è Ü ∏ ∏ (Mermaid)

```mermaid
sequenceDiagram
    participant DM as decision_making
    participant EP as execution_position
    participant BA as BinanceAdapter
    participant AO as account_observer

    Note over DM,AO: RID = uuid4()  ≥ µ Ω µ   ∏   É µ Ç   è  ≤ Message.__init__

    DM->>EP: CMD:OPEN (rid, symbol, side, qty, ...)
    EP->>EP: OpenFlowFSM guards check
    EP->>DM: DEC:OPEN (rid, symbol, side, qty, ...)
    EP->>EP: aurora_log_adapter.log_trade_intent(rid, ...)

    EP->>BA: place_market_entry() async
    BA->>EP: response with order_id
    Note over EP: Exchange ACK - order_id    æ ª É á µ Ω,  Ω æ  Ω µ  ª æ ≥ ∏   É µ Ç   è    RID

    AO->>EP: EVT:FILL/PARTIAL_FILL (order_id, qty, price, ...)
    Note over AO,EP:  ö æ     µ ª è Ü ∏ è  á µ   µ ∑ order_id,  Ω æ RID  Ω µ    µ   µ ¥   µ Ç   è  ≤ EVT

    EP->>BA: place_stop_market_close_position() async
    EP->>BA: place_take_profit_market_close_position() async
    BA->>EP: SL/TP responses with sl_id, tp_id
    Note over EP: SL/TP order_ids  ≥ µ Ω µ   ∏   É é Ç   è,  Ω æ  Ω µ    ≤ è ∑ ã ≤   é Ç   è    entry order_id
```

## 2.  ü   æ ± µ ª ã  ∏  ¥ É ± ª ∏

###  û Ç   É Ç   Ç ≤ É é â ∏ µ  ∑ ≤ µ Ω å è
1. **Exchange ACK**:  ü æ ª É á µ Ω ∏ µ order_id  æ Ç Binance  Ω µ  ª æ ≥ ∏   É µ Ç   è    RID.  ¢ æ ª å ∫ æ  ≤ _execute_decision LOG.info,  Ω æ  ± µ ∑    Ç   É ∫ Ç É   ∏   æ ≤   Ω Ω æ ≥ æ  ª æ ≥  .
2. **OCO Group ID**: SL  ∏ TP orders  Ω µ    ≤ è ∑ ã ≤   é Ç   è    entry order_id  á µ   µ ∑ OCO group. Binance    æ ¥ ¥ µ   ∂ ∏ ≤   µ Ç OCO,  Ω æ  ∫ æ ¥  ∏     æ ª å ∑ É µ Ç  æ Ç ¥ µ ª å Ω ã µ STOP_MARKET  ∏ TAKE_PROFIT_MARKET.
3. **Parent ClientOrderId**: SL/TP orders  Ω µ  ∏ º µ é Ç parent_client_order_id,  É ∫   ∑ ã ≤   é â µ ≥ æ  Ω   entry order.
4. **Partial FILL correlation**: EVT:FILL  æ Ç account_observer    æ ¥ µ   ∂ ∏ Ç order_id,  Ω æ  Ω µ RID  æ   ∏ ≥ ∏ Ω   ª å Ω æ ≥ æ CMD:OPEN.
5. **Retry/Fallback correlation**:  ü   ∏ retry TP ( ∏ ∑- ∑   -2021),  Ω æ ≤ ã π order_id  Ω µ    ≤ è ∑ ã ≤   µ Ç   è     æ   ∏ ≥ ∏ Ω   ª å Ω ã º.

###  ü æ ª è  µ   Ç å,  Ω æ  Ω µ      æ ∫ ∏ ¥ ã ≤   é Ç   è
1. **idempotent_key**:  ü µ   µ ¥   µ Ç   è  ∏ ∑ CMD:OPEN  ≤ DEC:OPEN,  Ω æ  Ω µ  ≤ SL/TP orders.
2. **span_id/parent_span_id**:  û     µ ¥ µ ª µ Ω ã  ≤ Message,  Ω æ  Ω µ  ∏     æ ª å ∑ É é Ç   è  ¥ ª è tracing.
3. **why_explain_ref**:  î ª è  ¥ µ Ç   ª å Ω æ ≥ æ  æ ± ä è   Ω µ Ω ∏ è,  Ω æ  Ω µ  ∑     æ ª Ω è µ Ç   è  ≤ execution logs.

## 3.  ü ª   Ω AUR-004 (additive-only correlation)

###  ü   µ ¥ ª   ≥   µ º ã µ    æ ª è/   ≤ è ∑ ∏
```python
#  í Message.pld  ¥ ª è DEC:OPEN  ∏ EVT
{
    "corr_id": "uuid4()",  #  ù æ ≤ ã π correlation ID  ¥ ª è  ≤   µ π  Ü µ   æ á ∫ ∏
    "parent_client_order_id": null,  #  î ª è SL/TP -  É ∫   ∑ ã ≤   µ Ç  Ω   entry
    "oco_group_id": "uuid4()",  #  ì   É        ¥ ª è entry + SL + TP
    "link_ack_id": "order_id  æ Ç exchange",  #  ° ≤ è ∑ å DEC:OPEN ‚Üî ACK
    "link_fill_id": "order_id",  #  î ª è EVT:FILL correlation
}
```

###  ¢ æ á ∫ ∏  ∫ æ     µ ª è Ü ∏ ∏ (hooks)
1. ** í OpenFlowFSM.handle()**:  ü   ∏  ≥ µ Ω µ     Ü ∏ ∏ DEC:OPEN  ¥ æ ±   ≤ ∏ Ç å `corr_id`, `oco_group_id`
2. ** í _execute_decision()**:  ü æ   ª µ place_market_entry    æ Ö     Ω ∏ Ç å `entry_order_id`,    µ   µ ¥   Ç å  ≤ SL/TP  ∫   ∫ `parent_client_order_id`
3. ** í account_observer**:  ü   ∏  ≥ µ Ω µ     Ü ∏ ∏ EVT:FILL  ¥ æ ±   ≤ ∏ Ç å `corr_id`  ∏ ∑ lookup    æ order_id
4. ** í aurora_log_adapter**:  õ æ ≥ ∏   æ ≤   Ç å corr_id  ≤ º µ   Ç æ/ ≤ º µ   Ç µ    rid

###  ° æ ≥ ª     æ ≤   Ω ∏ µ    L1-ORDER-LOGGER
-  ¶ µ ª µ ≤ ã µ    æ ª è: corr_id, oco_group_id, parent_client_order_id, link_ack_id
-  ò ∑ ± µ ≥   Ç å  ¥ É ± ª ∏   æ ≤   Ω ∏ è:  ∏     æ ª å ∑ æ ≤   Ç å    É â µ   Ç ≤ É é â ∏ µ rid  ∫   ∫ fallback, corr_id  ∫   ∫ primary  ¥ ª è tracing

## 4. L3-METRICS-SUMMARY ( ¥ ∏ ∑   π Ω)

###  ú ∏ Ω ∏- Ω   ± æ    º µ Ç   ∏ ∫
- **open_success_rate**: ( É     µ à Ω ã µ DEC:OPEN) / ( ≤   µ CMD:OPEN) * 100
- **mean_time_to_open**:  °   µ ¥ Ω µ µ  ≤   µ º è  æ Ç CMD:OPEN  ¥ æ DEC:OPEN ( º  )
- **defer_rate**: ( æ Ç ª æ ∂ µ Ω Ω ã µ CMD:OPEN) / ( ≤   µ CMD:OPEN) * 100
- **block_rate**: ( ∑   ± ª æ ∫ ∏   æ ≤   Ω Ω ã µ CMD:OPEN) / ( ≤   µ CMD:OPEN) * 100
- **retry_count**:  ö æ ª ∏ á µ   Ç ≤ æ retry      ∏      ∑ º µ â µ Ω ∏ ∏ orders
- **qos_cooldown_hits**:  ö æ ª ∏ á µ   Ç ≤ æ  æ Ç ∫ ª æ Ω µ Ω ∏ π  ∏ ∑- ∑   cooldown

###  ò   Ç æ á Ω ∏ ∫ ∏  º µ Ç   ∏ ∫
- **open_success_rate**:  ò ∑ OpenFlowFSM._metrics["fsm_open_decisions_total"] /  æ ± â µ µ CMD:OPEN ( Ω É ∂ µ Ω    á µ Ç á ∏ ∫  ≤ Ö æ ¥ è â ∏ Ö)
- **mean_time_to_open**: Timestamp CMD:OPEN - timestamp DEC:OPEN,    ≥   µ ≥ ∏   æ ≤   Ç å  ≤ metrics_collector
- **defer_rate/block_rate**:  ò ∑ QoS  ª æ ≥ ∏ ∫ ∏  ≤ decision_making ( µ   ª ∏  µ   Ç å)
- **retry_count**:  í _execute_decision      ∏ retry TP  ∏ ∑- ∑   -2021
- **qos_cooldown_hits**:  ò ∑ OpenFlowFSM guards

### JSON-   µ   æ   Ç: reports/summary_gate_status.json
```json
{
  "timestamp": "2025-10-31T12:00:00Z",
  "period_hours": 24,
  "metrics": {
    "open_success_rate": 95.2,
    "mean_time_to_open_ms": 45.3,
    "defer_rate": 2.1,
    "block_rate": 1.8,
    "retry_count": 12,
    "qos_cooldown_hits": 8
  },
  "breakdown_by_symbol": {
    "BTCUSDT": {
      "open_success_rate": 96.1,
      "cmd_open_count": 150,
      "dec_open_count": 144
    },
    "ETHUSDT": {
      "open_success_rate": 94.3,
      "cmd_open_count": 120,
      "dec_open_count": 113
    }
  },
  "alerts": [
    "ETHUSDT defer_rate > 5% threshold"
  ]
}
```

 ê ≥   µ ≥   Ü ∏ è  ≤ `tools/metrics_summary.py`:
-  ß ∏ Ç   Ç å  ∏ ∑ Prometheus /metrics/json
-  ò ª ∏  ∏ ∑ WAL  ª æ ≥ æ ≤
-  ì   É     ∏   æ ≤   Ç å    æ symbol,    á ∏ Ç   Ç å      æ Ü µ Ω Ç ã
-  ó     ∏   ã ≤   Ç å JSON  Ñ   π ª

## 5.  °   ∏   æ ∫  Ñ   π ª æ ≤  ¥ ª è  ± É ¥ É â ∏ Ö        ≤ æ ∫

###  û   Ω æ ≤ Ω ã µ  Ñ   π ª ã  ¥ ª è AUR-004 correlation:
- `vfoundation/core/protocol.py`:  î æ ±   ≤ ∏ Ç å    æ ª è corr_id, oco_group_id  ≤ Message
- `apps/reference/domains/execution_position/fsm_open.py`:  ì µ Ω µ   ∏   æ ≤   Ç å corr_id/oco_group_id  ≤ DEC:OPEN
- `apps/reference/domains/execution_position/fsm.py`:  ü µ   µ ¥   Ç å parent_client_order_id  ≤ SL/TP orders
- `apps/reference/domains/account_observer.py`:  î æ ±   ≤ ∏ Ç å corr_id lookup  ≤ EVT:FILL
- `apps/reference/domains/execution_position/aurora_log_adapter.py`:  õ æ ≥ ∏   æ ≤   Ç å corr_id

###  §   π ª ã  ¥ ª è L3-METRICS-SUMMARY:
- `tools/metrics_summary.py`:  ° æ ∑ ¥   Ç å  Ω æ ≤ ã π  Ñ   π ª  ¥ ª è    ≥   µ ≥   Ü ∏ ∏  ∏  ≥ µ Ω µ     Ü ∏ ∏ JSON
- `apps/reference/domains/execution_position/fsm_open.py`:  î æ ±   ≤ ∏ Ç å timestamp tracking  ¥ ª è mean_time_to_open
- `apps/reference/domains/execution_position/metrics_collector.py`:  †     à ∏   ∏ Ç å  º µ Ç   ∏ ∫ ∏  ¥ ª è retry_count, qos_hits
- `vfoundation/obs/debug_api.py`:  î æ ±   ≤ ∏ Ç å endpoints  ¥ ª è  á Ç µ Ω ∏ è  º µ Ç   ∏ ∫  ≤ tools/

###  ° æ   É Ç   Ç ≤ É é â ∏ µ  Ñ   π ª ã:
- `docs/ORDER_LIFECYCLE_CORRELATION.md`:  î æ ∫ É º µ Ω Ç   Ü ∏ è  Ω æ ≤ æ π    Ö µ º ã correlation
- `tests/test_order_lifecycle_correlation.py`:  ¢ µ   Ç ã  ¥ ª è      æ ≤ µ   ∫ ∏ corr_id propagation
- `tests/test_metrics_summary.py`:  ¢ µ   Ç ã  ¥ ª è JSON    µ   æ   Ç  </content>
<parameter name="filePath">c:\Users\user\Music\Phenix\artifacts\LIFECYCLE_AUDIT.md
