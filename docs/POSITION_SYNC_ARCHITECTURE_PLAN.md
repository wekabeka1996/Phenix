# Position & Order Sync Architecture Plan (Draft)

> Draft by GitHub Copilot – unified view on keeping positions and TP/SL orders in sync with Binance at all times.

## 1. Goals & Non‑Goals

### 1.1. Goals

- Ensure the system **never loses executed trades**: every Binance fill must either immediately or eventually appear in the internal portfolio state.
- Make `EVT:TRADE_EXECUTED` the **canonical, unified event** for fills from all sources (WS, REST, account observer, DR replay).
- Guarantee that `PositionTracking` always converges to the **true Binance state** via account snapshots (`EVT:ACCOUNT_UPDATE_RECEIVED`).
- Maintain a consistent mapping between **positions and their TP/SL orders**, with regular reconciliation and orphan cleanup.
- Preserve existing DR guarantees (WAL, replay) while avoiding situations where WAL issues silently freeze portfolio updates in testnet/dev.

### 1.2. Non‑Goals

- No changes to external APIs or configs consumed by other services.
- No breaking changes to message schemas (only additive fields / new event sources).
- No changes to risk/decision logic, except where it must read improved portfolio/exposure signals.

---

## 2. Target Architecture (High‑Level)

### 2.1. Event & Snapshot Model

- **Primary source** for portfolio updates: `EVT:TRADE_EXECUTED` events.
- **Secondary (fallback) source** for portfolio updates: `EVT:ACCOUNT_UPDATE_RECEIVED` (plus `/fapi/v2/positionRisk`).
- **DR & replay**: TRADE/ACCOUNT events are WAL‑logged and can be replayed to recover state after restart.
- **Deduplication layer** (in `PositionTracking`): all incoming trade events are normalized into an idempotent key and processed exactly once per trade.

### 2.2. Data Flow Overview

1. Binance Futures Testnet/Mainnet → WebSocket `ORDER_TRADE_UPDATE` / `ACCOUNT_UPDATE`.
2. `BinanceExecutionAdapter`:
   - Normalizes WS events.
   - Emits:
     - `EVT:TRADE_EXECUTED` for order fills.
     - `EVT:ACCOUNT_UPDATE_RECEIVED` for account snapshots.
3. `OrderTimeoutWatchdog`:
   - Polls REST `/fapi/v1/order`.
   - Detects late fills or cancels not visible via WS.
   - Emits `EVT:TRADE_EXECUTED` / `EVT:ORDER_STATE_CHANGED` via hooks.
4. `AccountObserver`:
   - Polls `get_my_trades` for each tracked symbol.
   - Emits `EVT:TRADE_EXECUTED` for any fills missed by other paths.
5. `PositionTracking`:
   - Subscribes to `EVT:TRADE_EXECUTED`, `EVT:ACCOUNT_UPDATE_RECEIVED`, `EVT:BALANCE_UPDATE_RECEIVED`.
   - Updates positions, equity, margin usage.
   - Emits `EVT:PORTFOLIO_STATE_UPDATED` as the **single portfolio source of truth**.
6. `ExecPosFSM` + `ExposureGuard` + `OrderGuardian`:
   - Listen to `EVT:PORTFOLIO_STATE_UPDATED` and `EVT:TRADE_EXECUTED`.
   - Maintain exposure state and bracket (TP/SL) ownership.
   - Periodically sync open TP/SL against `/fapi/v1/openOrders` and `PositionTracking` state.

---

## 3. Concrete Changes (Planned Patches)

### 3.1. Unify Fills as EVT:TRADE_EXECUTED

#### 3.1.1. AccountObserver emits TRADE_EXECUTED

**File:** `apps/reference/domains/account_observer/account_observer.py`

**Current:** `_process_trades` emits `EVT:FILL` with a TRADE_EXECUTED‑compatible payload.

```python
self.fsm.emit(
    "EVT:FILL",
    payload=payload,
    why="Detected new user fill from Binance account.",
)
```

**Planned change:**

