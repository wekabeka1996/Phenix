#  † µ   ª ñ ∑ æ ≤   Ω ñ  Ñ É Ω ∫ Ü ñ ó  ¥ æ º µ Ω É Account Balance

##  û ≥ ª è ¥

 î æ º µ Ω `account_balance`    µ   ª ñ ∑ É î  ∫ ª     `AccountConnector`  ∑  Ω   ± æ   æ º  º µ Ç æ ¥ ñ ≤  ¥ ª è  º æ Ω ñ Ç æ   ∏ Ω ≥ É    Ç   Ω É      Ö É Ω ∫ É Binance Futures.  í   ñ  º µ Ç æ ¥ ∏  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É é Ç å      ∏ Ω Ö   æ Ω Ω µ      æ ≥     º É ≤   Ω Ω è  Ç    æ ±   æ ± ∫ É    æ º ∏ ª æ ∫  ¥ ª è  ∑   ± µ ∑   µ á µ Ω Ω è  Ω   ¥ ñ π Ω æ   Ç ñ.

##  û   Ω æ ≤ Ω ∏ π  ∫ ª    : AccountConnector

###  ö æ Ω   Ç   É ∫ Ç æ    Ç    ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ è

#### `__init__(fsm: FSMCore, config: Dict[str, Any]) -> None`
** û   ∏  :**  Ü Ω ñ Ü ñ   ª ñ ∑ É î  ∑' î ¥ Ω   Ω Ω è  ∑ Binance API  á µ   µ ∑ BinanceAdapter.

** ü       º µ Ç   ∏:**
- `fsm`:  ï ∫ ∑ µ º   ª è   FSM core  ¥ ª è  µ º ñ   ñ ó    æ ¥ ñ π
- `config`:  ö æ Ω Ñ ñ ≥ É     Ü ñ π Ω ∏ π    ª æ ≤ Ω ∏ ∫  ∑ API credentials  Ç    Ω   ª   à Ç É ≤   Ω Ω è º ∏

** õ æ ≥ ñ ∫    ñ Ω ñ Ü ñ   ª ñ ∑   Ü ñ ó:**
1.  ó ± µ   µ ∂ µ Ω Ω è    æ   ∏ ª   Ω å  Ω   FSM  Ç    ∫ æ Ω Ñ ñ ≥ É     Ü ñ é
2.  û Ç   ∏ º   Ω Ω è  ñ Ω Ç µ   ≤   ª É  æ   ∏ Ç É ≤   Ω Ω è  ∑ `account_observer.poll_interval`
3.  í ∏ ± ñ   API  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  ∑   ª µ ∂ Ω æ  ≤ ñ ¥ `trading_mode`:
   - `live`:  í ∏ ∫ æ   ∏   Ç   Ω Ω è  ± æ π æ ≤ ∏ Ö API  ∫ ª é á ñ ≤
   - `testnet`/`hybrid`:  í ∏ ∫ æ   ∏   Ç   Ω Ω è  Ç µ   Ç æ ≤ ∏ Ö API  ∫ ª é á ñ ≤
4.  í   ª ñ ¥   Ü ñ è  Ω   è ≤ Ω æ   Ç ñ  ≤   ñ Ö  Ω µ æ ± Ö ñ ¥ Ω ∏ Ö API          º µ Ç   ñ ≤
5.  ° Ç ≤ æ   µ Ω Ω è  µ ∫ ∑ µ º   ª è     `BinanceAdapter`

** í ∏ ∫ ∏ ¥   î:** `ValueError`      ∏  Ω µ   æ ≤ Ω ñ π API  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó

###  £       ≤ ª ñ Ω Ω è  ∂ ∏ Ç Ç î ≤ ∏ º  Ü ∏ ∫ ª æ º

#### `start() -> None`
** û   ∏  :**  ó     É   ∫   î  º æ Ω ñ Ç æ   ∏ Ω ≥      Ö É Ω ∫ É  É  Ñ æ Ω æ ≤ æ º É    æ Ç æ Ü ñ.

