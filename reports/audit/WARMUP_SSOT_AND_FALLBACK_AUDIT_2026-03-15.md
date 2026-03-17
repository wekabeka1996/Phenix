# WARMUP / BARS / REGIME READINESS — SSOT AND FALLBACK AUDIT
**Date**: 2026-03-15
**Branch**: Phenix_v2
**Auditor**: Principal Configuration & Runtime Contract Auditor
**Scope**: warmup, required_bars, regime warmup, config loading, fallback/default patterns
**Method**: Direct code inspection only — no reliance on prior reports, README, or documentation

---

## 1. EXECUTIVE VERDICT

**Is there a single SSOT for warmup / bars / regime requirements?**

**NO. There are at least three parallel truth layers.**

| Layer | Location | Mechanism |
|---|---|---|
| Layer 1 (primary) | `regime.yaml` + `config_models.py` | Pydantic-validated YAML. The canonical source. |
| Layer 2 (derived) | `strategy_compatibility_matrix.py` | Computed formula with `getattr(…, default)` fallbacks that shadow Layer 1 |
| Layer 3 (hardcoded) | `startup_warmup.py` + `main.py` | Hardcoded integer literals, completely decoupled from config |

**The three layers agree numerically today** because the fallback values in Layer 2 match the YAML values in Layer 1, and because Layer 3's hardcoded 320 exceeds Layer 2's formula of 301. However, they are structurally independent. A YAML change will not automatically propagate to Layer 3. A change to regime.yaml's `atr_sma_length` from 288 to 400 would:
- Fix Layer 1: Pydantic reads 400
- Fix Layer 2 formula: computed result becomes max(192, 14+400-1) = 413
- NOT fix Layer 3: `regime_basis_candles=320` and `_rd_bars_count=320` remain unchanged
- Runtime result: hydration fetches 320 bars but detector needs 413 → **regime detector never becomes fully ready → all strategies blocked forever**

This is a live silent bomb. Not currently triggered, but architecturally inevitable on any significant regime.yaml tuning.

**Fallback drift**: The `getattr(sma_cfg, "sma_long_period", 192) or 192` fallback and companions in `strategy_compatibility_matrix.py` happen to exactly match the YAML today. If the operator changes YAML values, the fallbacks will diverge from YAML truth. There is no enforcement that they remain in sync.

**Most dangerous single location**: `startup_warmup.py` line 221: `regime_basis_candles=320`. This is a bare integer literal with no YAML or Pydantic binding. Operator changes to regime.yaml will not change this. The system will silently under-hydrate.

**Can these cause live bugs (71/301, 51/96, 23/96)?**: Yes, directly. The 301 bars required is correct but it requires 301 5m bars = 25 hours of live data at startup without basis hydration. The observed `71/301` (aurora) and `23/96` (md_amr) patterns from the forensic audit match this exactly: without proper basis seeding, handlers only accumulate real-time bars. The `96` in the original observation was likely a previous hard-coded minimum, since replaced by 301 via the regime warmup formula.

---

## 2. CLAIMED PHILOSOPHY vs REPO REALITY

| Principle | Expected | Actual | Verdict | Evidence |
|---|---|---|---|---|
| No silent fallbacks | All defaults explicit, named, and either Pydantic-typed or logged as contract violations | `getattr(sma_cfg, "sma_long_period", 192) or 192` and 12 other silent getattr fallbacks in strategy_compatibility_matrix.py | **FAIL** | `strategy_compatibility_matrix.py` lines 99–135 |
| Truth lives in YAML + Pydantic | All business-critical numbers come from YAML fields validated by Pydantic models | `regime_basis_candles=320` and `_rd_bars_count=320` are bare integer literals in business logic code | **FAIL** | `startup_warmup.py:221`, `main.py:1365` |
| Business logic must not invent config | Handlers/planners read config, never invent it | startup_warmup.py invents `regime_basis_candles` with no YAML or Pydantic binding | **FAIL** | `startup_warmup.py:221` |
| Required bars formulas must not be duplicated | One formula, one location | Formula exists in strategy_compatibility_matrix.py AND as hardcoded 320 in startup_warmup.py AND as hardcoded 320 in main.py | **FAIL** | Three separate locations compute/assume same number, all differently |
| Dependency contracts must be explicit | Planner uses same truth as handler uses same truth as detector | Planner uses matrix (301), handlers use matrix (301), but hydration (startup_warmup) uses 320 hardcoded | **PARTIAL** | Planner/handler consistent; hydration is not |
| Planner truth matches runtime truth | `basis_required_bars` in planner == gate threshold in handler | Planner builds from matrix = 301. Handler reads matrix = 301. Consistent. BUT: detector is seeded with 320 bars, handler gates on 301. Detached. | **PARTIAL** | `startup_hydration_planner.py` vs `startup_warmup.py:221` |
| Strict Pydantic validation | All config consumed via Pydantic, no dict access | strategy_compatibility_matrix.py uses raw `getattr` bypassing Pydantic field access | **FAIL** | `strategy_compatibility_matrix.py` lines 87–135 |

