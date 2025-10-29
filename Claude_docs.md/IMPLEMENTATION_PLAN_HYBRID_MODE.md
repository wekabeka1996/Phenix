# 📋 ВСЕОХОПЛЮЮЧИЙ ПЛАН РЕАЛІЗАЦІЇ ГІБРИДНОЇ КОНФІГУРАЦІЇ РЕЖИМІВ

**RID**: AURORA_HYBRID_MODE_IMPLEMENTATION_PLAN_V1  
**Дата**: 27 жовтня 2025  
**Статус**: 📋 План (без реалізації)  
**Мета**: Дозволити доменам читати режим з конфігу та працювати незалежно:
- ✅ `market_data` читає з **LIVE** Binance
- ✅ `execution_position` пише на **TESTNET** Binance
- ✅ Інші домени узгоджено адаптуються

---

## 📐 АРХІТЕКТУРНИЙ ОГЛЯД

### Поточний Стан

```
┌─────────────────────────────────────┐
│  config/aurora/                     │
│  ├─ system.yaml (global)            │
│  └─ trading.yaml (global)           │
│     trading_mode: "hybrid_..."      │
└────────────────────┬────────────────┘
                     │ (всі домени читають ОДИН режим)
                     ▼
        ┌────────────────────────┐
        │   FSM Core             │
        └────────────┬───────────┘
                     │
        ┌────────────┴──────────────────┐
        │                               │
     ┌──▼──┐                        ┌──▼──┐
     │ MD  │ (читає режим 1)        │ EP  │ (читає режим 1)
     └─────┘                        └─────┘
     Проблема: Обидва одній режим!
```

### Бажаний Стан

```
┌──────────────────────────────────────────────┐
│  config/aurora/                              │
│  ├─ system.yaml (global)                     │
│  ├─ trading.yaml (global)                    │
│  ├─ domain_modes.yaml (НОВИЙ)                │
│  │  ├─ market_data:                          │
│  │  │   mode: "live"                         │
│  │  │   data_source: "live"                  │
│  │  └─ execution_position:                   │
│  │      mode: "testnet"                      │
│  │      execution_target: "testnet"          │
│  └─ schemas/                                 │
│     └─ domain_modes_schema.json (НОВИЙ)      │
└────────────────────┬─────────────────────────┘
                     │ (кожен домен читає свій режим)
                     ▼
        ┌────────────────────────┐
        │   FSM Core             │
        └────────────┬───────────┘
                     │
        ┌────────────┴──────────────────┐
        │                               │
     ┌──▼──────┐                    ┌──▼───────┐
     │ MD      │ (читає режим A)    │ EP       │ (читає режим B)
     │ mode:live                    │ mode:test
     └─────────┘                    └──────────┘
     ✅ Незалежна конфігурація!
```

---

## 🔧 ТЕХНІЧНІ КОМПОНЕНТИ

### 1. СТРУКТУРА КОНФІГУРАЦІЇ (Додавання)

#### 1.1 Новий файл: `config/aurora/domain_modes.yaml`

