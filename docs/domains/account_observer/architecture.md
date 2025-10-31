# Архітектурна � хема домену Account Observer

## Загальна архітектура

Домен `account_observer` реалізує паттерн **Observer** для па� ивного моніторингу торгової активно� ті на Binance Futures. Архітектура побудована на принципах надійно� ті, дедуплікації та а� инхронної обробки.

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Binance API   │◄──►│  AccountObserver │◄──►│   FSM Events    │
│   (Read-Only)   │    │   (Core Logic)   │    │   (Internal)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Deduplication   │
                       │   & Caching      │
                       └──────────────────┘
```

## Компоненти архітектури

### 1. AccountObserver (Головний кла� )

**Відповідальні� ть:**
- Управління життєвим циклом домену
- Координація API викликів для моніторингу трейдів
- Дедуплікація оброблених трейдів
- Емі� ія подій про нові торгові операції

**Ключові методи:**
- `__init__()` - Ініціалізація з конфігурацією та Binance клієнтом
- `start()` - Запу� к фонового моніторингу
- `stop()` - Graceful shutdown
- `_poll_loop()` - О� новний цикл опитування
- `_poll_trades()` - Отримання трейдів з API
- `_process_trades()` - Обробка та фільтрація трейдів
- `_trade_to_payload()` - Конвертація в payload події

### 2. Binance Client (Зовнішня залежні� ть)

**Роль:** Клієнт для взаємодії з Binance Futures API (read-only)

**Викори� товувані методи:**
- `get_my_trades(symbol, limit)` - Отримання о� танніх трейдів для � имволу

### 3. Deduplication System (Внутрішня логіка)

**Механізм дедуплікації:**
- `processed_trade_ids: Set[int]` - множина оброблених ID трейдів
- Перевірка наявно� ті trade_id перед обробкою
- Додавання в множину пі� ля у� пішної обробки

## Робочі проце� и

### Проце�  ініціалізації

```mermaid
graph TD
    A[Створення AccountObserver] --> B[Валідація конфігурації]
    B --> C[Вибір режиму роботи]
    C --> D[Ініціалізація Binance Client]
    D --> E[Налаштування � имволів для моніторингу]
    E --> F[Ініціалізація � труктур дедуплікації]
```

### О� новний цикл моніторингу

```mermaid
graph TD
    A[Початок циклу] --> B{Ча�  опитування?}
    B -->|Так| C[Опитування в� іх � имволів]
    B -->|Ні| A
    C --> D[Обробка трейдів кожного � имволу]
    D --> E[Фільтрація нових трейдів]
    E --> F[Емі� ія EVT:TRADE_EXECUTED]
    F --> G[Очікування інтервалу опитування]
    G --> A
```

### Обробка окремого трейду

```mermaid
graph TD
    A[Отримання трейду] --> B{trade_id в processed_trade_ids?}
    B -->|Так| C[Пропу� к - дублікат]
    B -->|Ні| D[Додавання в processed_trade_ids]
    D --> E[Конвертація в payload]
    E --> F[Емі� ія EVT:TRADE_EXECUTED]
    F --> G[Логування у� пішної обробки]
```

## Структури даних

### Trade Data Structure (від Binance API)
```python
@dataclass
class BinanceTrade:
    symbol: str          # Торгова пара
    id: int             # Унікальний ID трейду
    orderId: int        # ID ордера
    price: str          # Ціна виконання
    qty: str            # Кількі� ть
    quoteQty: str       # Загальна варті� ть
    commission: str     # Комі� ія
    commissionAsset: str # Актив комі� ії
    time: int           # Ча�  виконання (ms)
    isBuyer: bool       # Напрямок (купівля/продаж)
    isMaker: bool       # Maker/Taker
    isBestMatch: bool   # Найкраще � півпадання
```

### Event Payload Structure
```python
@dataclass
class TradeExecutedPayload:
    symbol: str         # Торгова пара
    side: str          # 'buy' або 'sell'
    price: str         # Ціна як рядок для точно� ті
    quantity: str      # Кількі� ть (від'ємна для продажу)
    ts: int            # Timestamp в мілі� екундах
    fees: str          # Комі� ія як рядок
    venue: str         # 'binance'
