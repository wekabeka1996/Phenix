# 📄 Паспорт конфігурації: `config/aurora/regime.yaml`

Нотатка про контекст: у `apps/reference/domains/regime_detector/` зараз **немає** `types.py`; типи конфігів визначені в `apps/reference/config_models.py`, а контракт події — в `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`.

---

### `basis_tf_sec`
* **Type:** `int`
* **Logic Owner:** `regime_detector` (bar-only SSOT) + `decision_making` (liveness guard)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:69` (func: `__init__`); `apps/reference/domains/regime_detector/regime_detector.py:235` (func: `handle_event`); `apps/reference/domains/decision_making/aurora_handler.py:422` (func: `_check_regime_liveness`)
* **Mathematical Role:**
    > **Bar-only тактування.** Обробляються лише `EVT:FEATURES_CALCULATED` з `tf_sec == basis_tf_sec`, тік-події (`tf_sec=0`) ігноруються.  
    > **Liveness-вікно (fail-closed):** `max_delay_ms = basis_tf_sec * 1000 * liveness_factor`. Якщо heartbeat режиму не приходить довше цього вікна → блок торгівлі.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Рідше оновлення режиму (більший lag), довші «реальні» вікна SMA/ATR у секундах (`period_in_bars * basis_tf_sec`), але більш толерантний liveness (менше випадкових блоків через затримки).
    * 🔽 **Lower Value:** Частіші оновлення (менший lag), але більша чутливість до шуму; liveness-вікно стає коротшим → більше шансів fail-closed блокування при пропусках барів/чергах.
* **Invariant/Constraints:** `required`; **повинен бути > 0** (інакше RegimeDetector фактично перестане емiтити heartbeat, а DM заблокує торгівлю).

---

### `uncertain_cutoff`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (confidence gate)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:70` (func: `__init__`); `apps/reference/domains/regime_detector/regime_detector.py:494` (func: `handle_event`)
* **Mathematical Role:**
    > **Fail-closed демоут слабких режимів:** якщо `regime != "UNCERTAIN"` і `confidence < uncertain_cutoff` → примусово `regime="UNCERTAIN"`, `confidence=conf_min`, `source_model="uncertain_cutoff_gate"`.  
    > Це напряму впливає на downstream: `UNCERTAIN` зазвичай означає «не торгувати/консервативно» (див. DM docs).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Більше демоутів у `UNCERTAIN` → менше режимних «тверджень», менше угод/перемикань режимів, але більша ймовірність пропустити ранній тренд/волатильність.
    * 🔽 **Lower Value:** Більше «дозволених» режимів з нижчою впевненістю → швидша реакція, але ризик noisy regime changes та false-positive режимів.
* **Invariant/Constraints:** `0.0 <= value <= 1.0` (Pydantic: `apps/reference/config_models.py:3003`).

---

### `liveness_factor`
* **Type:** `int`
* **Logic Owner:** `decision_making` (Aurora handler safety gate)
* **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:420` (func: `_check_regime_liveness`); `apps/reference/config_models.py:3009` (Pydantic Field)
* **Mathematical Role:**
    > **Fail-closed safety guard** від «мертвого» режиму:  
    > `max_delay_ms = basis_tf_sec * 1000 * liveness_factor`. Якщо `delta_ms > max_delay_ms` → блок (NRR `NRR-REGIME-DETECTOR-DEAD`) + `EVT:STRATEGY_DECISION_BLOCKED`.  
    > Якщо heartbeat ще ніколи не приходив → блок (NRR `NRR-REGIME-NO-HEARTBEAT`).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Довше дозволене «мовчання» RegimeDetector → менше фальшивих блоків через затримки/черги, але довше можна торгувати на застарілому режимі (ризик).
    * 🔽 **Lower Value:** Агресивніше fail-closed блокування (швидше «вбиває» торгівлю при пропусках/зависаннях), зате менше шансів торгувати на stale regime.
* **Invariant/Constraints:** `value >= 1` (Pydantic). Фактичний fallback у коді: якщо конфіг недоступний → `basis_tf_sec=300`, `liveness_factor=3` (safe defaults).

---

### `hysteresis_bars`
* **Type:** `int`
* **Logic Owner:** `regime_detector` (stability / anti-churn)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:538` (func: `handle_event`)
* **Mathematical Role:**
    > **Підтвердження зміни режиму:** stable-режим оновлюється лише якщо `pending_regime` тримається `>= hysteresis_bars` послідовних basis-барів.  
    > Це змінює семантику `changed` у `EVT:REGIME_DETECTED` (бо емiтиться `stable_regime`, не raw).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Менше churn/перемикань, сильніше згладжування, але більший lag входу в новий режим (особливо при швидких розворотах).
    * 🔽 **Lower Value:** Швидші перемикання stable-режиму (може бути noisy), більше `changed=True` подій, більше downstream реакцій (фільтри/множники/закриття на flip).