```yaml
# =============================================================================
# DOMAIN-LEVEL MODE CONFIGURATION
# =============================================================================
# Цей файл дозволяє налаштовувати режим для кожного домену окремо.
# Це основа для гібридної conifg (live data + testnet execution).

# NOTE: Значення можуть перевизначатися через env vars: ${DOMAIN_MODE_MARKET_DATA}

domain_modes:
  
  # =========== DATA ACQUISITION LAYER ===========
  
  market_data:
    enabled: true
    mode: "${DOMAIN_MODE_MARKET_DATA:-live}"  # Default: live
    description: "Market data source (live/testnet)"
    # Валідні значення: "live", "testnet", "shadow"
    # "live" → читає з live.binance_api
    # "testnet" → читає з testnet.binance_api
    # "shadow" → використовує mock data (для тестування)
    
    # Спадковість: наслідує binance_api конфіг із system.yaml
    inherit_binance_api_from: "live"  # або "testnet"
    
    # Data source specific options
    data_options:
      use_real_time: true    # Для live - use WebSocket, для testnet - REST polling
      fallback_to_rest: true # Якщо WebSocket впаде, перейти на REST
  
  # =========== FEATURE & ANALYSIS LAYER ===========
  
  feature_engineering:
    enabled: true
    mode: "inherit"  # Наслідує від market_data
    description: "Depends on market_data mode"
    # "inherit" → використовує той же режим що й market_data
    # Причина: feature_engineering аналізує дані від market_data
  
  risk_management:
    enabled: true
    mode: "inherit"  # Незалежна аналітика, режим не важить
    description: "Risk analysis (regime-independent)"
  
  # =========== EXECUTION LAYER ===========
  
  execution_position:
    enabled: true
    mode: "${DOMAIN_MODE_EXECUTION:-testnet}"  # Default: testnet
    description: "Trade execution target (testnet/live/shadow)"
    # Валідні значення: "testnet", "live", "shadow"
    # "testnet" → відправляє ордери на testnet.binance
    # "live" → відправляє ордери на live binance (РЕАЛЬНІ ГРОШІ!)
    # "shadow" → симулює виконання без торгівлі
    
    # Спадковість: наслідує binance_api конфіг із system.yaml
    inherit_binance_api_from: "testnet"  # або "live"
    
    # Execution specific options
    execution_options:
      dry_run: false              # true = тільки симуляція
      rate_limit: 10              # ордерів на хвилину
      max_position_size_usd: 5000 # Максимум на позицію
  
  # =========== PORTFOLIO TRACKING ===========
  
  account_balance:
    enabled: true
    mode: "inherit"  # Наслідує режим execution_position
    description: "Portfolio tracking (follows execution)"
  
  position_tracking:
    enabled: true
    mode: "inherit"  # Режим-незалежний
    description: "Position analytics"

# =============================================================================
# VALIDATION & CONSTRAINTS
# =============================================================================

validation:
  rules:
    - name: "live_data_without_live_execution"
      condition: 'market_data.mode == "live" && execution_position.mode == "shadow"'
      warning: "⚠️  Reading live data but not executing - use for backtesting"
    
    - name: "shadow_data_with_live_execution"
      condition: 'market_data.mode == "shadow" && execution_position.mode == "live"'
      severity: "ERROR"
      message: "❌ Cannot execute live trading with shadow data - data will be unrealistic"
    
    - name: "inconsistent_modes"
      condition: 'account_balance.binance_api != execution_position.binance_api'
      warning: "⚠️  Account tracking uses different API than execution"

# =============================================================================
# ALLOWED COMBINATIONS (Recommendation)
# =============================================================================

allowed_combinations:
  - name: "PRODUCTION_LIVE"
    market_data: "live"
    execution_position: "live"
    description: "Live data + live execution (REAL MONEY!)"
    when: "Production trading"
  
  - name: "PRODUCTION_HYBRID"
    market_data: "live"
    execution_position: "testnet"
    description: "Live data + testnet execution (RECOMMENDED FOR TESTING)"
    when: "Development & validation before going live"
  
  - name: "DEV_TESTNET"
    market_data: "testnet"
    execution_position: "testnet"
    description: "Testnet data + testnet execution"
    when: "Local development"
  
  - name: "BACKTEST"
    market_data: "shadow"
    execution_position: "shadow"
    description: "Historical data + simulation"
    when: "Strategy backtesting"
```

#### 1.2 Оновлення: `config/aurora/system.yaml`

**Додати раніше `trading_mode` лінії**:
```yaml
# NEW: Include domain-specific mode configuration
domain_configuration:
  config_file: "domain_modes.yaml"  # Path to domain modes config
  auto_validate: true               # Validate on startup
  fail_on_invalid: true             # Stop if invalid combination
```

#### 1.3 Оновлення: `config_loader.py`

