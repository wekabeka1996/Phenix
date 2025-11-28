# ExecPosRuntimeV2 Runtime Specification

**Status:** Canonical (ExecPosRuntimeV2 is the default runtime)
**Last verified against code:** 2025-11-21
**Sources:** `apps/reference/domains/execution_position/shadow_execpos/*.py`, tests under `tests/domains/execution_position/shadow_execpos/`

## 1. Overview & Scope
- Describes the current, working behavior of `ExecPosRuntimeV2` (no legacy dual-runtime semantics).
- Covers API, event model, state model, core flows, WAL/exposure interactions, invariants, and known limitations.
- Reflects existing code; any unimplemented items are called out as TODOs, not asserted as done.

## 2. Runtime API & Construction
- Constructed directly or via `runtime_factory.V2RuntimeFacade` (default `runtime_mode="v2"`).
- Core entrypoints:
  - `handle(event | dict)`: async dispatcher for `RuntimeEvent` or dict with `kind`, `symbol`, `payload`.
  - `hydrate(snapshot)`: preloads `positions` and `orders` into in-memory maps.
  - `get_metrics()` / `get_metrics_snapshot()`: returns metrics dict (see §7).
  - `shutdown()`: placeholder, logs shutdown only.
- Services composed:
  - `ExecPosAsyncManager` (infrastructure, not directly exposed)
  - `ExecutionService` (adapter facade with retry/error normalization)
  - `ExecPosGatekeeper` (entry guards)
  - `PriceEnricher` (fill enrichment)
  - `FillIdempotency` (with TTL-based cleanup)
  - `AggOcoWatchdogService` (detect-only)
  - `ExecPosWALWriter` (writes EXEC_TRADE / EXEC_POSITION)
  - `ExposureBridge` (emits exposure updates)

## 3. Event Model
- Runtime events (`RuntimeEvent.kind`):
  - `ENTRY_INTENT`, `CANCEL_INTENT`, `CLOSE_INTENT`
  - `TRADE_EXECUTED`
  - `POSITION_SNAPSHOT`, `ORDERS_SNAPSHOT`
- Legacy Message → RuntimeEvent mapping: `shadow_execpos/event_adapter.py` (see also updated `FSM_EVENT_MAP.md`).
  - `CMD:OPEN` → `ENTRY_INTENT` (side, qty, price, order_type, client_order_id…)
  - `CMD:CANCEL`/`CMD:CANCEL_ORDER` → `CANCEL_INTENT` (order_id/client_order_id)
  - `CMD:CLOSE`/`CMD:FORCE_CLOSE` → `CLOSE_INTENT` (qty optional, reason)
  - `EVT:TRADE_EXECUTED`/`EVT:FILL`/`EVT:PARTIAL_FILL` → `TRADE_EXECUTED` (qty/price/role/cum_qty…)
  - `EVT:PORTFOLIO_STATE_UPDATED`/`POSITION_SNAPSHOT`/`ACCOUNT_UPDATE` → `POSITION_SNAPSHOT`
  - `EVT:OPEN_ORDERS_UPDATED`/`ORDERS_SNAPSHOT` → `ORDERS_SNAPSHOT`

## 4. State Model
- `_positions_by_symbol`: `{symbol: {symbol, qty, side|direction, position_size, entry_price, avg_price?, margin?, realized_pnl?, unrealized_pnl?}}`
  - Qty is float; entry_price set on first open; no averaging on subsequent fills (limitation).
- `_open_orders_by_symbol`: `{symbol: [{order_id, client_order_id, symbol, side, quantity, price, type}]}`. No bracket metadata is tracked.
- Idempotency stores: `FillIdempotency._seen_fills` keyed by `symbol|side|order_id` with TTL-based cleanup.
- Metrics dict: see §7.

## 5. Core Flows (Actual Behavior)
### 5.1 ENTRY_INTENT
- Gatekeeper runs guards (min qty/notional, step sizes, cooldown) → `GateDecision`.
- On allow: ExecutionService `place_order(...)`; success appends open order to `_open_orders_by_symbol`.
- No bracket/TP/SL placement is performed by RuntimeV2 today.

### 5.2 CANCEL_INTENT
- ExecutionService `cancel_order(...)`; success removes matching order_id from `_open_orders_by_symbol`.

### 5.3 CLOSE_INTENT
- ExecutionService `close_position(symbol, quantity)` is invoked.
- On success: clears position entry for symbol (`qty=0`, side=FLAT). No bracket cleanup, no close-FSM logic (stub/limitation).

### 5.4 TRADE_EXECUTED
Ordering: idempotency → enrichment → state update → WAL → exposure → watchdog.
- Idempotency: `FillIdempotency.should_process_fill` drops duplicate cumulative qty.
- Enrichment: `PriceEnricher.enrich_trade` (payload/position/quote price preference).
- State update:
  - Maintains qty and direction; adds/subtracts based on side BUY/SELL.
  - Sets `entry_price/avg_price` only on first open; no weighted average thereafter (limitation).