- Emit `EVT:TRADE_EXECUTED` instead of `EVT:FILL`.
- Optionally retain `EVT:FILL` for backward compatibility (dual emit) but mark it as legacy.

**Patch sketch (additive):**

- Replace single emit with dual path:
  - `EVT:TRADE_EXECUTED` (canonical).
  - `EVT:FILL` (legacy, can be removed later).

#### 3.1.2. BinanceExecutionAdapter: do not drop unmatched fills

**File:** `apps/reference/domains/execution_position/binance_execution_adapter.py`

**Current behavior:** `_handle_order_trade_update` requires `order_index` correlation and otherwise logs "No correlation found" and returns.

```python
if not order_ref:
    logger.warning(
        f"[BinanceAdapter] No correlation found for order {client_order_id}/{exchange_order_id}, skipping"
    )
    return
```

**Problem:** If `order_index` misses the mapping (restart, TTL, different entry path), the fill is dropped and `EVT:TRADE_EXECUTED` is never emitted.

**Planned change:**

- When `order_ref` is missing:
  - Emit a minimal `EVT:TRADE_EXECUTED` event with:
    - `symbol`,
    - `side`,
    - `qty`,
    - `price`,
    - `clientOrderId` / `exchangeOrderId`,
    - `why="ws_fill_unmatched_order_index"`.
  - Skip `order_index.mark_terminal`, but still propagate the fill to ExecPosFSM and PositionTracking.

**Patch sketch:**

- Add an alternative branch in `_handle_order_trade_update` for the `not order_ref` case that builds and emits `EVT:TRADE_EXECUTED` via `self.fsm_core.emit`.

### 3.2. Make Watchdog Polling a Reliable Fallback

**File:** `apps/reference/domains/execution_position/fsm.py`, `OrderTimeoutWatchdog` coupling.

**Current:**

- `OrderTimeoutWatchdog` has hooks to `adapter.get_order` + `emit_fn("EVT:TRADE_EXECUTED", ...)`.
- `ExecPosFSM` connects hooks in `__init__` when `adapter` is available.
- `watchdog.start()` / `ensure_started()` rely on having a running event loop.

**Planned improvements:**

- Ensure the watchdog is **always started** when ExecPosFSM is active and an asyncio loop is available.
- Optionally read `check_interval_ms` from `trading.execution.watchdog.check_interval_ms` (additive config) to tune REST latency without reducing `fill_ttl_ms`.

**Patch sketch:**

- Extend FSM manage config / `ExecutionManageConfig` to optionally carry `check_interval_ms`.
- Pass it to `OrderTimeoutWatchdog(ack_ttl_ms, fill_ttl_ms, check_interval_ms=...)`.
- Ensure `ensure_started()` is called from safe FSM event handlers (e.g., after first OPEN DECISION) so that polling begins as soon as the first live order is sent.

### 3.3. PositionTracking WAL Gate Soften (Testnet/Dev safety)

**File:** `apps/reference/domains/position_tracking/position_tracking.py`

**Current:**

- On `wal.append` failure (`None`), handler logs CRITICAL and returns early, skipping portfolio update.

**Planned change:**

- Introduce a mode (e.g., testnet / dev profile flag) in config to control WAL strictness.
- In testnet/dev mode:
  - Log error but **continue** processing TRADE/ACCOUNT events to keep portfolio in sync.
- In production mode:
  - Keep current behavior (strong DR guarantees) unless explicitly relaxed.

**Patch sketch:**

- Read a flag from config, e.g. `config.trading.dr.strict_wal` (default `True`).
- Wrap the `return` on WAL failure in a conditional:
  - if strict → `return`.
  - else → log and proceed.

### 3.3.1. Trade‑level Deduplication & Reconciliation Priority

**File:** `apps/reference/domains/position_tracking/position_tracking.py`

**Planned change (dedup):**

- Introduce a small in‑memory (and optionally WAL‑backed) **trade index** keyed by a stable id, e.g.:
  - `trade_uid = f"{exchange_trade_id}|{symbol}|{side}|{qty}|{price}"` (or a dedicated field if present),
  - or, for AccountObserver, use Binance `id` from `get_my_trades`.
