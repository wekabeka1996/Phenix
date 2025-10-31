#                                       :                                                                     ,                                 

##                 

                                                           .          (OBI, TFI, delta_price)                                 **                                     **,                                                  :

###            - `market_data_connector.py`            177-180:

```python
payload = {
    "bid_size": decimal.Decimal('1'),      #                  1 -                   !
    "ask_size": decimal.Decimal('1'),      #                  1 -                   !
    "buy_volume": volume / 2,              #                                   -                                   !
    "sell_volume": volume / 2              #                                   -                                   !
}
```

###                         

```
OBI (Order Book Imbalance) = (bid_size - ask_size) / (bid_size + ask_size)
                           = (1 - 1) / (1 + 1) 
                           = 0 / 2 
                           = 0.0000                 !

TFI (Trade Flow Imbalance) = (buy_volume - sell_volume) / (buy_volume + sell_volume)
                           = (volume/2 - volume/2) / (volume/2 + volume/2)
                           = 0 / volume
                           = 0.0000                 !

delta_price = (current_price - prev_price) / prev_price
            =                                  ,                      1/3               
            =         : 0.05 (             5%)
```

###                   

**                                               = 0                                      **,              :
- OBI = 0    0.6 = 0
- TFI = 0    0.35 = 0  
- delta_price ~             0.05     0

                                   :
```
Trade intent for ETHUSDT rejected: Neutral signal score -0.0415
Trade intent for BTCUSDT rejected: quantity is zero or negative
```

---

##               

###          1:                             WebSocket streams

                                                                     (`system.yaml`            98-100):

```yaml
market_data:
  websocket_streams:
    - "bookTicker"  #        OBI (Order Book Imbalance)
    - "trade"       #        TFI      delta_price
```

###          2:                                             WebSocket

**       OBI:**                `bookTicker` stream:
```json
{
  "s": "BTCUSDT",
  "b": "113956.50",  // bid price
  "B": "2.5",        // bid quantity             !
  "a": "113957.00",  // ask price
  "A": "3.2"         // ask quantity             !
}
```

**       TFI:**                `trade` stream:
```json
{
  "s": "BTCUSDT",
  "p": "113956.50",  // price
  "q": "0.5",        // quantity
  "b": 12345,        // buyer order id
  "a": 12346,        // seller order id
  "T": 1698764512345, // trade time
  "m": false         // is buyer maker?                                     !
}
```

**       delta_price:**         -                               (             klines                 )

###          3:                                  

-                          `bid_size`      `ask_size`                     N trade'    
-                          count buy_trades vs sell_trades                     1    
-                    feature values            1-2                (                5       )

###          4:                                                 

                `feature_engineering.py` DEBUG                   :

```python
self.logger.debug(f"Features for {symbol}: "
    f"bid_size={bid_size}, ask_size={ask_size}     OBI={obi:.4f}, "
    f"buy_vol={buy_volume}, sell_vol={sell_volume}     TFI={tfi:.4f}, "
    f"delta_price={delta_price:.6f}")
```

---

##             

- [ ]                              WebSocket                       bookTicker
- [ ]                              WebSocket                       trade
- [ ]              DEBUG                           bid_size, ask_size, buy_volume, sell_volume
- [ ]                           OBI      TFI                      (                       )
- [ ]                                                                                 
- [ ]                    integration           

---

##                                   

**                  :** CR  TICO (P0) -                                                              

**                           :** 30-60             

**                    :** BinanceAdapter                                         WebSocket             
