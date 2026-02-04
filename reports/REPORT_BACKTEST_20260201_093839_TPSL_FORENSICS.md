# REPORT — Backtest run_id=20260201_093839 (Aurora TP/SL + market_regime forensics)

**Scope / contract**
- Цель: дать проверяемое объяснение, откуда в `intents[].why` берётся строка `tpsl:... tp_rr=4.00 sl_pct≈0.0075`, как формируется `market_regime`, и почему именно такие числа видны в артефакте.
- Политика: **ничего не додумывать**. Где нет артефактов/SSOT — явно помечаю **NOT FOUND**.

**Primary artifact**
- `reports/backtests/backtest_20260201_093839.json`

---

## 1) Источник `why.tpsl` и расчёт `tp_rr/sl_pct` (и почему HIGH_VOLATILITY показывает 4.00/0.0075)

### 1.1 Где формируется строка `tpsl:...` (точка истины)
Строка для `intents[].why` создаётся в обработчике Aurora на этапе формирования payload события `EVT:STRATEGY_SIGNAL_PRODUCED`.

**Code**: `apps/reference/domains/decision_making/aurora_handler.py`
- `_compute_regime_tpsl(...)` → считает stop/target + `tpsl_ctx`
- `_apply_tpsl_guardrails(...)` → применяет clamp/валидации
- дальше строится `tpsl_why = f"tpsl:regime=... sl_pct=... tp_rr=..."` и добавляется в `why_chain`

Ключевой фрагмент (смысл):
- `sl_pct` в why берётся из `tpsl_ctx['sl_pct_eff']`
- `tp_rr` в why берётся из `tpsl_ctx['tp_rr_eff']` (для `pct_mult`) или `tpsl_ctx['rr']` (для `atr`)

### 1.2 Формулы в режиме `pct_mult`
**Code**: `apps/reference/domains/decision_making/aurora_handler.py` → `_compute_tpsl_pct_mult(...)`

В `pct_mult` используется следующая математика:
- $sl\_pct\_{eff\_pre} = sl\_pct\_{base} \times sl\_mult[regime]$
- $tp\_rr\_{eff\_pre} = tp\_low\_ratio\_{base} \times tp\_mult[regime]$
- $tp\_dist\_pct = sl\_pct\_{eff\_pre} \times tp\_rr\_{eff\_pre}$

И затем по стороне:
- BUY: `stop = entry*(1-sl_pct)`; `target = entry*(1+tp_dist_pct)`
- SELL: `stop = entry*(1+sl_pct)`; `target = entry*(1-tp_dist_pct)`

### 1.3 Guardrails: clamp RR/SL (и важный нюанс телеметрии)
**Code**: `apps/reference/domains/decision_making/aurora_handler.py` → `_apply_tpsl_guardrails(...)`

Guardrails делают:
- clamp SL-дистанции в диапазон `[min_sl_pct, max_sl_pct]` (перестраивают `stop_price`)
- считают текущий RR как `current_rr = tp_dist_pct / sl_dist_pct`
- clamp RR в диапазон `[min_tp_rr, max_tp_rr]` (перестраивают `target_price`)
- после clamp записывают:
  - `tpsl_ctx['sl_pct_eff'] = sl_dist_pct` (POST-clamp)
  - `tpsl_ctx['rr_eff'] = current_rr` (POST-clamp)

**НЮАНС (корень путаницы):**
- `tpsl_ctx['tp_rr_eff']` (который рассчитан как `tp_low_ratio_base * tp_mult`) **НЕ обновляется после clamp RR**.
- строка `why` печатает **`tp_rr_eff`**, а не **`rr_eff`**.

Итог: **в `why` может стоять `tp_rr=4.00`, даже если реальный RR по stop/target уже зажат до 3.00**.

### 1.4 Проверка на артефакте: `why` говорит 4.00, но фактически RR=3.00
Я проверил напрямую по артефакту: вычислил фактический RR из цен ордера/stop/target:

$$ rr\_{actual} = \frac{|target-entry|/entry}{|entry-stop|/entry} $$

Результат для `HIGH_VOLATILITY` (первые примеры):
- `why.tpsl` содержит `tp_rr=4.00`
- **фактический `rr_actual` стабильно 3.00**
- `sl_pct` совпадает (0.0075)

Мини-таблица (репрезентативные intent’ы):

| market_regime | rid | side | why.tpsl | sl_pct_actual | rr_actual |
|---|---|---:|---|---:|---:|
| LOW_VOLATILITY | aurora_BTCUSDT_1684036500000 | BUY | tpsl:regime=LOW_VOLATILITY mode=pct_mult sl_pct=0.0037 tp_rr=2.00 | 0.003750 | 2.000 |
| TREND_UP | aurora_BTCUSDT_1684509600000 | BUY | tpsl:regime=TREND_UP mode=pct_mult sl_pct=0.0055 tp_rr=1.25 | 0.005500 | 1.250 |
| TREND_DOWN | aurora_BTCUSDT_1685508600000 | SELL | tpsl:regime=TREND_DOWN mode=pct_mult sl_pct=0.0055 tp_rr=1.25 | 0.005500 | 1.250 |
| HIGH_VOLATILITY | aurora_BTCUSDT_1684068000000 | BUY | tpsl:regime=HIGH_VOLATILITY mode=pct_mult sl_pct=0.0075 tp_rr=4.00 | 0.007500 | 3.000 |

