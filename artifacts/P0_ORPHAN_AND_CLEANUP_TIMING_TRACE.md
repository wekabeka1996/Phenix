# P0 Orphan And Cleanup Timing Trace

## Scope

This trace covers:
- orphan_monitor cadence fields
- guardian tidy-entry timing
- telemetry stale-record cleanup timing

## Orphan monitor loop

1. Config block:
   - config/aurora/trading.yaml:103-109 defines orphan_monitor enabled/run_on_startup/periodic_interval_sec/min_order_age_sec/batch_cancel_limit/rate_limit_per_min.
2. Typed model:
   - apps/reference/config_models.py:1498-1514 defines OrphanMonitorConfig with periodic_interval_sec, min_order_age_sec, batch_cancel_limit, and rate_limit_per_min.
3. Storage in ExecPosFSM:
   - apps/reference/domains/execution_position/fsm.py:411-417 copies the values into self._orphan_cfg.
4. Proven live cadence:
   - apps/reference/domains/execution_position/lifecycle.py:106-108 sleeps by periodic_interval_sec and then calls cleanup_orphans().
   - apps/reference/domains/execution_position/lifecycle.py:165 also calls cleanup_orphans() on startup.
5. Unproven fields:
   - No audited forwarding from min_order_age_sec, batch_cancel_limit, or rate_limit_per_min into cleanup_orphans() was found.
   - cleanup_orphans() itself owns batch_limit=50 at apps/reference/domains/execution_position/order_guardian.py:887-891.

Verdict:
- periodic_interval_sec is live.
- min_order_age_sec, batch_cancel_limit, and rate_limit_per_min are only partially proven.

## Guardian tidy-entry timing

1. Config owner:
   - config/aurora/domains.yaml:585-596 defines guardian.cleanup_ttl_ms and guardian.symbol_cooldown_ms.
2. Typed model:
   - apps/reference/config_models.py:3894-3916 defines GuardianConfig.
3. Consumer:
   - apps/reference/domains/execution_position/event_handlers.py:752-767 reads cleanup_ttl_ms and symbol_cooldown_ms in entry_tidy_gate_allow().

Verdict:
- These fields are live entry-reopen suppression controls and should not be mixed with orphan-loop cleanup rewiring.

## Telemetry stale-record cleanup

1. Default-only owner:
   - apps/reference/telemetry/trade_lifecycle_logger.py:122-130 defines orphan_ttl_sec=3600 and auto_sweep_interval_sec=60.
2. Singleton construction:
   - apps/reference/telemetry/trade_lifecycle_logger.py:393 instantiates TradeLifecycleLogger() without YAML injection.
3. Consumers:
   - apps/reference/telemetry/trade_lifecycle_logger.py:193 advances the next sweep by auto_sweep_interval_sec.
   - apps/reference/telemetry/trade_lifecycle_logger.py:206-220 expires stale open records using orphan_ttl_sec.

Verdict:
- Telemetry cleanup timings are live but default-only and distinct from the core order orphan cleanup loop.

## Safe boundary

1. If the next slice is about execution timeout truth, only document the partially proven orphan_monitor fields as unproven.
2. Do not change orphan cleanup semantics, guardian tidy-entry timing, and telemetry stale-record cleanup in one implementation batch.
