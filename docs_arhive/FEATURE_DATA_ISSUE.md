# üö®  ö † ò ¢ ò ß ù ê  ü † û ë õ ï ú ê:  § ñ á ∏      Ö É é Ç å   è  ∑  ∫ æ Ω   Ç   Ω Ç Ω ∏ Ö  ∑ Ω   á µ Ω å,     Ω µ  ∑  ∂ ∏ ≤ ∏ Ö  ¥   Ω ∏ Ö

##  ü   æ ± ª µ º  

 ° ∏   Ç µ º    ù ï        Ü é î  Ω    ∂ ∏ ≤ ∏ Ö  ¥   Ω ∏ Ö.  § ñ á ∏ (OBI, TFI, delta_price)    æ ∑     Ö æ ≤ É é Ç å   è  ∑ ** ö û ù ° ¢ ê ù ¢ ù ò •  ∑ Ω   á µ Ω å**,     Ω µ  ∑    µ   ª å Ω ∏ Ö  ¥   Ω ∏ Ö    ∏ Ω ∫ É:

###  î æ ∫   ∑ - `market_data_connector.py`  ª ñ Ω ñ è 177-180:

```python
payload = {
    "bid_size": decimal.Decimal('1'),      # ‚ùå  ó ê í ñ î ò 1 -  ö û ù ° ¢ ê ù ¢ ê!
    "ask_size": decimal.Decimal('1'),      # ‚ùå  ó ê í ñ î ò 1 -  ö û ù ° ¢ ê ù ¢ ê!
    "buy_volume": volume / 2,              # ‚ùå  ó ê í ñ î ò    æ ª æ ≤ ∏ Ω   -  î ï  § ê ö ¢ û  ö û ù ° ¢ ê ù ¢ ê!
    "sell_volume": volume / 2              # ‚ùå  ó ê í ñ î ò    æ ª æ ≤ ∏ Ω   -  î ï  § ê ö ¢ û  ö û ù ° ¢ ê ù ¢ ê!
}
```

###  © æ  Ü µ  æ ∑ Ω   á   î

```
OBI (Order Book Imbalance) = (bid_size - ask_size) / (bid_size + ask_size)
                           = (1 - 1) / (1 + 1) 
                           = 0 / 2 
                           = 0.0000 ‚úÖ  ó ê í ñ î ò!

TFI (Trade Flow Imbalance) = (buy_volume - sell_volume) / (buy_volume + sell_volume)
                           = (volume/2 - volume/2) / (volume/2 + volume/2)
                           = 0 / volume
                           = 0.0000 ‚úÖ  ó ê í ñ î ò!

delta_price = (current_price - prev_price) / prev_price
            =  î ñ π   Ω æ  ∑ º ñ Ω é î Ç å   è,    ª µ  Ü µ  ª ∏ à µ 1/3    ∏ ≥ Ω   ª É
            =  í   ≥  : 0.05 ( ≤   å æ ≥ æ 5%)
```

###  † µ ∑ É ª å Ç   Ç

** ° ∏ ≥ Ω   ª ∏        ∫ Ç ∏ á Ω æ  ∑   ≤ ∂ ¥ ∏ = 0    ± æ  ± ª ∏ ∑ å ∫ æ  ¥ æ  Ω å æ ≥ æ**,  Ç æ º É  â æ:
- OBI = 0 √ó 0.6 = 0
- TFI = 0 √ó 0.35 = 0  
- delta_price ~  º   ª   √ó 0.05 ‚âà 0

 õ æ ≥ ∏    ñ ¥ Ç ≤ µ   ¥ ∂ É é Ç å:
```
Trade intent for ETHUSDT rejected: Neutral signal score -0.0415
Trade intent for BTCUSDT rejected: quantity is zero or negative
```

---

##  † ñ à µ Ω Ω è

###  ö   æ ∫ 1:  ü µ   µ   Ç   ≤ ∏ Ç ∏  Ω   WebSocket streams

 ö æ Ω Ñ ñ ≥  ≤ ∂ µ  ≤ ∏ ∑ Ω   á   î  Ω µ æ ± Ö ñ ¥ Ω ñ    æ Ç æ ∫ ∏ (`system.yaml`  ª ñ Ω ñ è 98-100):

```yaml
market_data:
  websocket_streams:
    - "bookTicker"  #  î ª è OBI (Order Book Imbalance)
    - "trade"       #  î ª è TFI  Ç   delta_price
```

###  ö   æ ∫ 2:  Ü º   ª µ º µ Ω Ç É ≤   Ç ∏  æ ±   æ ± ∫ É WebSocket