**Вывод по п.1:**
- `sl_pct=0.0075` — реально использованный SL (post-clamp).
- `tp_rr=4.00` в why — **pre-clamp произведение** `tp_low_ratio_base * tp_mult[HIGH_VOLATILITY]`.
- Реальный RR по ценам **зажат до 3.00** (см. `rr_actual`).

### 1.5 Почему именно clamp до 3.00
По умолчанию `max_tp_rr=3.0` задан в модели конфигурации:

**Code**: `apps/reference/config_models.py` → `RegimeTpSlConfig`
- `max_tp_rr: float = 3.0` (clamp down if above)

И в рантайме guardrails берут значение так:
- `max_tp_rr = Decimal(str(getattr(regime_tpsl_cfg, 'max_tp_rr', 3.0)))`

Т.е. если в effective config не выставляли `max_tp_rr > 3.0`, RR будет зажат до 3.0, но why может продолжать печатать 4.0.

---

## 2) Где берётся `market_regime` (детектор, фичи, timeframe, пороги)

### 2.1 Детектор режимов (BAR-only SSOT)
**Code**: `apps/reference/domains/regime_detector/regime_detector.py`

Ключевое:
- Детектор слушает `EVT:FEATURES_CALCULATED`.
- **BAR-only фильтр**:
  - игнорирует `tf_sec == 0` (tick)
  - игнорирует любой `tf_sec != basis_tf_sec`

`basis_tf_sec` берётся из конфигурации (см. ниже) и равен 300 → режим считается на **5m барах**.

### 2.2 Модели и приоритеты определения режима
**Code**: `apps/reference/domains/regime_detector/regime_detector.py`

Приоритеты:
1) Volatility (volatility_v2): если `atr_ready` и `atr_baseline_ready`:
   - `vol_ratio = atr_val / atr_baseline`
   - если `vol_ratio > threshold_multiplier` → `HIGH_VOLATILITY`
   - если `vol_ratio < low_vol_multiplier` → `LOW_VOLATILITY`
2) Mean reversion (mean_reversion_v2): если SMAs готовы и отклонения меньше `threshold`.
3) SMA trend:
   - `TREND_UP` если `sma_short > sma_long` и `price > sma_short`
   - `TREND_DOWN` если `sma_short < sma_long` и `price < sma_short`

Потом применяется `uncertain_cutoff`: если `confidence < cutoff`, режим демотится в `UNCERTAIN`.

### 2.3 Конфиг порогов и таймфрейма
**Config**: `config/aurora/regime.yaml`
- `basis_tf_sec: 300`
- `uncertain_cutoff: 0.35`
- volatility:
  - `atr_period: 1`, `atr_sma_length: 10`
  - `threshold_multiplier: 2.0` (HIGH)
  - `low_vol_multiplier: 0.5` (LOW)

---

## 3) Как применяется YAML для BTCUSDT (loader/merge/effective config, и что с `timeframe_sec: null`)

### 3.1 Loader/merge: какие файлы участвуют
**Code**: `apps/reference/config_loader.py`

`ConfigLoader.load_config()`:
1) грузит `system.yaml`, `trading.yaml`, `regime.yaml`, `domains.yaml`
2) проверяет дубликаты leaf-path’ов (`_fail_on_duplicate_paths`)
3) мерджит в `merged_config` через `deep_merge(...)`
4) отдельно подмешивает SSOT:
   - `instruments.yaml` → `merged_config['instruments']`
   - `strategies.yaml` → `merged_config['strategies_registry']`
5) по assignments из `strategies.yaml` грузит профили:
   - `config/aurora/strategies/<strategy_id>.yaml`
   - кладёт в `merged_config['strategies'][strategy_id]`

### 3.2 Effective config на момент run_id=20260201_093839
**NOT FOUND** в артефакте.

Проверено:
- `backtest_20260201_093839.json` содержит `config_snapshot`, но там только 3 ключа:
  - `trading_mode`
  - `trading.backtest`
  - `trading.execution`
- в артефакте **нет** `strategies.*`, **нет** `strategies_registry.assignments`, **нет** `domains`, **нет** `regime`.

Следствие:
- из текущего артефакта невозможно доказательно извлечь значения:
  - `exit.sl_pct`
  - `take_profit.tp_low_ratio`
  - `exit.regime_tpsl.tp_mult/sl_mult`
  - `exit.regime_tpsl.max_tp_rr` (override)

Если нужно «100% factual effective config», требуется либо:
- запись `git sha`/`config hash` внутри отчёта (её нет), либо
- отдельный артефакт снапшота `resolved_config` (в этой версии отчёта отсутствует).