---

## 3. REQUIRED BARS TRUTH MAP

### 3.1 aurora strategy (profile: aurora_quadratic)

| Element | Value | Source | File | Line |
|---|---|---|---|---|
| Profile function | `_aurora_basis_required_bars(config)` | delegates to `_structural_regime_basis_required_bars` | `strategy_compatibility_matrix.py` | 106–107 |
| Formula | `max(sma_long, atr_period + atr_sma_length - 1)` | regime detector warmup formula | `strategy_compatibility_matrix.py` | 103 |
| sma_long (YAML) | 192 | `regime.yaml → models.sma_trend.sma_long_period` | `config/aurora/regime.yaml` | 32 |
| sma_long (fallback) | 192 | `getattr(sma_cfg, "sma_long_period", 192) or 192` | `strategy_compatibility_matrix.py` | 99 |
| atr_period (YAML) | 14 | `regime.yaml → models.volatility.atr_period` | `config/aurora/regime.yaml` | 40 |
| atr_period (fallback) | 14 | `getattr(vol_cfg, "atr_period", 14) or 14` | `strategy_compatibility_matrix.py` | 100 |
| atr_sma_length (YAML) | 288 | `regime.yaml → models.volatility.atr_sma_length` | `config/aurora/regime.yaml` | 42 |
| atr_sma_length (fallback) | 288 | `getattr(vol_cfg, "atr_sma_length", 288) or 288` | `strategy_compatibility_matrix.py` | 101 |
| **Result** | **301** | max(192, 14+288-1) | computed | — |
| Pydantic model | `SMARegimeModelConfig.sma_long_period: int` (no default), `VolatilityRegimeModelConfig.atr_period: int` (no default), `atr_sma_length: int` (no default) | All mandatory, no Field defaults | `config_models.py` | 1327–1350 |
| Fallback matches YAML? | YES today | coincidence or intent? | — | — |
| Runtime gate threshold | 301 | read from matrix via `get_active_strategy_profile` | `aurora_decision.py` | 253–264 |
| HTF requirements | m15=50, h4=100, d1=200 | `domains.yaml → feature_engineering.pillars.backfill` | `strategy_compatibility_matrix.py` | 119, 125, 131 |
| HTF fallbacks | 50/100/200 | `getattr(backfill_cfg, "m15_candles", 50) or 50` etc. | `strategy_compatibility_matrix.py` | 119–131 |

### 3.2 mean_reversion strategy

| Element | Value | Source | File | Line |
|---|---|---|---|---|
| Formula | `max(min_bars, _structural_regime_basis_required_bars(config))` | regime warmup dominates | `strategy_compatibility_matrix.py` | 209–211 |
| min_bars (YAML) | 25 | `mean_reversion.yaml → strategy.min_bars` | `config/aurora/strategies/mean_reversion.yaml` | 131 |
| min_bars (fallback) | 25 | `getattr(getattr(mr_cfg, "strategy", None), "min_bars", 25) or 25` | `strategy_compatibility_matrix.py` | 210 |
| min_bars (Pydantic) | `MRStrategyParamsConfig.min_bars: int = Field(...)` — no default, mandatory | `config_models.py` | 405 |
| regime warmup | 301 | same formula as aurora | `strategy_compatibility_matrix.py` | 211 |
| **Result** | **301** | max(25, 301) | computed | — |
| Local min_bars gate | 25 | `MeanReversionStrategy.config.min_bars` | `mean_reversion_strategy.py` | 363 |
| Note | MR has TWO bars gates: the handler uses matrix-based 301 via planner BUT the underlying MRStrategy itself also checks `min_bars=25` on each signal | This is a layered check, not a contradiction | `mean_reversion_strategy.py` + `strategy_compatibility_matrix.py` | 363, 209 |

### 3.3 md_amr strategy

