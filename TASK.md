 **повний список ордерів USDT-M (Futures /fapi)** і як їх правильно подавати на біржу. Дам коротко: що це, які поля обов’язкові, і мінімальні приклади (REST і через CCXT). Джерела — офіційні доки Binance. ([Центр разработчиков Binance][1])

---

# Типи ордерів і обов’язкові поля (USDT-M Futures)

| Type                   | Що це         | Обов’язкові поля                                                                           | Нюанси                                                                                                                       |
| ---------------------- | ------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| `LIMIT`                | Лімітний      | `symbol`, `side`, `type=LIMIT`, `timeInForce`, `quantity`, `price` *(або `priceMatch`)*    | Підтримує `GTC/IOC/FOK/GTX/GTD`; `priceMatch` (опонент/черга) взаємовиключний із `price`. ([Центр разработчиков Binance][2]) |
| `MARKET`               | Ринковий      | `symbol`, `side`, `type=MARKET`, `quantity`                                                | `timeInForce` не застосовується. ([Центр разработчиков Binance][2])                                                          |
| `STOP`                 | Стоп-ліміт    | `symbol`, `side`, `type=STOP`, `quantity`, `stopPrice`, (`price` або `priceMatch`)         | Тригер за `workingType`=`MARK_PRICE`/`CONTRACT_PRICE`, за замовчуванням `CONTRACT_PRICE`. ([Центр разработчиков Binance][2]) |
| `STOP_MARKET`          | Стоп-маркет   | `symbol`, `side`, `type=STOP_MARKET`, `stopPrice`                                          | Якщо додаєш `closePosition=true` → **не** передавати `quantity` і `reduceOnly`. ([Центр разработчиков Binance][2])           |
| `TAKE_PROFIT`          | ТП-ліміт      | `symbol`, `side`, `type=TAKE_PROFIT`, `quantity`, `stopPrice`, (`price` або `priceMatch`)  | Аналогічно `STOP`. ([Центр разработчиков Binance][2])                                                                        |
| `TAKE_PROFIT_MARKET`   | ТП-маркет     | `symbol`, `side`, `type=TAKE_PROFIT_MARKET`, `stopPrice`                                   | З `closePosition=true` **без** `quantity` і **без** `reduceOnly`. ([Центр разработчиков Binance][2])                         |
| `TRAILING_STOP_MARKET` | Трейлінг-стоп | `symbol`, `side`, `type=TRAILING_STOP_MARKET`, `callbackRate` *(+ опц. `activationPrice`)* | Валідація: BUY → `activationPrice` < поточної; SELL → `activationPrice` > поточної. ([Центр разработчиков Binance][2])       |

Додаткові параметри, які реально важливі:

* `positionSide`: у **Hedge Mode обов’язковий** (`LONG`/`SHORT`), в One-way — не потрібен. ([Центр разработчиков Binance][1])
* `reduceOnly`: **можна** для часткового закриття; **не допускається** разом із `closePosition=true` і в Hedge Mode. ([Центр разработчиков Binance][1])
* `closePosition`: лише з `STOP_MARKET`/`TAKE_PROFIT_MARKET`; за тригеру **закриє весь** поточний лонг (якщо `SELL`) або шорт (якщо `BUY`). **Не** поєднується з `quantity`/`reduceOnly`. ([Центр разработчиков Binance][1])
* `workingType`: що тригерить `stopPrice` — `MARK_PRICE` або `CONTRACT_PRICE` (за замовчуванням). ([Центр разработчиков Binance][1])
* `priceProtect`: вмикає захист тригерів від різких відхилень (перевіряє `triggerProtect` із `exchangeInfo`). ([Центр разработчиков Binance][2])
* `timeInForce`: `GTC`, `IOC`, `FOK`, **`GTX` (post-only)**, **`GTD` (із `goodTillDate`)**; для ринкових і *_MARKET не застосовується. Помилки для `GTX/FOK` тепер повертаються **відразу**. ([Центр разработчиков Binance][3])
* `priceMatch`: автоматичний підбір ціни для `LIMIT/STOP/TAKE_PROFIT` (опонент/черга). Не можна разом із `price`. **Нещодавно частину значень тимчасово прибрали** — дивись change-log. ([developers.binance.info][4])

---

# Мінімальні приклади (REST)

> База для **testnet**: `https://testnet.binancefuture.com` (`/fapi`). Підпис і `timestamp` обов’язкові для приватних викликів. ([developers.binance.me][5])

**1) MARKET (відкриття)**

```
POST /fapi/v1/order
symbol=BTCUSDT&side=BUY&type=MARKET&quantity=0.001&timestamp=...&signature=...
```

(без `timeInForce`). ([Центр разработчиков Binance][1])

**2) STOP_MARKET (SL «закрий усе»)**

