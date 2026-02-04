# State Machine Passport: `config/aurora/strategies/mean_reversion.yaml` (Phase 8)

Цей паспорт описує **state machine** стратегії Mean Reversion: як `MeanReversion1mStrategy` обробляє бари (`on_bar`) і як `MeanReversionHandler` оркеструє тригер/гейти та емісію `EVT:STRATEGY_SIGNAL_PRODUCED`.

**Critical Consumers (Trace Targets):**
1. **State Machine:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py` (`MeanReversion1mStrategy`)
2. **Handler:** `apps/reference/domains/decision_making/mean_reversion_handler.py`
3. **Indicators:** `apps/reference/domains/feature_engineering/indicators.py` (`compute_bollinger_bands`, `compute_atr`, `compute_rsi`)
4. **Regime Mapping:** `apps/reference/domains/feature_engineering/regime_mapping.py` (`map_to_flat_regime`, `MRParameters`)

**Дата генерації:** `2026-02-03`

---

### `entry_logic` (Synthesis)
* **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:300` (`MeanReversion1mStrategy.on_bar`); `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:491` (`_evaluate_signal`); `apps/reference/domains/feature_engineering/indicators.py:90` (`compute_bollinger_bands`)
* **Condition:** `IF (pct_b < entry_threshold) THEN BUY` ; `IF (pct_b > 1 - entry_threshold) THEN SELL`
    ```text
    # Gating order (fail-closed style)
    on_bar(symbol, bar):
      state.bars += bar
      if len(bars) < min_bars:                 return NEUTRAL("insufficient_bars")
      update_indicators(bb, atr, rsi)
      if in_cooldown(last_signal_ts):          return NEUTRAL("cooldown")

      flat_regime = map_to_flat_regime(regime, atr_pct, thresholds)
      if flat_regime is None:                  return NEUTRAL("regime_not_flat:*")
      if flat_regime.name not in allowed_regimes:
                                                return NEUTRAL("regime_not_allowed:*")

      if bb is None:                           return NEUTRAL("no_bb")
      if bb.width < min_bb_width:              return NEUTRAL("bb_width_too_narrow")
      if bb.width > max_bb_width:              return NEUTRAL("bb_width_too_wide")

      pct_b = (close - bb.lower) / (bb.upper - bb.lower)   # can be <0 or >1
      if pct_b < entry_threshold:               emit LONG (side=BUY)
      else if pct_b > (1 - entry_threshold):    emit SHORT (side=SELL)
      else:                                     return NEUTRAL("no_signal")

      # RSI is NOT a hard gate: it only increases confidence when extreme.
    ```

---

### `exit_logic` (Synthesis)
* **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:570` (`_evaluate_signal`)
* **Condition:** `Signal emits static stop_price/target_price (no time-based exit in strategy)`
    ```text
    entry_price = close

    # Base TP anchor:
    # - tp_to_mid=true  => target = bb.mid
    # - tp_to_mid=false => target = opposite band (LONG->bb.upper, SHORT->bb.lower)
    target0 = bb.mid if tp_to_mid else (bb.upper for LONG, bb.lower for SHORT)

    # Stop:
    sl_mult = sl_atr_mult * stop_mult(regime)            # stop_mult from regime_sizing
    atr_eff = atr if atr else (bb.upper - bb.lower) / 4  # fallback if ATR missing
    stop = entry ± atr_eff * sl_mult                     # - for LONG, + for SHORT

    # Target:
    target = entry ± (|target0 - entry| * target_mult(regime))  # target_mult from regime_sizing

    # Optional buffers (if configured via YAML): widen stop/target by % of entry
    stop   ±= entry * sl_buffer_pct
    target ±= entry * tp_buffer_pct
    ```
* **Note:** `max_hold_sec` (timeout) не реалізований у `MeanReversion1mStrategy`/`MeanReversionHandler`; якщо є forced-exit таймер — це вже зона ExecutionPosition/ManageFlow, не цього state machine.

---

### `regime_filtering` (Synthesis)
* **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:335` (`on_bar`); `apps/reference/domains/feature_engineering/regime_mapping.py:77` (`map_to_flat_regime`)
* **Condition:** `Trade only when Aurora regime maps to FlatRegime AND is allowlisted`
    ```text
    map_to_flat_regime(regime):
      TREND_*         => None
      HIGH_VOLATILITY => None
      UNCERTAIN       => None
      LOW_VOLATILITY  => FLAT_LOW
      MEAN_REVERSION  => classify by atr_pct using (low_vol_pct, high_vol_pct)

    allowlist check:
      if flat_regime.name not in allowed_regimes => NO TRADE
      # Important: empty allowed_regimes => allow nothing (explicit fail-closed).
    ```
