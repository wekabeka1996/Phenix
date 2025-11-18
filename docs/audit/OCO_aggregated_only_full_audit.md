1. Scope & Context
------------------

- **Objective.** Audit Aggregated-Only OCO mode in the `execution_position` domain and its interaction with Binance Futures.
- **In scope.**
  - Runtime: `apps/reference/domains/execution_position/fsm.py`, `fsm_manage.py`,
    `agg_oco_watchdog.py`, `manage_config.py`, `apps/reference/services/order_guardian.py`,
    `apps/reference/adapters/binance_adapter.py`.
  - Contracts: `apps/reference/domains/execution_position/Readme/CONTRACT_aggregated_orders_v1.md`,
    `CONTRACT_aggregated_oco_v1.md`.
  - Config: `config/domains/execution.yaml`, `configs/master_config_v1.yaml`.
  - Tests: key suites under `tests/domains/execution_position/` and `tests/units/` listed in the task.
- **Mode definition.**
  - Aggregated-only mode is active when both:
    - `execution.manage.brackets.aggregated_oco.enabled = true`
    - `execution.manage.brackets.aggregated_oco.aggregated_only_mode = true`
  - In this mode:
    - Entry/exit orders must be *clean* (no inline TP/SL).
    - Aggregated OCO (Guardian + ManageFlow + watchdog) is the single owner of SL/TP lifecycle per `(symbol, side)`.


2. Inventory of TP/SL and OCO Touchpoints
-----------------------------------------

### 2.1 Adapter calls (reduceOnly / closePosition)

- `apps/reference/adapters/binance_adapter.py`
  - `place_market_entry` (872+):
    - `type="MARKET"`, quantized `quantity`, no TP/SL fields, no `reduceOnly` / `closePosition`.
  - `place_stop_market_close_position` (900+):
    - `type="STOP_MARKET"`, `stopPrice`, `workingType="MARK_PRICE"`,
      `closePosition="true"`, `priceProtect="true"`.
  - `place_take_profit_market_close_position` (967+):
    - `type="TAKE_PROFIT_MARKET"`, same flags as SL.
  - `place_limit_reduce_only` (1034+):
    - `type="LIMIT"`, `timeInForce="GTC"`, `price`, `quantity`, `reduceOnly="true"`.
  - `place_market_reduce_only` (1103+):
    - `type="MARKET"`, quantized `quantity`, `reduceOnly="true"`.

These are the only low‑level calls that create or close TP/SL / reduceOnly orders.

### 2.2 ExecPosFSM (entry, TP/SL, cleanup)

- `apps/reference/domains/execution_position/fsm.py`
  - `_execute_decision` (OPEN path, ~2860+):
    - Calls `place_market_entry` for DEC:OPEN entries.
    - When `_aggregated_only_mode` is **False**:
      - Computes TP/SL via `resolve_brackets_config` + `calc_tp_sl_from_mark`.
      - Places SL (`place_stop_market_close_position`) and TP
        (`place_take_profit_market_close_position` with LIMIT fallback).
    - When `_aggregated_only_mode` is **True**:
      - Skips inline TP/SL, logs `"Aggregated-only mode: delegating TP/SL to ManageFlow"`.
  - `_execute_decision` (CLOSE path, ~2580+):
    - Optional `OrderGuardian.close_entry` for parent‑id‑based CLOSE.
    - Uses `place_market_reduce_only` to flatten remaining qty.
    - Cancels tracked brackets via `_symbol_brackets` and direct `cancel_order`.
    - Optional symbol‑wide reconcile:
      - Fetches `get_open_orders(symbol)` and cancels any `STOP_MARKET` / `TAKE_PROFIT_MARKET` /
        `LIMIT` order with `reduceOnly` or `closePosition`.
    - Calls `order_guardian.cleanup_orphans()` and `order_guardian.reconcile_symbol(symbol, rid)`.
  - Orphan cleanup / DR:
    - `_cleanup_loop` periodically calls `order_guardian.cleanup_orphans()`.
    - `_startup_order_guardian_sync` runs a one‑shot `cleanup_orphans()` and rehydrates FSM flows.

### 2.3 ManageFlowFSM (legacy vs aggregated brackets)