** î ª è OBI:**    ª É Ö   Ç ∏ `bookTicker` stream:
```json
{
  "s": "BTCUSDT",
  "b": "113956.50",  // bid price
  "B": "2.5",        // bid quantity ‚úÖ  ñ ò í ï!
  "a": "113957.00",  // ask price
  "A": "3.2"         // ask quantity ‚úÖ  ñ ò í ï!
}
```

** î ª è TFI:**    ª É Ö   Ç ∏ `trade` stream:
```json
{
  "s": "BTCUSDT",
  "p": "113956.50",  // price
  "q": "0.5",        // quantity
  "b": 12345,        // buyer order id
  "a": 12346,        // seller order id
  "T": 1698764512345, // trade time
  "m": false         // is buyer maker?  ‚úÖ  ü û ö ê ó £ Ñ  ù ê ü † Ø ú û ö!
}
```

** î ª è delta_price:**  ± É ¥ å- è ∫ æ ó    ñ ≤ Ω è  ¥   Ω ∏ Ö ( Ω   ≤ ñ Ç å klines  ≤ ∏   Ç   á   î)

###  ö   æ ∫ 3:  ù   ∫ æ   ∏ á µ Ω Ω è  ¥   Ω ∏ Ö

-  ù   ∫ æ   ∏ á É ≤   Ç ∏ `bid_size`  Ç   `ask_size`  ∑  æ   Ç   Ω Ω ñ Ö N trade' ñ ≤
-  ù   ∫ æ   ∏ á É ≤   Ç ∏ count buy_trades vs sell_trades  ∑    æ   Ç   Ω Ω é 1 Ö ≤
-  û ± Ω æ ≤ ª è Ç ∏ feature values  ∫ æ ∂ Ω ñ 1-2    µ ∫ É Ω ¥ ∏ ( Ω µ  ∫ æ ∂ Ω ñ 5    µ ∫)

###  ö   æ ∫ 4:  õ æ ≥ É ≤   Ω Ω è  ¥ ª è  ≤ µ   ∏ Ñ ñ ∫   Ü ñ ó

 î æ ¥   Ç ∏  ≤ `feature_engineering.py` DEBUG  ª æ ≥ É ≤   Ω Ω è:

```python
self.logger.debug(f"Features for {symbol}: "
    f"bid_size={bid_size}, ask_size={ask_size} ‚Üí OBI={obi:.4f}, "
    f"buy_vol={buy_volume}, sell_vol={sell_volume} ‚Üí TFI={tfi:.4f}, "
    f"delta_price={delta_price:.6f}")
```

---

##  ° Ç   Ç É  

- [ ]  Ü º   ª µ º µ Ω Ç É ≤   Ç ∏ WebSocket  æ ±   æ ± ∫ É  ¥ ª è bookTicker
- [ ]  Ü º   ª µ º µ Ω Ç É ≤   Ç ∏ WebSocket  æ ±   æ ± ∫ É  ¥ ª è trade
- [ ]  î æ ¥   Ç ∏ DEBUG  ª æ ≥ É ≤   Ω Ω è  ¥ ª è bid_size, ask_size, buy_volume, sell_volume
- [ ]  ü µ   µ ≤ ñ   ∏ Ç ∏  â æ OBI  Ç   TFI  ∑ º ñ Ω é é Ç å   è ( Ω µ  ∫ æ Ω   Ç   Ω Ç ∏)
- [ ]  ü µ   µ ≤ ñ   ∏ Ç ∏  â æ    ∏ ≥ Ω   ª ∏  ≥ µ Ω µ   É é Ç å   è  ∫ æ   µ ∫ Ç Ω æ
- [ ]  ó     É   Ç ∏ Ç ∏ integration  Ç µ   Ç ∏

---

##  ß      Ω    ≤ ∏       ≤ ª µ Ω Ω è

** ü   ñ æ   ∏ Ç µ Ç:** CR√çTICO (P0) -    ∏   Ç µ º    ù ï        Ü é î  ± µ ∑  ∂ ∏ ≤ ∏ Ö  ¥   Ω ∏ Ö

** û á ñ ∫ É ≤   Ω ∏ π  á    :** 30-60  Ö ≤ ∏ ª ∏ Ω

** ó   ª µ ∂ Ω ñ   Ç å:** BinanceAdapter    æ ≤ ∏ Ω µ Ω    ñ ¥ Ç   ∏ º É ≤   Ç ∏ WebSocket    æ Ç æ ∫ ∏
