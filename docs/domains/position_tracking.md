# Домен Position Tracking (Від� теження Позицій)

## Загальна інформація

**Ідентифікатор домену:** `position_tracking`  
**Роль в � и� темі:** Центр � тану портфеля та розрахунку P&L

## Архітектурна роль

Домен `position_tracking` є центральним � ховищем � тану торгового портфеля в � и� темі Aurora. Він інтегрує дані про виконані трейди, балан�  рахунку та позиції, розраховуючи realized/unrealized P&L та підтримуючи актуальний � тан equity.

### Відповідальні� ть
- Від� теження в� іх відкритих позицій по � имволах
- Розрахунок realized та unrealized P&L
- Агрегація даних про equity портфеля
- WAL інтеграція для disaster recovery
- Емі� ія оновлень � тану портфеля

## Структура домену

### О� новні компоненти

#### PositionTracking
Головний кла�  домену, що управляє � таном портфеля.

**Ініціалізація:**
- Підпи� ка на події трейдів та оновлень рахунку
- Ініціалізація � труктур даних для позицій та P&L
- Налаштування WAL інтеграції

**Методи життєвого циклу:**
- `start()` - запу� к компоненту
- `on_trade_executed()` - обробка виконаних трейдів
- `on_account_update()` - обробка оновлень рахунку

### Внутрішня архітектура

#### Управління позиціями
```
_positions: Dict[str, Dict[str, Any]]
    ├── symbol -> position data
    ├── avg_price: � ередня ціна входу
    ├── quantity: поточна кількі� ть
    ├── realized_pnl: реалізваний P&L
    └── venue: біржа виконання
```

#### WAL інтеграція
```
on_trade_executed() -> WAL write first
    ├── Запи�  події в WAL перед обробкою
    ├── Критична зупинка при WAL failure
    ├── Безперервні� ть при disaster recovery
```

## FSM події

### Генеровані події

#### EVT:PORTFOLIO_STATE_UPDATED
**Ча� тота:** Пі� ля кожного EVT:TRADE_EXECUTED  
**Направлення:** Decision Making, Risk Management, Audit Trail  

**Payload � труктура:**
```json
{
  "ts": 1640995200000,
  "equity": "1000.50",
  "realized_pnl": "25.30",
  "unrealized_pnl": "-5.20",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "quantity": "0.001",
      "avg_price": "50000.00",
      "current_price": "50250.00",
      "unrealized_pnl": "2.50",
      "realized_pnl": "0.00"
    }
  ]
}
```

**Опи� :** Передає повний � тан портфеля пі� ля кожного трейду.

### Споживані події

#### EVT:TRADE_EXECUTED
**Джерело:** Account Observer  
**Викори� тання:** Отримання даних про виконані трейди для оновлення позицій  
**Ча� тота:** Подієво при нових трейдах

#### EVT:ACCOUNT_UPDATE_RECEIVED
**Джерело:** Account Balance  
**Викори� тання:** Отримання даних про позиції з біржі  
**Ча� тота:** Реального ча� у (30 � ек)

#### EVT:BALANCE_UPDATE_RECEIVED
**Джерело:** Account Balance  
**Викори� тання:** Отримання даних про балан�  активів  
**Ча� тота:** Реального ча� у (30 � ек)

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Account Observer
- **Вхід:** EVT:TRADE_EXECUTED
- **Викори� тання:** Отримання трейдів для оновлення позицій
- **Ча� тота:** Подієво

#### Account Balance
- **Вхід:** EVT:ACCOUNT_UPDATE_RECEIVED, EVT:BALANCE_UPDATE_RECEIVED
- **Викори� тання:** Синхронізація з біржовими даними
- **Ча� тота:** Реального ча� у

#### Decision Making
- **Вихід:** EVT:PORTFOLIO_STATE_UPDATED
- **Викори� тання:** Дані про equity для sizing рішень
- **Ча� тота:** Пі� ля кожного трейду

#### Risk Management
- **Вихід:** EVT:PORTFOLIO_STATE_UPDATED
- **Викори� тання:** Розрахунок ризиків портфеля
- **Ча� тота:** Пі� ля кожного трейду

### А� инхронні залежно� ті
Критичний для в� іх доменів, що потребують даних про портфель.

## Розрахунок P&L

### Realized P&L
```
realized_pnl += (exit_price - entry_price) × quantity - fees
```
**Тригер:** При закритті або ча� тковому закритті позиції.

### Unrealized P&L
```
unrealized_pnl = Σ(current_price - avg_entry_price) × quantity
```
**Тригер:** При кожному оновленні цін або позицій.

### Equity
```
equity = wallet_balance + unrealized_pnl
```
**Джерело:** Балан�  рахунку + нереалізований P&L.

## WAL та Disaster Recovery

### WAL-first підхід
```python
# Write to WAL BEFORE processing
wal_hash = wal.append(event_dict)
if wal_hash is None:
    # CRITICAL: Halt processing
    return
```

**Мета:** Гарантія durability перед state mutation.

### State Persistence
- В� і зміни позицій запи� ують� я в WAL
- Можливі� ть відновлення � тану пі� ля збоїв
- Кон� и� тентні� ть даних при перезапу� ку

## Конфігурація

### О� новні параметри
```yaml
system:
  trading:
    instruments:
      BTCUSDT:
        step_size: "0.001"
      ETHUSDT:
        step_size: "0.01"
```

### Режими роботи
- **live:** Від� теження бойових позицій
- **testnet:** Від� теження те� тових позицій

## Моніторинг та діагно� тика

### Метрики
- Кількі� ть відкритих позицій
- Total realized/unrealized P&L
- Equity changes over time
- WAL write success rate

### Логування
- **Інформаційні:** Оновлення портфеля, розрахунки P&L
- **Попередження:** Не� оответ� твия з біржовими даними
- **Критичні:** WAL write failures

## Обробка помилок

### Стратегії відновлення
1. **WAL failure:** Критична зупинка обробки
2. **Invalid data:** Логування та пропу� к проблемних трейдів
3. **State inconsistency:** Перевірка та корекція при на� тупних оновленнях

### Data Validation
- Перевірка цінових даних на валідацію
- Валідація quantity та side
- Контроль цілі� но� ті позицій

## Те� тування

### Інтеграційні те� ти
- Валідація розрахунків P&L
- Перевірка WAL інтеграції
- Те� тування відновлення � тану

### Модульні те� ти
- Перевірка логіки оновлення позицій
- Валідація P&L розрахунків
- Те� тування error handling

## Архітектурні о� обливо� ті

### Single Source of Truth
Position Tracking є єдиним джерелом правди для:
- Поточного � тану портфеля
- І� торичних P&L даних
- Equity розрахунків

### WAL-first Design
В� і зміни запи� ують� я в WAL перед обробкою, що забезпечує:
- Atomicity операцій
- Durability при збої
- Consistency при відновленні