# Аналіз Проблеми Відхилення Ордерів BTCUSDT

## Опис Проблеми

Система відхиляє всі trade intents для BTCUSDT з причиною:
```
qty rounded to zero from raw 0.0003801122591059045310711640746
```

Це наслідок TASK50 (Quantity Normalization Contract) з fail-closed семантикою.

## Корінь Проблеми

### Розрахунок Qty для BTCUSDT

**Вхідні дані:**
- Position size: $33.87 USDT (5% від equity $677.50)
- Price: $89,104.40
- Step size: 0.001 BTC
- Min qty: 0.001 BTC

**Математика:**
```
Raw qty = position_size / price = 33.87 / 89104.4 ≈ 0.000380 BTC
Rounded qty = raw_qty.quantize(0.001, ROUND_DOWN) = 0.000 BTC
```

**Результат:** Rounded qty = 0 → відхилення ордера

### Чому Це Відбувається

1. **Висока ціна BTC:** $89K робить навіть невеликі позиції дуже маленькими в BTC
2. **Великий step_size:** 0.001 BTC = мінімальний лот
3. **Консервативний position sizing:** 5% equity = $33.87
4. **Fail-closed семантика:** TASK50 забороняє silent bump-ups

## Вплив на Систему

### Що Працює
- ✅ ETHUSDT: ціна ~$2,500 → qty ~0.013 → rounded до 0.013
- ✅ SOLUSDT: ціна ~$150 → qty ~0.226 → rounded до 0.226
- ✅ DOGEUSDT: ціна ~$0.20 → qty ~170 → rounded до 170

### Що Не Працює
- ❌ BTCUSDT: занадто дорога для поточного sizing
- ❌ Можливо XRPUSDT при високих цінах

## Можливі Рішення

### Рішення 1: Збільшити Global Percent Equity (Найпростіше)

**Ідея:** Збільшити базовий position sizing з 5% до 15-20%

**Реалізація:**
```yaml
# config/aurora/trading.yaml
trading:
  decision:
    position_sizing:
      percent_equity: 0.15  # 15% замість 5%
```

**Розрахунок:**
- 15% від $677.50 = $101.62
- Qty = 101.62 / 89104 ≈ 0.00114
- Rounded = 0.001 BTC ✅
- Notional = $89.10 ✅

**Переваги:**
- Працює для всіх інструментів
- Простий конфіг
- Зберігає існуючу логіку

### Рішення 2: Збільшити BTC-specific Regime Sizing

**Ідея:** Збільшити multipliers для BTCUSDT

**Реалізація:**
```yaml
# config/aurora/aurora_instruments.yaml
BTCUSDT:
  regime_sizing:
    HIGH_VOLATILITY: 2.0    # 33.87 * 2.0 = 67.74
    LOW_VOLATILITY: 3.0     # 33.87 * 3.0 = 101.61
    MEAN_REVERSION: 3.0     # 33.87 * 3.0 = 101.61
```

**Переваги:**
- Тільки для BTC
- Режим-залежний контроль

### Рішення 3: Змінити Qty Calculation (Не Рекомендовано)

**Ідея:** Дозволити bump-up до min_qty

**Мінуси:**
- Порушує TASK50 fail-closed контракт
- Silent зміни розміру позиції

### Рішення 2: Змінити Qty Calculation Logic

**Ідея:** Якщо rounded_qty = 0, використовувати min_qty

**Реалізація в decision_making.py:**
```python
if rounded_qty <= 0:
    # Замість відхилення - використовувати min_qty
    rounded_qty = min_qty
    self.logger.info(f"[{symbol}] QTY_BUMP: rounded to min_qty {min_qty}")
```

**Переваги:**
- Автоматичне рішення
- Забезпечує торгівлю

**Недоліки:**
- Silent bump-up (порушує TASK50 контракт)
- Потенційно занадто великі позиції

### Рішення 3: Інструмент-специфічний Min Position Size

**Ідея:** Встановити min_position_size_usd для кожного інструменту

**Реалізація:**
```yaml
# config/aurora/aurora_instruments.yaml
BTCUSDT:
  min_position_size_usd: 100  # Замість глобальних 10
```

**Переваги:**
- Контроль на рівні інструменту
- Сумісний з існуючою логікою

### Рішення 4: Динамічний Position Sizing

**Ідея:** Розраховувати sizing на основі min_qty * price

**Реалізація:**
```python
# В _calculate_position_size
min_required_usd = min_qty * price
if final_pos_size_usd < min_required_usd:
    final_pos_size_usd = min_required_usd
```

## Рекомендація

**Вибрати Рішення 1** - збільшити percent_equity до 0.15 (15%).

Це:
- ✅ Найпростіше рішення
- ✅ Працює для всіх інструментів
- ✅ Зберігає fail-closed семантику TASK50
- ✅ Забезпечує торгівлю BTC з адекватним ризиком

## Імплементація

1. **Оновити trading.yaml:**
   ```yaml
   trading:
     decision:
       position_sizing:
         percent_equity: 0.15  # збільшити з 0.05
   ```

2. **Перевірити роботу:**
   - Position size стане ~$101.62
   - BTC qty стане ~0.00114 → rounded до 0.001
   - Ордери повинні проходити

3. **Моніторити ризик:**
   - Загальна експозиція зросте
   - Можливо додати додаткові ліміти в risk_management

## Висновок

Проблема - очікуваний наслідок TASK50 fail-closed семантики при торгівлі дорогими активами. Рішення вимагає балансу між ризиком та можливістю торгівлі.</content>
<parameter name="filePath">/home/wekabeka/Музыка/Phenix/BTCUSDT_QTY_REJECTION_ANALYSIS.md