# CONFIDENCE-REGIME-AUDIT-001

Цель: собрать SSOT-пакет по «confidence режима»: где считается, как сериализуется/передаётся, где влияет на решения (гейты), какие пороги управляют поведением, какие есть тесты и какие остаются пробелы.

Важное ограничение: навигация contract-first (registry-first). Поэтому исходная точка — verb registry.

---

## 0) Артефакты (сырые сканы)

Сохранённые результаты `rg`:
- reports/CONFIDENCE_REGIME_AUDIT_001_artifacts/rg_confidence.txt
- reports/CONFIDENCE_REGIME_AUDIT_001_artifacts/rg_regime_detected.txt
- reports/CONFIDENCE_REGIME_AUDIT_001_artifacts/rg_regime_labels.txt
- reports/CONFIDENCE_REGIME_AUDIT_001_artifacts/rg_hysteresis_inertia.txt

---

## 1) SSOT: verb → owner → schema

**SSOT-источник**: apps/reference/dictionaries/verb_registry_v1.yaml

- EVT:REGIME_DETECTED объявлен как `owner: regime_detector` и указывает на schema-файл.
  - См. apps/reference/dictionaries/verb_registry_v1.yaml#L241-L250

Следствие (инвариант): любые контрактные изменения payload для REGIME_DETECTED должны начинаться с verb registry и schema (в owner-домене).

---

## 2) Контракт события: EVT:REGIME_DETECTED (payload)

**Schema SSOT**: apps/reference/domains/regime_detector/schemas/regime_detected_v1.json

Ключевые поля:
- `regime`: enum `TREND_UP|TREND_DOWN|MEAN_REVERSION|HIGH_VOLATILITY|LOW_VOLATILITY|UNCERTAIN`
  - apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L20-L31
- `confidence`: строка (string-encoded Decimal) в диапазоне [0..1]
  - apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L32-L36
- `source_model`: строка-идентификатор модели/правила
  - apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L37-L42
- `warmup`: `full_ready`, `ticks_seen`, `ready{...}`, `reasons[]`
  - apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L43-L60
- `data_quality`: `drops[]`, `notes[]`
  - apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L61-L76
- required: `ts, symbol, regime, confidence, source_model`
  - apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L78-L78

⚠️ Наблюдение о дрейфе/несостыковке:
- schema описывает `ts` как «microseconds», но в producer коде используется `ts_ms = int(ts)` и тесты подают `now_ms` (миллисекунды).
  - producer: apps/reference/domains/regime_detector/regime_detector.py#L188-L246
  - тест: tests/runtime/test_task24_regime_detector_correctness.py#L74-L109

---

## 3) Статический аудит: «где живёт confidence» (таблица)