* **Invariant/Constraints:** `1 <= value <= 10` (Pydantic: `apps/reference/config_models.py:3016`).

---

### `vol_slope_gate_enabled`
* **Type:** `int` *(boolean flag)*
* **Logic Owner:** `regime_detector` (HIGH_VOL “dying storm” gate)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:438` (func: `handle_event`)
* **Mathematical Role:**
    > Якщо увімкнено і raw-режим = `HIGH_VOLATILITY`, детектор рахує `vol_ratio_slope = EMA(span=3) - EMA(span=6)` по `vol_ratio = atr_val/atr_baseline`.  
    > При стійкому спаді (`vol_ratio_slope <= eps` протягом `confirm_bars`) → примусово `regime="UNCERTAIN"`, `source_model="slope_gate"`, `storm_rejected=True`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** *(true)* Більше випадків “HIGH_VOL rejected → UNCERTAIN” (консервативніше, менше торгових рішень у «затухаючих бурях»).
    * 🔽 **Lower Value:** *(false)* HIGH_VOL приймається без slope-перевірки (швидше входить у HIGH_VOL, але більше ризику «помилкового шторму» на піку/після піку).
* **Invariant/Constraints:** `bool`, default `true` (Pydantic: `apps/reference/config_models.py:3022`).

---

### `vol_slope_gate_eps`
* **Type:** `float`
* **Logic Owner:** `regime_detector`
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:445` (func: `handle_event`)
* **Mathematical Role:**
    > Поріг для slope gate: тригериться, якщо `vol_ratio_slope <= vol_slope_gate_eps` (після EMA3/EMA6).  
    > Чим більший `eps`, тим «вищий стандарт» для визнання, що шторм ще наростає.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Частіше відхиляє `HIGH_VOLATILITY` (бо навіть слабко-позитивний slope може не пройти) → більше `UNCERTAIN`.
    * 🔽 **Lower Value:** Рідше відхиляє `HIGH_VOLATILITY` (допускає нульовий/слабко-негативний slope) → більше HIGH_VOL режимів.
* **Invariant/Constraints:** `-0.1 <= value <= 0.1` (Pydantic: `apps/reference/config_models.py:3026`).

---

### `vol_slope_gate_confirm_bars`
* **Type:** `int`
* **Logic Owner:** `regime_detector`
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:447` (func: `handle_event`)
* **Mathematical Role:**
    > Кількість послідовних барів, коли `vol_ratio_slope <= eps`, потрібна щоб активувати slope gate. Реалізовано через лічильник `_slope_reject_count[symbol]`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Менше фальшивих відхилень HIGH_VOL (потрібна «стійка» деградація), але довший час до спрацювання захисту.
    * 🔽 **Lower Value:** Швидше гасить HIGH_VOL при першій ознаці затухання, але може бути надто агресивним (noisy rejects).
* **Invariant/Constraints:** `1 <= value <= 5` (Pydantic: `apps/reference/config_models.py:3030`).

---

### `models.sma_trend.sma_short_period`
* **Type:** `int`
* **Logic Owner:** `regime_detector` (SMA warmup + TREND detection)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:90` (func: `__init__`); `apps/reference/domains/regime_detector/regime_detector.py:331` (func: `handle_event`)
* **Mathematical Role:**
    > Довжина короткої SMA у **барах**. Якщо `features["sma_short"]` відсутня/0, обчислюється з буфера:  
    > `sma_short = mean(last sma_short_period prices)`.  
    > Впливає на готовність `warmup.ready["sma_short"]`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Більш згладжена SMA → менше шуму, але більший lag і довший warmup (потрібно більше барів).
    * 🔽 **Lower Value:** Швидша реакція, менший warmup, але більше шуму та частіші хибні перетини.
