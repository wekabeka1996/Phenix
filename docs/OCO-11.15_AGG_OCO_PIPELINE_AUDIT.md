# OCO-11.15 Aggregated-OCO Pipeline Audit

## Problem Statement
After completing OCO-11.14 and passing all aggregated-OCO unit tests, live TP/SL brackets still fail to appear on the exchange. This points to a mismatch between the tested pipeline and the real runtime path or to a configuration/guard regression that prunes decisions before they reach the adapter.

> "After the successful rollout of OCO-11.14 and passing aggregated-OCO tests, TP/SL still fail to appear on the exchange in live mode. We suspect a drift between the tested pipeline and the real runtime or a configuration/guard regression."

## Expected Pipeline (docs + current implementation)
```
EVT:TRADE_EXECUTED (watchdog / fill)
  → ExecPosFSM.handle(...)
    → delegates to ManageFlowFSM (aggregated-only)
      → _handle_aggregated_fill_event()
      → _compute_aggregated_brackets()
      → _normalize_reduce_only_qty() + qty_guard
      → _emit_place_order() → DEC:PLACE_ORDER
  → ExecPosFSM._execute_decision(verb="PLACE_ORDER")
    → adapter.place_* (SL/TP)
    → OrderGuardian / BracketSetMeta
    → AGG_OCO_BRACKETS_PLACED
```