**Добавити методи**:
```python
class AuroraConfig:
    # ДОДАНО:
    
    def get_domain_mode(self, domain: str) -> str:
        """Get the configured mode for a specific domain"""
        # Читати з domain_modes.yaml
        # Розв'язати ${ENV_VAR} посилання
        # Обробити "inherit" значення
    
    def get_domain_binance_api_config(self, domain: str) -> dict:
        """Get Binance API config for a domain's specific mode"""
        # Отримати inherit_binance_api_from
        # Повернути відповідний live/testnet конфіг
    
    def validate_domain_modes(self) -> list[str]:
        """Validate domain mode configuration"""
        # Перевірити валідні комбінації
        # Повернути список warnings/errors
```

### 2. ОНОВЛЕННЯ ДОМЕНІВ (Мінімальні)

#### 2.1 `MarketDataConnector`

**Поточний код** (рядок ~50):
```python
mode = config.get("trading_mode", "testnet")
```

**Оновити на**:
```python
# ДОДАНО: Domain-specific mode support
from apps.reference.config_loader import get_config
aurora_config = get_config()
mode = aurora_config.get_domain_mode("market_data")
api_config = aurora_config.get_domain_binance_api_config("market_data")
```

#### 2.2 `BinanceExecutionAdapter`

**Поточний код** (рядок ~10-20):
```python
self.base_url = "https://testnet.binancefuture.com" if self.config.get('trading_env') == 'test' else "https://fapi.binance.com"
```

**Оновити на**:
```python
# ДОДАНО: Domain-specific mode support
from apps.reference.config_loader import get_config
aurora_config = get_config()
mode = aurora_config.get_domain_mode("execution_position")
api_config = aurora_config.get_domain_binance_api_config("execution_position")
self.base_url = api_config.get("rest_url")
```

#### 2.3 Інші домени

- `RiskManagement` - **НЕ змінювати** (режим-незалежна)
- `DecisionMaking` - **НЕ змінювати** (режим-незалежна)
- `FeatureEngineering` - **НЕ змінювати** (наслідує від market_data)
- `PositionTracking` - **НЕ змінювати** (режим-незалежна)
- `AccountBalance` - **ДОДАТИ** читання режиму з конфіга (наслідує execution)
- `AccountObserver` - **НЕ змінювати** (читає з execution режиму)

### 3. FSM КОНТРАКТ (Розширення)

#### 3.1 Оновити `vfoundation/core/protocol.py`

**Додати поле до Message**:
```python
class Message(BaseModel):
    # ... існуючі поля ...
    
    # ДОДАНО:
    mode: Optional[str] = None  # Domain mode: live/testnet/shadow
    mode_contract: Optional[str] = None  # e.g. "data_src=live:execution=testnet"
```

**Валідація**:
```python
@field_validator("mode")
@classmethod
def _mode_valid(cls, v: Optional[str]) -> Optional[str]:
    if v and v not in ["live", "testnet", "shadow", "inherit"]:
        raise ValueError(f"Invalid mode: {v}")
    return v
```

#### 3.2 Оновити `FSMCore`

**Додати методи**:
```python
class FSMCore:
    # ДОДАНО:
    
    def get_domain_mode(self, domain: str) -> str:
        """Get current mode for domain (for FSM context)"""
        # Делегувати до config
    
    def validate_mode_contract(self, msg: Message) -> bool:
        """Validate that message respects domain modes"""
        # Перевірити що mode в Message узгоджений з domain config
```

---

## 🔄 ПОРЯДОК РЕАЛІЗАЦІЇ (З ЗАЛЕЖНОСТЯМИ)

### **ФАЗА 1: КОНФІГУРАЦІЯ (Foundational)**

| # | Задача | Залежності | Файли | Статус |
|---|--------|-----------|-------|--------|
| 1.1 | Створити `domain_modes.yaml` | - | `config/aurora/domain_modes.yaml` | 📋 |
| 1.2 | Оновити `system.yaml` з domain_configuration | 1.1 | `config/aurora/system.yaml` | 📋 |
| 1.3 | Схема валідації `domain_modes_schema.json` | 1.1 | `config/aurora/schemas/domain_modes_schema.json` | 📋 |
| **КОНТРОЛЬНА ТОЧКА 1** | Конфіг структура готова | 1.1-1.3 | - | ✋ |

