# Account Balance Domain (Домен Балан� у Рахунку)

## Огляд

Домен `account_balance` є фундаментальним компонентом � и� теми Aurora, що забезпечує моніторинг фінан� ового � тану торгового рахунку на Binance Futures. Він ви� тупає як мі� т між біржовими API та внутрішньою логікою � и� теми, перетворюючи � ирі дані балан� у в � труктуровані FSM події.

## Архітектурна роль

### Відповідальні� ть
- **Моніторинг балан� у:** Отримання та обробка даних про балан�  активів з Binance Futures API
- **Від� теження позицій:** Моніторинг відкритих ф'ючер� них позицій в режимі реального ча� у
- **Стандартизація даних:** Перетворення � ирих API даних в � тандартизовані події FSM � и� теми
- **Надійні� ть:** Забезпечення актуально� ті фінан� ового � тану для прийняття торгових рішень

### Критичні� ть для � и� теми
Домен є критичним компонентом, о� кільки його дані викори� товують� я:
- **Risk Management** для оцінки ризиків портфеля
- **Decision Making** для розрахунку розмірів позицій
- **Position Tracking** для � инхронізації � тану портфеля
- **Execution Management** для валідації до� тупного капіталу

## Структура домену

```
account_balance/
├── README.md              # Цей файл - огляд домену
├── documentation.md       # Детальна документація FSM подій та взаємодій
├── architecture.md        # Архітектурна � хема та робочі проце� и
├── dictionaries.yaml      # Словники даних та конфігурації
├── functions.md           # Реалізовані функції та методи
├── examples/              # Приклади коду та конфігурації
│   ├── config.yaml        # Приклад конфігурації
│   ├── usage.py           # Приклад викори� тання
│   └── tests/             # Те� тові приклади
└── schema.json           # JSON Schema для валідації подій
```

## О� новні компоненти

### AccountConnector
Головний кла�  домену, що реалізує підключення до Binance API та моніторинг рахунку.

**Ключові можливо� ті:**
- Автоматичний вибір API залежно від режиму роботи (live/testnet/hybrid)
- Фоновий моніторинг з конфігурованим інтервалом
- Graceful degradation при проблемах з API
- Структурована емі� ія FSM подій

## FSM події

### Генеровані події
- `EVT:BALANCE_UPDATE_RECEIVED` - Оновлення балан� у активів
- `EVT:ACCOUNT_UPDATE_RECEIVED` - Оновлення � тану рахунку та позицій

### Споживані події
Домен працює автономно і не � поживає зовнішні події.

## Взаємодії з доменами

### Синхронні зв'язки
- **Position Tracking** ← `EVT:ACCOUNT_UPDATE_RECEIVED`
- **Risk Management** ← `EVT:BALANCE_UPDATE_RECEIVED`, `EVT:ACCOUNT_UPDATE_RECEIVED`
- **Decision Making** ← `EVT:BALANCE_UPDATE_RECEIVED`

### А� инхронні залежно� ті
Домен працює незалежно, але його дані критичні для в� іх торгових рішень.

## Конфігурація

### О� новні параметри
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
  poll_interval: 30  # � екунди
  retry_attempts: 3
  backoff_multiplier: 2.0
```

## Моніторинг

### Метрики
- `account_balance.updates_success` - Кількі� ть у� пішних оновлень
- `account_balance.api_errors` - Кількі� ть помилок API
- `account_balance.last_update_age` - Вік о� танніх даних (� екунди)

### Логування
- INFO: У� пішні оновлення балан� у/позицій
- WARN: Проблеми з API, від� утні� ть USDT
- ERROR: Критичні помилки з'єднання

## Запу� к та викори� тання

### Ініціалізація
```python
from apps.reference.domains.account_balance import AccountConnector

connector = AccountConnector(config)
await connector.start()
```

### Отримання поточного � тану
```python
# Через FSM події або прямий виклик
balance_data = await connector.get_current_balance()
positions_data = await connector.get_current_positions()
```

## Те� тування

### Інтеграційні те� ти
```bash
pytest tests/domains/account_balance/ -v
```

### Модульні те� ти
```bash
pytest tests/unit/domains/account_balance/ -v
```

## Безпека

- API ключі зберігають� я в захищених змінних � ередовища
- HTTPS для в� іх API викликів
- Аудит в� іх операцій з рахунком
- Ніяких логів з реальними обліковими даними

## Розробка

### Додавання нових функцій
1. Оновіть `dictionaries.yaml` з новими � труктурами даних
2. Додайте методи в `AccountConnector`
3. Оновіть `schema.json` для нових подій
4. Напишіть те� ти
5. Оновіть документацію

### Контрибуція
- Дотримуйте� ь конвенцій кодування проекту
- Додавайте те� ти для нових функцій
- Оновлюйте документацію при змінах

## Дивіть� я також

- [Детальна документація](documentation.md) - FSM події та взаємодії
- [Архітектурна � хема](architecture.md) - Робочі проце� и та діаграми
- [Словники даних](dictionaries.yaml) - Структури даних
- [Реалізовані функції](functions.md) - API та методи</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_balance\README.md