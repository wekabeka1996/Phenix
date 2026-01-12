# CONFIDENCE-REGIME-NORMALIZE-002 Report

## Огляд

Цей таск нормалізує формат події `EVT:REGIME_DETECTED` та впроваджує SNR-based confidence замість штучно завищених значень.

**Дата:** 2026-01-09
**Статус:** ✅ Завершено

---

## 1. Канонічний формат (Contract Changes)

### 1.1 Timestamp: `ts_ms`

| Поле | Тип | Опис |
|------|-----|------|
| `ts_ms` | `int` | **CANONICAL** - мілісекунди з epoch |
| `ts` | `int` | **DEPRECATED** - збережено для backward compatibility |

**Зміна:** `ts` (мікросекунди) замінено на `ts_ms` (мілісекунди).

### 1.2 Confidence: Float

| Було | Стало |
|------|-------|
| `confidence: string` (e.g., `"0.75"`) | `confidence: float` (e.g., `0.75`) |

**Зміна:** Confidence тепер є нативним float [0.0, 1.0], а не string-encoded Decimal.

---

## 2. SNR-Based Confidence (De-Optimistic)

### 2.1 Проблема

Раніше `confidence_min=0.5` штучно завищувало впевненість навіть для слабких сигналів:

```python
# OLD: Always >= 0.5, even for flat markets
bounded_confidence = max(abs(confidence), conf_min)  # conf_min=0.5
```

### 2.2 Нова логіка

**Signal-to-Noise Ratio (SNR):**

```python
# SNR = spread_ratio / noise
spread_ratio = abs(sma_short - sma_long) / sma_long
noise = max(atr_pct, cached_atr_pct, snr_noise_floor)
snr = spread_ratio / noise

# Sigmoid mapping
confidence = sigmoid(snr_sigmoid_a * (snr - snr_center))
# Then: confidence *= persistence_multiplier
```

**Параметри (config/aurora/regime.yaml):**

| Параметр | Значення | Опис |
|----------|----------|------|
| `snr_center` | 1.0 | SNR при якому confidence = 0.5 |
| `snr_sigmoid_a` | 2.0 | Крутизна сигмоїди |
| `snr_noise_floor` | 0.001 | Мінімальний шум (eps) |
| `persistence_window` | 5 | Вікно для стабільності знаку тренду |
| `persistence_min_ratio` | 0.6 | Мін. частка консистентних знаків |

### 2.3 Uncertain Cutoff

**Нове поле:** `global.uncertain_cutoff` (default: 0.25)

```yaml
global:
  uncertain_cutoff: 0.25
```

**Логіка:**
```python
if regime != "UNCERTAIN" and confidence < uncertain_cutoff:
    regime = "UNCERTAIN"
    data_notes.append(f"confidence_below_cutoff:{confidence:.3f}<{uncertain_cutoff}")
```

Це гарантує, що слабкі сигнали НЕ маскуються під TREND_UP/TREND_DOWN.

---

## 3. Зміни в файлах

### 3.1 Schema

**`apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`:**
- `ts` → `ts_ms` (canonical)
- `confidence: string` → `confidence: number`
- Додано deprecated `ts` field

### 3.2 Config Models

**`apps/reference/config_models.py`:**
- `SMARegimeModelConfig`: додано SNR параметри
- `MeanReversionRegimeModelConfig`: додано `snr_noise_floor`
- Новий клас `RegimeGlobalConfig` з `uncertain_cutoff`

### 3.3 Regime Detector

**`apps/reference/domains/regime_detector/regime_detector.py`:**
- Новий метод `_calculate_snr_confidence()`
- Новий метод `_get_persistence_multiplier()`
- Новий метод `_update_trend_sign()`
- Emit `ts_ms` + `ts` (backward compat)
- Emit `confidence` як float
- Uncertain cutoff logic

### 3.4 Config

**`config/aurora/regime.yaml`:**
- `confidence_min: 0.5` → `0.1` (REDUCED!)
- Додано `global.uncertain_cutoff: 0.25`
- Додано SNR параметри в `models.sma_trend`
- Додано `snr_noise_floor` в `models.mean_reversion`

### 3.5 Tests

**Оновлені:**
- `tests/domains/test_regime_detector.py`
- `tests/config/test_regime_yaml_strict_validation.py`
- `tests/runtime/test_task24_regime_detector_correctness.py`

**Нові тести:**
- `test_flat_low_vol_does_not_produce_high_trend_confidence`
- `test_strong_trend_produces_high_snr_confidence`
- `test_schema_compliance_ts_ms_and_float_confidence`
- `test_uncertain_cutoff_demotes_low_confidence_trend`
- `test_payload_contains_ts_ms_canonical`
- `test_confidence_is_float_not_string`
- `test_snr_parameters_have_defaults`
- `test_confidence_min_reduced_from_legacy`

---

## 4. Backward Compatibility

### 4.1 Consumers

Consumers повинні:
1. Читати `ts_ms` як канон
2. Fallback на `ts` якщо `ts_ms` відсутній (legacy)
3. Приймати `confidence` як float АБО string (для старих повідомлень)

**Приклад:**
```python
ts_ms = payload.get("ts_ms") or payload.get("ts")
confidence = float(payload.get("confidence", 0.0))
```

### 4.2 Producers

Producer (RegimeDetector) тепер емісить:
- `ts_ms` (canonical) + `ts` (deprecated, same value)
- `confidence` як float

---

## 5. Ризики та наступні кроки

### 5.1 Ризики

| Ризик | Severity | Mitigation |
|-------|----------|------------|
| Consumer не обробляє float confidence | Low | Backward compat: `float(str)` працює |
| SNR параметри не калібровані | Medium | Наступний таск: статистична калібровка |
| uncertain_cutoff занадто агресивний | Medium | Моніторинг; може потребувати tuning |

### 5.2 Наступні кроки

1. **Калібровка SNR параметрів:**
   - Аналіз історії: коли confidence відповідала прибуткам?
   - A/B тестування різних `snr_center` / `snr_sigmoid_a`

2. **Persistence Logic:**
   - Можливо замінити на Exponential Moving Sign
   - Враховувати час між змінами знаку

3. **Per-Symbol Tuning:**
   - Різні волатильності вимагають різних SNR параметрів

---

## 6. Верифікація

**Результати тестування:**

```
===== 141 passed, 13 skipped in 138.04s =====
```

Всі 141 тест пов'язаний з regime пройшов успішно.

Запустіть тести:

```bash
pytest -q tests/domains/test_regime_detector.py
pytest -q tests/runtime/test_task24_regime_detector_correctness.py
pytest -q tests/config/test_regime_yaml_strict_validation.py

# Повний набір:
pytest tests/ -k "regime" -v
```

---

## 7. Summary

| Before | After |
|--------|-------|
| `ts` (microseconds, inconsistent) | `ts_ms` (milliseconds, canonical) |
| `confidence: string` | `confidence: float` |
| `confidence_min: 0.5` (always optimistic) | `confidence_min: 0.1` + SNR-based |
| No uncertain cutoff | `uncertain_cutoff: 0.25` |

**Головна ціль досягнута:** Система більше не "впевнена завжди". Слабкі сигнали → UNCERTAIN або низька confidence.
