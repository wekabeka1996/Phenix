#  ü   ∏ ∫ ª   ¥ ∏  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ¥ æ º µ Ω É Account Observer

 ¶ è        ∫    º ñ   Ç ∏ Ç å        ∫ Ç ∏ á Ω ñ      ∏ ∫ ª   ¥ ∏  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è  ¥ æ º µ Ω É `account_observer`  ¥ ª è  º æ Ω ñ Ç æ   ∏ Ω ≥ É  Ç æ   ≥ æ ≤ æ ó    ∫ Ç ∏ ≤ Ω æ   Ç ñ.

##  §   π ª ∏      ∏ ∫ ª   ¥ ñ ≤

### [usage_examples.py](usage_examples.py)
 ö æ º   ª µ ∫   Ω ñ      ∏ ∫ ª   ¥ ∏  ∫ æ ¥ É Python  ¥ ª è    ñ ∑ Ω ∏ Ö    Ü µ Ω     ñ ó ≤  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è:

- ** ë   ∑ æ ≤ µ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è**:  Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è,  ∑     É   ∫  Ç    ∑ É   ∏ Ω ∫    º æ Ω ñ Ç æ   ∏ Ω ≥ É
- ** ü   æ   ª É Ö æ ≤ É ≤   Ω Ω è    æ ¥ ñ π**:  û ±   æ ± ∫      æ ¥ ñ π `EVT:TRADE_EXECUTED`
- ** † æ ∑ à ∏   µ Ω ñ  º æ ∂ ª ∏ ≤ æ   Ç ñ**:  § ñ ª å Ç     Ü ñ è  Ç   µ π ¥ ñ ≤,    Ç   Ç ∏   Ç ∏ ∫    ≤    µ   ª å Ω æ º É  á     ñ
- ** Ü Ω Ç µ ≥     Ü ñ è**:  °   ñ ≤       Ü è  ∑  ñ Ω à ∏ º ∏  ¥ æ º µ Ω   º ∏ (position tracking)
- ** û ±   æ ± ∫      æ º ∏ ª æ ∫**: Graceful degradation  Ç    ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è
- ** ¢ µ   Ç É ≤   Ω Ω è**:  ú æ ∫ ∏  Ç    ñ Ω Ç µ ≥     Ü ñ π Ω ñ  Ç µ   Ç ∏

### [config_examples.yaml](config_examples.yaml)
 ü   ∏ ∫ ª   ¥ ∏  ∫ æ Ω Ñ ñ ≥ É     Ü ñ π Ω ∏ Ö  Ñ   π ª ñ ≤  ¥ ª è    ñ ∑ Ω ∏ Ö    µ   µ ¥ æ ≤ ∏ â:

- **production.yaml**:  ü   æ ¥ É ∫ Ç ∏ ≤ Ω    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  ∑    æ ≤ Ω ∏ º  Ω   ± æ   æ º    ∏ º ≤ æ ª ñ ≤
- **testnet.yaml**:  ¢ µ   Ç æ ≤    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  ¥ ª è    æ ∑   æ ± ∫ ∏
- **minimal.yaml**:  ú ñ Ω ñ º   ª å Ω    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  ¥ ª è  à ≤ ∏ ¥ ∫ æ ≥ æ    Ç     Ç É
- **filtered.yaml**:  ö æ Ω Ñ ñ ≥ É     Ü ñ è  ∑  Ñ ñ ª å Ç     º ∏  Ç   µ π ¥ ñ ≤
- **high_frequency.yaml**:  û   Ç ∏ º ñ ∑ æ ≤   Ω    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è  ¥ ª è  ≤ ∏   æ ∫ æ ó  á     Ç æ Ç ∏
- **debug.yaml**:  ö æ Ω Ñ ñ ≥ É     Ü ñ è  ¥ ª è  ¥ ñ   ≥ Ω æ   Ç ∏ ∫ ∏  Ç    Ω   ª   ≥ æ ¥ ∂ µ Ω Ω è

