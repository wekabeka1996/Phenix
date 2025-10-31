#  § É Ω ∫ Ü ñ ó  ¥ æ º µ Ω É Account Observer

##  û   Ω æ ≤ Ω ∏ π  ∫ ª    : AccountObserver

 ö ª     `AccountObserver`    µ   ª ñ ∑ É î  º æ Ω ñ Ç æ   ∏ Ω ≥  Ç æ   ≥ æ ≤ æ ó    ∫ Ç ∏ ≤ Ω æ   Ç ñ  á µ   µ ∑ Binance API  ∑    ≤ Ç æ º   Ç ∏ á Ω æ é  ¥ µ ¥ É   ª ñ ∫   Ü ñ î é  Ç    µ º ñ   ñ î é    æ ¥ ñ π FSM.

###  ö æ Ω   Ç   É ∫ Ç æ  : `__init__(self, fsm: Any, config: dict[str, Any]) -> None`

 Ü Ω ñ Ü ñ   ª ñ ∑ É î  µ ∫ ∑ µ º   ª è   AccountObserver  ∑ FSM  Ç    ∫ æ Ω Ñ ñ ≥ É     Ü ñ î é.

** ü       º µ Ç   ∏:**
- `fsm: Any` -  ï ∫ ∑ µ º   ª è   FSM core  ¥ ª è  µ º ñ   ñ ó    æ ¥ ñ π
- `config: dict[str, Any]` -  ö æ Ω Ñ ñ ≥ É     Ü ñ è  ¥ æ º µ Ω É  ∑  Ω     Ç É   Ω æ é    Ç   É ∫ Ç É   æ é:
  - `trading_mode: str` -  † µ ∂ ∏ º    æ ± æ Ç ∏ ('live', 'testnet', 'hybrid_*')
  - `binance_api: dict` -  ö æ Ω Ñ ñ ≥ É     Ü ñ è API  ∑  ∫ ª é á   º ∏  ¥ ª è live/testnet
    - `live: dict` - API  ∫ ª é á ñ  ¥ ª è mainnet
      - `api_key: str` - Binance API  ∫ ª é á
      - `api_secret: str` - Binance API    µ ∫   µ Ç
    - `testnet: dict` - API  ∫ ª é á ñ  ¥ ª è testnet
      - `api_key: str` - Testnet API  ∫ ª é á
      - `api_secret: str` - Testnet API    µ ∫   µ Ç
  - `account_observer: dict` -  °   µ Ü ∏ Ñ ñ á Ω    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  ¥ æ º µ Ω É
    - `poll_interval: int` -  Ü Ω Ç µ   ≤   ª  æ   ∏ Ç É ≤   Ω Ω è  ≤    µ ∫ É Ω ¥   Ö ( ∑    ∑   º æ ≤ á É ≤   Ω Ω è º 5)
    - `symbols: list[str]` -  °   ∏   æ ∫    ∏ º ≤ æ ª ñ ≤  ¥ ª è  º æ Ω ñ Ç æ   ∏ Ω ≥ É ( ∑    ∑   º æ ≤ á É ≤   Ω Ω è º ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])
    - `trade_limit: int` -  ö ñ ª å ∫ ñ   Ç å  Ç   µ π ¥ ñ ≤  ¥ ª è  æ Ç   ∏ º   Ω Ω è  ∑        ∑ ( ∑    ∑   º æ ≤ á É ≤   Ω Ω è º 50)

** ü æ ≤ µ   Ç   î:** `None`

** í ∏ ∫ ∏ ¥   î:**
- `ImportError` -  è ∫ â æ  Ω µ  ≤   Ç   Ω æ ≤ ª µ Ω    ± ñ ± ª ñ æ Ç µ ∫   python-binance
- `ValueError` -      ∏  Ω µ ≤   ª ñ ¥ Ω ñ π  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó API  ∫ ª é á ñ ≤

** ü   ∏ ∫ ª   ¥  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è:**
```python
config = {
    'trading_mode': 'testnet',
    'binance_api': {
        'testnet': {
            'api_key': 'your_testnet_api_key',
            'api_secret': 'your_testnet_api_secret'
        }
    },
    'account_observer': {
        'poll_interval': 5,
        'symbols': ['BTCUSDT', 'ETHUSDT'],
        'trade_limit': 50
    }
}

observer = AccountObserver(fsm, config)
```

---

###  ú µ Ç æ ¥: `start(self) -> None`

 ó     É   ∫   î  Ñ æ Ω æ ≤ µ  æ   ∏ Ç É ≤   Ω Ω è  Ç æ   ≥ æ ≤ æ ó    ∫ Ç ∏ ≤ Ω æ   Ç ñ.

** ü       º µ Ç   ∏:**  ù µ º   î

** ü æ ≤ µ   Ç   î:** `None`

** ü æ ± ñ á Ω ñ  µ Ñ µ ∫ Ç ∏:**
-  ó     É   ∫   î daemon thread  ¥ ª è `_poll_loop()`
-  í   Ç   Ω æ ≤ ª é î          æ   `running = True`
-  õ æ ≥ É î    æ á   Ç æ ∫    æ ± æ Ç ∏