| Где | Что (поле/сигнал) | Роль | Что делает | Ссылки |
|---|---|---|---|---|
| apps/reference/dictionaries/verb_registry_v1.yaml | `EVT:REGIME_DETECTED → owner/schema` | SSOT/контракт | Определяет owner и schema | apps/reference/dictionaries/verb_registry_v1.yaml#L241-L250 |
| apps/reference/domains/regime_detector/schemas/regime_detected_v1.json | `confidence` (string Decimal [0..1]) | SSOT/контракт | Тип/диапазон, обязательность | apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L32-L36 |
| apps/reference/domains/regime_detector/regime_detector.py | `_calculate_confidence()` (SMA spread) | compute | confidence = abs((sma_short-sma_long)/sma_long * multiplier), bounded [min,max] | apps/reference/domains/regime_detector/regime_detector.py#L120-L167 |
| apps/reference/domains/regime_detector/regime_detector.py | data-quality stale tick → `UNCERTAIN + conf_min` | gate (fail-closed) | При stale features не обновляет буферы, эмитит `UNCERTAIN` | apps/reference/domains/regime_detector/regime_detector.py#L188-L246 |
| apps/reference/domains/regime_detector/regime_detector.py | `data_drops` → `UNCERTAIN + conf_min` | gate (fail-closed) | Даже если модель нашла режим, любой drop принудительно сбрасывает в `UNCERTAIN` | apps/reference/domains/regime_detector/regime_detector.py#L380-L406 |
| config/aurora/regime.yaml | `models.sma_trend.confidence_*`, volatility multipliers, MR multipliers | config SSOT | Численные параметры формулы confidence | config/aurora/regime.yaml#L21-L41 |
| config/aurora/system.yaml | `system.market_data.tick_ttl_ms` | config SSOT | TTL для stale gate в producer | config/aurora/system.yaml#L14-L26 |
| apps/reference/domains/decision_making/decision_making.py | `on_regime()` сохраняет `confidence` по symbol | transmit/cache | Кеширует regime/warmup/confidence в `_per_symbol_regimes` | apps/reference/domains/decision_making/decision_making.py#L1906-L1933 |
| apps/reference/domains/decision_making/decision_making.py | warmup guard (`full_ready`) | gate (fail-closed) | Логирует и/или блокирует поведение при warmup=false | apps/reference/domains/decision_making/decision_making.py#L1934-L1956 |
| apps/reference/domains/decision_making/decision_making.py | `_warmup_gate_before_trade_intent()` | gate (fail-closed) | Требует regime warmup + FE warmup + свежие features + risk; reduce_only пропускает | apps/reference/domains/decision_making/decision_making.py#L2052-L2130 |
| config/aurora/domains.yaml | `arming.require_regime_warmup`, `directional_sanity.min_confidence` | config SSOT | Управляет warmup-логикой и минимальным порогом confidence | config/aurora/domains.yaml#L61-L84 |
| apps/reference/config_models.py | `DirectionalSanityConfig.min_confidence` семантика | config model SSOT | Явно: `max(regime_confidence, trend_confidence)` | apps/reference/config_models.py#L1060-L1086 |
| apps/reference/domains/decision_making/decision_making.py | `effective_conf = max(regime_confidence, trend_confidence)` | gate | Если `trend_dir` unknown или `effective_conf < min_conf`, то deny | apps/reference/domains/decision_making/decision_making.py#L2280-L2368 |
| schemas/decision_trace_emitted_v1.json | `regime_confidence` в форензик-событии | log/telemetry | Фиксирует what/why при DENY/ALLOW в directional gate | schemas/decision_trace_emitted_v1.json#L24-L44 |
| apps/reference/domains/strategies/plugins/aurora_builtin.py | слушает `EVT:REGIME_DETECTED` и форвардит | wiring | Подключает AuroraHandler к REGIME_DETECTED (если symbol назначен) | apps/reference/domains/strategies/plugins/aurora_builtin.py#L34-L72 |
| apps/reference/domains/decision_making/aurora_handler.py | `state.regime_confidence = float(event.get("confidence", 0.0))` | cache | Кеширует confidence для symbol | apps/reference/domains/decision_making/aurora_handler.py#L594-L624 |
| apps/reference/domains/decision_making/aurora_handler.py | asymm regime inertia (risk-off immediate, risk-on delayed) | gate | Меняет `regime_effective` по severity + confirm windows | apps/reference/domains/decision_making/aurora_handler.py#L352-L416 |
| config/aurora/strategies/aurora.yaml | `anti_churn.regime_inertia.*`, `severity_map` | config SSOT | Параметры inertia (confirm_window_sec, immediate_risk_off, severity_map) | config/aurora/strategies/aurora.yaml#L146-L191 |
| apps/reference/domains/feature_engineering/regime_mapping.py | `UNCERTAIN → None` | gate (fail-closed) | MR не торгует при неопределённом режиме | apps/reference/domains/feature_engineering/regime_mapping.py#L124-L146 |
| tests/domains/test_regime_detector.py | `confidence > 0.7/0.8` на clear-signal | test | Проверяет, что producer выдаёт высокий confidence в очевидных сценариях | tests/domains/test_regime_detector.py#L99-L112 |
| tests/runtime/test_task24_regime_detector_correctness.py | stale/data-gap → UNCERTAIN или low confidence | test | Проверяет fail-closed по stale_features и data gaps | tests/runtime/test_task24_regime_detector_correctness.py#L74-L110 |
| tests/config/test_regime_yaml_strict_validation.py | strict validation regime.yaml | test | extra='forbid', missing required keys → ValidationError | tests/config/test_regime_yaml_strict_validation.py#L1-L176 |
| tests/domains/decision_making/test_aurora_handler.py | caches confidence + warmup; inertia semantics | test | Проверяет on_regime_detected, warmup блокировки, confirm_window | tests/domains/decision_making/test_aurora_handler.py#L96-L126 |

---

## 4) Карта пайплайна: producer → событие → consumer → decision points

