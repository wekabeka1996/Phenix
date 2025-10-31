# 🚨 КРИТИЧНА ПРОБЛЕМА: Фічи рахують� я з кон� тантних значень, а не з живих даних

## Проблема

Си� тема НЕ працює на живих даних. Фічи (OBI, TFI, delta_price) розраховують� я з **КОНСТАНТНИХ значень**, а не з реальних даних ринку:

### Доказ - `market_data_connector.py` лінія 177-180:

```python
payload = {
    "bid_size": decimal.Decimal('1'),      # ❌ ЗАВЖДИ 1 - КОНСТАНТА!
    "ask_size": decimal.Decimal('1'),      # ❌ ЗАВЖДИ 1 - КОНСТАНТА!
    "buy_volume": volume / 2,              # ❌ ЗАВЖДИ половина - ДЕ ФАКТО КОНСТАНТА!
    "sell_volume": volume / 2              # ❌ ЗАВЖДИ половина - ДЕ ФАКТО КОНСТАНТА!
}
```

### Що це означає

```
OBI (Order Book Imbalance) = (bid_size - ask_size) / (bid_size + ask_size)
                           = (1 - 1) / (1 + 1) 
                           = 0 / 2 
                           = 0.0000 ✅ ЗАВЖДИ!

TFI (Trade Flow Imbalance) = (buy_volume - sell_volume) / (buy_volume + sell_volume)
                           = (volume/2 - volume/2) / (volume/2 + volume/2)
                           = 0 / volume
                           = 0.0000 ✅ ЗАВЖДИ!

delta_price = (current_price - prev_price) / prev_price
            = Дій� но змінюєть� я, але це лише 1/3 � игналу
            = Вага: 0.05 (в� ього 5%)
```

### Результат

**Сигнали практично завжди = 0 або близько до нього**, тому що:
- OBI = 0 × 0.6 = 0
- TFI = 0 × 0.35 = 0  
- delta_price ~ мала × 0.05 ≈ 0

Логи підтверджують:
```
Trade intent for ETHUSDT rejected: Neutral signal score -0.0415
Trade intent for BTCUSDT rejected: quantity is zero or negative
```

---

## Рішення

### Крок 1: Пере� тавити на WebSocket streams

Конфіг вже визначає необхідні потоки (`system.yaml` лінія 98-100):

```yaml
market_data:
  websocket_streams:
    - "bookTicker"  # Для OBI (Order Book Imbalance)
    - "trade"       # Для TFI та delta_price
```

### Крок 2: Імплементувати обробку WebSocket

**Для OBI:** � лухати `bookTicker` stream:
```json
{
  "s": "BTCUSDT",
  "b": "113956.50",  // bid price
  "B": "2.5",        // bid quantity ✅ ЖИВЕ!
  "a": "113957.00",  // ask price
  "A": "3.2"         // ask quantity ✅ ЖИВЕ!
}
```

**Для TFI:** � лухати `trade` stream:
```json
{
  "s": "BTCUSDT",
  "p": "113956.50",  // price
  "q": "0.5",        // quantity
  "b": 12345,        // buyer order id
  "a": 12346,        // seller order id
  "T": 1698764512345, // trade time
  "m": false         // is buyer maker?  ✅ ПОКАЗУЄ НАПРЯМОК!
}
```

**Для delta_price:** будь-якої рівня даних (навіть klines ви� тачає)

### Крок 3: Накопичення даних

- Накопичувати `bid_size` та `ask_size` з о� танніх N trade'ів
- Накопичувати count buy_trades vs sell_trades за о� танню 1хв
- Обновляти feature values кожні 1-2 � екунди (не кожні 5 � ек)

### Крок 4: Логування для верифікації

Додати в `feature_engineering.py` DEBUG логування:

```python
self.logger.debug(f"Features for {symbol}: "
    f"bid_size={bid_size}, ask_size={ask_size} → OBI={obi:.4f}, "
    f"buy_vol={buy_volume}, sell_vol={sell_volume} → TFI={tfi:.4f}, "
    f"delta_price={delta_price:.6f}")
```

---

## Стату� 

- [ ] Імплементувати WebSocket обробку для bookTicker
- [ ] Імплементувати WebSocket обробку для trade
- [ ] Додати DEBUG логування для bid_size, ask_size, buy_volume, sell_volume
- [ ] Перевірити що OBI та TFI змінюють� я (не кон� танти)
- [ ] Перевірити що � игнали генерують� я коректно
- [ ] Запу� тити integration те� ти

---

## Ча�  на виправлення

**Пріоритет:** CRÍTICO (P0) - � и� тема НЕ працює без живих даних

**Очікуваний ча� :** 30-60 хвилин

**Залежні� ть:** BinanceAdapter повинен підтримувати WebSocket потоки
