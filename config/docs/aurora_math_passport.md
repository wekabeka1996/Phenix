# Math & Logic Passport: `config/aurora/strategies/aurora.yaml` (Phase 7)

Цей паспорт описує **математику та логіку взаємодії** ключових полів Aurora SSOT (`config.strategies.aurora.*`) з runtime-ядром: скоринг, пороги, hysteresis, side-bias та liquidity gate.

**Critical Consumers (Trace Targets):**
1. **Scoring Kernel:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py`
2. **Signal Handler:** `apps/reference/domains/decision_making/aurora_handler.py`
3. **Feature Weights:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py` + `apps/reference/domains/decision_making/signal_score_v2.py`

**Дата генерації:** `2026-02-03`

---

### `scoring_logic` (Synthesis)
* **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:148`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:96`; `apps/reference/domains/decision_making/signal_score_v2.py:80`; `apps/reference/domains/decision_making/aurora_handler.py:834`
* **Formula:** `score = dir_score * (1 + strength_alpha * strength_score)`
    ```text
    # 0) Per-symbol policy (handler)
    base_threshold = strategies.aurora.decision.signal_threshold (or per-symbol override)
    neutral_threshold = strategies.aurora.decision.neutral_threshold (or per-symbol override)
    weights = strategies.aurora.decision.signal_weights (or assets.<SYM>.weights)
    neutrals = strategies.aurora.decision.feature_neutrals (or assets.<SYM>.feature_neutrals)
    regime_factor = regime_thresholds[regime] else regime_thresholds["DEFAULT"]  (fail-closed if missing/<=0)

    # 1) delta_price normalization (kernel)
    dp_pct = delta_price_raw / price
    dp_pct_cap = clamp(dp_pct, -delta_price_cap_pct, +delta_price_cap_pct)
    delta_price = dp_pct_cap / delta_price_cap_pct          # ∈ [-1, 1]

    # 2) Net-zero centered feature contribution (SignalScoreV2)
    component_i = w_i * (x_i - neutral_i)
    score_raw = Σ component_i
    wabs = Σ |w_i|                  # only for active/ready features (missing/not-ready are skipped)
    score_norm = score_raw / wabs
    score_clamped = clamp(score_norm, -1, +1)

    # 3) Direction/Strength split (DirectionStrengthScore)
    dir_score = SignalScoreV2(score over directional_features)                 # ∈ [-1, 1]
    strength_base = SignalScoreV2(score over strength_features)                # ∈ [-1, 1]
    strength_score = clamp(max(0, strength_base), 0, strength_cap)             # ∈ [0, strength_cap]
    score = dir_score * (1 + strength_alpha * strength_score)                  # NOT clamped

    # 4) Thresholding (kernel): base × regime × side-bias
    thr0 = base_threshold * regime_factor
    # side-bias (kernel): penalize overrepresented side by raising its threshold
    buy_bias_mult = 1
    sell_bias_mult = 1
    if (buy_count + sell_count) >= min_intents:
        sell_share = sell_count / (buy_count + sell_count)
        if sell_share > target_ratio:
            sell_bias_mult = 1 + penalty_factor * ((sell_share - target_ratio) / (1 - target_ratio))
        elif sell_share < (1 - target_ratio):
            buy_share = 1 - sell_share
            buy_bias_mult = 1 + penalty_factor * ((buy_share - target_ratio) / (1 - target_ratio))
    thr_buy  = thr0 * buy_bias_mult
    thr_sell = thr0 * sell_bias_mult

    # 5) Hysteresis (kernel)
    if current_side == "":
        enter BUY  if score >= thr_buy
        enter SELL if score <= -thr_sell
    if current_side == "buy":
        flip->SELL if score <= -thr_sell
        hold BUY   if score >= neutral_threshold
        else exit->neutral
    if current_side == "sell":
        flip->BUY  if score >= thr_buy
        hold SELL  if score <= -neutral_threshold
        else exit->neutral
    ```
* **Normalization:** `SignalScoreV2` clamped subscores (`dir_score`, `strength_base`) to `[-1, 1]`, але `final score` **не клэмпиться** після `dir * (1 + α·strength)`; діапазон: `score ∈ [-(1 + α·cap), +(1 + α·cap)]` при `|dir_score|=1`. (`apps/reference/domains/decision_making/signal_score_v2.py:206`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:221`)
* **Non-linearities:** `clamp(-1,1)` у `SignalScoreV2`, `max(0,·)` + `min(cap,·)` у strength, множення `dir*(1+α·strength)`, а також threshold/hysteresis логіка (piecewise) у kernel. Сигмоїдів/тангесів у цьому пайплайні немає. (`apps/reference/domains/decision_making/signal_score_v2.py:206`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:259`)

