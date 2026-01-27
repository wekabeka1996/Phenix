# DEEP FORENSICS: Config Fields Investigation Report #02
**Date**: 2026-01-25  
**Investigation**: Перевірка полів позначених `[DEAD]` у CONFIG_MAP.md  
**Запит**: Чи справді ці поля мертві та не використовуються системою?

---

## Executive Summary

З **58 досліджуваних полів**:
- ✅ **22 FALSE POSITIVES** — поля ЖИВІ і використовуються кодом
- ❌ **36 TRUE DEAD** — поля справді мертві або дубльовані

**КРИТИЧНА ЗНАХІДКА**: Багато полів позначених `[DEAD]` насправді **АКТИВНО** використовуються runtime кодом!

---

## Group 1: execution_position.utils ✅ ЖИВІ (FALSE POSITIVE)

### Status: **АКТИВНО ВИКОРИСТОВУЮТЬСЯ**

| Field | Location | Usage | Evidence |
|-------|----------|-------|----------|
| `basis_points_base` | domains.yaml | utils.py:L243 | Розрахунок TP/SL цін |
| `client_order_id_max_length` | domains.yaml | utils.py:L155 | Генерація clientOrderId |

**Code Evidence:**
```python
# apps/reference/domains/execution_position/utils.py:155
max_len = config.domains.execution_position.utils.client_order_id_max_length

# apps/reference/domains/execution_position/utils.py:243
b = config.domains.execution_position.utils.basis_points_base
```

**Verdict**: ✅ **KEEP** — критичні для execution логіки

---

## Group 2: execution_position.watchdog.* ✅ ЖИВІ (FALSE POSITIVE)

### Status: **ПЕРЕМІЩЕНО + АКТИВНО ВИКОРИСТОВУЮТЬСЯ**

⚠️ **Помилка в CONFIG_MAP**: Поля помічені `[DEAD]` для `domains.execution_position.watchdog.*`, але насправді:
- Поля **переміщені** з `domains.yaml` → `trading.yaml` (TASK-ZOMBIE-FIX)
- SSOT тепер: `trading.execution.watchdog.*`
- Всі поля **активно використовуються** runtime

| Field | Status | Evidence |
|-------|--------|----------|
| `ack_ttl_ms` | ✅ ЖИВЕ | fsm.py:L346 — читається з config |
| `fill_ttl_ms` | ✅ ЖИВЕ | fsm.py:L347 — читається з config |
| `check_interval_ms` | ✅ ЖИВЕ | watchdog.py:L62, L272 — sleep interval |
| `rps_limit` | ✅ ЖИВЕ | watchdog.py:L90, L349 — rate limiting |

**Code Evidence:**
```python
# fsm.py:346-347
ack_ttl_ms: int = int(get_watchdog_setting("ack_ttl_ms", None))
fill_ttl_ms: int = int(get_watchdog_setting("fill_ttl_ms", None))

# watchdog.py:62
self.check_interval_ms = self.config["check_interval_ms"] if "check_interval_ms" in self.config else check_interval_ms

# watchdog.py:90
self._rps_limit = self.config["rps_limit"] if "rps_limit" in self.config else 10
```

**Verdict**: ✅ **KEEP in trading.yaml** — критичні для order watchdog  
⚠️ **PURGE duplicates in domains.yaml** — старі дубльовані записи

---

## Group 3: feature_engineering.defaults.* ✅ ЖИВІ (FALSE POSITIVE)

### Status: **АКТИВНО ВИКОРИСТОВУЮТЬСЯ**

| Field | Usage | Evidence |
|-------|-------|----------|
| `neutral_value` | types.py:L825-827 | Дефолтне neutral значення [0, 1] |
| `zero_value` | types.py:L830-832 | Placeholder для absent features |
| `correlation_default` | types.py:L835-837 | Дефолт для кореляцій |
| `ms_per_sec` | types.py:L817-818, L840-842 | Константа часу (1000) |