* **Invariant/Constraints:** `value >= 2` (Pydantic: `apps/reference/config_models.py:805`). Рекомендовано: `sma_short_period < sma_long_period` (логічний інваріант, не валідований явно).

---

### `models.sma_trend.sma_long_period`
* **Type:** `int`
* **Logic Owner:** `regime_detector`
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:91` (func: `__init__`); `apps/reference/domains/regime_detector/regime_detector.py:334` (func: `handle_event`)
* **Mathematical Role:**
    > Довжина довгої SMA у **барах**. Якщо `features["sma_long"]` відсутня/0:  
    > `sma_long = mean(last sma_long_period prices)`.  
    > Також виступає базою у трендовій впевненості та у MR-метриках (ділення на `sma_long`).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Стабільніший «якір» тренду → менше шуму, але значно більший lag та warmup; тренди фіксуються пізніше.
    * 🔽 **Lower Value:** Раніше бачить зміни, але більше whipsaw; якщо наблизити до short-періоду — різко росте churn.
* **Invariant/Constraints:** `value >= 5` (Pydantic: `apps/reference/config_models.py:806`). Бажано: `sma_long_period` істотно більший за `sma_short_period`.

---

### `models.sma_trend.confidence_multiplier`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (trend confidence calibration)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:177` (func: `_calculate_confidence`)
* **Mathematical Role:**
    > Масштабує трендовий «spread ratio»:  
    > `spread_ratio = (sma_short - sma_long) / sma_long`  
    > `confidence_raw = spread_ratio * confidence_multiplier`  
    > `confidence = clamp(abs(confidence_raw), confidence_min, confidence_max)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Швидше насичує confidence до `confidence_max` → менше демоутів `uncertain_cutoff`, але ризик «overconfident» трендів на невеликих розходженнях.
    * 🔽 **Lower Value:** Більше низьких confidence → більше `UNCERTAIN` через cutoff, більш консервативно, але можна втратити ранні тренди.
* **Invariant/Constraints:** `value >= 1.0` (Pydantic: `apps/reference/config_models.py:807`).

---

### `models.sma_trend.confidence_min`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (global confidence floor)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:173` (func: `_calculate_confidence`); `apps/reference/domains/regime_detector/regime_detector.py:394` (func: `handle_event`)
* **Mathematical Role:**
    > Нижня межа confidence. Важливо: `conf_min/conf_max` беруться з **sma_trend** і використовуються як базові межі також для volatility/MR confidence:  
    > Vol/MR роблять `confidence = min(conf_max, conf_min + delta * model_conf_mult)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Піднімає floor для всіх моделей → менше `UNCERTAIN` (і через cutoff теж), але може замаскувати реальну невпевненість.
    * 🔽 **Lower Value:** Дозволяє моделям бути «чесно невпевненими» → частіший `UNCERTAIN`, сильніше fail-closed поводження.
* **Invariant/Constraints:** `0.0 <= value <= 1.0` (Pydantic: `apps/reference/config_models.py:808`). Логічно: має бути `< confidence_max`.

---

### `models.sma_trend.confidence_max`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (global confidence cap)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:186` (func: `_calculate_confidence`); `apps/reference/domains/regime_detector/regime_detector.py:395` (func: `handle_event`)
* **Mathematical Role:**
    > Верхня межа confidence (cap) для тренду і як cap для volatility/MR (через `min(conf_max, ...)`).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Дозволяє більш «екстремальні» confidence (менше saturation), потенційно менше `UNCERTAIN` при високому cutoff, але ризик overconfidence downstream.
    * 🔽 **Lower Value:** Раніше «стеля» — більше режимів будуть мати однаковий max confidence; якщо cutoff близько до max — може збільшити `UNCERTAIN` при неідеальних умовах.
* **Invariant/Constraints:** `0.0 <= value <= 1.0` (Pydantic: `apps/reference/config_models.py:809`). Логічно: має бути `> confidence_min`.

---