- `apps/reference/domains/execution_position/fsm_manage.py`
  - Entry recognition in FLAT (280+):
    - Uses `order_type`, `reduceOnly`, `closePosition` to distinguish ENTRY vs EXIT fills.
    - ENTRY: `_on_fill` + `_place_brackets`.
    - EXIT in FLAT: clears local state, no brackets are placed.
  - `_place_brackets` (392+):
    - If `_aggregated_only_mode` is true:
      - Asserts aggregated_oco is enabled, then calls `_place_brackets_aggregated`.
    - Else if aggregated_oco enabled:
      - Also calls `_place_brackets_aggregated`.
    - Else:
      - Calls `_place_brackets_legacy`.
  - `_place_brackets_legacy` (397+):
    - Computes SL/TP via `resolve_brackets_config` + `TPSLValidationRules`.
    - Emits DEC:PLACE_ORDER for SL (`STOP_MARKET`) and TP (`LIMIT`) via `_emit_place_order`.
    - If `_aggregated_only_mode` is true, raises `RuntimeError` instead of placing.
  - `_place_brackets_aggregated` + `_place_or_update_bracket_set_from_levels` (577+):
    - Computes aggregated levels via `compute_aggregated_brackets`.
    - Emits DEC:PLACE_ORDER for SL and TP (always `reduceOnly=True`).
    - Logs changes and stores `_current_bracket_set_id`.
  - `_clear_position_state` (1080+):
    - Clears local position, SL/TP prices, and state.
    - Calls `_clear_guardian_bracket_set` → `OrderGuardian.clear_bracket_set_for_position`.

### 2.4 OrderGuardian and Aggregated OCO

- `apps/reference/services/order_guardian.py`
  - `register_bracket_set` (214+):
    - Creates or updates `BracketSetMeta` for `(symbol, side)` and increments `version`.
  - `clear_bracket_set_for_position` (259+):
    - Removes `BracketSetMeta` for `(symbol, side)`.
  - `ensure_single_bracket_set_for_position` (432+):
    - For position size > 0:
      - Cancels extra bracket‑like orders for `(symbol, side)` while keeping the active SL/TP.
      - Enforces TTL guard (`ttl_protect_new_bracket_ms`) and fail‑closed guard
        (`allow_unprotected_position=False`).
    - For position size == 0:
      - Cancels all reduceOnly/closePosition orders for `(symbol, side)`.
      - Clears `BracketSetMeta`.
  - `cleanup_orphans` (1471+):
    - When no position (or `hard=True`), cancels tracked reduceOnly/closePosition orders and emits
      `EVT:SYMBOL_TIDY`.

### 2.5 Aggregated OCO watchdog

- `apps/reference/domains/execution_position/agg_oco_watchdog.py`
  - `validate_agg_oco_invariants`:
    - Enforces:
      - `NO_SL_FOR_OPEN_POSITION`
      - `ORPHAN_SL_FOR_ZERO_POSITION`
      - `MULTIPLE_META_SETS`
    - Uses `reduceOnly` / `closePosition` flags to classify orders.
- `apps/reference/domains/execution_position/fsm.py`
  - `_run_agg_oco_watchdog_once` (1426+):
    - Fetches open positions + orders from adapter.
    - Rehydrates Guardian meta where needed.
    - Runs invariants checker and logs violations.
    - For `ORPHAN_SL_FOR_ZERO_POSITION` and `auto_heal_orphans=True`:
      - Calls `order_guardian.cleanup_orphans(symbol=...)`.
      - Calls `order_guardian.clear_bracket_set_for_position(symbol, side)`.


3. Aggregated-Only vs Legacy Behaviour
--------------------------------------

### 3.1 Config contract and runtime flags

- `ExecutionManageConfig` (`manage_config.py`):
  - Exposes `aggregated_only_mode` property as
    `bool(self.brackets.aggregated_oco.aggregated_only_mode)`.
- Config resolution:
  - Legacy (YAML) path builds `BracketsMetaConfig.aggregated_oco` via `_resolve_aggregated_oco`.
  - v2 (config_v2) path uses `_resolve_aggregated_oco_from_v2`.
- Validation (`_validate_manage_config`):
  - If `aggregated_only_mode=true` and `aggregated_oco.enabled=false` → `ConfigError`.
  - If `aggregated_oco.watchdog.enabled=true` and `aggregated_only_mode=false` → `ConfigError`.
  - If `aggregated_only_mode=true`:
    - Requires `recalc_on_partial_close=true`.
    - Requires `allow_unprotected_position=false`.
- ExecPosFSM and ManageFlowFSM both derive their `_aggregated_only_mode` from this config via
  `resolve_execution_manage_config`, so the flag is consistent across layers.

### 3.2 Entry/exit payloads vs CONTRACT_aggregated_orders_v1

- Contract (simplified):
  - **Entry:** no inline TP/SL fields; no `reduceOnly` / `closePosition`; pure size/price intent.
  - **Exit:** `MARKET`/`LIMIT` with `reduceOnly` or `closePosition`; no inline TP/SL.
  - All protection provided by Aggregated OCO, not by the entry/exit itself.