** õ æ ≥ ñ ∫  :**
1.  ü µ   µ ≤ ñ   ∫  ,  á ∏  ≤ ∂ µ  ∑     É â µ Ω æ
2.  í   Ç   Ω æ ≤ ª µ Ω Ω è          æ     `running = True`
3.  ° Ç ≤ æ   µ Ω Ω è daemon    æ Ç æ ∫ É  ∑  º µ Ç æ ¥ æ º `_monitor_loop`
4.  ó     É   ∫    æ Ç æ ∫ É
5.  õ æ ≥ É ≤   Ω Ω è  É     ñ à Ω æ ≥ æ  ∑     É   ∫ É

#### `stop() -> None`
** û   ∏  :**  ó É   ∏ Ω è î  º æ Ω ñ Ç æ   ∏ Ω ≥  Ç    ∑   ∫   ∏ ≤   î  ∑' î ¥ Ω   Ω Ω è.

** õ æ ≥ ñ ∫  :**
1.  í   Ç   Ω æ ≤ ª µ Ω Ω è `running = False`
2.  û á ñ ∫ É ≤   Ω Ω è  ∑   ≤ µ   à µ Ω Ω è    æ Ç æ ∫ É (thread.join())
3.  ó   ∫   ∏ Ç Ç è HTTP    µ   ñ ó    ¥     Ç µ    
4.  õ æ ≥ É ≤   Ω Ω è  ∑ É   ∏ Ω ∫ ∏

###  û   Ω æ ≤ Ω ∏ π  Ü ∏ ∫ ª  º æ Ω ñ Ç æ   ∏ Ω ≥ É

#### `_monitor_loop() -> None`
** û   ∏  :**  ì æ ª æ ≤ Ω ∏ π  Ü ∏ ∫ ª  º æ Ω ñ Ç æ   ∏ Ω ≥ É,  â æ        Ü é î  É  Ñ æ Ω æ ≤ æ º É    æ Ç æ Ü ñ.

** õ æ ≥ ñ ∫  :**
1.  ° Ç ≤ æ   µ Ω Ω è  Ω æ ≤ æ ≥ æ event loop  ¥ ª è      ∏ Ω Ö   æ Ω Ω ∏ Ö  æ   µ     Ü ñ π
2.  ¶ ∏ ∫ ª    æ ∫ ∏ `running == True`:
   -  í ∏ ∫ ª ∏ ∫ `_fetch_and_emit_account_data()`
   -  û á ñ ∫ É ≤   Ω Ω è `update_interval`    µ ∫ É Ω ¥
3.  ó   ∫   ∏ Ç Ç è event loop      ∏  ∑   ≤ µ   à µ Ω Ω ñ

** û ±   æ ± ∫      æ º ∏ ª æ ∫:**  õ æ ≥ É ≤   Ω Ω è  ∑   ≤ µ   à µ Ω Ω è  Ü ∏ ∫ ª É

###  û Ç   ∏ º   Ω Ω è  Ç    æ ±   æ ± ∫    ¥   Ω ∏ Ö

#### `_fetch_and_emit_account_data() -> None`
** û   ∏  :**  ê   ∏ Ω Ö   æ Ω Ω æ  æ Ç   ∏ º É î  ¥   Ω ñ  ∑ Binance API  Ç    µ º ñ Ç É î FSM    æ ¥ ñ ó.

** õ æ ≥ ñ ∫    ¥ ª è  ±   ª   Ω   É:**
1.  í ∏ ∫ ª ∏ ∫ `adapter.get_account_balance()`
2.  í   ª ñ ¥   Ü ñ è  Ç ∏   É  ≤ ñ ¥   æ ≤ ñ ¥ ñ ( º   î  ± É Ç ∏ list)
3.  ó ± µ   µ ∂ µ Ω Ω è  ¥   Ω ∏ Ö  É `_latest_balance_data`
4.  î µ Ç   ª å Ω µ  ª æ ≥ É ≤   Ω Ω è USDT  ±   ª   Ω   É
5.  í ∏ ∫ ª ∏ ∫ `_emit_balance_update()`

** õ æ ≥ ñ ∫    ¥ ª è    æ ∑ ∏ Ü ñ π:**
1.  í ∏ ∫ ª ∏ ∫ `adapter.get_open_positions()`
2.  í   ª ñ ¥   Ü ñ è  Ç ∏   É  ≤ ñ ¥   æ ≤ ñ ¥ ñ ( º   î  ± É Ç ∏ list)
3.  í ∏ ∫ ª ∏ ∫ `_emit_positions_update()`

