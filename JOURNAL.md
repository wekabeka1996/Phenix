# Engineering Journal


## 2026-03-04: Phase 0.7 — Backtest Engine OHLCV DataContract Integration

**Task:** Wire fail-fast OHLCV data contract validation into `BacktestEngine.load_data()` at parquet load time (per-symbol, before frame concatenation).

**Why:** Corrupt or misaligned parquet files (missing columns, nulls in price cols, high < low) currently produce silent bad data or cryptic downstream errors mid-run. Phase 0.7 adds a hard gate at the earliest possible point — immediately after `q.collect()` per symbol — so violations surface as a clear `ValueError` with the symbol name and exact violation list.

**Design decision — polars-native (no pyarrow/pandas):**
The existing `tools/parquet_contract/data_contract.py` `DataContract` class is pandas-based and requires `pyarrow` for polars→pandas conversion; `pyarrow` is not installed in this environment. Rather than adding a dependency, the validation was implemented as a self-contained native polars check — mirrors the same 4-check structure (missing columns → dtype class → nulls → semantic invariants) without any bridge overhead.

**Changes:**

1. `backtest_engine/engine.py`:
   - `_OHLCV_REQUIRED`, `_OHLCV_NUMERIC`, `_OHLCV_NUMERIC_DTYPES` — module-level constants (frozenset/tuple)
   - `_validate_ohlcv_contract(frame, symbol)` — new module-level function; native polars; 4-check pipeline; raises `ValueError: "DataContract violation (ohlcv) [SYMBOL]: ..."` on any failure
   - `load_data()`: replaced inline `frames.append(q.collect(streaming=True))` with explicit `collected = q.collect()` + `_validate_ohlcv_contract(collected, symbol)` + `frames.append(collected)`
   - Added `except ValueError: raise` before the existing `except Exception` catch-all so DataContract violations are not silently swallowed

2. `tests/backtest_engine/test_data_contract_integration.py` (new):
   - `TestValidateOhlcvContractUnit` (6 tests): valid frame passes, missing column, null in close, high<low, negative volume, single-row edge case
   - `TestLoadDataContractIntegration` (3 tests): valid parquet → `load_data()` succeeds, high<low parquet → raises, null close parquet → raises

**Test results:**
```
tests/backtest_engine/test_data_contract_integration.py  9/9 pass, 0.31s
tests/backtest_engine/ (full suite)                     57/57 pass, 2 skipped (pre-existing), 0 regressions
```

**Invariants after this change:**
- Every symbol's OHLCV parquet is validated at load time before entering the simulation loop
- Contract violations raise `ValueError` and propagate — they are not silenced by the general IO error handler
- Validation is pure polars — no pyarrow dependency; fast (sub-millisecond for typical bar counts)


## 2026-03-01: EP-SSOT-NORMALIZE-SIGNEDV2-P2 — normalize_mode SSOT Final Hardening

**Task:** Complete two-phase SSOT enforcement for `normalize_mode` / `normalize_signals_mode`.
Phase 1 wired YAML → runtime (YAML → `AuroraConfigLoaderMixin` → kernel). Phase 2 (this session)
removes the remaining "two-truths" and silent fallbacks.

**Why:** `SignalsConfig` previously had `Literal["off", "signed_v2"]` but the kernel (`AuroraScoringKernel`) rejected `"off"` at runtime. Config said "allowed"; kernel said "rejected" = two truths. Additionally, `signals=None` silently fell back to `"signed_v2"` on the strict pydantic path — silent default in a fail-closed system.

**Changes:**

1. `apps/reference/config_models.py`:
   - `SignalsConfig.normalize_signals_mode`: `Literal["off", "signed_v2"]` → `Literal["signed_v2"]`. `"off"` removed from production YAML boundary. Forensic passthrough still works by passing `normalize_mode="off"` directly to the scoring function.
   - Removed dead `_forbid_legacy_normalize_signals_in_live` model validator (unreachable: `Literal["signed_v2"]` rejects `legacy_v1` before the validator runs).

2. `apps/reference/domains/decision_making/aurora_config_loader.py` (lines 162–176):
   - `signals=None` on strict pydantic path → `ConfigContractError` (fail-closed). Test-mock path (`_strict_pydantic_config=False`) falls back to `"signed_v2"`.

3. `apps/reference/domains/decision_making/decision_making.py` (lines 153–160):
   - Added `normalize_signals_mode` init block: reads from `config.strategies.aurora.decision.signals.normalize_signals_mode` with `try/except` fallback = `"signed_v2"`. Mirrors `AuroraConfigLoaderMixin` pattern for `DecisionMaking` (which does not extend the mixin).

4. `apps/reference/domains/decision_making/scoring_direction_strength_v1.py` (docstring):
   - Updated to clarify `"off"` = forensic-only passthrough, not valid in production YAML. `legacy_v1` removed.

5. Test fixtures updated (`"off"` → `"signed_v2"` in 4 files):
   - `tests/domains/decision_making/test_normalize_mode_ssot.py`: `test_config_accepts_off` → `test_config_rejects_off_mode`
   - `tests/config/test_toplevel_forbid_enforcement.py:44`
   - `tests/config/test_typed_dict_any_configs.py:49`
   - `tests/domains/decision_making/test_side_bias_window_updates_v1.py:129`

6. Test fixtures for `SimpleNamespace` + `__new__`-based construction:
   - `tests/domains/decision_making/test_aurora_handler.py:44`: added `normalize_signals_mode="signed_v2"` to signals SimpleNamespace
   - `tests/domains/decision_making/test_aurora_reentry_cooldown.py:31`: same
   - `tests/domains/decision_making/test_task40_one_open_order_guard.py:95`: `dm.normalize_signals_mode = "signed_v2"` added to `_mk_dm` (`__new__`-bypass helper)

**Evidence pack:**
- `rg "legacy_v1" apps/ config/` → only docstrings + error-message patterns (no active code)
- `rg "net_zero" apps/ config/` → only docs (`aurora_math_passport.md`)
- `rg "normalize_mode_effective" apps/` → `intent_builder.py:365` ✅ (WAL metadata wired)

**Test results:**
```
tests/domains/decision_making/  288/288 pass
tests/config/                   240/240 pass
tests/audit/                    513/513 pass (combined)
Broader suite                  1269+ pass, 5 pre-existing unrelated fails
```

**Invariants after this change:**
- Production YAML can only express `normalize_signals_mode: signed_v2` (Pydantic `Literal["signed_v2"]`)
- Forensic tooling can pass `normalize_mode="off"` directly to `compute_direction_strength_score()` — no YAML bypass
- `signals=None` on strict pydantic path → `ConfigContractError` (no silent default)
- `intent_builder.py` writes `normalize_mode_effective` to WAL ORDER_INTENT for every placed trade


## 2026-03-01: Phase R3-A-lite — Market Policy Tables (PKG-R3A)

**Task:** Build (trend × vol × stress × horizon) edge tables and derive Aurora sizing + MR entry policies — without requiring backtest trades. Directly from forward returns on historical bars.

**Why:** R3-B confirmed TREND_UP has near-zero sign lift but measurable Cohen's d (fat-tail mean advantage). This means TREND_UP is a sizing signal, not a binary entry filter. TREND_DOWN (SMA 48/192) marks oversold = mean-reversion setup. `TREND_DOWN|HIGH_VOL` consistently 0.53-0.57 sign_acc across all 4 symbols. R3-A-lite quantifies these effects per regime cell and derives operational policies.

**Changes:**