| Element | Value | Source | File | Line |
|---|---|---|---|---|
| Formula | `max(96, channel_window_bars, atr_window, atr_stats_window, _structural_regime_basis_required_bars(config))` | regime warmup always dominates | `strategy_compatibility_matrix.py` | 230–235 |
| **96** | HARDCODED — NO YAML SOURCE | bare integer literal, no Pydantic field | `strategy_compatibility_matrix.py` | 231 |
| channel_window_bars (YAML) | 12 | `md_amr.yaml → channel_window_bars` | `config/aurora/strategies/md_amr.yaml` | 8 |
| channel_window_bars (fallback) | 12 | `getattr(md_cfg, "channel_window_bars", 12) or 12` | `strategy_compatibility_matrix.py` | 232 |
| atr_window (YAML) | 14 | `md_amr.yaml → atr_window` | `config/aurora/strategies/md_amr.yaml` | 10 |
| atr_stats_window (YAML) | 64 | `md_amr.yaml → atr_stats_window` | `config/aurora/strategies/md_amr.yaml` | 11 |
| regime warmup | 301 | same formula as aurora | `strategy_compatibility_matrix.py` | 235 |
| **Result** | **301** | max(96, 12, 14, 64, 301) = 301 | computed | — |
| Internal REST hydration | 100 | `_REST_HYDRATION_LIMIT = 100` hardcoded class constant | `md_amr_handler.py` | 100 |
| **STRUCTURAL GAP** | Internal md_amr REST hydration only fetches 100 bars but gate requires 301 | md_amr must rely on EXTERNAL startup basis hydration to clear the 301 gate | `md_amr_handler.py` line 100 vs matrix line 230–235 | |

---

## 4. REGIME WARMUP TRUTH MAP

### 4.1 Where regime warmup bars is defined

| Location | Value | Binding | Status |
|---|---|---|---|
| `regime.yaml → models.sma_trend.sma_long_period` | 192 | Pydantic: `SMARegimeModelConfig.sma_long_period: int = Field(ge=2)` | SSOT Layer 1 |
| `regime.yaml → models.volatility.atr_period` | 14 | Pydantic: `VolatilityRegimeModelConfig.atr_period: int = Field(ge=1)` | SSOT Layer 1 |
| `regime.yaml → models.volatility.atr_sma_length` | 288 | Pydantic: `VolatilityRegimeModelConfig.atr_sma_length: int = Field(ge=10)` | SSOT Layer 1 |
| `strategy_compatibility_matrix._structural_regime_basis_required_bars()` | Computes max(192, 301) = 301 | `getattr` fallbacks (no Pydantic) | LAYER 2 — derived with fallbacks |
| `startup_warmup.resolve_feature_engineering_backfill_plan()` | 320 | HARDCODED integer literal | LAYER 3 — independent |
| `main.py` line 1365 | 320 | HARDCODED integer literal + comment | LAYER 3 — independent |

### 4.2 RegimeDetector's actual warmup requirement

The `RegimeDetector.__init__()` allocates:
```python
self._price_buf[symbol] = deque(maxlen=max(sma_short_period, sma_long_period))  # max(48, 192) = 192
self._tr_buf[symbol] = deque(maxlen=atr_period)   # 14
self._atr_buf[symbol] = deque(maxlen=atr_sma_length)  # 288
```

To be `full_ready`, the detector needs:
- `sma_long_ready` → 192 bars with valid close prices (from price_buf or feature sma_long)
- `atr_baseline_ready` → `atr_sma_length=288` ATR values → requires `atr_period + atr_sma_length - 1 = 301` bars

**RegimeDetector actual minimum for `full_ready`: 301 bars**

This is what `_structural_regime_basis_required_bars()` computes. The formula is correct.

The startup hydration gives 320 bars (19 buffer beyond minimum). That's fine.

### 4.3 Separation of concern violations

**Strategy-local required bars**: Bars needed by the strategy's own indicator windows.
- aurora: none directly (it delegates to regime bars)
- mean_reversion: `min_bars=25` (bb_window + buffer)
- md_amr: `channel_window_bars=12`, `atr_window=14`, `atr_stats_window=64`

**Foundational dependency bars (regime)**: Bars needed for the global regime detector.
- Same for all regime-dependent strategies: 301 (from `_structural_regime_basis_required_bars`)

**Hydration planner bars**: The number passed to hydration executor.
- Comes from `StrategyHydrationRequirement.basis_required_bars` = same as matrix (301)
- This is for the strategy handler's cold-start counter seed

**Regime detector hydration bars**: Bars fetched to seed the regime detector itself.
- `regime_basis_candles=320` in `startup_warmup.py` line 221
- `_rd_bars_count=320` in `main.py` line 1365
- **THESE ARE INDEPENDENT FROM THE MATRIX AND FROM EACH OTHER**

**Handler readiness gate bars**: The threshold checked in `aurora_decision.py` and `md_amr_handler.py`.
- Both read from `get_active_strategy_profile(config, strategy_id).basis_required_bars` → matrix → 301