** û ±   æ ± ∫      æ º ∏ ª æ ∫:**  û ∫   µ º    æ ±   æ ± ∫    ¥ ª è  ±   ª   Ω   É  Ç      æ ∑ ∏ Ü ñ π  ∑  ¥ µ Ç   ª å Ω ∏ º  ª æ ≥ É ≤   Ω Ω è º

###  ï º ñ   ñ è FSM    æ ¥ ñ π

#### `_emit_balance_update(balance_data: List[Dict[str, Any]]) -> None`
** û   ∏  :**  ï º ñ Ç É î    æ ¥ ñ é `EVT:BALANCE_UPDATE_RECEIVED`  ∑  ¥   Ω ∏ º ∏  ±   ª   Ω   É.

** ¢     Ω   Ñ æ   º   Ü ñ è  ¥   Ω ∏ Ö:**
1.  § ñ ª å Ç     Ü ñ è    ∫ Ç ∏ ≤ ñ ≤  ∑ `balance > 0`
2.  ö æ Ω ≤ µ   Ç   Ü ñ è  á ∏   ª æ ≤ ∏ Ö  ∑ Ω   á µ Ω å  É `Decimal`  ¥ ª è  Ç æ á Ω æ   Ç ñ
3.  ° Ç ≤ æ   µ Ω Ω è      ∏   ∫ É assets  ∑    æ ª è º ∏:
   - `asset`:  Ω   ∑ ≤      ∫ Ç ∏ ≤ É
   - `balance`:  ∑   ≥   ª å Ω ∏ π  ±   ª   Ω  
   - `crossUnPnl`:  Ω µ   µ   ª ñ ∑ æ ≤   Ω ∏ π P&L
   - `crossWalletBalance`:  ±   ª   Ω   cross margin
   - `updateTime`:  á      æ Ω æ ≤ ª µ Ω Ω è

**Payload    Ç   É ∫ Ç É   ∏:**
```python
{
    'assets': [...],  #      ∏   æ ∫    ∫ Ç ∏ ≤ ñ ≤
    'updateTime': int  #  º   ∫   ∏ º   ª å Ω ∏ π updateTime  ∑    ∫ Ç ∏ ≤ ñ ≤
}
```

** ï º ñ   ñ è    æ ¥ ñ ó:**
- Event name: `"EVT:BALANCE_UPDATE_RECEIVED"`
- Why: `"Balance data updated from Binance API."`
-  õ æ ≥ É ≤   Ω Ω è  ∫ ñ ª å ∫ æ   Ç ñ    ∫ Ç ∏ ≤ ñ ≤  ∑  ±   ª   Ω   æ º > 0

#### `_emit_positions_update(positions_data: List[Dict[str, Any]]) -> None`
** û   ∏  :**  ï º ñ Ç É î    æ ¥ ñ é `EVT:ACCOUNT_UPDATE_RECEIVED`  ∑  ¥   Ω ∏ º ∏    æ ∑ ∏ Ü ñ π  Ç    ∑   ≥   ª å Ω æ ≥ æ    Ç   Ω É.

** ¢     Ω   Ñ æ   º   Ü ñ è    æ ∑ ∏ Ü ñ π:**
1.  § ñ ª å Ç     Ü ñ è    æ ∑ ∏ Ü ñ π  ∑ `positionAmt != 0`
2.  ö æ Ω ≤ µ   Ç   Ü ñ è  É Decimal  ¥ ª è  Ç æ á Ω æ   Ç ñ
3.  ° Ç ≤ æ   µ Ω Ω è      ∏   ∫ É  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π  ∑    æ ª è º ∏:
   - `symbol`:  Ç æ   ≥ æ ≤           
   - `positionAmt`:    æ ∑ º ñ      æ ∑ ∏ Ü ñ ó
   - `entryPrice`:  Ü ñ Ω    ≤ Ö æ ¥ É
   - `unRealizedProfit`:  Ω µ   µ   ª ñ ∑ æ ≤   Ω ∏ π      ∏ ± É Ç æ ∫
   - `leverage`:    ª µ á µ
   - `marginType`:  Ç ∏    º     ∂ ñ
   - `markPrice`:    æ ∑ Ω   á µ Ω    Ü ñ Ω  
   - `liquidationPrice`:  Ü ñ Ω    ª ñ ∫ ≤ ñ ¥   Ü ñ ó