1. `tools/parquet_pipeline/policy_tables.py` (new, ~300 lines):
   - `_cvar5(arr)`: mean of bottom 5% (Expected Shortfall)
   - `_tail_uplift(arr)`: p95 - p50 (upside tail extension)
   - `compute_edge_table()`: per (trend × vol × stress × horizon) cell — n, mean, std, p05/p50/p95, sign_acc, cvar5, tail_uplift
   - `derive_trend_policy()`: Aurora sizing multiplier = clamp(1 + mean_uplift/baseline_std, 0.25, 2.50); signal = increase/neutral/reduce; baseline = FLAT|MID_VOL|NORMAL
   - `derive_mr_policy()`: MR entry policy (boost/allow/reduce/block) by sign_acc_delta thresholds (>0.03 / ≥-0.01 / ≥-0.04 / <-0.04)

2. `tools/parquet_pipeline/__main__.py`: r3a subcommand added:
   - `_parse_r3a_args()`: --with-stress flag triggers A4 actuator attachment (enter=0.60, CB=6, min_dur=15, window=200, max=2)
   - `_generate_r3a_report()`: per-symbol Aurora sizing + MR entry + Edge Table @ 24b in markdown
   - `main_r3a()`: polars pipeline → stress_v0 → optional A4 actuator → edge table + policies → parquet + report + manifest

3. `tests/test_policy_tables.py` (new): 24 tests — `TestCvar5` (3), `TestTailUplift` (3), `TestComputeEdgeTable` (9), `TestDeriveTrendPolicy` (4), `TestDeriveMrPolicy` (5)

**CLI:**
```bash
python -X utf8 -m tools.parquet_pipeline r3a \
  --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/ \
  --with-stress
```

**Key findings (cross-symbol, 4 assets, 2023-06—2024-03):**

Aurora sizing (primary_horizon=24b):
- `TREND_UP|HIGH_VOL|NORMAL` → sizing_mult 1.05—1.16, signal=increase on 3/4 symbols (ETH=neutral at 1.048); tail_ratio 1.94—3.01
- `TREND_DOWN|HIGH_VOL|NORMAL` → sizing_mult 1.08—1.16, signal=increase on all 4 symbols (mean-reversion bounce positive mean at 2h)
- `TREND_UP|LOW_VOL|*` → neutral/reduce in most symbols (thin regime, low edge)
- `FLAT|HIGH_VOL|STRESS` → neutral BTC/ETH, but DOGE has outlier (-6% mean return at 24b)

MR entry policy (primary_horizon=12b):
- `TREND_DOWN|HIGH_VOL|NORMAL` → **boost** all 4 symbols (deltas: +0.065, +0.074, +0.046, +0.028) — most robust finding
- `TREND_DOWN|HIGH_VOL|STRESS` → boost BTC/DOGE, neutral ETH, increase PEPE
- `TREND_UP|MID_VOL|STRESS` → block BTC/ETH, block DOGE, allow PEPE
- `TREND_UP|LOW_VOL|STRESS` → block/reduce on 3/4 (sample n=46-123, treat with caution)

**Test results:**
```
tests/test_policy_tables.py   24/24 pass, 0.51s
Regression suite              5 pre-existing fails only (unchanged)
```

**Outputs generated:**
- `reports/r3a_market_policy_tables.md` — full cross-symbol policy tables
- `reports/r3a_edge_{BTC,ETH,DOGE,PEPE}.parquet` — per-symbol edge tables
- `reports/r3a_aurora_policy_{sym}.parquet`, `r3a_mr_policy_{sym}.parquet`
- `reports/r3a_edge_results.parquet` (combined), `reports/r3a_manifest.json`


## 2026-03-01: Phase R3-B — Forward Separability (PKG-R3B)

**Task:** Validate whether the SMA-slope trend label (from R2) carries predictive edge over
forward return horizons N ∈ {12, 24, 48} bars (1h / 2h / 4h at 5m).

**Motivation:** R2 confirmed vol separation is strong (0.17-0.21 overlap), but trend_return_overlap
at 1-bar returns was 0.87-0.92 — expected for 5m noise. R3-B verifies that the trend label is
predictive over multi-bar horizons before building any strategy overlay on top of it.

**Design decisions:**
- Forward return: `fwd_ret_N[t] = log(close[t+N] / close[t])` — avoids look-ahead, numpy-native.
- Cohen's d with pooled std — standardised mean difference between label groups.
- Sign lift = `P(fwd_ret > 0 | TREND_UP) − P(fwd_ret > 0 | FLAT)` — probability advantage.
- Edge verdict thresholds: strong (|d|>0.20 AND |lift|>0.05), moderate (0.10/0.02), weak (0.05/0.01), none.
- Vol interaction 3×3 matrix (trend × vol_bucket) — captures whether HIGH_VOL+TREND_UP has higher edge.
- Reuses `_trend_labels`, `_vol_labels` from `regime_grid.py` with R2 winner params as defaults.
- Reuses `_histogram_overlap`, `_bhattacharyya` from `market_structure.py` — no duplication.

**Changes:**

1. `tools/parquet_pipeline/forward_separability.py` (new, ~280 lines):
   - `compute_forward_returns(df, horizons) → pl.DataFrame`: attaches fwd_ret_N columns; last N bars = NaN
   - `_cohens_d(a, b) → float`: pooled std; returns 0.0 on empty/zero-variance arrays
   - `_sign_accuracy(arr) → float`: P(x > 0); NaN excluded; 0.5 on empty
   - `_edge_verdict(cohens_d, sign_lift) → str`: strong/moderate/weak/none
   - `_label_stats(df, trend_col, horizon) → dict`: per-label mean/std/sign_accuracy/n
   - `run_forward_separability(df, *, sma_short, sma_long, slope_threshold, atr_window, hysteresis_bars, horizons, tf_minutes) → dict`
     - Returns: params, horizons, tf_minutes, label_distribution, per_horizon, vol_interaction
   - `flatten_separability_to_df(result, symbol) → pl.DataFrame`: one row per (label, horizon) for export

2. `tools/parquet_pipeline/__main__.py` (+~280 lines):
   - `_parse_r3b_args()`: --symbols, --tf, --months-range, --months, --data-dir, --output-dir,
     --window, --burn-in, --sma-short, --sma-long, --slope-threshold, --atr-window, --hysteresis-bars, --horizons
   - `_generate_r3b_report(results, ...)`: 4-section markdown (edge verdict, DOWN vs FLAT, label dist, vol interaction)
   - `main_r3b()`: multi-symbol runner → writes r3_forward_separability_{sym}.parquet, combined parquet, report, manifest
   - Routing: `elif sys.argv[1] == "r3b"` added

3. `tests/test_forward_separability.py` (new, 34 tests, 0.53s):
   - `TestComputeForwardReturns` (7): columns present, last N = NaN, first bar finite, length unchanged, missing close → nulls, default horizons, exact log-ratio check
   - `TestCohensD` (4): identical = 0, large separation, empty = 0, sign correct
   - `TestSignAccuracy` (5): all positive, all negative, 50/50, empty = 0.5, NaN excluded
   - `TestEdgeVerdict` (6): strong, moderate, weak_d, weak_lift, none, negative strong
   - `TestRunForwardSeparability` (9): keys, horizons, dist keys, dist sums to 100, label stats present, sign_acc in [0,1], finite values, valid verdicts, vol matrix combos
   - `TestFlattenSeparabilityToDf` (3): shape (3 labels × H horizons), symbol column, empty result no crash

**Test result:** 34/34 pass, 0.53s, 0 regressions (pre-existing 5 unchanged).

**CLI usage:**
```bash
python -X utf8 -m tools.parquet_pipeline r3b \
  --symbols BTCUSDT ETHUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/
```

**Outputs:** `reports/r3_forward_separability_{symbol}.parquet`, `reports/r3_forward_separability_results.parquet`,
`reports/r3_forward_separability_report.md`, `reports/r3_forward_separability_manifest.json`


## 2026-03-01: Phase R2 — Regime Grid Calibration (PKG-R2)

**Task:** Grid-search over (sma_short, sma_long, slope_threshold, atr_window, hysteresis_bars)
to find regime labeling configurations that are stable (low churn), separable (distinct
return/vol distributions per label), and balanced (no state < 1% or > 80% of bars).