### 3.3 Что значит `timeframe_sec: null`
- Для стратегии Aurora глобальный `strategies.aurora.timeframe_sec` **обязателен**.
  - **Code**: `apps/reference/domains/decision_making/aurora_handler.py` → `_load_config()`
  - если отсутствует → `ConfigContractError`
- Пер-символьный `strategies.aurora.assets.<SYM>.timeframe_sec` является `Optional[int]` (может быть `null`).
  - **Model**: `apps/reference/config_models.py` → `AuroraInstrumentConfig.timeframe_sec: Optional[int] = None`
  - В loader’е логика SSOT по `timeframe_sec` (TASK23B) применяется **только** для назначений `mean_reversion`.
    - **Code**: `apps/reference/config_loader.py` → `_apply_timeframe_sec_ssot_precedence()`

---

## 4) Валидаторы/модели: fail-closed vs clamp, silent fallback

### 4.1 Pydantic-модель regime TP/SL
**Code**: `apps/reference/config_models.py` → `RegimeTpSlConfig`
- `extra='forbid'` → неизвестные поля ломают загрузку (fail-fast)
- `validate_default_keys` требует ключ `DEFAULT` в словарях (`sl_mult/tp_mult` либо `sl_k_atr/rr_by_regime`)
- Guardrails имеют дефолты прямо в модели:
  - `min_sl_pct=0.003`, `max_sl_pct=0.06`
  - `min_tp_rr=0.3`, `max_tp_rr=3.0`
  - `min_dist_bps=15`

### 4.2 Fail-closed входные параметры для `pct_mult`
**Code**: `apps/reference/domains/decision_making/aurora_handler.py` → `_compute_tpsl_pct_mult()`
- Если `exit.sl_pct is None` → возвращает `None` (TP/SL не инжектится)
- Если `take_profit.tp_low_ratio is None` → возвращает `None`

Это fail-closed именно для инжекта TP/SL (не «тихий дефолт»).

### 4.3 Silent fallback
Есть слой «совместимости»:
- В guardrails значения берутся через `getattr(..., default)`.
- Это важно, если `regime_tpsl_cfg` приходит не как `RegimeTpSlConfig` (например, мок/старый объект).

---

## 5) Воспроизведение чисел из отчёта: 3–5 примеров и как они следуют из кода

Ключевой факт: в артефакте `why.tpsl` печатает:
- `sl_pct` = POST-clamp `sl_pct_eff`
- `tp_rr` = PRE-clamp `tp_rr_eff` (pct_mult)

Поэтому:
- LOW_VOL / TREND_* совпадают (RR не требует clamp)
- HIGH_VOL показывает 4.00, но фактически RR=3.00 (clamp по max_tp_rr)

См. таблицу в секции 1.4 (она построена из реальных `order.price/stop_price/target_price`).

---

## 6) Итог: причины `tp_rr=4.0`, контрольные переменные для WR, и что именно чинить

### 6.1 Причины появления `tp_rr=4.00` в `why`
Фактическая причина в этом run:
- `tp_rr=4.00` — это **расчётный** `tp_rr_eff = tp_low_ratio_base * tp_mult[HIGH_VOLATILITY]`.
- Далее guardrails зажимают реальный RR до `max_tp_rr` (скорее всего дефолт `3.0`).
- Почему-строка остаётся с 4.00, потому что она выводит `tp_rr_eff`, а не `rr_eff`.

### 6.2 Что контролировать, чтобы это влияло на WR (и было прозрачно)
1) `exit.regime_tpsl.max_tp_rr`
   - если хотите реальный RR=4, это значение должно быть ≥ 4.
2) Формирование `why`
   - чтобы аудит не вводил в заблуждение, `tp_rr` в why должен отражать **post-clamp** `rr_eff`.
3) `exit.sl_pct` и `exit.regime_tpsl.sl_mult[regime]`
   - напрямую задают SL дистанцию.
4) `take_profit.tp_low_ratio` и `exit.regime_tpsl.tp_mult[regime]`
   - задают расчётный RR (до clamp).

### 6.3 NOT FOUND (что именно не удалось доказать из артефакта)
- Effective config (resolved_config) для BTCUSDT на момент run_id=20260201_093839.
- Конкретные значения `tp_low_ratio_base`, `tp_mult[HIGH_VOLATILITY]`, `max_tp_rr` (override).

### 6.4 Рекомендация (если хотите, могу сделать PR в рабочей копии)
Минимальная правка для честной телеметрии:
- В `apps/reference/domains/decision_making/aurora_handler.py` в строке `tpsl_why` печатать `rr_eff` (post-clamp), а не `tp_rr_eff`.
  - Например: `tp_rr={tpsl_ctx.get('rr_eff', tpsl_ctx.get('tp_rr_eff', ...)):.2f}`.

Это не меняет торговую логику, но убирает «ложные 4.00» при clamp.