** † æ ∑     Ö É Ω æ ∫  ∑   ≥   ª å Ω æ ≥ æ    Ç   Ω É:**
1.  í ∏ ∫ æ   ∏   Ç   Ω Ω è `_latest_balance_data`  ¥ ª è USDT    ∫ Ç ∏ ≤ É
2.  û Ç   ∏ º   Ω Ω è `totalWalletBalance`  ∑    æ ª è `balance`
3.  û Ç   ∏ º   Ω Ω è `totalUnrealizedProfit`  ∑    æ ª è `crossUnPnl`
4.  û Ç   ∏ º   Ω Ω è `totalCrossWalletBalance`  ∑  ≤ ñ ¥   æ ≤ ñ ¥ Ω æ ≥ æ    æ ª è

**Payload    Ç   É ∫ Ç É   ∏:**
```python
{
    'totalWalletBalance': str,
    'totalUnrealizedProfit': str,
    'totalCrossWalletBalance': str,
    'positions': [...],  #      ∏   æ ∫  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π
    'updateTime': int    #    æ Ç æ á Ω ∏ π timestamp  ≤ ms
}
```

** ï º ñ   ñ è    æ ¥ ñ ó:**
- Event name: `"EVT:ACCOUNT_UPDATE_RECEIVED"`
- Why: `"Open positions data updated from Binance API."`
-  õ æ ≥ É ≤   Ω Ω è  ∫ ñ ª å ∫ æ   Ç ñ  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π  Ç   wallet balance

##  í Ω É Ç   ñ à Ω ñ    Ç   ∏ ± É Ç ∏  ∫ ª     É

###  ö æ Ω Ñ ñ ≥ É     Ü ñ π Ω ñ    Ç   ∏ ± É Ç ∏
- `fsm`:  ü æ   ∏ ª   Ω Ω è  Ω   FSM core
- `config`:  ö æ Ω Ñ ñ ≥ É     Ü ñ π Ω ∏ π    ª æ ≤ Ω ∏ ∫
- `update_interval`:  Ü Ω Ç µ   ≤   ª  æ   ∏ Ç É ≤   Ω Ω è  ≤    µ ∫ É Ω ¥   Ö ( ∑    ∑   º æ ≤ á É ≤   Ω Ω è º 30)

###  ° Ç   Ω  ≤ ∏ ∫ æ Ω   Ω Ω è
- `thread`:  § æ Ω æ ≤ ∏ π    æ Ç ñ ∫  ≤ ∏ ∫ æ Ω   Ω Ω è
- `running`:  ü       æ      ∫ Ç ∏ ≤ Ω æ   Ç ñ  º æ Ω ñ Ç æ   ∏ Ω ≥ É
- `adapter`:  ï ∫ ∑ µ º   ª è   BinanceAdapter

###  ö µ à æ ≤   Ω ñ  ¥   Ω ñ
- `_latest_balance_data`:  û   Ç   Ω Ω ñ  ¥   Ω ñ  ±   ª   Ω   É  ∑ API `/fapi/v2/balance`

##  í ∏ ∫ æ   ∏   Ç æ ≤ É ≤   Ω ñ  ∑ æ ≤ Ω ñ à Ω ñ  ∑   ª µ ∂ Ω æ   Ç ñ

### vfoundation.adapters.binance_adapter.BinanceAdapter
** ú µ Ç æ ¥ ∏:**
- `get_account_balance()`:  û Ç   ∏ º   Ω Ω è  ±   ª   Ω   É    ∫ Ç ∏ ≤ ñ ≤
- `get_open_positions()`:  û Ç   ∏ º   Ω Ω è  ≤ ñ ¥ ∫   ∏ Ç ∏ Ö    æ ∑ ∏ Ü ñ π
- `close_session()`:  ó   ∫   ∏ Ç Ç è HTTP    µ   ñ ó

### vfoundation.core.FSMCore
** ú µ Ç æ ¥ ∏:**
- `emit(event_name, payload, why)`:  ï º ñ   ñ è FSM    æ ¥ ñ ó

##  û ±   æ ± ∫      æ º ∏ ª æ ∫