- Tests:
  - `tests/domains/execution_position/test_contract_aggregated_orders_mode.py`:
    - `test_entry_orders_have_no_inline_tp_sl_in_aggregated_mode`:
      - Asserts DEC:OPEN payload lacks `tp_price`, `sl_price`, `stopLoss`, `takeProfit`,
        `ocoOrder`, `attachedOrders` and has no reduceOnly/closePosition flags.
    - `test_exit_orders_do_not_carry_inline_tp_sl`:
      - Asserts DEC:CLOSE payload is TP/SL‑free but carries a reduceOnly/closePosition flag.
- Implementation:
  - ExecPosFSM only computes inline TP/SL when `_aggregated_only_mode` is False.
  - DEC:CLOSE payloads are built without TP/SL; brackets are always separate orders.

**Result:** with `aggregated_only_mode=true`, runtime behaviour matches the documented contract
for entry/exit payloads.

### 3.3 Legacy TP/SL gating

- Legacy TP/SL placement exists only in `ManageFlowFSM._place_brackets_legacy`.
- It is guarded in two ways:
  - `_place_brackets` routing never selects it when aggregated_oco is enabled.
  - `_place_brackets_legacy` itself raises if `_aggregated_only_mode` is true.
- ExecPosFSM never calls `_place_brackets_legacy` directly; all bracket placement is delegated via
  ManageFlowFSM.

**Conclusion:** in aggregated-only mode, legacy inline TP/SL paths are effectively disabled both at
config and at runtime, and cannot be re‑enabled without changing config to leave aggregated-only
mode.


4. Adapter & Exchange Integration
---------------------------------

### 4.1 Mapping to Binance Futures

- All TP/SL orders placed by ExecPosFSM or ManageFlowFSM ultimately use:
  - `STOP_MARKET` / `TAKE_PROFIT_MARKET` with:
    - `closePosition="true"`,
    - `workingType="MARK_PRICE"`,
    - `priceProtect="true"`.
  - Or `LIMIT` orders with `reduceOnly="true"` for TP or fallback.
- `BracketOrderPayload` in `contracts.py` enforces:
  - `closePosition=true` must not carry `quantity`.
  - Conditional orders require `stop_price`.
  - `workingType=MARK_PRICE` when `closePosition=true`.
- Error contracts (`TPSLValidationRules`) and adapter code cooperate to avoid:
  - `-2021` ("would immediately trigger") via price validation and offsets.
  - `-4116` ("duplicate clientOrderId") via client id ledger.

### 4.2 Aggregated-only behaviour vs adapter usage

- In aggregated-only mode:
  - Entries are always `place_market_entry` without TP/SL or reduceOnly/closePosition.
  - Aggregated brackets (SL/TP) are emitted as separate orders with `reduceOnly` or
    `closePosition` flags and correct `workingType`/`priceProtect`.
  - Manual or system exits use `place_market_reduce_only` and do not embed TP/SL logic.
- No path uses client‑side OCO groups; all aggregation is done at the Guardian level with pure
reduceOnly/closePosition orders.

**Conclusion:** adapter usage is consistent with Binance Futures expectations and with the
Aggregated‑Only contract.


5. ExecPosFSM ↔ ManageFlowFSM ↔ OrderGuardian ↔ Watchdog
---------------------------------------------------------

### 5.1 Scenario traces (summary)

- **0 → X (first entry).**
  - `CMD:OPEN` → `OpenFlowFSM` → `DEC:OPEN`.
  - ExecPosFSM `_execute_decision`:
    - `place_market_entry`, register entry with Guardian, track in watchdog.
    - Skip inline TP/SL if `_aggregated_only_mode`.
  - On `EVT:TRADE_EXECUTED`:
    - Forward to ManageFlowFSM; ENTRY fill triggers `_place_brackets_aggregated`.
    - Aggregated SL/TP DEC:PLACE_ORDER messages go back through ExecPosFSM to adapter.
    - Guardian registers a single `BracketSetMeta` for `(symbol, side)`.

- **X → Y (scale-in).**
  - New ENTRY fill plus updated position from live snapshot (`_build_live_position_provider`).
  - ManageFlowFSM `_handle_aggregated_fill_event_aggregated_only`:
    - Recomputes qty/avg price from snapshot.
    - Calls `_recalc_aggregated_brackets` with `reason="snapshot_scale_in"`.
  - Guardian (via `ensure_single_bracket_set_for_position`) keeps a single bracket set and bumps
    `version`.