**Conclusion**: Planner bars (301) and handler gate bars (301) are consistent. Regime detector hydration bars (320) exceed the minimum (301) but are architecturally disconnected.

---

## 5. CONFIG LOADER FALLBACK AUDIT

All findings from `config_loader.py`:

| Pattern | Location | Classification | Notes |
|---|---|---|---|
| `_resolve_mode_overrides()` — applies `decision.{mode}.*` overrides | `config_loader.py:493–576` | SANCTIONED_COMPATIBILITY | Documented, intentional, logged at INFO |
| Backtest force when either source says backtest | `config_loader.py:1009–1019` | SILENT_POLICY_OVERRIDE | Documented in comment, but no hard fail. Warning logged only. |
| Hybrid mode SSOT wiring (`_ensure_domain` calls) | `config_loader.py:536–556` | LEGACY_COMPAT | Code-level truth injection for domain modes. Not in YAML. Commented as "TASK28: Keep in loader" — intentional. |
| `domains.yaml` optional loading | `config_loader.py:879–884` | SAFE_TYPED_DEFAULT | If domains.yaml missing, uses `{}`. Pydantic will catch missing required fields. |
| `trading_block["mode"] = root_mode` when only root set | `config_loader.py:1031–1032` | SANCTIONED_COMPATIBILITY | Propagates root truth to trading block. Logical. |
| `config.get("trading_mode", "production")` in `_resolve_mode_overrides` | `config_loader.py:504` | SAFE_TYPED_DEFAULT | Fallback to "production" only for override resolver; actual trading_mode is validated later |

**Summary for config_loader**: The loader is largely clean. The hybrid-mode domain injection (`_ensure_domain`) is the most notable code-level truth beyond YAML, but it's intentional and documented. No silent bars/warmup/regime overrides found in the loader.

---

## 6. RUNTIME FALLBACK AUDIT

### HIGH_RISK_SILENT_TRUTH (highest severity)

| File | Line | Pattern | Value | Risk |
|---|---|---|---|---|
| `strategy_compatibility_matrix.py` | 99 | `getattr(sma_cfg, "sma_long_period", 192) or 192` | 192 | If sma_cfg is None (config path failure), silently uses 192. Formula result changes silently. |
| `strategy_compatibility_matrix.py` | 100 | `getattr(vol_cfg, "atr_period", 14) or 14` | 14 | Same. |
| `strategy_compatibility_matrix.py` | 101 | `getattr(vol_cfg, "atr_sma_length", 288) or 288` | 288 | Same. Most critical: this drives the `301` result. If vol_cfg is None, result = max(192, 14+288-1) = 301 (matches YAML). But if YAML changes and vol_cfg somehow resolves stale, drift. |
| `startup_warmup.py` | 221 | `regime_basis_candles=320` | 320 | Bare integer literal. No YAML, no Pydantic, no config binding. If regime.yaml atr_sma_length changes, this stays at 320. Could under-hydrate. |
| `main.py` | 1365 | `_rd_bars_count = 320  # 288 atr_sma_length + 32 buffer` | 320 | Same as above, duplicated in second code path in main.py. Two places to fix if config changes. |

### SILENT_RUNTIME_FALLBACK (medium-high severity)

| File | Line | Pattern | Value | Risk |
|---|---|---|---|---|
| `strategy_compatibility_matrix.py` | 119 | `getattr(backfill_cfg, "m15_candles", 50) or 50` | 50 | If FE pillars config missing, silently falls back |
| `strategy_compatibility_matrix.py` | 125 | `getattr(backfill_cfg, "h4_candles", 100) or 100` | 100 | Same |
| `strategy_compatibility_matrix.py` | 131 | `getattr(backfill_cfg, "d1_candles", 200) or 200` | 200 | Same |
| `strategy_compatibility_matrix.py` | 172 | `getattr(aurora_cfg, "timeframe_sec", 300) or 300` | 300 | If aurora config missing, silently uses 5m |
| `strategy_compatibility_matrix.py` | 208 | `getattr(mr_cfg, "timeframe_sec", 300) or 300` | 300 | Same for MR |
| `strategy_compatibility_matrix.py` | 229 | `getattr(md_cfg, "timeframe_sec", 900) or 900` | 900 | Same for md_amr |
| `strategy_compatibility_matrix.py` | 232 | `getattr(md_cfg, "channel_window_bars", 12) or 12` | 12 | md_amr channel window fallback |
| `strategy_compatibility_matrix.py` | 233 | `getattr(md_cfg, "atr_window", 14) or 14` | 14 | md_amr atr window fallback |
| `strategy_compatibility_matrix.py` | 234 | `getattr(md_cfg, "atr_stats_window", 64) or 64` | 64 | md_amr stats window fallback |
| `startup_warmup.py` | 218 | `getattr(backfill_cfg, "d1_candles", 200) or 200` | 200 | Duplicates the matrix fallback |
| `startup_warmup.py` | 219 | `getattr(backfill_cfg, "h4_candles", 100) or 100` | 100 | Same |
| `startup_warmup.py` | 220 | `getattr(backfill_cfg, "m15_candles", 50) or 50` | 50 | Same |
| `md_amr_handler.py` | 206 | `return int(self._cfg.timeframe_sec) if self._cfg is not None else 900` | 900 sentinel | If cfg is None (init failed), property returns 900. Callers see a valid timeframe but strategy is broken. |
| `safety_gates.py` | 449 | `getattr(ds_cfg, 'min_regime_confidence', 0.0)` | 0.0 | If field missing from Pydantic model, regime confidence gate is silently disabled |
| `safety_gates.py` | 306 | `getattr(sg_cfg, "system_stress_policy", "off")` | "off" | If field missing, stress policy silently set to off |
| `safety_gates.py` | 309 | `getattr(sg_cfg, "stress_attenuation_factor", 0.5)` | 0.5 | Same |

