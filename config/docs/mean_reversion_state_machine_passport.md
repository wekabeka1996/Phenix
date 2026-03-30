# Code-Driven State Machine Passport: `config/aurora/strategies/mean_reversion.yaml`

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/mean_reversion_state_machine_passport.md`
> - **Audit date:** 2026-03-29
> - **Audit mode:** Code-driven deep sync
> - **Major drifts found:**
>   1. Missing strategy parameters like `bb_window`, `bb_num_std`, `rsi_window`, `entry_threshold`, RSI thresholds, and confidence scalars added for completeness.
>   2. The previous assertion that `DOGEUSDT` is the only live MR symbol is stale; current `strategies.yaml` has no `mean_reversion` assignments.
>   3. `timeframe_sec=300` and the dormant DOGE-specific override block in `mean_reversion.yaml` are still present on disk, but they are not live-loaded while `mean_reversion` is unassigned.
> - **Overall confidence:** HIGH

Цей паспорт описує code/runtime контракт state machine для `mean_reversion`, але у поточному перевіреному registry state ця стратегія не має live assignment і не стартує у runtime. Нижче зафіксовано, що саме лишається істинним для dormant profile на диску і який handler/state-machine path активується, якщо `mean_reversion` буде reassigned пізніше.

Owner surface:
- Strategy state machine: `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- Runtime orchestration: `apps/reference/domains/decision_making/mean_reversion_handler.py`
- Plugin wiring: `apps/reference/domains/strategies/plugins/mean_reversion.py`
- Typed contract: `apps/reference/config_models.py::MeanReversion1mStrategyConfig`

## 1. Головна корекція паспорта

Старий документ застряг у змішаній термінології `1m/3m/Phase 8`, але поточний live YAML задає:
- `timeframe_sec: 300`
- registry assignments для `mean_reversion` зараз відсутні

Тобто поточний live path такий:
- клас усе ще називається `MeanReversion1mStrategy`
- деякі handler/docstring comments усе ще кажуть `1m` або `3m`
- профіль на диску лишається 5m (`300s`), але live activation зараз відсутня через registry-level disable

## 2. Activation SSOT

`mean_reversion` активується не просто через `enabled=true`, а через assignment-first контракт:
- `config/aurora/strategies.yaml` визначає, які symbols assigned до `mean_reversion`
- `MeanReversionHandler._parse_config()` бере фінальний universe як `assigned ∩ assets.enabled`

Поточний live assignment set:
- `DOGEUSDT → mean_reversion` (strategies.yaml line 41)

Поточний live наслідок цього стану:
- `ConfigLoader` live-loadить `config.strategies.mean_reversion`
- `StrategyRuntime` стартує `MeanReversionPlugin` для DOGEUSDT
- `MeanReversionHandler` активний для DOGEUSDT (assigned ∩ assets.DOGEUSDT.enabled=true)

Fail-closed інваріанти, якщо `mean_reversion` буде reassigned:
- якщо `config.strategies.mean_reversion` відсутній, handler падає
- якщо `mean_reversion.enabled=false`, але symbol assigned, handler падає
- якщо assigned symbol відсутній у `mean_reversion.assets` або `enabled=false`, handler падає

## 3. Де проходить межа state machine

Власне state machine закінчується на `MRSignal` і не керує execution lifecycle.

До state machine належить:
- накопичення bars
- індикатори `BB`, `ATR`, `RSI`
- regime mapping у flat regimes
- entry/no-entry рішення по `%B`
- розрахунок `entry_price`, `stop_price`, `target_price`, `confidence`

До handler overlay належить:
- assignment/config gating
- `CMD:PROCESS_STRATEGY` payload validation
- liquidity gate
- objective engine integration
- runtime readiness/runtime permissions envelope
- emission `EVT:STRATEGY_SIGNAL_PRODUCED`

До downstream execution domain належить:
- `ExecPosFSM`
- `ManageFlowFSM`
- bracket/order lifecycle
- `ORDER_UPDATED` sync, `TTL_EXPIRED_3600s`, `ORPHANED_TTL`

Це критично для incident analysis: split-brain із `ManageFlowFSM` не є behavior самого MR state machine.

## 4. Реальний trigger path

Описаний нижче trigger path є code/runtime contract path. У поточному verified live config він активний для DOGEUSDT через assignment у strategies.yaml.

Поточний primary entrypoint для decision path:
- тільки `CMD:PROCESS_STRATEGY`

`MeanReversionHandler._on_process_strategy()` робить таке:
- reject якщо `tf_sec` відсутній
- skip якщо `tf_sec != self.timeframe_sec`
- reject якщо відсутній `bar_close_ts`
- reject якщо відсутній `bar`
- пропускає symbol, який не входить у `enabled_symbols`
- будує `Bar` з payload
- кешує `features` для volatility/liquidity propagation
- кешує `price_motion` з top-level CMD payload (dedicated per-symbol cache, NOT inside features)
- встановлює regime з payload або з внутрішнього кешу
- застосовує Vector 2 Directional Bias (якщо enabled)
- викликає `strategy.on_bar(symbol, bar, ts_ms)` (з `finally` для R3 threshold clearing)
- якщо signal actionable:
  - застосовує Vector 1 Microstructure Veto (якщо enabled)
  - перевіряє liquidity gate
  - якщо обидва пройдені, емить `EVT:STRATEGY_SIGNAL_PRODUCED`

Отже, стара tick-driven ментальна модель більше не є SSOT. У файлах ще є історичні сліди старого шляху, але live contract зараз bar-driven через `CMD:PROCESS_STRATEGY`.

## 5. Внутрішня логіка `MeanReversion1mStrategy.on_bar()`

Актуальний порядок state machine такий:

1. Додати завершений bar у symbol state
2. Якщо bars < `min_bars` → neutral `insufficient_bars`
3. Оновити `BB`, `ATR`, `RSI`
4. Якщо cooldown активний → neutral `cooldown`
5. Перетворити external regime у `FlatRegime` через `map_to_flat_regime()`
6. Якщо regime не flat → neutral `regime_not_flat:*`
7. Якщо `flat_regime.name` не входить у `allowed_regimes` → neutral `regime_not_allowed:*`
8. Якщо `BB` відсутній → neutral `no_bb`
9. Якщо `bb.width < min_bb_width` → neutral `bb_width_too_narrow:*`
10. Якщо `bb.width > max_bb_width` → neutral `bb_width_too_wide:*`
11. Обчислити `%B`
12. Якщо `%B < entry_threshold` → LONG
13. Якщо `%B > 1 - entry_threshold` → SHORT
14. Інакше → neutral `no_signal:*`

Важливе уточнення:
- RSI не є hard gate
- RSI лише додає бонус до `confidence`, якщо підтверджує екстремум

## 6. Entry / exit semantics усередині strategy

`MeanReversion1mStrategy` не відкриває позиції сама. Вона лише формує `MRSignal` з advisory prices.

Entry:
- `entry_price = current close`

Target:
- якщо `tp_to_mid=true`, базова ціль = `bb.mid`
- якщо `tp_to_mid=false`, базова ціль = протилежна band boundary
- потім target distance множиться на `mr_params.target_mult`
- опційно додається `tp_buffer_pct`

Stop:
- базовий stop = `ATR * sl_atr_mult * mr_params.stop_mult`
- якщо ATR немає, fallback = `(bb.upper - bb.lower) / 4`
- опційно додається `sl_buffer_pct`

Time-based forced exit у самій strategy немає. Якщо існують timeout/cleanup/forced close сценарії, це вже execution-position domain, не state machine.

## 7. Override semantics

Handler будує фактичний `MRStrategyConfig` у такому порядку:
- глобальні `mean_reversion.strategy`
- потім `mean_reversion.assets.<SYM>.allowed_regimes`
- потім найспецифічніші `mean_reversion.assets.<SYM>.strategy.*`

Тобто precedence для `allowed_regimes` така:
- global default
- per-asset `allowed_regimes`
- per-asset strategy override `strategy.allowed_regimes`, якщо заданий

Це підтверджено config wiring tests.

## 8. Liquidity gate і objective engine не належать самій state machine

`MeanReversion1mStrategy` про них нічого не знає.

Liquidity gate живе в handler:
- precedence: `assets.<SYM>.liquidity_gate` → global `mean_reversion.liquidity_gate`
- якщо gate enabled, а `liquidity_kappa` відсутній у cache, handler fail-closed кидає помилку контракту
- якщо `kappa < kappa_min`, сигнал блокується до emission

Objective Engine теж живе в handler, уже після формування `MRSignal`:
- вмикається тільки якщо і domain, і strategy objective blocks enabled
- використовує portfolio, exposure summary, regime timestamps/confidence та cached features
- може блокувати emission через `OBJECTIVE_GATE_BLOCKED`
- може fail-close через `OBJECTIVE_ENGINE_FAIL_CLOSED`

## 9. Signal payload boundary

Коли signal пройшов handler overlays, emit містить:
- `strategy_id=mean_reversion`
- `tf_sec=self.timeframe_sec`
- `side`
- `price_ctx.entry_price/stop_price/target_price`
- `regime`
- `volatility` і `liquidity` з cached features
- `mr_params`
- `score` і `scoring.objective`
- `runtime_permissions`
- `runtime_readiness`

Отже, downstream execution бачить уже не raw state-machine reasoning, а обгорнутий decision payload.

## 10. Що реально говорить YAML сьогодні

У поточному профілі:
- `timeframe_sec=300`
- `execution.entry_order_type=MARKET`
- `safety_gates.enabled=false`
- `objective.enabled=true`
- live assignment: `DOGEUSDT → mean_reversion` (strategies.yaml)
- `DOGEUSDT.strategy.min_bb_width=0.005` активний у live profile
- `microstructure_veto.enabled=false` (V1 dormant)
- `directional_bias.enabled=false` (V2 dormant)

Для incident context це важливо:
- strategy-level вхід у squeeze breakout лишається «правильним за кодом», якщо `bb_width > 0.005`, але цей path зараз не live-active
- downstream execution split-brain після цього вже не є частиною MR state machine

## 11. Drift, виявлений аудитом

- Імена та comments у codebase частково застарілі: `MeanReversion1mStrategy`, `Mean Reversion 3m strategy`, старі Phase B/T2B описи. Live TF SSOT зараз 300s.
- Старий integration файл `tests/integration/test_mean_reversion_handler_event_contract_v1.py` позначений `skip` і досі прив'язаний до старого tick-based path. Це не слід використовувати як джерело істини.
- Старий паспорт переоцінював “strategy-owned” зони і недостатньо чітко відділяв їх від execution FSM layer.
- **STALE (corrected 2026-03-31):** Previous passport stated “live assignments для mean_reversion відсутні”. This was stale — `DOGEUSDT` IS assigned to `mean_reversion` in `strategies.yaml` line 41.
- **STALE (corrected 2026-03-31):** `MRDirectionalBiasConfig` Pydantic docstring (config_models.py:600-601) had inverted semantics: stated “positive funding → SHORT stricter, LONG easier” which is backwards. Code formula is correct (positive funding → LONG harder, SHORT easier). Docstring corrected.
- **STALE (corrected 2026-03-30):** V1 `missing_policy` previously allowed `”skip”`. R1 hardening removed it; only `”block”` accepted (Literal constraint).
- **STALE (corrected 2026-03-30):** V2 handler comments had inverse trigger semantics. R2 fixed all comments/docstrings to match code formula.

## 12. Підсумок

