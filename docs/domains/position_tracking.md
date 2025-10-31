#  î æ º µ Ω Position Tracking ( í ñ ¥   Ç µ ∂ µ Ω Ω è  ü æ ∑ ∏ Ü ñ π)

##  ó   ≥   ª å Ω    ñ Ω Ñ æ   º   Ü ñ è

** Ü ¥ µ Ω Ç ∏ Ñ ñ ∫   Ç æ    ¥ æ º µ Ω É:** `position_tracking`  
** † æ ª å  ≤    ∏   Ç µ º ñ:**  ¶ µ Ω Ç      Ç   Ω É    æ   Ç Ñ µ ª è  Ç      æ ∑     Ö É Ω ∫ É P&L

##  ê   Ö ñ Ç µ ∫ Ç É   Ω      æ ª å

 î æ º µ Ω `position_tracking`  î  Ü µ Ω Ç     ª å Ω ∏ º    Ö æ ≤ ∏ â µ º    Ç   Ω É  Ç æ   ≥ æ ≤ æ ≥ æ    æ   Ç Ñ µ ª è  ≤    ∏   Ç µ º ñ Aurora.  í ñ Ω  ñ Ω Ç µ ≥   É î  ¥   Ω ñ      æ  ≤ ∏ ∫ æ Ω   Ω ñ  Ç   µ π ¥ ∏,  ±   ª   Ω        Ö É Ω ∫ É  Ç      æ ∑ ∏ Ü ñ ó,    æ ∑     Ö æ ≤ É é á ∏ realized/unrealized P&L  Ç      ñ ¥ Ç   ∏ º É é á ∏    ∫ Ç É   ª å Ω ∏ π    Ç   Ω equity.

###  í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å
-  í ñ ¥   Ç µ ∂ µ Ω Ω è  ≤   ñ Ö  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π    æ    ∏ º ≤ æ ª   Ö
-  † æ ∑     Ö É Ω æ ∫ realized  Ç   unrealized P&L
-  ê ≥   µ ≥   Ü ñ è  ¥   Ω ∏ Ö      æ equity    æ   Ç Ñ µ ª è
- WAL  ñ Ω Ç µ ≥     Ü ñ è  ¥ ª è disaster recovery
-  ï º ñ   ñ è  æ Ω æ ≤ ª µ Ω å    Ç   Ω É    æ   Ç Ñ µ ª è

##  ° Ç   É ∫ Ç É      ¥ æ º µ Ω É

###  û   Ω æ ≤ Ω ñ  ∫ æ º   æ Ω µ Ω Ç ∏

#### PositionTracking
 ì æ ª æ ≤ Ω ∏ π  ∫ ª      ¥ æ º µ Ω É,  â æ  É       ≤ ª è î    Ç   Ω æ º    æ   Ç Ñ µ ª è.

** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è:**
-  ü ñ ¥   ∏   ∫    Ω      æ ¥ ñ ó  Ç   µ π ¥ ñ ≤  Ç    æ Ω æ ≤ ª µ Ω å      Ö É Ω ∫ É
-  Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è    Ç   É ∫ Ç É    ¥   Ω ∏ Ö  ¥ ª è    æ ∑ ∏ Ü ñ π  Ç   P&L
-  ù   ª   à Ç É ≤   Ω Ω è WAL  ñ Ω Ç µ ≥     Ü ñ ó

** ú µ Ç æ ¥ ∏  ∂ ∏ Ç Ç î ≤ æ ≥ æ  Ü ∏ ∫ ª É:**
- `start()` -  ∑     É   ∫  ∫ æ º   æ Ω µ Ω Ç É
- `on_trade_executed()` -  æ ±   æ ± ∫    ≤ ∏ ∫ æ Ω   Ω ∏ Ö  Ç   µ π ¥ ñ ≤
- `on_account_update()` -  æ ±   æ ± ∫    æ Ω æ ≤ ª µ Ω å      Ö É Ω ∫ É

###  í Ω É Ç   ñ à Ω è      Ö ñ Ç µ ∫ Ç É    

