# REGIME Detector — Audit логіки (Detection + Confidence)

Дата аудиту: 2026-02-03  
Scope (SSOT):  
- `apps/reference/domains/regime_detector/regime_detector.py`  
- `config/aurora/regime.yaml`

Ціль: зафіксувати фактичні формули/умови, перш ніж змінювати “confidence” (впевненість) або додавати динаміку (decay/slope/momentum).

Нота про конфіг:
- `basis_tf_sec`, `uncertain_cutoff`, `models.*` — **безпосередньо використовуються** RegimeDetector.
- `liveness_factor` присутній в `regime.yaml`, але **не використовується** в `regime_detector.py` (ймовірно, його читає інший домен/guard).

---

## A) Архітектура Детекції (Detection Logic)

### A1. Вхідні дані та формат події

RegimeDetector слухає лише одну подію:
- `EVT:FEATURES_CALCULATED` (`handle_event`)

Очікувані поля в `event.pld`:
- `symbol` — рядок (обовʼязково)
- `ts` — timestamp у мс (обовʼязково, каститься в `int`)
- `tf_sec` — таймфрейм у секундах (обовʼязково для “bar-only” фільтра)
- `features` — `dict`, який містить:
  - `price` (обовʼязково; парситься у `Decimal`)
  - `sma_short` (опційно; якщо немає/0 — рахується з буфера)
  - `sma_long` (опційно; якщо немає/0 — рахується з буфера)
  - `high`, `low` (опційно; потрібні для “OHLC TR” у ATR; інакше може бути close-to-close ATR за конфігом)

### A2. BAR-ONLY SSOT (фільтрація таймфреймів)

Детектор працює **тільки на базовому барі**:
- Якщо `tf_sec == 0`: подія вважається tick-level і **мовчки ігнорується** (це НЕ data-quality drop).
- Якщо `tf_sec != basis_tf_sec`: подія ігнорується.

Параметри з `config/aurora/regime.yaml`:
- `basis_tf_sec: 300` (5m)

### A3. Data-quality gates (fail-closed)

До будь-яких розрахунків є перевірки:
- Немає `symbol` або `ts` → drop + return
- Немає `features` або `features` порожній/не dict → drop + return
- `ts` не каститься в `int` → drop + return
- Немає `features["price"]` → drop + return
- `price` не парситься/`price <= 0` → drop + return

#### Stale gate (bar TTL)

Є окремий gate “stale_features” **до оновлення буферів**:
- `ttl_ms` для барів береться з `config.system.market_data.bar_ttl_ms`, або дефолт `10000`
- Якщо `now_wall_ms - ts_ms > ttl_ms` → детектор:
  - **не оновлює буфери**
  - одразу емить `EVT:REGIME_DETECTED` з `regime="UNCERTAIN"`, `confidence=confidence_min`
  - `source_model="data_quality_gate"`

### A4. State Memory / “памʼять” в реалізації

У коді є **історична памʼять** на рівні індикаторів/буферів (пер-символ):
- `_price_buf[symbol]`: deque з останніми цінами для SMA та prev_close
- `_tr_buf[symbol]`: deque з True Range для ініціалізації ATR
- `_atr_last[symbol]`: останній ATR для рекурентного (Wilder) оновлення
- `_atr_buf[symbol]`: deque з ATR значеннями для baseline (SMA ATR)
- `_ticks_seen[symbol]`: лічильник барів (у коді названо ticks_seen)

Є також памʼять **лише для телеметрії/логів**, але не для decision logic:
- `_last_emitted_regime[symbol]`: використовується тільки для `changed` та логування
- `_last_full_ready[symbol]`: тільки для лога “warmup complete”

Важливо: **гістерезису для режимів немає** (нема “залишайся в режимі X, поки…” / нема “двох порогів” на вхід/вихід). Режим визначається на кожному базисному барі заново, на основі поточних значень індикаторів.

### A5. Пайплайн індикаторів

