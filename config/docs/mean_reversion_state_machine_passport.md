# Code-Driven State Machine Passport: `config/aurora/strategies/mean_reversion.yaml`

Цей паспорт описує лише поточний live/runtime контракт state machine для `mean_reversion`: де закінчується власне bar-based стратегія і де починаються handler overlays та downstream execution.

Owner surface:
- Strategy state machine: `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- Runtime orchestration: `apps/reference/domains/decision_making/mean_reversion_handler.py`
- Plugin wiring: `apps/reference/domains/strategies/plugins/mean_reversion.py`
- Typed contract: `apps/reference/config_models.py::MeanReversion1mStrategyConfig`

## 1. Головна корекція паспорта

Старий документ застряг у змішаній термінології `1m/3m/Phase 8`, але поточний live YAML задає:
- `timeframe_sec: 300`
- registry assignment для `mean_reversion` зараз лише на `DOGEUSDT`

Тобто поточний live path такий:
- клас усе ще називається `MeanReversion1mStrategy`
- деякі handler/docstring comments усе ще кажуть `1m` або `3m`
- але реально активний runtime profile зараз 5m (`300s`), і саме він є live TF SSOT

## 2. Activation SSOT

`mean_reversion` активується не просто через `enabled=true`, а через assignment-first контракт:
- `config/aurora/strategies.yaml` визначає, які symbols assigned до `mean_reversion`
- `MeanReversionHandler._parse_config()` бере фінальний universe як `assigned ∩ assets.enabled`

Поточний live assignment:
- `DOGEUSDT`

Fail-closed інваріанти при assignment:
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
- встановлює regime з payload або з внутрішнього кешу
- викликає `strategy.on_bar(symbol, bar, ts_ms)`
- якщо signal actionable і liquidity gate проходить, емить `EVT:STRATEGY_SIGNAL_PRODUCED`

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
- `DOGEUSDT` є єдиним live symbol через assignment
- `DOGEUSDT.strategy.min_bb_width=0.005`

Для incident context це важливо:
- strategy-level вхід у squeeze breakout справді може бути «правильним за кодом», якщо `bb_width > 0.005`
- downstream execution split-brain після цього вже не є частиною MR state machine

## 11. Drift, виявлений аудитом

- Імена та comments у codebase частково застарілі: `MeanReversion1mStrategy`, `Mean Reversion 3m strategy`, старі Phase B/T2B описи. Live TF SSOT зараз 300s.
- Старий integration файл `tests/integration/test_mean_reversion_handler_event_contract_v1.py` позначений `skip` і досі прив'язаний до старого tick-based path. Це не слід використовувати як джерело істини.
- Старий паспорт переоцінював “strategy-owned” зони і недостатньо чітко відділяв їх від execution FSM layer.

## 12. Підсумок

Поточна `mean_reversion` state machine є bar-driven mean-reversion логікою, яка:
- працює на live 5m bars
- приймає рішення через `%B`, BB width, flat regime mapping, cooldown та confidence boosts
- не володіє execution lifecycle
- передає downstream уже збагачений handler-ом payload

Правильна ментальна модель така:
- `MeanReversion1mStrategy` = math/state
- `MeanReversionHandler` = activation + contract gates + enrichment + emission
- `ExecPosFSM/ManageFlowFSM` = execution/state reconciliation, де й живуть incident-класи типу `ORDER_UPDATED` desync

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