### [sample_trade_event.json](sample_trade_event.json)
 ü   ∏ ∫ ª   ¥    æ ¥ ñ ó `EVT:TRADE_EXECUTED`  É  Ñ æ   º   Ç ñ JSON  ∑  É   ñ º    æ ± æ ≤' è ∑ ∫ æ ≤ ∏ º ∏    æ ª è º ∏.

### [event_sequences.md](event_sequences.md)
 ü æ   ª ñ ¥ æ ≤ Ω æ   Ç ñ    æ ¥ ñ π  ¥ ª è  Ç µ   Ç É ≤   Ω Ω è    ñ ∑ Ω ∏ Ö    Ü µ Ω     ñ ó ≤:

-  ù æ   º   ª å Ω      æ   ª ñ ¥ æ ≤ Ω ñ   Ç å  Ç   µ π ¥ ñ ≤
-  í ∏   æ ∫    á     Ç æ Ç    Ç æ   ≥ ñ ≤ ª ñ
-  ü æ º ∏ ª ∫ ∏  Ç    ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è
-  ¢ µ   Ç É ≤   Ω Ω è  ¥ µ ¥ É   ª ñ ∫   Ü ñ ó

##  ® ≤ ∏ ¥ ∫ ∏ π    Ç     Ç

### 1.  ë   ∑ æ ≤    ∫ æ Ω Ñ ñ ≥ É     Ü ñ è
```yaml
account_observer:
  trading_mode: live
  symbols: [BTCUSDT, ETHUSDT]
```

### 2.  ü   æ   Ç ∏ π  ∫ æ ¥
```python
from binance.client import Client
from aurora.domains.account_observer import AccountObserver

config = {'trading_mode': 'live', 'symbols': ['BTCUSDT']}
client = Client('api_key', 'api_secret')

observer = AccountObserver(config, client)
observer.start()

# Observer        Ü é î  ≤  Ñ æ Ω ñ  Ç    µ º ñ Ç É î    æ ¥ ñ ó EVT:TRADE_EXECUTED
```

### 3.  û ±   æ ± ∫      æ ¥ ñ π
```python
@fsm.on_event('EVT:TRADE_EXECUTED')
def handle_trade(event):
    payload = event.payload
    print(f" ¢   µ π ¥: {payload['symbol']} {payload['side']} {payload['quantity']} @ {payload['price']}")
```

##  ° Ç   É ∫ Ç É     payload    æ ¥ ñ ó

 í   ñ    æ ¥ ñ ó `EVT:TRADE_EXECUTED`  º ñ   Ç è Ç å    Ç   Ω ¥     Ç ∏ ∑ æ ≤   Ω ∏ π payload:

```json
{
  "symbol": "BTCUSDT",        //  ¢ æ   ≥ æ ≤           
  "side": "buy",             // "buy"    ± æ "sell"
  "price": "50000.00",       //  ¶ ñ Ω    è ∫    è ¥ æ ∫
  "quantity": "0.00100000",  //  ö ñ ª å ∫ ñ   Ç å ( ≤ ñ ¥' î º Ω    ¥ ª è      æ ¥   ∂ É)
  "ts": 1640995200000,       // Unix timestamp  ≤  º ñ ª ñ   µ ∫ É Ω ¥   Ö
  "fees": "0.00025000",      //  ö æ º ñ   ñ è  è ∫    è ¥ æ ∫
  "venue": "binance",        //  ú   π ¥   Ω á ∏ ∫
  "trade_id": 12345,         //  £ Ω ñ ∫   ª å Ω ∏ π ID  Ç   µ π ¥ É
  "order_id": 67890          // ID  æ   ¥ µ    
}
```

##  ù   π ∫     â ñ        ∫ Ç ∏ ∫ ∏