#### SMA

1) Якщо в `features` прийшли `sma_short`/`sma_long` і вони `> 0` → використовуються напряму.  
2) Інакше SMA рахується з `_price_buf` (тільки якщо буфер має достатню довжину).

Параметри з `config/aurora/regime.yaml`:
- `models.sma_trend.sma_short_period`
- `models.sma_trend.sma_long_period`

#### ATR (volatility pipeline, Wilder)

Увімкнено лише якщо `models.volatility.enabled: true`.

True Range (TR) рахується так:
- Якщо є `high`, `low` і є `prev_close`:
  - `TR = max(high - low, abs(high - prev_close), abs(low - prev_close))`
- Інакше, якщо є `prev_close` і `allow_close_to_close_atr=true`:
  - `TR = abs(close - prev_close)` (і додається note `atr_close_to_close`)
- Інакше:
  - додається drop `atr_missing_ohlc` (і потім режим буде fail-closed у UNCERTAIN)

ATR:
- Для першого ATR (коли `_atr_last` ще нема): потрібні `atr_period` TR значень,
  - `ATR_init = mean(TR[-atr_period:])`
- Далі Wilder smoothing:
  - `ATR_t = (ATR_{t-1} * (n - 1) + TR_t) / n`, де `n = atr_period`

ATR baseline:
- `ATR_baseline = mean(ATR[-atr_sma_length:])` (простий SMA по останніх ATR)

Параметри з `config/aurora/regime.yaml`:
- `models.volatility.atr_period`
- `models.volatility.atr_sma_length`
- `models.volatility.allow_close_to_close_atr`

### A6. Пріоритети режимів (Decision Order)

Код використовує пріоритети; перевірки йдуть **послідовно**, і наступний блок запускається тільки якщо `regime` все ще `UNCERTAIN`:

1) **Volatility** (якщо `enabled` і готовий ATR+baseline)
2) **Mean Reversion** (потрібні SMA)
3) **SMA Trend** (потрібні SMA + price filter)

Після цього є 2 “гейти”, які можуть **перезаписати будь-який режим на UNCERTAIN**:
- `data_drops` → `UNCERTAIN` (`source_model="data_quality_gate"`)
- `uncertain_cutoff` → `UNCERTAIN` (`source_model="uncertain_cutoff_gate"`)

### A7. Вихід (що саме емиться)

На кожному базисному барі (heartbeat) емиться `EVT:REGIME_DETECTED`, навіть якщо режим не змінився.

Ключові поля payload:
- `regime`: один з `TREND_UP`, `TREND_DOWN`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `MEAN_REVERSION`, `UNCERTAIN`
- `confidence`: `str(Decimal)` (наприклад `"0.77"`)
- `source_model`: `"sma_trend_v1" | "volatility_v2" | "mean_reversion_v2" | "data_quality_gate" | "uncertain_cutoff_gate"`
- `changed`: boolean (порівняння з `_last_emitted_regime[symbol]`, **не впливає** на decision logic)
- `warmup`: readiness-мапа (SMA/ATR готовність) + причини
- `data_quality`: `drops`/`notes`

---

## B) Математика Впевненості (Confidence Math)

Нотація:
- `conf_min = models.sma_trend.confidence_min`
- `conf_max = models.sma_trend.confidence_max`

Важливо: `conf_min/conf_max` беруться з **sma_trend** і застосовуються як загальні межі навіть для volatility та mean-reversion.

### B1. TREND_UP / TREND_DOWN (SMA Trend)

Умова TREND_UP:
- `sma_short_ready && sma_long_ready`
- `sma_short > sma_long`
- `price > sma_short`

Умова TREND_DOWN:
- `sma_short_ready && sma_long_ready`
- `sma_short < sma_long`
- `price < sma_short`

Confidence формула (`_calculate_confidence`):