**Motivation:** Phase R1 proved the market has detectable structure. R2 converts that
knowledge into calibrated SMA+vol regime labels for regime.yaml — specifically finding
parameter ranges where labels are stable enough for strategy gating without being decorative.

**Changes:**

1. `tools/parquet_pipeline/regime_grid.py` (new, ~335 lines):
   - `_sma_slope(close, sma_short, sma_long) → pl.Series`: normalised slope via polars expression form
   - `_apply_hysteresis(labels, n) → pl.Series`: O(n) flip suppression; n=1 = identity; return-to-committed commits immediately
   - `_trend_labels(df, sma_short, sma_long, slope_threshold, hysteresis_bars) → pl.Series`: TREND_UP/TREND_DOWN/FLAT; warmup nulls → FLAT fill
   - `_vol_labels(df, atr_window) → pl.Series`: LOW_VOL/MID_VOL/HIGH_VOL via rolling bar_range proxy, global p33/p66 tertiles
   - `_count_switches(labels)`, `_median_run_bars(labels)`: stability helpers
   - `compute_grid_row(df, ...)` → 22-key dict: 5 params + 8 coverage + 4 stability + 4 separability + 1 score
   - `_score_grid_row(row)`: `0.5*churn_score + 0.4*sep_score - 0.1*cov_penalty`; score ∈ [-0.10, 0.90]
   - `run_regime_grid(df, ...)` → Polars DataFrame sorted by score descending; skips sma_short ≥ sma_long
   - Reuses `_histogram_overlap`, `_bhattacharyya` from `market_structure.py` — no duplication

2. `tools/parquet_pipeline/__main__.py` (~340 new lines):
   - `_parse_r2_args()`: --symbols, --tf, --months-range, --months, --data-dir, --output-dir, --window, --burn-in
   - `_generate_r2_report(results, symbols, tf, months)`: 5-section markdown
     - §1 Top-5 cross-symbol avg score table
     - §2 Per-symbol top-3 detail table
     - §3 Parameter sensitivity (mean score per axis value)
     - §4 Coverage check (configs with coverage_ok=False)
     - §5 Calibration recommendations (min/max/mode for top 10%)
   - `main_r2(argv=None)`: multi-symbol runner; per-symbol parquet + top-20 JSON; combined results.parquet; report + manifest
   - Routing: `elif sys.argv[1] == "r2"` (backward-compatible; r1/main() unchanged)

3. `tests/test_regime_grid.py` (new, 29 tests):
   - `TestApplyHysteresis` (4): identity n=1, isolated flip filtered, two consecutive commits, empty series
   - `TestTrendLabels` (5): uptrend→TREND_UP, downtrend→TREND_DOWN, flat→FLAT, hyst reduces switches, length correct
   - `TestVolLabels` (4): distinct groups present, constant bar_range→MID_VOL, window 14vs28 no crash, short no crash
   - `TestComputeGridRow` (7): all 22 keys, spd≥0, trend sum=1, vol sum=1, overlap in [0,1], all finite, score in [-0.15,1.0]
   - `TestScoreGridRow` (4): near-max for perfect row, high churn reduces, high overlap reduces, coverage violation penalizes
   - `TestRunRegimeGrid` (5): sorted desc, shape correct, invalid sma skipped, single combo=1 row, all numeric finite

**CLI usage:**
```bash
python -m tools.parquet_pipeline r2 \
  --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/
```

**Outputs per symbol:** `regime_grid_{symbol}.parquet` (all combos), `regime_grid_{symbol}_top20.json`
**Cross-symbol:** `regime_grid_results.parquet`, `regime_grid_report.md`, `regime_grid_manifest.json`

**Grid axes:**
- sma_short: [24, 36, 48], sma_long: [96, 144, 192] → all combos valid (no sma_short ≥ sma_long)
- slope_threshold: [0.0005, 0.001, 0.0015, 0.002]
- atr_window: [14, 21, 28]
- hysteresis_bars: [1, 2, 3]
- Total: 324 valid combos per symbol

**Scoring design:**
- 50% stability (tanker priority): `churn_score = max(0, 1 - trend_spd / 5.0)`
- 40% separability: `sep_score = 0.5*(1-trend_return_overlap) + 0.5*(1-vol_atr_overlap)`
- 10% coverage penalty: -1.0 if any state < 1% or > 80% of bars

**Key implementation decisions:**
- `bar_range` (already in STRESS_OUTPUT_COLUMNS) used as ATR proxy — no raw OHLC needed
- NaN from rolling warmup falls into MID_VOL: `np.where(nan < p33)` = False (numpy silent NaN semantics)
- `group_by(col).agg(pl.len())` for coverage pcts (avoids `value_counts()` API instability across polars versions)
- Separability compares FLAT vs non-FLAT returns and LOW_VOL vs HIGH_VOL ATR via R1 histogram helpers
- score `-0.1` lower bound: can go slightly below 0 only when coverage_ok=False (penalty dominated)

**Test count:** 29 new tests; 29/29 green in 0.37s; 0 regressions (5 pre-existing failures unchanged).

---

## 2026-03-01: Phase 0.6 — Per-Strategy SystemStress Policy + STRESS Attenuation (PKG-0.6)

**Task:** Add `system_stress_policy: off|attenuate|block` per-strategy to `SafetyGatesConfig` so Gate 0.5 is opt-in per strategy. Add configurable STRESS attenuation: `policy=attenuate` halves `margin_pct_mult` when state=STRESS.

**Motivation:** Phase 0.5 globally blocked EXTREME entries for all strategies. Mean-reversion is counter-trend — stress overlay must not apply. Aurora is trend-following — stress gates fully relevant. Per-strategy policy resolves this without a global toggle.

**Policy semantics:**
- `off` → Gate 0.5 entirely bypassed; EXTREME is ignored for this strategy (fail-open on missing config)
- `attenuate` → EXTREME=DENY(NRR-059); STRESS=ALLOW but `margin_pct_mult *= stress_attenuation_factor`
- `block` → EXTREME=DENY(NRR-059) and STRESS=DENY(NRR-059)

**Changes:**

1. `apps/reference/config_models.py`:
   - `SafetyGatesConfig` gains 2 new fields with defaults (backward-compatible):
     - `system_stress_policy: Literal["off", "attenuate", "block"] = "off"`
     - `stress_attenuation_factor: float = Field(default=0.5, ge=0.0, le=1.0)`

2. `config/aurora/strategies/aurora.yaml`:
   ```yaml
   safety_gates:
     enabled: true
     system_stress_policy: attenuate   # EXTREME=DENY, STRESS=size_down
     stress_attenuation_factor: 0.50   # margin_pct_mult *= 0.5 when STRESS
   ```

3. `config/aurora/strategies/mean_reversion.yaml`:
   ```yaml
   safety_gates:
     enabled: false
     system_stress_policy: "off"   # quoted: YAML 1.1 parses bare 'off' as bool False
   ```
   **Implementation note:** YAML 1.1 treats bare `off` as Python `False`. Pydantic `Literal["off", ...]` rejects `False`. Always quote `off`/`on`/`yes`/`no` in YAML when binding to `Literal` string fields.

4. `apps/reference/domains/decision_making/safety_gates.py`:
   - New helper `_resolve_stress_policy(config, strategy_id) → (str, float)`:
     fail-open: returns `("off", 1.0)` on any missing/bad config so strategies without the field are unaffected
   - `_check_system_stress_gate()` gains `stress_policy: str = "off"` param:
     - `policy=="off"` short-circuits before reading `system_stress_states` (true bypass)
     - `policy in ("attenuate","block")` + EXTREME → DENY(NRR-059)
     - `policy=="block"` + STRESS → DENY(NRR-059)
     - `policy=="attenuate"` + STRESS → ALLOW, surface state for gateway attenuation
   - `apply_safety_gates()`: calls `_resolve_stress_policy()`, passes `stress_policy` to Gate 0.5

