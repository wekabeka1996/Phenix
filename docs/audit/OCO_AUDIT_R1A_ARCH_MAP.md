# PACK OCO-AUDIT-R1 — R1-A Aggregated OCO Architecture Map

**Date:** 2025-11-23  
**RID:** OCO-AUDIT-R1-A-ARCH  
**Type:** Read-only architecture audit (no code changes)  
**Scope:** ExecPosRuntimeV2 + Aggregated OCO / TP‑SL lifecycle (shadow_execpos)

---

## 1. Scope & Goals

- Map how Aggregated OCO / TP‑SL is implemented around `ExecPosRuntimeV2`:
  - Modules/classes involved.
  - Events and entrypoints that trigger bracket logic.
  - How TP/SL plans (`PLACE_SL`, `PLACE_TP`, `CANCEL`, `ADJUST`) are produced and executed.
- Describe data flow:
  - Position sources (runtime mirror vs exchange snapshots).
  - Order sources (ORDERS_SNAPSHOT vs local mirror).
  - How data flows through `BracketService` to `ExecutionService`.
- Provide a TP/SL state machine for `(symbol, side)` and identify where the code binds TP/SL to positions and aggregates multiple orders into a single bracket set.

This document is descriptive only and reflects current behavior in:

- `apps/reference/domains/execution_position/shadow_execpos/*.py`
- `vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py`
- `apps/reference/domains/execution_position/manage_config.py`, `brackets_config.py`
- Docs: `EXEC_POS_BRACKETS_CONTRACT.md`, `FSM_EVENT_MAP.md`, `EXEC_POS_V2_RUNTIME_SPEC.md`, `OCO_aggregated_only_full_audit.md`

---

## 2. Module & Class Map (Aggregated OCO / TP‑SL)

