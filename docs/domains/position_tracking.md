# Домен Position Tracking (Відстеження Позицій)

## Загальна інформація

**Ідентифікатор домену:** `position_tracking`  
**Роль в системі:** Центр стану портфеля та розрахунку P&L

## Архітектурна роль

Домен `position_tracking` є центральним сховищем стану торгового портфеля в системі Aurora. Він інтегрує дані про виконані трейди, баланс рахунку та позиції, розраховуючи realized/unrealized P&L та підтримуючи актуальний стан equity.

### Відповідальність
- Відстеження всіх відкритих позицій по символах
- Розрахунок realized та unrealized P&L
- Агрегація даних про equity портфеля
- WAL інтеграція для disaster recovery
- Емісія оновлень стану портфеля

## Структура домену

### Основні компоненти

#### PositionTracking
Головний клас домену, що управляє станом портфеля.

**Ініціалізація:**
- Підписка на події трейдів та оновлень рахунку
- Ініціалізація структур даних для позицій та P&L
- Налаштування WAL інтеграції

**Методи життєвого циклу:**
- `start()` - запуск компоненту
- `on_trade_executed()` - обробка виконаних трейдів
- `on_account_update()` - обробка оновлень рахунку

### Внутрішня архітектура

#### Управління позиціями
```
_positions: Dict[str, Dict[str, Any]]
    ├── symbol -> position data
    ├── avg_price: середня ціна входу
    ├── quantity: поточна кількість
    ├── realized_pnl: реалізваний P&L
    └── venue: біржа виконання
```

#### WAL інтеграція
```
on_trade_executed() -> WAL write first
    ├── Запис події в WAL перед обробкою
    ├── Критична зупинка при WAL failure
    ├── Безперервність при disaster recovery
```

## FSM події

### Генеровані події

#### EVT:PORTFOLIO_STATE_UPDATED
**Частота:** Після кожного EVT:TRADE_EXECUTED  
**Направлення:** Decision Making, Risk Management, Audit Trail  

**Payload структура:**
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

**Опис:** Передає повний стан портфеля після кожного трейду.

### Споживані події

#### EVT:TRADE_EXECUTED
**Джерело:** Account Observer  
**Використання:** Отримання даних про виконані трейди для оновлення позицій  
**Частота:** Подієво при нових трейдах

#### EVT:ACCOUNT_UPDATE_RECEIVED
**Джерело:** Account Balance  
**Використання:** Отримання даних про позиції з біржі  
**Частота:** Реального часу (30 сек)

#### EVT:BALANCE_UPDATE_RECEIVED
**Джерело:** Account Balance  
**Використання:** Отримання даних про баланс активів  
**Частота:** Реального часу (30 сек)

## Взаємодія з іншими доменами

### Синхронні зв'язки

#### Account Observer
- **Вхід:** EVT:TRADE_EXECUTED
- **Використання:** Отримання трейдів для оновлення позицій
- **Частота:** Подієво

#### Account Balance
- **Вхід:** EVT:ACCOUNT_UPDATE_RECEIVED, EVT:BALANCE_UPDATE_RECEIVED
- **Використання:** Синхронізація з біржовими даними
- **Частота:** Реального часу

#### Decision Making
- **Вихід:** EVT:PORTFOLIO_STATE_UPDATED
- **Використання:** Дані про equity для sizing рішень
- **Частота:** Після кожного трейду

#### Risk Management
- **Вихід:** EVT:PORTFOLIO_STATE_UPDATED
- **Використання:** Розрахунок ризиків портфеля
- **Частота:** Після кожного трейду

### Асинхронні залежності
Критичний для всіх доменів, що потребують даних про портфель.

## Розрахунок P&L

### Realized P&L
```
realized_pnl += (exit_price - entry_price) × quantity - fees
```
**Тригер:** При закритті або частковому закритті позиції.

### Unrealized P&L
```
unrealized_pnl = Σ(current_price - avg_entry_price) × quantity
```
**Тригер:** При кожному оновленні цін або позицій.

### Equity
```
equity = wallet_balance + unrealized_pnl
```
**Джерело:** Баланс рахунку + нереалізований P&L.

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
- Всі зміни позицій записуються в WAL
- Можливість відновлення стану після збоїв
- Консистентність даних при перезапуску

## Конфігурація

### Основні параметри
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
- **live:** Відстеження бойових позицій
- **testnet:** Відстеження тестових позицій

## Моніторинг та діагностика

### Метрики
- Кількість відкритих позицій
- Total realized/unrealized P&L
- Equity changes over time
- WAL write success rate

### Логування
- **Інформаційні:** Оновлення портфеля, розрахунки P&L
- **Попередження:** Несоответствия з біржовими даними
- **Критичні:** WAL write failures

## Обробка помилок

### Стратегії відновлення
1. **WAL failure:** Критична зупинка обробки
2. **Invalid data:** Логування та пропуск проблемних трейдів
3. **State inconsistency:** Перевірка та корекція при наступних оновленнях

### Data Validation
- Перевірка цінових даних на валідацію
- Валідація quantity та side
- Контроль цілісності позицій

## Тестування

### Інтеграційні тести
- Валідація розрахунків P&L
- Перевірка WAL інтеграції
- Тестування відновлення стану

### Модульні тести
- Перевірка логіки оновлення позицій
- Валідація P&L розрахунків
- Тестування error handling

## Архітектурні особливості

### Single Source of Truth
Position Tracking є єдиним джерелом правди для:
- Поточного стану портфеля
- Історичних P&L даних
- Equity розрахунків

### WAL-first Design
Всі зміни записуються в WAL перед обробкою, що забезпечує:
- Atomicity операцій
- Durability при збої
- Consistency при відновленні