* **Wiring Detail:** Regime filter застосовується **після** оновлення індикаторів (бо `atr_pct` залежить від ATR), але **до** обчислення entry signal (до `%B`/RSI логіки). (`apps/reference/domains/feature_engineering/mean_reversion_strategy.py:325`)

---

### `activation_wiring` (Synthesis)
* **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:214` (`MeanReversionHandler._parse_config`); `apps/reference/domains/decision_making/mean_reversion_handler.py:697` (`_on_process_strategy`)
* **Condition:** `Strategy runs only for (assigned ∩ enabled) symbols, and only on CMD:PROCESS_STRATEGY(tf_sec == timeframe_sec)`
    ```text
    enabled_symbols = {sym | sym has "mean_reversion" in strategies_registry.assignments[sym]}
                     ∩ {sym | mean_reversion.assets[sym].enabled == true}

    # Hard fail-closed checks:
    if assigned_symbols non-empty and mean_reversion config missing => raise
    if assigned_symbols non-empty and mean_reversion.enabled == false => raise
    if any assigned symbol missing/disabled in mean_reversion.assets => raise

    # Runtime trigger:
    on CMD:PROCESS_STRATEGY:
      if tf_sec missing => reject
      if tf_sec != mean_reversion.timeframe_sec => skip
      if bar_close_ts missing => reject
      if bar missing => reject
      run MeanReversion1mStrategy.on_bar(...)
      if signal actionable and liquidity gate passes (if configured) => emit EVT:STRATEGY_SIGNAL_PRODUCED
    ```

---

### `strategies.mean_reversion.enabled`
- **Type:** `bool`
- **Logic Owner:** `MeanReversionHandler`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:244`
- **Mathematical Role:**
    > Global kill-switch. Важливо: активація стратегії є SSOT-driven через `strategies_registry.assignments`, але якщо MR призначена (assigned) і `enabled=false`, handler **падає fail-closed** (SSOT conflict).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ дозволяє MR працювати (але тільки для assigned symbols).
    - 🔽 **Too Low:** `false` ⇒ hard-stop (і навіть `raise` при наявності assignments).

---

### `strategies.mean_reversion.assets.<SYM>.enabled`
- **Type:** `bool`
- **Logic Owner:** `MeanReversionHandler`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:261`
- **Mathematical Role:**
    > Per-asset enable. Якщо символ assigned у registry, але відсутній або `enabled=false` в `mean_reversion.assets`, handler робить **fail-closed raise** (щоб не було “silent disable” на assigned символі).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ символ може торгуватись (за умови assignment).
    - 🔽 **Too Low:** `false` ⇒ символ вимикається, але assignment тоді стає помилкою конфігу (fail-closed).

---

### `strategies.mean_reversion.assets.<SYM>.strategy.*` (override semantics)
- **Type:** `object`
- **Logic Owner:** `MeanReversionHandler` → `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/decision_making/mean_reversion_handler.py:321`
- **Mathematical Role:**
    > Override-ланцюжок параметрів state machine: handler будує `MRStrategyConfig` як `global strategy defaults` → `asset.strategy overrides` (лише явно задані поля) і передає в `MeanReversion1mStrategy`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Агресивні overrides (нижчі пороги/вужчі фільтри) ⇒ більше сигналів, більше noise/churn.
    - 🔽 **Too Low:** Консервативні overrides ⇒ менше сигналів, більше missed opportunities.

---

### `strategies.mean_reversion.execution.entry_order_type`
- **Type:** `string`
- **Logic Owner:** `DecisionMaking` (ORDER-POLICY-01)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3142`
- **Mathematical Role:**
    > Політика entry-ордера для стратегії (fail-closed якщо відсутня): `MARKET` або `LIMIT`. Для MR в SSOT задано `MARKET` (швидкий mean-reversion entry, але гірший контроль ціни).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `MARKET` ⇒ швидкий fill, але slippage risk ↑.
    - 🔽 **Too Low:** `LIMIT` ⇒ контроль ціни ↑, але risk missed fill ↑.

---

