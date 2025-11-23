# ExecPos Event Flow (Runtime V2)

> Canonical behavior is defined in `docs/EXEC_POS_V2_RUNTIME_SPEC.md`.  
> This file gives a concise flow view for ExecPosRuntimeV2 (legacy dual-runtime language is historical).

1) **INTENT → ENTRY**
- Legacy `CMD:OPEN` → `RuntimeEvent(kind="ENTRY_INTENT")` via `MessageToRuntimeEventAdapter`.
- Gatekeeper validates (qty/notional/steps/cooldown) → allow/deny.
- On allow: `ExecutionService.place_order` → open_orders cache updated; structured log + metrics.
- No TP/SL/bracket placement occurs in V2.

2) **INTENT → CANCEL**
- `CMD:CANCEL`/`CMD:CANCEL_ORDER` → `CANCEL_INTENT`.
- `ExecutionService.cancel_order`; success prunes `_open_orders_by_symbol`; metrics/log only.

3) **INTENT → CLOSE**
- `CMD:CLOSE`/`CMD:FORCE_CLOSE` → `CLOSE_INTENT`.
- `ExecutionService.close_position`; on success position state is zeroed. No bracket cleanup (close FSM not ported).

4) **TRADE_EXECUTED**
- Idempotency (cumulative qty) → enrichment (price) → state update (qty/direction, entry_price on first open).
- WAL writes: EXEC_TRADE then EXEC_POSITION (if state changed).
- ExposureBridge emits `EVT:EXEC_POS_EXPOSURE_UPDATED`.
- Watchdog analyzes for SL/orphan violations; recommends only (no auto-heal).

5) **SNAPSHOTS**
- `POSITION_SNAPSHOT`: rebuilds `_positions_by_symbol` then watchdog.
- `ORDERS_SNAPSHOT`: rebuilds `_open_orders_by_symbol` then watchdog.

6) **Aggregated OCO / Trailing**
- Aggregated OCO computation, trailing stops, and close FSM are **not implemented** in Runtime V2. Watchdog is detect-only.
