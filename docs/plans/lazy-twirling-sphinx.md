# ПЛАН: Alpha Search + Mean Reversion — fail-fast та cleanup

## Scope досліджених проблем

| # | Проблема | Файл | Ризик |
|---|---|---|---|
| A | `signal_weights/feature_neutrals/regime_thresholds` — Optional з fallback | `alpha_search/config_models.py` + `aurora_adapter.py` | Середній — silent wrong weights |
| B | `force_close_all/reset_symbol/reset_all` CRASH коли `resampler is None` | `mean_reversion_strategy.py:654,668,676` | Середній — поки не викликаються |
| C | `on_tick` мертвий код (200 рядків) | `mean_reversion_strategy.py:368-452` | Низький — захаращує код |
| D | Confidence hardcodes `0.5`, `2`, `0.2` без config path | `mean_reversion_strategy.py:541-557` | Середній — не можна тюнити |
| E | `wall_ts_ms = time.time()` | `feature_engineering.py:601` | НЕ проблема — causality guard only, см. нижче |

**wall_ts_ms вирок**: `wall_ts_ms` читається ТІЛЬКИ в causality check (`_calculate_and_emit_features_for_tf:820`). Використовується щоб уникнути false "anchor_from_future" rejection коли бар закривається до приходу live anchor tick. Це **навмисна архітектурна конструкція**, а не wallclock leak в логіку торгівлі. Не чіпати.

---

## Tier A — Alpha Search: silent fallback → fail-loud

### Проблема
```python
# config_models.py:65-72
signal_weights: Optional[Dict[str, float]] = Field(default=None, ...)
feature_neutrals: Optional[Dict[str, float]] = Field(default=None, ...)
regime_thresholds: Optional[Dict[str, float]] = Field(default=None, ...)
```
```python
# aurora_adapter.py:126-129
self._signal_weights = signal_weights or _FALLBACK_SIGNAL_WEIGHTS  # тихий fallback
self._feature_neutrals = feature_neutrals or _FALLBACK_FEATURE_NEUTRALS
self._regime_thresholds = regime_thresholds or _FALLBACK_REGIME_THRESHOLDS
```
Якщо `signal_weights` зникне з YAML — Pydantic не впаде, система тихо перейде на `_FALLBACK_SIGNAL_WEIGHTS`.

### Фікс

**Файл 1: `apps/reference/domains/alpha_search/config_models.py`**

Зробити `signal_weights`, `feature_neutrals`, `regime_thresholds` **required** — прибрати `Optional` та `default=None`:
```python
# BEFORE:
signal_weights: Optional[Dict[str, float]] = Field(default=None, ...)
feature_neutrals: Optional[Dict[str, float]] = Field(default=None, ...)
regime_thresholds: Optional[Dict[str, float]] = Field(default=None, ...)

# AFTER:
signal_weights: Dict[str, float] = Field(description="Feature weights for directional scoring.")
feature_neutrals: Dict[str, float] = Field(description="Neutral/center values per feature.")
regime_thresholds: Dict[str, float] = Field(description="Regime-based threshold multipliers.")
```

**Файл 2: `apps/reference/domains/alpha_search/models/aurora_adapter.py`**

Прибрати `_FALLBACK_*` fallback з конструктора — зробити `signal_weights` обов'язковим:
```python
# BEFORE:
def __init__(self, signal_weights=None, ...):
    self._signal_weights = signal_weights or _FALLBACK_SIGNAL_WEIGHTS

# AFTER:
def __init__(self, signal_weights: Dict[str, float], ...):
    self._signal_weights = signal_weights
```
Аналогічно для `feature_neutrals` та `regime_thresholds`.
`_FALLBACK_*` константи залишити як TEST HELPERS (помітити коментарем).

**Файл 3: `backtest_plugin.py`** — не потребує змін, він вже передає `adapter_cfg.signal_weights`.

**Файл 4: 12 тестів що падуть** — треба оновити:
- `tests/domains/alpha_search/test_backtest_plugin.py` (~11 місць)
- `tests/domains/alpha_search/test_integration.py` (1 місце)

В кожному місці де `AuroraAdapterConfig()` без аргументів — додати:
```python
from apps.reference.domains.alpha_search.models.aurora_adapter import (
    _FALLBACK_SIGNAL_WEIGHTS, _FALLBACK_FEATURE_NEUTRALS, _FALLBACK_REGIME_THRESHOLDS
)
AuroraAdapterConfig(
    signal_weights=_FALLBACK_SIGNAL_WEIGHTS,
    feature_neutrals=_FALLBACK_FEATURE_NEUTRALS,
    regime_thresholds=_FALLBACK_REGIME_THRESHOLDS,
)
```

**Файл 5: NEW TEST** `tests/unit/alpha_search/test_aurora_adapter_config_contract.py`
- `AuroraAdapterConfig()` без `signal_weights` → raises `ValidationError`
- `AuroraAdapterConfig()` без `feature_neutrals` → raises `ValidationError`
- `AuroraAdapterConfig()` без `regime_thresholds` → raises `ValidationError`
- З usіма трьома полями → OK

---

## Tier B — MR: crash-prone reset methods

