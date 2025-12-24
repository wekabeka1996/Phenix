#                             Account Observer

##                          : AccountObserver

         `AccountObserver`                                                                                        Binance API                                                                                       FSM.

###                       : `__init__(self, fsm: Any, config: dict[str, Any]) -> None`

                                          AccountObserver    FSM                                .

**                  :**
- `fsm: Any` -                    FSM core                               
- `config: dict[str, Any]` -                                                                                 :
  - `trading_mode: str` -                         ('live', 'testnet', 'hybrid_*')
  - `binance_api: dict` -                          API                          live/testnet
    - `live: dict` - API                   mainnet
      - `api_key: str` - Binance API         
      - `api_secret: str` - Binance API             
    - `testnet: dict` - API                   testnet
      - `api_key: str` - Testnet API         
      - `api_secret: str` - Testnet API             
  - `account_observer: dict` -                                                           
    - `poll_interval: int` -                                                           (                                5)
    - `symbols: list[str]` -                                                             (                                ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'])
    - `trade_limit: int` -                                                                         (                                50)

**                :** `None`

**              :**
- `ImportError` -                                                           python-binance
- `ValueError` -                                                      API             

**                                       :**
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

###           : `start(self) -> None`

                                                                                        .

**                  :**           

**                :** `None`

**                           :**
-                  daemon thread        `_poll_loop()`
-                                   `running = True`
-                                       

**                                       :**
```python
observer.start()
#                                    
```

---

###           : `stop(self) -> None`

                                         graceful shutdown.

**                  :**           

**                :** `None`

**                           :**
-                      `running = False`
-                                                (timeout 10             )
-                                             
-                            

**                                       :**
```python
observer.stop()
#                                      
```

---

###           : `is_running(self) -> bool`

                                                         .

**                  :**           

**                :** `bool` - `True`                                               

**                                       :**
```python
if observer.is_running():
    print("                                     ")
```

---

###                              : `_poll_loop(self) -> None`

                                               API.                                                        .

**                :**
1.                                 `running`
2.                           -                  `_poll_trades()`
3.              `poll_interval`             
4.                          

**                             :**
-                                                                 
-                                                                            

---

###                              : `_poll_trades(self) -> None`

                                                                                      .

**                :**
1.                                         `symbols`:
   -                  `_poll_symbol_trades(symbol)`
2.                                                     

**                             :**
-                                                                                         
-                                                                            

---

###                              : `_poll_symbol_trades(self, symbol: str) -> None`

                                                                      .

**                  :**
- `symbol: str` -                         (                  , 'BTCUSDT')

**                :**
1.                  `binance_client.get_my_trades(symbol, limit=trade_limit)`
2.                                                `_process_trades()`
3.                              

**                             :**
- `BinanceAPIException` -                                 
- `Exception` -                                                      

---

###                              : `_process_trades(self, trades: list, symbol: str) -> None`

                                                                                                .

**                  :**
- `trades: list` -                                    Binance API
- `symbol: str` -                        

**                :**
1.                                                   :
   -                         `trade['id']`                            
   -               -               `processed_trade_ids`
   -                               `_trade_to_payload()`
   -                         `EVT:TRADE_EXECUTED`
2.                                             

**                        :**
-                          `processed_trade_ids: Set[int]`
-                                                                  
-                                                      

---

###                              : `_trade_to_payload(self, trade: dict) -> dict`

                                                Binance    payload            FSM.

**                  :**
- `trade: dict` -                              Binance API

**                :** `dict` - Payload                   EVT:TRADE_EXECUTED

**                   payload:**
```python
{
    'symbol': str,      #                        
    'side': str,        # 'buy'        'sell'
    'price': str,       #                                                 
    'quantity': str,    #                    (      '                              )
    'ts': int,          # Timestamp                            
    'fees': str,        #                               
    'venue': str        # 'binance'
}
```

**                      :**
- `isBuyer: true`     `side: 'buy'`
- `isBuyer: false`     `side: 'sell'`
- `qty`     `quantity` (      '                              )
- `price`, `commission`                                             </content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\functions.md