- **Y → Z (partial close).**
  - EXIT fill (`reduceOnly`/`closePosition` or STOP/TP type).
  - Aggregated-only path again uses live snapshot:
    - If qty > 0: recomputes levels, emits new brackets.
    - If qty = 0: clears ManageFlow state and Guardian meta.

- **Z → 0 (full close).**
  - Via brackets:
    - Snapshot shows zero qty → `_clear_position_state` and
      `clear_bracket_set_for_position`.
    - Watchdog enforces `ORPHAN_SL_FOR_ZERO_POSITION` and auto‑heals if needed.
  - Via manual DEC:CLOSE:
    - Sets `manage._closing_position=True` (anti‑race).
    - Cancels known brackets and calls `place_market_reduce_only`.
    - Optionally reconciles symbol‑wide open orders and runs `cleanup_orphans()`.
    - Calls `reconcile_symbol(symbol, rid)` to align Guardian state.
    - Clears `manage._closing_position` on completion.

- **DR / restart.**
  - Startup reconcile links existing orders and positions, rehydrates Guardian metas and FSM flows.
  - Watchdog rehydrates missing metas before validation, using live open orders.

### 5.2 Mixed aggregated / legacy regime

- Validator currently enforces:
  - `aggregated_only_mode => aggregated_oco.enabled`.
  - `aggregated_oco.watchdog.enabled => aggregated_only_mode`.
- It does **not** enforce:
  - `aggregated_oco.enabled => aggregated_only_mode`.
- In a configuration with `aggregated_oco.enabled=true`, `aggregated_only_mode=false`:
  - ManageFlowFSM routes to Aggregated OCO.
  - ExecPosFSM still runs inline TP/SL in `_execute_decision`.
- This yields a *mixed* regime:
  - per‑entry inline brackets **and** per‑position Aggregated OCO brackets may coexist.
  - ownership becomes ambiguous, especially during scale‑in/partial close.
- Current default configs set both flags to `true`, so production avoids this, but the potential
remains at config level.


6. Behavioural Conflicts & Race Conditions
------------------------------------------

### 6.1 Overlapping cleanup paths

- Cleanup of reduceOnly/closePosition orders can be triggered by:
  - ExecPosFSM DEC:CLOSE reconcile.
  - `OrderGuardian.cleanup_orphans` (startup, periodic loop, watchdog auto‑heal).
  - `OrderGuardian.ensure_single_bracket_set_for_position` (via
    `cleanup_other_brackets_for_symbol` or tests).
  - `_on_portfolio_state_updated` calling `reconcile_symbol` when a position transitions to zero.
- All paths treat `-2011` / "unknown order" as idempotent success and guard on Guardian ownership.
- Tests for Guardian cleanup and watchdog runtime flows confirm that:
  - No double‑cleanup causes exceptions.
  - Zero‑position invariants (no brackets, no meta) are preserved.

### 6.2 Bracket placement races with DEC:CLOSE

- ExecPosFSM sets `manage._closing_position=True` on `CMD:CLOSE` and DEC:CLOSE entry.
- ManageFlowFSM’s `_prepare_for_bracket_placement`:
  - Blocks new brackets while the closing flag is active within `anti_race_close_ms`.
  - Resets the flag after TTL or on new ENTRY.
- This prevents bracket re‑installation while a close is in flight.
- No evidence was found (in code or tests) of brackets being created after a DEC:CLOSE has been
initiated for the same symbol.

### 6.3 Watchdog vs Guardian responsibilities

- Aggregated OCO watchdog never places or cancels orders directly.
  - It only inspects `{positions, open_orders, bracket_metas}` and:
    - Logs violations.
    - Asks Guardian to clean or clear state (via `cleanup_orphans` and
      `clear_bracket_set_for_position`) when `auto_heal_orphans` is enabled.
- Guardian remains the single owner of:
  - `BracketSetMeta` lifecycle.
  - Order‑level cleanup decisions.

**Conclusion:** responsibilities between ManageFlow, Guardian, and watchdog are well separated; the
remaining complexity lies in the number of cleanup entry points rather than conflicting logic.


7. Test Coverage Review
-----------------------

### 7.1 Covered areas

- **Aggregated-only contract tests**
  - `test_contract_aggregated_orders_mode.py`:
    - Entry/exit payload cleanliness.
    - Aggregated bracket lifecycle (single meta per side, version bumps, full‑close cleanup, flip).
- **Multi‑entry / partial‑close flows**
  - `test_aggregated_oco_multi_entry_flow.py`:
    - Multi‑entry aggregation, partial close, full close, per‑symbol isolation.