### **ФАЗА 2: CONFIG LOADER (Config Management)**

| # | Задача | Залежності | Файли | Статус |
|---|--------|-----------|-------|--------|
| 2.1 | Додати методи в ConfigLoader | 1.2 | `apps/reference/config_loader.py` | 📋 |
| 2.1.1 | - `get_domain_mode()` | 2.1 | `` | 📋 |
| 2.1.2 | - `get_domain_binance_api_config()` | 2.1 | `` | 📋 |
| 2.1.3 | - `validate_domain_modes()` | 2.1 | `` | 📋 |
| 2.2 | Тести ConfigLoader | 2.1 | `tests/test_domain_mode_config.py` | 📋 |
| **КОНТРОЛЬНА ТОЧКА 2** | ConfigLoader готовий | 2.1-2.2 | - | ✋ |

### **ФАЗА 3: FSM КОНТРАКТ (Foundation for Domain Integration)**

| # | Задача | Залежності | Файли | Статус |
|---|--------|-----------|-------|--------|
| 3.1 | Додати `mode` поле до Message | - | `vfoundation/core/protocol.py` | 📋 |
| 3.2 | Додати валідацію `mode` | 3.1 | `` | 📋 |
| 3.3 | Оновити FSMCore з методами | 2.1 | `vfoundation/core/fsm.py` | 📋 |
| 3.4 | Тести Message контракту | 3.1-3.3 | `tests/test_fsm_mode_contract.py` | 📋 |
| **КОНТРОЛЬНА ТОЧКА 3** | FSM готовий | 3.1-3.4 | - | ✋ |

### **ФАЗА 4: ДОМЕНИ (Domain Integration)**

| # | Задача | Залежності | Файли | Статус |
|---|--------|-----------|-------|--------|
| 4.1 | Оновити MarketDataConnector | 2.1, 3.3 | `apps/reference/domains/market_data/` | 📋 |
| 4.1.1 | - Читати режим з конфіга | 4.1 | `` | 📋 |
| 4.1.2 | - Тести MarketDataConnector | 4.1 | `tests/domains/test_market_data_mode.py` | 📋 |
| 4.2 | Оновити BinanceExecutionAdapter | 2.1, 3.3 | `apps/reference/domains/execution_position/` | 📋 |
| 4.2.1 | - Читати режим з конфіга | 4.2 | `` | 📋 |
| 4.2.2 | - Тести BinanceExecutionAdapter | 4.2 | `tests/domains/test_execution_mode.py` | 📋 |
| 4.3 | Оновити ExecPosFSM | 2.1, 3.3 | `apps/reference/domains/execution_position/fsm.py` | 📋 |
| 4.3.1 | - Синхронізувати API | 4.3 | `` | 📋 |
| 4.3.2 | - Передавати mode в Message | 4.3 | `` | 📋 |
| 4.4 | Оновити AccountConnector | 2.1 | `apps/reference/domains/account_balance/` | 📋 |
| 4.4.1 | - Наслідувати режим від execution | 4.4 | `` | 📋 |
| 4.5 | Синхронізувати інші домени (readonly) | 2.1 | Всі інші домени | 📋 |
| **КОНТРОЛЬНА ТОЧКА 4** | Домени готові | 4.1-4.5 | - | ✋ |

### **ФАЗА 5: ТЕСТУВАННЯ (Validation)**

| # | Задача | Залежності | Файли | Статус |
|---|--------|-----------|-------|--------|
| 5.1 | Інтеграційний тест: live data + testnet exec | 4.1-4.4 | `tests/integration/test_hybrid_mode.py` | 📋 |
| 5.2 | Інтеграційний тест: testnet data + testnet exec | 4.1-4.4 | `tests/integration/test_testnet_mode.py` | 📋 |
| 5.3 | Валідація mode constraints | 2.2 | `tests/test_domain_mode_validation.py` | 📋 |
| 5.4 | End-to-end: запуск main.py з hybrid режимом | 4.1-4.4 | (manual test) | 📋 |
| 5.5 | Покриття 77 тестів що були broken | 4.1-4.5 | `tests/**/*.py` | 📋 |
| **КОНТРОЛЬНА ТОЧКА 5** | Тестування пройдене | 5.1-5.5 | - | ✋ |