###  ° Ç     Ç µ ≥ ñ ó
1. **API    æ º ∏ ª ∫ ∏:**  õ æ ≥ É ≤   Ω Ω è  ∑ `exc_info=True`  ¥ ª è  ¥ µ Ç   ª å Ω æ ≥ æ traceback
2. ** ù µ ≤   ª ñ ¥ Ω ñ  ¥   Ω ñ:**  ü µ   µ ≤ ñ   ∫    Ç ∏   ñ ≤  Ç        æ   É   ∫  Ω µ ∫ æ   µ ∫ Ç Ω ∏ Ö  ∑     ∏   ñ ≤
3. ** ú µ   µ ∂ µ ≤ ñ      æ ± ª µ º ∏:** Graceful degradation  ∑  æ   Ç   Ω Ω ñ º ∏  ≤ ñ ¥ æ º ∏ º ∏  ¥   Ω ∏ º ∏

###  õ æ ≥ É ≤   Ω Ω è
- **INFO:**  £     ñ à Ω ñ  æ   µ     Ü ñ ó,  ∫ ñ ª å ∫ ñ   Ç å  ¥   Ω ∏ Ö
- **WARNING:**  í ñ ¥   É Ç Ω ñ   Ç å USDT,      æ ± ª µ º ∏  ∑  ¥   Ω ∏ º ∏
- **ERROR:**  ö   ∏ Ç ∏ á Ω ñ    æ º ∏ ª ∫ ∏  ∑    æ ≤ Ω ∏ º traceback

##  ü   æ ¥ É ∫ Ç ∏ ≤ Ω ñ   Ç å

###  û   Ç ∏ º ñ ∑   Ü ñ ó
- ** § ñ ª å Ç     Ü ñ è:**  ¢ ñ ª å ∫ ∏    ∫ Ç ∏ ≤ ∏  ∑  ±   ª   Ω   æ º > 0  Ç      æ ∑ ∏ Ü ñ ó  ∑ amount != 0
- ** ö µ à É ≤   Ω Ω è:**  ó ± µ   µ ∂ µ Ω Ω è  ±   ª   Ω   É  ¥ ª è  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ≤    æ ∑ ∏ Ü ñ è Ö
- ** ê   ∏ Ω Ö   æ Ω Ω ñ   Ç å:**  ù µ ± ª æ ∫ É é á ñ API  ≤ ∏ ∫ ª ∏ ∫ ∏
- **Background execution:**  û ∫   µ º ∏ π    æ Ç ñ ∫  Ω µ  ± ª æ ∫ É î  æ   Ω æ ≤ Ω ∏ π      æ Ü µ  

###  ú µ Ç   ∏ ∫ ∏  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è
- **CPU:**  ú ñ Ω ñ º   ª å Ω µ  Ω   ≤   Ω Ç   ∂ µ Ω Ω è ( Ç ñ ª å ∫ ∏    µ   ñ æ ¥ ∏ á Ω ñ API  ≤ ∏ ∫ ª ∏ ∫ ∏)
- **Memory:**  § ñ ∫   æ ≤   Ω ∏ π    æ ∑ º ñ    ¥ ª è  ∫ µ à É ≤   Ω Ω è  æ   Ç   Ω Ω ñ Ö  ¥   Ω ∏ Ö
- **Network:** 2 API  ≤ ∏ ∫ ª ∏ ∫ ∏  ∫ æ ∂ Ω ñ 30    µ ∫ É Ω ¥
- **Storage:**  ù µ  ≤ ∏ ∫ æ   ∏   Ç æ ≤ É î    æ   Ç ñ π Ω µ    Ö æ ≤ ∏ â µ

##  ¢ µ   Ç É ≤   Ω Ω è

###  ú æ ¥ É ª å Ω ñ  Ç µ   Ç ∏
- ** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è:**  í   ª ñ ¥   Ü ñ è  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  Ç      Ç ≤ æ   µ Ω Ω è    ¥     Ç µ    
- **API  º æ ∫ ∏:**  ° ∏ º É ª è Ü ñ è  ≤ ñ ¥   æ ≤ ñ ¥ µ π Binance API
- ** ¢     Ω   Ñ æ   º   Ü ñ è:**  ü µ   µ ≤ ñ   ∫    ∫ æ Ω ≤ µ   Ç   Ü ñ ó  ¥   Ω ∏ Ö  É    æ ¥ ñ ó
- ** ï º ñ   ñ è:**  í   ª ñ ¥   Ü ñ è    Ç   É ∫ Ç É   ∏ payload    æ ¥ ñ π

