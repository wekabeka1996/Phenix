# Account Balance Domain (Домен Балансу Рахунку)

## Огляд

Домен `account_balance` є фундаментальним компонентом системи Aurora, що забезпечує моніторинг фінансового стану торгового рахунку на Binance Futures. Він виступає як міст між біржовими API та внутрішньою логікою системи, перетворюючи сирі дані балансу в структуровані FSM події.

## Архітектурна роль

### Відповідальність
- **Моніторинг балансу:** Отримання та обробка даних про баланс активів з Binance Futures API
- **Відстеження позицій:** Моніторинг відкритих ф'ючерсних позицій в режимі реального часу
- **Стандартизація даних:** Перетворення сирих API даних в стандартизовані події FSM системи
- **Надійність:** Забезпечення актуальності фінансового стану для прийняття торгових рішень

### Критичність для системи
Домен є критичним компонентом, оскільки його дані використовуються:
- **Risk Management** для оцінки ризиків портфеля
- **Decision Making** для розрахунку розмірів позицій
- **Position Tracking** для синхронізації стану портфеля
- **Execution Management** для валідації доступного капіталу

## Структура домену

```
account_balance/
├── README.md              # Цей файл - огляд домену
├── documentation.md       # Детальна документація FSM подій та взаємодій
├── architecture.md        # Архітектурна схема та робочі процеси
├── dictionaries.yaml      # Словники даних та конфігурації
├── functions.md           # Реалізовані функції та методи
├── examples/              # Приклади коду та конфігурації
│   ├── config.yaml        # Приклад конфігурації
│   ├── usage.py           # Приклад використання
│   └── tests/             # Тестові приклади
└── schema.json           # JSON Schema для валідації подій
```

## Основні компоненти

### AccountConnector
Головний клас домену, що реалізує підключення до Binance API та моніторинг рахунку.

**Ключові можливості:**
- Автоматичний вибір API залежно від режиму роботи (live/testnet/hybrid)
- Фоновий моніторинг з конфігурованим інтервалом
- Graceful degradation при проблемах з API
- Структурована емісія FSM подій

## FSM події

### Генеровані події
- `EVT:BALANCE_UPDATE_RECEIVED` - Оновлення балансу активів
- `EVT:ACCOUNT_UPDATE_RECEIVED` - Оновлення стану рахунку та позицій

### Споживані події
Домен працює автономно і не споживає зовнішні події.

## Взаємодії з доменами

### Синхронні зв'язки
- **Position Tracking** ← `EVT:ACCOUNT_UPDATE_RECEIVED`
- **Risk Management** ← `EVT:BALANCE_UPDATE_RECEIVED`, `EVT:ACCOUNT_UPDATE_RECEIVED`
- **Decision Making** ← `EVT:BALANCE_UPDATE_RECEIVED`

### Асинхронні залежності
Домен працює незалежно, але його дані критичні для всіх торгових рішень.

## Конфігурація

### Основні параметри
```yaml
trading_mode: "hybrid_live_data_testnet_exec"
binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
    api_secret: "${BINANCE_LIVE_API_SECRET}"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
account_balance:
  poll_interval: 30  # секунди
  retry_attempts: 3
  backoff_multiplier: 2.0
```

## Моніторинг

### Метрики
- `account_balance.updates_success` - Кількість успішних оновлень
- `account_balance.api_errors` - Кількість помилок API
- `account_balance.last_update_age` - Вік останніх даних (секунди)

### Логування
- INFO: Успішні оновлення балансу/позицій
- WARN: Проблеми з API, відсутність USDT
- ERROR: Критичні помилки з'єднання

## Запуск та використання

### Ініціалізація
```python
from apps.reference.domains.account_balance import AccountConnector

connector = AccountConnector(config)
await connector.start()
```

### Отримання поточного стану
```python
# Через FSM події або прямий виклик
balance_data = await connector.get_current_balance()
positions_data = await connector.get_current_positions()
```

## Тестування

### Інтеграційні тести
```bash
pytest tests/domains/account_balance/ -v
```

### Модульні тести
```bash
pytest tests/unit/domains/account_balance/ -v
```

## Безпека

- API ключі зберігаються в захищених змінних середовища
- HTTPS для всіх API викликів
- Аудит всіх операцій з рахунком
- Ніяких логів з реальними обліковими даними

## Розробка

### Додавання нових функцій
1. Оновіть `dictionaries.yaml` з новими структурами даних
2. Додайте методи в `AccountConnector`
3. Оновіть `schema.json` для нових подій
4. Напишіть тести
5. Оновіть документацію

### Контрибуція
- Дотримуйтесь конвенцій кодування проекту
- Додавайте тести для нових функцій
- Оновлюйте документацію при змінах

## Дивіться також

- [Детальна документація](documentation.md) - FSM події та взаємодії
- [Архітектурна схема](architecture.md) - Робочі процеси та діаграми
- [Словники даних](dictionaries.yaml) - Структури даних
- [Реалізовані функції](functions.md) - API та методи</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_balance\README.md