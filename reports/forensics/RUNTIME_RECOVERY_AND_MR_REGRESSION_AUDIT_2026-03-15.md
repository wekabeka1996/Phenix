# Runtime Recovery And MR Regression Audit (2026-03-15)

## 1. Executive Verdict

### Hard verdict
- `md_amr` stayed cold after restart because startup basis import was still a single-shot path. When the fetch failed once, `execute_startup_basis_hydration()` imported `0` bars, skipped seeding, and both `XRPUSDT` and `BNBUSDT` continued counting only live 15m bars.
- `aurora` had the same failure class. `BTCUSDT`, `ETHUSDT`, and `SOLUSDT` advanced from `139/301` to `154/301` one live 5m bar at a time, which proves startup replay never seeded their handler counters.
- Previous tests lied because they proved helper methods and direct `seed_startup_bars()` calls, not the real `ConfigLoader -> StrategyRuntime -> hydration plan -> PillarBackfillService -> startup hydrator -> handler counter` contract.
- `mean_reversion` regression is not explained by "market drift" alone. The strongest proven regression is DOGE config drift on top of the earlier `180s -> 300s` structural change:
  - `bb_window 20 -> 40`
  - `bb_num_std 2.1 -> 2.5`
  - `cooldown_sec 210 -> 660`
  - added `flat_low_short_min_bb_width`
  - added `squeeze_expansion_veto`
  - added `momentum_separation_veto`
- Secondary MR blocker is execution drift: the only observed live DOGE MR entry on 2026-03-15 at `13:14:59` produced an `ORDER_INTENT`, then failed with Binance `[-1007] Timeout waiting for response from backend server.`

### Operator answers
1. `md_amr` was still cold because handler counters were never seeded at startup. Live logs show pure live accumulation from `8/96` to `51/96`.
2. The broken contract was the startup import path: a transient fetch failure returned an unsuccessful `BackfillResult`, `hydrate_basis_bars()` imported nothing, and `STARTUP_BASIS_SEED_SKIPPED reason=no_seed_source` followed.
3. Tests missed it because they were synthetic or helper-level; they never exercised the real startup composition path with current config and real plugin wiring.
4. `mean_reversion` became materially worse because DOGE was hardened into a much slower and narrower strategy after the last healthier 300s profile, while the earlier 180s edge had already been abandoned.
5. The most likely root regression class is `MULTI_FACTOR`, led by `CONFIG_DRIFT`, then `TIMEFRAME_DRIFT`, then `EXECUTION_BEHAVIOR_REGRESSION`.
6. First fix priority is startup basis recovery, because until `aurora` and `md_amr` seed correctly the system remains non-functional after restart. Second priority is MR DOGE rollback to the last healthier 300s profile. Third priority is exchange timeout hardening.

## 2. Active Runtime Matrix

| strategy | symbol | tf_sec | bars_required | bars_seen_observed | ready | primary blocker | secondary blocker |
|---|---:|---:|---:|---:|---|---|---|
| aurora | BTCUSDT | 300 | 301 | 153 on 2026-03-15 22:00:05 | no | startup basis import failed, counter never seeded | quadratic path never reached |
| aurora | ETHUSDT | 300 | 301 | 153 on 2026-03-15 22:00:04 | no | startup basis import failed, counter never seeded | quadratic path never reached |
| aurora | SOLUSDT | 300 | 301 | 153 on 2026-03-15 22:00:03 | no | startup basis import failed, counter never seeded | quadratic path never reached |
| md_amr | XRPUSDT | 900 | 96 | 51 on 2026-03-15 22:00:06 | no | startup basis import failed, counter never seeded | local REST hydration still separate debt |
| md_amr | BNBUSDT | 900 | 96 | 51 on 2026-03-15 22:00:07 | no | startup basis import failed, counter never seeded | local REST hydration still separate debt |
| mean_reversion | DOGEUSDT | 300 | 25 | 72 bars completed by 2026-03-15 15:15:03 | yes | DOGE config drift shrank edge | live open order timed out (`-1007`) |

## 3. Bootstrap Failure Chain

1. Restart occurred around `2026-03-15 09:09:15`:
   - `logs/domain_mean_reversion.log` recorded `MR_INIT` and `MR_REGISTER`.
2. `main.py` starts strategy handlers before building the restore report and hydration plan.
3. `build_startup_hydration_plan()` correctly requests:
   - `aurora`: `301` bars at `300s`
   - `md_amr`: `96` bars at `900s`
4. Before this package, `PillarBackfillService.fetch_candles()` was single-shot:
   - one adapter failure
   - one empty response
   - or one sub-threshold result
   immediately ended the startup import attempt.