Поточна `mean_reversion` state machine в коді є bar-driven mean-reversion логікою, яка:
- працює на 5m bars у своєму profile contract
- приймає рішення через `%B`, BB width, flat regime mapping, cooldown та confidence boosts
- не володіє execution lifecycle
- передає downstream уже збагачений handler-ом payload, якщо strategy reassigned і handler активований

Правильна ментальна модель така:
- `MeanReversion1mStrategy` = math/state
- `MeanReversionHandler` = activation + contract gates + enrichment + emission
- `ExecPosFSM/ManageFlowFSM` = execution/state reconciliation, де й живуть incident-класи типу `ORDER_UPDATED` desync

---

### `strategies.mean_reversion.strategy.score_multiplier`
- **Type:** `float`
- **Logic Owner:** `MeanReversionHandler` (signal scoring)
- **Code Reference:** `apps/reference/config_models.py:399`
- **Default:** `1.0` (Pydantic default; NOT in YAML)
- **Category:** **Pydantic default** — always uses 1.0 because no YAML knob exists
- **Mathematical Role:**
    > Multiplier applied to signal score before emission. At 1.0 it is a no-op.
- **Fallback:** None. Pydantic default always used. Operator cannot override without adding YAML field.

---

### `strategies.mean_reversion.strategy.sl_buffer_pct`
- **Type:** `float` *(ratio; 0.002 = +0.20%)*
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:171`
- **Default:** `0` (dataclass default; can be set in per-asset override YAML)
- **Category:** **Pydantic/dataclass default** — 0 means no extra buffer
- **Mathematical Role:**
    > Additive buffer on top of ATR-based SL distance: `final_sl = atr_sl + entry_price * sl_buffer_pct`. Widens SL beyond what `sl_atr_mult * stop_mult` alone provides.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** SL pushed further away → less stop-outs but higher risk per trade.
    - 🔽 **Zero:** Default. Pure ATR-based SL.

---

### `strategies.mean_reversion.strategy.tp_buffer_pct`
- **Type:** `float` *(ratio; 0.002 = +0.20%)*
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:173`
- **Default:** `0` (dataclass default; can be set in per-asset override YAML)
- **Category:** **Pydantic/dataclass default** — 0 means no extra buffer
- **Mathematical Role:**
    > Additive buffer on top of BB-based TP distance: `final_tp = bb_tp + entry_price * tp_buffer_pct`. Pushes TP further from entry.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** TP pushed further → lower winrate, higher R:R.
    - 🔽 **Zero:** Default. Pure BB-based TP.

---

### `strategies.mean_reversion.strategy.min_bars`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:321`
- **Mathematical Role:**
    > Warmup барів перед сигналами: доки `len(bars) < min_bars`, стратегія повертає neutral (`insufficient_bars`). Гарантує, що BB/ATR/RSI мають шанс бути готовими.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Довший warmup ⇒ менше торгівлі на старті сесії (менше risk), але більше missed early moves.
    - 🔽 **Too Low:** Раніші сигнали ⇒ ризик торгувати на нестабільних індикаторах.

---

### `strategies.mean_reversion.strategy.bb_window`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:463`
- **Mathematical Role:**
    > Довжина вікна для побудови Bollinger Bands (SMA та StdDev).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Канал інертніший ⇒ повільніше адаптується до зміни ціни, сигнали рідші.
    - 🔽 **Too Low:** Канал реактивний ⇒ сигнали частіші, більше хибних пробоїв.

---

### `strategies.mean_reversion.strategy.bb_num_std`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:464`
- **Mathematical Role:**
    > Множник стандартного відхилення для ширини Bollinger Bands.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Ширший канал ⇒ ціна рідше торкається границь, менше сигналів (консервативно).
    - 🔽 **Too Low:** Вужчий канал ⇒ ціна частіше пробиває границі, більше сигналів (агресивно).

---

### `strategies.mean_reversion.strategy.entry_threshold`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:535`
- **Mathematical Role:**
    > Поріг індикатора `%B` для входу. Вхід, якщо `%B < entry_threshold` (LONG) або `%B > 1 - entry_threshold` (SHORT).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Глибше входження або вхід ще до торкання межі ⇒ більше угод, нижча якість.
    - 🔽 **Too Low:** Вхід тільки при сильному пробої межі ⇒ менше угод, вища якість.

---

### `strategies.mean_reversion.strategy.rsi_window`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:469`
- **Mathematical Role:**
    > Довжина вікна для обчислення RSI (Relative Strength Index). Використовується для підтвердження oversold/overbought стану.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** RSI інертніший ⇒ менше екстремальних значень.
    - 🔽 **Too Low:** RSI реактивніший ⇒ більше хибних розворотних сигналів.

---

### `strategies.mean_reversion.strategy.rsi_oversold` / `rsi_overbought`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:548`
- **Mathematical Role:**
    > Пороги RSI для підтвердження. Якщо RSI перетинає поріг, додається `confidence_rsi_bonus`.
- **Tuning Sensitivity:**
    - 🔼 **Too High (Oversold)** / 🔽 **Too Low (Overbought):** Більша зона для формування бонусу ⇒ вищий середній confidence.

---

### `strategies.mean_reversion.strategy.confidence_base` / `confidence_bb_slope` / `confidence_rsi_bonus`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:544-550`
- **Mathematical Role:**
    > Обчислює `confidence`: `base + |%B - threshold| * bb_slope + (rsi_bonus if rsi_confirms else 0)`.
- **Tuning Sensitivity:**
    - Scalars, що безпосередньо формують підсумковий `confidence` (clamped до 1.0), який впливає на Objective Engine/ downstream scoring.

---

