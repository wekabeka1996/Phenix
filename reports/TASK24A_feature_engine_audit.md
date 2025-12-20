# TASK24A — FeatureEngineering Forensic Audit (P0/P1)

Scope: `apps/reference/domains/feature_engineering/**`

## Findings (P0)

### P0 — `macro_sync` silently collapses to neutral (`0.5`) in common conditions

- **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:346`
- **Why:** `compute_macro_sync()` returns `self.cfg.neutral_value` (configured as `0.5`) on multiple “not computable” paths, without emitting any readiness/data-quality signal.
- **Key failure modes:**
  - **Length mismatch ⇒ no correlation computed**
    - **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:372`
    - **What breaks:** correlation is computed **only** when `len(anchor_returns) == len(state.returns_buffer)`. With different tick rates, lengths diverge and the function returns neutral.
  - **Errors swallowed**
    - **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:373-377`
    - **What breaks:** exceptions during correlation are silently ignored (`except Exception: pass`), increasing “always neutral” probability.
  - **Wrong config coupling**
    - **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:340`
    - **What breaks:** `update_macro_sync_buffer()` gates on `delta_price_spike_filter_ms` (delta_price config), not `macro_sync.*`; this is a hidden coupling that can block return updates.
- **Impact:** downstream domains cannot distinguish “true corr=0 (macro_sync=0.5 after mapping)” from “NOT_READY placeholder”, enabling silent degrade.

### P0 — `volatility_state` truthiness bug (0-valued ranges treated as missing)

- **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:224-228`
- **What breaks:** `current_range` uses `if state.range_max and state.range_min` (truthiness). When either is `Decimal('0')`, it incorrectly falls back to `Decimal('0')`.
- **Impact:** volatility regime can be understated/zeroed silently; downstream sizing/regime logic receives misleading “calm” state.

## Findings (P1)

### P1 — `volume_spike` mixes numeric types and ignores `time_diff_ms` (tick-rate dependent)

- **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:88-150`
- **What breaks:**
  - **float + Decimal mixing**
    - **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:125-128` (float accumulation)
    - **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:142-149` (Decimal division)
  - **No time normalization**
    - `update_volume_spike()` uses only tick timestamp + a coarse “window close” (`window_sec`) and accumulates raw volume; it does not normalize by `dt` between ticks.
- **Impact:** identical “volume/sec” streams can produce different spikes depending on tick rate; silent drift is likely across symbols/exchanges.

### P1 — “tick <5s drop” gating: not present as a literal, but hidden coupling exists

- **Observation:** No explicit “<5s drop” in this module; however `update_macro_sync_buffer()` currently gates using `delta_price_spike_filter_ms` (commonly used for “gap” filters).
- **File/line:** `apps/reference/domains/feature_engineering/calculation_engine.py:340`
- **Risk:** macro_sync behavior can unintentionally follow delta_price gating rather than a dedicated macro_sync staleness/TTL policy.

## Zombie / Phase1 duplicate

- **Target:** `apps/reference/domains/feature_engineering/feature_engineering_phase1.py`
- **Status:** file not present in workspace (`find apps/reference -name '*feature_engineering_phase1*'` returns empty).
- **Risk:** docs reference it, but runtime imports appear absent; still needs an import-ban test to prevent reintroduction.

## Summary (“what breaks / why”)

- `macro_sync` can become a near-constant neutral feature due to strict-length correlation + swallowed errors + wrong gating config, without any readiness signal.
- `volume_spike` is not time-normalized and mixes float/Decimal, so spike values are tick-rate dependent.
- `volatility_state` uses truthiness checks and can mis-handle 0.0 values.

