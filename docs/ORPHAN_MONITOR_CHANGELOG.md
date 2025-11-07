# Orphaned Bracket Monitor: Configurable Enhancements

Scope: apps/reference/domains/execution_position/fsm.py (ExecPosFSM)

This change adds a configurable, low-risk enhancement to the orphaned bracket monitor while preserving existing behavior and tests.

## What changed

- Added a configurable orphan monitor with:
  - periodic interval (seconds)
  - run on startup (initial sync)
  - minimum order age filter (seconds)
  - batch cancel limit (per run)
  - simple per-minute rate limiting (shared across symbols)
  - basic metrics surfaced via `ExecPosFSM.get_metrics()` under `orphan_monitor`
- Periodic loop and startup sync are only scheduled when `enabled=true` and FSM is not in shadow mode.
- Explicit calls to `cleanup_orphaned_bracket_orders()` keep working regardless of `enabled` (useful for tests and one-off remediation).

## Config schema (additive-only)

Path: `trading.execution.manage.orphan_monitor`

```
trading:
  execution:
    manage:
      orphan_monitor:
        enabled: true                 # default: true
        run_on_startup: true          # default: true
        periodic_interval_sec: 300    # default: 300s
        min_order_age_sec: 0          # default: 0 (no age filter)
        batch_cancel_limit: 50        # default: 50 cancels per run
        rate_limit_per_min: 120       # default: 120 cancels/minute
```

All fields are optional; defaults are applied if omitted.

## Behavior details

- Startup:
  - If not in shadow mode and `enabled && run_on_startup`, schedules `sync_open_orders_and_positions()` once.
  - If `enabled`, also schedules the periodic cleanup loop with the configured interval.

- Cleanup (`cleanup_orphaned_bracket_orders`):
  - Detects symbols with no open position and cancels reduce-only/closePosition orders of types STOP_MARKET, TAKE_PROFIT_MARKET, LIMIT.
  - Optional filters:
    - `min_order_age_sec`: Skip orders newer than this age if an order timestamp is available (best effort, uses known Binance time fields when present).
    - `batch_cancel_limit`: Stop after N successful cancels in a single run.
    - `rate_limit_per_min`: Per-minute cap across all symbols; excess orders are skipped for the minute window.

- Metrics (`get_metrics()`):
  - `orphan_monitor`: `{ loops, cancels, skipped_age, skipped_rate_limit, errors, cfg }`
  - Keeps counters in-memory; safe to reset on process restart.

## Safety & compatibility

- All changes are additive; default behavior equals the previous implementation (5-minute loop, no age filter/limits) except that interval and scheduling are now governed by config (defaults preserve prior behavior).
- Tests using `shadow_mode=True` are unaffected by background scheduling; explicit calls remain the same.
- If time fields are missing in exchange orders, the age filter does not skip such orders.

## Rollout

- Shadow → Canary (10–20%) → Full cutover.
- Monitor `orphan_monitor` metrics and adapter logs for any regressions.

## Files changed

- apps/reference/domains/execution_position/fsm.py
  - Added config parsing and loop scheduling logic in `__init__`
  - Added metrics exposure in `get_metrics`
  - Extended `cleanup_orphaned_bracket_orders` with min-age, batch limit, rate limiting
  - Parameterized `_cleanup_loop` interval and increment loop metric

## Rationale

- Prevent exchange-side throttling and accidental mass-cancel floods.
- Avoid cancelling fresh brackets that may be legitimate (age filter).
- Provide observability to tune parameters in production.