### 4.1 Producer

- Producer домен: `regime_detector`
- Подписка: `EVT:FEATURES_CALCULATED`
  - apps/reference/domains/regime_detector/regime_detector.py#L112-L116
- Эмиссия: `EVT:REGIME_DETECTED` с полями schema (`regime`, `confidence`, `warmup`, `data_quality`)
  - apps/reference/domains/regime_detector/regime_detector.py#L410-L429

### 4.2 Consumers / wiring

**DecisionMaking** (центральный consumer):
- `on_regime()` принимает `event.pld`, кладёт `confidence` в `_per_symbol_regimes[symbol]`.
  - apps/reference/domains/decision_making/decision_making.py#L1906-L1933
- Дальше значение участвует в directional sanity gate (см. ниже).

**AuroraHandler** (через aurora_builtin plugin):
- Плагин слушает `EVT:REGIME_DETECTED` и форвардит payload в AuroraHandler при условии SSOT assignment.
  - wiring: apps/reference/domains/strategies/plugins/aurora_builtin.py#L34-L72
- Handler кеширует `regime_confidence` и применяет inertia для `regime_effective`.
  - cache: apps/reference/domains/decision_making/aurora_handler.py#L594-L624
  - inertia: apps/reference/domains/decision_making/aurora_handler.py#L352-L416

**FeatureEngineering / MR mapping**:
- `map_to_flat_regime()` запрещает (fail-closed) торговлю MR при `UNCERTAIN` и/или отсутствии ATR%.
  - apps/reference/domains/feature_engineering/regime_mapping.py#L110-L146

---

## 5) Config SSOT: ключи, значения, где используются

### 5.1 Producer (regime_detector)

- SMA trend confidence параметры:
  - `models.sma_trend.confidence_multiplier: 20.0`
  - `models.sma_trend.confidence_min: 0.5`
  - `models.sma_trend.confidence_max: 0.95`
  - config: config/aurora/regime.yaml#L21-L31
  - использование: `_calculate_confidence()` apps/reference/domains/regime_detector/regime_detector.py#L142-L167

- Volatility confidence параметры:
  - `models.volatility.threshold_multiplier: 2.0`
  - `models.volatility.low_vol_multiplier: 0.5`
  - `models.volatility.high_vol_confidence_multiplier: 2.0`
  - `models.volatility.low_vol_confidence_multiplier: 3.0`
  - config: config/aurora/regime.yaml#L28-L37
  - использование: HIGH/LOW_VOL confidence apps/reference/domains/regime_detector/regime_detector.py#L332-L361

- Mean reversion confidence параметры:
  - `models.mean_reversion.threshold: 0.005`
  - `models.mean_reversion.confidence_multiplier: 100.0`
  - config: config/aurora/regime.yaml#L37-L40
  - использование: MR confidence apps/reference/domains/regime_detector/regime_detector.py#L365-L379

- Data-quality TTL:
  - `system.market_data.tick_ttl_ms: 2000`
  - config: config/aurora/system.yaml#L14-L26
  - использование: stale gate apps/reference/domains/regime_detector/regime_detector.py#L197-L246

### 5.2 DecisionMaking (гейты)

- Warmup gate toggle:
  - `domains.decision_making.arming.require_regime_warmup: true`
  - config: config/aurora/domains.yaml#L61-L67
  - использование: DecisionMaking init / поведение в `on_regime()` apps/reference/domains/decision_making/decision_making.py#L1934-L1943

- Directional sanity gate:
  - `domains.decision_making.directional_sanity.enabled: true`
  - `domains.decision_making.directional_sanity.min_confidence: 0.0`
  - config: config/aurora/domains.yaml#L70-L84
  - семантика min_confidence: apps/reference/config_models.py#L1060-L1086
  - использование: effective_conf comparison apps/reference/domains/decision_making/decision_making.py#L2338-L2368

### 5.3 Aurora anti-churn (inertia)

- `strategies.aurora.decision.anti_churn.regime_inertia.confirm_window_sec: 90`
- `strategies.aurora.decision.anti_churn.regime_inertia.immediate_risk_off: true`
- `strategies.aurora.decision.anti_churn.regime_inertia.severity_map: ...`
  - config: config/aurora/strategies/aurora.yaml#L146-L191
  - загрузка в runtime: apps/reference/domains/decision_making/aurora_handler.py#L240-L284
  - применение: apps/reference/domains/decision_making/aurora_handler.py#L352-L416