### LEGACY_COMPAT (lower severity, gated or justified)

| File | Lines | Pattern | Classification | Notes |
|---|---|---|---|---|
| `aurora_config_loader.py` | 156–168 | All `getattr(decision, "...", default)` calls | LEGACY_COMPAT | Explicitly gated: `if not self._strict_pydantic_config`. Strict path (production) hard-fails instead. |
| `aurora_config_loader.py` | 254–256 | `neutral_threshold` fallback to `Decimal("0.05")` | LEGACY_COMPAT | Not gated but low business impact |
| `strategy_compatibility_matrix.py` | 231 | `96` hardcoded minimum for md_amr | LEGACY_COMPAT (dead) | 96 is always overridden by 301 from regime warmup. Dead code that causes confusion. |
| `strategy_compatibility_matrix.py` | 210 | `getattr(…, "min_bars", 25) or 25` | LEGACY_COMPAT | 25 is always overridden by 301. Low risk. |

### NONCRITICAL_HELPER or TEST_ONLY

| File | Pattern | Classification |
|---|---|---|
| `aurora_config_loader.py` | `direction_strength_cfg.strength_alpha = 0.5 if ds_cfg else 0.5` | NONCRITICAL_HELPER |
| `aurora_config_loader.py` | `holding_period_enabled = False` when hp_cfg disabled | SAFE_TYPED_DEFAULT |
| `aurora_config_loader.py` | `anti_churn_enabled = False` / `time_multipliers = {}` | SAFE_TYPED_DEFAULT |

---

## 7. SILENT TRUTH RISK RANKING

Ranked by severity (highest = most dangerous live impact):

### RANK 1 — CRITICAL
**`startup_warmup.py:221` — `regime_basis_candles=320` hardcoded**

- Impact: If `atr_sma_length` in regime.yaml is raised above 306 (making regime warmup require > 320 bars), startup hydration will silently under-hydrate. RegimeDetector will not fully warm up. All regime-dependent strategies will block forever at cold-start.
- Currently: 320 > 301 — safe by 19 bars buffer
- YAML change risk: HIGH — regime.yaml is tuned regularly (see recent change from atr_sma_length=100 to 288)
- No Pydantic field. No config binding. No formula. Pure assumption.

### RANK 2 — CRITICAL
**`main.py:1365` — `_rd_bars_count = 320` second duplicate**

- Same risk as Rank 1. Two separate code paths both assume 320. If one is fixed, the other may not be.
- The comment `# 288 atr_sma_length + 32 buffer` shows the author knew this was derived from config, but chose a literal instead.

### RANK 3 — HIGH
**`strategy_compatibility_matrix.py:99–101` — `getattr(sma_cfg/vol_cfg, ..., 192/14/288) or 192/14/288`**

- Impact: If `sma_cfg` or `vol_cfg` is None (config resolution failure), the formula uses hardcoded values silently. The matrix computes 301 based on hardcoded fallbacks instead of actual config. Handlers and planner both use the matrix — they would see a valid but wrong `basis_required_bars`.
- The fallbacks happen to match YAML today. If YAML changes, they diverge.
- Under strict Pydantic loading, these paths should rarely be None. But they can be None in tests, in degraded config, or if the loader is bypassed.
- Missing hard-fail if vol_cfg is None.