---

### `strategies.aurora.decision.signal_weights.obi`
- **Type:** `float`
- **Logic Owner:** `SignalScoreV2` (via `DirectionStrengthScore`)
- **Code Reference:** `apps/reference/domains/decision_making/signal_score_v2.py:110`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:151`
- **Mathematical Role:**
    > Вага OBI у directional part: входить у `component = w*(obi - neutral_obi)`, далі у нормалізовану суму `dir_score = Σ component / Σ|w|`. Позитивний `w` означає, що зростання OBI (відносно нейтралі) підсилює BUY-напрям.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Надмірна реакція на стакан → високий churn/overfitting на мікроструктуру.
    - 🔽 **Too Low:** OBI майже не впливає → втрата раннього direction signal.

---

### `strategies.aurora.decision.signal_weights.tfi`
- **Type:** `float`
- **Logic Owner:** `SignalScoreV2` (via `DirectionStrengthScore`)
- **Code Reference:** `apps/reference/domains/decision_making/signal_score_v2.py:110`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:151`
- **Mathematical Role:**
    > Вага TFI у directional part: лінійний внесок `(tfi - neutral_tfi)` у `dir_score`. Позитивний `w` підсилює BUY при tfi>neutral, SELL при tfi<neutral.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Доминація одного тренд-індикатора → пропуск інших (OBI/EMA) і помилки у noisy-trend.
    - 🔽 **Too Low:** Trend component слабкий → стратегія стає менш тренд-слідуючою.

---

### `strategies.aurora.decision.signal_weights.delta_price`
- **Type:** `float`
- **Logic Owner:** `AuroraScoringKernel` + `SignalScoreV2`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:148`; `apps/reference/domains/decision_making/signal_score_v2.py:110`
- **Mathematical Role:**
    > Вага нормалізованого `delta_price` у directional part. В kernel `delta_price` спочатку приводиться до `[-1,1]` через `delta_price_cap_pct`, після чого входить у `component = w*(delta_price_norm - neutral_delta_price)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Momentum домінує → FOMO entries; більше блоків safety gates або стопів.
    - 🔽 **Too Low:** Недостатня чутливість до price action → запізнілі входи/виходи.

---

### `strategies.aurora.decision.signal_weights.ema_bias`
- **Type:** `float`
- **Logic Owner:** `SignalScoreV2` (via `DirectionStrengthScore`)
- **Code Reference:** `apps/reference/domains/decision_making/signal_score_v2.py:151`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:151`
- **Mathematical Role:**
    > Вага EMA-bias у directional part. Типовий контракт для EMA-bias — `[0,1]` з `neutral=0.5`, тому centered внесок: `(ema_bias - 0.5)` (масштаб залежить від upstream нормалізації).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Перекос у бік EMA → стратегія “бачить” тренд всюди; менше mean-reversion safety.
    - 🔽 **Too Low:** EMA інформація не використовується → direction слабший у трендових режимах.

---

### `strategies.aurora.decision.signal_weights.depth_imbalance`
- **Type:** `float`
- **Logic Owner:** `SignalScoreV2` (via `DirectionStrengthScore`)
- **Code Reference:** `apps/reference/domains/decision_making/signal_score_v2.py:110`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:151`
- **Mathematical Role:**
    > Вага depth-imbalance у directional part. Негативна вага означає інверсію: якщо `depth_imbalance` зростає вище нейтралі (наприклад, більше ask-домінації), це зменшує `dir_score` (SELL pressure).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Надмірна “мікроструктурна” інверсія → noise-sensitive flips.
    - 🔽 **Too Low:** Ігнорування дисбалансу глибини → гірше входи в тонкій ліквідності.

---