5. `apps/reference/domains/decision_making/strategy_gateway.py`:
   - After regime-based `margin_pct_mult` (or `None` treated as `Decimal("1")`), before `_calculate_position_size()`:
     ```python
     _stress = dm._system_stress_states.get(symbol, "NORMAL")
     if _stress == "STRESS" and _policy == "attenuate":
         margin_pct_mult = (margin_pct_mult or Decimal("1")) * Decimal(str(_factor))
     ```
   - Wrapped in `try/except` — fail-open: attenuation errors must never block trades

6. `tests/test_system_stress_overlay.py` (modified):
   - `TestCheckSystemStressGate._call()` default updated to `stress_policy="attenuate"` to preserve Phase 0.5 test semantics under the new `"off"` default
   - `test_disabled_flag_bypasses`: explicit `stress_policy="attenuate"` — proves `apply_safety_gates_flag=False` bypass works independently of policy

7. `tests/test_stress_policy.py` (new, 23 tests):
   - `TestResolveStressPolicy` (6): missing strategy, valid attenuate, valid block, bad policy fallback, factor clamped, missing safety_gates attr
   - `TestStressPolicyOff` (3): NORMAL/STRESS/EXTREME → ALLOW (even EXTREME bypassed)
   - `TestStressPolicyAttenuate` (4): NORMAL→ALLOW, STRESS→ALLOW+surface, EXTREME→DENY, reduce_only bypass
   - `TestStressPolicyBlock` (4): NORMAL→ALLOW, STRESS→DENY, EXTREME→DENY, reduce_only bypass
   - `TestStressAttenuation` (6): halves existing mult, mult=None→factor, off leaves unchanged, NORMAL unchanged, EXTREME not attenuated in gateway, custom factor

**Test count:** 23 new tests; 22 Phase 0.5 tests still pass (45/45 combined); 0 regressions (5 pre-existing failures unchanged).

**Key implementation decisions:**
- Default `policy="off"` (fail-open): any strategy that doesn't set the field gets zero Gate 0.5 interference — existing configs unaffected
- `_factor` applied to `margin_pct_mult`, not `risk_fraction` — consistent with how regime_sizing already works at that point
- `SafetyGateResult.system_stress_state` field unchanged (Phase 0.5); attenuation factor not added to result — gateway reads config directly
- NRR-059 reused for both EXTREME and STRESS-block cases (same semantics: stress entry blocked)

---

## 2026-03-01: Phase R1 — Market Structure Audit (PKG-R1)

**Task:** Build a market-first research layer: statistical characterization of price/vol
distributions before any strategy parameter tuning. Outputs 5 blocks of analysis across
4 symbols (BTCUSDT, ETHUSDT, DOGEUSDT, 1000PEPEUSDT).

**Motivation:** Strategy calibration (R2/R3) requires knowing the market's statistical
character first — distribution tails, regime persistence, separability, memory structure.
Without this, parameter tuning is empirical guesswork blind to the data-generating process.

**Deliverables:**

1. `tools/parquet_pipeline/market_structure.py` (new, ~360 lines):
   - Block 1 `compute_distribution_stats()` — 4 metrics (atr, realized_vol, log_return,
     bar_range): count, mean, std, skew, kurtosis, p25/50/75/90/99, tail_ratio
   - Block 2 `compute_persistence_stats()` — run-length encoding (pure Python accumulator),
     autocorr(return, lag=1), autocorr(vol, lag=1)
   - Block 3 `compute_regime_separability()` — 2-axis proxy labels (directionality +
     vol_bucket), histogram-based Bhattacharyya distance and overlap coefficient
     (polars-first, no scipy; `np.histogram` on shared bins)
   - Block 4 `compute_structural_breaks()` — Hurst R/S exponent, vol_clustering_lag1/2/5,
     rolling mean/variance shift detection
   - Block 5 `simulate_stability_grid()` — actuator config grid search (optional flag),
     reuses `actuator_rules.run_actuator` + `aggregation.compute_stress_level`

2. `tools/parquet_pipeline/__main__.py` (modified, +~390 lines):
   - `_parse_months_range("2023-06:2024-03")` → list of months (year boundary wrap)
   - `_parse_r1_args()` — `--symbols`, `--months-range`, `--include-grid`, `--window`,
     `--burn-in`, `--output-dir`
   - `_generate_r1_report()` — 5-section markdown (distributions, persistence,
     separability, structural breaks, calibration recommendations)
   - `main_r1()` — multi-symbol runner; per-symbol JSON + cross-symbol report + manifest
   - Routing: `sys.argv[1] == "r1"` → `main_r1()` (backward-compatible; existing `main()` tests unchanged)

3. `tests/test_market_structure.py` (new, 38 tests):
   - `TestComputeDistributionStats` (6), `TestComputePersistenceStats` (6),
     `TestHistogramHelpers` (4), `TestProxyLabels` (4),
     `TestComputeRegimeSeparability` (5), `TestComputeStructuralBreaks` (5),
     `TestSimulateStabilityGrid` (4), `TestParseMonthsRange` (4)
   - All synthetic DataFrames — no parquet I/O; 38/38 pass in 0.37s

**CLI usage:**
```bash
python -m tools.parquet_pipeline r1 \
  --symbols BTCUSDT ETHUSDT DOGEUSDT 1000PEPEUSDT \
  --months-range 2023-06:2024-03 \
  --output-dir reports/
```

**Key design decisions:**
- Polars-first throughout; numpy only for histogram math (`_bhattacharyya`, `_histogram_overlap`)
  and `_hurst_rs` R/S loop. No scipy/pandas dependency.
- Proxy labeling is 2-axis (Directionality + Vol bucket), not mutually exclusive regimes.
  SMA_SHORT=24, SMA_LONG=96, slope_flat_threshold=0.002; ATR tertiles p33/p66.
- Bhattacharyya uses shared `np.linspace(combined_min, combined_max, 50)` bins for
  numerically stable comparison of unequal-length series.
- `_hurst_rs` returns 0.5 (neutral) for n < 20 or insufficient chunk diversity.
- Block 5 gated behind `--include-grid` flag (slow: O(T×K³) actuator calls).
- `SEPARABILITY_OVERLAP_WARN = 0.70`: flag raised when histograms overlap > 70%.

**Test count:** 38 new tests; 0 regressions.

---

## 2026-03-01: Phase 0.5 — SystemStressOverlay Live DM Integration (PKG-0.5)

**Task:** Wire A4 preset as a live runtime overlay in the event bus:
`EVT:BAR_CLOSED → SystemStressOverlay → EVT:SYSTEM_STRESS_STATE_UPDATED → DecisionMaking._system_stress_states → SafetyGates Gate 0.5`

**Changes:**

1. `schemas/system_stress_state_updated_v1.json` (new): JSON Schema for the emitted event.
2. `apps/reference/domains/system_stress/__init__.py` (new): package marker.
3. `apps/reference/domains/system_stress/system_stress_overlay.py` (new, ~280 lines):
   - `_SymbolStressState`: per-symbol rolling z-score buffers with strict no-lookahead guarantee
     (compute z against current deque, then append — replicates Polars `.shift(1)` pattern)
   - `_StressActuator`: incremental per-bar FSM (NORMAL/STRESS/EXTREME) with consecutive-bar
     confirmation, min_duration guard, and circuit breaker
   - `SystemStressOverlay`: FSM domain; subscribes to `EVT:BAR_CLOSED` (tf_sec==basis_tf_sec),
     maintains per-symbol state, emits `EVT:SYSTEM_STRESS_STATE_UPDATED` on transitions only
4. `config/aurora/regime.yaml`: updated `state_mapping` from A0 defaults to A4 winner values
   (`consecutive_bars_enter=6`, `consecutive_bars_exit=4`, `min_duration_bars=15`,
   `switch_window_bars=200`, `max_switches_per_window=2`)
