# Aggregated OCO – SOLUSDT Position Amplification Notes

**Date:** 2025‑11‑19  
**Scope:** Deeper investigation of SOLUSDT position growth and the interaction between `ManageFlowFSM` and `ExecutionQtyGuard` in the `execution_position` domain, without changing tests.

---

## 1. Context & Symptoms

- Historical behaviour (from your description and incident docs):
  - Initial bug: SOLUSDT position “quickly scaled” by +1 SOL steps.
  - Second bug: increments of +10 SOL.
  - Third bug: a single jump to ~181 SOL.
- These effects are *position size* changes, not just TP/SL sizes.
- You already traced the problem space to:
  - `apps/reference/domains/execution_position/fsm_manage.py`
  - `apps/reference/domains/execution_position/qty_guard.py`

Key question: can `ManageFlowFSM` + `ExecutionQtyGuard` themselves inflate position size, or are they just adjacent to the real source (OpenFlow / ExecPos orchestration)?

---

## 2. What ExecutionQtyGuard Actually Does

Path: `apps/reference/domains/execution_position/qty_guard.py`

- `ExecutionQtyGuard.evaluate(symbol, qty, price=None)`:
  - Converts `qty` to `Decimal` (`_to_decimal`), stored as `raw_qty`.
  - Resolves the instrument profile via `resolve_instrument_profile`, reading:
    - `step_size`
    - `min_qty`
    - `min_notional`
  - If `raw_qty < min_qty` → returns `allowed=False` (`below_min_qty`).
  - Computes `normalized_qty = _round_to_step(raw_qty, step_size)` with `ROUND_DOWN`.
    - If `normalized_qty <= 0` → reject (`qty_rounds_to_zero`).
    - If `normalized_qty < min_qty` → reject (`below_min_qty`).
  - When `price` is provided:
    - Checks `normalized_qty * price >= min_notional`; otherwise rejects (`below_min_notional`).
  - On success returns `QtyGuardResult(allowed=True, normalized_qty=normalized_qty, raw_qty=raw_qty)`.

Important invariant:

- The guard **never increases** quantity:
  - `_round_to_step` uses `ROUND_DOWN` only.
  - There is no code path where `normalized_qty > raw_qty`.
  - On error it either blocks the order (no DEC) or falls back to logging and returns the original absolute qty (see below).

Therefore, any “exploding” position sizes (e.g. 181 SOL) are not produced by `ExecutionQtyGuard`’s arithmetic.

---

## 3. How ManageFlowFSM Uses Qty Guard (Reduce‑Only Brackets)

Path: `apps/reference/domains/execution_position/fsm_manage.py`

Bracket placement path (aggregated OCO):

1. `_place_brackets_aggregated(msg, reason)`:
   - Computes aggregated TP/SL levels via `_compute_aggregated_bracket_levels`.
   - Delegates to `_place_or_update_bracket_set_from_levels(msg, levels, reason)`.

2. `_place_or_update_bracket_set_from_levels(...)`:
   - Sets `self.sl_price`, `self.tp_price`.
   - Computes `qty_value = _coerce_abs_decimal(self.position_qty)` – i.e. **absolute aggregated position size**.
   - Picks `guard_price = _select_guard_price(levels)` (min of SL/TP prices).
   - Logs `AGG_OCO_BEFORE_QTY_GUARD` with `position_qty` and `guard_price`.
   - Calls:

     ```python
     qty_str = self._normalize_reduce_only_qty(
         symbol=symbol,
         qty=qty_value,
         price=guard_price,
         context=reason or "aggregated_brackets",
     )
     ```

   - If `qty_str is None` → logs a guard warning and **does not place brackets** (state → `TRACKING`).
   - Else uses `qty_str` for both SL and TP reduce‑only orders (opposite side).

3. `_normalize_reduce_only_qty(...)`:
   - If aggregated‑only mode is off or `_qty_guard` is missing → returns `str(qty)` (no guard).
   - In aggregated‑only mode:
     - Coerces `qty_abs = abs(Decimal(str(qty)))`.
     - Calls `self._qty_guard.evaluate(symbol=symbol or "UNKNOWN", qty=qty_abs, price=price)`.
     - On guard exception:
       - Logs `AGG_QTY_GUARD_ERROR`.
       - Returns `str(qty_abs)` – **still no inflation**.
     - If `not guard_result.allowed or not guard_result.qty_str()`:
       - Logs `AGG_SL_SKIPPED_MIN_QTY`.
       - Returns `None` (brackets skipped).
     - Otherwise returns `guard_result.qty_str()` – the rounded‑down quantity.

Implications:

- ManageFlowFSM uses qty_guard only for **TP/SL reduce‑only orders**, never for entries.
- The only effect qty_guard can have is:
  - `allow` → reduce‑only SL/TP placed with `normalized_qty <= position_qty`.
  - `reject` → SL/TP не ставляться (позиція лишається без захисту).