### `strategies.aurora.decision.signal_weights.macro_resid`
- **Type:** `float`
- **Logic Owner:** `SignalScoreV2` (via `DirectionStrengthScore`)
- **Code Reference:** `apps/reference/domains/decision_making/signal_score_v2.py:110`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:151`
- **Mathematical Role:**
    > Вага `macro_resid` у directional part: лінійний centered внесок у `dir_score`. Типово `neutral=0.0`, тобто внесок ~ `w*macro_resid`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Макро-фактор домінує локальні фічі → пропуск локальних можливостей.
    - 🔽 **Too Low:** Макро-контекст майже не впливає → більший ризик ловити “ніж” під час crash.

---

### `strategies.aurora.decision.signal_weights.volume_spike`
- **Type:** `float`
- **Logic Owner:** `DirectionStrengthScore` (strength part)
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:206`
- **Mathematical Role:**
    > Вага `volume_spike` у strength part. Впливає на `strength_base`, який після `max(0, ·)` та `cap` масштабує `dir_score` через `(1 + α·strength)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** “Сила” починає піддувати direction надто часто → score виходить за [-1,1] і пороги треба піднімати.
    - 🔽 **Too Low:** Strength майже нульовий → `score ≈ dir_score`, менше адаптації під “силу” руху.

---

### `strategies.aurora.decision.signal_weights.volatility_state`
- **Type:** `float`
- **Logic Owner:** `DirectionStrengthScore` (strength part)
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:206`
- **Mathematical Role:**
    > Вага `volatility_state` у strength part. Працює як “підсилювач/ослаблювач” direction через strength-пайплайн.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Vol state надто впливає на amplitude → нестабільний score.
    - 🔽 **Too Low:** Vol state не впливає → менш режимно-адаптивна інтенсивність сигналу.

---

### `strategies.aurora.decision.feature_neutrals` (all)
- **Type:** `dict[str, float]`
- **Logic Owner:** `SignalScoreV2`
- **Code Reference:** `apps/reference/domains/decision_making/signal_score_v2.py:51`; `apps/reference/domains/decision_making/signal_score_v2.py:151`
- **Mathematical Role:**
    > Neutral offsets — це “центр” фічі: у кожній вкладці використовується `(x - neutral)` перед множенням на вагу. Це робить скор **net-zero**: `x==neutral` → внесок 0 незалежно від ваги.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Зміщення нейтралі ламає знак/амплітуду centered внеску → системний bias у score.
    - 🔽 **Too Low:** Зміщення в інший бік → симетрична проблема; часто проявляється як перекос BUY/SELL.

---