###  Ü Ω Ç µ ≥     Ü ñ π Ω ñ  Ç µ   Ç ∏
- **FSM  ñ Ω Ç µ ≥     Ü ñ è:**  ü µ   µ ≤ ñ   ∫    µ º ñ   ñ ó  Ç        æ ∂ ∏ ≤   Ω Ω è    æ ¥ ñ π
- **API  ñ Ω Ç µ ≥     Ü ñ è:**  ¢ µ   Ç É ≤   Ω Ω è  ∑    µ   ª å Ω ∏ º ∏ credentials (testnet)
- **Error handling:**  ° ∏ º É ª è Ü ñ è  º µ   µ ∂ µ ≤ ∏ Ö    æ º ∏ ª æ ∫  Ç   API failures

##  ë µ ∑   µ ∫  

###  ó   Ö ∏   Ç  æ ± ª ñ ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö
- API  ∫ ª é á ñ    µ   µ ¥   é Ç å   è  Ç ñ ª å ∫ ∏  á µ   µ ∑  ∫ æ Ω   Ç   É ∫ Ç æ  
-  ù µ  ª æ ≥ É é Ç å   è  É  ∑ ≤ ∏ á   π Ω æ º É    µ ∂ ∏ º ñ
-  í ∏ ∫ æ   ∏   Ç   Ω Ω è HTTPS  á µ   µ ∑ BinanceAdapter

###  ê É ¥ ∏ Ç
-  í   ñ API  ≤ ∏ ∫ ª ∏ ∫ ∏  ª æ ≥ É é Ç å   è  ± µ ∑ sensitive data
-  î µ Ç   ª å Ω µ  ª æ ≥ É ≤   Ω Ω è  Ñ ñ Ω   Ω   æ ≤ ∏ Ö  æ   µ     Ü ñ π
- Timestamp  ≤   ñ Ö  æ   µ     Ü ñ π  ¥ ª è    É ¥ ∏ Ç É

##  † æ ∑ à ∏   µ Ω Ω è  Ñ É Ω ∫ Ü ñ æ Ω   ª å Ω æ   Ç ñ

###  ú æ ∂ ª ∏ ≤ ñ  ¥ æ ¥   ≤   Ω Ω è
1. **WebSocket    ñ ¥ Ç   ∏ º ∫  :**  ü µ   µ Ö ñ ¥  ∑ REST  Ω   real-time updates
2. **Multi-asset    ñ ¥ Ç   ∏ º ∫  :**  ú æ Ω ñ Ç æ   ∏ Ω ≥  ¥ æ ¥   Ç ∫ æ ≤ ∏ Ö    ∫ Ç ∏ ≤ ñ ≤
3. **Historical data:**  ó ± µ   µ ∂ µ Ω Ω è  ñ   Ç æ   ñ ó  ±   ª   Ω   É
4. **Alerting:**  ü æ ≤ ñ ¥ æ º ª µ Ω Ω è      æ  ∫   ∏ Ç ∏ á Ω ñ  ∑ º ñ Ω ∏  ±   ª   Ω   É

###  ö æ Ω Ñ ñ ≥ É     Ü ñ π Ω ñ    æ ∑ à ∏   µ Ω Ω è
-  ù   ª   à Ç É ≤   Ω Ω è  Ñ ñ ª å Ç   ñ ≤    ∫ Ç ∏ ≤ ñ ≤/   æ ∑ ∏ Ü ñ π
-  öastom Ω ñ  ñ Ω Ç µ   ≤   ª ∏  æ   ∏ Ç É ≤   Ω Ω è
-  î æ ¥   Ç ∫ æ ≤ ñ  º µ Ç   ∏ ∫ ∏  º æ Ω ñ Ç æ   ∏ Ω ≥ É
-  Ü Ω Ç µ ≥     Ü ñ è  ∑    ñ ∑ Ω ∏ º ∏    µ ∂ ∏ º   º ∏  Ç æ   ≥ ñ ≤ ª ñ</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_balance\functions.md