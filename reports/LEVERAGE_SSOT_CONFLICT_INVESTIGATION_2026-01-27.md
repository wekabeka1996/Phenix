# Leverage SSOT Conflict — Глибоке Дослідження

> **Дата:** 2026-01-27  
> **Мета:** Аналіз конфлікту між bootstrap leverage та sizing calculations  
> **Статус:** 🔴 КРИТИЧНИЙ КОНФЛІКТ ВИЯВЛЕНО

---

## Executive Summary

| Аспект | Проблема | Критичність |
|--------|----------|-------------|
| **Дублювання конфігів** | 3 різних місця зберігають leverage для BTCUSDT | 🔴 КРИТИЧНО |
| **Розбіжність значень** | 20x vs 50x для BTCUSDT | 🔴 КРИТИЧНО |
| **Sizing vs Bootstrap** | Використовують **різні** джерела | 🔴 КРИТИЧНО |
| **Стара логіка** | `leverage_defaults` ще використовується в ExposureGuard | 🟡 LEGACY |

---

## 1. Знайдені джерела Leverage (3 дублювання)

### 1.1. `instruments.yaml` — НОВА ЛОГІКА (SSOT для Sizing)

**Шлях:** `config/aurora/instruments.yaml`  
**Структура:** `instruments.<SYMBOL>.execution.target_leverage`

```yaml
instruments:
  BTCUSDT:
    execution:
      target_leverage: 50        # ← SSOT для sizing calculations
      leverage_policy: "set_and_verify"
      margin_mode: "isolated"
```