### `strategies.mean_reversion.strategy.min_bb_width`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:515`; `apps/reference/domains/feature_engineering/indicators.py:139`
- **Mathematical Role:**
    > Фільтр “занадто вузького” каналу: `bb.width = (upper - lower) / mid`. Якщо `width < min_bb_width` → no-trade (ризик fee-churn у dead market).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Блокує більше low-vol фаз ⇒ менше churn, але більше пропущених “дрібних” MR сетапів.
    - 🔽 **Too Low:** Дозволяє торгувати у вузьких каналах ⇒ більше noise/fees.

---

### `strategies.mean_reversion.strategy.max_bb_width`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:523`; `apps/reference/domains/feature_engineering/indicators.py:139`
- **Mathematical Role:**
    > Фільтр “занадто широкого” каналу: якщо `bb.width > max_bb_width` → no-trade (mean reversion edge деградує у високій волатильності).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дозволяє торгувати у high-vol ⇒ більше ризик/stop-outs.
    - 🔽 **Too Low:** Рано блокує ⇒ менше угод у “широких” флетах.

---

### `strategies.mean_reversion.strategy.atr_window`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:466`; `apps/reference/domains/feature_engineering/indicators.py:159`
- **Mathematical Role:**
    > ATR window для стопів і для `atr_pct = ATR/price` (класифікація FLAT_HIGH/LOW). Визначає, наскільки “довгою” є пам’ять волатильності.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** ATR інертний ⇒ стопи/класифікація режиму повільно адаптуються.
    - 🔽 **Too Low:** ATR реактивний ⇒ стопи/режим швидко стрибають (можливий churn між FLAT_*).

---

### `strategies.mean_reversion.strategy.sl_atr_mult`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:576`
- **Mathematical Role:**
    > Базовий SL множник: `sl_mult = sl_atr_mult * stop_mult(regime)`, `stop_distance = ATR_eff * sl_mult`. Керує risk per trade через дистанцію SL.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Ширші стопи ⇒ менше stop-outs, але більший risk/втрата на угоду.
    - 🔽 **Too Low:** Тісні стопи ⇒ більше stop-outs, але менший risk на одну угоду.

---

