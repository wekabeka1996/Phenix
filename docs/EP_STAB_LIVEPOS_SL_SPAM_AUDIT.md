## A. Duplicate / Divergent Logic Check

### A.1 Responsibility Map

- **ExecPosFSM (`apps/reference/domains/execution_position/fsm.py`)**
  - Live position state:
    - `_resolve_live_position_state(symbol)` is the single provider used by ManageFlowFSM via `_build_live_position_provider`.
    - Sources: WS position snapshots (`_ws_position_cache`), latest portfolio state (`_latest_portfolio_state`), and REST fallback with backoff (`_livepos_rest_backoff_until`, `REST_FALLBACK_TIMEOUT_SEC`).
  - Watchdog / auto-heal:
    - Config: `aggregated_oco.watchdog` (enabled, interval, `auto_heal_orphans`).
    - Loop: `_agg_oco_watchdog_loop` → `_run_agg_oco_watchdog_once`.
    - Invariants: calls `normalize_positions_for_watchdog` / `validate_agg_oco_invariants` to compute `NO_SL_FOR_OPEN_POSITION`, `ORPHAN_SL_FOR_ZERO_POSITION`, `TOO_MANY_SL_FOR_OPEN_POSITION`, `MULTIPLE_META_SETS`.
    - Auto-heal: `_auto_heal_watchdog_violation` dispatches to:
      - `_heal_orphan_sl_for_zero_position` (ORPHAN),
      - `_heal_too_many_sl_for_open_position` (TOO_MANY),
      - `_heal_no_sl_for_open_position` (NO_SL).
    - Retry guard: `_autoheal_retry_counts` caps NO_SL auto-heal to 5 attempts per symbol in a 60s window.
  - Delegation:
    - Per-symbol flows: `_get_or_create_flows` returns `(OpenFlowFSM, ManageFlowFSM, CloseFlowFSM)`.
    - Manage flow: `manage_flow(symbol)` exposes `ManageFlowFSM` and receives EVT:TRADE_EXECUTED, ORDER_UPDATED, MARKET_DATA, etc.
    - Guardian: holds `order_guardian` instance, delegates:
      - `cleanup_orphans`, `ensure_single_bracket_set_for_position`, `clear_bracket_set_for_position`, `reconcile_symbol`, `list_bracket_sets`.
    - Cleanup loop: `_cleanup_loop` periodically calls `order_guardian.cleanup_orphans()` when orphan-monitor is enabled.

