# AURORA TF MODE SPEC 002

## 1. Current Behavior (Hybrid Implicit)

Станом на зараз, система працює в режимі **Implicit Hybrid**:

*   **Tick Features:** `FeatureEngineering` емітить події `EVT:FEATURES_CALCULATED` на кожному тіку без поля `tf_sec` (воно відсутнє в payload).
*   **Bar Features:** `FeatureEngineering` емітить події раз на 300с (5хв) з полем `"tf_sec": 300`.
*   **Handler Logic:**
    ```python
    tf_sec = event.get("tf_sec")
    if tf_sec and tf_sec != self.timeframe_sec: return
    ```
    *   Тіки (tf_sec=None) -> `if None` -> False -> **PASS**.
    *   Бари (tf_sec=300) -> `if 300 != 300` -> False -> **PASS**.
    *   Інші бари (напр. 1m) -> `if 60 != 300` -> True -> **REJECT**.

**Результат:** Стратегія оцінює вхід **на кожному тіку** + додатково на закритті бару.

## 2. Risks (Ризики)

1.  **Entry Noise (Шум входів):** Вхід може відбутися на випадковому тіку всередині 5-хвилинної свічки, коли ціна "смикнулася", але до кінця свічки сигнал зникне. Це класична помилка "intra-bar entry" для стратегій, тренованих/базованих на close prices.
2.  **Log Spam / Overhead:** Ядро запускається 20-30 разів на секунду (залежно від тіків), генеруючи логі та навантаження, хоча рішення про вхід має прийматися рідко.
3.  **Whipsaw Losses:** Швидкий вхід на тіку і швидкий стоп/розворот на наступному тіку (ping-pong), який ми намагаємося лікувати " милицями" типу `REENTRY_COOLDOWN`. Краще лікувати причину.

## 3. Recommended Mode: BAR_ONLY_ENTRIES

Ми обираємо режим, де **ВХІД (Entry)** дозволений виключно на закритті бару (Bar Close), але **ВИХІД (Exit/Manage)** дозволений на будь-якому тіку.

*   **Tick Context:** Дозволяє оновлювати internal state, трекати Stops/TP, Reduce-only closes.
*   **Bar Context:** Дозволяє відкривати нові позиції (Entry) та робити розвороти (Flip).

## 4. Minimal Patch Spec (План змін)

### A. Configuration (`config/aurora/strategies/aurora.yaml`)

Додати нову секцію `cadence` в `decision`:

```yaml
metrics: ...
decision:
  # ... existing config ...
  cadence:
    mode: "bar_only"          # bar_only | tick_only | hybrid_explicit
    entry_tf_sec: 300         # Timeframe required for entries
    allow_tick_entries: false # Explicit override flag (safer default: false)
```

### B. Logic (`apps/reference/domains/decision_making/aurora_handler.py`)

Додати метод `_check_cadence_gate` і викликати його перед генерацією `TRADE_INTENT`.

```python
    def _check_cadence_gate(self, symbol: str, signal_side: str, tf_sec: int | None) -> bool:
        """
        Returns TRUE if action should be BLOCKED due to cadence rules.
        """
        cadence_cfg = self.config.strategies.aurora.decision.cadence
        mode = cadence_cfg.mode  # "bar_only"
        
        # Determine strictness
        is_entry = (self._symbol_states[symbol].position_side == "") and (signal_side != "")
        is_flip = (self._symbol_states[symbol].position_side != "") and (signal_side != "") and (signal_side != self._symbol_states[symbol].position_side)
        
        # Only block Entries and Flips (allow exits/holds)
        if not (is_entry or is_flip):
            return False

        if mode == "bar_only":
            required_tf = cadence_cfg.entry_tf_sec # 300
            
            # If this is a tick (tf_sec is None) or wrong bar -> BLOCK
            if tf_sec != required_tf: # None != 300 is True
                # Log once per N ticks to avoid spam? Or just return True silently?
                # Better: return True and let caller decide specific logging (e.g. debug only)
                return True
                
        return False
```

Вставити виклик у `_on_signal_produced` або `_process_scoring_result`:

```python
        # ... calculated score ...
        result = self._scoring_kernel.calculate(...)
        
        # CADENCE GATE
        if self._check_cadence_gate(symbol, result.side, tf_sec):
            if result.side: # If it wanted to trade
                self.logger.debug(f"[{symbol}] CADENCE: Blocked entry on tick (bar_only mode)")
                # Force neutral result effectively blocking entry
                result.side = "" 
                result.score = 0.0
                return # Stop processing
```

### C. Test Plan

1.  **Test Tick Entry Block:**
    *   Setup: `mode="bar_only"`, position=Flat.
    *   Input: Tick event (`tf_sec=None`) with strong signal features.
    *   Expect: **No Trade Intent**. Logs show "CADENCE: Blocked".

2.  **Test Bar Entry Pass:**
    *   Setup: `mode="bar_only"`, position=Flat.
    *   Input: Bar event (`tf_sec=300`) with strong signal.
    *   Expect: **Trade Intent Proposed**.

3.  **Test Tick Exit Pass:**
    *   Setup: `mode="bar_only"`, position=LONG.
    *   Input: Tick event (`tf_sec=None`) with SHORT/NEUTRAL signal (Exit).
    *   Expect: **Trade Intent Proposed (Close/Reduce)**.

4.  **Test Flip Block on Tick:**
    *   Setup: `mode="bar_only"`, position=LONG.
    *   Input: Tick event with strong SHORT signal.
    *   Expect: **Blocked** (Flip is technically Entry of new side). Or maybe allow Close-only? 
    *   *Decision:* Strict bar_only blocks Flips on ticks. It should ideally trigger Close-only (reduce), but simpler to just block whole flip until bar close. Or better: **Downgrade Flip to Close**. (Це складніше, для MVP просто блок).

---