### **ФАЗА 6: ДОКУМЕНТАЦІЯ & ВАЛІДАЦІЯ**

| # | Задача | Залежності | Файли | Статус |
|---|--------|-----------|-------|--------|
| 6.1 | Оновити README з domain modes | 4.1-4.5 | `docs/DOMAIN_MODES_GUIDE.md` | 📋 |
| 6.2 | Playbook: "Як налаштувати hybrid режим" | 6.1 | `docs/PLAYBOOK_HYBRID_SETUP.md` | 📋 |
| 6.3 | Оновити JOURNAL з RID записом | - | `JOURNAL.md` | 📋 |
| 6.4 | Фінальна валідація всіх 644 тестів | 5.5 | (pytest run) | 📋 |
| **ГОТОВО** | Система в production | 6.1-6.4 | - | ✋ |

---

## 📊 МАТРИЦЯ ФАЙЛІВ (Що змінювати)

### Нові файли (CREATE)

```
✅ config/aurora/domain_modes.yaml
✅ config/aurora/schemas/domain_modes_schema.json
✅ tests/test_domain_mode_config.py
✅ tests/test_fsm_mode_contract.py
✅ tests/domains/test_market_data_mode.py
✅ tests/domains/test_execution_mode.py
✅ tests/integration/test_hybrid_mode.py
✅ tests/integration/test_testnet_mode.py
✅ tests/test_domain_mode_validation.py
✅ docs/DOMAIN_MODES_GUIDE.md
✅ docs/PLAYBOOK_HYBRID_SETUP.md
```

### Модифіковані файли (EDIT)

```
📝 config/aurora/system.yaml                          (додати domain_configuration)
📝 apps/reference/config_loader.py                    (додати методи)
📝 vfoundation/core/protocol.py                       (додати mode поле)
📝 vfoundation/core/fsm.py                            (додати методи)
📝 apps/reference/domains/market_data/market_data_connector.py
📝 apps/reference/domains/execution_position/binance_execution_adapter.py
📝 apps/reference/domains/execution_position/fsm.py
📝 apps/reference/domains/account_balance/account_connector.py
📝 JOURNAL.md                                         (запис про реалізацію)
```

### Незмінні файли (NO CHANGE)

```
✅ apps/reference/domains/feature_engineering/
✅ apps/reference/domains/risk_management/
✅ apps/reference/domains/decision_making/
✅ apps/reference/domains/position_tracking/
✅ apps/reference/domains/account_observer/
✅ Всі інші компоненти
```

---

## 🧪 ВАЛІДАЦІЙНІ КРИТЕРІЇ

### Для кожної контрольної точки:

| CP | Критерій | Як тестувати | Очікуваний результат |
|----|---------|---------|----|
| 1 | Конфіг парсується без помилок | `python -c "from apps.reference.config_loader import ConfigLoader; ConfigLoader().load_config()"` | ✅ OK |
| 2 | ConfigLoader методи работают | `pytest tests/test_domain_mode_config.py -v` | 100% passed |
| 3 | Message валідація работает | `pytest tests/test_fsm_mode_contract.py -v` | 100% passed |
| 4 | Домени читають конфіг | `LOG_LEVEL=DEBUG python apps/reference/main.py` (check logs) | "Domain mode: live" / "Domain mode: testnet" |
| 5 | Інтеграційні тести | `pytest tests/integration/test_hybrid_mode.py -v` | 100% passed |
| 6 | Повний pytest suite | `pytest --ignore=tests/test_acl_stub_smoke.py -q` | 644 tests passed |

---

## 🚨 КРИТИЧНІ ТОЧКИ & РИЗИКИ