** ü   ∏ ∫ ª   ¥  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è:**
```python
observer.start()
#  ¢ µ   µ          Ü é î  É  Ñ æ Ω ñ
```

---

###  ú µ Ç æ ¥: `stop(self) -> None`

 ó É   ∏ Ω è î  º æ Ω ñ Ç æ   ∏ Ω ≥  Ç   graceful shutdown.

** ü       º µ Ç   ∏:**  ù µ º   î

** ü æ ≤ µ   Ç   î:** `None`

** ü æ ± ñ á Ω ñ  µ Ñ µ ∫ Ç ∏:**
-  í   Ç   Ω æ ≤ ª é î `running = False`
-  û á ñ ∫ É î  ∑   ≤ µ   à µ Ω Ω è    æ Ç æ ∫ É (timeout 10    µ ∫ É Ω ¥)
-  õ æ ≥ É î  ∑   ≤ µ   à µ Ω Ω è    æ ± æ Ç ∏
-  û á ∏ â   î    µ   É     ∏

** ü   ∏ ∫ ª   ¥  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è:**
```python
observer.stop()
#  ú æ Ω ñ Ç æ   ∏ Ω ≥  ∑ É   ∏ Ω µ Ω æ
```

---

###  ú µ Ç æ ¥: `is_running(self) -> bool`

 ü µ   µ ≤ ñ   è î  á ∏        Ü é î  º æ Ω ñ Ç æ   ∏ Ω ≥.

** ü       º µ Ç   ∏:**  ù µ º   î

** ü æ ≤ µ   Ç   î:** `bool` - `True`  è ∫ â æ  º æ Ω ñ Ç æ   ∏ Ω ≥    ∫ Ç ∏ ≤ Ω ∏ π

** ü   ∏ ∫ ª   ¥  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è:**
```python
if observer.is_running():
    print(" ú æ Ω ñ Ç æ   ∏ Ω ≥    ∫ Ç ∏ ≤ Ω ∏ π")
```

---

###  ü   ∏ ≤   Ç Ω ∏ π  º µ Ç æ ¥: `_poll_loop(self) -> None`

 û   Ω æ ≤ Ω ∏ π  Ü ∏ ∫ ª  æ   ∏ Ç É ≤   Ω Ω è API.  í ∏ ∫ æ Ω É î Ç å   è  É  æ ∫   µ º æ º É    æ Ç æ Ü ñ.

** ê ª ≥ æ   ∏ Ç º:**
1.  ü µ   µ ≤ ñ   è î          æ   `running`
2.  Ø ∫ â æ    ∫ Ç ∏ ≤ Ω ∏ π -  ≤ ∏ ∫ ª ∏ ∫   î `_poll_trades()`
3.  û á ñ ∫ É î `poll_interval`    µ ∫ É Ω ¥
4.  ü æ ≤ Ç æ   é î  Ü ∏ ∫ ª

** û ±   æ ± ∫      æ º ∏ ª æ ∫:**
-  õ æ ≥ É î    æ º ∏ ª ∫ ∏    ª µ      æ ¥ æ ≤ ∂ É î    æ ± æ Ç É
-  ù µ    µ   µ   ∏ ≤   î  Ü ∏ ∫ ª      ∏  æ ¥ ∏ Ω æ á Ω ∏ Ö    æ º ∏ ª ∫   Ö

---

###  ü   ∏ ≤   Ç Ω ∏ π  º µ Ç æ ¥: `_poll_trades(self) -> None`

 û   ∏ Ç É î  Ç   µ π ¥ ∏  ¥ ª è  ≤   ñ Ö    ∏ º ≤ æ ª ñ ≤  É  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó.

** ê ª ≥ æ   ∏ Ç º:**
1.  î ª è  ∫ æ ∂ Ω æ ≥ æ    ∏ º ≤ æ ª É  ≤ `symbols`:
   -  í ∏ ∫ ª ∏ ∫   î `_poll_symbol_trades(symbol)`
2.  ê ≥   µ ≥ É î    Ç   Ç ∏   Ç ∏ ∫ É  ≤ ∏ ∫ ª ∏ ∫ ñ ≤

** û ±   æ ± ∫      æ º ∏ ª æ ∫:**
-  ü   æ ¥ æ ≤ ∂ É î  ∑  ñ Ω à ∏ º ∏    ∏ º ≤ æ ª   º ∏      ∏    æ º ∏ ª Ü ñ  æ ¥ Ω æ ≥ æ
-  õ æ ≥ É î    æ º ∏ ª ∫ ∏  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ    ∏ º ≤ æ ª É  æ ∫   µ º æ

---

###  ü   ∏ ≤   Ç Ω ∏ π  º µ Ç æ ¥: `_poll_symbol_trades(self, symbol: str) -> None`

 û   ∏ Ç É î  Ç   µ π ¥ ∏  ¥ ª è  ∫ æ Ω ∫   µ Ç Ω æ ≥ æ    ∏ º ≤ æ ª É.