- **ManageFlowFSM (`apps/reference/domains/execution_position/fsm_manage.py`)**
  - Event handling:
    - `handle(msg)`:
      - FLAT + EVT:PARTIAL_FILL / FILL / TRADE_EXECUTED:
        - Uses `is_exit_order(pld)` to distinguish ENTRY vs EXIT.
        - ENTRY: `_on_fill(msg)` to seed `position_qty`, `position_entry_price`, `position_side`, `_agg_side`; transitions to `BRACKETS_PENDING` and calls `_place_brackets(...)`.
        - EXIT: clears local position/price/SL/TP state and stays FLAT (no new brackets on exit fills).
      - TRACKING / BRACKETS_PLACED:
        - `_check_rules(msg)` for:
          - Aggregated OCO fill handling (`_handle_aggregated_fill_event`),
          - Trailing stop / breakeven / time stop,
          - Quick profit,
          - Emergency SL.
  - Aggregated TP/SL placement:
    - `self._aggregated_only_mode` + `_is_aggregated_oco_enabled()` choose aggregated vs legacy path.
    - `_place_brackets_aggregated(msg, reason)`:
      - Calls `_compute_aggregated_bracket_levels(reason=agg_why)`:
        - Guard: if `position_entry_price is None or <= 0` → log `AGG_OCO_ENTRY_PRICE_NOT_READY` and return `None` (no DEC, no error).
        - Uses `resolve_brackets_config` + `compute_aggregated_brackets` (pure function in `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py`) with `AggregatedOcoRiskConfig` and `InstrumentPriceConstraints`.
      - `_place_or_update_bracket_set_from_levels`:
        - Sets `sl_price`, `tp_price`, `state=BRACKETS_PENDING`, `_current_bracket_set_id`.
        - Builds base client id + `_sl` / `_tp` suffix via `_build_sl_tp_client_ids`.
        - Emits DEC:PLACE_ORDER for SL (STOP_MARKET) and TP (LIMIT) via `_emit_place_order`, both with `reduceOnly=True`.
        - Buffers TP in `_pending_decisions`.
        - Registers aggregated bracket meta via `order_guardian.register_bracket_set(...)`.
  - State transitions:
    - Uses `ManageState` enum (FLAT, BRACKETS_PENDING, BRACKETS_PLACED, TRACKING, WAIT_MODE, ERROR).
    - `_clear_position_state()`:
      - Resets all position and bracket fields, sets state to FLAT.
      - Calls `_clear_guardian_bracket_set(symbol, agg_side)` → `OrderGuardian.clear_bracket_set_for_position(...)`.
  - Aggregated recalc & TTL:
    - `_handle_aggregated_fill_event` / `_handle_aggregated_fill_event_aggregated_only`:
      - Compute `fill_qty` from msg payload.
      - `is_exit_fill = is_exit_order(pld)` ensures EXIT fills reduce or close position instead of placing new TP/SL.
      - Uses `_get_live_position_state()` (ExecPosFSM provider) to get canonical snapshot (`qty`, `avg_price`, `side`, `source`).
      - Derives reason: `"snapshot_entry_fill" | "snapshot_scale_in" | "snapshot_partial_close" | "snapshot_recalc"`.
      - Logs `AGG_OCO_LIVE_SNAPSHOT_RECALC` and calls `_recalc_aggregated_brackets(msg, reason=reason)`.
    - `_recalc_aggregated_brackets(msg, reason)`:
      - TTL: `ttl_ms = max(agg_cfg.ttl_protect_new_bracket_ms or 0, 0)`.
      - Auto-heal detection: `is_auto_heal = (msg.why == "watchdog_autoheal_no_sl") or ("autoheal" in reason)`.
      - If not auto-heal and within TTL window and either:
        - `agg_cfg.allow_unprotected_position` is True, or
        - there is any `sl_order_id` or `tp_order_id`,
        → logs `"[BRK][agg] skip recalc reason=... elapsed=... ttl=..."` and returns `None`.
      - Otherwise:
        - Cancels existing brackets via `_cancel_active_brackets(msg, reason)` (DEC:CANCEL_ORDER for tracked SL/TP), clearing `sl_order_id`/`tp_order_id`.
        - Calls `_place_brackets_aggregated` to place a fresh aggregated bracket set.

- **OrderGuardian (`apps/reference/services/order_guardian.py`)**
  - BracketSetMeta:
    - Dataclass `BracketSetMeta` is the single canonical metadata for an aggregated bracket set:
      - Fields: `bracket_set_id`, `symbol`, `side`, `sl_order_id`, `tp_order_id`, `created_ts`, `version`.
    - `_bracket_sets: Dict[(symbol, side), BracketSetMeta]` ensures **at most one** bracket set per (symbol, side).
  - Metadata lifecycle / cardinality:
    - `register_bracket_set(...)`:
      - Registers or updates metadata under key `(symbol.upper(), normalized_side)`.
      - Bumps `version` each time.
    - `get_active_bracket_set(symbol, side)` / `list_all_bracket_sets()`:
      - Read-only accessors used by ExecPosFSM and tests.
    - `clear_bracket_set_for_position(symbol, side)`:
      - Deletes `_bracket_sets[(symbol, side)]`, single point for “position closed → drop bracket meta”.
    - `ensure_single_bracket_set_for_position(...)`:
      - Cleanup policy when `position_amt > 0`:
        - Selects candidate bracket-like orders via `_select_bracket_orders_for_symbol_side`:
          - Normalizes payload via `_normalize_order_payload`, then filters:
            - `_is_bracket_candidate(order)` → `reduceOnly or closePosition`,
            - `_matches_requested_position_side(order, side)` for LONG/SHORT vs BUY/SELL.
        - Protects current bracket ids from metadata (`meta.sl_order_id`, `meta.tp_order_id`).
        - Cancels extra reduceOnly/closePosition orders for that (symbol, side), respecting TTL `ttl_protect_new_bracket_ms`.
      - When `position_amt == 0`:
        - Cancels all bracket candidates.
        - Emits `agg_oco_zero_position_cleanup` event.
        - Calls `clear_bracket_set_for_position(symbol, side)`.
  - Cleanup / reconcile:
    - `cleanup_orphans(symbol=None, hard=False)`:
      - Scans open orders and positions, cancels orphan reduceOnly/closePosition orders.
      - `hard=True` cancels all reduceOnly/closePosition brackets for the symbol, regardless of position.
    - `reconcile_symbol(symbol, rid)`:
      - Symbol-wide reconcile (used by ExecPosFSM DEC:CLOSE path).

