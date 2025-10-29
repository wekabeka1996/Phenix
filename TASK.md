

Будь ласка, виконай наступні завдання для рефакторингу логіки та посилення XAI (Explainability) у доменах `decision_making` та `execution_position`.

**Мета:** Привести код у відповідність до принципів "Explain Everything" (XAI) та "Clean Code", підготувавши його до майбутніх розширень логіки сайзингу.

-----

**Завдання 1: Рефакторинг логіки сайзингу в `decision_making.py`**

**Мета:** Ізолювати поточну спрощену логіку розрахунку розміру позиції в окрему функцію для полегшення майбутньої заміни на Kelly/CVaR.

1.  **Файл:** `apps/reference/domains/decision_making/decision_making.py`

2.  **Створи новий приватний метод** у класі `DecisionMaking` (або статичну функцію, якщо не потрібен `self`): `_calculate_simple_position_size_usd`.

3.  **Перенеси** поточну логіку розрахунку `final_pos_size_usd` з методу `_calculate_position_size` у цей новий метод.

    *Логіка для перенесення (приблизно):*

    ```python
    # ... (отримання equity, self.liq_cap_usd) ...
    final_pos_size_usd = min(self.liq_cap_usd, equity * decimal.Decimal('0.1')) # Спрощений сайзинг

    if final_pos_size_usd < self.min_pos_size_usd:
        return None, f"position size {final_pos_size_usd} is below minimum {self.min_pos_size_usd}"

    return final_pos_size_usd, f"pos_size_usd={final_pos_size_usd:.2f} (simple 10% equity cap)"
    ```

4.  **Зміни метод `_calculate_position_size`** так, щоб він викликав `_calculate_simple_position_size_usd` для отримання `final_pos_size_usd`. Решта логіки (розрахунок `qty` з `price`, округлення `step_size`) має залишитися в `_calculate_position_size`.

    *Приклад `_calculate_position_size` (після рефакторингу):*

    ```python
    def _calculate_position_size(self, symbol: str, price: decimal.Decimal, side: str, context: dict) -> tuple[Optional[decimal.Decimal], str]:
        portfolio = context['portfolio']
        equity = decimal.Decimal(str(portfolio.get('equity', '0')))
        
        # Виклик нової ізольованої функції
        final_pos_size_usd, why_sizing = self._calculate_simple_position_size_usd(equity)
        
        if final_pos_size_usd is None:
            return None, why_sizing

        # ... (решта логіки: отримання step_size, розрахунок qty, округлення, перевірка rounded_qty > 0) ...

        return rounded_qty, why_sizing
    ```

-----

**Завдання 2: Посилення XAI в `decision_making.py`**

**Мета:** Надати чіткі, машиночитні `why` рядки, що пояснюють рішення, згідно з Конституцією.

1.  **Файл:** `apps/reference/domains/decision_making/decision_making.py`
2.  **Онови метод `_make_decision_for_symbol`:**
      * При відхиленні сигналу (Neutral):
          * **Було:** `self.logger.info(f"Trade intent for {symbol} rejected: Neutral signal score {signal_score:.4f}")`
          * **Зміни:** `self.logger.info(f"REJECT: Neutral signal {signal_score:.4f} (Threshold: {signal_threshold})")`
      * При відхиленні через режим:
          * **Було:** `self.logger.info(f"Trade intent for {symbol} ({side}) rejected by regime filter (current regime: {current_regime}).")`
          * **Зміни:** `self.logger.info(f"REJECT: Counter-trend {side} blocked by regime {current_regime}")`
3.  **Онови метод `_propose_trade_intent`:**
      * **Мета:** Сформувати деталізований масив `why`.

      * **Було:** `trade_intent = { ... "why": [why], ... }`

      * **Зміни:** Замість передачі `why` як аргументу, збери його тут з контексту (який вже є у `_make_decision_for_symbol` і передається в `_calculate_position_size`, але для `_propose_trade_intent` знадобиться більше деталей).

      * *Рефакторинг (Альтернатива):* Найкраще буде збирати `why_chain` у `_make_decision_for_symbol` і передавати його в `_propose_trade_intent`.

      * **Давай зробимо так:**

          * У `_make_decision_for_symbol`, де розраховується `signal_score`, додай `why_chain.append(f"Signal {signal_score:.4f} vs Threshold {signal_threshold}")`.
          * `why_sizing` (з `_calculate_position_size`) вже додається до `why_chain`.
          * У `_propose_trade_intent`, зміни параметр `why: str` на `why_chain: list[str]`.
          * **Було (в `_propose_trade_intent`):** `"why": [why]`
          * **Стало (в `_propose_trade_intent`):** `"why": why_chain`
          * Переконайся, що `_make_decision_for_symbol` тепер викликає `self._propose_trade_intent(..., why_chain=why_chain, ...)`

