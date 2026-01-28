# 📄 Паспорт конфігурації: aurora/trading.yaml (Section: binance_api, trading, market_data, execution)

## 🔍 Загальний опис блоку
Цей документ описує структуру та логіку використання `trading.yaml`. Блоки `market_data` та `execution` визначають "очі" (дані) та "руки" (виконання ордерів) системи.

## 🛠 Деталізація полів

| Поле | Тип | Pydantic | Статус | Роль у проекті |
|---|---|---|---|---|
| `binance_api` | `dict` | ✅ | 🟢 Active | Креденціали та URL для REST/WebSocket API |
| `trading.mode` | `str` | ✅ | 🟢 Active | Глобальний перемикач режиму (backtest, live, testnet) |
| `market_data` | `dict` | ✅ | 🟢 Active | Конфігурація джерел даних та агрегаторів |
| `execution` | `dict` | ✅ | 🟢 Active | Параметри виконання, ризик-гварди та Watchdog |
| `ops.panic_killswitch` | `bool` | ✅ | 🟢 Active | Аварійне припинення торгівлі та скасування ордерів |
| `tca_prefs` | `TCAPrefsConfig` | ✅ **TYPED** | 🟢 Active | Налаштування TCA з strict validation (Scorched-Earth 2026-01-27) |
| `risk_budgets` | `RiskBudgetsConfig` | ✅ **TYPED** | 🟢 Active | Ліміти ризику з strict validation (Scorched-Earth 2026-01-27) |
| `risk.soft_limits` | `dict` | ✅ | 🟢 Active | "М'які" ліміти на експозицію та сайзінг |
| `risk.regime_adaptation`|`dict`| ✅ | 🟢 Active | Динамічна зміна лімітів залежно від режиму |

---