5. `apps/reference/domains/decision_making/normalized_reject_reasons.py`:
   added `SYSTEM_STRESS_ENTRY_BLOCKED = "NRR-059"`
6. `apps/reference/domains/decision_making/decision_making.py`:
   - `self._system_stress_states: Dict[str, str] = {}` (volatile cache, same pattern as `_per_symbol_regimes`)
   - Subscription: `fsm.listen("EVT:SYSTEM_STRESS_STATE_UPDATED", self._on_system_stress)`
   - Handler `_on_system_stress()`: caches `pld["state"]` per symbol
   - Pass `system_stress_states=self._system_stress_states` to `apply_safety_gates()`
7. `apps/reference/domains/decision_making/safety_gates.py`:
   - `SafetyGateResult.system_stress_state: str = "NORMAL"` (carried downstream for Phase 0.6 attenuation)
   - `_check_system_stress_gate()`: EXTREME→DENY(NRR-059); STRESS→ALLOW+surface; reduce_only bypasses
   - Gate 0.5 inserted in `apply_safety_gates()` chain after Gate 0 (config), before Gate 1 (regime conf)
8. `apps/reference/bootstrap/domain_builder.py`:
   - `LiveDomainBundle.system_stress_overlay: Optional[SystemStressOverlay] = None`
   - Instantiated in `build_live_domains()` and returned in bundle
9. `apps/reference/main.py`:
   - Import + backtest path wiring (after `RegimeDetector`): `SystemStressOverlay(config, fsm)` + `fsm.register_domain`
10. `tests/test_system_stress_overlay.py` (new, 22 tests):
    - `TestStressActuator` (5): stays_normal, NORMAL→STRESS, hysteresis, interrupted reset, circuit_breaker
    - `TestSystemStressOverlayDisabled` (2): no subscription, no emission
    - `TestSystemStressOverlayBurnIn` (2): burn-in suppression, tf_sec filter
    - `TestSystemStressOverlayTransition` (4): quiet bars hold, NORMAL→crisis, no duplicate, symbol isolation
    - `TestCheckSystemStressGate` (7): NORMAL/STRESS/EXTREME/reduce_only/None/unknown/disabled
    - `TestSafetyGateResultField` (2): default NORMAL, field persistence
11. `tests/domains/decision_making/test_directional_sanity_gate.py`:
    `dm._system_stress_states = {}` added to `dm_minimal` fixture
12. `tests/domains/decision_making/test_task40_one_open_order_guard.py`:
    `dm._system_stress_states = {}` added to fixture

**Test count:** 22 new tests pass; 5 pre-existing failures remain (unrelated: `test_failclosed_validation.py` x4, risk_management x1); zero regressions introduced.

**Gate semantics:**
- `EXTREME` (stress_level ≥ 0.85): new entries DENIED (NRR-059); reduce_only bypasses
- `STRESS` (0.60 ≤ stress_level < 0.85): new entries ALLOWED; `system_stress_state` field surfaced for Phase 0.6 attenuation (risk_fraction reduction)
- `NORMAL`: no change to flow

**Key implementation notes:**
- No-lookahead: z-score computed against deque contents BEFORE appending current bar (exact replication of offline batch logic)
- NORMAL→EXTREME direct: when `stress_level ≥ enter_extreme`, actuator jumps directly without going through STRESS — expected behavior
- `enabled=False` is a true no-op: constructor returns immediately without subscribing, zero overhead
- `min_duration_bars=15` applies to ALL states including NORMAL (anti-churn cooldown: 75 min at 5m after returning from STRESS)

---

## 2026-03-01: Phase 0.4 — A4 Multi-Symbol Portability (PKG-0.4)

**Task:** Verify that A4 preset generalises beyond BTCUSDT to ETH, DOGE, and 1000PEPE (different microstructures).
**Context:** A4 was selected from grid search on BTCUSDT only. Risk: overfitting to BTC's specific
volatility regime in Jan-Mar 2024 (ETF approval period).

**Changes:**
1. `tools/parquet_pipeline/validate_preset.py` (new, ~290 lines):
   - Single-preset multi-symbol runner (no full grid overhead)
   - `_run_symbol()`: per-symbol stress_v0 + aggregation + actuator
   - `_verdict()`: PASS / WARN / FAIL per acceptance thresholds
   - `generate_report()`: cross-symbol table + top-5 switch events per symbol
   - CLI: `python tools/parquet_pipeline/validate_preset.py [--preset A4] [--symbols ...]`
2. `reports/stress_a4_multiasset_report.md` (generated)

**Results (A4, 5m, Jan-Mar 2024):**

| Symbol | /day | STRESS% | Longest run | Verdict |
|--------|------|---------|-------------|---------|
| BTCUSDT | 1.55 | 6.8% | 865 bars | PASS |
| ETHUSDT | 1.57 | 7.0% | 745 bars | PASS |
| DOGEUSDT | 1.39 | 5.4% | 1,169 bars | PASS |
| 1000PEPEUSDT | 1.28 | 4.9% | 1,282 bars | PASS |

**Overall verdict: PORTABLE.**

**Key observations:**
- Meme/high-vol assets (DOGE, 1000PEPE) have FEWER switches than BTC/ETH (1.28-1.39/day vs 1.55-1.57/day)
  — the wide CB window (200 bars) is the main stabiliser across asset classes
- STRESS% is slightly lower for meme assets (4.9-5.4%) vs majors (6.8-7.0%) — expected, as meme assets
  have higher baseline volatility, pushing z-scores above the threshold less frequently relative to their norm
- EXTREME = 0% across all symbols — confirms enter_extreme=0.85 is correctly set for this period

**Acceptance thresholds used:**
- PASS: switches/day ≤ 3.0 AND 2% ≤ STRESS% ≤ 35%
- WARN: switches/day ≤ 5.0 OR STRESS% ≥ 1%

**Conclusion:** A4 is the confirmed foundation preset. Ready for `regime.yaml` update and DM integration.

**Verification:** 53/53 pipeline tests green.

---

## 2026-03-01: Phase 0.3 — Actuator Preset Grid Search (PKG-0.3)

**Task:** Grid-search 6 ActuatorConfig presets on real data to find a "moderate tanker" config.
**Context:** Phase 0.2 baseline (A0) produced 226 switches/90 days (2.5/day). Target: ≤1.5/day
with STRESS% between 5-20% (gate active but not dominant).

**Changes:**
1. `tools/parquet_pipeline/tune_presets.py` (new, ~450 lines):
   - 6 preset definitions (A0–A5) varying enter/exit thresholds, consecutive bars, min_duration, CB window
   - `_collect_result()`: metrics per preset (switches, %NORMAL/STRESS/EXTREME, longest run, top-10 events)
   - `_select_winner()`: primary=switches/day≤1.5 AND secondary=STRESS%∈[5,20]; fallback composite score
   - `generate_report()`: full markdown with comparison table, per-preset detail, top-10 switch timestamps+z-scores
   - CLI: `python tools/parquet_pipeline/tune_presets.py [--symbol --tf --months --output]`
2. `reports/stress_tuning_report.md` (generated):
   - Full grid results for BTCUSDT/5m Jan-Mar 2024

**Key finding — bifurcation at enter_stress 0.60 vs 0.65:**
- Presets at 0.60 threshold: A0 (226/day=2.50), A1 (196/2.16), A4 (140/1.55)
- Presets at 0.65 threshold: A2 (8/0.09), A3 (2/0.02), A5 (2/0.02)
- The aggregation (weighted_vote, current sigma thresholds) rarely produces stress_level > 0.65 outside
  of true extreme events. The 0.60 threshold sits in a churn zone where the signal oscillates.
- Tightening thresholds to 0.65 eliminates almost all switches but makes the gate decorative (0.1% STRESS).