```
POST /fapi/v1/order
symbol=BTCUSDT&side=SELL&type=STOP_MARKET&stopPrice=60000&closePosition=true
&workingType=MARK_PRICE&timestamp=...&signature=...
```

> Жодного `quantity` і жодного `reduceOnly`. У Hedge Mode — не став `side=SELL` для `positionSide=SHORT` (заборонено). ([Центр разработчиков Binance][1])

**3) TAKE_PROFIT (TP-ліміт частковий)**

```
POST /fapi/v1/order
symbol=BTCUSDT&side=SELL&type=TAKE_PROFIT&quantity=0.001&stopPrice=61000&price=61050
&timeInForce=GTC&workingType=CONTRACT_PRICE&reduceOnly=true
&timestamp=...&signature=...
```

> Якщо хочеш «закрити все» на TP — використовуй `TAKE_PROFIT_MARKET + closePosition=true` (без qty/RO). ([Центр разработчиков Binance][1])

**4) TRAILING_STOP_MARKET**

```
POST /fapi/v1/order
symbol=BTCUSDT&side=SELL&type=TRAILING_STOP_MARKET&callbackRate=0.5&activationPrice=62000
&workingType=MARK_PRICE&timestamp=...&signature=...
```

> Валідація BUY/SELL щодо `activationPrice` — як у таблиці вище. ([Центр разработчиков Binance][2])

---

# Те ж саме через **CCXT (binanceusdm)**

> Увімкни ф’ючерси (клас `binanceusdm` або `options.defaultType='future'`). Символи в **уніфікованому** форматі `BTC/USDT`. Додаткові поля — через `params`. ([GitHub][6])

```python
import ccxt.async_support as ccxt

ex = ccxt.binanceusdm({
    "apiKey": "...", "secret": "...",
    "enableRateLimit": True,
    "options": {"defaultType": "future"},
})
await ex.load_markets()
```

**1) MARKET**

```python
await ex.create_order("BTC/USDT", "market", "buy", 0.001, None, {})
```

**2) STOP_MARKET (SL close-all)**

```python
params = {"stopPrice": 60000, "workingType": "MARK_PRICE", "closePosition": True}
# важливо: без amount і без reduceOnly
await ex.create_order("BTC/USDT", "stop_market", "sell", None, None, params)
```

(Гарантовано закриє **всю** LONG-позицію, коли спрацює тригер. Не міксуй з qty/RO.) ([Центр разработчиков Binance][1])

**3) TAKE_PROFIT (частковий TP-ліміт)**

```python
params = {"stopPrice": 61000, "workingType": "CONTRACT_PRICE", "timeInForce": "GTC", "reduceOnly": True}
await ex.create_order("BTC/USDT", "take_profit", "sell", 0.001, 61050, params)
```

**4) TRAILING_STOP_MARKET**

```python
params = {"callbackRate": 0.5, "activationPrice": 62000, "workingType": "MARK_PRICE"}
await ex.create_order("BTC/USDT", "trailing_stop_market", "sell", 0.001, None, params)
```

> Для reduceOnly у CCXT — це **custom param**: `{'reduceOnly': True}`; у Hedge Mode додавай `positionSide`. ([GitHub][7])

---

## Типові помилки, які треба уникнути

* **`-2022 reduceOnly order would increase position`** — невірна сторона, або qty > позиції, або ти поєднав `closePosition=true` з `quantity`/`reduceOnly`. Для close-all *_MARKET завжди без qty/RO. ([Binance Developer Community][8])
* **Пост-онлі**: `timeInForce=GTX` — якщо ордер торкається ринку, біржа **відхиляє одразу** (`-5022`). ([Центр разработчиков Binance][3])
* **Hedge Mode**: завжди став `positionSide`, і не юзай `reduceOnly`. ([Центр разработчиков Binance][1])
* **GTD**: якщо ставиш `timeInForce=GTD`, обов’язково додай `goodTillDate` (секундна точність) і він має бути > now+600s. ([Центр разработчиков Binance][2])

---

## Короткий чек-лист перед відправкою

1. Правильний **ендпоінт** (`/fapi/v1/order`) і **testnet baseURL**. ([developers.binance.me][5])
2. `positionSide` в Hedge Mode; **правильний `side`**: для LONG захист — `SELL`, для SHORT — `BUY`. ([Центр разработчиков Binance][1])
3. Якщо `closePosition=true` → **жодного** `quantity` і `reduceOnly`. ([Центр разработчиков Binance][1])
4. `workingType` для умовних — чітко вибери (`MARK_PRICE`/`CONTRACT_PRICE`). ([Центр разработчиков Binance][1])
5. Для `LIMIT/STOP/TAKE_PROFIT` узгодь `timeInForce`/`price`/`priceMatch`. ([Центр разработчиков Binance][2])