- For each incoming `EVT:TRADE_EXECUTED`:
  - compute `trade_uid` and check a recent‑window cache (LRU / TTL‑based);
  - if already seen → log `why="trade_dedup_hit"` and skip processing;
  - if new → store `trade_uid` in cache and proceed with WAL + position update.
- Optionally, persist `trade_uid` in WAL metadata for replayed events, to keep behavior identical after restart.

**Planned change (reconciliation priority):**

- Define explicit rules inside `PositionTracking`:
  - **Rule 1:** `EVT:ACCOUNT_UPDATE_RECEIVED` (plus `/positionRisk` if used) is the **ground truth** snapshot.
  - **Rule 2:** `EVT:TRADE_EXECUTED` is applied incrementally **between** snapshots, but any snapshot can override local state.
  - **Rule 3:** on every snapshot, compute a diff vs current `_positions` and:
    - apply adds/updates/removals so that internal state matches snapshot;
    - emit a metric for drift if non‑empty diff.
- Expose a small helper like `reconcile_with_snapshot(snapshot_positions)` to keep this logic centralized.

### 3.4. Stronger Account Snapshot Integration

**Files:**

- `apps/reference/domains/account_balance/account_connector.py`
- `apps/reference/domains/execution_position/binance_execution_adapter.py`
- `apps/reference/domains/position_tracking/position_tracking.py`

**Planned alignment:**

- Verify that `EVT:ACCOUNT_UPDATE_RECEIVED` is consistently emitted when:
  - `/fapi/v2/positionRisk` is refreshed;
  - or when WS `ACCOUNT_UPDATE` is received.
- Ensure `PositionTracking.on_account_update` is always subscribed in the same FSMCore instance as `BinanceExecutionAdapter` / `account_balance`.
- Optionally add a **sanity metric**:
  - time since last `ACCOUNT_UPDATE_RECEIVED`;
  - if exceeds threshold, raise alert and optionally trigger a manual `/positionRisk` fetch.

### 3.4.1. Emergency Resync Path (No WAL Dependency)

**Files:**

- `apps/reference/domains/position_tracking/position_tracking.py`
- `apps/reference/domains/account_balance/account_connector.py`

**Planned change:**

- Add an **explicit resync entrypoint**, e.g. `PositionTracking.force_full_resync(reason: str)` that:
  - triggers a fresh fetch of `/fapi/v2/positionRisk` and balances via existing connectors;
  - reconstructs `_positions` and balance state purely from snapshot data;
  - emits `EVT:ACCOUNT_UPDATE_RECEIVED` and `EVT:PORTFOLIO_STATE_UPDATED` with `why="manual_resync"` or `why="auto_resync_drift"`.
- This path must:
  - not rely on WAL being healthy (it can still log, but must not abort if append fails);
  - be safe to call from a health monitor or admin API.

**Triggering conditions (examples):**

- Drift metric above a threshold (see §3.6).
- Time since last snapshot exceeds SLO (e.g., > 30–60s during active trading).
- Manual operator action via debug endpoint (e.g., `GET /debug/force_resync/{symbol}` or global).

No functional breaking changes here, mostly wiring validation.

### 3.5. TP/SL Ownership & Orphan Cleanup Hardening

**Files:**

- `apps/reference/domains/execution_position/fsm.py`
- `apps/reference/domains/execution_position/order_guardian.py`
- `apps/reference/domains/execution_position/manage_config.py`

**Planned improvements:**

- Standardize how TP/SL orders are:
  - recorded per position / parent order,
  - reconciled when `EVT:PORTFOLIO_STATE_UPDATED` shows position closure,
  - cleaned up on startup (using `OrderGuardian` startup reconcile).
- Explicitly document mode:
  - **single‑entry per symbol** vs **multi‑entry** and how that affects symbol‑wide cleanup.
- Ensure that after any position becomes flat (0 size):
  - OrphanMonitor runs `reconcile_symbol(symbol)`;
  - All reduceOnly / closePosition TP/SL without a live position are cancelled.

No radical changes, mostly better usage of existing `OrderGuardian.reconcile_symbol` and `_symbol_brackets` data.

