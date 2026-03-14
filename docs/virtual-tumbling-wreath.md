# STARTUP-BASIS-HYDRATION — Cold-Start Gate Fix
**Branch:** Phenix_v2 | **Date:** 2026-03-13 | **Status:** PLAN — AWAITING APPROVAL

---

## Context

**Problem:** After restart, Aurora and md_amr refuse to open orders for up to 25 hours.

**Root cause chain:**
1. `atr_sma_length: 288` in `config/aurora/regime.yaml:42` (intentionally changed from 100
   during quadratic refactoring — comment preserved as `# LIVE (was): atr_sma_length: 100`)
2. `strategy_compatibility_matrix.py:91`: `basis_required_bars = max(sma_long=192, atr_period + atr_sma_length - 1 = 301) = 301`
3. `aurora_decision.py:195`: gate blocks all signals until `_bars_seen_since_restart[symbol] >= 301`
4. `md_amr_handler.py:1047`: same gate, `basis_required_bars = 96` (15m × 96 = 24h)
5. Counter is **only incremented on `CMD:PROCESS_STRATEGY`** (`aurora_handler.py:599`, `md_amr_handler.py:949`)
6. FE only emits `CMD:PROCESS_STRATEGY` when `warmup.full_ready == True` (`feature_engineering.py:1694`)
7. Historical fetch already exists (`PillarBackfillService`) but only seeds regime/pillar state — never reaches `_bars_seen_since_restart`

**Solution:** Startup basis executor that:
1. Fetches historical closed bars from Binance (using existing `PillarBackfillService`)
2. Injects them into `BarAggregator` with `WARMUP_IMPORT` source mode → FE processes → fills feature buffers
3. Directly seeds `_bars_seen_since_restart` in each handler via `seed_startup_bars()` (bypasses CMD path, which is blocked by FE warmup gate during import)

**Expected outcome:** On cold start at 10:00, system fetches 301 closed 5m bars + 96 closed 15m bars, seeds both counters, and trading is unblocked after the warmup gate releases — no more 25-hour wait.

---

## Critical Constraints

- `atr_sma_length: 288` is intentional — do NOT lower it
- FE will NOT emit CMD for WARMUP_IMPORT bars (warmup.full_ready blocks it) — this is expected; `seed_startup_bars()` is the correct solution, not a cmd-path workaround
- Executor must run **after all services are started** (`feature_engineering.start()` + `decision_making.start()`) but **inside the startup warmup gate** (before `release_startup_warmup_gate()`)
- `bar_aggregator` may be `None` — always guard
- Aurora handler is wrapped: `started_strategy_handlers["aurora"]` → `_AuroraHandlerWrapper` → `.handler` → `AuroraHandler`
- md_amr handler is direct: `started_strategy_handlers["md_amr"]` → `MDAMRHandler`

---

## Implementation — 5 Files, 5 Steps

### Step 1 — `apps/reference/domains/market_data/bar_aggregator.py`

**Add `source_mode` parameter to `_emit_bar_closed()`** (currently hardcodes `LIVE`):

```python
def _emit_bar_closed(
    self, bar: Bar, event_ts_ms: int,
    source_mode: RuntimeBarSourceMode = RuntimeBarSourceMode.LIVE,
) -> None:
```

Replace the hardcoded `source_mode=RuntimeBarSourceMode.LIVE` on line 269 with the parameter.

**Add new public method `inject_historical_bar(bar: Bar) -> None`:**

```python
def inject_historical_bar(self, bar: Bar) -> None:
    """Inject a pre-built completed bar for startup warmup (WARMUP_IMPORT mode).
    Stores bar, updates _last_ts boundary, emits EVT:BAR_CLOSED with WARMUP_IMPORT.
    Does NOT go through tick-based OHLCV construction.
    """
    key = (bar.symbol, bar.timeframe_sec)
    with self._locks[key]:
        completed_list = self._completed_bars[key]
        completed_list.append(bar)
        if len(completed_list) > self.max_bars_per_key:
            completed_list.pop(0)
        # Advance _last_ts so subsequent live ticks are not dropped as OOO
        self._last_ts[key] = max(self._last_ts.get(key, 0), bar.end_ts_ms)
        self._bars_completed += 1
    # Emit outside lock (emit_fn may trigger downstream synchronous handlers)
    self._emit_bar_closed(bar, bar.end_ts_ms, source_mode=RuntimeBarSourceMode.WARMUP_IMPORT)
```