-----

**Завдання 3: Посилення XAI в `fsm_open.py`**

**Мета:** Замінити загальні коди помилок на специфічні, згідно з Конституцією (XAI).

1.  **Файл:** `apps/reference/domains/execution_position/fsm_open.py` (клас `OpenFlowFSM`).
2.  **Онови метод `handle` (у разі успіху):**
      * **Було:** `dec = Message( ... why="OPEN_OK", ... )`
      * **Стало:** `dec = Message( ... why="Open guards passed", ... )`
3.  **Онови метод `handle` (у разі відмов `_reject`):**
      * Заміни всі виклики `self._reject(msg, "OPEN_GUARD_FAIL", ...)` на специфічні `why` коди:
      * **Відсутні поля:**
          * **Було:** `return self._reject(msg, "OPEN_GUARD_FAIL", "missing symbol or side")`
          * **Стало:** `return self._reject(msg, "GUARD_MISSING_FIELDS", "missing symbol or side")`
      * **Мін. кількість:**
          * **Було:** `return self._reject(msg, "OPEN_GUARD_FAIL", f"qty below minimum {min_qty}")`
          * **Стало:** `return self._reject(msg, "GUARD_MIN_QTY", f"qty {qty_dec} below minimum {min_qty}")`
      * **Ціна для LIMIT:**
          * **Було:** `return self._reject(msg, "OPEN_GUARD_FAIL", "LIMIT order requires price")`
          * **Стало:** `return self._reject(msg, "GUARD_MISSING_PRICE", "LIMIT order requires price")`
      * **Мін. вартість (Notional):**
          * **Було (LIMIT):** `return self._reject(msg, "OPEN_GUARD_FAIL", f"notional {notional} < {min_notional}")`
          * **Стало (LIMIT):** `return self._reject(msg, "GUARD_MIN_NOTIONAL", f"notional {notional} < {min_notional}")`
          * **Було (MARKET):** `return self._reject(msg, "OPEN_GUARD_FAIL", f"estimated notional {notional} < {min_notional}")`
          * **Стало (MARKET):** `return self._reject(msg, "GUARD_MIN_NOTIONAL", f"estimated notional {notional} < {min_notional}")`
      * **Кулдаун:**
          * **Було:** `return self._reject(msg, "OPEN_GUARD_FAIL", "cooldown active")`
          * **Стало:** `return self._reject(msg, "GUARD_COOLDOWN", "cooldown active")`
      * *(`IDEMPOTENCY_FAIL` та `MAX_ORDERS_REACHED` вже мають бути коректними з попередніх кроків).*

-----

**Завдання 4: Валідація та Оновлення Журналів**

1.  **Запусти всі тести** (`pytest`), щоб переконатися, що рефакторинг не зламав існуючу логіку (особливо тести для `fsm_open.py` та `decision_making.py`).
2.  **Додай запис** до `docs/Хазяйство/JOURNAL_мій.md`:
    ```markdown
    ## 2025-10-29 | RID: DEBUG_EXEC_LOGIC_REFACTOR_P4 | Крок 4: Рефакторинг логіки та посилення XAI

    **WHY:** Покращити читабельність коду сайзингу та деталізувати `why` поля для рішень та відмов, згідно з Конституцією FSM (XAI).
    **ACTION:**
        1. `decision_making.py`: Винесено логіку розрахунку `final_pos_size_usd` в окремий метод `_calculate_simple_position_size_usd` для майбутньої заміни.
        2. `decision_making.py`: Покращено `why_chain` для `EVT:TRADE_INTENT_PROPOSED`, включено деталі про сигнал та сайзинг.
        3. `fsm_open.py`: Замінено загальний `why="OPEN_GUARD_FAIL"` на специфічні коди (`GUARD_MISSING_FIELDS`, `GUARD_MIN_QTY`, `GUARD_MIN_NOTIONAL`, `GUARD_COOLDOWN`).
    **VALIDATION:** Всі `pytest` тести проходять.
    **STATUS:** ✅ **ЗАВЕРШЕНО**
    **NEXT:** Завершення фази дебагінгу.
    ```
3.  **Онови `TODO.md`**, позначивши `DEBUG_EXEC_LOGIC_REFACTOR_P4` як виконаний.

Дякую\!