**Winner: A4** — Anti-flip hard (enter=0.60, consecutive_enter=6, min_duration=15, switch_window=200, max_switches=2):
- Switches: 140 (1.55/day) — just barely over target but best in class for STRESS% coverage
- NORMAL: 93.2%, STRESS: 6.8%, EXTREME: 0%
- Longest stable run: 865 bars (~72 hours)
- Top-10 events are verifiable real events (Jan 2-8 2024 BTC ETF volatility)

**Observation for next Phase:** The 0.60 entry threshold is mediocre for churn control at this
sigma/weight setup. Either lower thresholds (so 0.65 produces more STRESS% coverage), or keep 0.60
and rely on CB + min_duration for inertia (A4 approach). A4 is the correct starting config.

**Verification:** 53/53 pipeline tests green.

---

## 2026-03-01: Phase 0.2 — Stress State Actuator (PKG-0.2)

**Task:** Phase 0.2 — aggregation (z-scores → stress_level) + hysteresis FSM (stress_level → NORMAL/STRESS/EXTREME).
**Context:** Z-scores from Phase 0.1 need to be collapsed into a single composite stress_level,
then run through a deterministic state machine with hysteresis to produce stable state labels.

**Changes:**
1. `tools/parquet_pipeline/aggregation.py` (134 lines):
   - `TRIGGER_MAP`: maps config keys (atr, vol, gap, range, volume, spread, depth) to z-score columns + sigma thresholds
   - `compute_stress_level()`: adds `stress_level` column (0..1) via three aggregation methods:
     - `weighted_vote`: binary fire per trigger (z > sigma), then weighted sum
     - `k_of_n`: count firing triggers / k, clamped to [0, 1]
     - `max`: max exceedance ratio (z/sigma), clamped to [0, 1]
2. `tools/parquet_pipeline/actuator_rules.py` (183 lines):
   - Pure, deterministic, O(n) hysteresis FSM
   - `StressState` enum: NORMAL, STRESS, EXTREME
   - `ActuatorConfig` frozen dataclass: enter/exit thresholds, consecutive-bar confirmation,
     min_duration, circuit breaker (switch_window_bars, max_switches_per_window)
   - `run_actuator()`: returns `ActuatorResult` with per-bar state, why (<=80 chars), switches_cumulative
3. `tools/parquet_pipeline/__main__.py` (expanded to 422 lines):
   - `--emit-state` CLI flag
   - Default config fallbacks: `_DEFAULT_THRESHOLDS`, `_DEFAULT_WEIGHTS`, `_DEFAULT_ACTUATOR`
   - Config extraction: `_extract_thresholds()`, `_extract_aggregation()`, `_extract_actuator_config()`
   - State summary: total switches, state distribution %, longest stable run
   - New artifact: `stress_state_timeseries.parquet` (timestamp, stress_level, state, why, switches_total)
   - Provenance includes `state_computed` flag
4. `tools/parquet_pipeline/stress.py` (z-score no-lookahead fix):
   - Added `.shift(1)` on `rolling_mean/std` baseline so bar t uses `[t-window..t-1]` only
   - Docstring updated to reflect shifted rolling
5. `tests/test_stress_actuator.py` (22 tests):
   - Aggregation: weighted_vote (all/none/partial fire), k_of_n (exceed/below k), max, no_active_triggers
   - Actuator: pure_normal, normal→stress, hysteresis holds, consecutive resets, min_duration,
     stress→extreme, extreme→stress, full cycle, circuit breaker, empty input, cumulative switches, why<=80
   - CLI: --emit-state produces parquet + summary with state section
6. `tests/test_parquet_pipeline.py`: +1 test (no-lookahead z-score), now 31 tests

**Real-data validation (BTCUSDT/5m Jan-Mar 2024, 26,088 bars):**
- Total switches: 226 (~2.5/day)
- NORMAL: 23,609 bars (90.5%), STRESS: 2,479 bars (9.5%), EXTREME: 0 bars (0.0%)
- Longest stable run: 626 bars (NORMAL, ~52 hours)
- **NOTE:** 226 switches is in the low-hundreds range. Current `regime.yaml` defaults
  (consecutive_bars_enter=3, min_duration_bars=5, switch_window_bars=50) produce moderate
  stability. For "tanker" behavior, consider increasing consecutive_bars_enter to 5-6
  or min_duration_bars to 10-15. This is a config tuning decision, not a code issue.

**Verification:** 53/53 pipeline tests green (31 Phase 0.1 + 22 Phase 0.2). 225/225 config regression green.

---

## 2026-03-01: Phase 0.1 — Parquet Audit + Stress v0 Pipeline (PKG-0.1)

**Task:** Phase 0.1 — offline Polars-native pipeline for data audit + stress metric extraction.
**Context:** No tooling existed to validate parquet data quality or compute stress baselines
for threshold calibration. Backtest engine loads raw data with no pre-flight check.

**Decision:** New `tools/parquet_pipeline/` module (CLI: `python -m tools.parquet_pipeline`).
NOT modifying backtest engine or domain code — pure offline tooling.

**Changes:**
1. `tools/parquet_pipeline/__init__.py`: Package marker.
2. `tools/parquet_pipeline/discovery.py` (78 lines):
   - `discover_files()`: find parquet files matching backtest engine's search logic
   - `DEFAULT_RENAME = {"open_time": "timestamp"}`: column mapping at tool layer
   - `parse_tf_minutes()`: parse "5m"/"1h"/"1d" to minutes
3. `tools/parquet_pipeline/audit.py` (161 lines):
   - Schema check (6 canonical OHLCV columns after rename)
   - Null counts, duplicate timestamps, time-gap detection (>1.5x interval)
   - OHLCV semantic invariants (high>=low, volume>=0)
   - Value ranges
4. `tools/parquet_pipeline/stress.py` (115 lines):
   - `compute_stress_v0()`: log_return, realized_vol (rolling std), ATR (rolling mean of TR),
     gap (inter-bar), bar_range (normalized)
   - Z-scores with `min_periods=1` for partial-window ramp-up
   - inf/NaN z-score cleanup (div-by-zero when std=0)
   - Burn-in row drop via `with_row_index()` filter
5. `tools/parquet_pipeline/__main__.py` (199 lines):
   - CLI: `--symbol`, `--tf`, `--months`, `--audit-only`, `--window`, `--burn-in`
   - Optional config loading from `system_stress` section (fallback: window=100, burn_in=120)
   - Outputs: `audit_report.json`, `stress_timeseries.parquet`, `stress_summary.md`, `provenance.json`
6. `tests/test_parquet_pipeline.py` (30 tests):
   - Discovery: enriched preference, month filter, klines fallback, not-found
   - Audit: valid data, missing cols, nulls, duplicates, gaps, semantics, value ranges
   - Stress: output columns, burn-in, log_return, bar_range, atr, gap, z-score finiteness
   - CLI: audit-only, full pipeline, not-found, month filter

**Real-data validation:** BTCUSDT/5m Jan-Mar 2024 (26,208 bars):
- Audit: 0 gaps, 0 duplicates, all semantics clean
- Z-scores: z_realized_vol max=9.14, z_gap max=9.87 (extreme events correctly detected)

**Verification:** 30/30 new tests green. 225/225 config regression tests green.

---

## 2026-03-01: FIX-DELETED-TOOLS-TESTS-P1 — Restore green config regression

**Task:** Fix 2 pre-existing failing tests referencing deleted/moved tools.
**Context:** `tools/auroractl.py` was moved to `tools/cli/auroractl.py` but tests still
referenced old path. `tools/autofill_config_defaults_into_yaml.py` was deleted with no
replacement; its test was dead.

**Path chosen:** B (update/remove tests to match current tooling).

**Changes:**
1. `tests/config/test_config_strategy_ssot_freeze.py`: Updated `test_auroractl_provenance_stage_is_strategy`
   - `tools/auroractl.py` → `tools/cli/auroractl.py` (moved path)
   - `python3` → `sys.executable` (Windows compat)