####  £       ≤ ª ñ Ω Ω è    æ ∑ ∏ Ü ñ è º ∏
```
_positions: Dict[str, Dict[str, Any]]
    ‚îú‚î ‚î  symbol -> position data
    ‚îú‚î ‚î  avg_price:    µ   µ ¥ Ω è  Ü ñ Ω    ≤ Ö æ ¥ É
    ‚îú‚î ‚î  quantity:    æ Ç æ á Ω    ∫ ñ ª å ∫ ñ   Ç å
    ‚îú‚î ‚î  realized_pnl:    µ   ª ñ ∑ ≤   Ω ∏ π P&L
    ‚îî‚î ‚î  venue:  ± ñ   ∂    ≤ ∏ ∫ æ Ω   Ω Ω è
```

#### WAL  ñ Ω Ç µ ≥     Ü ñ è
```
on_trade_executed() -> WAL write first
    ‚îú‚î ‚î   ó     ∏      æ ¥ ñ ó  ≤ WAL    µ   µ ¥  æ ±   æ ± ∫ æ é
    ‚îú‚î ‚î   ö   ∏ Ç ∏ á Ω    ∑ É   ∏ Ω ∫        ∏ WAL failure
    ‚îú‚î ‚î   ë µ ∑   µ   µ   ≤ Ω ñ   Ç å      ∏ disaster recovery
```

## FSM    æ ¥ ñ ó

###  ì µ Ω µ   æ ≤   Ω ñ    æ ¥ ñ ó

#### EVT:PORTFOLIO_STATE_UPDATED
** ß     Ç æ Ç  :**  ü ñ   ª è  ∫ æ ∂ Ω æ ≥ æ EVT:TRADE_EXECUTED  
** ù         ≤ ª µ Ω Ω è:** Decision Making, Risk Management, Audit Trail  

**Payload    Ç   É ∫ Ç É    :**
```json
{
  "ts": 1640995200000,
  "equity": "1000.50",
  "realized_pnl": "25.30",
  "unrealized_pnl": "-5.20",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "quantity": "0.001",
      "avg_price": "50000.00",
      "current_price": "50250.00",
      "unrealized_pnl": "2.50",
      "realized_pnl": "0.00"
    }
  ]
}
```

** û   ∏  :**  ü µ   µ ¥   î    æ ≤ Ω ∏ π    Ç   Ω    æ   Ç Ñ µ ª è    ñ   ª è  ∫ æ ∂ Ω æ ≥ æ  Ç   µ π ¥ É.

###  °   æ ∂ ∏ ≤   Ω ñ    æ ¥ ñ ó

#### EVT:TRADE_EXECUTED
** î ∂ µ   µ ª æ:** Account Observer  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  ¥   Ω ∏ Ö      æ  ≤ ∏ ∫ æ Ω   Ω ñ  Ç   µ π ¥ ∏  ¥ ª è  æ Ω æ ≤ ª µ Ω Ω è    æ ∑ ∏ Ü ñ π  
** ß     Ç æ Ç  :**  ü æ ¥ ñ î ≤ æ      ∏  Ω æ ≤ ∏ Ö  Ç   µ π ¥   Ö

#### EVT:ACCOUNT_UPDATE_RECEIVED
** î ∂ µ   µ ª æ:** Account Balance  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  ¥   Ω ∏ Ö      æ    æ ∑ ∏ Ü ñ ó  ∑  ± ñ   ∂ ñ  
** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É (30    µ ∫)

#### EVT:BALANCE_UPDATE_RECEIVED
** î ∂ µ   µ ª æ:** Account Balance  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  ¥   Ω ∏ Ö      æ  ±   ª   Ω      ∫ Ç ∏ ≤ ñ ≤  
** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É (30    µ ∫)

##  í ∑   î º æ ¥ ñ è  ∑  ñ Ω à ∏ º ∏  ¥ æ º µ Ω   º ∏

###  ° ∏ Ω Ö   æ Ω Ω ñ  ∑ ≤' è ∑ ∫ ∏

#### Account Observer
- ** í Ö ñ ¥:** EVT:TRADE_EXECUTED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  Ç   µ π ¥ ñ ≤  ¥ ª è  æ Ω æ ≤ ª µ Ω Ω è    æ ∑ ∏ Ü ñ π
- ** ß     Ç æ Ç  :**  ü æ ¥ ñ î ≤ æ