**Хто читає:**
- ✅ `DecisionMaking._calculate_position_size()` — L2629: `leverage = int(spec.execution.target_leverage)`
- ✅ `ExposureGuard.resolve_symbol_leverage()` — L371-376 (SSOT priority #1)

**Поточні значення:**
| Symbol | target_leverage |
|--------|-----------------|
| BTCUSDT | **50** |
| ETHUSDT | 41 |
| SOLUSDT | 20 |
| DOGEUSDT | 20 |
| XRPUSDT | 20 |

---

### 1.2. `strategies/aurora.yaml` — НОВА ЛОГІКА (для Bootstrap)

**Шлях:** `config/aurora/strategies/aurora.yaml`  
**Структура:** `aurora.assets.<SYMBOL>.leverage.target`

```yaml
aurora:
  assets:
    BTCUSDT:
      leverage:
        target: 20               # ← Для LeverageBootstrapper
        mode: "ISOLATED"
    ETHUSDT:
      leverage:
        target: 20               # ← НЕ ЗБІГАЄТЬСЯ з instruments!
        mode: "ISOLATED"
```

**Хто читає:**
- ✅ `ExecutionPosition.run_leverage_bootstrap()` → `_collect_leverage_configs()`
- ✅ `LeverageBootstrapper.sync_symbol()`

**Поточні значення:**
| Symbol | leverage.target |
|--------|-----------------|
| BTCUSDT | **20** |
| ETHUSDT | **20** |
| SOLUSDT | **20** |

---

### 1.3. `trading.yaml` — СТАРА ЛОГІКА (Legacy Fallback)

**Шлях:** `config/aurora/trading.yaml`  
**Структура:** `trading.execution.exposure.leverage_defaults`

```yaml
trading:
  execution:
    exposure:
      leverage_defaults:
        BTCUSDT: 20              # ← Legacy fallback
        ETHUSDT: 20
        SOLUSDT: 20
        XRPUSDT: 20
        DOGEUSDT: 20
        __default__: 20
```

**Хто читає:**
- ⚠️ `ExposureGuard.resolve_symbol_leverage()` — L390-400 (fallback if instruments.yaml fails)

**Статус:** `[LEGACY]` — використовується тільки як fallback

---

## 2. 🔴 Критичний Конфлікт: BTCUSDT

### Таблиця розбіжностей:

| Джерело | Шлях | Значення | Використовується для |
|---------|------|----------|---------------------|
| `instruments.yaml` | `instruments.BTCUSDT.execution.target_leverage` | **50** | Sizing calculations |
| `aurora.yaml` | `strategies.aurora.assets.BTCUSDT.leverage.target` | **20** | Bootstrap on exchange |
| `trading.yaml` | `trading.execution.exposure.leverage_defaults.BTCUSDT` | **20** | ExposureGuard fallback |

### Наслідки:

1. **При старті системи** — `LeverageBootstrapper` читає `aurora.yaml` і виставляє на біржі **20x**
2. **При розрахунку розміру позиції** — `DecisionMaking` читає `instruments.yaml` і рахує як **50x**

### Математичний конфлікт:

```
# Sizing calculation (instruments.yaml: 50x)
notional_target = equity × margin_pct × 50 = $500 × 0.10 × 50 = $2,500

# Exchange actual (aurora.yaml: 20x)
max_notional = equity × 20 = $500 × 20 = $10,000
required_margin = $2,500 / 20 = $125

# Очікувана margin (за sizing логікою)
expected_margin = $2,500 / 50 = $50

# РЕЗУЛЬТАТ: Замовлення може бути відхилене через:
# - Insufficient margin (якщо equity < $125)
# - Неправильний PnL калькулейшен
```

---

## 3. Потік даних: Де яка логіка працює

### 3.1. Startup Flow (Bootstrap)

```
[System Start]
       │
       ▼
[ExecutionPosition.run_leverage_bootstrap()]
       │
       ▼
[_collect_leverage_configs()]
       │ ← Читає: strategies.aurora.assets.<SYM>.leverage.target
       ▼
[LeverageBootstrapper.sync_symbol()]
       │
       ▼
[BinanceAdapter.set_leverage(symbol, 20)]  ← ВИСТАВЛЯЄ 20x на біржі
```

### 3.2. Runtime Flow (Sizing)

```
[Signal Generated]
       │
       ▼
[DecisionMaking._calculate_position_size()]
       │ ← Читає: instruments.<SYM>.execution.target_leverage (50)
       ▼
[compute_notional_target(leverage=50)]
       │
       ▼
[qty = notional_target / price]  ← РАХУЄ як 50x!
```

### 3.3. Exposure Guard Flow

```
[ExposureGuard.can_open()]
       │
       ▼
[resolve_symbol_leverage()]
       │ ← SSOT: instruments.yaml (50) ✅
       │ ← Fallback: trading.yaml (20) ⚠️
       ▼
[reserve_margin = notional / leverage]
```

---

## 4. Порівняння логік

### Нова логіка (P1: Active Leverage Management)

| Компонент | Файл | Статус |
|-----------|------|--------|
| **LeverageConfig model** | `config_models.py:71` | ✅ Готовий |
| **LeverageBootstrapper** | `bootstrapping/leverage_bootstrapper.py` | ✅ Готовий |
| **LeverageService** | `leverage_service.py` | 🟡 Готовий, НЕ WIRED |
| **_collect_leverage_configs()** | `fsm.py:580` | ✅ Читає strategy configs |
| **run_leverage_bootstrap()** | `fsm.py:532` | ✅ Викликає bootstrapper |

**Джерело leverage:** `strategies.aurora.assets.<SYM>.leverage.target`

### Стара логіка (Legacy)

| Компонент | Файл | Статус |
|-----------|------|--------|
| **leverage_defaults** | `trading.yaml:131` | 🟡 LEGACY, fallback only |
| **ExposureGuard fallback** | `exposure_guard.py:390-400` | ⚠️ Ще активний |

### Sizing логіка (SSOT)

| Компонент | Файл | Статус |
|-----------|------|--------|
| **target_leverage** | `instruments.yaml` | ✅ SSOT для sizing |
| **DecisionMaking** | `decision_making.py:2629` | ✅ Читає instruments |

---

## 5. Аналіз: Яка логіка краща?

### ✅ `instruments.yaml` (Sizing SSOT) — РЕКОМЕНДОВАНО як ЄДИНИЙ SSOT

**Переваги:**
1. Вже є SSOT для sizing, constraints (step_size, min_qty, min_notional)
2. Містить `leverage_policy` — контролює поведінку (set_and_verify vs verify_only)
3. Консистентний з margin_mode
4. Читається в `DecisionMaking` — критичний для правильного sizing

**Поля:**
```yaml
execution:
  margin_mode: "isolated"
  target_leverage: 50
  leverage_policy: "set_and_verify"
  max_notional_utilization: 0.8
```

### ⚠️ `strategies.aurora.assets.<SYM>.leverage` — ДУБЛЮВАННЯ

**Проблема:**
1. Дублює `instruments.yaml` з іншими значеннями
2. Читається тільки для bootstrap, не для sizing
3. Створює неузгодженість між біржею та розрахунками

**Поля:**
```yaml
leverage:
  target: 20
  mode: "ISOLATED"
```

### ❌ `trading.yaml leverage_defaults` — DEPRECATED

**Проблема:**
1. Legacy fallback — не використовується якщо instruments.yaml є
2. Не має `leverage_policy`
3. Не консистентний з margin_mode

---

## 6. Рекомендований План Виправлення

### Phase 1: Consolidation (КРИТИЧНО)

1. **Видалити `leverage` з `strategies/aurora.yaml`**
   - Поле `strategies.aurora.assets.<SYM>.leverage` — DEAD
   - LeverageBootstrapper має читати з `instruments.yaml`

2. **Модифікувати `_collect_leverage_configs()`**
   ```python
   # BEFORE (fsm.py:580+)
   leverage_cfg = asset_cfg.leverage  # ← Читає strategy config
   
   # AFTER
   spec = self.config.instruments.get(symbol)
   if spec and spec.execution:
       leverage_cfg = LeverageConfig(
           target=spec.execution.target_leverage,
           mode=spec.execution.margin_mode.upper(),
       )
   ```

3. **Видалити `trading.yaml leverage_defaults`**
   - Після міграції ExposureGuard повністю на instruments SSOT

### Phase 2: Assertion Guard (VALIDATION)

4. **Додати startup assertion**
   ```python
   # В startup flow (fsm.py або main.py)
   for symbol in trading_symbols:
       instruments_lev = config.instruments[symbol].execution.target_leverage
       
       # Перевірити що strategy leverage (якщо є) == instruments
       strategy_lev = strategy_assets.get(symbol, {}).get('leverage', {}).get('target')
       if strategy_lev is not None and strategy_lev != instruments_lev:
           raise ConfigContractError(
               path=f"strategies.*.assets.{symbol}.leverage.target",
               why=f"LEVERAGE_SSOT_CONFLICT: strategy={strategy_lev}, instruments={instruments_lev}. "
                   f"SSOT is instruments.{symbol}.execution.target_leverage",
           )
   ```

### Phase 3: Cleanup (MAINTENANCE)

5. **Видалити мертві поля зі schema**
   - `LeverageConfig` в strategy assets — deprecated
   - Оновити docs/CONFIG_MAP.md

6. **Оновити тести**
   - `test_leverage_config_loading.py` — тести на новий flow
   - Gate test: leverage SSOT consistency

---

## 7. Негайні дії (Hotfix)

### Варіант A: Синхронізувати значення (Швидкий фікс)

Змінити `strategies/aurora.yaml` щоб значення збігалися:

```yaml
# aurora.yaml
BTCUSDT:
  leverage:
    target: 50    # ← Змінити з 20 на 50 (match instruments.yaml)
    mode: "ISOLATED"

ETHUSDT:
  leverage:
    target: 41    # ← Змінити з 20 на 41 (match instruments.yaml)
    mode: "ISOLATED"
```

**Ризик:** Дублювання залишається, може розсинхронізуватись знову.

### Варіант B: LeverageBootstrapper читає instruments (Правильний фікс)

Змінити `_collect_leverage_configs()` щоб читав з instruments:

```python
def _collect_leverage_configs(self) -> Dict[str, "LeverageConfig"]:
    """Collect LeverageConfig from instruments.yaml SSOT."""
    result: Dict[str, LeverageConfig] = {}
    
    for symbol in self._get_active_symbols():
        spec = self.config.instruments.get(symbol)
        if spec and spec.execution and spec.execution.target_leverage:
            from apps.reference.config_models import LeverageConfig
            result[symbol] = LeverageConfig(
                target=spec.execution.target_leverage,
                mode=spec.execution.margin_mode.upper(),
            )
    
    return result
```

---

## 8. Таблиця значень для синхронізації

| Symbol | instruments.yaml | aurora.yaml | trading.yaml | Потрібне значення |
|--------|-----------------|-------------|--------------|------------------|
| BTCUSDT | 50 | 20 | 20 | **50** |
| ETHUSDT | 41 | 20 | 20 | **41** |
| SOLUSDT | 20 | 20 | 20 | 20 ✅ |
| DOGEUSDT | 20 | - | 20 | 20 ✅ |
| XRPUSDT | 20 | - | 20 | 20 ✅ |

---

## 9. Висновок

### Корінь проблеми:

Під час реалізації P1: Active Leverage Management було створено **нову структуру** для leverage в strategy configs (`strategies.aurora.assets.<SYM>.leverage`), але:

1. **Не видалено стару логіку** (`trading.yaml leverage_defaults`)
2. **Не синхронізовано з SSOT** (`instruments.yaml target_leverage`)
3. **Різні компоненти читають різні джерела**

### Рекомендація:

**ЄДИНИЙ SSOT для leverage: `instruments.<SYM>.execution.target_leverage`**

Всі інші джерела (`strategies.*.leverage`, `trading.leverage_defaults`) мають бути:
1. Deprecated
2. Видалені з runtime логіки
3. Замінені на читання з instruments.yaml

---

## Appendix: Файли для модифікації

| Файл | Дія | Пріоритет |
|------|-----|-----------|
| `fsm.py:_collect_leverage_configs()` | Читати з instruments | P0 |
| `strategies/aurora.yaml` | Видалити leverage блоки | P1 |
| `strategies/mean_reversion.yaml` | Видалити leverage блоки | P1 |
| `trading.yaml:leverage_defaults` | Deprecated → Видалити | P2 |
| `config_models.py:LeverageConfig` | Залишити для bootstrap interface | - |
| `exposure_guard.py:resolve_symbol_leverage` | Видалити fallback гілку | P2 |