**Import addition** (already imported via existing usage, but confirm):
`from apps.reference.contracts.runtime_bar_identity import RuntimeBarSourceMode` (already present).

---

### Step 2 — `apps/reference/bootstrap/startup_basis_hydrator.py` (NEW FILE)

```python
"""Startup basis bars hydrator — seeds FE feature buffers from Binance historical data."""
from __future__ import annotations
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.reference.domains.market_data.bar_aggregator import BarAggregator

LOG = logging.getLogger(__name__)


def hydrate_basis_bars(
    aggregator: "BarAggregator",
    symbol: str,
    tf_sec: int,
    n_bars: int,
    fetch_result: Any,
) -> int:
    """Inject historical closed bars from fetch_result into BarAggregator.

    Args:
        aggregator: BarAggregator instance (may be None — returns 0)
        symbol: Trading symbol e.g. "BTCUSDT"
        tf_sec: Timeframe in seconds (e.g. 300 for 5m, 900 for 15m)
        n_bars: Max bars to inject (takes last n_bars from result)
        fetch_result: BackfillResult from PillarBackfillService.fetch_candles()

    Returns:
        Number of bars successfully injected.
    """
    from apps.reference.domains.feature_engineering.bar_resampler import Bar

    if aggregator is None:
        LOG.warning("hydrate_basis_bars: bar_aggregator is None, skipping sym=%s tf=%d", symbol, tf_sec)
        return 0
    if fetch_result is None or not fetch_result.success:
        LOG.warning(
            "hydrate_basis_bars: fetch_result not successful sym=%s tf=%d error=%s",
            symbol, tf_sec, getattr(fetch_result, "error", "no_result"),
        )
        return 0

    candles = fetch_result.candles or []
    candles_to_import = candles[-n_bars:]  # take the most recent n_bars
    tf_ms = tf_sec * 1000
    count = 0

    for candle in candles_to_import:
        try:
            start_ts_ms = int(candle.open_time_ms)
            end_ts_ms = start_ts_ms + tf_ms - 1  # close_boundary - 1
            bar = Bar(
                symbol=symbol,
                timeframe_sec=tf_sec,
                open=Decimal(str(candle.open)),
                high=Decimal(str(candle.high)),
                low=Decimal(str(candle.low)),
                close=Decimal(str(candle.close)),
                volume=Decimal(str(candle.volume)),
                trade_count=1,  # klines API does not provide per-bar trade count
                start_ts_ms=start_ts_ms,
                end_ts_ms=end_ts_ms,
            )
            aggregator.inject_historical_bar(bar)
            count += 1
        except Exception as exc:
            LOG.warning("hydrate_basis_bars: failed to inject bar sym=%s ts=%s err=%s",
                        symbol, getattr(candle, "open_time_ms", "?"), exc)

    LOG.info(
        "hydrate_basis_bars: injected %d/%d bars sym=%s tf=%ds",
        count, len(candles_to_import), symbol, tf_sec,
    )
    return count
```

---

### Step 3 — `apps/reference/domains/decision_making/aurora_handler.py`

Add `seed_startup_bars()` method to `AuroraHandler` class (after `_bars_seen_since_restart` declaration, around line 225):

```python
def seed_startup_bars(self, symbol: str, count: int) -> None:
    """Seed _bars_seen_since_restart after startup basis import.

    Called by startup executor after hydrate_basis_bars() completes.
    Uses max() to avoid overwriting any live bars already counted.
    """
    if count > 0:
        current = self._bars_seen_since_restart.get(symbol, 0)
        self._bars_seen_since_restart[symbol] = max(current, count)
        self.logger.info(
            "[%s] seed_startup_bars: _bars_seen_since_restart=%d (seeded=%d)",
            symbol, self._bars_seen_since_restart[symbol], count,
        )
```