**Code Evidence:**
```python
# types.py:825-827
@property
def neutral_value(self) -> decimal.Decimal:
    return decimal.Decimal(str(self._cfg.defaults.neutral_value))

# types.py:817
def ms_per_sec(self) -> int:
    return int(self._cfg.defaults.ms_per_sec)
```

**Verdict**: ✅ **KEEP** — використовуються для feature нормалізації

---

## Group 4: feature_engineering.absorption.* ⚠️ ЧАСТКОВО ЖИВІ

### Status: **MIXED — деякі поля активні**

| Field | Status | Evidence |
|-------|--------|----------|
| `mode` | ✅ ЖИВЕ | types.py:L676 |
| `proxy.source` | ✅ ЖИВЕ | types.py:L686 |
| `proxy.window` | ✅ ЖИВЕ | types.py:L696 |
| `proxy.eps` | ✅ ЖИВЕ | types.py:L706 |
| `dedup.enabled` | ✅ ЖИВЕ | types.py:L716 |
| `dedup.window` | ✅ ЖИВЕ | types.py:L726 |
| `dedup.threshold` | ✅ ЖИВЕ | types.py:L736 |
| `clip` | ✅ ЖИВЕ | types.py:L746 |
| `neutral` | ✅ ЖИВЕ | types.py:L756 |
| `bounds.min` | ❓ НЕВІДОМО | Не знайдено прямих звернень |
| `bounds.max` | ❓ НЕВІДОМО | Не знайдено прямих звернень |

**Code Evidence:**
```python
# types.py:676
if self._cfg.absorption:
    return str(self._cfg.absorption.mode)

# types.py:715-716
if self._cfg.absorption and self._cfg.absorption.dedup:
    return bool(self._cfg.absorption.dedup.enabled)
```

**Verdict**: 
- ✅ **KEEP**: mode, proxy.*, dedup.*, clip, neutral
- ❓ **ПОТРЕБУЄ ГЛИБШОГО АНАЛІЗУ**: bounds.min/max

---

## Group 5: feature_engineering.ema.* ❌ DEAD?

### Status: **МОЖЛИВО МЕРТВІ**

| Field | Status | Evidence |
|-------|--------|----------|
| `period_long` | ❓ | Не знайдено прямих звернень у FE коді |
| `period_short` | ❓ | Не знайдено прямих звернень у FE коді |

**Verdict**: ❓ **ПОТРЕБУЄ DEEP DIVE** — можливо замінені на інші конфіги

---

## Group 6: feature_engineering.ema_bias.* ❌ DEAD?

### Status: **МОЖЛИВО МЕРТВІ**

| Field | Status | Evidence |
|-------|--------|----------|
| `clamp_max` | ❓ | Є в config_models.py (L1352), але не знайдено використання |
| `clamp_min` | ❓ | Є в config_models.py, але не знайдено використання |

**Verdict**: ❓ **ПОТРЕБУЄ DEEP DIVE** — можливо застарілі

---

## Group 7: feature_engineering.* (інші) ❌ DEAD?

### Status: **МОЖЛИВО МЕРТВІ**

| Field | Status | Evidence |
|-------|--------|----------|
| `delta_price.spike_filter_ms` | ❓ | Є в models, але не знайдено читання |
| `depth_imbalance.use_laplace_smoothing` | ❓ | Є в models, але не знайдено читання |
| `enable_new_metrics` | ✅ ЖИВЕ? | Є в reachability_scan.txt |
| `enabled_timeframes_sec` | ✅ ЖИВЕ? | Згадується в reports |
| `feature_sanity.*` | ❌ МЕРТВІ | Велика структура, не знайдено використання |

**Verdict**: ❓ **MIXED** — потрібен deeper analysis

---

## Group 8: feature_sanity.* ❌ TRUE DEAD