## Key Files In Scope
- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/fsm_manage.py`
- `apps/reference/domains/execution_position/order_guardian.py`
- `apps/reference/domains/execution_position/qty_guard.py`
- `apps/reference/domains/execution_position/brackets_config.py`
- `apps/reference/domains/execution_position/manage_config.py`
- `tests/domains/execution_position/test_agg_oco_fill_to_brackets_pipeline.py`
- `tests/domains/execution_position/test_contract_aggregated_orders_mode.py`
- `tests/domains/execution_position/test_execpos_place_order_decisions.py`
- `tests/domains/execution_position/test_agg_oco_min_qty_guard_runtime.py`
- `tests/config/test_execution_manage_v2.py`

## Findings Overview
### ExecPosFSM `DEC:PLACE_ORDER` Path (apps/reference/domains/execution_position/fsm.py)

- `_execute_decision` contains a single explicit branch for `verb == "PLACE_ORDER"` (line ~2810) that immediately forwards to `_handle_place_order_decision`; there are no aggregated-only feature flags or `self._aggregated_only_mode` checks that could short-circuit DEC execution before adapter calls.
- `_handle_place_order_decision` expects ManageFlow to provide a complete payload and explicitly reads:
  - `symbol`, `side`, `qty` (stringified), `order_type` (STOP_MARKET / TAKE_PROFIT_MARKET / LIMIT), `price` (for LIMIT), `stopPrice` (for STOP/TP), `position_side`, `reduceOnly`, `closePosition`, and `newClientOrderId`.
  - Reduce-only enforcement: returns early if both `reduceOnly` and `closePosition` flags are false, meaning any DEC lacking those booleans is silently dropped.
- Adapter dispatch table:
  - `STOP_MARKET` ⇒ `adapter.place_stop_market_close_position(symbol, side, stop_price, position_side, new_client_order_id)`.
  - `TAKE_PROFIT_MARKET/TAKE_PROFIT` ⇒ `adapter.place_take_profit_market_close_position(...)` with the same signature.
  - `LIMIT` ⇒ `_call_reduce_only_order(adapter.place_limit_reduce_only, symbol, side, price, qty, position_side, new_client_order_id)`; still requires reduce-only semantics.
- After adapter success, order IDs are tracked via `_symbol_brackets` and `_record_aggregated_bracket_success`, culminating in the `AGG_OCO_BRACKETS_PLACED` log as soon as both SL+TP order IDs return.
- No guard present that would skip adapter execution in aggregated-only mode; the only drop conditions are malformed payload fields (missing symbol/side/order_type/stop) or reduceOnly/closePosition absent.

### ManageFlow DEC Emission + Guards (apps/reference/domains/execution_position/fsm_manage.py)

- `_place_or_update_bracket_set_from_levels` orchestrates aggregated bracket placement: it captures previous SL/TP snapshots, computes `why` metadata, and calls `_build_sl_tp_client_ids` to derive `newClientOrderId` base/variants. `_current_bracket_set_id` is set to the truncated seed so OrderGuardian can register the pair once ExecPos reports back.
- `_emit_place_order` always targets `dst="execution_position"`, replicating the EVT→DEC route used in runtime. Payload contract includes: `symbol`, `side`, `qty`, `order_type`, `price` (LIMIT only), `stopPrice` (STOP/TP), `reduceOnly=True`, `newClientOrderId`, `workingType`, and `priceProtect`. The WHY chain is preserved via `idempotent_key=client_id` and `data_ref=msg.data_ref`.
- `_normalize_reduce_only_qty` is the only place that can squelch DEC emission: when `_aggregated_only_mode` is enabled it invokes `ExecutionQtyGuard.evaluate(symbol, qty_abs, price)` and returns `None` if `allowed` is false or if `qty_str()` is falsy. Any `None` bubbles up, the FSM reverts to `TRACKING`, and no DEC is emitted.
- `_select_guard_price` feeds the guard with the minimum of SL/TP levels, so even a healthy qty can be rejected if price is low enough to violate `min_notional` or `min_qty`. Recent min-qty guard tweaks therefore directly control whether aggregated brackets ever leave ManageFlow.
- No extra aggregated-only kill switches exist in `_emit_place_order`; the method does not inspect `_aggregated_only_mode` or `_closing_position`. Skips only happen earlier (`_closing_position` gating inside `_handle_aggregated_fill_event`, guard returning `None`, or `_compute_aggregated_bracket_levels` raising `AggregatedOcoError`).

## Runtime Regression Candidates
_(Populate after comparing runtime vs tests.)_

## Test Harness vs Runtime Path

- `tests/domains/execution_position/test_agg_oco_fill_to_brackets_pipeline.py`
  - Builds ExecPosFSM through `agg_oco_test_utils.make_execpos`, which forces `shadow_mode=True`, injects `LocalBus`, stubs OrderGuardian/Watchdog, and never spins the actual FSMCore bus.
  - `fsm.handle(EVT:TRADE_EXECUTED)` synchronously returns a single `DEC:PLACE_ORDER` message (ManageFlow result) that the test immediately feeds back into `_execute_decision`. In production, ManageFlow emits DEC back onto the FSM bus and ExecPosFSM schedules `_execute_decision` asynchronously; the test therefore bypasses WAL logging, bus routing, and concurrency windows.
  - Adapter interactions are mocked via `RecordingBracketAdapter` assigned manually; no real adapter lifecycle, connection guardrails, or config overrides are exercised.

- `tests/domains/execution_position/test_execpos_place_order_decisions.py`
  - Calls `_execute_decision` directly with handcrafted DEC messages, completely skipping the ManageFlow computation, qty guard, WAL append, and bus idempotency logic. These tests validate adapter fan-out but offer no signal about whether DEC ever reaches `_execute_decision` in runtime.

- `tests/domains/execution_position/test_contract_aggregated_orders_mode.py`
  - Uses `shadow_mode=True` ExecPosFSM tied to a `MagicMock` FSM core and stubbed adapter/guardian/watchdog (injected via monkeypatch). All DEC routing again returns from `handle()` directly instead of traversing the FSM core event bus. Harness utilities (`AggregatedOcoHarness`) fast-forward ManageFlow state changes by calling helpers directly.

- `tests/domains/execution_position/test_agg_oco_min_qty_guard_runtime.py`
  - Instantiates `ManageFlowFSM` in isolation with a fake `ExecutionQtyGuard`, replacing `_emit_place_order` via `types.MethodType` to capture payloads. There is no ExecPosFSM, adapter, or message bus; the guard is exercised in unit isolation, so regressions caused by integrating guard decisions with actual config profiles or runtime providers remain invisible.

**Implication:** Current integration tests short-circuit key pipeline segments (FSMCore bus, WAL, async `_execute_decision`, adapter wiring). They cannot detect regressions where DEC messages are dropped before `_execute_decision` (e.g., due to guard/config drift or bus routing misconfiguration). A new runtime-style test must simulate the real bus, aggregated-only config, and adapter spy to close this coverage gap.

## Proposed Fix Plan
_(Populate after isolating the failing link.)_