---

### Step 4 — `apps/reference/domains/decision_making/md_amr_handler.py`

Add `seed_startup_bars()` method to `MDAMRHandler` class (after `_bars_seen_since_restart` declaration, around line 143):

```python
def seed_startup_bars(self, symbol: str, count: int) -> None:
    """Seed _bars_seen_since_restart after startup basis import."""
    if count > 0:
        current = self._bars_seen_since_restart.get(symbol, 0)
        self._bars_seen_since_restart[symbol] = max(current, count)
        self.mlog.info(
            "MD_AMR seed_startup_bars sym=%s bars_seen=%d (seeded=%d)",
            symbol, self._bars_seen_since_restart[symbol], count,
        )
```

---

### Step 5 — `apps/reference/main.py`

**Import** (top of file, with other bootstrap imports):
```python
from apps.reference.bootstrap.startup_basis_hydrator import hydrate_basis_bars
```

**Executor block** — insert inside the startup warmup gate block, after the existing regime backfill section and before `release_startup_warmup_gate()` (~line 1230-1246).

Relative anchor: after the `except Exception as _regime_bf_err:` block that follows regime backfill, before `release_startup_warmup_gate()`.

```python
        # ── STARTUP_BASIS_EXECUTOR ─────────────────────────────────────────
        # Inject historical basis bars into BarAggregator (WARMUP_IMPORT mode)
        # Seeds FE feature buffers AND _bars_seen_since_restart counters so
        # Aurora/md_amr cold-start gates pass immediately on first live bar.
        LOG.info(" STARTUP_BASIS_EXECUTOR starting")
        if bar_aggregator is not None and backfill_adapter is not None:
            _basis_svc = PillarBackfillService(backfill_adapter)
            _basis_seeded: dict[str, dict[str, int]] = {}  # {strategy_id: {symbol: count}}
            for _plan_id, _plan in hydration_plan.plans.items():
                _has_basis_action = any(
                    a.action == "RESTORE_OR_REPLAY_BASIS_BARS"
                    for a in _plan.actions
                )
                if not _has_basis_action:
                    continue
                _sym = _plan.symbol
                _tf = _plan.requirement.basis_tf_sec
                _n = _plan.requirement.basis_required_bars
                _sid = _plan.strategy_id
                try:
                    _fetch = guardian_runtime.run(
                        _basis_svc.fetch_candles(_sym, _tf, _n),
                        timeout=60.0,
                    )
                    _n_imported = hydrate_basis_bars(bar_aggregator, _sym, _tf, _n, _fetch)
                    LOG.info(
                        " BASIS_HYDRATION strategy=%s sym=%s tf=%ds bars=%d/%d success=%s",
                        _sid, _sym, _tf, _n_imported, _n,
                        _fetch.success if _fetch else False,
                    )
                    # Seed _bars_seen_since_restart in the strategy handler
                    _handler_raw = started_strategy_handlers.get(_sid)
                    if _handler_raw is not None:
                        # Aurora is wrapped in _AuroraHandlerWrapper; md_amr is direct
                        _inner = getattr(_handler_raw, "handler", _handler_raw)
                        if hasattr(_inner, "seed_startup_bars"):
                            _inner.seed_startup_bars(_sym, _n_imported)
                    _basis_seeded.setdefault(_sid, {})[_sym] = _n_imported
                except Exception as _basis_err:
                    LOG.error(
                        " BASIS_HYDRATION failed strategy=%s sym=%s: %s",
                        _sid, _sym, _basis_err, exc_info=True,
                    )
            LOG.info(" STARTUP_BASIS_EXECUTOR done: %s", _basis_seeded)
        else:
            LOG.warning(
                " STARTUP_BASIS_EXECUTOR skipped: bar_aggregator=%s backfill_adapter=%s",
                bar_aggregator, backfill_adapter,
            )
        # ── END STARTUP_BASIS_EXECUTOR ──────────────────────────────────────
```