### 3.6. Health Metrics & Drift Monitoring

**Files:**

- `apps/reference/domains/position_tracking/position_tracking.py`
- metrics/observability integration layer (wherever existing metrics are emitted).

**Planned metrics:**

- `position_sync.last_account_update_age_seconds` – gauge: `now - last_account_update_ts`.
- `position_sync.position_drift_detected_total` – counter: increments when snapshot reconciliation finds diff vs `_positions`.
- `position_sync.position_drift_current` – gauge: number of symbols currently in drift (optional labels: symbol, magnitude).
- `position_sync.fill_source_total{source=ws|rest_watchdog|account_observer|dr_replay}` – counters: how many fills came from each source.
- `position_sync.trade_dedup_hit_total` – counter: deduplicated trade events.

**Usage:**

- Alert if `last_account_update_age_seconds` exceeds threshold.
- Alert if `position_drift_detected_total` increases rapidly in a short window.
- Use `fill_source_total` to validate that WS is dominant in normal conditions and that REST/observer only pick up edge cases.

---

## 4. Definition of Done (DoD)

The work is considered **done** when all the following conditions are met:

1. **Fill visibility**
   - 100% of Binance fills (including fills occurring long after initial order placement) result in either:
     - at least one `EVT:TRADE_EXECUTED` delivered to `PositionTracking`, **or**
     - a `EVT:ACCOUNT_UPDATE_RECEIVED` snapshot that updates the position.
   - No testnet trade can remain on Binance without eventually being visible in `PositionTracking._positions`.

2. **Portfolio consistency**
   - After a restart and WAL replay, `PositionTracking.get_positions()` is consistent with a fresh `/positionRisk` call (within timing tolerance).
   - `EVT:PORTFOLIO_STATE_UPDATED.positions` matches Binance positions for all tracked symbols in test scenarios.

3. **TP/SL ownership and cleanup**
   - When a position is closed (by any path – TP, SL, manual CLOSE, external intervention):
     - All associated TP/SL reduceOnly / closePosition orders are either executed or cancelled within a bounded time window (e.g., 30–60 seconds).
   - Orphan TP/SL (no corresponding open position) are not present in `/fapi/v1/openOrders` after the orphan monitor interval.

4. **No regression in production safety**
   - WAL strictness in production remains as before (or explicitly governed by config).
   - No changes break existing JSON schemas or external integrations.

5. **Observability**
   - Metrics and logs exist to answer:
     - How many fills came from WS vs REST vs AccountObserver?
     - How often does AccountUpdate‑based reconciliation adjust our positions?
     - Are there any "late" reconciliations (position difference detected)?
    - How often deduplication drops duplicate trades?
    - How often an emergency resync is triggered and by which reason?

---

## 5. Test Plan

### 5.1. Unit / Component Tests

1. **AccountObserver → TRADE_EXECUTED**
   - Given a mocked Binance `get_my_trades` response with one fill:
     - Ensure `_process_trades` emits `EVT:TRADE_EXECUTED` with correct payload.
     - Optionally check that `EVT:FILL` is still emitted (if kept for compatibility).

2. **BinanceExecutionAdapter unmatched WS fill**
   - Simulate `_handle_order_trade_update` with:
     - valid WS payload;
     - no `order_ref` found in `order_index`.
   - Verify that:
     - Adapter emits `EVT:TRADE_EXECUTED` on `fsm_core` with `why="ws_fill_unmatched_order_index"`.

3. **OrderTimeoutWatchdog REST fallback**
   - Configure a test `get_order_fn` that returns `status="FILLED"` on second call.
   - Verify that `_poll_order_statuses`:
     - emits `EVT:TRADE_EXECUTED` via `emit_fn` exactly once;
     - removes the order from `acked_orders`.

4. **PositionTracking WAL soft‑fail (testnet mode)**
   - Mock `wal.append` to return `None`.
   - With `strict_wal=False` in config:
     - `on_trade_executed` still updates positions and emits `EVT:PORTFOLIO_STATE_UPDATED`.