- **Bracket Aggregator (`vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py`)**
  - Pure calculation:
    - `compute_aggregated_brackets(position_amt, avg_entry_price, side, risk_cfg, constraints)`:
      - Validates inputs (`position_amt > 0`, `avg_entry_price > 0`, `sl_pct > 0`, `tp_rr > 0`, tick_size / min_price > 0, side in {LONG, SHORT}).
      - Computes raw SL/TP from entry price and risk config:
        - LONG: `sl = price * (1 - sl_pct)`, `tp = price * (1 + sl_pct * tp_rr)`.
        - SHORT: `sl = price * (1 + sl_pct)`, `tp = price * (1 - sl_pct * tp_rr)`.
      - Applies constraints via `_apply_price_constraints` and `_round_down_to_tick`.
      - Returns immutable `AggregatedBracketLevels(tp_price, sl_price, why)`.
  - There is no cleanup logic here; all cleanup is delegated to OrderGuardian/ExecPosFSM.

### A.2 Duplicate / Divergent Logic Check

This section is summarized in D.1/D.2 with risk ratings; detailed per-signal mapping was performed over:

- `cancel_order(` call sites in ExecPosFSM and OrderGuardian.
- All occurrences of `reduceOnly` / `closePosition` in:
  - `apps/reference/domains/execution_position`,
  - `apps/reference/services/order_guardian.py`,
  - `tests/domains/execution_position`.
- `_symbol_brackets` usage in ExecPosFSM.
- Aggregated OCO watchdog invariants:
  - `NO_SL_FOR_OPEN_POSITION`,
  - `ORPHAN_SL_FOR_ZERO_POSITION`,
  - `TOO_MANY_SL_FOR_OPEN_POSITION`,
  - `MULTIPLE_META_SETS`.
- `BracketSetMeta` lifecycle in OrderGuardian.
- `compute_aggregated_brackets` in `bracket_aggregator.py` and its usage from `ManageFlowFSM._compute_aggregated_bracket_levels`.
- `AGG_OCO_ENTRY_PRICE_NOT_READY` guard and call sites.

High-level conclusions:

- Cleanup semantics for aggregated TP/SL are owned by `OrderGuardian` (ExecPosFSM no longer contains a competing bracket-cleanup algorithm for symbol-wide flows).
- NO_SL/ORPHAN/TOO_MANY invariants are defined only once (in `agg_oco_watchdog`).
- EXIT/SL criteria are conceptually consistent across:
  - `is_exit_order(pld)` (ENTRY/EXIT classification),
  - watchdog `_normalize_orders` / `_is_sl_order`,
  - OrderGuardian `_is_bracket_candidate` / `_is_sl_order`.
- The main divergence is at the **adapter boundary**:
  - `BinanceAdapter.get_open_orders()` hides `reduceOnly` / `closePosition` / `type` / `stopPrice`, so watchdog and OrderGuardian cannot apply their exit/SL criteria to aggregated bracket orders.

Details and risk ratings are documented in sections B and D.

---

## B. Invariant & Auto-heal Analysis

### B.1 Invariant Definitions & Exit-order Criteria

#### B.1.1 NO_SL / ORPHAN / TOO_MANY invariants (watchdog)

From `agg_oco_watchdog.validate_agg_oco_invariants`:

- Inputs:
  - `positions`: raw positions (REST/WS) → normalized via `_normalize_positions` using `PositionSnapshot.from_rest_list(...)`.
  - `open_orders`: raw open orders (adapter / REST) → normalized via `_normalize_orders`.
  - `bracket_metas`: `BracketSetMeta` list → grouped via `_group_metas`.

- Per key `(symbol, side)` (canonical LONG/SHORT):
  - `qty` = position quantity (`WatchdogPosition.quantity`).
  - `orders_for_key` = list of `WatchdogOrder` (filtered on `symbol`, `side`).
  - `sl_count` = number of `orders_for_key` where `is_sl` is True.
  - `meta_count` = number of `BracketSetMeta` for the key.

- Invariants:
  - **NO_SL_FOR_OPEN_POSITION**
    - Condition:
      - `qty > 0` and `sl_count == 0`.
    - Intuition:
      - “Open position with no SL bracket orders visible to the watchdog.”
  - **TOO_MANY_SL_FOR_OPEN_POSITION**
    - Condition:
      - `qty > 0` and `sl_count > 1`.
    - Intuition:
      - “Open position protected by more than one SL bracket (over-hedged).”
  - **ORPHAN_SL_FOR_ZERO_POSITION**
    - Condition:
      - `qty == 0` and `orders_for_key` is non-empty.
    - Intuition:
      - “SL/TP orders exist for a flat position.”
  - **MULTIPLE_META_SETS**
    - Condition:
      - `meta_count > 1`.
    - Intuition:
      - “More than one `BracketSetMeta` registered for `(symbol, side)`.”

#### B.1.2 Watchdog vs OrderGuardian exit-order criteria

- Watchdog (`agg_oco_watchdog._normalize_orders` / `_is_sl_order`):
  - Filters orders as EXIT/BRACKET candidates only if:
    - `reduceOnly` or `reduce_only` is truthy, OR
    - `closePosition` or `close_position` is truthy.
  - Among candidates, identifies SL via:
    - Explicit `is_sl` flag, OR
    - STOP* in `type/origType/kind`, or STOP in `workingType`, or `_sl` suffix in `clientOrderId`, or non-zero `stopPrice/activatePrice`.

- OrderGuardian (`_is_bracket_candidate` / `_is_sl_order`):
  - Bracket candidate if:
    - `reduceOnly` or `closePosition` is truthy (after normalization).
  - SL when:
    - `kind` is STOP/SL-like, or `"STOP"` substring in `type`.

The intended contract is:

- ManageFlowFSM and `is_exit_order` own ENTRY vs EXIT semantics at FILL time.
- Watchdog and OrderGuardian both treat **reduceOnly/closePosition** as the key signal that an order is a TP/SL bracket for invariants and cleanup.

#### B.1.3 Potential mismatch (YES/NO + explanation)

- The algorithms themselves are aligned, but:
  - `BinanceAdapter.get_open_orders()` strips `reduceOnly`, `closePosition`, `type`, `stopPrice` from `/openOrders` JSON into `ExchangeOrderResponse`.
  - When watchdog and OrderGuardian normalize these dataclasses back into dicts, exit flags are missing.
  - Consequently:
    - Watchdog `_normalize_orders` drops aggregated TP/SL orders entirely.
    - OrderGuardian `_is_bracket_candidate` returns False for those orders.
    - `sl_count` is computed as 0 for open positions that are in fact protected by SL.
  - This is a **YES** for “potential mismatch”: the criteria are correct, but the data they operate on do not match expectations.

### B.2 Auto-heal loops / async behaviour

#### B.2.1 Auto-heal retry semantics

- `_agg_oco_watchdog_loop` runs at configured interval, calling `_run_agg_oco_watchdog_once`.
- `_run_agg_oco_watchdog_once`:
  - Fetches `open_orders` + `positions` via adapter.
  - Reads `metas = _list_guardian_bracket_sets()`.
  - Computes violations via `validate_agg_oco_invariants`.
  - Logs violations and, if `_agg_watchdog_auto_heal` is True, calls `_auto_heal_watchdog_violation`.
