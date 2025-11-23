# WATCHDOG-DEDUP-S1 - AggOcoWatchdog Deduplication

## 1. Current Watchdog Behavior
- File: `apps/reference/domains/execution_position/shadow_execpos/watchdog.py` (V2, detect-only).
- Invariants surfaced: missing SL for open position, orphan SL when flat, too many SL for open position; `MULTIPLE_META_SETS` constant exists but is not enforced.
- Flow: normalize mixed adapter payloads into `BracketPositionView`/`BracketOrderView`, evaluate bracket state, convert WARN/ALERT plans into `WatchdogRecommendation`.
- Auto-heal: none inside watchdog; no adapter/guardian mutations. OrderGuardian auto-heal already disabled via `v2_compat_mode` and tests.

## 2. Overlap with BracketService
- BracketService.evaluate covers: missing SL (PLACE_SL), orphan SL/TP when flat (CANCEL), too many SL (CANCEL extras), stale levels, duplicate/meta issues, with canonical `reason_code`/`why`.
- Legacy watchdog logic re-counted SL orders and produced bespoke reason strings that overlap with BracketService output.
- TP/SL geometry already handled in BracketService/tp_sl_math; watchdog should not compute prices or invariants itself.

## 3. Design: Thin Watchdog over BracketService
- Goal: watchdog acts as a consumer of BracketService, no duplicate invariant math.
- Behavior: periodically call `BracketService.evaluate_all(...)` with normalized positions/orders (and optional guardian meta); aggregate `BracketPlan` severities → WARN/ALERT => log/metrics; INFO => drop.
- Legacy to drop: manual SL counting/reason strings; any adapter/guardian mutation hooks or auto-heal.
- What remains: scheduling cadence, severity aggregation (INFO/WARN/ALERT), metrics/logging (`watchdog_violations`, alert logs).
- Contract (V2): no calls into OrderGuardian mutation methods; no TP/SL math here; all invariants/reasons taken from `BracketService`/`BracketPlan`; detect-only.

## 4. Implementation Summary (Phase 2)
- `watchdog.py` now delegates to `BracketService.evaluate_all` and translates `BracketPlan` actions into recommendations; no local invariant logic.
- Position/order normalization retained for heterogeneous payloads; legacy constants kept only for compatibility, not used in logic.
- Logging tightened: BracketService failures are error-logged; each evaluated plan is logged at debug with severity/why/actions; still detect-only (no adapter/guardian calls).
- Tests updated to the thin-BracketService contract: `tests/domains/execution_position/shadow_execpos/test_watchdog_v2.py` mocks `evaluate_all`; `.../test_watchdog_ported_logic.py` asserts WARN/ALERT mapping for missing/orphan/too-many SL via BracketService-driven plans.