### Проблема
```python
# mean_reversion_strategy.py:654 — force_close_all
bar = state.resampler.force_close(timestamp_ms)  # AttributeError якщо resampler is None

# mean_reversion_strategy.py:668 — reset_symbol
self._states[symbol].resampler.reset()  # AttributeError

# mean_reversion_strategy.py:676 — reset_all
state.resampler.reset()  # AttributeError
```
`resampler` завжди `None` в продакшені (лінія 279). Якщо ці методи будуть викликані — crash.

### Фікс

**Файл: `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`**

Додати None-guard в усі три методи:
```python
# force_close_all:
bar = state.resampler.force_close(timestamp_ms) if state.resampler else None

# reset_symbol:
if self._states[symbol].resampler is not None:
    self._states[symbol].resampler.reset()

# reset_all:
if state.resampler is not None:
    state.resampler.reset()
```

**NEW TEST** в `tests/domains/feature_engineering/test_mr_strategy_none_resampler.py`:
- `reset_symbol(symbol)` без resampler — не крашиться
- `reset_all()` без resampler — не крашиться
- `force_close_all(ts)` без resampler — повертає `{symbol: None}`, не крашиться

---

## Tier C — MR on_tick: видалення мертвого коду

### Проблема
`on_tick` (lines 368-452) — 85 рядків мертвого коду. Усі тести на нього вже `pytest.mark.skip(reason="T2B-02")`. Ніколи не виконується (resampler=None → return None на лінії 395).

### Фікс

**Файл: `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`**

Видалити весь метод `on_tick` (lines 368-452). Залишити docstring-notice якщо є посиланняззовні.

Перевірити: є зовнішні виклики `on_tick`? Якщо є - зробити `raise NotImplementedError("Deprecated: use on_bar()")` замість видалення.

---

## Tier D — MR Confidence: hardcodes → config

### Проблема
```python
# _evaluate_signal:
confidence = Decimal("0.5") + (entry_threshold - pct_b) * Decimal("2")  # base=0.5, mult=2
confidence += Decimal("0.2")  # rsi_boost=0.2
```
Неможливо тюнити без зміни коду.

### Фікс

**Файл 1: `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`**

Додати в `MRStrategyConfig`:
```python
# Confidence formula params
confidence_base: Decimal = Decimal("0.5")
confidence_distance_mult: Decimal = Decimal("2")
rsi_confidence_boost: Decimal = Decimal("0.2")
```

Замінити в `_evaluate_signal`:
```python
# BEFORE:
confidence = Decimal("0.5") + (entry_threshold - pct_b) * Decimal("2")
confidence += Decimal("0.2")

# AFTER:
confidence = self.config.confidence_base + (entry_threshold - pct_b) * self.config.confidence_distance_mult
confidence += self.config.rsi_confidence_boost
```

**Файл 2: YAML** `config/aurora/strategies/mean_reversion.yaml` (і/або `aurora.yaml`) — додати нові поля з поточними значеннями як дефолт (backward compatible зміна).

**NEW TEST** в `tests/domains/feature_engineering/test_mr_confidence_config.py`:
- Confidence з `confidence_base=0.7` повертає значення > 0.5 (не захардкоджено)
- Confidence з `rsi_confidence_boost=0.3` відрізняється від boost=0.2

---

## Порядок імплементації

1. ✅ **Tier B** (crash-guard) — виконано
2. ✅ **Tier C** (delete on_tick) — виконано
3. ✅ **Tier D** (confidence config) — виконано
4. ✅ **Tier A** (signal_weights required) — виконано
5. ✅ `test_aurora_adapter_config_contract.py` — написано
6. ✅ `test_mr_strategy_none_resampler.py` — написано
7. ⏳ `test_mr_confidence_config.py` — ЗАЛИШИЛОСЬ НАПИСАТИ
8. ⏳ Запустити повний test suite

---

## Верифікація

```bash
# Після Tier A:
pytest tests/domains/alpha_search/ -v
pytest tests/unit/alpha_search/test_aurora_adapter_config_contract.py -v

# Після Tier B+C:
pytest tests/domains/feature_engineering/ -v
pytest tests/domains/feature_engineering/test_mr_strategy_none_resampler.py -v

# Після Tier D:
pytest tests/domains/feature_engineering/test_mr_confidence_config.py -v

# Фінальний прогін:
pytest -q tests/ --ignore=tests/integration
```

Очікувано: всі тести PASSED.

---

## Файли для зміни

| Файл | Зміна |
|---|---|
| `apps/reference/domains/alpha_search/config_models.py` | signal_weights/feature_neutrals/regime_thresholds → required |
| `apps/reference/domains/alpha_search/models/aurora_adapter.py` | прибрати `or _FALLBACK` з constructor |
| `tests/domains/alpha_search/test_backtest_plugin.py` | ~11 місць: передати _FALLBACK_* явно |
| `tests/domains/alpha_search/test_integration.py` | 1 місце: передати _FALLBACK_* явно |
| `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` | None-guard в reset/force_close + delete on_tick + confidence_* поля |
| `config/aurora/strategies/mean_reversion.yaml` | додати confidence_base/distance_mult/rsi_confidence_boost |
| `tests/unit/alpha_search/test_aurora_adapter_config_contract.py` | NEW |
| `tests/domains/feature_engineering/test_mr_strategy_none_resampler.py` | NEW |
| `tests/domains/feature_engineering/test_mr_confidence_config.py` | NEW |