### `models.volatility.enabled`
* **Type:** `int` *(boolean flag)*
* **Logic Owner:** `regime_detector` (volatility pipeline)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:345` (func: `handle_event`); `apps/reference/domains/regime_detector/regime_detector.py:401` (func: `handle_event`)
* **Mathematical Role:**
    > Якщо `true`, обчислюється ATR/baseline і може спрацювати **Priority 1** volatility-класифікація (`HIGH_VOLATILITY`/`LOW_VOLATILITY`).  
    > Також змінює `warmup.full_ready`: при enabled потрібно `atr` і `atr_baseline`; при disabled вони вважаються готовими (`True`).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** *(true)* Volatility режими можуть «перекривати» тренд/МR (пріоритет 1), і warmup стає довшим (потрібен baseline).
    * 🔽 **Lower Value:** *(false)* Немає HIGH/LOW_VOL режимів; більше класифікацій піде в TREND/MR, і `full_ready` настане швидше.
* **Invariant/Constraints:** `bool` (Pydantic: `apps/reference/config_models.py:819`).

---

### `models.volatility.atr_period`
* **Type:** `int`
* **Logic Owner:** `regime_detector`
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:112` (func: `__init__`); `apps/reference/domains/regime_detector/regime_detector.py:374` (func: `handle_event`)
* **Mathematical Role:**
    > Період ATR (Wilder).  
    > Seed: коли `len(TR_buf) >= atr_period` → `init_atr = mean(last atr_period TR)`;  
    > Далі: `atr = (last_atr*(n-1) + tr)/n`, де `n=atr_period`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Більш інертний ATR → повільніше реагує на сплески, менше фальшивих HIGH_VOL, але більший lag та довший seed.
    * 🔽 **Lower Value:** Швидше реагує, раніше дає HIGH/LOW_VOL, але більше шуму/переключень.
* **Invariant/Constraints:** `value >= 1` (Pydantic: `apps/reference/config_models.py:820`).

---

### `models.volatility.atr_sma_length`
* **Type:** `int`
* **Logic Owner:** `regime_detector`
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:113` (func: `__init__`); `apps/reference/domains/regime_detector/regime_detector.py:387` (func: `handle_event`)
* **Mathematical Role:**
    > Довжина baseline для ATR:  
    > `atr_baseline = mean(last atr_sma_length atr_values)`;  
    > `vol_ratio = atr_val / atr_baseline`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Стабільніший baseline → менше випадкових HIGH/LOW_VOL, але довший warmup до `atr_baseline_ready` (може блокувати торгівлю, якщо в DM увімкнено require warmup).
    * 🔽 **Lower Value:** Швидший baseline → швидше `full_ready` і швидша volatility-класифікація, але baseline стає шумнішим.
* **Invariant/Constraints:** `value >= 10` (Pydantic: `apps/reference/config_models.py:821`).

---

### `models.volatility.allow_close_to_close_atr`
* **Type:** `int` *(boolean flag)*
* **Logic Owner:** `regime_detector` (data-quality vs fallback TR)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:362` (func: `handle_event`)
* **Mathematical Role:**
    > Визначає, чи дозволено TR/ATR без OHLC:  
    > якщо `high/low` немає, але є `prev_close` і flag=true → `tr = abs(close - prev_close)` + note `atr_close_to_close`;  
    > якщо flag=false → `data_drops += ["atr_missing_ohlc"]` → пізніше **fail-closed**: `regime="UNCERTAIN"` (data_quality_gate).
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** *(true)* Більше robustness до неповних feature-пейлоадів (ATR працює на close-to-close), але ATR може бути менш коректним (особливо в gap/всередині бару).
    * 🔽 **Lower Value:** *(false)* Строгий контракт на OHLC: без них volatility деградує до data drop → більше `UNCERTAIN` і/або блок торгівлі downstream (консервативніше).
* **Invariant/Constraints:** `bool` (Pydantic: `apps/reference/config_models.py:822`).

---

