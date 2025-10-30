# Aurora Core FSM

Federated State Machine system for algorithmic trading on Binance Futures.

## Quick Start

1. **Setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Binance API credentials
   ```

2. **Choose trading environment:**
   - **Testnet** (recommended): `USE_TESTNET=true` in `.env`
   - **Mainnet** (real money): `USE_TESTNET=false` in `.env`

3. **Run the system:**
   ```bash
   python apps/reference/main.py
   ```

---

## 🚀 vFoundation: Архітектура та Принципи для LLM-Агентів

Ця система побудована на внутрішньому фреймворку **vFoundation**, який реалізує архітектуру **Федеративних Скінченних Автоматів (Federated FSM)**.

- **Федерація:** Система розділена на незалежні домени (FSM), кожен з яких відповідає за свою частину логіки.
- **Гарячий шлях (Hot Path):** Домен `TRADE FSM` (`execution_position`) відповідає за швидке виконання угод. Його головний пріоритет — низька затримка (SLO: p95 ≤ 50ms).
- **Холодний шлях (Cold Path):** Домени `LEARN FSMs` (`analyzer`, `risk_strategy`) виконують важкі обчислення, аналіз даних та навчання, не блокуючи основний торговий цикл.
- **Центральна Координація:**
    - `OrchestratorFSM`: Керує життєвим циклом кожного запиту (RID) та застосовує "охоронців" (Guards) — **Idempotency, TTL, Circuit Breaker**.
    - `MetaFSM`: Відповідає за реєстр компонентів та валідацію даних за допомогою схем.

## 🔄 Повний Цикл Прийняття Рішень

Це покроковий шлях, який проходить кожен торговий сигнал в системі.

1.  **Збір Даних:** `MarketDataConnector` отримує ринкові дані (тіки) з біржі -> `EVT:MARKET_TICK_RECEIVED`.
2.  **Розрахунок Фіч:** `FeatureEngineering` обробляє тіки та розраховує показники (OBI, TFI) -> `EVT:FEATURES_CALCULATED`.
3.  **Оцінка Ризику:** `RiskManagement` аналізує ринкову ситуацію -> `EVT:RISK_ASSESSMENT_COMPLETED`.
4.  **Агрегація та Рішення:** `DecisionMaking` збирає фічі, ризик-оцінку та стан портфеля (`EVT:PORTFOLIO_STATE_UPDATED`), генерує сигнал та розраховує розмір позиції.
5.  **Формування Наміру:** Якщо сигнал сильний, `DecisionMaking` створює `EVT:TRADE_INTENT_PROPOSED` з детальним `why_chain`.
6.  **Команда та Виконання:** `Orchestrator` перетворює намір на `CMD:OPEN` і відправляє його в `ExecPosFSM`.
7.  **Pre-Trade Перевірки:** `OpenFlowFSM` (частина `ExecPosFSM`) перевіряє команду на відповідність лімітам (мін. розмір, кулдаун, ліміт активних ордерів).
8.  **Взаємодія з Біржею:** `BinanceAdapter` відправляє ордер на біржу та встановлює TP/SL.
9.  **Зворотний Зв'язок:** Біржа повідомляє про виконання ордера -> `EVT:TRADE_EXECUTED`.
10. **Оновлення Стану:** `PositionTracking` отримує подію про виконання, оновлює PnL та `equity` портфеля -> `EVT:PORTFOLIO_STATE_UPDATED`. **Цикл замикається.**

## 📚 Словники та Контракти (Contracts-First)

Система дотримується принципу **"Спочатку Контракт"**. Це означає, що структура даних є первинною.

-   **Джерело Правди:** Людсько-читні **Словники** у форматі `YAML`. Вони описують усі сутності та події в системі.
    -   **Розташування:** `vfoundation/dictionaries/`
-   **Процес:** Спеціальний скрипт (`vfound schema`) компілює ці `YAML`-файли в машиночитні **JSON Schemas** (`.json`).
    -   **Розташування Схем:** `vfoundation/schemas/`
-   **Призначення:** Ці схеми використовуються по всій системі (особливо в `MetaFSM`) для валідації даних "на льоту", що гарантує цілісність та надійність потоків даних.

## 🗺️ Навігація для LLM-Агентів (Ключові Шляхи)

-   **Основна логіка доменів:** `apps/reference/domains/`
    -   `decision_making/`: Логіка прийняття рішень.
    -   `execution_position/`: Логіка виконання ордерів (FSMs: `fsm_open.py`, `fsm_manage.py`, `fsm_close.py`).
    -   `position_tracking/`: Логіка відстеження стану портфеля.
-   **Ядро фреймворку vFoundation:** `vfoundation/vfoundation/`
    -   `core/`: Базові класи FSM, протокол повідомлень.
    -   `dr/`: Логіка відмовостійкості (WAL, Replay).
    -   `adapters/`: Адаптери до зовнішніх сервісів (Binance).
-   **Контракти (Джерело Правди):** `vfoundation/dictionaries/`
-   **Згенеровані Схеми:** `vfoundation/schemas/`
-   **Конфігурації:** `config/aurora/`
-   **Тести:** `tests/`

---

## Environment Configuration

### Testnet (Safe Development)
```bash
USE_TESTNET=true
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_API_SECRET=your_testnet_secret
```

### Mainnet (Real Trading)
```bash
USE_TESTNET=false
BINANCE_MAINNET_API_KEY=your_mainnet_key
BINANCE_MAINNET_API_SECRET=your_mainnet_secret
```

## Features

- **Real Order Book Data**: Uses Binance depth streams for accurate market data
- **Testnet/Mainnet Support**: Automatic switching based on `USE_TESTNET`
- **Centralized Configuration**: YAML + environment variables
- **Event-Driven Architecture**: FSM-based component communication

## Architecture

- `market_data`: Real-time Binance order book feeds
- `feature_engineering`: Technical indicators from market data
- `risk_management`: Position risk assessment
- `position_tracking`: Portfolio state management
- `decision_making`: Trade signal generation

## Configuration Files

- `config/aurora/trading.yaml`: Trading parameters
- `config/aurora/system.yaml`: System settings
- `.env`: Environment-specific secrets