2. `tools/cli/auroractl.py`: Fixed `PROJECT_ROOT = parents[1]` → `parents[2]`
   (bug introduced when file moved from `tools/` to `tools/cli/` — path depth changed)
3. `tests/config/test_optional_required_null_autofill.py`: **Removed** (dead test,
   `tools/autofill_config_defaults_into_yaml.py` was deleted with no replacement)

**Why not shims (Path A)?** Creating stub scripts to make dead-tool tests pass would be
creating dead code to pass dead tests. The autofill workflow no longer exists. The auroractl
tool exists at a new path — updating the reference is the correct fix.

**Verification:** `pytest tests/config/ -v` → 225 passed, 3 skipped, 1 deselected, **0 failed**.

---

## 2026-03-01: Phase 0.0A — system_stress SSOT config (PKG-0.0A)

**Task:** Phase 0.0 — System Stress Guard config + Pydantic models
**Context:** Adding independent circuit-breaker overlay (NORMAL/STRESS/EXTREME) for DM gating.
NOT a replacement for TREND/MR regimes — orthogonal guard layer.

**Decision:** NOT creating parallel `regime_foundation/` domain. Additive section in existing
`regime.yaml` SSOT + models in existing `config_models.py`. Avoids config drift, duplicate
loader paths, terminology fragmentation.

**Changes:**
1. `config/aurora/regime.yaml`: +44 lines (`system_stress` section, `enabled: false` by default)
2. `apps/reference/config_models.py`: +205 lines (5 Pydantic models with cross-validators)
   - `SystemStressThresholdsConfig` (7 sigma triggers, orderbook-gated)
   - `SystemStressAggregationConfig` (weighted_vote/k_of_n/max, strict key validation)
   - `SystemStressStateMappingConfig` (hysteresis ordering invariants)
   - `SystemStressConfig` (top-level with rolling/expanding baseline, burn_in, sources_enabled)
3. `AuroraConfig.system_stress: Optional[SystemStressConfig] = None` (backward compatible)
4. `tests/config/test_system_stress_config.py`: 33 tests (unit + ConfigLoader integration)

**Verification:** 33/33 new tests green. 224/224 config regression tests green (0 new failures).

---

## 2026-03-01: Phase 0.0B — Parquet Data Contract (PKG-0.0B)

**Task:** Fail-fast column/dtype/semantic validation for backtest data
**Context:** No data contract existed — bad parquet files would produce cryptic runtime errors
deep in computation. This tooling catches violations at load time.

**Decision:** Placed in `tools/parquet_contract/` (offline tooling), NOT in a new domain.

**Changes:**
1. `tools/parquet_contract/data_contract.py` (251 lines):
   - `OHLCVContract`: 6 required columns (timestamp, OHLCV)
   - `L2Contract`: 5 required columns (timestamp, bid/ask price/qty)
   - `DataContract.validate_dataframe()`: columns, dtype class (float32/float64 both OK),
     nullability, semantic invariants
   - OHLCV semantics: high >= low/open/close, volume >= 0, timestamp UTC
   - L2 semantics: bid < ask, qty >= 0, timestamp UTC
   - Dtype errors short-circuit before semantics (prevent mixed-type crashes)
2. `tests/test_data_contract.py`: 26 tests

**Verification:** 26/26 tests green.

---
## 2026-01-30: DM QoS P2-Lite Purge and Wiring Audit

**Task:** DM_QOS_P2_LITE_PURGE_AND_WIRING_AUDIT
**Context:** Audited DecisionMaking QoS logic to reduce cognitive load and verify "Exposure Block" feature status without full refactor.

**Findings:**
1. **Dead Code Confirmed:** `_check_qos_rules` was strictly unreachable (0 callsites).
2. **Missing Wiring:** `_handle_exposure_block` is UNWIRED (no event listener calls it). It also contains a SPLIT-BRAIN BUG (writes to flat key, read by partitioned query). "Global Exposure Block" logic is effectively non-existent despite config presence.
3. **P2-Lite Action:**
    - **DELETED** `_check_qos_rules`.
    - **ANNOTATED** `_handle_exposure_block` with failure warning/TODO.
    - **VERIFIED** QoS tests pass.

## 2026-01-30: DM_SAFETY_BYPASSES_P1 — Critical Security Hardening

**Task:** DM_SAFETY_BYPASSES_P1
**Context:** Identified and fixed two critical security vulnerabilities in the `decision_making` domain.

**Vulnerabilities Fixed:**
1. **Hardcoded safety gates bypass:** `apply_safety_gates = str(strategy_id) == "aurora"` allowed any non-Aurora strategy to bypass directional sanity and price motion gates.
2. **Fail-open exposure cache:** Missing/stale/error cache conditions allowed trades, violating fail-closed principle.

**Changes:**
1. `decision_making.py`: Safety gates now read from `strategies.<id>.safety_gates.enabled` config. Missing config → FAIL-CLOSED (NRR-054).
2. `decision_making.py`: Exposure cache precheck now returns `False` (block) on missing/stale/error (NRR-053).
3. `normalized_reject_reasons.py`: Added NRR-053 (EXPOSURE_CACHE_UNAVAILABLE), NRR-054 (CONFIG_SAFETY_GATES_MISSING).
4. `config_models.py`: Added `SafetyGatesConfig` Pydantic model.
5. `aurora.yaml`, `mean_reversion.yaml`: Added explicit `safety_gates.enabled` field.

**Risk Note — Mean Reversion safety_gates.enabled=false:**
MR intentionally trades against trend (counter-trend), so directional sanity and price motion gates are DISABLED.
**Alternative guards protecting MR:**
- Regime gating: MR only trades in FLAT regimes (`allowed_regimes`).
- Bollinger Band boundaries: BB upper/lower provide entry structure.
- ATR-based stops: `sl_atr_mult` prevents runaway losses.
- Per-asset `max_risk_score` filtering in Phase 3+.

**P2 TODO:** Consider `safety_gates.profile: "counter_trend"` to formalize MR-specific gate logic (e.g., require oversold/overbought RSI instead of trend confirmation).

**Verification:**
- NRR-053/054 uniqueness confirmed.
- All strategy YAMLs updated.
- 22/22 tests passed.


## 2026-01-08: VF-DICT Forensics (Global/Domain Dictionaries)

**Task:** VF-DICT-FORENSIC (01..05)
**Context:** Investigate vFoundation Global/Domain Dictionaries as governance SSOT (op/verb/TTL/security/routing) and prove how/if they are used by runtime vs tooling.

**Outcome (facts):**
1. **Inventory:** Dictionary artifacts exist in three layers: global dictionaries (`global_v2_2*.yaml`), domain dictionaries (`vfoundation/dictionaries/domains/domain_*.yaml`), and app domain metadata (`apps/reference/domains/**/domain_dict.json`).
2. **Runtime usage:** vFoundation runtime does not parse these dictionary YAML files; enforcement currently lives in code (Message op allowlist, TTL range + expiry, signature required for DEC/CMD, NO_ROUTE for unknown handlers).
3. **CLI usage:** `vfound dict --global` only checks dictionary file existence (no content parsing).
4. **Data quality:** `vfoundation/dictionaries/global_v2_2_framework.yaml` contains a markdown code-fence and is not valid YAML for parsing; this is currently harmless because it's not parsed.

**Reports:**
- `reports/VF-DICT-FORENSIC-01.md` — inventory, validity, duplication signals
- `reports/VF-DICT-FORENSIC-02.md` — proven code/CLI references
- `reports/VF-DICT-FORENSIC-03.md` — where runtime validation lives today
- `reports/VF-DICT-FORENSIC-04.md` — Aurora event-space vs dictionary declarations (OP-level)
- `reports/VF-DICT-FORENSIC-05.md` — Option A/B/C evolution menu (no implementation)

