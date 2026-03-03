# Звіт про глибоке дослідження: Архітектурний борг у Feature Engineering

Я провів детальний аудит кодової бази `apps/reference/domains/feature_engineering/` (зокрема файлів `types.py`, `feature_engineering.py`, `calculation_engine.py`) на предмет наявності "тихих фолбеків" (silent fallbacks), "захардкоджених параметрів" (magic numbers) та порушень контрактів (try/except blocks).

Дослідження показує, що хоча система має чіткий об'єктно-орієнтований поділ на HotState та Engine, **значний архітектурний борг все ще присутній**.

## 1. Епідемія "Silent Fallbacks" (Тихі відмови)

Найбільша проблема домену — приховування помилок конфігурації або відсутності даних через використання конструкцій `try/except Exception`, які просто ігнорують помилку або повертають дефолтне/нульове значення без зміни стану `ready = False`.

### Знайдені вразливості:

**1.1 `types.py` (Конфігураційні фолбеки)**
У класі `FeatureEngineeringConfig` я знайшов більше 40 (!) блоків `try/except AttributeError` або `except Exception`. Замість того, щоб впасти при старті (fail-fast), якщо якогось ключа немає в конфігу, система тихо підставляє хардкодне значення. 
* *Приклад (Large Trade Imbalance):*
```python
try:
    return bool(self._cfg.large_trade_imbalance.enabled)
except Exception:
    return True # <--- ТИХИЙ ФОЛБЕК (Hardcoded magic)
```
* *Приклад (Macro Sync):*
```python
try:
    return int(self._cfg.macro_sync.max_late_ms)
except Exception:
    return 0 # <--- ТИХИЙ ФОЛБЕК
```
**Наслідок:** Якщо ви зробите опечатку в `feature_engineering.yaml`, система не повідомить про це і буде працювати на прихованих (хардкодних) значеннях.

**1.2 `feature_engineering.py` (Ігнорування виключень у Runtime)**
Головний цикл `on_market_tick` огорнуто у величезний `try/except Exception: pass/log`.
```python
try:
    # 1000 рядків логіки
except Exception as e:
    self.logger.error(f"Error calculating features for {symbol}: {e}")
```
* *Приклад (Price Motion Sanity):* Якщо розрахунок price_motion падає з помилкою, система мовчки створює порожній блок з `None`.
```python
try:
    pm_block = compute_price_motion_block(...)
except Exception:
    pm_block = {"ret_10s": None, ...} # ТИХИЙ ФОЛБЕК
```

**1.3 `calculation_engine.py` (Тихі повернення Neutral Values)**
У центральному файрволі `sanitize_feature` ми маємо:
```python
try:
    val_float = float(raw_value)
except (ValueError, TypeError):
    return (self.cfg.neutral_value, False, "invalid_value_type")
```
Хоча тут коректно ставиться `is_ready = False`, але саме повернення `neutral_value` при фундаментальних помилках даних (наприклад, прийшов словник замість числа) є приховуванням проблеми на рівні скорингу (якщо гейт readiness десь не спрацює).

## 2. Magic Numbers (Захардкоджені параметри)

Незважаючи на наявність Pydantic-схем, у коді розкидані магічні константи, які не можна змінити через конфігурацію:

1. **Price Motion Clip Abs (feature_engineering.py:1252)**
   ```python
   clip_abs = float(getattr(self._price_motion_sanity_cfg, "pm_norm_clip_abs", 10.0))
   ```
   *Магічне число: `10.0`*. Якщо цього ключа немає в конфігу, він обрізає моментум до 10.0.

2. **Spread Health Defaults (types.py:317+)**
   Деякі пороги здоров'я стакану захардкоджені: `spread_health_window_sec = 60` або `spread_health_min_trades_count = 5`.

3. **Кореляційний поріг Пірсона (calculation_engine.py)**
   В обчисленнях `_pearson_correlation` жорстко зашито мінімальну кількість семплів: `n < 2` або `1e-15` для запобігання діленню на нуль. Це прийнятна математична "магія", але поріг перевірки кореляції (наприклад, `if len(tfi_vals) >= 10`) жорстко зашитий на `10` у `compute_absorption`.

## 3. Слабке використання SSOT (Single Source of Truth)

Метод `getattr(..., "key", default)` та словниковий `dict.get("key", default)` використовуються повсюдно в `feature_engineering.py`.
* *Наприклад:* `symbol = event.pld.get("symbol")`
* *Наприклад:* `bar_close_ts = bar_data.get("end_ts_ms") or bar_data.get("close_ts") or bar_data.get("kline_close_time")`

**Проблема:** Такий стиль "вгадування" формату вхідних даних порушує жорсткі контракти (Schema validation). Замість того, щоб пропускати дані через валідатор `BarClosedEvent` чи `MarketTick`, система працює як "всеїдна труба", витягуючи ключі, які зможе знайти. Це призводить до непередбачуваної поведінки при зміні версії формату даних.

## 4. Висновок та Рекомендації

Архітектура Feature Engineering страждає від так званого "оборонного програмування", доведеного до абсурду. Розробники настільки боялися крашу системи (System Crash), що обгорнули кожну операцію в `try/except`, які тихо підставляють нулі, `None` або хардкодні дефолти. 

У фінансових системах **Fail-Fast > Fail-Silent**. Якщо `alpha` розраховується на "вгаданих" даних, система може місяцями втрачати гроші.

**Що потрібно виправити (План рефакторингу):**
1. **Знищити тихі фолбеки в `types.py`:** Якщо конфіг (YAML) не має поля `large_trade_imbalance.enabled`, система повинна впасти при запуску з помилкою `ConfigValidationError`, а не тихо ставити `True`.
2. **Видалити `getattr(obj, "key", 10.0)`:** Замінити всі магічні числа на обов'язкові поля в Pydantic `FeatureEngineeringDomainConfig`.
3. **Жорстка типізація входів:** Замість `event.pld.get(...)` використовувати парсинг через чіткі dataclasses/pydantic моделі для тиків і барів. Якщо прийшов невалідний тик - відкидати його з яскравим `ERROR` логом, а не підставляти дефолти.

Система жива, але тримається на "милицях" з `try/except`.