5. **AccountUpdate reconciliation**
   - Feed `on_account_update` with a snapshot containing:
     - a new non‑zero position for symbol X;
     - zero position for symbol Y that was previously open.
   - Verify:
     - X is added/updated in `_positions`;
     - Y is removed from `_positions`.

### 5.2. Integration Tests (Testnet)

1. **Late fill after timeout**
   - Place an order on testnet with small size but artificially delay websocket (or disable WS):
     - Let watchdog mark it as timeout (NRR‑019).
     - Ensure Binance eventually fills the order.
   - Expected:
     - Either AccountObserver or REST polling produces `EVT:TRADE_EXECUTED`.
     - PositionTracking shows a non‑zero position.
     - Next `/positionRisk` snapshot matches internal position.

2. **Restart & DR replay**
   - Open a position and record fills in WAL.
   - Restart the app (or simulate by re‑instantiating FSM + PositionTracking and running DR loader).
   - Expected:
     - After replay, `PositionTracking.get_positions()` matches Binance `/positionRisk`.

3. **TP/SL orphan cleanup**
   - Open a position with TP/SL.
   - Force position closure outside the main FSM path (e.g., manual close in Binance UI / separate script).
   - Wait for account/update + orphan monitor.
   - Expected:
     - PositionTracking reports zero position.
     - `OrderGuardian` cancels orphan TP/SL.
     - `/openOrders` has no reduceOnly / closePosition orders for that symbol.

4. **Mixed source fills**
   - Run a session where some orders are filled quickly (WS), others slowly (REST/AccountObserver).
   - Expected:
     - For every executed order, the system either:
       - logs `EVT:TRADE_EXECUTED` (from some source), and
       - portfolio state is updated accordingly.

---

## 6. Rollout Strategy

1. **Phase 1 – Local + Testnet only**
   - Implement AccountObserver & BinanceExecutionAdapter changes.
   - Enable soft WAL mode in testnet.
   - Validate via unit and integration tests.

2. **Phase 2 – Shadow in live‑like env**
   - Run in `shadow_live` mode with no real capital risk.
   - Monitor discrepancies between PositionTracking and `/positionRisk`.

3. **Phase 3 – Hardened Production Profile**
   - Enable config‑guarded behavior in live.
   - Keep WAL strict in production unless explicitly disabled.
   - Monitor metrics & alerts for any new anomalies.

---

## 7. Next Steps

- [x] Implement and review patches for AccountObserver and BinanceExecutionAdapter.
  - ✅ `apps/reference/domains/account_observer/account_observer.py`: `_process_trades` now emits canonical `EVT:TRADE_EXECUTED` (with optional legacy `EVT:FILL` guard), propagates Binance trade IDs via `orderId`, and keeps `qty`/precision for downstream FSMs.
  - ✅ `apps/reference/domains/execution_position/binance_execution_adapter.py`: `_handle_order_trade_update` no longer drops fills without `order_index` correlation—`_build_trade_executed_payload()` constructs idempotent payloads and `_emit_trade_event()` forwards unmatched fills with `why="ws_fill_unmatched_order_index"`; `EVT:ORDER_STATE_CHANGED` still emitted for bookkeeping.
  - ✅ Downstream consumers updated to treat `quantity`/`qty` interchangeably (`fsm_manage.py`, `fsm_close.py`, `fsm.py`) so that new payloads remain backward compatible; duplicate legacy `EVT:FILL` events are deduped in `ExecPosFSM`.
  - ✅ Regression coverage: `tests/integration/test_order_lifecycle_correlation.py::test_account_observer_fill_correlation` and `tests/unit/test_websocket_payload_normalization.py::test_integration_handle_order_trade_update_includes_orderId_in_payload` validate both event sources.
- [x] Harden OrderTimeoutWatchdog fallback path (configurable polling cadence + guaranteed start-on-loop).
  - ✅ `apps/reference/domains/execution_position/manage_config.py`: `WatchdogConfig` now exposes additive `check_interval_ms`, resolved from `trading.execution.manage.watchdog.check_interval_ms` (default 1000 ms) without breaking existing configs.
  - ✅ `apps/reference/domains/execution_position/fsm.py`: ExecPosFSM logs/passes the interval into `OrderTimeoutWatchdog`, auto-starts the watchdog once an asyncio loop is bound (either immediately or via `call_soon_threadsafe`), and forwards explicit loop handles during order place/ack/fill callbacks.
  - ✅ `apps/reference/domains/execution_position/watchdog.py`: start/ensure logic refactored into `_start_task` with loop-aware scheduling so polling can be armed safely from other threads while keeping idempotency guarantees.