## 2026-01-08: Config Contract Ghost Rejections Eliminated

**Task:** TASK-CFG-REJECT-INTEGRATE-01
**Context:** Previous forensic analysis revealed that `ConfigContractError` exceptions (raised when strictly typed config is missing or invalid) were being caught and logged but did not emit standard rejection events. This created "ghost" failures where the system would silently stop trading on a symbol without a trace in the event bus or order logs.

**Changes:**
1.  **NRR Integration:** Added `NRR-CFG-001` (MISSING) and `NRR-CFG-002` (INVALID) to `NormalizedRejectReasons`.
2.  **Strategy Gateway:** Modified `_on_strategy_signal_gateway` in `DecisionMaking` to emit `EVT:TRADE_INTENT_REJECTED` when a config contract violation occurs.
3.  **Feature Engine:** Modified `on_features` to emit `EVT:DECISION_BLOCKED` (new health event) when config errors prevent feature calculation.
4.  **Verification:** Updated `test_config_contract_block_normalization.py` to verify event emission.

**Outcome:**
All configuration-related trading blocks are now observable in the event stream. The "Ghost" class of errors has been eliminated.
- **2026-01-08:** Synced `EVT:DECISION_BLOCKED` to new SSOT `docs/FSM_EVENT_MAP.md` and added `decision_blocked_total` metric.
- **2026-01-08:** Deleted dead legacy spot `AccountObserver` domain (reachability=0 for Futures, unwired from main.py).
- **2026-01-08:** Fixed test env: FastAPI missing (installed in .venv but pytest not using it?).

## 2026-01-08: VF-VERB-REG — SSOT Verb Registry (seed + warn-only drift gate)

**Task:** VF-VERB-REG-01/02/03
**Context:** Prepare a single SSOT verb registry seeded from runtime string-scan (no runtime enforcement). Add a warn-only CI gate to surface drift immediately without breaking.

**Changes:**
1. **SSOT registry created:** `apps/reference/dictionaries/verb_registry_v1.yaml` generated from runtime scan (`.py` without `tests/**`).
2. **Warn-only gate:** `tests/vfoundation/test_verb_registry_warn_only.py` compares runtime scan vs registry and writes diffs into `reports/` without failing on coverage gaps.
3. **Owner labeling (top-N):** marked owner + status for the top-20 most frequent runtime tokens; schema is populated only when an exact `<verb_lower>_v1.json` exists (otherwise `null`).

**Reports:**
- `reports/VF-VERB-REG-01.md` — seed generation summary
- `reports/VF-VERB-REG-02.md` + `reports/VF-VERB-REG-02_diff.json` — warn-only drift output
- `reports/VF-VERB-REG-03.md` — owner labeling summary

**Non-goals (explicit):** no runtime deny/allow by verb; no attempt to extract registry from `Router.register` (not used in prod wiring).

## 2026-01-08: VF-VERB-REG-04/05 — Owner inference report + coverage threshold

**Task:** VF-VERB-REG-04/05
**Context:** Speed up cleanup of `owner: unknown` with evidence-based path heuristics (no auto-changes). Tighten drift gate so it fails only once coverage is basically complete.

**Changes:**
1. **Owner inference report (no autofix):** Added `tests/vfoundation/test_verb_owner_inference_report.py` which scans runtime `.py` (no tests), aggregates occurrences per file and per `apps/reference/domains/<X>/` bucket, and suggests owner only when ≥70% of occurrences land in one domain.
2. **Artifacts:** Writes `reports/VF-VERB-REG-04_owner_suggestions.json` and `reports/VF-VERB-REG-04.md`.
3. **Coverage gate policy:** Updated `tests/vfoundation/test_verb_registry_warn_only.py` to fail only if `coverage >= 98%` AND `runtime_not_in_registry > 0` (until then it stays warn-only).

## 2026-01-08: VF-VERB-REG-06 — Apply owner suggestions (>=70%)

**Task:** VF-VERB-REG-06
**Context:** Apply evidence-based owner suggestions to reduce `owner: unknown` without guesses.

**Changes:**
- Updated `apps/reference/dictionaries/verb_registry_v1.yaml` by changing **only** `owner` for entries where current owner was `unknown` and inference confidence was ≥70%.
- Regenerated VF-VERB-REG-04 reports after the update.

**Artifacts:**
- `reports/VF-VERB-REG-06_applied.json` — applied changes with confidence + evidence
- `reports/VF-VERB-REG-06.md` — short summary
- **2026-01-08:** Validated and Frozen 'Alpha Search' domain (Task ALPHA-FREEZE-01/02). Added determinism tests, safe metrics, and offline eval script.

## 2026-01-08: AGENT-NAV-VERB-REG-01 — Agent Navigation Playbook (registry-first)

**Task:** AGENT-NAV-VERB-REG-01
**Context:** After establishing SSOT for system language (Verb Registry) and governance dictionaries, we need an explicit, contract-first navigation instruction for Copilot/LLM agents.

**Changes:**
- Added a strict navigation playbook in `docs/AGENT_NAVIGATION_PLAYBOOK.md`.
- Rules are registry-first (`apps/reference/dictionaries/verb_registry_v1.yaml`), owner-boundary (`apps/reference/domains/<owner>/`), and policy-aware (global/domain governance YAML).

**Outcome:**
Copilot/agents now have a single official procedure that forbids guessing verbs/owners and forbids repo-wide wandering without a contract.

## 2026-01-08: Exchange Filters Startup Guard Integration

**Task:** TASK-EXF-IMPLEMENTATION (07..12)
**Context:** Implemented a critical startup guard that validates `config/aurora/instruments.yaml` against real-time exchange constraints (`/fapi/v1/exchangeInfo`). This prevents runtime rejections due to precision mismatches (LOT_SIZE, PRICE_FILTER) or missing filters.

**Changes:**
1.  **Validator Implementation (`validator.py`):**
    *   Added logic to fetch and parse exchange filters (`LOT_SIZE`, `PRICE_FILTER`, `MIN_NOTIONAL`).
    *   Implemented batch fetching (1 request for all symbols) to optimize startup time (~N -> 1 request).
    *   Removed unsafe defaults (e.g., `min_notional=5`) to ensure fail-closed behavior on missing data.
2.  **Configuration (`system.yaml`/`config_models.py`):**
    *   Added `validate_instruments_on_startup` (default: True).
    *   Added `warn_only_filters` (default: False) for Dev/Shadow environments.
3.  **Wiring (`main.py`):**
    *   Integrated validation logic immediately after config loading.
    *   Implemented blocking behavior on CRITICAL mismatches (SystemExit 1).
4.  **Testing:**
    *   Added `tests/contracts/test_exchange_filters_validation.py` (Unit).
    *   Added `tests/integration/test_startup_filters_wiring.py` (E2E Integration).

**Policies:**
*   **Fail-Closed:** In LIVE/TESTNET, any critical filter mismatch blocks startup.
*   **Warn-Only:** Available via config for non-critical environments.

**Artifacts:**
*   `docs/STARTUP_GUARDS.md`: Official documentation of the new guard.

## 2026-01-08: Execution Management (Zombie) Removal

**Task:** EM-ZOMBIE-01
**Context:** Domain `execution_management` was identified as a non-functional stub (not wired, no logic, tests only checking logs). It was creating confusion vs `execution_position` (the real execution domain).

**Changes:**
1.  **Removed:** `apps/reference/domains/execution_management/` and `tests/test_execution_management.py`.
2.  **Refactored:** `apps/reference/main.py` - Renamed log file `domain_execution_management.log` to `domain_execution_position.log` (as it was actually containing ExecPos logs).
3.  **Docs:** Added tombstone in `docs/deprecations/`.

**Validation:**
*   Confirmed 0 functional references in code/config.
*   Verified `main.py` wiring logic remains intact (integration tests passed).