### RANK 4 — HIGH
**`strategy_compatibility_matrix.py:119,125,131` and `startup_warmup.py:218–220` — HTF candle count fallbacks**

- Duplicated fallbacks for m15_candles/h4_candles/d1_candles in two places.
- The matrix and the warmup planner both independently read these with the same `or 50/100/200` fallbacks.
- If domains.yaml is partially missing, both silently use defaults. No hard-fail.

### RANK 5 — MEDIUM
**`safety_gates.py:449` — `min_regime_confidence` silent fallback to 0.0**

- Regime confidence gate is silently disabled if config key is missing.
- If operator intends to require minimum regime confidence but mistypes the key name, the gate is silently bypassed.
- Impact: entries in uncertain/low-confidence regimes allowed through without warning.

### RANK 6 — MEDIUM
**`md_amr_handler.py:100` — `_REST_HYDRATION_LIMIT = 100` vs required 301**

- md_amr internal REST hydration only fetches 100 bars.
- The handler gate requires 301 bars to clear.
- md_amr must rely entirely on the external startup basis hydration (from the planner/executor) to seed its counter via `seed_startup_bars()`.
- If external seeding is skipped or fails, md_amr internal hydration alone cannot clear the gate.
- This is a structural dependency that is not documented in the handler itself.

### RANK 7 — LOW (gated/dead)
**`strategy_compatibility_matrix.py:231` — `96` hardcoded minimum for md_amr**

- Dead code: always overridden by 301.
- Misleading: suggests md_amr needs 96 bars but this is the old pre-regime requirement.
- No YAML or Pydantic source.

---

## 8. ARCHITECTURAL JUSTIFICATION ANALYSIS

### `getattr(sma_cfg, "sma_long_period", 192) or 192` (and `atr_period`/`atr_sma_length` siblings)

**Justified?** NO.

**Why not**: When config is properly loaded via Pydantic (`AuroraConfig`), `sma_cfg` is a `SMARegimeModelConfig` instance with `sma_long_period: int = Field(ge=2)` — no default. Pydantic validates it exists. Using `getattr` with a fallback here means:
1. The fallback can never trigger in production (Pydantic already guaranteed the field exists)
2. The fallback CAN trigger when config is partially loaded (tests, bypassed loader, config bugs)
3. When it triggers, it silently uses stale values instead of failing closed

**What contract should replace it**: Direct attribute access. If `sma_cfg` is None, hard-fail. If `sma_cfg.sma_long_period` is invalid, Pydantic already caught it. The function should be:
```python
def _structural_regime_basis_required_bars(config: Any) -> int:
    regime_cfg = getattr(config, "regime", config)
    models_cfg = regime_cfg.models  # Will raise AttributeError if not present — GOOD
    sma_long = int(models_cfg.sma_trend.sma_long_period)
    atr_period = int(models_cfg.volatility.atr_period)
    atr_sma_length = int(models_cfg.volatility.atr_sma_length)
    return max(sma_long, atr_period + atr_sma_length - 1)
```

### `regime_basis_candles=320` in `startup_warmup.py`

**Justified?** NO.

**Why not**: 320 is derived from config (`atr_sma_length=288 + atr_period=14 - 1 = 301` rounded up to 320). But the code hardcodes the derived value instead of computing it. The comment in `main.py:1365` says `# 288 atr_sma_length + 32 buffer` — showing the author knew this was config-derived but embedded it anyway.

**What contract should replace it**: `FeatureEngineeringBackfillPlan.regime_basis_candles` should call `_structural_regime_basis_required_bars(config) + buffer_bars`, where `buffer_bars` is a configurable or at minimum a named constant (e.g., `_REGIME_HYDRATION_BUFFER = 19`).

### `96` hardcoded in md_amr profile

**Justified?** NO — it's dead code.

**Why not**: `max(96, 12, 14, 64, 301) = 301`. The 96 never wins. It was presumably set when regime warmup wasn't factored in. Now that `_structural_regime_basis_required_bars` always returns 301, the 96 is invisible. But it adds confusion and has no YAML source.

**What contract should replace it**: Remove 96 entirely, or if a true md_amr-local minimum exists, add it as a YAML field: `md_amr.yaml → min_warmup_bars: <value>`.

### Legacy non-strict path in `aurora_config_loader.py`

**Justified?** YES — explicitly gated.

**Why**: The `if not self._strict_pydantic_config:` gate ensures the fallback defaults only apply when loading partial/mock configs (test environments). In production (`_strict_pydantic_config=True`), any missing field raises `ConfigContractError`. This is a correct two-path design.

**Should be left as-is**. The explicit gate is the contract.

### `_REST_HYDRATION_LIMIT = 100` in md_amr_handler