5. `execute_startup_basis_hydration()` then received an unsuccessful fetch result:
   - `hydrate_basis_bars()` imported `0`
   - `seeded_bars` stayed `0`
   - seeding was skipped with `reason=no_seed_source`
6. Handlers then counted only live bars:
   - `md_amr` advanced `8 -> 51` exactly one bar every 15m
   - `aurora` advanced `139 -> 154` exactly one bar every 5m
7. Result:
   - `md_amr_handler:cold_start:51/96`
   - `aurora_handler BARS_REQUIRED gate: 153/301`
   - no real post-restart readiness

### Exact code path audited
- `apps/reference/main.py`
- `apps/reference/bootstrap/startup_hydration_planner.py`
- `apps/reference/bootstrap/startup_basis_hydrator.py`
- `apps/reference/domains/feature_engineering/pillar_backfill.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/domains/decision_making/md_amr_handler.py`

### Non-root causes ruled out
- Handler registration timing is not the main failure. `StrategyRuntime(...).start()` happens before startup hydration in `main.py`.
- TF contract is internally consistent for `aurora` and `md_amr`:
  - `aurora`: `300s`, `301 bars`
  - `md_amr`: `900s`, `96 bars`

## 4. Test Realism Audit

| test file | classification | why it gave false confidence |
|---|---|---|
| `tests/test_bootstrap_readiness_hardening.py` | `SYNTHETIC`, `MOCK_ONLY`, `DOES_NOT_TOUCH_REAL_PATH` | Builds handlers with `object.__new__`, calls `_emit_bootstrap_lifecycle()` and `seed_startup_bars()` directly, never exercises startup import or plugin/runtime wiring. |
| `tests/bootstrap/test_startup_basis_hydrator.py` | `HELPER_LEVEL`, partially realistic | Covers the hydrator helper itself, but with perfect fake adapters and hand-built plans. It did not prove resilience to real startup fetch failure. |
| `tests/domains/decision_making/test_aurora_runtime_readiness_contract.py` | `PAYLOAD_CONTRACT_ONLY` | Validates readiness payload shape, not startup hydration truth. |

### New failing-first proofs added
- `tests/unit/feature_engineering/test_pillar_backfill_startup.py`
  - reproduced the real failure class: one transient timeout -> no retry -> cold startup
- `tests/bootstrap/test_startup_basis_real_path.py`
  - exercised the real path with:
    - `ConfigLoader`
    - current live config
    - `StrategyRuntime`
    - real plugins
    - real startup hydration plan
    - real `execute_startup_basis_hydration()`

## 5. Bootstrap Root Cause(s)

### Ranked causes
1. `CRITICAL`: single-shot startup fetch in `PillarBackfillService.fetch_candles()`
   - proof: failing-first reproducer
   - live symptom match: zero startup seed, pure live accumulation
2. `HIGH`: startup readiness summary was not trustworthy enough
   - `seed_source` was hardcoded in lifecycle emission instead of reflecting actual source
   - executor result had no per-strategy readiness summary
3. `HIGH`: prior test suite never covered the real composition root
   - all green tests still allowed the exact live failure class

### Fix implemented
- `apps/reference/domains/feature_engineering/pillar_backfill.py`
  - added `3` startup retry attempts for transient failures / empty responses / insufficient fetches
- `apps/reference/bootstrap/startup_basis_hydrator.py`
  - added truthful `readiness` summary
  - fixed lifecycle `seed_source`

## 6. Mean Reversion Regression Analysis

### Historical baseline
- `logs/mean_reversion/bars_180s.tsv` shows the earlier healthier regime on `2026-03-03` through `2026-03-07`.
- DOGE emitted repeated actionable signals on `180s` bars:
  - `2026-03-03 07:17:59 SHORT`
  - `2026-03-03 07:47:59 LONG`
  - `2026-03-03 08:14:59 LONG`
  - `2026-03-03 21:50:59 SHORT`
  - many more throughout the file

### Current state
- Current runtime is `300s`:
  - `logs/domain_mean_reversion.log` shows `timeframe_sec: 300`
- On `2026-03-15`, only one live DOGE MR signal was observed:
  - `2026-03-15 13:14:59 LONG DOGEUSDT`
  - then `13:19:59 cooldown`
  - then `13:24:59` onward mostly `UNCERTAIN` / blocked
- The resulting order never opened:
  - `ORDER_INTENT` at `1773580503046`
  - `ORDER_REJECTED` at `1773580505709`
  - reason: Binance backend timeout `[-1007]`