---

## 6) Формулы / эвристики confidence (producer)

### 6.1 SMA trend

Фактическая логика (псевдокод по _calculate_confidence):

```
if sma_long == 0:
  return conf_min
spread_ratio = (sma_short - sma_long) / sma_long
raw = spread_ratio * confidence_multiplier
confidence = clamp(abs(raw), conf_min, conf_max)
```

- Код: apps/reference/domains/regime_detector/regime_detector.py#L120-L167
- Параметры: config/aurora/regime.yaml#L21-L31

### 6.2 Volatility regimes

```
vol_ratio = atr / atr_baseline
if vol_ratio > threshold_multiplier:
  excess = vol_ratio - threshold_multiplier
  confidence = min(conf_max, conf_min + excess * high_vol_confidence_multiplier)
if vol_ratio < low_vol_multiplier:
  calm = low_vol_multiplier - vol_ratio
  confidence = min(conf_max, conf_min + calm * low_vol_confidence_multiplier)
```

- Код: apps/reference/domains/regime_detector/regime_detector.py#L332-L361
- Параметры: config/aurora/regime.yaml#L28-L37

### 6.3 Mean reversion

```
threshold = mr.threshold
sma_spread = abs(sma_short - sma_long) / sma_long
dev_short = abs(price - sma_short) / sma_short
dev_long  = abs(price - sma_long) / sma_long

if sma_spread < threshold and dev_short < threshold and dev_long < threshold:
  tightness = threshold - max(sma_spread, dev_short, dev_long)
  confidence = min(conf_max, conf_min + tightness * mr.confidence_multiplier)
```

- Код: apps/reference/domains/regime_detector/regime_detector.py#L365-L379
- Параметры: config/aurora/regime.yaml#L37-L40

---

## 7) Инвентарь confidence gates (fail-open vs fail-closed) + риски оптимизма

### 7.1 Producer: data-quality (fail-closed)

- **stale_features**: немедленно эмитит `UNCERTAIN` и `confidence=conf_min`, не обновляя буферы.
  - apps/reference/domains/regime_detector/regime_detector.py#L188-L246
- **любой data_drops**: принудительно `UNCERTAIN`, даже если модель распознала режим.
  - apps/reference/domains/regime_detector/regime_detector.py#L380-L406

Риск оптимизма: низкий (fail-closed).

### 7.2 DecisionMaking: readiness/warmup gate (fail-closed)

- `_warmup_gate_before_trade_intent()` блокирует новые входы (reduce_only разрешён), если нет:
  - portfolio,
  - свежих features,
  - risk,
  - per-symbol regime warmup full_ready,
  - features warmup full_ready.
  - apps/reference/domains/decision_making/decision_making.py#L2052-L2130

Риск оптимизма: низкий (fail-closed). Цена: потенциальная «лишняя» блокировка при неполном warmup.

### 7.3 DecisionMaking: directional sanity gate (смешанная логика)

- Использует `effective_conf = max(regime_confidence, trend_confidence)`.
  - apps/reference/domains/decision_making/decision_making.py#L2338-L2368
- Deny при:
  - `trend_dir` не подтверждён,
  - или `effective_conf < min_confidence`.

Риск оптимизма:
- Если `min_confidence` в config равен 0.0, то ветка `effective_conf < min_conf` фактически выключена, и confidence перестаёт ограничивать ALLOW (остаётся только требование определённого тренда).
  - config: config/aurora/domains.yaml#L70-L84

### 7.4 AuroraHandler: inertia (не про confidence напрямую, но про «использование режима в решениях»)

- Risk-off (более «плохой») режим — сразу.
- Risk-on (более «хороший») — только после confirm_window_sec.
  - runtime: apps/reference/domains/decision_making/aurora_handler.py#L352-L416
  - config: config/aurora/strategies/aurora.yaml#L146-L191

Риск оптимизма: снижает «дергание» и ранние переключения в risk-on.

### 7.5 MR mapping: fail-closed

- `UNCERTAIN → None` (MR не должен торговать)
- `MEAN_REVERSION` без ATR% → None
  - apps/reference/domains/feature_engineering/regime_mapping.py#L110-L146

---

## 8) Тесты: что гарантируют и где пробелы

### 8.1 Producer correctness