| Module / File | Class / Concept | Role in Aggregated OCO / TP‑SL |
| --- | --- | --- |
| `shadow_execpos/runtime.py` | `ExecPosRuntimeV2` | Main orchestrator for execution_position V2; tracks positions & open orders, dispatches events, invokes `BracketService`, applies `BracketPlan` via `ExecutionService`, and calls `AggOcoWatchdogService`. |
| `shadow_execpos/bracket_service.py` | `BracketService`, `BracketRulesConfig`, `PositionView`, `OrderView`, `BracketState`, `BracketPlan`, `BracketAction` | Pure computation layer for bracket state: reconstructs bracket sets from positions+orders, checks invariants (missing SL, orphans, stale levels, too many legs), and emits `BracketPlan` with `CANCEL` / `PLACE_SL` / `PLACE_TP` / `ADJUST` actions. |
| `vfoundation/.../bracket_aggregator.py` | `compute_aggregated_brackets`, `AggregatedOcoRiskConfig`, `InstrumentPriceConstraints` | Pure price math: computes aggregated SL/TP levels from `(side, avg_entry_price, position_amt, sl_pct, tp_rr, constraints)`. Used by `BracketService._compute_desired_levels`. |
| `shadow_execpos/watchdog.py` | `AggOcoWatchdogService` | Detect-only watchdog that normalizes raw positions/orders into `BracketPositionView` / `BracketOrderView`, runs `BracketService.evaluate_all`, and converts `BracketPlan`s into `WatchdogRecommendation`s (kind + `WatchdogAction`). Runtime uses it primarily to trigger snapshot refresh. |
| `shadow_execpos/execution_service.py` | `ExecutionService` | Adapter facade that actually calls Binance adapter (`place_order`, `cancel_order`) for bracket actions. All `PLACE_SL` / `PLACE_TP` / `ADJUST` / `CANCEL` produced by `BracketService` go through here. |
| `shadow_execpos/runtime.py` | Guard / support services | `ExecPosGatekeeper` (entry guards), `PriceEnricher`, `FillIdempotency`, `EventIdempotency`, `ExecPosWALWriter`, `ExposureBridge`, `TrailingStopService`, `CloseFlowService` — not bracket-specific but participate in the event pipeline before/after bracket evaluation. |
| `shadow_execpos/event_adapter.py` | `MessageToRuntimeEventAdapter` | Converts legacy FSM `Message` objects (e.g. `CMD:OPEN`, `EVT:TRADE_EXECUTED`, `EVT:ORDERS_SNAPSHOT`) into `RuntimeEvent`s consumed by `ExecPosRuntimeV2`. |
| `runtime_factory.py` | `V2RuntimeFacade` | Bridges FSM ↔ `ExecPosRuntimeV2`: subscribes to `EVT:TRADE_EXECUTED`, `EVT:ACCOUNT_UPDATE_RECEIVED`, `EVT:TRADE_INTENT_PROPOSED`; fetches snapshots from adapter; sends `ORDERS_SNAPSHOT`, `TRADE_EXECUTED`, `POSITION_SYNC` events to runtime. |
| `manage_config.py` | `ExecutionManageConfig`, `BracketsMetaConfig`, `AggregatedOcoConfig` | Resolves manage/brackets/aggregated_oco configuration (enabled flags, recalc_on_* toggles, watchdog settings) from legacy + V2 configs. Currently not wired directly into `ExecPosRuntimeV2`; used mainly by legacy/manage flows. |
| `brackets_config.py` | `ResolvedBrackets` | Resolves basis points for SL/TP (sl_bps, tp_bps, offset_bps) from config. Used by legacy `ExecPosFSM` / ManageFlow; current V2 aggregated OCO relies instead on `sl_pct`/`tp_rr` via `BracketRulesConfig`. |
| `apps/reference/adapters/binance_execution_adapter.py` | adapter methods (`place_order_v2`, `get_open_orders`, etc.) | Concrete Binance Futures adapter used by `ExecutionService` and `V2RuntimeFacade` to send and query orders (entries, brackets, cleanups). |
| `apps/reference/domains/execution_position/docs/EXEC_POS_BRACKETS_CONTRACT.md` | Contract spec | Documents desired `BracketService` contract, invariants, and expected call patterns (including recalc on scale-in/partial close, orphan cleanup). |
| `docs/audit/OCO_aggregated_only_full_audit.md` | Legacy OCO audit | Full audit of legacy Aggregated-Only OCO path (ExecPosFSM + ManageFlowFSM + OrderGuardian). Serves as historical baseline; V2 runtime has partially reimplemented similar responsibilities. |

High-level architecture:

```text
WS / FSM Events
   ↓ (MessageToRuntimeEventAdapter, V2RuntimeFacade)
ExecPosRuntimeV2.handle(...)
   ↓
PositionState + open_orders mirrors
   ↓ (BracketPositionView / BracketOrderView)
BracketService.build_state(...) + evaluate(...)
   ↓
BracketPlan (CANCEL / PLACE_SL / PLACE_TP / ADJUST)
   ↓
ExecPosRuntimeV2._apply_bracket_plan(...)
   ↓
ExecutionService → BinanceAdapter (STOP_MARKET / TAKE_PROFIT_MARKET reduceOnly)
   + optional guardian.register_bracket_set / clear_bracket_set
```

---

## 3. Event Entry Points into Aggregated OCO

### 3.1 Runtime events and handlers

`ExecPosRuntimeV2.handle(event)` dispatches based on `kind`:

| `RuntimeEvent.kind` | Handler | Notes for TP/SL |
| --- | --- | --- |
| `ENTRY_INTENT` | `_handle_entry_intent` | Places entry order via `ExecutionService.place_order`; does **not** place TP/SL directly. Brackets are created later from fills and snapshots. |
| `CANCEL_INTENT` | `_handle_cancel_intent` | Cancel arbitrary order via `ExecutionService.cancel_order`; not TP/SL specific but may cancel brackets. |
| `CLOSE_INTENT` | `_handle_close_intent` | Invokes `CloseFlowService` / `ExecutionService` to close position; no direct bracket cleanup logic in V2 runtime. |
| `TRADE_EXECUTED` | `_handle_trade_executed` | Core fill handler: updates `PositionState` via `apply_fill`, writes WAL, emits exposure, runs watchdog, then calls `_evaluate_brackets(symbol, new_state, reason="trade_executed")`. |
| `POSITION_SYNC` | `_handle_position_sync` | Handles per-symbol position updates from account update; for non-flat positions triggers `_evaluate_brackets(symbol, current_state, reason="account_update_sync")`. |
| `POSITION_SNAPSHOT` | `_handle_position_snapshot` | Rebuilds positions from REST/WS snapshot; triggers watchdog but **does not** call `_evaluate_brackets` directly. |
| `ORDERS_SNAPSHOT` | `_handle_orders_snapshot` | Rebuilds `_open_orders_by_symbol`, updates `_orders_snapshot_state` (`UNKNOWN` → `FRESH`/`STALE`), triggers watchdog, and on first non-empty snapshot calls `_run_bracket_recovery_pass()` which uses `BracketService.evaluate_all` + `_apply_bracket_plan`. |

### 3.2 FSM / WS events that feed `ExecPosRuntimeV2`

From `runtime_factory.V2RuntimeFacade` and `shadow_execpos/event_adapter.py`:

| Legacy event | Mapping | Bracket-related behavior |
| --- | --- | --- |
| `CMD:OPEN` | → `ENTRY_INTENT` | Entry intent goes through Gatekeeper + ExecutionService, **without** inline TP/SL (aggregated OCO design). |
| `CMD:CANCEL` / `CMD:CANCEL_ORDER` | → `CANCEL_INTENT` | Can cancel brackets if caller targets SL/TP IDs. |
| `CMD:CLOSE`, `CMD:FORCE_CLOSE` | → `CLOSE_INTENT` | Closes positions; bracket cleanup is expected to be handled later via watchdog/recovery, not inline. |
| `EVT:TRADE_EXECUTED` / `EVT:FILL` / `EVT:PARTIAL_FILL` | → `TRADE_EXECUTED` | `V2RuntimeFacade.on_trade_executed` first calls `_sync_orders_and_handle_trade`: fetches `adapter.get_open_orders(symbol)` → emits `ORDERS_SNAPSHOT` → then passes `TRADE_EXECUTED` to runtime, ensuring fresh order mirror before bracket evaluation. |
| `EVT:ACCOUNT_UPDATE_RECEIVED` | → `_process_account_update` | Fetches full `get_open_orders()` (all symbols), emits `ORDERS_SNAPSHOT`, then per-position emits `POSITION_SYNC`. This pathway ensures account updates also maintain a consistent position+orders view for bracket logic. |
| `EVT:PORTFOLIO_STATE_UPDATED` / `POSITION_SNAPSHOT` | → `POSITION_SNAPSHOT` | Rehydrates positions on startup or periodic snapshots; supports DR but does not directly change brackets. |
| `EVT:OPEN_ORDERS_UPDATED` / `ORDERS_SNAPSHOT` | → `ORDERS_SNAPSHOT` | Direct orders snapshot events (e.g. from adapter); also feed `_handle_orders_snapshot`. |

---

## 4. How TP/SL Plans Are Produced and Executed

### 4.1 From runtime state to `BracketState`

For a given `(symbol, side)`:

1. `ExecPosRuntimeV2` holds:
   - `_positions_by_symbol[symbol] -> PositionState(qty, avg_entry_price, realized_pnl, ...)`
   - `_open_orders_by_symbol[symbol] -> list[raw_order_dict]`
   - `_orders_snapshot_state[symbol] -> "UNKNOWN" | "STALE" | "FRESH"` plus per-symbol snapshot timestamps.