```text
spread_ratio = (SMA_short - SMA_long) / SMA_long
raw = spread_ratio * models.sma_trend.confidence_multiplier
confidence = clamp(abs(raw), conf_min, conf_max)
```

де:
- `clamp(x, a, b) = min(max(x, a), b)`
- Якщо `SMA_long == 0` → повертається `conf_min`

Параметри з `config/aurora/regime.yaml`:
- `models.sma_trend.confidence_multiplier`
- `models.sma_trend.confidence_min`
- `models.sma_trend.confidence_max`

### B2. HIGH_VOLATILITY / LOW_VOLATILITY (Volatility v2)

Передумови (обовʼязково):
- `models.volatility.enabled == true`
- `atr_ready == true` (є `atr_val`)
- `atr_baseline_ready == true` (є `atr_baseline`)
- `atr_val > 0` і `atr_baseline > 0`

Базова метрика:

```text
vol_ratio = ATR / ATR_baseline
```

HIGH_VOLATILITY:
- Умова: `vol_ratio > threshold_multiplier`
- Confidence:

```text
excess = vol_ratio - threshold_multiplier
confidence = min(conf_max, conf_min + excess * high_vol_confidence_multiplier)
```

LOW_VOLATILITY:
- Умова: `vol_ratio < low_vol_multiplier`
- Confidence:

```text
calm = low_vol_multiplier - vol_ratio
confidence = min(conf_max, conf_min + calm * low_vol_confidence_multiplier)
```

Параметри з `config/aurora/regime.yaml`:
- `models.volatility.threshold_multiplier`
- `models.volatility.low_vol_multiplier`
- `models.volatility.high_vol_confidence_multiplier`
- `models.volatility.low_vol_confidence_multiplier`

### B3. MEAN_REVERSION (Mean Reversion v2)

Передумови:
- `regime == "UNCERTAIN"` (тобто volatility не спрацювала або не готова)
- `sma_short_ready && sma_long_ready`
- `sma_short > 0 && sma_long > 0 && price > 0`

Метрики:

```text
sma_spread = abs(SMA_short - SMA_long) / SMA_long
dev_short  = abs(price - SMA_short) / SMA_short
dev_long   = abs(price - SMA_long) / SMA_long
```

Умова режиму:
- `sma_spread < threshold`
- `dev_short < threshold`
- `dev_long < threshold`

Confidence:

```text
tightness = threshold - max(sma_spread, dev_short, dev_long)
confidence = min(conf_max, conf_min + tightness * mean_reversion.confidence_multiplier)
```

Параметри з `config/aurora/regime.yaml`:
- `models.mean_reversion.threshold`
- `models.mean_reversion.confidence_multiplier`

### B4. Post-gates: Data drops та Uncertain cutoff

1) Якщо накопичились `data_drops` → режим примусово:
```text
regime = "UNCERTAIN"
confidence = conf_min
source_model = "data_quality_gate"
```

2) Якщо режим не UNCERTAIN, але `confidence < uncertain_cutoff` → демоут:
```text
regime = "UNCERTAIN"
confidence = conf_min
source_model = "uncertain_cutoff_gate"
```

Параметр з `config/aurora/regime.yaml`:
- `uncertain_cutoff`

---

## C) Аналіз “Сліпих Зон” (Gap Analysis)

### C1. Чи є похідна/нахил метрик (slope)?

Ні. У decision logic **немає**:
- `dATR/dt`, `d(vol_ratio)/dt`, “ATR is rising/falling”
- “momentum” або будь-якого аналізу знаку/швидкості зміни показників

Є лише:
- згладжування ATR через Wilder (використовує попередній ATR) та baseline через SMA, але це **не slope**, а фільтрація/інерція.

### C2. Чи є механізми зниження впевненості з часом (decay)?

Ні. Confidence — це **чиста функція поточного бару** (точніше: поточних індикаторів, які самі вже містять історію), без:
- експоненційного/лінійного decay з часом “перебування” в режимі
- penalty за тривалість/вік сигналу
- вимоги повторного підтвердження (N з M барів)