###  ö æ Ω Ñ ñ ≥ É     Ü ñ è
-  í ∏ ± ∏     π Ç µ `poll_interval`  ∑   ª µ ∂ Ω æ  ≤ ñ ¥    æ Ç   µ ± (1-10    µ ∫ É Ω ¥  ¥ ª è live, 30+  ¥ ª è  Ç µ   Ç É ≤   Ω Ω è)
-  û ± º µ ∂ É π Ç µ  ∫ ñ ª å ∫ ñ   Ç å    ∏ º ≤ æ ª ñ ≤  ¥ ª è  ∫     â æ ó      æ ¥ É ∫ Ç ∏ ≤ Ω æ   Ç ñ
-  í ∏ ∫ æ   ∏   Ç æ ≤ É π Ç µ `max_processed_trades`  ¥ ª è  ∫ æ Ω Ç   æ ª é      º' è Ç ñ

###  û ±   æ ± ∫      æ º ∏ ª æ ∫
-  ó   ≤ ∂ ¥ ∏  æ ±   æ ± ª è π Ç µ    æ º ∏ ª ∫ ∏ API (rate limits, network issues)
-  † µ   ª ñ ∑ É π Ç µ  µ ∫     æ Ω µ Ω Ü ñ   ª å Ω É  ∑   Ç   ∏ º ∫ É      ∏    æ º ∏ ª ∫   Ö
-  õ æ ≥ É π Ç µ  ∫   ∏ Ç ∏ á Ω ñ    æ º ∏ ª ∫ ∏  ¥ ª è  ¥ ñ   ≥ Ω æ   Ç ∏ ∫ ∏

###  ¢ µ   Ç É ≤   Ω Ω è
-  í ∏ ∫ æ   ∏   Ç æ ≤ É π Ç µ  º æ ∫ ∏  ¥ ª è  ñ ∑ æ ª è Ü ñ ó  Ç µ   Ç ñ ≤
-  ¢ µ   Ç É π Ç µ  ¥ µ ¥ É   ª ñ ∫   Ü ñ é  ∑    æ ≤ Ç æ   é ≤   Ω ∏ º ∏  ¥   Ω ∏ º ∏
-  ü µ   µ ≤ ñ   è π Ç µ        ≤ ∏ ª å Ω ñ   Ç å  ∫ æ Ω ≤ µ   Ç   Ü ñ ó payload

###  ü   æ ¥ É ∫ Ç ∏ ≤ Ω ñ   Ç å
-  ú æ Ω ñ Ç æ   Ç µ  ≤ ∏ ∫ æ   ∏   Ç   Ω Ω è      º' è Ç ñ ( ∫ µ à ID  Ç   µ π ¥ ñ ≤)
-  ° Ç µ ∂ Ç µ  ∑    á     Ç æ Ç æ é API  ≤ ∏ ∫ ª ∏ ∫ ñ ≤
-  û   Ç ∏ º ñ ∑ É π Ç µ `trade_limit`  ¥ ª è  ≤   à æ ≥ æ  æ ±   è ≥ É  Ç æ   ≥ ñ ≤ ª ñ

##  ° É º ñ   Ω ñ   Ç å

- **Python**: 3.11+
- **Binance API**: Futures API
- **vFoundation**: 1.0+
- **FSM**:  ü æ ¥ ¥ µ   ∂ ∫      æ ¥ ñ π  Ç   observer pattern

##  î ∏ ≤ ñ Ç å   è  Ç   ∫ æ ∂

- [README.md](../README.md) -  ó   ≥   ª å Ω    ñ Ω Ñ æ   º   Ü ñ è      æ  ¥ æ º µ Ω
- [architecture.md](../architecture.md) -  ê   Ö ñ Ç µ ∫ Ç É   Ω ñ  ¥ µ Ç   ª ñ
- [functions.md](../functions.md) - API  Ñ É Ω ∫ Ü ñ π
- [schema.json](../schema.json) - JSON Schema
- [dictionaries.yaml](../dictionaries.yaml) -  ö æ Ω Ñ ñ ≥ É     Ü ñ π Ω ñ    ª æ ≤ Ω ∏ ∫ ∏</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\examples\README.md