** ü       º µ Ç   ∏:**
- `symbol: str` -  ¢ æ   ≥ æ ≤            ( Ω       ∏ ∫ ª   ¥, 'BTCUSDT')

** ê ª ≥ æ   ∏ Ç º:**
1.  í ∏ ∫ ª ∏ ∫   î `binance_client.get_my_trades(symbol, limit=trade_limit)`
2.  § ñ ª å Ç   É î  ≤ ñ ¥   æ ≤ ñ ¥ å  á µ   µ ∑ `_process_trades()`
3.  û Ω æ ≤ ª é î  º µ Ç   ∏ ∫ ∏

** û ±   æ ± ∫      æ º ∏ ª æ ∫:**
- `BinanceAPIException` -  ª æ ≥ É î  Ç      æ ≤ µ   Ç   î
- `Exception` -  ª æ ≥ É î  è ∫  Ω µ æ á ñ ∫ É ≤   Ω É    æ º ∏ ª ∫ É

---

###  ü   ∏ ≤   Ç Ω ∏ π  º µ Ç æ ¥: `_process_trades(self, trades: list, symbol: str) -> None`

 û ±   æ ± ª è î      ∏   æ ∫  Ç   µ π ¥ ñ ≤  ¥ ª è    ∏ º ≤ æ ª É  ∑  ¥ µ ¥ É   ª ñ ∫   Ü ñ î é.

** ü       º µ Ç   ∏:**
- `trades: list` -  °   ∏   æ ∫  Ç   µ π ¥ ñ ≤  ≤ ñ ¥ Binance API
- `symbol: str` -  ¢ æ   ≥ æ ≤           

** ê ª ≥ æ   ∏ Ç º:**
1.  î ª è  ∫ æ ∂ Ω æ ≥ æ  Ç   µ π ¥ É  ≤      ∏   ∫ É:
   -  ü µ   µ ≤ ñ   è î  á ∏ `trade['id']`  ≤ ∂ µ  æ ±   æ ± ª µ Ω ∏ π
   -  Ø ∫ â æ  Ω ñ -  ¥ æ ¥   î  ≤ `processed_trade_ids`
   -  ö æ Ω ≤ µ   Ç É î  á µ   µ ∑ `_trade_to_payload()`
   -  ï º ñ Ç É î    æ ¥ ñ é `EVT:TRADE_EXECUTED`
2.  û Ω æ ≤ ª é î  º µ Ç   ∏ ∫ ∏  æ ±   æ ± ∫ ∏

** î µ ¥ É   ª ñ ∫   Ü ñ è:**
-  í ∏ ∫ æ   ∏   Ç æ ≤ É î `processed_trade_ids: Set[int]`
-  ü µ   µ ≤ ñ   è î  Ω   è ≤ Ω ñ   Ç å    µ   µ ¥  æ ±   æ ± ∫ æ é
-  î æ ¥   î    ñ   ª è  É     ñ à Ω æ ó  æ ±   æ ± ∫ ∏

---

###  ü   ∏ ≤   Ç Ω ∏ π  º µ Ç æ ¥: `_trade_to_payload(self, trade: dict) -> dict`

 ö æ Ω ≤ µ   Ç É î  Ç   µ π ¥  ∑  Ñ æ   º   Ç É Binance  ≤ payload    æ ¥ ñ ó FSM.

** ü       º µ Ç   ∏:**
- `trade: dict` -  ¢   µ π ¥  É  Ñ æ   º   Ç ñ Binance API

** ü æ ≤ µ   Ç   î:** `dict` - Payload  ¥ ª è    æ ¥ ñ ó EVT:TRADE_EXECUTED

** ° Ç   É ∫ Ç É     payload:**
```python
{
    'symbol': str,      #  ¢ æ   ≥ æ ≤           
    'side': str,        # 'buy'    ± æ 'sell'
    'price': str,       #  ¶ ñ Ω    è ∫    è ¥ æ ∫  ¥ ª è  Ç æ á Ω æ   Ç ñ
    'quantity': str,    #  ö ñ ª å ∫ ñ   Ç å ( ≤ ñ ¥' î º Ω    ¥ ª è      æ ¥   ∂ É)
    'ts': int,          # Timestamp  ≤  º ñ ª ñ   µ ∫ É Ω ¥   Ö
    'fees': str,        #  ö æ º ñ   ñ è  è ∫    è ¥ æ ∫
    'venue': str        # 'binance'
}
```

** ö æ Ω ≤ µ   Ç   Ü ñ è:**
- `isBuyer: true` ‚Üí `side: 'buy'`
- `isBuyer: false` ‚Üí `side: 'sell'`
- `qty` ‚Üí `quantity` ( ≤ ñ ¥' î º Ω µ  ¥ ª è      æ ¥   ∂ É)
- `price`, `commission` ‚Üí  ∑ ± µ   ñ ≥   é Ç å   è  è ∫    è ¥ ∫ ∏</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\functions.md