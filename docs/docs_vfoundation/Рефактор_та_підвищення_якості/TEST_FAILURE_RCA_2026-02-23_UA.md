# Глибинне RCA падіння тестів (46 collection errors)

**Дата аналізу:** 2026-02-23  
**Середовище:** Windows (`win32`), Python 3.14.3, pytest 9.0.2  
**Сфера:** падіння під час `pytest` collection у монорепо `Phenix`

## 1) Executive Summary

1. **44 із 46 помилок (95.65%)** мають **єдину кореневу причину**: тест `tests/integration/test_pillar_to_decision_e2e.py` під час імпорту глобально підміняє `sys.modules["vfoundation"/*]` на `MagicMock`, що ламає пакетний імпорт для всього ранa.
2. **2 із 46 помилок (4.35%)** — окремий шар: два unit-тести намагаються відкрити **видалений** файл `vfoundation/adapters/binance_adapter.py` (легасі-дрейф після рефакторингу).
3. Основний висновок: це **не масовий баг production-коду vfoundation**, а поєднання
   - дефекту ізоляції тестів (архітектурний борг тестового контуру),
   - легасі-тестів, що відстали від структури коду.

## 2) Як перевірялось (доказова база)

### Експеримент A — baseline (повтор симптома)

Команда:

```powershell
.\.venv\Scripts\python -m pytest --collect-only -q --maxfail=1000
```

Результат:
- `collected 3308 items / 46 errors / 7 deselected / 13 skipped / 3301 selected`

### Експеримент B — прибрати лише `test_pillar_to_decision_e2e.py`

Команда:

```powershell
.\.venv\Scripts\python -m pytest --collect-only -q --ignore tests\integration\test_pillar_to_decision_e2e.py
```

Результат:
- `collected 3826 items / 2 errors / 7 deselected / 13 skipped / 3819 selected`
- лишились тільки 2 `FileNotFoundError` по `binance_adapter.py`

### Експеримент C — прибрати лише 2 binance unit-тести

Команда:

```powershell
.\.venv\Scripts\python -m pytest --collect-only -q --maxfail=1000 --ignore tests\units\test_binance_adapter_unit.py --ignore tests\units\test_vfoundation_binance_adapter_unit.py
```

Результат:
- `collected 3308 items / 44 errors ...`

Висновок: **44 помилки створює саме `test_pillar_to_decision_e2e.py`**.

### Експеримент D — прибрати 3 проблемні файли

Команда:

```powershell
.\.venv\Scripts\python -m pytest --collect-only -q --ignore tests\integration\test_pillar_to_decision_e2e.py --ignore tests\units\test_binance_adapter_unit.py --ignore tests\units\test_vfoundation_binance_adapter_unit.py
```

Результат:
- `3819/3826 tests collected (7 deselected)`
- **0 collection errors**

### Експеримент E — пряма причинність «отруєння імпорту»

1) `tests/test_ttl_cache.py` сам по собі:

```powershell
.\.venv\Scripts\python -m pytest tests\test_ttl_cache.py -q
```

- `21 passed`

2) той же файл, але разом з `test_pillar_to_decision_e2e.py`:

```powershell
.\.venv\Scripts\python -m pytest tests\integration\test_pillar_to_decision_e2e.py tests\test_ttl_cache.py -q
```

- `ModuleNotFoundError: ... 'vfoundation.core' is not a package`

3) Python check після імпорту проблемного модуля:
- `sys.modules["vfoundation"]` -> `MagicMock`
- `has __path__? False`
- імпорт `vfoundation.core.cache.ttl_cache` падає

## 3) Знахідка №1 (головна): глобальна підміна `sys.modules` у тесті

**Файл:** `tests/integration/test_pillar_to_decision_e2e.py`  
**Ключові рядки:** 10-15

```python
sys.modules["vfoundation"] = vfoundation_mock
sys.modules["vfoundation.core"] = MagicMock()
sys.modules["vfoundation.core.protocol"] = MagicMock()
sys.modules["vfoundation.dr"] = MagicMock()
sys.modules["vfoundation.dr.wal"] = MagicMock()
sys.modules["vfoundation.core.why_codes"] = MagicMock()
```

### Що цей тест намагається перевірити логічно

- сценарій `FE pillars -> AuroraHandler -> EVT:STRATEGY_SIGNAL_PRODUCED`
- виклик `AuroraHandler.on_process_strategy(...)` і перевірку `psi_vector` (`quadratic_v1`, `pillar_sum`, `raw_exposure`)

### Чому реалізація тесту некоректна

1. Підміна робиться на **module level під час import**, а не локально в тесті/фікстурі.
2. Нема rollback/cleanup (`del`/`pop`/restore) для `sys.modules`.
3. Через це всі наступні тести в тому ж процесі бачать `vfoundation` як не-пакет (`MagicMock` без `__path__`).