- [x] Introduce config flag for PositionTracking WAL strictness.
  - ✅ `apps/reference/domains/position_tracking/position_tracking.py`: added `strict_wal` resolver (`trading.dr.strict_wal` with safe fallbacks), centralized WAL append helper, and downgraded failures to error-only when the flag is false so testnet/dev continue processing even if WAL is flaky.
  - ✅ Guarded logging ensures production (default strict) still halts on WAL issues; soft mode emits warnings but keeps consuming trade/account events to avoid portfolio drift.
  - ✅ Regression coverage: `tests/domains/test_position_tracking_logic.py::test_trade_processing_continues_when_wal_soft_fail` (and companions) exercise both strict and soft paths for trade/account updates.
- [x] Deliver §3.3.1 trade deduplication + snapshot reconciliation priority.
  - ✅ `apps/reference/domains/position_tracking/position_tracking.py`: introduced stable `trade_uid` extraction, LRU/TTL dedup cache with configurable window, WAL metadata enrichment (`dedup_uid`), and `_trade_is_duplicate` short‑circuit metrics so repeated fills are skipped deterministically.
  - ✅ Added `_reconcile_positions_from_snapshot()` helper and rewired `on_account_update` to treat Binance snapshots as ground truth (diff detection, drift metric, manual-close alerts, AlertManager hooks) while keeping WAL gates + per-side margin math intact.
  - ✅ Regression coverage: `tests/domains/test_position_tracking_logic.py` now covers dedup hits, snapshot overrides, manual closure detection, and WAL strict/soft combos; suite `tests/domains/test_position_tracking_logic.py` (27 tests) green via `pytest`.
- [ ] Add/extend tests as outlined.

## 8. Implementation Status Log

| Date (UTC) | Scope | Details |
| --- | --- | --- |
| 2025-11-14 | §3.1 Unify Fills | AccountObserver now emits `EVT:TRADE_EXECUTED` (+ optional legacy `EVT:FILL`); BinanceExecutionAdapter now emits canonical trade events even when `order_index` misses; FSM Manage/Close flows consume the enriched payload (qty/quantity) and skip duplicate legacy fills; targeted pytest suite green. |
| 2025-11-15 | §3.2 Watchdog fallback | Manage resolver surfaces `watchdog.check_interval_ms`; ExecPosFSM threads the interval into `OrderTimeoutWatchdog`, auto-schedules watchdog startup via shared asyncio loop (including cross-thread `call_soon_threadsafe`), and passes explicit loop handles when ensuring the watchdog during order place/ack/fill flows; watchdog now shares `_start_task` to safely start from deferred contexts. |
| 2025-11-15 | §3.3 WAL guard | PositionTracking reads `trading.dr.strict_wal`, defaults to production strict mode, and centralizes WAL writes so soft mode logs errors but keeps processing trades/account snapshots; dedicated unit tests assert both strict (halt) and non-strict (continue) behavior for TRADE and ACCOUNT events. |
| 2025-11-16 | §3.3.1 Dedup + Reconcile | PositionTracking now computes stable `trade_uid` values, appends them to WAL metadata, and gates trade processing with a configurable LRU dedup cache; `_reconcile_positions_from_snapshot` applies Binance snapshots atomically, increments drift counters, and routes manual-close alerts via AlertManager. Unit suite (`tests/domains/test_position_tracking_logic.py`) expanded to cover dedup hits, snapshot overrides, and manual closures—full pytest run green. |
- [ ] Run targeted testnet scenarios (late fills, restarts, manual closes).
- [ ] Update domain docs (`execution_position`, `position_tracking`, `account_balance`) to reference this plan as the canonical position‑sync spec.