### C3. Чому Confidence може “застрягати” на 0.95 при спаді волатильності?

Причини прямо з формул:

1) **Сатурація до `conf_max`**  
Volatility confidence лінійно росте зі “запасом” від порогу і дуже швидко доходить до стелі.

Для поточного конфігу (`conf_min=0.5`, `conf_max=0.95`):
- HIGH_VOL: `conf = min(0.95, 0.5 + (vol_ratio - 1.5) * 2.0)`
  - досягнення стелі: `(vol_ratio - 1.5) * 2.0 >= 0.45` → `vol_ratio >= 1.725`
- LOW_VOL: `conf = min(0.95, 0.5 + (0.6 - vol_ratio) * 3.0)`
  - досягнення стелі: `(0.6 - vol_ratio) * 3.0 >= 0.45` → `vol_ratio <= 0.45`

Тобто навіть якщо волатильність падає, але `vol_ratio` ще ≥ 1.725, confidence лишається 0.95. Код не враховує напрям (падає/росте), тільки рівень відносно порога.

2) **ATR_baseline має інерцію**  
Навіть якщо ATR починає падати, baseline (SMA по ATR) може падати повільніше/швидше, і `ATR/ATR_baseline` може довго залишатися високим.

3) **Нема hysteresis / “exit threshold”**  
Пороги одні й ті самі для входу/виходу. Якщо ви “високо над порогом”, то поки не впадете нижче нього, логіка продовжить класифікацію як HIGH_VOLATILITY (і confidence буде визначатися лише поточним `excess`).

Аналогічний ефект можливий і в SMA-тренді:
- `confidence` сатурується на 0.95, коли `abs((SMA_short - SMA_long) / SMA_long) * 40.0 >= 0.95` → спред приблизно ≥ 2.375%.
Поки SMA ще розʼїхані, навіть якщо тренд “гасне”, confidence може залишатися вгорі.

### C4. Додаткові “сліпі зони”/нюанси, які впливають на рішення

- Volatility режими взагалі **не можуть** активуватися, поки не готовий `atr_baseline` (warmup може бути довгим при великих `atr_period/atr_sma_length`).
- В “сірій зоні” `low_vol_multiplier <= vol_ratio <= threshold_multiplier` volatility блок нічого не робить, і логіка падає в MR/trend (за наявності SMA). Це може створювати часті переключення при коливанні навколо порогів.
- Якщо `allow_close_to_close_atr=false` і немає OHLC → ставиться drop `atr_missing_ohlc`, і режим **в кінці** буде примусово UNCERTAIN (fail-closed). З `allow_close_to_close_atr=true` (як у конфігу) це перетворюється на note і режим може детектитись.

---

## D) Висновок для Патчу

### D1. Підтвердження щодо “Momentum/Slope” волатильності

У `apps/reference/domains/regime_detector/regime_detector.py` **немає** змінної або логіки, яка:
- явно обчислює slope/derivative `ATR` чи `vol_ratio`,
- або знижує confidence через “погіршення динаміки” (decay),
- або тримає режим з гістерезисом/памʼяттю переходів.

Є лише інерція індикаторів (Wilder ATR + SMA baseline), але це не “momentum” як сигнал для деградації.

### D2. Імплікації для дизайну патчу

Якщо ціль — щоб confidence деградувала, коли волатильність починає “згасати” (навіть якщо рівень ще вище порога), то в поточній архітектурі потрібно додати один із механізмів:
- slope term: `d(vol_ratio)/dt` або `d(ATR)/dt` (порівняння з попереднім баром)
- decay: зменшення confidence як функції часу/барів “після піку”
- hysteresis: різні пороги на вхід/вихід з HIGH_VOL/LOW_VOL
- persistence rules: вимога N послідовних підтверджень або cooldown на зміни режиму

Поточний код є “level-based” і не містить “динамічної деградації” сигналу.
