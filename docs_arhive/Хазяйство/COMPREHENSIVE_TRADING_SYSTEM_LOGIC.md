# ЛОГІКА АВТОТРЕЙДИНГОВОЇ СИСТЕМИ AURORA
## Повне Пояснення Механіки Прийняття Рішень та Виконання

**Документ:** Всебічне пояснення архітектури, метрик та алгоритмів торгівлі
**Дата:** Листопад 2025
**Статус:** Актуальний | Версія: 1.0

---

## 📋 ЗМІСТ

1. [Огляд системи](#1-огляд-системи)
2. [Архітектура та компоненти](#2-архітектура-та-компоненти)
3. [Інженерія ознак та сигналізація](#3-інженерія-ознак-та-сигналізація)
4. [Управління ризиками](#4-управління-ризиками)
5. [Прийняття рішень і генерація намірів](#5-прийняття-рішень--генерація-намірів)
6. [Виконання та управління позиціями](#6-виконання-та-управління-позиціями)
7. [Критерії прийняття/відхилення торгів](#7-критерії-прийняттявідхилення-торгів)
8. [Моніторинг портфеля](#8-моніторинг-портфеля)
9. [Адаптація та навчання (Холодний шлях)](#9-адаптація-та-навчання-холодний-шлях)
10. [Надійність та відновлення (Disaster Recovery)](#10-надійність-та-відновлення-disaster-recovery)

---

## 1. ОГЛЯД СИСТЕМИ

### 1.1 Загальна Архітектура

Система Aurora є **федеративною FSM-системою**, де централізована оркестрація координує незалежні компоненти через **шину подій** (Event Bus). Це забезпечує:

- **Розв'язаність**: Компоненти комунікують асинхронно через повідомлення `EVT:*`
- **Масштабованість**: Незалежна обробка кожної валютної пари
- **Надійність**: Повторна спроба, идемпотентність,復原
- **Спостережуваність**: Трасування через `why_chain` (пояснювальні ланцюги)

### 1.2 Основний Потік Торгівлі

```
┌─────────────────┐
│ Binance WebSocket
│  (Market Data)
└────────┬────────┘
         │ price, bid_size, ask_size, buy_vol, sell_vol
         ▼
┌─────────────────────────────┐
│ 1. FEATURE ENGINEERING      │ ← Розраховує OBI, TFI, delta_price
├─────────────────────────────┤
│ Emit: EVT:FEATURES_CALCULATED
└────────┬────────────────────┘
         │
         ├──────────────────────────────────────────┐
         │                                          │
         ▼                                          ▼
┌──────────────────────┐        ┌──────────────────────────┐
│ 2. RISK ASSESSMENT   │        │ 5. REGIME DETECTION      │
├──────────────────────┤        ├──────────────────────────┤
│ • Kelly fraction     │        │ • Тренд визначення       │
│ • CVaR обмеження     │        │ • Волатильність          │
│ • Торгівля дозволена │        │ • SMA crossover          │
└─────────┬────────────┘        └──────────────┬───────────┘
          │                                    │
          │ Emit: EVT:RISK_ASSESSMENT_COMPLETED
          │                    Emit: EVT:REGIME_DETECTED
          │                                    │
          └───────────┬──────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────────┐
│ 3. DECISION MAKING (Core Logic)               │
├───────────────────────────────────────────────┤
│ • Обчислює Signal Score                       │
│ • Перевіряє braking gates                     │
│ • Розраховує position size                    │
│ • Створює Trade Intent                        │
└─────────────┬─────────────────────────────────┘
              │
              ├─→ REJECT (Emit: EVT:TRADE_INTENT_REJECTED)
              │
              ├─→ ACCEPT (Emit: EVT:TRADE_INTENT_PROPOSED)
              │
              ▼
┌────────────────────────────────
│ • OpenFlow: Основний ордер на вхід            │
│ • ManageFlow: Дужки (SL, TP)                  │
│ • CloseFlow: Вихід та управління              │
└───────────────────────────────────────────────┘
              │
              ▼
┌───────────────────────────────────────────────┐
│ 6. PORTFOLIO TRACKING                         │
├───────────────────────────────────────────────┤
│ • Поточна позиція та ціна входу               │
│ • Невідкрити прибутки/збитки                  │
│ • Кумулятивні метрики                         │
└───────────────────────────────────────────────┘
```

### 1.3 Критичні Метрики

| Метрика | Значення | Описання |
|---------|----------|----------|
| **Signal Threshold** | ±0.15 | Поріг для BUY/SELL сигналу |
| **Stop Loss** | 50 bps (0.5%) | Максимальний збиток на позицію |
| **Take Profit Ratio** | 2:1 | Обсяг прибутку до збитку |
| **Kelly Factor Cap** | 0.3-0.6× | Консервативний коефіцієнт Kelly |
| **CVaR Trade Limit** | 100 bps | Max 1% на одну торгівлю |
| **CVaR Session Limit** | 200 bps | Max 2% на сесію |
| **Max Daily Drawdown** | 10% | Circuit breaker |

---

## 2. АРХІТЕКТУРА ТА КОМПОНЕНТИ

### 2.1 Інженерія Ознак (Feature Engineering)

**Відповідальність**: Трансформація сирих даних з Binance в торгові ознаки

**Входи:**
- Bid/Ask розміри (order book depth)
- Купівельні/продажні обсяги (flow)
- Поточна ціна та часовий штамп

**Вихід:**
```
EVT:FEATURES_CALCULATED {
  obi: float (-1.0 до +1.0),
  tfi: float (-1.0 до +1.0),
  delta_price: float (зміна ціни),
  price: float (поточна ціна),
  timestamp: int
}
```

**Формули:**

1. **OBI (Order Book Imbalance)**
   ```
   OBI = (bid_size - ask_size) / (bid_size + ask_size)
   ```
   - Показує дисбаланс попиту/пропозиції
   - +1.0 = максимальний купівельний тиск
   - -1.0 = максимальний продажний тиск

2. **TFI (Trade Flow Imbalance)**
   ```
   TFI = (buy_volume - sell_volume) / (buy_volume + sell_volume)
   ```
   - Показує напрямок грошових потоків
   - Агресивні покупці vs. агресивні продавці

3. **Delta Price**
   ```
   delta_price = current_price - previous_price
   (тільки якщо часова різниця < 1000 ms)
   ```
   - Миттєва зміна ціни
   - Індикатор імпульсу

### 2.2 Детектор Режиму (Regime Detector)

**Відповідальність**: Визначити поточний режим ринку

**Режими:**
- `TREND_UP` - Тренд вгору (SMA_short > SMA_long)
- `TREND_DOWN` - Тренд вниз (SMA_short < SMA_long)
- `NEUTRAL` - Бічний рух (SMA_short ≈ SMA_long)

**Вихід:**
```
EVT:REGIME_DETECTED {
  regime: "TREND_UP" | "TREND_DOWN" | "NEUTRAL",
  confidence: float (0.0-1.0),
  reason: string
}
```

**Використання**: Модифікаторі размеру позицій та фільтри входу

### 2.3 Управління Ризиками (Risk Management)

**Відповідальність**: Оцінити ризик та дозволити/заблокувати торгівлю

**Входи:**
- Поточна ціна
- Портфельний стан (капітал, позиції, збитки)
- Ознаки ринку

**Вихід:**
```
EVT:RISK_ASSESSMENT_COMPLETED {
  is_trading_allowed: bool,
  kelly_fraction: Decimal (0.0-1.0),
  cvar_limit_usd: Decimal,
  daily_loss_usd: Decimal,
  equity_remaining: Decimal
}
```

**Логіка Воріт (Gates):**

1. **Ворота Капіталу**: `equity > min_equity`
2. **Ворота Збитків**: `daily_drawdown < 10%`
3. **Ворота Ризику**: `risk_score < 0.8`
4. **Ворота CVaR**: `session_loss < 200 bps`

### 2.4 Прийняття Рішень (Decision Making)

**Відповідальність**: Синтезувати всі входи та создати торгові наміри

**Входи:**
- Ознаки (OBI, TFI, delta_price)
- Стан ризику (kelly_fraction, cvAR_limit)
- Стан портфеля (позиції, капітал)
- Режим ринку (тренд, впевненість)

**Вихід:**
```
EVT:TRADE_INTENT_PROPOSED {
  symbol: str,
  side: "BUY" | "SELL",
  signal_score: Decimal,
  position_size_usd: Decimal,
  stop_loss_pct: Decimal (0.5%),
  take_profit_pct: Decimal (1.0%),
  kelly_fraction: Decimal,
  why_chain: [explanation_entries]
}
```

**OR**

```
EVT:TRADE_INTENT_REJECTED {
  symbol: str,
  reason: str,
  details: dict
}
```

### 2.5 Виконання Позицій (Execution Position)

**Відповідальність**: Управління повним життєвим циклом позиції

**FSM Стани:**

1. **OpenFlow** - Ордер на вхід
   - Стан: OPEN → PENDING → FILLED
   - Дія: Розмістити основний ордер на вхід

2. **ManageFlow** - Ордери дужок
   - Стан: OPEN → PENDING → FILLED
   - Дія: Розмістити Stop Loss та Take Profit

3. **CloseFlow** - Ордер на вихід
   - Стан: OPEN → PENDING → FILLED
   - Дія: Закрити позицію або частиново виконати

### 2.6 Спостерігач Портфеля (Portfolio Observer)

**Відповідальність**: Синхронізація з рахунком Binance та відстеження метрик

**Функції:**
- Завантажити баланси з API
- Отримати відкриті позиції
- Розрахувати порт-метрики (NLV, max DD, win rate)
- Синхронізувати невідповідності

---

## 3. ІНЖЕНЕРІЯ ОЗНАК ТА СИГНАЛІЗАЦІЯ

### 3.1 Розрахунок Signal Score

**Формула:**
```
Signal Score = (OBI × 0.6) + (TFI × 0.35) + (ΔPrice × 0.05)
```

**Вага Компонентів:**
- **OBI (60%)** - Найважливіша, показує книгу ордерів
- **TFI (35%)** - Потоки грошей, агресивність
- **ΔPrice (5%)** - Імпульс, чутливість до руху

**Приклад Розрахунку:**

| Сценарій | OBI | TFI | ΔPrice | Signal | Рішення |
|----------|-----|-----|--------|--------|---------|
| Сильна покупка | +0.8 | +0.7 | +0.6 | **+0.695** | **BUY** ✅ |
| Сильний продаж | -0.8 | -0.7 | -0.6 | **-0.695** | **SELL** ✅ |
| Змішані сигнали | +0.5 | -0.3 | +0.8 | **+0.315** | **BUY** ✅ |
| Нейтраль | +0.1 | -0.1 | +0.0 | **+0.04** | **HOLD** ❌ |

### 3.2 Порогові Значення

**Buy Signal:**
```
Signal Score > +0.15  →  Формувати ПОКУПНИЙ намір
```

**Sell Signal:**
```
Signal Score < -0.15  →  Формувати ПРОДАЖНИЙ намір
```

**Neutral (No Trade):**
```
-0.15 ≤ Signal Score ≤ +0.15  →  Утримуватись від торгівлі
```

### 3.3 Розпорядження за Сигналом

Після виявлення сигналу система переходить до **Decision Making** для перевірки всіх воріт ризику.

**Алгоритм:**
1. Обчислити Signal Score з ознак
2. Порівняти з порогом (±0.15)
3. Якщо нейтральний → HOLD
4. Якщо BUY → Перейти до гейтів ризику
5. Якщо SELL → Перейти до гейтів ризику

---

## 4. УПРАВЛІННЯ РИЗИКАМИ

### 4.1 Розрахунок Kelly Fraction

**Формула Kelly:**
```
Full Kelly = (2×P - 1) / R

де:
  P = Ймовірність виграшу (~0.55 на тестах)
  R = Payoff Ratio (2:1, тобто R = 2)

Full Kelly = (2×0.55 - 1) / 2 = 0.1 / 2 = 0.05 (5%)
```

**Консервативна Kelly (Рекомендована):**
```
Conservative Kelly = Full Kelly × kelly_alpha
                   = Full Kelly × kelly_cap

де kelly_alpha = 0.3-0.6 (залежить від впевненості)

Приклад:
  Estimated Kelly = min(0.05, kelly_cap_0.05) = 0.05
  Conservative Kelly = 0.05 × 0.5 = 0.025 (2.5% капіталу)
```

### 4.2 Обчислення Розміру Позиції

**Крок 1: Базовий Van Tharp Model**
```
Position Size = (Risk per Trade $ / Stop Loss %) × (Price / 1.0)

Приклад:
  Капітал = $100,000
  Risk per Trade = 1% = $1,000
  Stop Loss = 50 bps = 0.5%

  Position Size = $1,000 / 0.5% = $200,000 (в купівельній спроможності)
  (Але це занадто велико → потрібні ліміти)
```

**Крок 2: CVaR Обмеження**
```
CVaR Limit per Trade = equity × 100 bps = $100,000 × 1% = $1,000
CVaR Limit per Session = equity × 200 bps = $100,000 × 2% = $2,000

Size = min(Size, CVaR_trade_limit, CVaR_session_limit)
```

**Крок 3: Ліквідність та Граничні Значення**
```
Liquidity Cap = $10,000 (за замовчуванням)
Min Position = $10
Max Position = $50,000

Final Size = min(Van Tharp Size, CVaR Limits, Liquidity Cap)
           = min($200,000, $1,000, $10,000)
           = $1,000
```

### 4.3 Ворота Ризику (Risk Gates)

**Ворота 1: Trading Allowed Flag**
```
IF is_trading_allowed == False:
  → REJECT з причиною "Trading Disabled"
```

**Ворота 2: Daily Drawdown**
```
daily_loss = abs(portfolio_loss)
max_daily_loss = equity × 10% = $100,000 × 10% = $10,000

IF daily_loss > max_daily_loss:
  → REJECT з причиною "Daily Loss Limit Exceeded"
```

**Ворота 3: Risk Score**
```
Risk Score = f(volatility, exposure, concentration)

IF risk_score > 0.8:
  → REJECT з причиною "Risk Score Too High"
```

**Ворота 4: Equity Requirement**
```
IF equity < min_equity ($100):
  → REJECT з причиною "Insufficient Equity"
```

---

## 5. ПРИЙНЯТТЯ РІШЕНЬ – ГЕНЕРАЦІЯ НАМІРІВ

### 5.1 Алгоритм Decision Making

**Pseudocode:**

```
function make_decision_for_symbol(symbol):
    # Крок 1: Перевірити наявність всіх входів
    IF NOT (features AND risk AND portfolio):
        RETURN None  # Чекаємо всіх даних

    # Крок 2: Перевірити cooling period
    IF symbol IN cooling_symbols AND NOT time_passed:
        RETURN None  # Занадто часто торгуємо одну пару

    # Крок 3: Обчислити Signal Score
    obi = features["obi"]
    tfi = features["tfi"]
    delta_price = features["delta_price"]

    signal_score = (obi × 0.6) + (tfi × 0.35) + (delta_price × 0.05)

    # Крок 4: Перевірити сигнальний поріг
    IF ABS(signal_score) < 0.15:
        EMIT EVT:TRADE_INTENT_REJECTED with "Neutral Signal"
        RETURN None

    # Крок 5: Визначити напрямок
    intended_side = "buy" IF signal_score > 0.15 ELSE "sell"

    # Крок 6: Перевірити ворота ризику
    IF NOT risk["is_trading_allowed"]:
        EMIT EVT:TRADE_INTENT_REJECTED with "Trading Disabled"
        RETURN None

    IF daily_loss > max_daily_loss:
        EMIT EVT:TRADE_INTENT_REJECTED with "Daily Loss Limit"
        RETURN None

    # Крок 7: Перевірити наявну позицію
    current_position = find_position(symbol)
    IF current_position AND same_side(current_position, intended_side):
        EMIT EVT:TRADE_INTENT_REJECTED with "Position Exists"
        RETURN None

    # Крок 8: Розрахувати розмір позиції
    position_size = calculate_position_size(
        kelly_fraction=risk["kelly_fraction"],
        equity=portfolio["equity"],
        stop_loss=0.5%,
        cvar_limit=risk["cvar_limit_usd"]
    )

    # Крок 9: Застосувати ліміти
    position_size = apply_caps(position_size)

    # Крок 10: Створити Trade Intent
    trade_intent = {
        symbol: symbol,
        side: intended_side,
        signal_score: signal_score,
        position_size_usd: position_size,
        stop_loss_pct: 0.5,
        take_profit_pct: 1.0,
        kelly_fraction: risk["kelly_fraction"],
        why_chain: [
            f"Signal Score: {signal_score:.3f}",
            f"Intended Side: {intended_side}",
            f"Position Size: {position_size:.2f} USD",
            ...
        ]
    }

    EMIT EVT:TRADE_INTENT_PROPOSED with trade_intent
    RETURN trade_intent
```

### 5.2 Why Chain Documentation

Кожне рішення документується через `why_chain` - послідовність пояснень:

**Приклад Why Chain:**

```
[
  "Signal Score: +0.485 (OBI=+0.6, TFI=+0.35, ΔP=+0.15)",
  "Signal Threshold: +0.15 → BUY signal triggered",
  "Trading Allowed: true",
  "Daily Loss Check: -$250 < -$10,000 → OK",
  "Position Check: No existing ETHUSDT position",
  "Kelly Calculation: Full=5%, Conservative=2.5%",
  "Van Tharp Size: $1,000 (1% risk of $100k)",
  "CVaR Trade Limit: $1,000 (1% of equity)",
  "CVaR Session Limit: $2,000 (2% of equity)",
  "Liquidity Cap: $10,000",
  "Final Position: $1,000 (Min of all caps)",
  "Regime: TREND_UP (confidence=0.85)",
  "Trade Intent: PROPOSED [RID=xyz123]"
]
```

---

## 6. ВИКОНАННЯ ТА УПРАВЛІННЯ ПОЗИЦІЯМИ

### 6.1 Життєвий Цикл Позиції

**Фаза 1: OpenFlow (Вхід)**

```
State Flow:
  IDLE → OPEN → PENDING → FILLED → SUCCESS

Дії:
1. Отримати EVT:TRADE_INTENT_PROPOSED
2. Розмістити основний ордер (BUY або SELL)
3. Ждати підтвердження від Binance
4. При FILLED:
   - Запам'ятати ціну входу
   - Запустити ManageFlow для дужок
   - Оновити стан портфеля

Приклад:
  Intent: BUY 2.5 ETH за $2,500
  → Ордер: LIMIT buy 2.5 ETHUSDT @ current_price
  → Статус: PENDING
  → (кілька сек)
  → Статус: FILLED ✅
  → Ціна входу: $2,500
```

**Фаза 2: ManageFlow (Дужки)**

```
Після заповнення основного ордера:

1. Розмістити Stop Loss ордер:
   - Side: SELL (протилежна)
   - Quantity: Та сама (2.5 ETH)
   - Price: entry_price × (1 - stop_loss_pct)
           = $1,000 × (1 - 0.5%)
           = $995 (максимум $5 збитку)

2. Розмістити Take Profit ордер:
   - Side: SELL
   - Quantity: Та сама (2.5 ETH)
   - Price: entry_price × (1 + take_profit_pct)
           = $1,000 × (1 + 1%)
           = $1,010 (мінімум $10 прибутку)

Брекет Ордер:
  ┌─────────────────────────────────────┐
  │         TAKE PROFIT: $1,010         │
  │              (SELL)                 │
  ├─────────────────────────────────────┤
  │        ENTRY: $1,000 (BUY FILLED)   │ ← Основна позиція
  ├─────────────────────────────────────┤
  │         STOP LOSS: $995             │
  │              (SELL)                 │
  └─────────────────────────────────────┘
```

**Фаза 3: CloseFlow (Вихід)**

```
Сценарій 1: Take Profit Fill
  - TP ордер виконаний → Прибуток +$10
  - SL ордер скасований
  - Позиція закрита → Portfolio updated
  - Event: EVT:POSITION_CLOSED {side: "win", pnl: +10}

Сценарій 2: Stop Loss Fill
  - SL ордер виконаний → Збиток -$5
  - TP ордер скасований
  - Позиція закрита → Portfolio updated
  - Event: EVT:POSITION_CLOSED {side: "loss", pnl: -5}

Сценарій 3: Manual Close
  - Користувач скасовує дужки
  - Розміщує ордер на закриття позиції
  - Прибуток/Збиток = поточна_ціна - ціна_входу

Сценарій 4: Timeout
  - Ордер не заповнений за 60 сек
  - Система скасовує та логує
  - Опціонально: переспроба або алерт
```

### 6.2 Управління Портфелем

**Структура Портфеля:**

```json
{
  "equity": 100000.00,
  "initial_equity": 100000.00,
  "available_balance": 99000.00,
  "margin_used": 1000.00,
  "positions": [
    {
      "symbol": "ETHUSDT",
      "side": "BUY",
      "quantity": 2.5,
      "entry_price": 1000.00,
      "current_price": 1005.00,
      "unrealized_pnl": 12.50,
      "unrealized_pnl_pct": 1.25,
      "stop_loss_price": 995.00,
      "take_profit_price": 1010.00,
      "created_at": "2025-11-04T10:30:00Z"
    }
  ],
  "metrics": {
    "total_pnl": 250.00,
    "total_pnl_pct": 0.25,
    "max_drawdown": -500.00,
    "max_drawdown_pct": 0.5,
    "win_rate": 0.65,
    "profit_factor": 2.1,
    "sharpe_ratio": 1.45
  }
}
```

**Обновлення Метрик:**

```
After Each Trade:
  1. Update current_price from latest market data
  2. Calculate unrealized_pnl = (current_price - entry_price) × quantity
  3. Calculate unrealized_pnl_pct = unrealized_pnl / (entry_price × quantity)
  4. Update max_drawdown = min(max_drawdown, unrealized_pnl)
  5. Update equity = initial_equity + total_pnl + unrealized_pnl
  6. Check if any position hit SL or TP

Every Minute:
  1. Fetch latest balances from Binance API
  2. Reconcile with internal state
  3. Log any discrepancies (drift detection)
  4. Emit EVT:PORTFOLIO_STATE_UPDATED
```

---

## 7. КРИТЕРІЇ ПРИЙНЯТТЯ/ВІДХИЛЕННЯ ТОРГІВ

### 7.1 Причини Відхилення (Rejection Reasons)

| Причина | Ворота | Опис | Рішення |
|---------|--------|------|---------|
| **Neutral Signal** | Signal | \|Score\| < 0.15 | Чекати сильнішого сигналу |
| **Trading Disabled** | Risk | is_trading_allowed = false | Чекати скидання прапора |
| **Daily Loss Limit** | Risk | Щоденний збиток > 10% | Чекати нового дня |
| **Position Exists** | Portfolio | На позицію вже торгують | Закрити поточну позицію |
| **Same Direction** | Portfolio | Вже є позиція тією ж стороною | Різні сигнали? |
| **Insufficient Equity** | Risk | Капітал < мінімум | Депозит або чекати |
| **Risk Score High** | Risk | risk_score > 0.8 | Зменшити експозицію |
| **CVaR Exceeded** | Risk | Сесійний ризик > 200 bps | Очікувати на скидання |
| **Regime Conflict** | Regime | Режим не підтримує сигнал | Фільтр за режимом ринку |
| **Cooling Period** | State | Торгувався символ < 30 сек | Охолоджувальний період |

### 7.2 Ієрархія Воріт

```
┌─────────────────────────────────────┐
│    1. SIGNAL CHECK (Міст звіти)     │
│  Signal Score > |0.15|? → Continue  │
│                | → REJECT "Neutral" │
└────────────────┬────────────────────┘
                 │
        ┌────────▼────────┐
        │   2. RISK GATES │
        └────────┬────────┘
                 │
        ┌────────▼──────────────────────┐
        │ is_trading_allowed?            │
        │ NO  → REJECT "Trading Disabled"│
        │ YES → Continue                 │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │ Daily Loss < 10%?              │
        │ NO  → REJECT "Loss Limit"      │
        │ YES → Continue                 │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │ Position Exists (same side)?   │
        │ YES → REJECT "Position Exists" │
        │ NO  → Continue                 │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │ Cooling Period Elapsed?        │
        │ NO  → REJECT "Cooling Period"  │
        │ YES → Continue                 │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │ Size Calculation & Caps        │
        │ → Apply all limits             │
        │ → Final Position Size          │
        └────────┬──────────────────────┘
                 │
        ┌────────▼──────────────────────┐
        │   ✅ TRADE INTENT PROPOSED    │
        │   Size: ${final_size}          │
        └────────────────────────────────┘
```

### 7.3 Логування Рішень

Кожне рішення логується структурованим JSONL форматом:

```json
{
  "timestamp": "2025-11-04T10:30:45.123Z",
  "rid": "trade-ethusdt-20251104-103045",
  "symbol": "ETHUSDT",
  "event_type": "EVT:TRADE_INTENT_PROPOSED",
  "signal_score": 0.485,
  "decision": "ACCEPT",
  "gates_passed": [
    {"name": "signal_check", "result": "pass", "value": 0.485},
    {"name": "trading_allowed", "result": "pass", "value": true},
    {"name": "daily_loss", "result": "pass", "value": -250},
    {"name": "position_check", "result": "pass", "value": null}
  ],
  "position_size_usd": 1000.0,
  "kelly_fraction": 0.025,
  "why_chain": ["Signal: +0.485 > 0.15", "All gates passed", "Size: $1000"],
  "user_id": "trader-1",
  "session_id": "session-xyz"
}
```

---

## 8. МОНІТОРИНГ ПОРТФЕЛЯ

### 8.1 Метрики Портфеля

**Метрики на Реальному Часі:**

| Метрика | Формула | Оновлення |
|---------|---------|----------|
| **Equity** | `initial_equity + cumulative_pnl` | Кожна закрита позиція |
| **Unrealized PnL** | `Σ(current_price - entry_price) × qty` | Кожна нова ціна |
| **Total Return** | `(Equity - Initial) / Initial` | Постійно |
| **Max Drawdown** | `min(Equity) - Initial Equity` | Постійно |
| **Win Rate** | `wins / (wins + losses)` | Кожна закрита позиція |
| **Profit Factor** | `gross_profit / gross_loss` | Кожна закрита позиція |
| **Sharpe Ratio** | `mean_return / std_dev` | Щодня |

**Приклад Розрахунку:**

```
Сесія: 10:00-12:00
Торги:
  1. BUY 2.5 ETH @ $1000 → SELL @ $1010 → +$10 (Win)
  2. BUY 3.0 BTC @ $50000 → SELL @ $49800 → -$600 (Loss)
  3. BUY 1.5 ETH @ $1000 → SELL @ $1020 → +$30 (Win)

Портфель:
  Wins: 2 (trades 1, 3)
  Losses: 1 (trade 2)
  Total PnL: +10 - 600 + 30 = -$560
  Win Rate: 2/3 = 66.7%
  Profit Factor: 40 / 600 = 0.067 (LOSS) ❌
```

### 8.2 Моніторинг Ризику

**Перевірки кожні 60 сек:**

```python
def monitor_portfolio():
    portfolio = get_portfolio()

    # 1. Перевірити max drawdown
    current_dd = (portfolio.equity - portfolio.initial_equity)
    max_dd = portfolio.max_drawdown

    if abs(current_dd) > portfolio.max_daily_loss:
        alert(f"Daily Loss Limit Reached: {current_dd:.2f}")
        halt_trading()

    # 2. Перевірити відкриті позиції
    for position in portfolio.positions:
        current_price = get_current_price(position.symbol)

        # Перевірити SL
        if position.side == "BUY" and current_price < position.stop_loss_price:
            execute_sl_order(position)

        # Перевірити TP
        if position.side == "BUY" and current_price > position.take_profit_price:
            execute_tp_order(position)

    # 3. Перевірити Drift (Розбіжність)
    account = binance_api.get_account()
    if account_state != portfolio:
        log_drift(account_state, portfolio)
        # Можливо синхронізувати або алерт

    # 4. Обновити метрики
    portfolio.update_metrics(current_price)
    emit(EVT:PORTFOLIO_METRICS_UPDATED, portfolio.metrics)
```

### 8.3 Алерти та Дії

| Умова | Алерт | Дія |
|-------|-------|-----|
| Max DD > 10% | 🔴 **CRITICAL** | Зупинити торгівлю |
| Daily Loss > 5% | 🟠 **WARNING** | Зменшити розмір |
| Win Rate < 50% | 🟡 **INFO** | Переглянути сигнали |
| Drift > 1% | 🟡 **INFO** | Синхронізувати |
| Open Position > 30 min | 🟡 **INFO** | Проконтролювати |

---

## ЗАКЛЮЧЕННЯ

Система Aurora реалізує **розумну, многоуровневу логіку торгівлі**:

1. **Ознаки** → OBI, TFI, ΔPrice показують ринковий стан
2. **Сигнали** → Зважена комбінація виявляє BUY/SELL можливості
3. **Ризик** → Kelly fraction + CVaR caps контролюють експозицію
4. **Рішення** → Множинні ворота гарантують безпеку
5. **Виконання** → FSM управляє повним циклом позиції
6. **Моніторинг** → Постійне відстеження метрик та ризиків

**Ключові Принципи:**
- ✅ **Адитивна структура**: Усі ворота повинні пройтися
- ✅ **Прозорість**: Кожне рішення задокументовано в `why_chain`
- ✅ **Безпека**: Консервативна Kelly, multi-cap позиціонування
- ✅ **Спостережуваність**: JSONL логування, метрики, трасування
- ✅ **Надійність**: Обробка помилок, восстановлення, idempotency

---

**Документ створено:** Листопад 2025
**Версія:** 1.0 | Статус: Актуальний
**Для питань:** Зверніться до архітектури або документів ROADMAP

---

## 9. АДАПТАЦІЯ ТА НАВЧАННЯ (ХОЛОДНИЙ ШЛЯХ)

Поточна логіка системи (гарячий шлях) оптимізована для швидкого прийняття рішень. Однак, щоб залишатися ефективною в умовах ринку, що постійно змінюється, система Aurora включає **холодний шлях** для адаптації та навчання. Цей процес працює асинхронно і не впливає на швидкість виконання торгів.

### 9.1 Компоненти Холодного Шляху

| Компонент | Відповідальність | Опис |
|---|---|---|
| **`rl_core`** | Reinforcement Learning Core | Аналізує історичні дані про торги, ринкові умови та результати (PnL), щоб знайти оптимальніші параметри. |
| **`reward_alysha`** | Reward Function | Розраховує "винагороду" для кожного торгового рішення, враховуючи не тільки прибуток, але й ризик, просідання та інші метрики якості. |
| **`xai_audit`** | Explainable AI Audit | Надає інтерпретацію рішень, прийнятих моделями машинного навчання, забезпечуючи прозорість та контроль. |
| **`data_monitoring`** | Data Monitoring | Відстежує якість вхідних даних та виявляє аномалії або зміщення (drift), які можуть вплинути на якість сигналів. |

### 9.2 Процес Навчання

1.  **Збір Даних**: Усі торгові події, рішення (`why_chain`), ринкові дані та метрики портфеля зберігаються в довгостроковому сховищі.
2.  **Розрахунок Винагороди**: Компонент `reward_alysha` оцінює кожну закриту позицію, присвоюючи їй бал винагороди. Наприклад, швидкий прибуток з низьким ризиком отримує вищу оцінку, ніж такий самий прибуток, але з високою волатильністю.
3.  **Тренування Моделі**: `rl_core` періодично (наприклад, раз на тиждень) використовує накопичені дані та бали винагороди для тренування нової версії моделі. Мета — максимізувати сукупну винагороду.
4.  **Валідація та "Канарковий" Реліз**:
    *   Нова модель проходить ретельне тестування на історичних даних (backtesting).
    *   Якщо результати позитивні, нові параметри (наприклад, ваги для `Signal Score` або пороги) розгортаються в режимі **"canary"** — спочатку застосовуються до невеликого відсотка капіталу або до однієї торгової пари.
5.  **Повне Розгортання**: Якщо "канарковий" реліз показує стабільну та покращену ефективність протягом певного періоду, нові параметри поступово розгортаються на всю систему.

Цей цикл дозволяє системі Aurora адаптуватися до нових ринкових умов, оптимізувати свою стратегію та зменшувати ризик деградації моделі з часом.

---

## 10. НАДІЙНІСТЬ ТА ВІДНОВЛЕННЯ (DISASTER RECOVERY)

Архітектура системи розроблена з урахуванням можливих збоїв. Головна мета — гарантувати, що жоден збій не призведе до втрати коштів або неконтрольованої поведінки. Це досягається за допомогою наступних механізмів, реалізованих у `vfoundation`.

### 10.1 Write-Ahead Log (WAL)

Кожна вхідна подія та кожне прийняте рішення (намір) перед обробкою записуються в **журнал упереджувального запису (WAL)**.
- **Призначення**: Якщо компонент (FSM) виходить з ладу посеред операції, після перезапуску він може відновити свій стан, "відтворивши" події з WAL, які ще не були повністю оброблені.
- **Приклад**: Система вирішила відкрити позицію, записала намір у WAL, але зазнала збою перед відправкою ордера на біржу. Після перезапуску вона перевірить WAL, побачить незавершений намір і або завершить його, або скасує, уникнувши подвійного відкриття.

### 10.2 Знімки Стану (Snapshots) та Відтворення (Replay)

- **Знімки Стану**: Періодично (наприклад, кожні 5 хвилин) система зберігає повний знімок стану всіх ключових компонентів (наприклад, стану портфеля, відкритих позицій, конфігурацій).
- **Відтворення (Replay)**: У випадку критичного збою, що унеможливлює простий перезапуск, система може відновитися наступним чином:
    1.  Завантажити останній стабільний знімок стану.
    2.  "Відтворити" (replay) всі події з WAL, що сталися *після* створення знімка.

Це гарантує, що система повернеться до консистентного стану, максимально наближеного до моменту збою, без втрати даних про позиції чи фінанси.

### 10.3 Ідемпотентність та Time-to-Live (TTL)

- **Ідемпотентність**: Кожна операція, що змінює стан (наприклад, відкриття позиції), розроблена так, щоб її повторне виконання не змінювало результат. Кожному ордеру присвоюється унікальний ідентифікатор (`clientOrderId`). Спроба відправити ордер з тим самим ID двічі не призведе до створення двох ордерів.
- **TTL (Час Життя)**: Кожен намір або команда має обмежений "час життя". Якщо, наприклад, намір на відкриття позиції не був виконаний протягом 60 секунд (через затримки або збій), він автоматично анулюється, щоб уникнути виконання застарілих рішень у невідповідних ринкових умовах.

Ці механізми разом створюють надійну систему, здатну переживати збої окремих компонентів або навіть повний перезапуск, мінімізуючи ризики для капіталу.