### `models.volatility.threshold_multiplier`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (HIGH_VOL threshold)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:411` (func: `handle_event`)
* **Mathematical Role:**
    > Поріг для HIGH_VOL:  
    > `vol_ratio = atr_val / atr_baseline`  
    > якщо `vol_ratio > threshold_multiplier` → `regime="HIGH_VOLATILITY"`,  
    > `excess = vol_ratio - threshold_multiplier`, `confidence = min(conf_max, conf_min + excess * high_vol_conf_mult)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Менше HIGH_VOL (потрібен сильніший сплеск ATR), більше шансів піти в TREND/MR/UNCERTAIN.
    * 🔽 **Lower Value:** Більше HIGH_VOL (легший вхід у «волатильність»), сильніше «перекриває» тренд/МR через пріоритет 1.
* **Invariant/Constraints:** `value >= 1.0` (Pydantic: `apps/reference/config_models.py:823`).

---

### `models.volatility.low_vol_multiplier`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (LOW_VOL threshold)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:412` (func: `handle_event`)
* **Mathematical Role:**
    > Поріг для LOW_VOL: якщо `vol_ratio < low_vol_multiplier` → `regime="LOW_VOLATILITY"`,  
    > `calm = low_vol_multiplier - vol_ratio`, `confidence = min(conf_max, conf_min + calm * low_vol_conf_mult)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** Легше потрапити в LOW_VOL (бо планка вище) → більше LOW_VOL режимів.
    * 🔽 **Lower Value:** Рідше LOW_VOL (потрібна дуже низька відносна ATR) → більше `UNCERTAIN`/TREND/MR замість LOW_VOL.
* **Invariant/Constraints:** `0.0 <= value <= 1.0` (Pydantic: `apps/reference/config_models.py:824`).

---

### `models.volatility.high_vol_confidence_multiplier`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (HIGH_VOL confidence scaling)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:419` (func: `handle_event`)
* **Mathematical Role:**
    > Масштаб confidence для HIGH_VOL: `confidence = min(conf_max, conf_min + (vol_ratio - threshold_multiplier) * high_vol_confidence_multiplier)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** HIGH_VOL швидше досягає `conf_max` → менше демоутів через `uncertain_cutoff`, більше «твердих» HIGH_VOL.
    * 🔽 **Lower Value:** Більш «обережний» confidence у HIGH_VOL → частіше буде нижче cutoff (якщо cutoff високий), більше `UNCERTAIN`.
* **Invariant/Constraints:** `value >= 1.0` (Pydantic: `apps/reference/config_models.py:825`).

---

### `models.volatility.low_vol_confidence_multiplier`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (LOW_VOL confidence scaling)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:425` (func: `handle_event`)
* **Mathematical Role:**
    > Масштаб confidence для LOW_VOL: `confidence = min(conf_max, conf_min + (low_vol_multiplier - vol_ratio) * low_vol_confidence_multiplier)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** LOW_VOL швидше стає «впевненим» → менше демоутів у `UNCERTAIN`, сильніша downstream поведінка LOW_VOL (наприклад, збільшення сайзу).
    * 🔽 **Lower Value:** Частіше низька впевненість → більше `UNCERTAIN` (консервативніше).
* **Invariant/Constraints:** `value >= 1.0` (Pydantic: `apps/reference/config_models.py:826`).

---

### `models.mean_reversion.threshold`
* **Type:** `float`
* **Logic Owner:** `regime_detector` (MR detector)
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:466` (func: `handle_event`)
* **Mathematical Role:**
    > MR спрацьовує **лише якщо** поточний режим досі `UNCERTAIN` (тобто не перекритий volatility):  
    > `sma_spread = abs(sma_short - sma_long) / sma_long`  
    > `dev_short = abs(price - sma_short) / sma_short`  
    > `dev_long = abs(price - sma_long) / sma_long`  
    > якщо всі `< threshold` → `regime="MEAN_REVERSION"`.  
    > Confidence: `tightness = threshold - max(sma_spread, dev_short, dev_long)`, `confidence = min(conf_max, conf_min + tightness * confidence_multiplier)`.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** MR стає «легше» (більше станів класифікуються як MEAN_REVERSION), confidence теж зростає (через більший `tightness`), але ризик неправильно назвати тренд/волатильність «плоским».
    * 🔽 **Lower Value:** MR рідше (жорсткіша «плоскість»), більше UNCERTAIN або TREND; при `0` MR практично вимикається (умови `< 0` недосяжні).
* **Invariant/Constraints:** `value >= 0.0` (Pydantic: `apps/reference/config_models.py:836`). Практично корисно: `threshold > 0`.

---