### Вплив

- Масовий каскад `ModuleNotFoundError` / `AttributeError: __path__`
- Блокується колекція тестів у `tests/vfoundation/*`, `tests/test_*`, інтеграційних сценаріях.

### Класифікація

- **Реальний дефект тесту** + **архітектурний борг тестового контуру** (ізоляція стану між тест-модулями).

## 4) Знахідка №2: легасі unit-тести на видалений модуль

**Файли:**
- `tests/units/test_binance_adapter_unit.py` (line 19 містить `"binance_adapter.py"`)
- `tests/units/test_vfoundation_binance_adapter_unit.py` (line 16 містить `"binance_adapter.py"`)

Обидва через `importlib.util.spec_from_file_location(...)` намагаються завантажити:
- `vfoundation/adapters/binance_adapter.py`

А файл відсутній, тому `FileNotFoundError` під час collection.

### Що тестували ці тести

- `_norm_params`, `_sign_build`, `_to_decimal`, `_round_step`

### Де ця логіка зараз

- у `apps/reference/adapters/binance_adapter.py`
  - `class BinanceAdapter` (line 126)
  - `_norm_params` (line 325)
  - `_sign_build` (line 372)
  - `_to_decimal` (line 1669)
  - `_round_step` (line 1687)

### Документальне підтвердження легасі-статусу

- `docs/docs_vfoundation/ROADMAP_HARDENING.md` line 74: **Delete `adapters/binance_adapter.py` (0 active imports confirmed)**

### Класифікація

- **Легасі-дрейф тестів** (міграція коду відбулась, тести не догнані).

## 5) Зв’язок із документацією та архконтекстом

1. `docs/docs_vfoundation/BLUEPRINT_PHASES_9_14.md` уже фіксує аналогічний ризик namespace collision:
   - line 289: *Phase 9.0.7 — виправити broader test suite collection errors*
   - line 299: причина `vfoundation.core is not a package`
   - line 314: ціль `0 collection errors`
2. Поточний інцидент — фактично **рецидив того самого класу проблеми** (package boundary / import isolation).

## 6) Другий порядок (після усунення collection-блокерів)

Після відключення 3 blocker-файлів collection стає чистим, але є ознаки додаткового легасі боргу у тестах:

1. `tests/integration/test_pillar_to_decision_e2e.py` падає вже на runtime (`TypeError` у `ContextShield`) через неповний `MagicMock`-конфіг.
2. `tests/integration/test_startup_filters_wiring.py` падає на runtime (`TypeError` у `setup_logging`) — тестовий mock-конфіг не відповідає новому контракту `config.observability.logging.default_level`.

Це не центральна причина 46 collection errors, але важливий сигнал: **частина integration-тестів застаріла відносно поточного config contract**.

## 7) Підсумкова класифікація: баг чи легасі чи архборг

1. **Primary root cause (44/46):**
   - Тип: дефект тесту + архітектурний борг ізоляції.
   - Не production-bug у `vfoundation`.
2. **Secondary root cause (2/46):**
   - Тип: легасі тести на видалений шлях.
3. **Process gap:**
   - Уже відомий у blueprint клас проблем (Phase 9.0.7), але регрес не заблокований автоматичним gate у CI.

## 8) Висновок (чітко)

Падіння з вашого логу **переважно не про “зламану бізнес-логіку vfoundation”**. Це комбінація:

1. **Токсичного тесту** (`test_pillar_to_decision_e2e.py`), який псує глобальний імпортний простір.
2. **Двох легасі unit-тестів**, що посилаються на файл, який документовано видалений.

Отже:
- це **не один глибинний production баг**,
- це **борг тестової архітектури + легасі шари**,
- і саме вони створюють хибне враження масового падіння ядра.

## 9) Рекомендований порядок відновлення (P0 → P2)

1. **P0:** ізолювати або переробити `test_pillar_to_decision_e2e.py`
   - прибрати module-level підміну `sys.modules[...]`
   - використовувати локальні `patch`/`monkeypatch` у межах тесту/фікстури
   - або тимчасово позначити `@pytest.mark.legacy`
2. **P0:** для 2 `binance_adapter_unit` тестів
   - або видалити/позначити `legacy`,
   - або мігрувати на `apps/reference/adapters/binance_adapter.py`
3. **P1:** додати guard у CI на namespace-poisoning
   - перевірка `pytest --collect-only --maxfail=1000`
   - статичний lint на module-level `sys.modules[...] =` у `tests/`
4. **P2:** вирівняти дрібний конфіг-борг
   - переглянути `pytest.ini` (`python_paths = apps vfoundation/vfoundation`) — шлях виглядає неконсистентним із фактичною структурою.