**Justified?** Partially — but the dependency is undocumented.

**Why partial**: md_amr's internal REST hydration is for warming up the strategy's own internal buffers (channel_window=12, atr_window=14). 100 bars is sufficient for that. The 301-bar gate is a separate concern handled by external startup seeding. But this dependency is not documented in the handler code.

**What contract should replace it**: Add a class docstring or comment that explicitly states: "_REST_HYDRATION_LIMIT covers only internal state warmup (max 64 bars needed). Cold-start 301-bar gate requires external seed_startup_bars() call from startup executor."

### `system_stress_policy` / `stress_attenuation_factor` fallbacks in safety_gates.py

**Justified?** PARTIALLY — these have YAML definitions.

**Verification**: `safety_gates:` → `system_stress_policy:` exists in `mean_reversion.yaml:38`. If the field is in YAML and Pydantic validates it, the getattr fallback is redundant. If Pydantic does not have this field, the fallback silently bypasses it.

**Without checking Pydantic model for this specific field**: The fallback to `"off"` for stress policy means the gate is silently disabled if config is missing. This is fail-open for stress protection, not fail-closed.

---

## 9. EXACT FIXES RECOMMENDED

### FIX-WARMUP-01: Bind `regime_basis_candles` to config formula [CRITICAL]

**File**: `apps/reference/bootstrap/startup_warmup.py` line 221
**Current**: `regime_basis_candles=320,`
**Required**: Compute from config: `_structural_regime_basis_required_bars(config) + 19` (or a named buffer constant), OR add a YAML field `regime.warmup_buffer_bars: 19` and read it.

This must be done in `resolve_feature_engineering_backfill_plan(config)` which already accepts `config` as parameter — the fix requires no signature change.

### FIX-WARMUP-02: Remove duplicate `_rd_bars_count = 320` in main.py [CRITICAL]

**File**: `apps/reference/main.py` line 1365
**Current**: `_rd_bars_count = 320  # 288 atr_sma_length + 32 buffer`
**Required**: Replace with call to same helper: `_rd_bars_count = _structural_regime_basis_required_bars(config) + 19`
OR: better, import and use `FeatureEngineeringBackfillPlan.regime_basis_candles` from the backfill plan already computed earlier.

### FIX-WARMUP-03: Remove fallbacks from `_structural_regime_basis_required_bars` [HIGH]

**File**: `apps/reference/contracts/strategy_compatibility_matrix.py` lines 87–103
**Current**: All three `getattr(..., default) or default` patterns
**Required**: Direct attribute access. If config tree is properly loaded, these will never be None. If they are None, hard-fail at the compatibility matrix level rather than silently computing a plausible-but-wrong number.

Example replacement:
```python
def _structural_regime_basis_required_bars(config: Any) -> int:
    try:
        regime_cfg = getattr(config, "regime", config)
        models_cfg = regime_cfg.models
        sma_long = int(models_cfg.sma_trend.sma_long_period)
        atr_period = int(models_cfg.volatility.atr_period)
        atr_sma_length = int(models_cfg.volatility.atr_sma_length)
        return max(sma_long, atr_period + atr_sma_length - 1)
    except (AttributeError, TypeError) as exc:
        raise ConfigContractError(
            path="regime.models",
            why=f"Regime warmup calculation failed: {exc}. Required fields: models.sma_trend.sma_long_period, models.volatility.atr_period, models.volatility.atr_sma_length"
        ) from exc
```

### FIX-WARMUP-04: Remove dead `96` minimum from md_amr profile [LOW]

**File**: `apps/reference/contracts/strategy_compatibility_matrix.py` line 231
**Current**: `max(96, channel_window_bars, atr_window, atr_stats_window, _structural_regime_basis_required_bars(config))`
**Required**: Remove `96` entirely or add it to `md_amr.yaml` as `min_warmup_bars: 96` (with documentation). The value must have a YAML source if it is to be retained.

### FIX-WARMUP-05: Document md_amr internal hydration gap [MEDIUM]

**File**: `apps/reference/domains/decision_making/md_amr_handler.py` line 100
**Current**: `_REST_HYDRATION_LIMIT = 100` with no context
**Required**: Add explicit comment:
```python
# Internal REST hydration: covers strategy indicator warmup only (max atr_stats_window=64 bars needed).
# The cold-start 301-bar gate (from _structural_regime_basis_required_bars) must be cleared via
# external seed_startup_bars() call from the startup executor (startup_basis_hydrator.py).
_REST_HYDRATION_LIMIT = 100
```

### FIX-WARMUP-06: Add Pydantic field for `min_regime_confidence` in `DirectionalSanityConfig` [MEDIUM]