### `strategies.mean_reversion.strategy.tp_to_mid`
- **Type:** `bool`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:570`
- **Mathematical Role:**
    > Вибір базової TP-цілі:
    > - `true` ⇒ `target0 = bb.mid` (mean target)
    > - `false` ⇒ `target0 = opposite band` (LONG→upper, SHORT→lower)
    > Потім застосовується `target_mult(regime)` до дистанції від entry.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `tp_to_mid=true` ⇒ ближчий TP → вища ймовірність тейка, але нижчий reward (R:R ↓).
    - 🔽 **Too Low:** `tp_to_mid=false` ⇒ дальший TP (до протилежної смуги) → reward ↑, але winrate ↓.
- **Special Focus (R:R impact):**
    > При фіксованому SL (через `sl_atr_mult * stop_mult`) перемикання `tp_to_mid` змінює базову `TP_distance`.
    > - Mid-band TP зазвичай значно ближчий, ніж “opposite band” TP, тому `R:R = TP_distance / SL_distance` зменшується.
    > - У FLAT_HIGH `target_mult > 1` може частково компенсувати mid-TP (збільшує TP_distance), але знак ефекту `tp_to_mid` зберігається.

---

### `strategies.mean_reversion.strategy.cooldown_sec`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:483`
- **Mathematical Role:**
    > Anti-churn cooldown: після actionable сигналу стратегія ігнорує нові входи `cooldown_sec` секунд (`elapsed_sec < cooldown_sec`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Менше churn, але більше missed opportunities.
    - 🔽 **Too Low:** Більше повторних входів/пере-входів → ризик overtrading.

---

### `strategies.mean_reversion.regime_thresholds.high_vol_pct`
- **Type:** `float` *(ratio; 0.003 = 0.3% ATR/price)*
- **Logic Owner:** `FlatRegimeThresholds` (via `map_to_flat_regime`)
- **Code Reference:** `apps/reference/domains/feature_engineering/regime_mapping.py:38`; `apps/reference/domains/decision_making/mean_reversion_handler.py:311`
- **Mathematical Role:**
    > Межа для FLAT_HIGH при `regime == MEAN_REVERSION`: якщо `atr_pct > high_vol_pct` ⇒ `FLAT_HIGH`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Рідше класифікує як FLAT_HIGH ⇒ стопи/targets рідше “розширюються” (може збільшити stop-outs у реально high-vol flat).
    - 🔽 **Too Low:** Частіше FLAT_HIGH ⇒ стопи ширші/targets далі частіше (risk profile ↑).

---

### `strategies.mean_reversion.regime_thresholds.low_vol_pct`
- **Type:** `float` *(ratio; 0.001 = 0.1% ATR/price)*
- **Logic Owner:** `FlatRegimeThresholds` (via `map_to_flat_regime`)
- **Code Reference:** `apps/reference/domains/feature_engineering/regime_mapping.py:38`; `apps/reference/domains/decision_making/mean_reversion_handler.py:311`
- **Mathematical Role:**
    > Межа для FLAT_LOW при `regime == MEAN_REVERSION`: якщо `atr_pct < low_vol_pct` ⇒ `FLAT_LOW`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Частіше FLAT_LOW ⇒ частіше “low-vol” профіль (менші targets, потенційно менше edge).
    - 🔽 **Too Low:** Рідше FLAT_LOW ⇒ більше часу у FLAT_NORMAL (стандартні stops/targets).

---

### `strategies.mean_reversion.allowed_regimes`
- **Type:** `list[string]`
- **Logic Owner:** `MeanReversion1mStrategy` (strict allowlist)
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:347`; `apps/reference/domains/decision_making/mean_reversion_handler.py:337`
- **Mathematical Role:**
    > Strict allowlist по `flat_regime.name`. Якщо allowlist порожній — **allow nothing** (fail-closed).
    >
    > **Override precedence:** `mean_reversion.allowed_regimes` (global) → `mean_reversion.assets.<SYM>.allowed_regimes` → `mean_reversion.assets.<SYM>.strategy.allowed_regimes` (якщо задано). (`apps/reference/domains/decision_making/mean_reversion_handler.py:337`)
    >
    > **Valid values:** `FLAT_LOW|FLAT_NORMAL|FLAT_HIGH` (бо саме ці строки генерує `FlatRegime.name`), тому значення на кшталт `MEAN_REVERSION` у allowlist не впливають на decision (no-op).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Додає більше режимів ⇒ більше торгівлі (включно з high-vol flat).
    - 🔽 **Too Low:** Менше режимів ⇒ менше сигналів; порожній список вимикає торгівлю (fail-closed).

---

### `strategies.mean_reversion.regime_sizing.<FLAT_*>.stop_mult`
- **Type:** `float`
- **Logic Owner:** `MRParameters` → `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/regime_mapping.py:204`; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:576`
- **Mathematical Role:**
    > Regime stop multiplier: входить у `sl_mult = sl_atr_mult * stop_mult`. Вищий `stop_mult` ⇒ ширший SL у цьому flat-regime.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Менше stop-outs, але більший risk per trade.
    - 🔽 **Too Low:** Тісніший SL, більше stop-outs (але risk per trade ↓).

---

### `strategies.mean_reversion.regime_sizing.<FLAT_*>.target_mult`
- **Type:** `float`
- **Logic Owner:** `MRParameters` → `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/regime_mapping.py:234`; `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:592`
- **Mathematical Role:**
    > Regime target multiplier: масштабує дистанцію до TP: `TP_distance *= target_mult`. Вищий `target_mult` ⇒ дальший TP (R:R ↑, winrate ↓).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Дальні тейки ⇒ lower winrate, можливі пропущені тейки.
    - 🔽 **Too Low:** Ближчі тейки ⇒ higher winrate, але lower reward.

---

### `strategies.mean_reversion.regime_sizing.<FLAT_*>.sizing_mult`
- **Type:** `float`
- **Logic Owner:** `MRParameters` (emitted; not applied in strategy math)
- **Code Reference:** `apps/reference/domains/feature_engineering/regime_mapping.py:174`; `apps/reference/domains/decision_making/mean_reversion_handler.py:512`
- **Mathematical Role:**
    > `sizing_mult` не змінює entry/exit формули у `MeanReversion1mStrategy`, але передається у `EVT:STRATEGY_SIGNAL_PRODUCED.mr_params` як контекст для downstream sizing/risk orchestration.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Якщо downstream використовує multiplier — збільшення експозиції в цьому regime.
    - 🔽 **Too Low:** Консервативніша експозиція в цьому regime.

---

### `strategies.mean_reversion.timeframe_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `MeanReversionHandler` (trigger gating)
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:282`; `apps/reference/domains/decision_making/mean_reversion_handler.py:740`
- **Mathematical Role:**
    > Timeframe-SSOT для тригеру: handler обробляє лише `CMD:PROCESS_STRATEGY` з `tf_sec == timeframe_sec`. Невідповідність ⇒ skip/reject.
    >
    > `MeanReversion1mStrategy` історично “1m”, але на SSOT-архітектурі працює з будь-якими барами, які приходять через `on_bar()`; реальний TF визначає саме цей gating. (`apps/reference/domains/feature_engineering/mean_reversion_strategy.py:300`)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший TF ⇒ менше барів/сигналів, більший lag, менше noise.
    - 🔽 **Too Low:** Менший TF ⇒ більше сигналів, більше noise і навантаження.

---

## 13. Vector 1: Microstructure Veto Overlay

> **Added:** 2026-03-30 (PACK-1/2/3)
> **Hardened:** 2026-03-30 (PACK-R1: strict fail-closed)
> **Runtime Wiring:** 2026-03-30 (MR-V1-WIRING: price_motion pipeline fix + E2E proof)
> **Status:** Code complete, tests passing, `enabled: false` in YAML

### Purpose
Handler-level bivariate overlay that blocks toxic continuation signals while allowing absorption setups. Applied between `strategy.on_bar()` signal output and `_emit_signal()`.

### Architecture
- **Logic Owner:** `MeanReversionHandler._check_microstructure_veto()`
- **Config SSOT:** `config/aurora/strategies/mean_reversion.yaml → microstructure_veto`
- **Pydantic Model:** `apps/reference/config_models.py::MRMicrostructureVetoConfig`
- **NRR Code:** `NRR-060` (`MICROSTRUCTURE_VETO`)

### Decision Logic (Bivariate)

```
1. If veto disabled → ALLOW
2. If TFI missing → BLOCK (fail-closed, unconditional)
3. If TFI not numeric → BLOCK (fail-closed)
4. Compute tfi_ema via EMA smoothing (span = tfi_ema_span)
5. If insufficient bars (< readiness_min_bars) → BLOCK (warmup)
6. If |tfi_ema| < tfi_adverse_threshold → ALLOW (no adverse flow)
7. If adverse TFI detected:
   a. If OBI confirm enabled AND OBI NOT adverse → ALLOW (book doesn't confirm)
   b. Check price reaction (bar geometry + price_motion returns):
      - If wick_ratio ≥ absorption_wick_ratio_min → absorption → ALLOW
      - If price rebound ≥ absorption_rebound_threshold → absorption → ALLOW
      - If adverse continuation ≥ price_continuation_threshold → BLOCK (toxic)
      - Otherwise → BLOCK (ambiguous, fail-closed)
```

### Key Invariants
- OBI is **confirm-only**, never sole veto driver
- Missing TFI → fail-closed unconditionally (no policy branch; `"skip"` removed in R1 hardening)
- Zero-range bar → always blocked (cannot compute wick ratio)
- Absorption evidence (wick OR rebound) overrides adverse TFI

### YAML Config Fields

| Field | Type | Default | Role |
|---|---|---|---|
| `enabled` | bool | false | Master switch |
| `tfi_ema_span` | int | 5 | EMA smoothing window for raw TFI |
| `tfi_adverse_threshold` | float | 0.3 | \|TFI\| > this = adverse flow |
| `obi_confirm_enabled` | bool | false | Enable OBI as confirming factor |
| `obi_adverse_threshold` | float | 0.3 | \|OBI\| > this = adverse book state |
| `price_reaction_lookback_sec` | int | 60 | Price continuation window |
| `price_continuation_threshold` | float | 0.001 | Adverse price move = toxic |
| `absorption_wick_ratio_min` | float | 0.4 | Wick ≥ 40% range = absorption |
| `absorption_rebound_threshold` | float | 0.0005 | Favorable price move = rebound |
| `readiness_min_bars` | int | 5 | Bars before veto engages |
| `missing_policy` | "block" | "block" | Always fail-closed (R1: "skip" removed) |

### Price Motion Contract (MR-V1-WIRING)

The veto reads price reaction data from `_last_cmd_price_motion[symbol]`, a per-symbol cache populated from the **top-level** `price_motion` field in `CMD:PROCESS_STRATEGY`. This field is:
- **Computed by:** `feature_engineering.py` (lines 1769-1793, `pm_block`)
- **Emitted at:** `cmd_payload["price_motion"]` (NOT nested inside `features`)
- **Schema:** `cmd_process_strategy_v1.json` (property `price_motion`)
- **Required keys:** `ret_10s`, `ret_60s`, `ret_300s` (numeric or null)

If `price_motion` is absent from the CMD payload, the veto has no continuation/rebound evidence and blocks conservatively (ambiguous block).

### Test Coverage
- 16 helper-level tests in `tests/domains/decision_making/test_mr_microstructure_veto.py`
- 15 config contract tests in `tests/config/test_mr_microstructure_veto_config.py`
- 11 E2E tests in `tests/integration/test_mr_v1_e2e_price_motion.py` (through `_on_process_strategy`)

---

## 14. Vector 2: Directional Bias Threshold Modulation

> **Added:** 2026-03-30 (PACK-4/5/6)
> **Hardened:** 2026-03-30 (PACK-R2: semantics fix, PACK-R3: isolation proof)
> **Status:** Code complete, tests passing, `enabled: false` in YAML

### Purpose
Splits symmetric `entry_threshold` into `base_long_threshold` and `base_short_threshold`. Funding rate dynamically modulates these thresholds per bar.

### Architecture
- **Logic Owner:** `MeanReversionHandler._apply_directional_bias()`
- **Config SSOT:** `config/aurora/strategies/mean_reversion.yaml → directional_bias`
- **Pydantic Model:** `apps/reference/config_models.py::MRDirectionalBiasConfig`
- **Strategy Side:** `MRStrategyConfig.entry_threshold_long` / `entry_threshold_short` (transient overrides)

### Formula

```python
norm_funding = clamp(funding_rate / funding_normalization_scale, -1, 1)
if |norm_funding| < funding_deadband: norm_funding = 0

eff_long  = clamp(base_long  - norm_funding * shift_magnitude, clamp_min, clamp_max)
eff_short = clamp(base_short + norm_funding * shift_magnitude, clamp_min, clamp_max)
```

**Interpretation (trigger geometry, not just threshold value):**
- `LONG fires when: pct_b < long_threshold` → lower threshold = harder (needs more oversold)
- `SHORT fires when: pct_b > (1 - short_threshold)` → higher short_threshold = lower boundary = easier
- Positive funding (longs pay) → LONG harder, SHORT easier (fade the crowd)
- Negative funding (shorts pay) → LONG easier, SHORT harder (fade the crowd)

### Key Invariants
- Missing `funding_rate` → graceful degradation to static split thresholds (NO fail-closed)
- Non-numeric `funding_rate` → fallback to static thresholds
- Thresholds always clamped to `[clamp_min, clamp_max]`
- When bias not configured → overrides cleared to `None` → legacy symmetric `entry_threshold` used
- Transient: values recomputed every bar, cleared in `finally` block after `on_bar()` (R3 hardening)
- Per-symbol isolation: each symbol has its own `MeanReversion1mStrategy` + `MRStrategyConfig` instance

### YAML Config Fields

| Field | Type | Default | Role |
|---|---|---|---|
| `enabled` | bool | false | Master switch |
| `base_long_threshold` | float | 0.115 | Static %B for LONG |
| `base_short_threshold` | float | 0.115 | Static %B for SHORT |
| `funding_shift_magnitude` | float | 0.02 | Max threshold shift per unit normalized funding |
| `funding_normalization_scale` | float | 0.0003 | Normalizer: funding / this = [-1, 1] |
| `funding_deadband` | float | 0.1 | \|norm\| < this → zero (noise suppression) |
| `threshold_clamp_min` | float | 0.01 | Floor: prevents degenerate entries |
| `threshold_clamp_max` | float | 0.3 | Ceiling: prevents unreachable entries |

### Pydantic Validators
- `clamp_min < clamp_max` enforced
- `base_long_threshold` and `base_short_threshold` must be within `[clamp_min, clamp_max]`
- `extra='forbid'` prevents stray fields

### Test Coverage
- 19 tests in `tests/domains/decision_making/test_mr_directional_bias.py`
- 16 config contract tests in `tests/config/test_mr_directional_bias_config.py`

### Contract Ratification (R4, 2026-03-30)

The implemented Vector 2 contract is a **symmetric simplified model**:
- Single `funding_shift_magnitude` applies uniformly to both LONG and SHORT sides
- Single `funding_normalization_scale` and `funding_deadband` for all directions
- Symmetric clamp `[clamp_min, clamp_max]` for both sides

This is explicitly ratified as the canonical V2 contract for the following reasons:
1. No live calibration data exists to justify per-side/per-direction differentiation
2. The simplified model correctly implements "fade the crowd" economic logic
3. Adding per-side sensitivity without data would create unjustified complexity
4. The model can be extended additively to a richer contract when calibration data is available

**Rejected (deferred) extensions**:
- `funding_shift_magnitude_long` / `funding_shift_magnitude_short` (per-side sensitivity)
- `positive_funding_sensitivity` / `negative_funding_sensitivity` (per-direction sensitivity)
- Per-side clamp controls (`clamp_min_long`, `clamp_max_short`, etc.)

These may be added in a future package when live trading data supports calibration.

---

## 14a. Strategy-Level Veto: FLAT_LOW SHORT BB Width Gate

> **Added:** Per-asset hardening for narrow-band FLAT_LOW short fades

### Purpose
Optional additional BB width floor that applies ONLY to SHORT signals in FLAT_LOW regime. Prevents fading into a narrow channel where fee-churn risk dominates.

### Architecture
- **Logic Owner:** `MeanReversion1mStrategy._evaluate_signal()` (line 505-518)
- **Config SSOT:** `config/aurora/strategies/mean_reversion.yaml → assets.<SYM>.strategy.flat_low_short_min_bb_width`
- **Dataclass Field:** `MRStrategyConfig.flat_low_short_min_bb_width: Optional[Decimal] = None`

### Decision Logic
```
if regime == FLAT_LOW
   AND candidate_side == SHORT
   AND flat_low_short_min_bb_width is not None
   AND bb_width < flat_low_short_min_bb_width
   → NEUTRAL (veto: "flat_low_short_bb_width_too_narrow")
```

### Fallback
- `None` → gate disabled; generic `min_bb_width` still applies
- **Category:** Runtime fallback (None = skip gate)

---

## 14b. Strategy-Level Veto: Squeeze Expansion Veto

> **Added:** Per-asset breakout-from-squeeze fade trap protection

### Purpose
Blocks counter-trend MR fades when the BB channel is rapidly expanding out of a squeeze. Prevents entry into a breakout that looks like a BB touch but is actually a directional expansion.

### Architecture
- **Logic Owner:** `MeanReversion1mStrategy._squeeze_expansion_veto_reason()` (lines 679-718)
- **Config SSOT:** `config/aurora/strategies/mean_reversion.yaml → assets.<SYM>.strategy.squeeze_expansion_veto`
- **Pydantic Model:** `apps/reference/config_models.py::MRSqueezeExpansionVetoConfig`
- **Dataclass Field:** `MRStrategyConfig.squeeze_expansion_veto: Optional[SqueezeExpansionVetoConfig] = None`

### Decision Logic
```
1. If veto config is None or not enabled → PASS
2. If no candidate signal → PASS
3. If current flat_regime not in configured regimes → PASS
4. If candidate_side not in configured sides → PASS
5. Compute previous_bb_width from prior completed window (recomputes BB from closes[:-1])
6. If previous_bb_width is None or <= 0 → PASS (insufficient data)
7. If previous_bb_width > squeeze_width_max → PASS (wasn't in squeeze)
8. If current_bb_width > post_squeeze_width_max → PASS (already fully expanded)
9. expansion_ratio = current_bb_width / previous_bb_width
10. If expansion_ratio < expansion_ratio_min → PASS (not expanding enough)
11. → VETO: "squeeze_expansion_veto:{side}:{prev_width}->{curr_width}"
```

### YAML Config Fields

| Field | Type | Constraint | Role |
|---|---|---|---|
| `enabled` | bool | — | Master switch |
| `squeeze_width_max` | float | >0 | Previous BB width must be ≤ this (squeeze definition) |
| `post_squeeze_width_max` | float | >0, ≥ squeeze_width_max | Current BB width must be ≤ this (still expanding) |
| `expansion_ratio_min` | float | >1.0 | current/previous width ratio to trigger veto |
| `regimes` | list[str] | min_length=1 | Flat regimes where veto applies |
| `sides` | list["LONG"/"SHORT"] | min_length=1 | Signal sides where veto applies |

### Validators
- `post_squeeze_width_max >= squeeze_width_max` enforced by Pydantic `@model_validator`

### Fallback
- Per-asset only (no global). `None` → veto disabled.
- **Category:** Runtime fallback (None = skip)

---

## 14c. Strategy-Level Veto: Momentum Separation Veto

> **Added:** Per-asset late-drift counter-trend fade protection

### Purpose
Blocks MR fades when price has already drifted significantly in the same direction as the candidate trade. Prevents fading into a strong directional move that has already separated from the mean.

### Architecture
- **Logic Owner:** `MeanReversion1mStrategy._momentum_separation_veto_reason()` (lines 733-775)
- **Config SSOT:** `config/aurora/strategies/mean_reversion.yaml → assets.<SYM>.strategy.momentum_separation_veto`
- **Pydantic Model:** `apps/reference/config_models.py::MRMomentumSeparationVetoConfig`
- **Dataclass Field:** `MRStrategyConfig.momentum_separation_veto: Optional[MomentumSeparationVetoConfig] = None`

### Decision Logic
```
1. If veto config is None or not enabled → PASS
2. If no candidate signal → PASS
3. If current flat_regime not in configured regimes → PASS
4. If candidate_side not in configured sides → PASS
5. If current_bb_width < min_current_bb_width → PASS (channel not wide enough)
6. If len(closes) < lookback_bars + 1 → PASS (insufficient data)
7. drift_pct = (current_close - reference_close) / reference_close
8. If candidate_side == SHORT and drift_pct < min_drift_pct → PASS (no strong upward drift)
9. If candidate_side == LONG and drift_pct > -min_drift_pct → PASS (no strong downward drift)
10. → VETO: "momentum_separation_veto:{side}:{drift_pct}%"
```

### YAML Config Fields

| Field | Type | Constraint | Role |
|---|---|---|---|
| `enabled` | bool | — | Master switch |
| `lookback_bars` | int | ≥1 | Bars to measure drift |
| `min_drift_pct` | float | >0 | Min cumulative drift to trigger veto |
| `min_current_bb_width` | float | >0 | BB width floor before veto engages |
| `regimes` | list[str] | min_length=1 | Flat regimes where veto applies |
| `sides` | list["LONG"/"SHORT"] | min_length=1 | Signal sides where veto applies |

### Fallback
- Per-asset only (no global). `None` → veto disabled.
- **Category:** Runtime fallback (None = skip)

### Key Invariant
- Momentum separation checks **opposite direction** to candidate: SHORT veto triggers on upward drift, LONG veto triggers on downward drift. This is the "don't fade a strong directional move" logic.

---

## 15. Defaults vs Fallbacks vs Hardcoded Policies

> Full matrix: `reports/MR_DEFAULTS_FALLBACKS_MATRIX.md`

### Summary of Category Distribution

| Category | Count | Examples |
|---|---|---|
| **YAML default** (operator-configurable) | ~30 core params + per-asset | `bb_window`, `entry_threshold`, `timeframe_sec` |
| **Pydantic default** (configurable, has fallback) | 6 | `confidence_base`, `confidence_bb_slope`, `confidence_rsi_bonus`, `system_stress_policy`, `score_multiplier`, `tfi_ema_span` |
| **Required / no default** | ~15 | `enabled`, `timeframe_sec`, `bb_window`, `entry_threshold`, `allowed_regimes` |
| **Runtime fallback** | 5 | Per-asset strategy overrides (`None` → global), per-asset liquidity/veto/bias (`None` → global) |
| **Graceful degradation** | 2 | Missing funding → static split thresholds; invalid funding → same |
| **Fail-closed** | 6 | Missing TFI, invalid TFI, zero-range bar, ambiguous case, missing OBI (when enabled), missing price_motion + adverse TFI |
| **Hardcoded policy** | 8 | OBI confirm-only, EMA formula, return key selection, absorption OR logic, clamp formula, per-symbol isolation, transient clearing, price_motion top-level contract |
| **Dormant default** | 4 | `microstructure_veto.enabled: false`, `directional_bias.enabled: false`, disabled assets (BTC/XRP/ETH/SOL) |

### Key Distinctions for Operators

1. **"Missing funding" is graceful degradation, NOT fail-closed.** V2 continues with static thresholds. No error, no reject.
2. **"Missing TFI" is fail-closed, NOT graceful degradation.** V1 blocks unconditionally. There is no "skip" policy anymore.
3. **OBI confirm-only is a code policy, NOT a config knob.** `obi_confirm_enabled` controls whether OBI is consulted, but OBI can never be the sole veto driver regardless of config.
4. **Per-asset overrides are runtime fallbacks.** `None` in per-asset means "use global". This is not a default — it's a two-level resolution chain.
5. **`MRStrategyConfig` dataclass defaults are test-only.** Production never uses them; handler always injects explicit YAML values.

---

## 16. Dormant vs Enabled Runtime Truth

> **Date of verification:** 2026-03-31

| Component | Status | Evidence |
|---|---|---|
| `mean_reversion` strategy | **ACTIVE** for DOGEUSDT | strategies.yaml:41, `mean_reversion.enabled: true`, `DOGEUSDT.enabled: true` |
| `mean_reversion` strategy for BTCUSDT | **DORMANT** | `BTCUSDT.enabled: false` in mean_reversion.yaml:193 |
| `mean_reversion` strategy for XRPUSDT | **DORMANT** | `XRPUSDT.enabled: false` |
| `mean_reversion` strategy for ETHUSDT | **DORMANT** | `ETHUSDT.enabled: false` |
| `mean_reversion` strategy for SOLUSDT | **DORMANT** | `SOLUSDT.enabled: false` |
| Vector 1 (Microstructure Veto) | **DORMANT** | `microstructure_veto.enabled: false` |
| Vector 2 (Directional Bias) | **DORMANT** | `directional_bias.enabled: false` |
| Safety gates | **OFF** | `safety_gates.enabled: false` (MR is counter-trend) |
| Objective engine | **ON** (OBSERVE mode) | `objective.enabled: true`, all gates `enforcement_mode: "OBSERVE"` |

### What "Dormant" means operationally

- **Code is deployed** — all V1/V2 logic is in the handler and tested.
- **Config exists on disk** — all YAML fields are present with validated values.
- **Not running** — `enabled: false` means the handler skips the subsystem entirely.
- **Zero risk** — dormant code does not affect live trading until operator sets `enabled: true`.

---

## 17. Stale Statements Corrected in This Actualization

| Statement | Location | Correction |
|---|---|---|
| "live assignments для mean_reversion відсутні" | passport Sections 2, 10 | DOGEUSDT IS assigned (strategies.yaml:41) |
| "ConfigLoader не live-loadить config.strategies.mean_reversion" | passport Section 2 | It IS loaded; DOGEUSDT is active |
| V1 decision logic "If TFI missing & policy=block" | passport Section 13 | `policy` is always `"block"` (R1 Literal constraint); conditional language removed |
| V1 decision logic ordering (TFI check after readiness) | passport Section 13 | TFI check is BEFORE readiness check in actual code (handler.py:670-692) |
| V2 Pydantic docstring "positive funding → SHORT stricter, LONG easier" | config_models.py:600 | Inverted; corrected to "LONG harder, SHORT easier" |