```

## Конфігурація та параметри

### Режими роботи

#### Live Mode
```
Конфігурація: trading_mode = "live"
API: Binance Live (mainnet)
Ключі: BINANCE_LIVE_API_KEY/SECRET
Символи: Реальні торгові пари
```

#### Testnet Mode
```
Конфігурація: trading_mode = "testnet"
API: Binance Testnet
Ключі: BINANCE_TESTNET_API_KEY/SECRET
Символи: Те� тові торгові пари
```

#### Hybrid Mode
```
Конфігурація: trading_mode = "hybrid_*"
Автоматичний вибір залежно від контек� ту
```

### Параметри моніторингу

```yaml
account_observer:
  poll_interval: 5        # Інтервал опитування (� екунди)
  symbols:                # Спи� ок � имволів для моніторингу
    - BTCUSDT
    - ETHUSDT
    - BNBUSDT
  trade_limit: 50        # Кількі� ть трейдів для отримання за раз
```

## Продуктивні� ть та SLA

### Цільові метрики
- **Свіжі� ть даних:** < 35 � екунд (poll_interval + обробка)
- **Дедуплікація:** 100% (жодних дублікатів подій)
- **До� тупні� ть:** 99.5% (допу� тимі 3.65 години про� тою на мі� яць)
- **Ча�  відповіді API:** < 5 � екунд median

### Моніторинг продуктивно� ті
- Кількі� ть опитувань за хвилину
- Розмір відповідей API
- Ча�  обробки трейдів
- Викори� тання пам'яті для кешу ID

## Безпека та надійні� ть

### Захи� т даних
- **Read-only ключі:** Тільки для читання, без можливо� ті торгівлі
- **Мінімальні дозволи:** До� туп тільки до вла� них трейдів
- **HTTPS:** В� і API виклики через захищений протокол

### Стратегії відновлення
1. **API помилки:** Продовження з іншими � имволами
2. **Мережеві проблеми:** Повтор при на� тупному циклі
3. **Пар� инг помилки:** Логування та пропу� к проблемних трейдів
4. **Memory leaks:** Обмеження розміру кешу processed_trade_ids

## Те� тування архітектури

### Інтеграційні те� ти
- **API Integration:** Мокування Binance API для те� тування отримання трейдів
- **FSM Integration:** Валідація емі� ії подій та їх � поживання
- **Deduplication:** Те� тування логіки уникнення дублікатів

### Performance Testing
- **Load Testing:** Симуляція великої кілько� ті трейдів
- **Memory Testing:** Перевірка витіків пам'яті при довготривалій роботі
- **Concurrency Testing:** Перевірка потокобезпечно� ті

## Розширення та еволюція

### Можливі покращення
- **WebSocket Integration:** Перехід з polling на real-time updates
- **Multi-Exchange Support:** Підтримка інших бірж
- **Advanced Filtering:** Фільтрація трейдів за ча� ом, � имволом, розміром
- **Batch Processing:** Групова обробка трейдів для оптимізації

### Міграційні � тратегії
- **Gradual Rollout:** По� тійне розгортання з моніторингом дедуплікації
- **A/B Testing:** Порівняння � тарих та нових вер� ій
- **Feature Flags:** Включення нових функцій через конфігурацію

## Діаграми по� лідовно� ті

### Нормальний потік роботи
```mermaid
sequenceDiagram
    participant App
    participant AccountObserver
    participant BinanceAPI
    participant FSM

    App->>AccountObserver: start()
    loop Every poll_interval
        AccountObserver->>BinanceAPI: get_my_trades(symbol, limit)
        BinanceAPI-->>AccountObserver: Recent trades
        AccountObserver->>AccountObserver: Filter new trades
        AccountObserver->>FSM: emit EVT:TRADE_EXECUTED
    end
```

### Потік обробки дублікатів
```mermaid
sequenceDiagram
    participant AccountObserver
    participant Cache
    participant FSM

    AccountObserver->>Cache: Check trade_id
    Cache-->>AccountObserver: Not processed
    AccountObserver->>Cache: Add trade_id
    AccountObserver->>FSM: emit EVT:TRADE_EXECUTED
    Note over Cache: Trade marked as processed
```</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\architecture.md