### `strategies.mean_reversion.execution.entry_tif`
- **Type:** `string|null`
- **Logic Owner:** `DecisionMaking` (ORDER-POLICY-01)
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:3142`
- **Mathematical Role:**
    > Time-in-force для LIMIT entries. Для `MARKET` зазвичай `null`/ignored. Якщо MR буде переведена на `LIMIT`, TIF стає обовʼязковим.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш агресивний TIF (IOC/FOK) ⇒ менше hanging orders, але більше rejects.
    - 🔽 **Too Low:** Пасивний TIF (GTC/GTX) ⇒ більше шансів maker, але більше ризик зависання.

---

### `strategies.mean_reversion.safety_gates.enabled`
- **Type:** `bool`
- **Logic Owner:** `DecisionMaking`
- **Code Reference:** `apps/reference/domains/decision_making/decision_making.py:2699`
- **Mathematical Role:**
    > DM-SAFETY-BYPASSES-P1: якщо `true`, DecisionMaking застосовує directional sanity + price-motion gates перед OPEN. Для mean reversion (контртренд) у SSOT зазвичай `false`, щоб не блокувати контртрендові входи. Missing block ⇒ fail-closed reject.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ більше safety, але менше MR угод (може системно “вбити” сигнал).
    - 🔽 **Too Low:** `false` ⇒ більше угод, але вище ризик входу “проти сильного руху”.

---

### `strategies.mean_reversion.strategy.bb_window`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:458`; `apps/reference/domains/feature_engineering/indicators.py:90`
- **Mathematical Role:**
    > Window SMA/STD для Bollinger Bands: `mid = SMA(close, bb_window)`, `upper/lower = mid ± bb_num_std * STD(close, bb_window)`. Впливає на ширину каналу і на `%B`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Повільніший mid/std ⇒ рідші входи, менше noise, але більше lag (гірша реакція на швидкі mean-reversion).
    - 🔽 **Too Low:** Швидший mid/std ⇒ часті входи, але більше false positives у шумі.

---

### `strategies.mean_reversion.strategy.bb_num_std`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:458`; `apps/reference/domains/feature_engineering/indicators.py:134`
- **Mathematical Role:**
    > Визначає ширину Боллінджера: `upper/lower = mid ± num_std * std`. Більше значення ⇒ ширші смуги ⇒ важче дістатись екстремів `%B`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Рідші входи; ловить лише екстремальні відхилення (може зменшити churn).
    - 🔽 **Too Low:** Часті входи; ризик торгувати “всередині шуму” (менше edge).

---

### `strategies.mean_reversion.strategy.entry_threshold`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:530`; `apps/reference/domains/feature_engineering/indicators.py:142`
- **Mathematical Role:**
    > Симетричний поріг по `%B`:
    > - `BUY` якщо `%B < entry_threshold`
    > - `SELL` якщо `%B > 1 - entry_threshold`
    > де `%B = (close - lower) / (upper - lower)`; може бути `<0` (нижче lower) або `>1` (вище upper).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Тригер ближче до середини каналу ⇒ більше trades, але слабший mean-reversion edge.
    - 🔽 **Too Low:** Тригер ближче до країв/за межами ⇒ менше trades, але “чистіші” екстреми.

---

### `strategies.mean_reversion.strategy.rsi_window`
- **Type:** `int`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:479`; `apps/reference/domains/feature_engineering/indicators.py:203`
- **Mathematical Role:**
    > RSI в MR — це **confidence booster**, не hard gate: якщо RSI екстремальний, confidence +0.2. Вікно визначає гладкість RSI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** RSI більш інертний ⇒ менше “екстремних підтверджень”, але стабільніше.
    - 🔽 **Too Low:** RSI більш реактивний ⇒ більше підтверджень, але більше noise.

---

### `strategies.mean_reversion.strategy.rsi_oversold`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:545`
- **Mathematical Role:**
    > Якщо `rsi < rsi_oversold`, confidence збільшується (`+0.2`) для LONG сигналу. Не блокує входи при відсутності підтвердження.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** “Oversold” спрацьовує частіше ⇒ confidence частіше підвищується (може викривити downstream використання score/confidence).
    - 🔽 **Too Low:** Підтвердження рідше ⇒ confidence ближче до базової (менше “підсилення”).

---

### `strategies.mean_reversion.strategy.rsi_overbought`
- **Type:** `float`
- **Logic Owner:** `MeanReversion1mStrategy`
- **Code Reference:** `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:556`
- **Mathematical Role:**
    > Якщо `rsi > rsi_overbought`, confidence збільшується (`+0.2`) для SHORT сигналу. Не блокує входи.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** “Overbought” спрацьовує частіше ⇒ частіше підсилення confidence.
    - 🔽 **Too Low:** Рідкі підтвердження ⇒ confidence рідше підсилюється.

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