- **Legacy vs aggregated regression**
  - `test_aggregated_oco_partial_close_legacy.py`,
    `test_aggregated_oco_scale_in_legacy.py`:
    - Demonstrate legacy gaps (xfail) and verify Aggregated OCO keeps SL coverage.
- **Guardian aggregated cleanup**
  - `test_order_guardian_aggregated_cleanup.py`:
    - TTL guard, cleanup of extra brackets, zero‑position cleanup, side normalization.
- **Watchdog invariants**
  - `test_agg_oco_invariants_checker.py`, `test_agg_oco_watchdog.py`:
    - All violation types and mixed payload forms.
- **Watchdog runtime integration**
  - `test_agg_oco_watchdog_runtime.py`:
    - Orphan SL cleanup when flat.
    - No auto‑heal when SL is missing but position is open.
    - DR rehydration and nominal flows without false positives.
- **Watchdog emit path**
  - `test_watchdog_emit_trade_executed.py`:
    - Ensures REST‑detected fills reach ManageFlowFSM and `_on_trade_executed`.

### 7.2 Gaps and missing tests

- **Config validation invariants**
  - No direct tests asserting that `_validate_manage_config` rejects:
    - `aggregated_only_mode=true, aggregated_oco.enabled=false`
    - `aggregated_only_mode=true, recalc_on_partial_close=false`
    - `aggregated_only_mode=true, allow_unprotected_position=true`
    - `aggregated_oco.watchdog.enabled=true, aggregated_only_mode=false`
- **Mixed regime behaviour**
  - No explicit ExecPosFSM + ManageFlowFSM test that runs with:
    - `aggregated_oco.enabled=true, aggregated_only_mode=false`
    - and documents the combined effect of inline TP/SL and Aggregated OCO brackets.
- **Quantity quantization edge cases**
  - Runtime logs show `ValueError("Quantity rounds to zero with stepSize")` bubbling from
    `BinanceAdapter.quantize_quantity` during `place_market_entry`.
  - There is no dedicated test asserting that such cases:
    - Produce a clear ERR / rejection to the caller, and
    - Leave no partial Guardian or bracket state behind.


8. Risks & Recommended Follow-ups
---------------------------------

### 8.1 Mixed aggregated / legacy regime

- **Risk.**
  - Configs with `aggregated_oco.enabled=true, aggregated_only_mode=false` enable Aggregated OCO
    in ManageFlowFSM but keep inline TP/SL in ExecPosFSM.
  - This can lead to overlapping SL/TP orders and unclear ownership.
- **Recommendation.**
  - Strengthen config validation so that in production either:
    - Aggregated OCO is fully disabled (pure legacy), or
    - Aggregated OCO is enabled with `aggregated_only_mode=true`, and inline TP/SL paths remain
      off.
  - Add tests that:
    - Assert `ConfigError` for unsupported combinations, or
    - Clearly document and validate the behaviour of mixed regimes if they must remain available
      for migration.

### 8.2 Tests for config invariants

- Add focused tests (e.g. in `tests/config/test_execution_manage_v2.py`) that construct configs
  with invalid combinations and assert that `_validate_manage_config` raises `ConfigError` for all
  forbidden patterns listed in 7.2.

### 8.3 Quantization / stepSize handling

- Based on the observed `Quantity rounds to zero with stepSize` error:
  - Add a regression test that:
    - Drives ExecPosFSM with a quantity below `step_size` for a symbol.
    - Confirms an ERR is emitted and that no brackets / Guardian state are created.
  - Consider documenting or validating per‑symbol `min_qty` and `step_size` to catch obviously
    untradeable strategy sizes at config time.

### 8.4 Observability and state snapshots

- To make Aggregated OCO easier to debug:
  - Reuse or extend the existing `agg_oco_snapshot` tooling so that, for a symbol, operators can
    quickly inspect:
    - live positions,
    - open reduceOnly/closePosition orders,
    - Guardian `BracketSetMeta` state.
  - Ensure watchdog and Guardian cleanup actions log both “before” and “after” states in a
    machine‑parsable form.

---

**High‑level conclusion.**

- For aggregated-only deployments with the shipped configs:
  - Legacy inline TP/SL is effectively disabled.
  - Aggregated OCO (ManageFlowFSM + OrderGuardian + watchdog) enforces the intended invariants:
    - SL present for open positions.
    - No brackets when flat.
    - Single `BracketSetMeta` per `(symbol, side)`.
  - Adapter usage is consistent with Binance Futures semantics.
- The main follow‑up work lies in:
  - Hardening config validation against mixed regimes.
  - Adding explicit tests for config invariants and quantity quantization.
  - Improving observability around Aggregated OCO state and cleanup.