---

## Critical Files

| File | Change |
|---|---|
| `apps/reference/domains/market_data/bar_aggregator.py` | Add `inject_historical_bar()` + `source_mode` param to `_emit_bar_closed()` |
| `apps/reference/bootstrap/startup_basis_hydrator.py` | NEW — `hydrate_basis_bars()` |
| `apps/reference/domains/decision_making/aurora_handler.py` | Add `seed_startup_bars()` |
| `apps/reference/domains/decision_making/md_amr_handler.py` | Add `seed_startup_bars()` |
| `apps/reference/main.py` | Add import + executor block inside warmup gate |

**Reference only (no changes):**
- `apps/reference/bootstrap/startup_hydration_planner.py` — action `RESTORE_OR_REPLAY_BASIS_BARS` already defined at line 221
- `apps/reference/contracts/runtime_bar_identity.py` — `RuntimeBarSourceMode.WARMUP_IMPORT` already defined at line 11
- `apps/reference/domains/feature_engineering/pillar_backfill.py` — `PillarBackfillService.fetch_candles()` reused as-is
- `apps/reference/domains/decision_making/aurora_decision.py` — gate logic unchanged
- `apps/reference/domains/decision_making/md_amr_handler.py:1033-1067` — gate logic unchanged

---

## Tests

### New test files

**`tests/domains/market_data/test_bar_aggregator_warmup_import.py`**
- `test_inject_historical_bar_emits_bar_closed_with_warmup_import_source_mode`
- `test_inject_historical_bar_stores_in_completed_bars`
- `test_inject_historical_bar_updates_last_ts_boundary`
- `test_inject_historical_bar_does_not_corrupt_live_tick_ooo_guard`

**`tests/bootstrap/test_startup_basis_hydrator.py`**
- `test_hydrate_basis_bars_returns_count`
- `test_hydrate_basis_bars_returns_zero_when_aggregator_none`
- `test_hydrate_basis_bars_returns_zero_on_failed_fetch`
- `test_hydrate_basis_bars_constructs_correct_bar_timestamps`

**`tests/domains/decision_making/test_seed_startup_bars.py`**
- `test_aurora_seed_startup_bars_sets_counter`
- `test_aurora_seed_startup_bars_does_not_overwrite_higher_live_count`
- `test_md_amr_seed_startup_bars_sets_counter`
- `test_md_amr_seed_startup_bars_zero_is_noop`

---

## Verification

```bash
# Step 1: BarAggregator
pytest tests/domains/market_data/test_bar_aggregator_warmup_import.py -v

# Step 2: Hydrator
pytest tests/bootstrap/test_startup_basis_hydrator.py -v

# Steps 3+4: Handler seeding
pytest tests/domains/decision_making/test_seed_startup_bars.py -v

# Full regression
pytest tests/domains/ tests/bootstrap/ tests/integration/ tests/contracts/ -v --tb=short
```

**End-to-end manual verification:**
1. Start system cold (no analytics snapshot) at any time
2. Check log for `STARTUP_BASIS_EXECUTOR done` with non-zero counts
3. Check log for `seed_startup_bars: _bars_seen_since_restart=301` (Aurora) and `=96` (md_amr)
4. Verify first live bar triggers order evaluation (no `BARS_REQUIRED_COLD_START` rejection)
5. WAL rejections with `BARS_REQUIRED_COLD_START` should drop to 0

---

## Rollback

- `bar_aggregator.py`: remove `inject_historical_bar()`, restore `_emit_bar_closed()` signature (1 line)
- `startup_basis_hydrator.py`: delete file
- `aurora_handler.py`, `md_amr_handler.py`: remove `seed_startup_bars()` method each
- `main.py`: remove import + executor block (~35 lines)

Zero impact on live trading path. All changes are startup-only / additive.