### What changed

#### Structural drift
- Earlier edge lived on `180s` artifacts (`bars_180s.tsv`)
- Current runtime uses `300s` (`config/aurora/strategies/mean_reversion.yaml`)

#### Last healthier 300s profile
Commit `6635ad3` already had `300s`, but DOGE was materially looser:
- `bb_window: 20`
- `bb_num_std: 2.1`
- `cooldown_sec: 210`
- no `flat_low_short_min_bb_width`
- no `squeeze_expansion_veto`
- no `momentum_separation_veto`

#### Current regressed profile before rollback
- `bb_window: 40`
- `bb_num_std: 2.5`
- `cooldown_sec: 660`
- added `flat_low_short_min_bb_width`
- added `squeeze_expansion_veto`
- added `momentum_separation_veto`

### Trade-level evidence
- `logs/mean_reversion/bars_300s.jsonl`
  - `2026-03-15 13:14:59`: DOGE LONG in `FLAT_LOW`
  - `2026-03-15 13:19:59`: blocked by cooldown
  - `2026-03-15 13:24:59` to `13:39:59`: neutral because regime degraded to `UNCERTAIN`
- `logs/order_log_v1.jsonl`
  - the same DOGE trade was rejected by the execution layer, not closed in profit/loss

### Regression class
- Primary: `CONFIG_DRIFT`
- Secondary: `TIMEFRAME_DRIFT`
- Tertiary: `EXECUTION_BEHAVIOR_REGRESSION`
- Overall classification: `MULTI_FACTOR`

### Safe fix applied in this package
- Rolled DOGE back to the last healthier `300s` profile:
  - `bb_window 40 -> 20`
  - `bb_num_std 2.5 -> 2.1`
  - removed `flat_low_short_min_bb_width`
  - removed `squeeze_expansion_veto`
  - removed `momentum_separation_veto`
  - `cooldown_sec 660 -> 210`

### What was not changed in this package
- Full `300s -> 180s` rollback
  - reason: larger pipeline change, higher live risk
- Exchange order timeout handling
  - separate execution-layer issue

## 7. Code/Config Diffs That Matter

- `apps/reference/domains/feature_engineering/pillar_backfill.py`
  - startup backfill now retries instead of failing cold after one transport error
- `apps/reference/bootstrap/startup_basis_hydrator.py`
  - per-strategy readiness summary is explicit and truthful
- `config/aurora/strategies/mean_reversion.yaml`
  - DOGE reverted to the last healthier `300s` profile

## 8. Fixes Implemented

1. Added retry resilience to startup basis import.
2. Added truthful readiness summary and correct seed-source reporting.
3. Added real-path startup reproducer against the current live config.
4. Added transient backfill reproducer.
5. Rolled back DOGE MR config drift to the last healthier `300s` profile.

## 9. Tests Added/Updated

### Realistic end-to-end coverage
- `tests/bootstrap/test_startup_basis_real_path.py`
  - current config
  - real plugins
  - real hydration plan
  - transient fetch failure recovery

### Helper / focused coverage
- `tests/unit/feature_engineering/test_pillar_backfill_startup.py`
  - transient fetch retry proof
  - cache expectations updated for retry cycle
- `tests/config/test_mean_reversion_doge_regression_config.py`
  - DOGE rollback guard

### Targeted verification run
- `pytest tests/config/test_mean_reversion_doge_regression_config.py tests/bootstrap/test_startup_basis_real_path.py tests/bootstrap/test_startup_basis_hydrator.py tests/bootstrap/test_startup_hydration_planner.py tests/unit/feature_engineering/test_pillar_backfill_startup.py -q`
- Result: `37 passed`

## 10. Residual Debt

- Live deployment still required to confirm the new startup retries actually seed counters in production.
- `md_amr` still logs a separate warning about unknown trading mode during local REST hydration; this did not explain `51/96`, but remains debt.
- Execution layer still needs a separate fix for Binance `-1007` open-order timeouts.
- The earlier `180s -> 300s` MR structural drift still needs a dedicated replay/backtest comparison before any full timeframe rollback.

## 11. Next-Step Priority

1. Redeploy and confirm new startup logs show successful basis import and seeding for all `aurora` and `md_amr` symbols.
2. Audit execution adapter behavior around Binance `-1007` and add safe idempotent reconciliation for unknown order status.
3. Run a dedicated DOGE MR replay comparing:
   - historical `180s`
   - current `300s`
   - rolled-back DOGE `300s` profile
4. Decide whether `180s` should be restored as a first-class live bar pipeline again.