- Clear-signal → высокий confidence:
  - TREND_UP confidence > 0.7: tests/domains/test_regime_detector.py#L99-L112
  - TREND_DOWN confidence > 0.7: tests/domains/test_regime_detector.py#L150-L167
  - MEAN_REVERSION confidence > 0.8: tests/domains/test_regime_detector.py#L213-L227

- Data-quality fail-closed:
  - stale_features → UNCERTAIN: tests/runtime/test_task24_regime_detector_correctness.py#L74-L110
  - data gap → UNCERTAIN или low confidence: tests/runtime/test_task24_regime_detector_correctness.py#L185-L201

### 8.2 Config SSOT strictness

- `regime.yaml` extra keys → ValidationError (extra='forbid')
- missing required keys → ValidationError
  - tests/config/test_regime_yaml_strict_validation.py#L1-L176

### 8.3 Consumer correctness (AuroraHandler)

- Кеширование confidence + warmup:
  - tests/domains/decision_making/test_aurora_handler.py#L96-L126
- Inertia semantics:
  - risk-off immediate / risk-on delayed / same-severity buffer
  - tests/domains/decision_making/test_aurora_handler.py#L330-L382

### 8.4 Пробелы (рекомендовано добавить в отдельной задаче)

- Контрактная согласованность `ts` vs `ts_ms` между schema/producers/consumers (сейчас есть явный дрейф).
  - schema: apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L6-L18
  - producer: apps/reference/domains/regime_detector/regime_detector.py#L188-L246
  - consumer: apps/reference/domains/decision_making/aurora_handler.py#L602-L610
- Явные тесты на то, что consumer корректно читает `confidence` как строку Decimal (а не только float), и что schema-валидатор не ломается на строковом типе.

---

## 9) Минимальный план логирования/сборки данных для калибровки confidence

Цель: собрать достаточно данных, чтобы валидировать «confidence ≈ вероятность правильного режима» (калибровка) и увидеть влияние гейтов.

### 9.1 Что логировать (минимум)

1) Все события EVT:REGIME_DETECTED в JSONL (как есть, без преобразований), ключи строго по schema.
- schema: apps/reference/domains/regime_detector/schemas/regime_detected_v1.json#L1-L86

2) Все EVT:DECISION_TRACE_EMITTED (форензика directional sanity) — только когда gate_outcome=DENY (или sampled).
- schema: schemas/decision_trace_emitted_v1.json#L1-L120

3) (Опционально) EVT:STRATEGY_DECISION_BLOCKED для AuroraHandler при warmup/cost gate — чтобы видеть блокировки pipeline.
- emitter: apps/reference/domains/decision_making/aurora_handler.py#L560-L592

### 9.2 Пример JSONL payload (реальные ключи)

EVT:REGIME_DETECTED (пример):

```json
{"ts": 1700000000123, "symbol": "BTCUSDT", "regime": "TREND_UP", "confidence": "0.77", "source_model": "sma_trend_v1", "warmup": {"full_ready": true, "ticks_seen": 1234, "ready": {"sma_short": true, "sma_long": true, "atr": true, "atr_baseline": true}, "reasons": []}, "data_quality": {"drops": [], "notes": []}}
```

EVT:DECISION_TRACE_EMITTED (пример):

```json
{"symbol":"BTCUSDT","ts":1700000000123,"intent_side":"LONG","signal_score":0.42,"regime":"TREND_UP","regime_confidence":0.77,"trend_dir":"UP","delta_price":0.0012,"pm_norm_10s":0.1,"pm_norm_60s":0.2,"pm_norm_300s":0.3,"vol_pct_10s":0.0008,"vol_pct_60s":0.0011,"vol_pct_300s":0.0020,"gate_outcome":"ALLOW","deny_reason":null,"why":"ok"}
```

---

## 10) Быстрые выводы

- Confidence режима вычисляется эвристически в producer (SMA/ATR/MR) и **жёстко ограничивается** `[confidence_min, confidence_max]` (по конфигу).
- В pipeline есть несколько fail-closed гейтов, которые сильнее confidence: stale/data gaps → UNCERTAIN; readiness/warmup → блокировка новых входов.
- Directional sanity gate использует `max(regime_confidence, trend_confidence)`: это важная семантика SSOT для min_confidence.
- Обнаружен контрактный дрейф по полю времени (`ts` vs `ts_ms`, «microseconds» vs ms) — это отдельный риск для трассировки и калибровки.