#### Account Balance
- ** í Ö ñ ¥:** EVT:ACCOUNT_UPDATE_RECEIVED, EVT:BALANCE_UPDATE_RECEIVED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  ° ∏ Ω Ö   æ Ω ñ ∑   Ü ñ è  ∑  ± ñ   ∂ æ ≤ ∏ º ∏  ¥   Ω ∏ º ∏
- ** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

#### Decision Making
- ** í ∏ Ö ñ ¥:** EVT:PORTFOLIO_STATE_UPDATED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  î   Ω ñ      æ equity  ¥ ª è sizing    ñ à µ Ω å
- ** ß     Ç æ Ç  :**  ü ñ   ª è  ∫ æ ∂ Ω æ ≥ æ  Ç   µ π ¥ É

#### Risk Management
- ** í ∏ Ö ñ ¥:** EVT:PORTFOLIO_STATE_UPDATED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  † æ ∑     Ö É Ω æ ∫    ∏ ∑ ∏ ∫ ñ ≤    æ   Ç Ñ µ ª è
- ** ß     Ç æ Ç  :**  ü ñ   ª è  ∫ æ ∂ Ω æ ≥ æ  Ç   µ π ¥ É

###  ê   ∏ Ω Ö   æ Ω Ω ñ  ∑   ª µ ∂ Ω æ   Ç ñ
 ö   ∏ Ç ∏ á Ω ∏ π  ¥ ª è  ≤   ñ Ö  ¥ æ º µ Ω ñ ≤,  â æ    æ Ç   µ ± É é Ç å  ¥   Ω ∏ Ö      æ    æ   Ç Ñ µ ª å.

##  † æ ∑     Ö É Ω æ ∫ P&L

### Realized P&L
```
realized_pnl += (exit_price - entry_price) √ó quantity - fees
```
** ¢   ∏ ≥ µ  :**  ü   ∏  ∑   ∫   ∏ Ç Ç ñ    ± æ  á     Ç ∫ æ ≤ æ º É  ∑   ∫   ∏ Ç Ç ñ    æ ∑ ∏ Ü ñ ó.

### Unrealized P&L
```
unrealized_pnl = Œ£(current_price - avg_entry_price) √ó quantity
```
** ¢   ∏ ≥ µ  :**  ü   ∏  ∫ æ ∂ Ω æ º É  æ Ω æ ≤ ª µ Ω Ω ñ  Ü ñ Ω    ± æ    æ ∑ ∏ Ü ñ π.

### Equity
```
equity = wallet_balance + unrealized_pnl
```
** î ∂ µ   µ ª æ:**  ë   ª   Ω        Ö É Ω ∫ É +  Ω µ   µ   ª ñ ∑ æ ≤   Ω ∏ π P&L.

## WAL  Ç   Disaster Recovery

### WAL-first    ñ ¥ Ö ñ ¥
```python
# Write to WAL BEFORE processing
wal_hash = wal.append(event_dict)
if wal_hash is None:
    # CRITICAL: Halt processing
    return
```

** ú µ Ç  :**  ì       Ω Ç ñ è durability    µ   µ ¥ state mutation.

### State Persistence
-  í   ñ  ∑ º ñ Ω ∏    æ ∑ ∏ Ü ñ π  ∑     ∏   É é Ç å   è  ≤ WAL
-  ú æ ∂ ª ∏ ≤ ñ   Ç å  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É    ñ   ª è  ∑ ± æ ó ≤
-  ö æ Ω   ∏   Ç µ Ω Ç Ω ñ   Ç å  ¥   Ω ∏ Ö      ∏    µ   µ ∑     É   ∫ É

##  ö æ Ω Ñ ñ ≥ É     Ü ñ è

###  û   Ω æ ≤ Ω ñ          º µ Ç   ∏
```yaml
system:
  trading:
    instruments:
      BTCUSDT:
        step_size: "0.001"
      ETHUSDT:
        step_size: "0.01"
```

###  † µ ∂ ∏ º ∏    æ ± æ Ç ∏
- **live:**  í ñ ¥   Ç µ ∂ µ Ω Ω è  ± æ π æ ≤ ∏ Ö    æ ∑ ∏ Ü ñ π
- **testnet:**  í ñ ¥   Ç µ ∂ µ Ω Ω è  Ç µ   Ç æ ≤ ∏ Ö    æ ∑ ∏ Ü ñ π