### Ризик 1: **Backward Compatibility**
- **Проблема**: Нові методи в ConfigLoader можуть зламати старий код
- **Мітигація**: Усі методи мають default значення (return old behavior if domain_modes.yaml не знайдено)

### Ризик 2: **Message Contract Breaking Change**
- **Проблема**: Додання `mode` поля до Message може зламати старий FSM код
- **Мітигація**: `mode` поле is optional (default=None); старий код ігнорує його

### Ризик 3: **Domain Mode Conflicts**
- **Проблема**: Якщо конфіг має невалідну комбінацію (live exec без live data)
- **Мітигація**: `validate_domain_modes()` перевіряє на startup, fail_on_invalid=true

### Ризик 4: **Env Var Resolution**
- **Проблема**: `${DOMAIN_MODE_MARKET_DATA}` має бути правильно розв'язаний
- **Мітигація**: Тестування всіх env var комбінацій в Фазі 5

---

## 📈 МЕТРИКИ УСПІХУ

| Метрика | Target | Current | Status |
|---------|--------|---------|--------|
| **Тестові збої виправлені** | 77 → 0 | 77 | 🔴 |
| **Помилки імпорту** | 33 → 0 | 33 | 🔴 |
| **pytest success rate** | ≥ 99% | 82% | 🟡 |
| **Config validation** | 100% | 0% | 🔴 |
| **Domain isolation** | 100% | 0% | 🔴 |
| **Documentation coverage** | 100% | 0% | 🔴 |

---

## ⏱️ ORІЄНТОВНІ ТЕРМІНИ

| Фаза | Тривалість | Примітка |
|------|-----------|---------|
| Фаза 1: Конфіг | 1-2 дні | Швидко, просто структура YAML |
| Фаза 2: ConfigLoader | 2-3 дні | Середня складність, багато методів |
| Фаза 3: FSM Контракт | 1-2 дні | Мініматьний код, головне - тести |
| Фаза 4: Домени | 3-4 дні | Найбільш праці, багато файлів |
| Фаза 5: Тестування | 2-3 дні | Налагодження, debug |
| Фаза 6: Документація | 1-2 дні | Наприкінці |
| **ВСЬОГО** | **10-16 днів** | За ідеальних умов |

---

## 🎯 НАСТУПНІ КРОКИ

1. **Затвердіть план** - чи все чітко?
2. **Обговоріть Фазу 1** - чи конфіг структура правильна?
3. **Почніть реалізацію** - коли готові, почнемо з Фази 1

---

## 📎 ДОДАТКИ

### А. Приклад Hybrid Mode конфігу в domain_modes.yaml

```yaml
domain_modes:
  market_data:
    mode: "live"               # 🟢 Read from LIVE Binance
  
  execution_position:
    mode: "testnet"            # 🟡 Write to TESTNET Binance
  
  account_balance:
    mode: "inherit"            # Reads from testnet
```

### Б. Приклад Log Output

```
2025-10-27 16:25:00 - INFO - MarketDataConnector initialized with mode=live
2025-10-27 16:25:00 - INFO - BinanceExecutionAdapter initialized with mode=testnet
2025-10-27 16:25:00 - INFO - Domain modes validation: ✅ OK (live data + testnet execution)
2025-10-27 16:25:05 - INFO - EVT:MARKET_TICK_RECEIVED (source=live) - BTCUSDT bid=108263 ask=108264
2025-10-27 16:25:06 - INFO - CMD:OPEN (target=testnet) - BTCUSDT buy qty=0.001
```

### В. Приклад ENV Vars для CI/CD

```bash
# Для гібридного тестування
export DOMAIN_MODE_MARKET_DATA=live
export DOMAIN_MODE_EXECUTION=testnet
export BINANCE_LIVE_API_KEY=xxx
export BINANCE_TESTNET_API_KEY=yyy

# Для чистого testnet
export DOMAIN_MODE_MARKET_DATA=testnet
export DOMAIN_MODE_EXECUTION=testnet
```

---

**Статус План**: ✅ **ГОТОВИЙ ДО ОБГОВОРЕННЯ**

Чекаю вашого затвердження перед початком реалізації.