- `_auto_heal_watchdog_violation`:
  - ORPHAN_SL_FOR_ZERO_POSITION → `_heal_orphan_sl_for_zero_position` (guardian.cleanup_orphans + clear_bracket_set_for_position).
  - TOO_MANY_SL_FOR_OPEN_POSITION → `_heal_too_many_sl_for_open_position` (guardian.ensure_single_bracket_set_for_position).
  - NO_SL_FOR_OPEN_POSITION → `_heal_no_sl_for_open_position`.

For NO_SL:

- `_heal_no_sl_for_open_position`:
  - Uses `_autoheal_retry_counts[f"autoheal_{symbol}"] = (count, last_ts)`:
    - Resets `count` if last attempt was more than 60 seconds ago.
    - Aborts auto-heal after 5 attempts within 60 seconds and logs `AGG_OCO_AUTOHEAL_ABORTED_LOOP_DETECTED`.
  - Looks up `ManageFlowFSM` for the symbol and, if stuck in BRACKETS_PENDING, forces state back to TRACKING.
  - Logs `AGG_OCO_WATCHDOG_AUTOHEAL` with incremented `retry_count`.
  - Constructs synthetic EVT:TRADE_EXECUTED with:
    - `why="watchdog_autoheal_no_sl"`,
    - `pld = {"symbol": symbol, "qty": str(violation.details["position_amt"] or 0), "source": "watchdog_autoheal"}`.
  - Routes this through `manage_flow.handle` and `_dispatch_decision`, then drains `manage_flow.consume_pending_decisions()` and dispatches those decisions as well.

#### B.2.2 Where success is detected

- There is no explicit “success” callback from ManageFlowFSM or OrderGuardian to auto-heal.
- Success is inferred indirectly:
  - On the next watchdog pass, if `validate_agg_oco_invariants` returns no violations for `(symbol, side)`, `_update_watchdog_snapshot` records status `OK`.
  - If violations persist (e.g., NO_SL), auto-heal continues to be invoked until the retry cap or until invariants are satisfied.

#### B.2.3 Where success can fail to be detected (SL spam candidate)

The critical failure path:

1. ManageFlowFSM + ExecPosFSM place valid aggregated SL/TP via adapter.
2. Adapter’s `get_open_orders()` removes exit flags from open orders.
3. Watchdog and Guardian normalization cannot recognize any bracket orders:
   - No WatchdogOrder objects are created for SL/TP.
   - `sl_count` stays 0 for an open position.
4. `validate_agg_oco_invariants` flags `NO_SL_FOR_OPEN_POSITION` on *every* watchdog pass.
5. `_heal_no_sl_for_open_position`:
   - Bypasses TTL via `_recalc_aggregated_brackets` (`is_auto_heal=True`).
   - Cancels existing tracked SL/TP (if any) and places new ones.
6. Because adapter output is unchanged (still hiding exit flags), the next watchdog run again sees `NO_SL_FOR_OPEN_POSITION`.

Result:

- For each watchdog interval, until the retry cap is hit, auto-heal:
  - Cancels the “old” SL and places a “new” one for the same stable position.
  - Leads to a burst of SL re-placement – perceived as “SL spam” in logs and at the exchange level.

---

## C. SL Spam Reproduction Test

### C.1 Test scenario summary

- New test: `tests/domains/execution_position/test_agg_oco_sl_spam_regression.py`.
- Scenario:
  - SOLUSDT LONG position opened (qty ≈ 1.0, entry price 130.0).
  - ManageFlowFSM computes and places aggregated TP/SL.
  - ExecPosFSM executes DEC:PLACE_ORDER via a stub adapter (`SpamAdapter`) that:
    - Exposes open positions correctly.
    - Exposes open orders **without** `reduceOnly` / `closePosition` flags, mimicking the data shape produced by `BinanceAdapter.get_open_orders` + `ExchangeOrderResponse`.
  - Aggregated OCO watchdog + auto-heal enabled and invoked multiple times:
    - `fsm._agg_watchdog_enabled = True`,
    - `fsm._agg_watchdog_auto_heal = True`.
- Observable:
  - Count distinct STOP_MARKET SL `orderId`s seen in `SpamAdapter.open_orders` after:
    - Initial bracket placement,
    - Several `_run_agg_oco_watchdog_once()` calls.
  - Expected invariant: `len(unique_sl_ids) == 1`.
  - Current behaviour (based on code + adapter mismatch): `len(unique_sl_ids) > 1`.