2. `_evaluate_brackets(symbol, position, reason=...)`:
   - Checks suppression (`_is_brackets_suppressed` → currently always `False`) and snapshot freshness/TTL:
     - `snapshot_state == "FRESH"` but TTL expired → demoted to `"STALE"`.
     - For `reason in {"account_update_sync", "guard_loop"}` with non‑FRESH snapshot → log `BRACKETS` `result="snapshot_blocked"` and return.
     - For `reason=="trade_executed"` and `snapshot_state=="UNKNOWN"` → `snapshot_blocked` and return (this is mitigated by `_sync_orders_and_handle_trade()` and the S29 empty snapshot fix).
   - Throttles `reason=="account_update_sync"` evaluations using `_last_brackets_apply_ts[symbol]` (currently 3s).
   - Builds `BracketPositionView` from `PositionState` (abs qty, avg_entry_price, realized/unrealized PnL).
   - Normalizes `_open_orders_by_symbol[symbol]` into `BracketOrderView` (extracting order_id, client_order_id, side, type, qty, stop_price, reduce_only, etc.).
   - Calls `BracketService.build_state(positions=[pos_view], orders=order_views, symbol=symbol, side=position.side)` and fetches `BracketState` for key `(symbol, position.side)`.
3. `BracketService.build_state(...)`:
   - Groups positions by `(symbol, side)` and orders by `symbol`.
   - For each `(symbol, side)` key, calls `_classify_orders(orders_for_symbol, side, pos_view)` to classify orders as `BracketLeg`s:
     - reduce_only / close_position + STOP‑type → leg_type `"SL"`.
     - reduce_only / close_position + TAKE_PROFIT or LIMIT‑type → leg_type `"TP"`.
     - Non‑reduce_only orders compatible with the side are `ENTRY` legs (not used directly for TP/SL).
   - Builds `BracketSet` when there is at least one leg or a position:
     - `BracketSet.position_qty` = `pos_view.qty` (or 0 for flat).
     - `BracketSet.legs` = all classified entry/SL/TP legs.
   - Wraps into `BracketState(symbol, side, position_view, bracket_set, snapshot_ts)`.

### 4.2 From `BracketState` to `BracketPlan`

`BracketService.evaluate(state, cfg)` (using `BracketRulesConfig`) implements:

- **Invariant 1 — Flat position, no brackets:**
  - `state.is_flat` and `state.has_brackets` → `severity="WARN"`, `why="orphan_brackets|pos_flat_sl_or_tp_active"`.
  - Emits `CANCEL` actions for all SL and TP legs (`reason_code="ORPHAN_SL"/"ORPHAN_TP"`).
- **Invariant 2 — Open position, SL requirement:**
  - Non‑flat `state.position_view`:
    - `sl_count == 0` and `cfg.allow_unprotected_position==False`:
      - `severity="ALERT"`, `why="missing_sl|pos>0_sl_count=0"`.
      - Calls `_compute_desired_levels(...)` (aggregator) and emits `PLACE_SL` with `qty=state.position_view.qty`.
    - `sl_count == 0` and `allow_unprotected_position==True` → `severity="INFO"`, no actions.
    - If `tp_count == 0` and (there is at least one existing SL or a pending `PLACE_SL` in actions):
      - Emits `PLACE_TP` with `qty=state.position_view.qty`.
- **Invariant 2b — Too many SL legs:**
  - `sl_count > cfg.max_sl_legs`:
    - `severity="WARN"`, `why="too_many_sl|expected=..._actual=..."`.
    - Emits `CANCEL` for extra SL legs beyond the first `max_sl_legs`.
- **Invariant 3 — Stale levels:**
  - Exactly one SL (`sl_count == 1`) and `severity` still `"INFO"`:
    - Calls `_compute_desired_levels(...)` to get target SL/TP prices.
    - If current SL price != desired SL → `severity="WARN"`, `why="stale_levels|sl_...→..."`, emits:
      - `CANCEL` for old SL.
      - `PLACE_SL` at new price with `qty=state.position_view.qty`.
    - If a TP leg exists and its price != desired TP:
      - Emits `CANCEL` + `PLACE_TP` similarly.

**Important:** Current implementation does **not** inspect or adjust SL/TP *quantities* based on position_qty beyond simply using `state.position_view.qty` for newly placed legs. There is no explicit invariant like “sum(bracket_qty) ≤ abs(position_qty)” in `BracketService.evaluate` today.

### 4.3 From `BracketPlan` to actual TP/SL orders

`ExecPosRuntimeV2._apply_bracket_plan(symbol, position, plan, reason)`:

- Logs plan summary and each `BracketAction`.
- Derives `exit_side` from `position.side`:
  - LONG position → `exit_side="SELL"`, SHORT → `"BUY"`, FLAT → `exit_side=None`.
- For each `BracketAction`:
  - `CANCEL`:
    - Calls `ExecutionService.cancel_order(symbol, order_id=action.order_id, client_order_id=action.client_order_id)`.
  - `PLACE_SL` / `PLACE_TP` (if `exit_side` is not `None`):
    - Maps to Binance order type:
      - `PLACE_SL` → `STOP_MARKET`.
      - `PLACE_TP` → `TAKE_PROFIT_MARKET`.
    - Quantity:
      - `qty = float(action.qty)` if present, else `abs(position.qty)`.
    - Deduplication:
      - `_has_equivalent_bracket(symbol, exit_side, action)` scans `_open_orders_by_symbol[symbol]` for an existing reduceOnly bracket with matching side, type, qty (±5%) and price (~0.1% tolerance). If found → skip placing.
    - Client order id:
      - `_make_bracket_client_order_id(symbol, action_type, exit_side, qty, price, position)`:
        - If `position` provided, uses `_build_position_id(symbol, position)` → `qty_tag = |qty| formatted`, `price_tag = avg_entry_price`, and returns `"AUR-BRK-{symbol}-{position.side}-{action_type}-{position_id}"[:32]`.
        - Else, hashes `(symbol, action_type, exit_side, qty, price)` via SHA‑256.
    - Calls `ExecutionService.place_order(symbol, side=exit_side, order_type=..., quantity=qty, stop_price=..., client_order_id=..., reduce_only=True)`.
    - On timeout (`error_kind=="ADAPTER_ERROR_TIMEOUT"`): marks `_orders_snapshot_state[symbol]="UNKNOWN"`, `last_orders_snapshot_ts=0`, and requests a fresh `ORDERS_SNAPSHOT` (`_request_orders_snapshot(force=True)`), then returns early.
  - `ADJUST`:
    - If `action.order_id` present → cancels old order.
    - Chooses order_type based on `reason_code`:
      - `"MISSING_SL"` / `"STALE_LEVELS"` → SL (`STOP_MARKET`).
      - Else → TP (`TAKE_PROFIT_MARKET`).
    - Places new reduceOnly order similar to `PLACE_*`.

After iterating actions:

- Logs `BRACKETS_EXEC` runtime event with `why="brackets_{reason}"`.
- If `guardian` is injected:
  - If `placed_orders` is non-empty:
    - Calls `guardian.register_bracket_set(symbol=symbol, side=position.side or "FLAT", orders=placed_orders)` (async‑aware).
  - Else:
    - Calls `guardian.clear_bracket_set(symbol=symbol, side=position.side or "FLAT")`.

---

## 5. Event → Handlers → Effect on TP/SL (Summary Table)

For a given `symbol`:

| Event source | Runtime events emitted | Key handlers | Effect on TP/SL / brackets |
| --- | --- | --- | --- |
| `CMD:OPEN` (DecisionMaking) | `ENTRY_INTENT` | `_handle_entry_intent` | Places entry order only. No immediate TP/SL; TP/SL created later from fills via bracket pipeline. |
| `EVT:TRADE_EXECUTED` (WS) | `ORDERS_SNAPSHOT` (from `_sync_orders_and_handle_trade`), then `TRADE_EXECUTED` | `_handle_orders_snapshot`, `_handle_trade_executed`, `_evaluate_brackets(reason="trade_executed")` | Updates position via `apply_fill`; with FRESH snapshot, `BracketService` usually emits `PLACE_SL`/`PLACE_TP` for new positions; `_apply_bracket_plan` sends SL/TP to exchange. |
| `EVT:ACCOUNT_UPDATE_RECEIVED` (WS) | `ORDERS_SNAPSHOT` + `POSITION_SYNC` | `_handle_orders_snapshot`, `_handle_position_sync`, `_evaluate_brackets(reason="account_update_sync")` | Reconciles position and orders based on account update. For non-flat positions and FRESH snapshot, can (re)run bracket evaluation (e.g. after missed fills or partial closes). |
| `EVT:OPEN_ORDERS_UPDATED` / `ORDERS_SNAPSHOT` (WS/REST) | `ORDERS_SNAPSHOT` | `_handle_orders_snapshot`, `_run_bracket_recovery_pass` (once) | Keeps `_open_orders_by_symbol` mirror fresh; first non-empty snapshot triggers DR-style `BracketService.evaluate_all` over all positions to seed protection, adjust stale levels, or clean orphans. |
| Guard loop (internal timer) | — | `_guard_loop` → `_run_guard_iteration` → `_evaluate_brackets(reason="guard_loop")` | For each active (non-flat) position with fresh orders snapshot and sufficient cooldown, runs bracket evaluation to correct drift/orphans periodically. |
| Watchdog analysis (internal) | — | `_run_watchdog_analysis` → `AggOcoWatchdogService.analyze` | Translates `BracketPlan` severities into `WatchdogRecommendation`s. Runtime currently uses these only to trigger `_request_orders_snapshot` (SUPPRESS_BRACKETS is disabled); no direct bracket cancel/place. |

---

## 6. TP/SL State Machine (Conceptual)

The effective TP/SL state machine is defined over `(symbol, side)` using a combination of:

- `PositionState` (`qty`, `side`).
- `BracketState` (`position_view`, `bracket_set.sl_legs`, `bracket_set.tp_legs`).
- Snapshot state (`_orders_snapshot_state[symbol]`).

### 6.1 States

Conceptual states for `(symbol, side)`:

- **`NO_POSITION`**:
  - `PositionState.qty ≈ 0`, or no `PositionState` entry.
  - No active reduceOnly SL/TP orders for this `(symbol, side)`.
- **`POSITION_WITH_NO_BRACKETS`**:
  - `abs(PositionState.qty) > 0`, `BracketState.sl_count == 0` and `tp_count == 0`.
  - Evaluating with `allow_unprotected_position=False` → `PLACE_SL` (and `PLACE_TP`) plan.
- **`POSITION_WITH_TP_SL`**:
  - `abs(qty) > 0`, `sl_count ≥ 1`, `tp_count ≥ 0`.
  - Sub-cases:
    - “Aligned”: levels close to `_compute_desired_levels` → `severity="INFO"`, no actions.
    - “Stale levels”: price drift → `CANCEL` + `PLACE_SL/TP`.
    - “Too many SLs”: `sl_count > max_sl_legs` → `CANCEL` extras.
- **`POSITION_WITH_ORPHAN_BRACKETS`**:
  - `PositionState.qty ≈ 0` (or no position), but `BracketState.has_brackets` is true.
  - `BracketService.evaluate` produces `CANCEL` actions for all SL/TP (Invariant 1).
  - In current runtime, this cleanup is only actively used via `_run_bracket_recovery_pass` (and potentially future wiring), not on every transition.
- **`UNKNOWN_ORDERS_STATE`**:
  - `_orders_snapshot_state[symbol] == "UNKNOWN"` or `"STALE"`, or TTL exceeded.
  - Bracket evaluation for reasons `account_update_sync` / `guard_loop` is skipped and logged as `BRACKETS` `result="snapshot_blocked"`.
  - For `trade_executed`, an `UNKNOWN` state blocks brackets until at least one snapshot is applied (S23/S29 fixes reduce but do not entirely eliminate this transient).

### 6.2 Transitions (high level)

Using `q` = `abs(PositionState.qty)`:

```mermaid
stateDiagram-v2
    [*] --> NO_POSITION

    NO_POSITION --> POSITION_WITH_NO_BRACKETS: TRADE_EXECUTED (q>0) + snapshot FRESH
    POSITION_WITH_NO_BRACKETS --> POSITION_WITH_TP_SL: BracketService PLAN(ALERT/WARN) → PLACE_SL/PLACE_TP applied

    POSITION_WITH_TP_SL --> POSITION_WITH_TP_SL: SCALE_IN (TRADE_EXECUTED same side) → avg_entry_price, q↑ → stale_levels → CANCEL+PLACE_SL/TP
    POSITION_WITH_TP_SL --> POSITION_WITH_TP_SL: GUARD_LOOP / ACCOUNT_UPDATE_SYNC with drift → stale_levels / too_many_sl → CANCEL and/or PLACE

    POSITION_WITH_TP_SL --> POSITION_WITH_ORPHAN_BRACKETS: FULL_CLOSE (q→0) but SL/TP still on exchange
    POSITION_WITH_ORPHAN_BRACKETS --> NO_POSITION: BracketService PLAN(WARN orphan_brackets) → CANCEL SL/TP (recovery path)

    NO_POSITION --> UNKNOWN_ORDERS_STATE: missing / stale ORDERS_SNAPSHOT
    POSITION_WITH_* --> UNKNOWN_ORDERS_STATE: snapshot TTL exceeded → `snapshot_blocked` (skips bracket evaluation)
    UNKNOWN_ORDERS_STATE --> (re-evaluate same logical state): fresh ORDERS_SNAPSHOT applied → `_orders_snapshot_state` FRESH
```

**Where transitions are implemented:**

- Position changes (OPEN, SCALE_IN, PARTIAL_CLOSE, REVERSE, FULL_CLOSE) come from:
  - `_handle_trade_executed` via `apply_fill`.
  - `_handle_position_sync` / `_handle_position_snapshot` via exchange snapshots.
- Bracket actions that cause state transitions are produced by:
  - `_evaluate_brackets` (per-symbol) for `reason in {"trade_executed", "account_update_sync", "guard_loop"}`.
  - `_run_bracket_recovery_pass` (global, DR/rehydrate).
- Snapshot gating and state `UNKNOWN_ORDERS_STATE` are controlled purely by:
  - `_handle_orders_snapshot`, `_mark_orders_snapshot`, `_is_orders_snapshot_fresh`, and `_orders_snapshot_state[symbol]`.

---

## 7. Binding TP/SL to Positions & Aggregation Semantics

### 7.1 Binding TP/SL to positions

Current binding keys:

- **Runtime mirror:**
  - Positions: `_positions_by_symbol[symbol] -> PositionState`.
  - Orders: `_open_orders_by_symbol[symbol] -> [order_dict]`.
  - Side is derived from `PositionState.qty` (`LONG`/`SHORT`/`FLAT`).
- **BracketService keys:**
  - `BracketState` keyed by `(symbol, side)` — this is the primary logical key for a “position + bracket set”.
  - `BracketSet.position_qty` mirrors `PositionView.qty`.
- **Client order id / bracket identity:**
  - `_make_bracket_client_order_id()` encodes a “position fingerprint” via:
    - `_build_position_id(symbol, position)` → formatted `|qty|` and `avg_entry_price` tags.
    - `clientOrderId` prefix `"AUR-BRK-{symbol}-{position.side}-{action_type}-{position_id}"` truncated to 32 chars.
  - No explicit `position_id` or `position_version` is tracked; identity is implicit via `(symbol, side, qty, avg_entry_price, action_type)`.
- **Guardian link:**
  - When `guardian` is provided, `register_bracket_set(symbol, side, orders)` / `clear_bracket_set(symbol, side)` is called from `_apply_bracket_plan`, using `PositionState.side` as guardian side.
  - This mirrors the “one bracket set per (symbol, side)” contract from legacy `OrderGuardian`, but without a first-class position identifier.

**Implications:**

- TP/SL linkage is **per symbol+side**, not per unique `position_id`. Multiple independent open/close cycles with identical `(qty, avg_entry_price)` can share the same clientOrderId fingerprint.
- Without `position_id`/versioning, distinguishing “old bracket orders from previous position” vs “new bracket set for current position” relies on price/qty differences and eventual cleanup via recovery/watchdog.

### 7.2 Aggregation of partial orders into a single bracket set