- WAL:
  - `ExecPosWALWriter.write_trade_wal` for EXEC_TRADE.
  - `ExecPosWALWriter.write_position_wal` for EXEC_POSITION when state changes.
- Exposure: `ExposureBridge.emit_exposure_update` with net size/direction/exposure_usdt.
- Watchdog: `AggOcoWatchdogService.analyze` runs; recommendations logged/metrics only—no automated actions are executed.

### 5.5 POSITION_SNAPSHOT / ORDERS_SNAPSHOT
- `POSITION_SNAPSHOT`: rebuilds `_positions_by_symbol` using normalized qty/entry_price/side; triggers watchdog.
- `ORDERS_SNAPSHOT`: clears and repopulates `_open_orders_by_symbol`; triggers watchdog.

## 6. Aggregated OCO / Close / Trailing Semantics\n- Aggregated OCO logic (compute levels, auto-heal, OrderGuardian integration) is **not implemented** in RuntimeV2.\n- Watchdog only detects bracket invariants (NO_SL_FOR_OPEN_POSITION, ORPHAN_SL_FOR_ZERO_POSITION, TOO_MANY_SL_FOR_OPEN_POSITION, MULTIPLE_META_SETS) and returns recommendations; RuntimeV2 does **not execute** cancel/place actions.\n- Close Flow FSM (stateful close conditions) is **not ported**; Runtime delegates CLOSE_INTENT decisions to shadow_execpos/close_flow.py (plan_close ? close_position calls). No bracket cleanup or multi-step close FSM yet.\n- Trailing stop / breakeven / time-stop logic is invoked via shadow_execpos/trailing.py for logging/signals; no auto-placement/cancel yet.\n- Brackets: BracketService is invoked after fills to build/evaluate bracket state (observe-only). Plans are logged and counted in metrics; no adapter/guardian mutations are performed.\n\n## 7. Metrics & Observability
- Runtime metrics (`ExecPosRuntimeV2._metrics`):
  - Counters: `events_total`, `events_by_kind`, `gatekeeper_allowed/rejected`, `execution_success/failed`, `fills_processed/duplicate`, `watchdog_violations`, `watchdog_violations_by_kind`, `wal_trades_written`, `wal_positions_written`, `exposure_updates_emitted`.
  - Derived: `positions_tracked`, `symbols_active`, `open_orders_tracked`, `status`.
- WAL writer metrics: trades/orders/positions written, write_errors.
- Exposure bridge metrics: exposures_emitted, emit_errors.
- Logging: `shadow_execpos/logging_v2.py` structured logs for ENTRY_INTENT outcomes; watchdog warnings are logged.
- Observability doc: `apps/reference/domains/execution_position/docs/EXECUTION_POSITION_V2_OBSERVABILITY.md`.

## 8. Safety & Invariants
- Invariants documented in `apps/reference/domains/execution_position/EXECUTION_POSITION_INVARIANTS.md` (I1–I6: single position per symbol, SL requirement, no orphans, finite values, idempotency, out-of-order consistency).
- Enforcement in code:
  - Idempotency on fills.
  - Watchdog detection (no auto-heal).
  - Concurrency harness tests for race patterns.
- Fail-closed philosophy: WAL/exposure/logging failures are logged and increment metrics but do not raise.

## 9. Known Limitations & TODOs (as of 2025-11-21)
- No Aggregated OCO computation or OrderGuardian integration; watchdog is detect-only.
- No trailing stop / breakeven / time-stop logic wired; `shadow_execpos/trailing.py` provides pure logic not yet integrated.
- Close flow is a stub; no stateful close FSM or bracket cleanup. `shadow_execpos/close_flow.py` provides pure logic not yet integrated.
- Position averaging on scale-in is not implemented in runtime state; `shadow_execpos/position_model.py` provides correct averaging and realized PnL for future integration.
- Watchdog recommendations are not executed; no auto-cancel/replace path.
- Config contract is ad-hoc (gatekeeper/watchdog keys expected in `config` dict); no unified schema.
- Exposure updates use simple `qty*entry_price` and may miss leverage/mark-price nuances.
- Runtime factory defaults to V2; legacy fallback is not currently supported in code.

## 10. Runtime – Tests Mapping
- `test_runtime_concurrency_edge_cases.py`: out-of-order/duplicate fills, invariant assertions (I1–I6).
- `test_runtime_integration_replay.py`, `test_runtime_wiring.py`, `test_shadow_runtime_skeleton.py`: wiring and basic event handling.
- `test_event_adapter.py`: Message ↔ RuntimeEvent normalization.
- `test_execution_service_ported_logic.py`: adapter error handling and retries.
- `test_gatekeeper_ported_logic.py`: guard parity.
- `test_watchdog_ported_logic.py`, `test_watchdog_gatekeeper_price_enricher_contracts.py`: invariant detection contracts.
- `test_wal_writer.py`: WAL write behavior/metrics.
- `test_v2_logging_runtime.py`, `test_v2_metrics_snapshot.py`: observability and metrics snapshot.
- `test_runtime_facade_integration.py`: runtime_factory facade behavior.