- Навіть у випадку guard‑помилки fallback – SL/TP ставляться з тим же `position_qty`, що прийшов у FSM, без збільшення.

Conclusion: `ManageFlowFSM` + `ExecutionQtyGuard` не можуть механічно збільшити саму **позицію SOLUSDT**. Вони лише локально контролюють розмір та наявність SL/TP.

---

## 4. Where SOLUSDT Amplification Is More Likely Coming From

Given the above, real position amplification (1 → 10 → 181 SOL) must come from layers that:

- emit DEC:OPEN with increasing `qty`, або
- інкрементують `position_qty` кілька разів на одну й ту саму подію.

Candidates:

- **OpenFlowFSM / ExecPosFSM**:
  - DEC:OPEN generation and routing.
  - `WATCHDOG_EMIT_TRADE_EXECUTED` handling – if a single fill is emitted/handled multiple times, `position_qty` can be incremented repeatedly.
  - Timeout / retry logic for entries: if timeouts cause re‑opening without clearing prior state, net position grows.
- **Position aggregation from WS + REST + local state**:
  - `_rehydrate_aggregated_brackets_on_startup` and related DR logic in `fsm.py`:
    - If SOLUSDT positions from historical fills are aggregated twice (e.g., WS snapshot + REST fallback + local OpenFlow state), you can see jumps like `Position -14.0` on restart.
  - Similar patterns described in `docs/INCIDENT_NO_TP_SL_AGG_OCO_2025-11-18.md` for SOLUSDT.
- **Risk / exposure config bugs**:
  - Misconfigured `max_position_size` or leverage overrides would *allow* large positions, but не пояснюють *кратне* збільшення від невеликого початкового order size.

So far, nothing in qty_guard or ManageFlowFSM suggests a path to “181 SOL” by themselves; вони скоріше “сусіди” проблеми: якщо вони не ставлять SL/TP, це робить великий SOL‑експожер ще небезпечнішим, але сам розмір позиції формується вище – в Open/ExecPos/Risk шарах.

---

## 5. Next Investigation Directions (without tests)

- **OpenFlowFSM + ExecPosFSM**:
  - Search for all handlers of `EVT:TRADE_EXECUTED` / `WATCHDOG_EMIT_TRADE_EXECUTED` and check, чи є захист від повторної обробки одного й того ж заповнення (correlation IDs, deduplication).
  - Перевірити DEC:OPEN retry / timeout code: чи немає циклу “timeout → повторний DEC:OPEN” без коректного оновлення/скидання локального `position_qty`.
- **Position rehydration** (`fsm.py`):
  - `_rehydrate_aggregated_brackets_on_startup`, `_startup_order_guardian_reconcile`:
    - шукати місця, де SOLUSDT може бути зарахований кілька разів при старті/рестарті (WS snapshot + REST + локальний FSM state).
- **Cross‑checking with existing incident docs**:
  - Пов’язати описані вами ступені (по 1, по 10, одразу 181 SOL) з конкретними RID/timestamps з `aurora_core.log`, `domain_execution_management.log`, `event_chain.log` для SOLUSDT.

All of these подальші кроки продовжуватимуться без змін у тестах, з фокусом на детальний аналіз кодових шляхів та логів, а не на TDD/рефакторинг.

---

## 6. Additional Findings from Deeper Dive (ExecPosFSM, OpenFlow, ExposureGuard)

This section continues the deep dive you requested, focusing on how fills and exposure interact with position size. It stays read‑only with respect to tests and code.

### 6.1. OpenFlowFSM – entry sizing and guards

Path: `apps/reference/domains/execution_position/fsm_open.py`

- OpenFlowFSM:
  - Receives `CMD:OPEN` and emits `DEC:OPEN` with fields `{symbol, side, qty, order_type, price?}`.
  - Uses instrument specs from config (`trading.instruments`) to enforce:
    - `min_qty`, `step_size`, `tick_size`, `min_notional`.
  - Automatically rounds **down** quantity to `step_size` and price to `tick_size`:

    ```python
    qty_rounded = ((qty_dec // step_size) * step_size).quantize(step_size)
    if qty_rounded != qty_dec:
        qty_dec = qty_rounded
    ```

  - Enforces `min_notional` for both LIMIT and MARKET (using reference price for MARKET).
  - Applies cooldown per symbol; if violated → ERR, no DEC:OPEN.
  - Emits a single `DEC:OPEN` per accepted CMD:OPEN and **does not rescale** qty upward.

Conclusion: OpenFlowFSM also never amplifies quantity; it may shrink or reject orders. Any “181 SOL” entry must come from upstream decision sizing or repeated CMD:OPEN, not from OpenFlowFSM math.