- Aggregation happens in `BracketService._classify_orders`:
  - Takes all `OrderView`s for a given `symbol`.
  - Filters by compatibility with `side`:
    - For **LONG** positions: exit orders must be `side="SELL"` and `reduce_only` (or `close_position`).
    - For **SHORT** positions: exit orders must be `side="BUY"` and `reduce_only`/`close_position`.
  - Classifies each compatible order as `BracketLeg` of type:
    - `"SL"` for `STOP_MARKET` / `STOP` reduceOnly orders.
    - `"TP"` for `TAKE_PROFIT_MARKET` / `TAKE_PROFIT` (and `LIMIT` reduceOnly).
    - `"ENTRY"` for non-reduceOnly orders (entries/scale-ins).
  - All legs for `(symbol, side)` are packed into a single `BracketSet`:
    - `BracketSet.position_qty` is the *aggregated* position quantity for that `(symbol, side)` (from `PositionView.qty`).
    - `BracketSet.legs` includes **all** attached SL/TP legs; invariants limit counts (`max_sl_legs`, `max_tp_legs`) but do not create multiple distinct bracket sets.
- Quantitative aggregation:
  - `PositionView.qty` is computed from `PositionState.qty` using `abs(qty)`; all SL/TP legs are treated as protecting this aggregated quantity.
  - There is currently **no explicit check** that the sum of SL/TP quantities equals (or is bounded by) `PositionView.qty`; aggregation is primarily in terms of *count* of legs and price levels.

---

## 8. Noted Gaps vs Contracts (for later phases)

This audit does **not** propose changes, but highlights discrepancies that matter for R1‑B/R1‑C:

- **Size invariants not enforced in `BracketService`:**
  - Contract docs talk about aggregated protection of the current position; however, the implementation:
    - Does not compare `sum(sl_leg.qty)` / `sum(tp_leg.qty)` to `position_qty`.
    - Only uses `position_qty` when *placing new* SL/TP (missing/stale), not when checking existing legs for oversizing.
- **Partial close recalc semantics:**
  - `BracketRulesConfig` includes `recalc_on_partial_close` / `recalc_on_scale_in`, but `BracketService.evaluate()` does not inspect fill roles or quantities and has no branch keyed off these flags.
  - Scale-in recalc happens indirectly via `avg_entry_price` change (price drift) and `stale_levels` detection.
  - Partial close that does **not** change `avg_entry_price` is not currently detected as requiring bracket qty adjustment — brackets may remain sized for the old, larger position.
- **Full close + orphan cleanup:**
  - `BracketService.evaluate()` can cancel orphans when invoked on a flat state with brackets.
  - In the runtime:
    - `_evaluate_brackets` is only called when `PositionState.side in {"LONG","SHORT"}` (non-flat).
    - Guard loop skips symbols with `abs(pos.qty) == 0`.
    - `_run_bracket_recovery_pass` runs **once** after initial non-empty `ORDERS_SNAPSHOT` (DR path) and sets `_recovery_completed=True`.
  - Result: continuous-orphan cleanup after full close relies on external systems (e.g. OrderGuardian) or future wiring, not on the current runtime+BracketService loop.
- **Race‑sensitive binding (no `position_id`):**
  - All bracket binding is keyed by `(symbol, side)` and price/qty fingerprint, not `position_id`.
  - In fast close‑then‑reopen sequences, there is no hard boundary preventing SL/TP from a previous position being interpreted as valid brackets for a new position if quantities and prices are compatible.
- **Spec vs implementation drift:**
  - `docs/EXEC_POS_V2_RUNTIME_SPEC.md` still states that:
    - BracketService is “observe-only” and runtime does not execute plans.
  - In code:
    - `_evaluate_brackets` and `_run_bracket_recovery_pass` actively call `_apply_bracket_plan`, which issues `ExecutionService.place_order`/`cancel_order` and updates guardian metadata.
  - Future contract updates should reconcile this and clearly flag V2 runtime as *executing* aggregated OCO plans.

These points are inputs into R1‑B (size-sync invariants), R1‑C (race-condition analysis), and R1‑D (test plan), not changes to behavior within this audit phase.