### `strategies.aurora.decision.direction_strength_scoring.directional_features`
- **Type:** `list[string]`
- **Logic Owner:** `DirectionStrengthScore`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:233`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:141`
- **Mathematical Role:**
    > Define set D, над яким рахується `dir_score`. Ваги для фіч поза D ігноруються (не входять у `w_dir`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Надто широкий D → більше джерел noise + складніше калібрувати neutrals.
    - 🔽 **Too Low:** Надто вузький D → dir_score крихкий до missing/not-ready фіч.

---

### `strategies.aurora.decision.direction_strength_scoring.strength_features`
- **Type:** `list[string]`
- **Logic Owner:** `DirectionStrengthScore`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:233`; `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:142`
- **Mathematical Role:**
    > Define set S, над яким рахується `strength_base`. Ваги поза S ігноруються (не входять у `w_str`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Strength стає “мішанкою” з різних типів метрик → складніша інтерпретація і калібрування α/cap.
    - 🔽 **Too Low:** Strength неінформативний → `score` майже не модулюється.

---

### `strategies.aurora.decision.direction_strength_scoring.strength_alpha`
- **Type:** `float`
- **Logic Owner:** `DirectionStrengthScore`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:221`
- **Mathematical Role:**
    > Множник α у формулі `score = dir * (1 + α·strength)`. Збільшує амплітуду score, не змінюючи знак (за умови `strength>=0`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `|score|` часто >1 → пороги треба узгоджувати, інакше часті enters/flips.
    - 🔽 **Too Low:** Strength майже не впливає → `score ≈ dir`.

---

### `strategies.aurora.decision.direction_strength_scoring.strength_cap`
- **Type:** `float`
- **Logic Owner:** `DirectionStrengthScore`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:218`
- **Mathematical Role:**
    > Upper-bound для `strength_score` після `max(0, strength_base)`: `strength_score = min(strength_score, cap)`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Strength може “роздувати” score на екстремах → нестабільність амплітуди.
    - 🔽 **Too Low:** Strength швидко насичується → мало різниці між “трохи сильним” і “дуже сильним” рухом.

---

### `strategies.aurora.decision.signals.delta_price_cap_pct`
- **Type:** `float` *(ratio; 0.02 = 2%)*
- **Logic Owner:** `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:242`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:148`
- **Mathematical Role:**
    > Cap для normalization `delta_price`: `dp_norm = clamp(delta_price/price, ±cap) / cap`. Визначає, при якому % руху `delta_price` насичується в `±1`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Великий cap → `delta_price_norm` рідше насичується → momentum менш “жорстко” обмежений.
    - 🔽 **Too Low:** Малий cap → швидка сатурація `±1` → delta_price втрачає градації, більше “on/off”.

---

### `strategies.aurora.decision.regime_threshold_multipliers`
- **Type:** `dict[str, float]`
- **Logic Owner:** `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:217`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:203`
- **Mathematical Role:**
    > Regime-factor `k(regime)` масштабує поріг: `thr0 = base_threshold * k(regime)`; якщо немає ключа для поточного regime — використовується `DEFAULT`; якщо немає і `DEFAULT` → scoring deferred (fail-closed).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `k>1` ⇒ вищий поріг ⇒ менше угод у цьому regime (консервативніше).
    - 🔽 **Too Low:** `k<1` ⇒ нижчий поріг ⇒ більше угод (агресивніше).
- **Special Focus (Aggressive in trend / quiet in flat):**
    > Щоб бути “агресивною” у трендових режимах, ставте `k(TREND_*) < 1` (нижчий поріг → легше enter).  
    > Щоб бути “тихою” у флеті/uncertain, ставте `k(FLAT/UNCERTAIN/HIGH_VOLATILITY) > 1` (вищий поріг → менше churn/false positives).  
    > Важливо: це працює **тільки через пороги**, сам `score` не масштабується regime-фактором.

---

### `strategies.aurora.decision.signal_threshold`
- **Type:** `float`
- **Logic Owner:** `AuroraHandler` → `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:180`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:220`
- **Mathematical Role:**
    > Base threshold для entry/flip/exit: у kernel використовується як `base_threshold` і перетворюється у `thr_buy/thr_sell` після regime-factor + side-bias.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Вищий поріг ⇒ менше entries/flips (консервативніше, більше missed opportunities).
    - 🔽 **Too Low:** Нижчий поріг ⇒ більше entries/flips (більше churn/overtrading).

---

### `strategies.aurora.decision.neutral_threshold`
- **Type:** `float`
- **Logic Owner:** `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:246`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:265`
- **Mathematical Role:**
    > Hysteresis exit/hold threshold. Для `current_side=buy`: HOLD якщо `score >= neutral_threshold`, EXIT якщо `score < neutral_threshold`; аналогічно для SELL з `-neutral_threshold`. Вхід все одно порівнюється з `thr_buy/thr_sell`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Neutral близько до entry-порогів ⇒ більше exits (менше “терпіння”), можливий churn.
    - 🔽 **Too Low:** Neutral дуже малий ⇒ позиції тримаються довше, але більший lag на exit.

---

### `strategies.aurora.decision.side_bias_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `AuroraHandler` (state) + `AuroraScoringKernel` (math)
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:212`; `apps/reference/domains/decision_making/aurora_handler.py:1973`
- **Mathematical Role:**
    > Визначає time-window для підрахунку `buy_count/sell_count`. За межами вікна timestamps очищаються; bias реагує на останню історію.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довге вікно ⇒ bias інертний (довше “пам’ятає” перекос).
    - 🔽 **Too Low:** Коротке вікно ⇒ bias шумний (реагує на випадкові серії).

---

### `strategies.aurora.decision.side_bias_target_ratio`
- **Type:** `float`
- **Logic Owner:** `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:213`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:226`
- **Mathematical Role:**
    > Target share для кожної сторони у bias-вікні. Якщо `sell_share > target_ratio`, penalize SELL threshold; якщо `buy_share > target_ratio`, penalize BUY threshold.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Target близький до 1 ⇒ bias рідко спрацьовує (майже дозволяє “перекіс”).
    - 🔽 **Too Low:** Target ближчий до 0.5 ⇒ bias частіше піднімає пороги (сильніша нейтралізація).

---

### `strategies.aurora.decision.side_bias_penalty_factor`
- **Type:** `float`
- **Logic Owner:** `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:214`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:232`
- **Mathematical Role:**
    > Max-amplitude penalty у множнику порогу: `bias_mult = 1 + penalty_factor * scaling`, де `scaling ∈ [0,1]` залежить від перевищення share над target.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Різко піднімає пороги “overrepresented” сторони ⇒ може прибити торгівлю у тренді.
    - 🔽 **Too Low:** Bias слабкий ⇒ більше перекосів BUY/SELL і потенційно більше risk концентрації.

---

### `strategies.aurora.decision.side_bias_min_intents`
- **Type:** `int`
- **Logic Owner:** `AuroraScoringKernel`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:226`
- **Mathematical Role:**
    > Мінімальна кількість intents у bias-window, після якої bias починає діяти. До цього `buy_bias_mult=sell_bias_mult=1`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Bias майже не включається → більше перекосів у невеликій статистиці.
    - 🔽 **Too Low:** Bias включається рано → ризик “покарання” на випадкових перших trades.

---

### `strategies.aurora.decision.liquidity_gate.enabled`
- **Type:** `bool`
- **Logic Owner:** `AuroraHandler`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:746`; `apps/reference/domains/decision_making/aurora_handler.py:1858`
- **Mathematical Role:**
    > Hard gate (не penalty): якщо enabled і `liquidity_kappa` not-ready/missing/invalid/low → стратегія блокує emission (score не рахується).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` + строгі min ⇒ менше угод, але менше slippage-risk.
    - 🔽 **Too Low:** `false` ⇒ більше угод у тонкій ліквідності, але більший execution risk.

---

### `strategies.aurora.decision.liquidity_gate.kappa_min`
- **Type:** `float`
- **Logic Owner:** `AuroraHandler`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1939`; `apps/reference/domains/decision_making/aurora_handler.py:1943`
- **Mathematical Role:**
    > Мінімальний допустимий `liquidity_kappa`: якщо `kappa < kappa_min` → блок (fail-closed) з reason `LIQUIDITY_LOW`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Блокує торгівлю на більшості low-liq фаз → багато missed opportunities.
    - 🔽 **Too Low:** Пропускає thin books → більше slippage/partial fills.

---

### `strategies.aurora.decision.liquidity_gate.kappa_max`
- **Type:** `float`
- **Logic Owner:** `AuroraHandler`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1931`
- **Mathematical Role:**
    > Defensive clamp: якщо `kappa > kappa_max`, handler зменшує до `kappa_max` перед порівнянням з min (захист від upstream drift).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Clamp майже не діє → kappa outliers проходять як є (але min-check все одно головний).
    - 🔽 **Too Low:** Перетискає kappa до низьких значень → частіше `LIQUIDITY_LOW`.

---

### `strategies.aurora.decision.liquidity_gate.failsafe_qty_check`
- **Type:** `bool`
- **Logic Owner:** `AuroraHandler`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_handler.py:1888`
- **Mathematical Role:**
    > Конфіг флаг, який зараз лише передається у контекст (details) liquidity gate; прямого впливу на gating-формулу в `_check_liquidity_gate()` не має.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ (наразі) немає змін у поведінці gate.
    - 🔽 **Too Low:** `false` ⇒ (наразі) немає змін у поведінці gate.

---

### `strategies.aurora.decision.essential_features`
- **Type:** `list[string]`
- **Logic Owner:** `AuroraScoringKernel` + `SignalScoreV2`
- **Code Reference:** `apps/reference/domains/decision_making/aurora_scoring_kernel.py:164`; `apps/reference/domains/decision_making/signal_score_v2.py:167`
- **Mathematical Role:**
    > Fail-closed readiness contract. Kernel defers якщо readiness-map не містить ключа для essential feature. Далі `SignalScoreV2` defers якщо essential weighted feature missing/not-ready (у межах `directional_features`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Занадто багато essential ⇒ часті defers під час warmup/дефіциту даних.
    - 🔽 **Too Low:** Занадто мало essential ⇒ ризик торгувати без критичних фіч.

---

### `strategies.aurora.decision.signals.normalize_signals_mode`
- **Type:** `string`
- **Logic Owner:** `AuroraScoringKernel` + `compute_direction_strength_score`
- **Code Reference:** `apps/reference/domains/decision_making/scoring_direction_strength_v1.py:144`; `apps/reference/domains/decision_making/aurora_scoring_kernel.py:179`
- **Mathematical Role:**
    > У `compute_direction_strength_score()` є спец-режим `signed_v2`, який масштабує `[0,1]` фічі з `neutral=0.5` так, щоб centered компонент був у `[-1,1]`.  
    > **Wiring note:** Mode прокидається у kernel і строго валідований: дозволено лише `signed_v2`. Будь-яке інше значення → fail-closed.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** N/A (mode fixed; tune weights/features instead).
    - 🔽 **Too Low:** N/A (`off/net_zero` forbidden).