##  ú æ Ω ñ Ç æ   ∏ Ω ≥  Ç    ¥ ñ   ≥ Ω æ   Ç ∏ ∫  

###  ú µ Ç   ∏ ∫ ∏
-  ö ñ ª å ∫ ñ   Ç å  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π
- Total realized/unrealized P&L
- Equity changes over time
- WAL write success rate

###  õ æ ≥ É ≤   Ω Ω è
- ** Ü Ω Ñ æ   º   Ü ñ π Ω ñ:**  û Ω æ ≤ ª µ Ω Ω è    æ   Ç Ñ µ ª è,    æ ∑     Ö É Ω ∫ ∏ P&L
- ** ü æ   µ   µ ¥ ∂ µ Ω Ω è:**  ù µ   æ æ Ç ≤ µ Ç   Ç ≤ ∏ è  ∑  ± ñ   ∂ æ ≤ ∏ º ∏  ¥   Ω ∏ º ∏
- ** ö   ∏ Ç ∏ á Ω ñ:** WAL write failures

##  û ±   æ ± ∫      æ º ∏ ª æ ∫

###  ° Ç     Ç µ ≥ ñ ó  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è
1. **WAL failure:**  ö   ∏ Ç ∏ á Ω    ∑ É   ∏ Ω ∫    æ ±   æ ± ∫ ∏
2. **Invalid data:**  õ æ ≥ É ≤   Ω Ω è  Ç        æ   É   ∫      æ ± ª µ º Ω ∏ Ö  Ç   µ π ¥ ñ ≤
3. **State inconsistency:**  ü µ   µ ≤ ñ   ∫    Ç    ∫ æ   µ ∫ Ü ñ è      ∏  Ω     Ç É   Ω ∏ Ö  æ Ω æ ≤ ª µ Ω Ω è Ö

### Data Validation
-  ü µ   µ ≤ ñ   ∫    Ü ñ Ω æ ≤ ∏ Ö  ¥   Ω ∏ Ö  Ω    ≤   ª ñ ¥   Ü ñ é
-  í   ª ñ ¥   Ü ñ è quantity  Ç   side
-  ö æ Ω Ç   æ ª å  Ü ñ ª ñ   Ω æ   Ç ñ    æ ∑ ∏ Ü ñ π

##  ¢ µ   Ç É ≤   Ω Ω è

###  Ü Ω Ç µ ≥     Ü ñ π Ω ñ  Ç µ   Ç ∏
-  í   ª ñ ¥   Ü ñ è    æ ∑     Ö É Ω ∫ ñ ≤ P&L
-  ü µ   µ ≤ ñ   ∫   WAL  ñ Ω Ç µ ≥     Ü ñ ó
-  ¢ µ   Ç É ≤   Ω Ω è  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è    Ç   Ω É

###  ú æ ¥ É ª å Ω ñ  Ç µ   Ç ∏
-  ü µ   µ ≤ ñ   ∫    ª æ ≥ ñ ∫ ∏  æ Ω æ ≤ ª µ Ω Ω è    æ ∑ ∏ Ü ñ π
-  í   ª ñ ¥   Ü ñ è P&L    æ ∑     Ö É Ω ∫ ñ ≤
-  ¢ µ   Ç É ≤   Ω Ω è error handling

##  ê   Ö ñ Ç µ ∫ Ç É   Ω ñ  æ   æ ± ª ∏ ≤ æ   Ç ñ

### Single Source of Truth
Position Tracking  î  î ¥ ∏ Ω ∏ º  ¥ ∂ µ   µ ª æ º        ≤ ¥ ∏  ¥ ª è:
-  ü æ Ç æ á Ω æ ≥ æ    Ç   Ω É    æ   Ç Ñ µ ª è
-  Ü   Ç æ   ∏ á Ω ∏ Ö P&L  ¥   Ω ∏ Ö
- Equity    æ ∑     Ö É Ω ∫ ñ ≤

### WAL-first Design
 í   ñ  ∑ º ñ Ω ∏  ∑     ∏   É é Ç å   è  ≤ WAL    µ   µ ¥  æ ±   æ ± ∫ æ é,  â æ  ∑   ± µ ∑   µ á É î:
- Atomicity  æ   µ     Ü ñ π
- Durability      ∏  ∑ ± æ ó
- Consistency      ∏  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω ñ