### 1. `binance_api`
* **Суть:** Налаштування доступу до API Binance Futures (Live та Testnet). Використовує змінні оточення для безпеки.
* **Домен:** `Market Data`, `Account Balance`, `Execution`.
* **Режими роботи:** Live (для торгівлі та даних), Testnet (для Hybrid режиму).
* **Code Trace:**
    * [apps/reference/domains/market_data/market_data_connector.py](apps/reference/domains/market_data/market_data_connector.py#L40) — вибір креденціалів залежно від режиму.
    * [apps/reference/domains/account_balance/account_connector.py](apps/reference/domains/account_balance/account_connector.py#L50) — авторизація для отримання балансу.
* **Валідація:** Модель `BinanceApiConfig` у `config_models.py`.

### 2. `trading.mode`
* **Суть:** Визначає поведінку всієї системи (live/testnet/backtest). Backtest очікується як **SSOT-only**: без додаткових YAML-оверлеїв.
* **Домен:** `System Core`.
* **Code Trace:**
    * [apps/reference/config_loader.py](apps/reference/config_loader.py) — завантаження та валідація SSOT конфігів.
    * [apps/reference/main.py](apps/reference/main.py#L80) — ініціалізація компонентів відповідно до режиму.

### 3. `trading.tca_prefs`
* **Суть:** Параметри контролю якості виконання ордерів. `max_slippage_bps` — критичний параметр для `TradeIntent`.
* **Домен:** `Decision Making`, `Execution Position`.
* **Режими роботи:** Live, Hybrid та Backtest.
* **Code Trace:**
    * [apps/reference/domains/decision_making/decision_making.py](apps/reference/domains/decision_making/decision_making.py#L420) — зчитування `max_slippage_bps` для формування інтенту.
    * [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L150) — перевірка ліміту проковзування перед виставленням ордера.
* **Математичний вплив:** `Limit Price = Entry Price * (1 ± max_slippage_bps/10000)`.

### 4. `trading.risk.soft_limits`
* **Суть:** Захисний механізм, що обрізає (clip) розмір позиції, якщо вона перевищує задані ліміти в USDT або плече.
* **Домен:** `Execution Position (Exposure Guard)`.
* **Режими роботи:** визначається SSOT конфігом; у backtest має поводитися так само, як і в live (якщо не закладено інакше в коді/контракті).
* **Code Trace:**
    * [apps/reference/domains/execution_position/soft_clip.py](apps/reference/domains/execution_position/soft_clip.py#L45) — логіка обрізки сайзу.
    * [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L210) — перевірка `side_exposure_usdt`.
* **Математичний вплив:** `final_qty = min(intent_qty, soft_limit_qty)`.

### 5. `trading.risk.regime_adaptation`
* **Суть:** Адаптує ліміти ризику до стану ринку. Наприклад, у тренді (`trend_up_delta`) дозволяє більшу експозицію.
* **Домен:** `Risk Management`.
* **Code Trace:**
    * [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L235) — застосування дельта-коефіцієнтів до софт-лімітів.
* **Математичний вплив:** `Adjusted Limit = Base Limit * (1 + delta)`.

---

### 5.5 **🟢 TYPED CONFIGS (Scorched-Earth 2026-01-27): `tca_prefs` & `risk_budgets`**

**Статус:** ✅ **FIXED** — Обидва конфіги тепер типізовані через Pydantic моделі з `extra='forbid'` (fail-fast на помилки).

**Що було:**
```yaml
tca_prefs: Dict[str, Any]      # Silent defaults на невідомі ключі
risk_budgets: Dict[str, Any]   # Тип-помилки проходили без помилок
```

**Що стало:**
```python
class TCAPrefsConfig(BaseModel):
    """Typed TCA Preferences (was Dict[str, Any])"""
    model_config = ConfigDict(extra='forbid')
    
    maker_fee_pct: float = Field(description='Maker fee percentage')
    taker_fee_pct: float = Field(description='Taker fee percentage')
    max_price_distance_bps: int = Field(description='Max price distance in basis points')

class RiskBudgetsConfig(BaseModel):
    """Typed Risk Budgets (was Dict[str, Any])"""
    model_config = ConfigDict(extra='forbid')
    
    daily_loss_limit_pct: float = Field(description='Daily loss limit %')
    hourly_loss_limit_pct: float = Field(description='Hourly loss limit %')
    max_exposure_pct: float = Field(description='Max total exposure %')
```

**Де знаходиться код:** [apps/reference/config_models.py](apps/reference/config_models.py#L2607-L2665)
- Line 2607-2608: `TCAPrefsConfig` definition
- Line 2626-2627: `RiskBudgetsConfig` definition  
- Line 2664-2665: Both used in `TradingConfig` (не як Dict!)

**Вплив:**
- ✅ **Fail-closed валідація:** Будь-яка помилка у YAML → `ValidationError` при завантаженні (no silent defaults)
- ✅ **IDE код-автозаповнення:** Тепер IDE знає типи (не `Dict[str, Any]`)
- ✅ **Runtime гарантії:** Тип дозолений — зменшує risk фіненціальних помилок

**Тести:**
- ✅ [tests/config/test_tca_prefs_strict_validation.py](tests/config/test_tca_prefs_strict_validation.py) — перевірка що `extra='forbid'` не дозволяє невідомі ключі
- ✅ [tests/config/test_risk_budgets_strict_validation.py](tests/config/test_risk_budgets_strict_validation.py) — перевірка що types дозволяються

---

### 6. `market_data`
* **Суть:** Налаштування отримання ринкових даних. Включає `macro_sync` (синхронізація "анкорів" BTC/ETH) та `bar_aggregator` (генерація OHLC барів для стратегій).
* **Домен:** `Market Data`, `Feature Engineering`.
* **Режими роботи:** Live, Hybrid (для читання цін), Backtest.
* **Code Trace:**
    * [apps/reference/domains/market_data/worker.py](apps/reference/domains/market_data/worker.py#L45) — `poll_interval_sec` та логіка мультипроцесингу.
    * [apps/reference/domains/market_data/market_data_connector.py](apps/reference/domains/market_data/market_data_connector.py#L35) — конфігурація `macro_sync` (anchors).
    * [apps/reference/domains/market_data/bar_aggregator.py](apps/reference/domains/market_data/bar_aggregator.py#L25) — ініціалізація таймфреймів для свічок.
* **Валідація:** Модель `MarketDataConfig` у `config_models.py`.

### 7. `execution.exposure`
* **Суть:** Глобальні ліміти ризику на портфель. Перевіряє `max_equity_utilization_pct` (плече портфеля) та частку окремих позицій.
* **Домен:** `Execution Position (Exposure Guard)`.
* **Code Trace:**
    * [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L90) — завантаження лімітів у `ExposureGuard`.
    * [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L656) — розрахунок доступного ліміту маржі: `equity_free_usdt * max_equity_utilization_pct`.
* **Математичний вплив:** Блокує `TradeIntent`, якщо `current_utilization + new_intent > max_utilization`.

### 8. `execution.watchdog` / `anti_race_close_ms`
* **Суть:** Технічні запобіжники. Watchdog стежить за "завислими" ордерами (`ack_ttl_ms`), а `anti_race` запобігає повторним входам у позицію одразу після закриття.
* **Домен:** `Execution Position (FSM)`.
* **Code Trace:**
    * [apps/reference/domains/execution_position/watchdog.py](apps/reference/domains/execution_position/watchdog.py#L30) — контроль тайм-аутів виконання.
    * [apps/reference/domains/execution_position/fsm_manage.py](apps/reference/domains/execution_position/fsm_manage.py#L40) — перевірка `anti_race_close_ms` перед відкриттям нового FSM.
    * [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L213) — застосування `cooldown_after_close_ms`.

### 9. `ops.panic_killswitch`
* **Суть:** "Червона кнопка". При активації система негайно переходить у глобальний Stop-режим та скасовує всі наміри на вхід.
* **Домен:** `System Wide / Execution FSM`.
* **Code Trace:**
    * [apps/reference/domains/execution_position/fsm.py](apps/reference/domains/execution_position/fsm.py#L978) — обробник активації кілл-світча.
* **Інваріант:** `If panic_killswitch == True Then All New Intents = Rejected, Pending Entries = Cancelled`.

### 10. `domain_configuration` / `risk_management.data_sources`
* **Суть:** Налаштування гібридного режиму (Hybrid Mode). Дозволяє читати дані з `live`, але виконувати ордери на `testnet` або використовувати `testnet` баланс для ризик-розрахунків при живих цінах.
* **Домен:** `Cross-Domain Orchestration`.
* **Code Trace:**
    * [apps/reference/utils/trading_modes.py](apps/reference/utils/trading_modes.py) — логіка маппінгу режимів на домени.
    * [apps/reference/domains/execution_position/exposure_guard.py](apps/reference/domains/execution_position/exposure_guard.py#L110) — вибір джерела даних для `portfolio_state`.
* **Інваріант:** Дозволяє безпечне тестування стратегій на реальних даних без ризику реальним капіталом.

---
**Вердикт Аудитора:** Блок `market_data.bar_aggregator` тепер включає 15m бари (`900s`), що критично для нових режимів волатильності. У `execution.exposure` видалені "зомбі-поля" (`max_side_utilization_pct`), що покращує чистоту конфігу. Рекомендується встановити `fsm_periodic_cleanup_enabled: true` для тривалих сесій.

---
**Вердикт Аудитора:** Блок `risk.score_weights` та `feature_flags` позначені як **ZOMBIE**. Вони присутні в конфігу, але логіка їх використання або застаріла (перенесена в `domains.yaml`), або відсутня в поточному релізі. Рекомендується видалити їх для усунення плутанини (Data Cleanliness).