### `models.mean_reversion.confidence_multiplier`
* **Type:** `float`
* **Logic Owner:** `regime_detector`
* **Code Reference:** `apps/reference/domains/regime_detector/regime_detector.py:475` (func: `handle_event`)
* **Mathematical Role:**
    > Масштабує MR confidence: `confidence = min(conf_max, conf_min + tightness * confidence_multiplier)`, де `tightness` — «запас» до порогу.
* **Tuning Sensitivity:**
    * 🔼 **Higher Value:** MR швидше стає «впевненим» → менше `UNCERTAIN`, більше стабільних MR-рішень downstream.
    * 🔽 **Lower Value:** MR частіше буде близько до `conf_min` → при високому `uncertain_cutoff` може демоутитись у `UNCERTAIN`.
* **Invariant/Constraints:** `value >= 1.0` (Pydantic: `apps/reference/config_models.py:837`).

---

## Пріоритети та конфлікти (volatility vs trend)

1. **Priority 1 — Volatility (ATR)**: якщо `models.volatility.enabled=true` і `atr_ready && atr_baseline_ready`, тоді `vol_ratio` може одразу встановити `HIGH_VOLATILITY` або `LOW_VOLATILITY` (`apps/reference/domains/regime_detector/regime_detector.py:401`).
2. **Slope gate (лише для HIGH_VOL)** може **збити** `HIGH_VOLATILITY` назад в `UNCERTAIN` після `confirm_bars` (EMA3-EMA6) умов (`:428–457`).
3. **Priority 2 — Mean Reversion** виконується **тільки якщо** режим досі `UNCERTAIN` (`:463–477`).
4. **Priority 3 — SMA Trend** виконується **тільки якщо** режим досі `UNCERTAIN` (`:478–484`).

Отже, коли “детектори сигналізують одночасно” на одному барі, конфлікт вирішується **порядком виконання**:
- якщо volatility спрацювала → **trend/MR не розглядаються** (бо їхні гілки вимагають `regime == "UNCERTAIN"`),
- MR має пріоритет над trend,
- після raw-вибору застосовується `hysteresis_bars`, і в `EVT:REGIME_DETECTED` емiтиться **stable_regime** (анти-чьорн), а не raw.

---

### `system_stress.robust_method`
* **Type:** `Literal["none", "mad"]`
* **Logic Owner:** `system_stress` (Robust Statistics)
* **Code Reference:** `apps/reference/domains/system_stress/system_stress_overlay.py` (func: `_z_robust`)
* **Mathematical Role:**
    > Зменшення кількості false-positive STRESS-переходів на жирних хвостах розподілу.  
    > `none`: звичайний Z-score: `(x - mean) / std`.  
    > `mad`: робастний Z-score: `0.6745 * (x - median) / MAD`.
* **Tuning Sensitivity:**
    * 🔼 **"mad" Value:** Менше false-positives від одиничних великих спайків у baseline, метрика стає стійкішою до fat-tail returns.
    * 🔽 **"none" Value:** Класичний підхід, більш чутливий до екстремальних викидів (std "роздмухується", що може як маскувати нові спайки, так і давати хибні сигнали при виході спайку з вікна).
* **Invariant/Constraints:** `none` or `mad` (Pydantic: `apps/reference/config_models.py`).

---

### `regime_shift_inception.enabled`
* **Type:** `bool`
* **Logic Owner:** `decision_making` (Regime-Shift Inception Guard)
* **Code Reference:** `apps/reference/domains/decision_making/inception_filter.py`
* **Mathematical Role:**
    > Дозволяє стратегії реагувати на raw-режим під час "stable_regime ∉ allowed_regimes". 
* **Invariant/Constraints:** `false` (Pydantic).

---

### `regime_shift_inception.action`
* **Type:** `Literal["none", "micro_size", "confirm_next_bar"]`
* **Logic Owner:** `decision_making`
* **Mathematical Role:**
    > Дія при inception: `none` = тільки телеметрія, `micro_size` = вхід зменшеним лотом.
* **Invariant/Constraints:** `none` (Pydantic).

---

### `regime_shift_inception.micro_size_fraction`
* **Type:** `float`
* **Logic Owner:** `decision_making`
* **Mathematical Role:**
    > Множник об'єму позиції при `action="micro_size"`.
* **Invariant/Constraints:** `0.0 < value <= 1.0` (Pydantic).