**File**: `apps/reference/config_models.py` — `DirectionalSanityConfig` class
**Current**: `getattr(ds_cfg, 'min_regime_confidence', 0.0)` in `safety_gates.py` — not in Pydantic model
**Required**: Add `min_regime_confidence: float = Field(default=0.0, ge=0.0, le=1.0)` to `DirectionalSanityConfig`. Then the field is Pydantic-validated and the `getattr` becomes `ds_cfg.min_regime_confidence`.

### FIX-WARMUP-07: Unify HTF candle count fallbacks [LOW]

**Files**: `strategy_compatibility_matrix.py` lines 119/125/131 and `startup_warmup.py` lines 218–220
Both compute the same fallbacks for the same config fields. The duplication is structural. Either:
- Factor out into a shared helper function, or
- Ensure both always read from the same `FeatureEngineeringBackfillPlan` struct (already computed by startup_warmup) rather than recomputing independently.

---

## 10. CONFIDENCE AND BLIND SPOTS

### Directly verified (high confidence)
- `strategy_compatibility_matrix.py` — full read, all formulas and fallbacks mapped
- `startup_warmup.py` — `FeatureEngineeringBackfillPlan` and `regime_basis_candles=320`
- `main.py:1365` — `_rd_bars_count = 320`
- `regime.yaml` — all model values (192, 14, 288)
- `config_models.py` — Pydantic models for `SMARegimeModelConfig`, `VolatilityRegimeModelConfig`, `DirectionalSanityConfig`, `MRStrategyParamsConfig`
- `RegimeDetector.__init__` — actual buffer allocation (192, 14, 288 from config)
- `aurora_decision.py` — cold-start bars gate (reads matrix)
- `md_amr_handler.py` — cold-start bars gate, `_REST_HYDRATION_LIMIT=100`, `seed_startup_bars()`
- `aurora_config_loader.py` — legacy path gating
- `mean_reversion_handler.py` — no local cold-start bars gate (relies on FE warmup + startup_warmup_gate)
- `mean_reversion_strategy.py:363` — local `min_bars` check inside MR strategy
- `startup_hydration_planner.py` — correctly consumes matrix profiles
- `config_loader.py` — mode override logic, MODE-SSOT conflict detection

### Uncertain / not fully explored
- `main.py` first hydration path (`startup_warmup:~1160`) — reads `backfill_plan.regime_basis_candles` which IS the hardcoded 320. Not independently computed.
- `aurora_handler.py` full `get_readiness_diagnostics()` implementation — assumed identical to `md_amr_handler.py`
- `domain_config.py` (`DomainConfigResolver`) — not read in detail; may have additional fallbacks
- Whether `_rd_bars_count=320` in main.py is on the same code path as `backfill_plan.regime_basis_candles=320` or a separate path — CRITICAL: if both paths run, bars are hydrated twice (harmless but wasteful); if only one runs, risk of missed hydration
- The exact runtime path for mean_reversion cold-start: whether `startup_warmup_gate_tokens()` vs FE `full_ready` is the operative gate
- Feature engineering warmup details — partial read only; `require_regime_warmup: true` in domains.yaml verified

---

## APPENDIX: KEY NUMBERS REFERENCE

| Number | Origin | Location | Meaning |
|---|---|---|---|
| 192 | `regime.yaml:32` | `models.sma_trend.sma_long_period` | SMA long period for trend detection |
| 48 | `regime.yaml:30` | `models.sma_trend.sma_short_period` | SMA short period |
| 14 | `regime.yaml:40` | `models.volatility.atr_period` | ATR calculation window |
| 288 | `regime.yaml:42` | `models.volatility.atr_sma_length` | ATR baseline SMA length |
| 301 | Computed | `strategy_compatibility_matrix.py:103` | `max(192, 14+288-1)` — regime warmup minimum |
| 320 | Hardcoded | `startup_warmup.py:221`, `main.py:1365` | Regime hydration bars fetched (301 + 19 buffer) |
| 25 | `mean_reversion.yaml:131` | `strategy.min_bars` | MR strategy local bar minimum |
| 96 | Hardcoded | `strategy_compatibility_matrix.py:231` | Dead md_amr floor (always overridden by 301) |
| 64 | `md_amr.yaml:11` | `atr_stats_window` | md_amr ATR stats buffer (overridden by 301) |
| 100 | Hardcoded | `md_amr_handler.py:100` | `_REST_HYDRATION_LIMIT` — internal REST fetch only |
| 301 | Runtime gate | `aurora_decision.py:265`, `md_amr_handler.py:1094` | Cold-start bars_required gate threshold |