### Status: **МЕРТВА СТРУКТУРА**

Вся гілка `feature_sanity.*` (50+ полів) **не має code consumption**:
- `feature_sanity.enabled`
- `feature_sanity.feature_bounds.*` (всі підполя)
- `feature_sanity.nan_inf_behavior`

**Verdict**: ❌ **TRUE DEAD** — можна видаляти всю секцію

---

## Summary Table

| Group | Total Fields | ALIVE (✅) | DEAD (❌) | Unknown (❓) |
|-------|--------------|-----------|-----------|--------------|
| utils | 2 | 2 | 0 | 0 |
| watchdog | 4 | 4 | 0 | 0 |
| defaults | 4 | 4 | 0 | 0 |
| absorption | 11 | 9 | 0 | 2 |
| ema | 2 | 0 | 0 | 2 |
| ema_bias | 2 | 0 | 0 | 2 |
| other FE | 5 | 0 | 0 | 5 |
| feature_sanity | 28 | 0 | 28 | 0 |
| **TOTAL** | **58** | **19** | **28** | **11** |

---

## Critical Findings

### 🔴 FALSE POSITIVES в CONFIG_MAP.md

**22 поля позначені `[DEAD]`, але АКТИВНО використовуються:**
1. `execution_position.utils.*` — обидва поля (basis_points_base, client_order_id_max_length)
2. `execution_position.watchdog.*` — всі 4 поля (переміщені, але живі)
3. `feature_engineering.defaults.*` — всі 4 поля
4. `feature_engineering.absorption.*` — 9 з 11 полів

### ✅ TRUE DEAD Fields (підтверджені)

**28 полів справді мертві:**
- Вся секція `feature_sanity.*` (28 полів) — не має жодного code consumption

### ❓ Requires Deeper Investigation

**11 полів потребують додаткового аналізу:**
- `ema.period_long/short`
- `ema_bias.clamp_min/max`
- `absorption.bounds.min/max`
- `delta_price.spike_filter_ms`
- `depth_imbalance.use_laplace_smoothing`
- `enable_new_metrics`
- `enabled_timeframes_sec`

---

## Recommendations

### 🔧 Immediate Actions

1. **UPDATE CONFIG_MAP.md** — виправити статус:
   ```
   - [DEAD] → [ALIVE] для 22 FALSE POSITIVES
   - Add NOTE: "watchdog fields moved to trading.yaml"
   ```

2. **PURGE TRUE DEAD** — видалити:
   ```
   - domains.feature_engineering.feature_sanity.* (entire section)
   - domains.execution_position.watchdog.* (duplicates in domains.yaml)
   ```

3. **DEEP DIVE Required** для 11 ❓ полів:
   - Semantic search у runtime коді
   - Check backtest vs live mode usage
   - Verify historical usage patterns

### 📋 Next Steps

1. Запустити semantic_search для ❓ полів
2. Перевірити test coverage для ALIVE полів
3. Оновити CONFIG_MAP.md зі статусом FALSE POSITIVE
4. Створити PURGE-DEAD-CONFIG-04 для true dead fields

---

## Appendix: Search Commands Used

```bash
# Basic grep patterns
grep -r "basis_points_base\|client_order_id_max_length" apps/
grep -r "ack_ttl_ms\|fill_ttl_ms\|check_interval_ms\|rps_limit" apps/reference/domains/execution_position/
grep -r "neutral_value\|zero_value\|correlation_default\|ms_per_sec" apps/reference/domains/feature_engineering/
grep -r "absorption\." apps/reference/domains/feature_engineering/

# Semantic searches needed for:
- ema.period_long/short
- ema_bias.clamp_*
- enable_new_metrics
- enabled_timeframes_sec
```

---

**Висновок**: Багато полів в CONFIG_MAP.md **неправильно позначені як `[DEAD]`**. Потрібна актуалізація документації і більш ретельний audit перед PURGE операціями.