### C.2 Current behaviour (expected xfail)

- The regression test is marked `xfail` with a reason explaining that:
  - With adapter hiding exit flags on open orders, watchdog repeatedly detects `NO_SL_FOR_OPEN_POSITION`.
  - Auto-heal repeatedly cancels and re-places SL for the same stable position.
  - This leads to multiple distinct SL order ids for a single (symbol, side), violating the “one SL per open position” invariant.

---

## D. Conclusions & Root Cause Hypotheses

### D.1 Duplicate logic / ownership

- **Cleanup SL/TP:**
  - Symbol-wide aggregated cleanup policy is owned by `OrderGuardian` (`cleanup_orphans`, `ensure_single_bracket_set_for_position`, `clear_bracket_set_for_position`).
  - ExecPosFSM provides orchestration and legacy/per-entry flows but does not define its own competing aggregate cleanup policy.
  - **ONE OWNER: OrderGuardian – YES.**

- **NO_SL_FOR_OPEN_POSITION definition:**
  - Defined centrally in `agg_oco_watchdog.validate_agg_oco_invariants`.
  - No other implementations found elsewhere.
  - **Single definition – YES.**

- **SL-order (EXIT/SL) criteria consistency:**
  - `is_exit_order(pld)` is the canonical ENTRY/EXIT classifier for FILL / DEC flows.
  - Watchdog and OrderGuardian both gate on `reduceOnly` / `closePosition` and then apply STOP-type heuristics for SL detection.
  - The core inconsistency is not in the criteria but in the availability of exit flags on open orders coming from `BinanceAdapter.get_open_orders`.
  - **Criteria consistent, data inconsistent – YES.**

- **Risk levels:**
  - Cleanup logic duplication: LOW.
  - Triple state tracking (`_symbol_brackets`, ManageFlowFSM state, `BracketSetMeta`): MEDIUM (legacy but contained).
  - Exit-flag visibility at adapter boundary (reduceOnly/closePosition dropped): HIGH – primary candidate for SL spam.

### D.2 SL spam – root cause hypothesis

- **Hypothesis:**
  - SL spam is caused not by duplicate cleanup algorithms but by a **data contract mismatch**:
    - `BinanceAdapter.get_open_orders()` hides `reduceOnly` / `closePosition` / `type` / `stopPrice`.
    - Watchdog and OrderGuardian therefore cannot see aggregated SL/TP bracket orders.
    - `validate_agg_oco_invariants` continually reports `NO_SL_FOR_OPEN_POSITION` for real, protected positions.
    - `_heal_no_sl_for_open_position` repeatedly cancels and re-places SL orders, bypassing TTL and relying only on a per-symbol retry cap.

- **Mechanism:**
  1. Position opens and aggregated TP/SL are placed successfully.
  2. Adapter exposes the position correctly but hides exit flags on open orders.
  3. Watchdog sees `qty > 0` and `sl_count == 0` and emits `NO_SL_FOR_OPEN_POSITION`.
  4. Auto-heal:
     - Forces ManageFlowFSM out of BRACKETS_PENDING if stuck.
     - Triggers aggregated bracket recalc with `is_auto_heal=True`, bypassing TTL.
     - Cancels existing tracked brackets and places new ones.
  5. Because the underlying `get_open_orders()` view never shows SL as a bracket, watchdog continues to see NO_SL after each auto-heal.
  6. Up to 5 times per minute (per symbol), new SL orders are placed, leading to bursts of SL spam.

- **Why tests did not catch it:**
  - Existing tests for watchdog and OrderGuardian use adapters/stubs that **do** expose `reduceOnly` / `closePosition` on open orders.
  - They validate invariants in a “perfectly wired” environment where exit flags are visible.
  - The production adapter path (`BinanceAdapter`) uses an intermediate dataclass that does not preserve those fields, creating a gap between test harness and runtime.

If the new regression test is run against the current code, it is expected to xfail with multiple SL ids observed for a stable SOLUSDT LONG position under watchdog auto-heal, confirming this hypothesis.