### 6.2. ExecPosFSM – unified TRADE_EXECUTED handling and deduplication

Path: `apps/reference/domains/execution_position/fsm.py`, `_on_trade_executed`.

- ExecPosFSM subscribes to a unified `EVT:TRADE_EXECUTED` stream:
  - Sources:
    - WebSocket trade updates from the adapter.
    - REST watchdog (`WATCHDOG_EMIT_TRADE_EXECUTED`) – polling based fills.
    - Other consumers (e.g., account observers).
  - `_emit_watchdog_event` normalizes watchdog payloads into canonical TRADE_EXECUTED messages and immediately calls `self.handle(msg)` after optional bus emission.
- Deduplication strategy in `_on_trade_executed`:
  - Builds `idempotent_key` from `payload["idempotent_key"] or client_order_id or rid`.
  - Uses `_processed_events` set with key:

    ```python
    event_key = f"trade_executed_{idempotent_key or rid or 'unknown'}_{symbol}"
    if event_key in self._processed_events:  # duplicated event
        return
    self._processed_events.add(event_key)
    ```

  - Additionally, when an `orderId` is present, it marks:

    ```python
    fill_key = f"fill_{order_id_for_fill}_{symbol}"
    self._processed_events.add(fill_key)
    ```

- Implication:
  - For a given `(symbol, client_order_id)` or `(symbol, rid)` the TRADE_EXECUTED handler should run only once.
  - This is specifically designed to avoid repeated increments to aggregated position for the same fill (your “multiplying SOL” scenario).
  - If amplification still happened, it likely pre‑dated this unified deduplication or involved cases where `idempotent_key` / `rid` were different across duplicates (e.g., slightly different payloads, separate watchers).

### 6.3. ExposureGuard & SoftClipEngine – clipping not amplification

Paths:
- `apps/reference/domains/execution_position/exposure_guard.py`
- `apps/reference/domains/execution_position/soft_clip.py`

Key points:

- ExposureGuard:
  - Resolves exposure policy from config (`max_equity_utilization_pct`, `per_symbol_cap_pct`, `max_directional_ratio`, etc.).
  - For each DEC:OPEN, calculates intended notional and consults SoftClipEngine:
    - Soft clipping favours *reducing* notional to fit within limits:
      - margin limit,
      - per‑side exposure limit,
      - directional ratio.
    - If clipped notional falls below `clip_min_notional_usdt` (10 USD) → order rejected (not amplified).
- SoftClipEngine:

  ```python
  # V_new = min(V_req, I_margin, I_side, I_directional)
  clipped_notional = min(deltas)
  if clipped_notional < clip_min_notional_usdt:
      allowed = False
  ```

  - All constraints are `min(...)` operations — they only reduce size.
  - There is no path where `clipped_notional > requested notional`.

Therefore, exposure guard + soft clip can at most allow or shrink requested SOLUSDT notional; вони не можуть із 10 USD зробити 181 SOL. Якщо такі розміри з’являлися, це означає, що upstream decision layer вже просив величезні DEC:OPEN (або кліпінг був вимкнений/обійдений).

### 6.4. Systemic fragility: why amplification is plausible despite guards

Combining the deep‑dive results:

- None of:
  - `ExecutionQtyGuard` (SL/TP),
  - `ManageFlowFSM` (aggregated brackets),
  - `OpenFlowFSM` (DEC:OPEN guards),
  - `ExposureGuard` + `SoftClipEngine`
  explicitly multiply position size.
- Amplification of SOLUSDT (1 → 10 → 181 SOL) must involve:
  - **Repeated DEC:OPEN with already large qty** from upstream decision/risk logic; or
  - **Deduplication gaps** where:
    - multiple TRADE_EXECUTED events had different `idempotent_key` / `rid`, so `_processed_events` did not recognise them as duplicates;
    - different code paths wrote to the same aggregated position (e.g., legacy FILL events vs unified TRADE_EXECUTED).
- Existing Phase 4 fragility report already calls out:
  - “No man’s land” between ManageFlowFSM and OrderGuardian.
  - Races around ACK vs bracket registration.
  - Lack of active reconciliation for live positions.

Your SOLUSDT episodes sit exactly в цій зоні: великі позиції були можливі, бо рішення/ризик шар дозволяв такі DEC:OPEN, а Aggregated OCO/qty_guard/ExposureGuard лише частково пом’якшували ситуацію (не збільшуючи, але й не завжди блокуючи).

At this depth, further narrowing down “181 SOL” потребує прямої кореляції DEC:OPEN/EVT:TRADE_EXECUTED з логів за конкретний період (RID‑рівень аналізу), але з боку доменних модулів зараз видно: жоден із guard’ів сам по собі не мультиплікує qty — вони радше створюють вразливе середовище, де повторні або занадто великі upstream‑рішення не гасяться достатньо агресивно.

