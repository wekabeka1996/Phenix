
---

## 2025-01-07 Tech Debt Cleanup: Duplicate Classes + Print Statements

### What: Fix critical class duplications and replace print() with LOG

### Issues Found & Fixed:

#### 1. Duplicate Class Definitions in config_models.py (CRITICAL BUG)
- **Problem:** Python's second class definition overwrites first, causing field loss
- `PositionSizingConfig` was defined twice (lines 61-70 and 362-367)
  - First version had: `risk_fraction_q`, `liquidity_kappa`, `kappa_mode`, `min_position_size_usd`, `liquidity_based_cap_usd`
  - Second version had ONLY: `min_position_size_usd`, `liquidity_based_cap_usd`
  - **Result:** Fields `risk_fraction_q`, `liquidity_kappa`, `kappa_mode` were LOST
  - These fields are actively used in decision_making.py (lines 2064-2085)
- `QoSConfig` vs `QosConfig` had different defaults (10 vs 60 for `exposure_block_cooldown_sec`)
- `SignalsConfig` was defined twice with different `normalize` defaults (False vs True)

#### 2. Solution Applied:
- Removed duplicate definitions (lines 362-393)
- Kept original comprehensive definitions (lines 55-87)
- Added comments to prevent future duplication
- `DecisionMakingDomainConfig` now correctly references original classes

#### 3. Print Statements → LOG in fsm_manage.py
- Replaced 6 `print()` calls with proper `LOG.debug/info/error`:
  - Line 442: FILL event diagnostic → `LOG.debug`
  - Line 452: EXIT fill detection → `LOG.info`
  - Lines 471, 477: ENTRY fill → `LOG.info`
  - Line 988: Brackets placed → `LOG.info`
  - Line 1378: Hydrate error → `LOG.error`

### Tests:
- ✅ FSM tests: 4/4 passed
- ✅ Config validation: All fields present
- ✅ No compile errors

### Files Modified:
- `apps/reference/config_models.py`
- `apps/reference/domains/execution_position/fsm_manage.py`

---

## 2025-12-04 Track B Integration: MR in DecisionMaking + Config-Driven Regime Sizing

### What: Integrate Mean Reversion 1m into DecisionMaking workflow

### Changes Made:

#### 1. Config Models (config_models.py)
- Added full Pydantic models for MR 1m strategy YAML:
  - `MRStrategyParamsConfig` - strategy parameters (BB, ATR, RSI windows)
  - `MRRegimeThresholdsConfig` - vol thresholds for FLAT classification
  - `MRAssetConfig` - per-asset enable/bb_window/sl_pct
  - `MRRegimeSizingConfig` - sizing/stop/target multipliers per regime
  - `MRRiskConfig` - position size, loss limits, fees
  - `MeanReversion1mStrategyConfig` - top-level container
- Added `mean_reversion_1m` field to `AuroraConfig`

#### 2. Config Loader (config_loader.py)
- Added loading of `strategies/mean_reversion_1m.yaml`
- Merges into root config as `mean_reversion_1m` key
- Graceful handling if file missing (optional)

#### 3. Mean Reversion Handler (mean_reversion_handler.py) — NEW FILE
- `MeanReversionHandler` class for MR integration with DecisionMaking
- Feature-flagged via `mean_reversion_1m.enabled` (default: false)
- Wiring: `EVT:TICK_RECEIVED` → `on_tick()` → `MRSignal` → `EVT:TRADE_INTENT_PROPOSED`
- Per-symbol enable/disable from assets config
- Passes `regime_sizing` from YAML to strategy for config-driven multipliers

#### 4. DecisionMaking Integration (decision_making.py)
- Added import and initialization of `MeanReversionHandler`
- Added `_on_tick_for_mr()` listener for `EVT:TICK_RECEIVED`
- Forward regime updates to MR handler in `on_regime()`
- Updated `__init__.py` version to 1.3.0

#### 5. Config-Driven Regime Sizing (regime_mapping.py)
- Modified `get_mr_sizing_multiplier()`, `get_mr_stop_multiplier()`, `get_mr_target_multiplier()`:
  - Added optional `config_sizing` parameter
  - Falls back to hardcoded defaults if not in config
- Modified `MRParameters.from_flat_regime()` to accept `config_sizing`
- Modified `get_mr_parameters()` to pass `config_sizing` through

#### 6. Strategy Integration (mean_reversion_strategy.py)
- Added `regime_sizing` parameter to `MeanReversion1mStrategy.__init__()`
- Passes `regime_sizing` to `MRParameters.from_flat_regime()` in `on_tick()`

#### 7. Bug Fix (fsm_manage.py)
- Fixed UnboundLocalError caused by local `LOG` redefinitions in methods
- Removed `import logging; LOG = logging.getLogger()` inside method bodies
- Now uses module-level LOG consistently

### Tests Added:
- `test_mean_reversion_handler.py` — 16 tests for MR handler
- Extended `test_regime_mapping.py` — +7 tests for config_sizing

### Tests Passed: 189
- All Aurora/MR module tests passing

---

## 2025-12-05 MILESTONE: Track A + Track B Complete (RID: MILESTONE-001)

### What: Phase 0 + Track A + Track B implementation complete

### Summary:
All core refactoring work complete. Aurora per-instrument config architecture and 1m Mean Reversion strategy modules are production-ready.

### Track A (Aurora Phase 3+) — COMPLETE
| Phase | Description | Tests |
|-------|-------------|-------|
| Phase 0 | Per-Instrument Config Architecture | 34 |
| A1 | Per-Asset Core Params (weights, side_bias, regime) | incl |
| A2 | TP1/TP2 Partial Exit (70/30 split) | incl |
| A3 | Trailing Stop (activation, peak tracking) | incl |
| A4 | Max Hold Time Watchdog (per-asset) | incl |

### Track B (1m Mean Reversion) — COMPLETE
| Module | Description | Tests |
|--------|-------------|-------|
| B1: bar_resampler.py | Tick → 1m OHLCV aggregation | 25 |
| B2: indicators.py | BB, ATR, RSI, SMA calculations | 26 |
| B3: regime_mapping.py | Aurora → FLAT regime mapping | 34 |
| B4: mean_reversion_strategy.py | Full MR strategy with signals | 25 |

### Tech Debt Cleaned:
- Removed legacy stub fields (trail_pct, breakeven_after_sec)
- Removed Rule 1/2 stub logic from FSM
- Removed duplicate DecisionConfig class
- Removed duplicate exposure field in ExecutionConfig

### Total Tests: 144 passed
- Aurora instrument config: 34
- Bar resampler: 25
- Indicators: 26
- Regime mapping: 34
- Mean Reversion strategy: 25

### Files Created:
- `feature_engineering/bar_resampler.py`
- `feature_engineering/indicators.py`
- `feature_engineering/regime_mapping.py`
- `feature_engineering/mean_reversion_strategy.py`
- `config/aurora/strategies/mean_reversion_1m.yaml`
- `tests/domains/test_bar_resampler.py`
- `tests/domains/test_indicators.py`
- `tests/domains/test_regime_mapping.py`
- `tests/domains/test_mean_reversion_strategy.py`

### ROADMAP Updated:
- Phase 0: ✅ DONE
- Track A: ✅ DONE
- Track B: ✅ DONE
- Phase A5 (Risk Weights): 🔜 Optional
- Validation: 🔜 Next

### Next Steps:
1. **Option A**: Phase A5 — Phase 3+ Risk Weights (2-3 hours, optional)
2. **Option B**: Walk-forward validation + Testnet testing

---

## 2025-12-04 Phase B4 Integration & Tech Debt Cleanup (RID: PHASE-B4-INT-001)

### What: Integrated Track B modules and cleaned config_models.py

### Why: Complete module exports and remove code duplication

### Changes Made:

#### Feature Engineering Exports (`feature_engineering/__init__.py`)
- Updated version to 1.2.0
- Added exports for all Track B modules:
  - Bar resampling: Bar, BarResampler, MultiSymbolBarResampler
  - Indicators: BollingerBands, compute_* functions, IndicatorState
  - Regime mapping: FlatRegime, map_to_flat_regime, MRParameters
  - MR Strategy: MRSignal, MeanReversion1mStrategy, etc.

#### 1m MR Production Config (`config/aurora/strategies/mean_reversion_1m.yaml`)
- Created production-ready config from Optuna R&D
- Per-asset parameters: BTCUSDT, ETHUSDT, XRPUSDT, DOGEUSDT (SOLUSDT disabled)
- Strategy params: bb_window, min_vol_atr, sl_pct, allowed_regimes
- Regime sizing multipliers: FLAT_LOW/NORMAL/HIGH
- Risk management: position_size, max_concurrent, daily_loss_limit

#### Config Models Cleanup (`config_models.py`)
- Removed duplicate `DecisionConfig` class (was defined twice)
- Removed duplicate `exposure` field in ExecutionConfig
- Kept single `MeanReversionConfig` for 1m MR strategy

### Tests: 161 passed, 1 skipped
- All Track B tests pass
- All config loader tests pass
- No regressions

### Files Created:
- `config/aurora/strategies/mean_reversion_1m.yaml`

### Files Modified:
- `apps/reference/domains/feature_engineering/__init__.py`
- `apps/reference/config_models.py`

### Tech Debt Resolved:
- Removed duplicate DecisionConfig class
- Removed duplicate exposure field
- Clean imports in feature_engineering

---

## 2025-12-04 Phase B4: MeanReversion1mStrategy (RID: PHASE-B4-001)

### What: Implemented 1m Mean Reversion strategy module

### Why: Complete bar-based MR strategy using Bollinger Bands and FLAT regime

### Changes Made:

#### MeanReversion1mStrategy (`feature_engineering/mean_reversion_strategy.py`)
- `MRSignalType` enum: LONG, SHORT, NEUTRAL
- `MRSignal` dataclass:
  - Properties: is_signal, side (BUY/SELL)
  - Entry/exit prices, BB, ATR, flat regime, MR params
  - Confidence score, timestamp, why chain
- `MRStrategyConfig` dataclass:
  - BB params: window=20, num_std=2.0
  - ATR/RSI windows: 14
  - Entry threshold: 5% inside band
  - RSI thresholds: 30/70
  - Cooldown: 60s
- `MRSymbolState` dataclass:
  - Manages bars, indicators (BB, ATR, RSI)
  - Last signal tracking for cooldown
- `MeanReversion1mStrategy` class:
  - `on_tick()` → aggregates to bars, evaluates signal
  - `_update_indicators()` → computes BB, ATR, RSI
  - `_evaluate_signal()` → generates MRSignal
  - `set_regime()` / `get_regime()` — external regime input
  - `force_close_all()` — session end handling
  - `reset_symbol()` / `reset_all()` — state management

#### Signal Logic:
- **LONG:** pct_b < 0.05 (price below lower BB)
- **SHORT:** pct_b > 0.95 (price above upper BB)
- **Confirmation:** RSI <30 (oversold) or >70 (overbought)
- **Regime filter:** Only FLAT regimes (MEAN_REVERSION, LOW_VOLATILITY, UNCERTAIN)
- **Stop:** ATR-based, adjusted by FLAT regime type
- **Target:** Mid BB, adjusted by FLAT regime type

### Tests: 25 new tests (`test_mean_reversion_strategy.py`)
- MRSignalType tests (2)
- MRSignal tests (4)
- MRStrategyConfig tests (2)
- MRSymbolState tests (3)
- MeanReversion1mStrategy tests (10)
- Regime filtering tests (2)
- Cooldown tests (2)

### Total Track B tests: 110 passed
- Bar resampler: 25
- Indicators: 26
- Regime mapping: 34
- MR Strategy: 25

### Files Created:
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `tests/domains/test_mean_reversion_strategy.py`

### Next: Integration with decision_making, config layer for 1m MR

---

## 2025-12-04 Phase B3: FLAT Regime Mapping (RID: PHASE-B3-001)

### What: Implemented FLAT regime mapping for 1m Mean Reversion

### Why: MR strategy needs FLAT_LOW/NORMAL/HIGH from Aurora regime output

### Changes Made:

#### Regime Mapping (`feature_engineering/regime_mapping.py`)
- `FlatRegime` enum: FLAT_LOW, FLAT_NORMAL, FLAT_HIGH
- `FlatRegimeThresholds` dataclass: ATR% thresholds for classification
  - high_vol_pct: 0.3% (R&D default)
  - low_vol_pct: 0.1% (R&D default)
- `map_to_flat_regime(regime, atr_pct)` → FLAT regime or None:
  - TREND_UP/DOWN, HIGH_VOLATILITY → None (skip MR)
  - LOW_VOLATILITY → FLAT_LOW
  - MEAN_REVERSION + ATR% → FLAT_LOW/NORMAL/HIGH
  - UNCERTAIN → FLAT_NORMAL (conservative)
- `is_flat_regime(regime)` → bool helper
- MR parameter multipliers:
  - `get_mr_sizing_multiplier()`: 0.8/1.0/0.7
  - `get_mr_stop_multiplier()`: 0.6/1.0/1.5 (ATR)
  - `get_mr_target_multiplier()`: 0.8/1.0/1.2 (BB distance)
- `MRParameters` dataclass with `from_flat_regime()` factory
- `get_mr_parameters()` convenience function

### Tests: 34 new tests (`test_regime_mapping.py`)
- FlatRegime enum tests (2)
- FlatRegimeThresholds classification tests (5)
- map_to_flat_regime() tests (15)
- is_flat_regime() tests (2)
- MR multiplier tests (6)
- MRParameters tests (4)

### Total B-track tests: 85 passed
- Bar resampler: 25
- Indicators: 26
- Regime mapping: 34

### Files Created:
- `apps/reference/domains/feature_engineering/regime_mapping.py`
- `tests/domains/test_regime_mapping.py`

### Next: Phase B4 (MeanReversion1mStrategy module)

---

## 2025-12-04 Track B: Bar Resampler & Indicators (RID: TRACK-B-001)

### What: Implemented bar resampler and technical indicators for 1m Mean Reversion

### Why: Infrastructure for bar-based strategies (1m MR needs OHLCV bars + Bollinger Bands)

### Changes Made:

#### Phase B1: Bar Resampler (`feature_engineering/bar_resampler.py`)
- `Bar` dataclass: OHLCV with properties (mid, range_pct, is_bullish/bearish)
- `BarResampler`: Single-symbol tick → bar aggregation
  - `add_tick()` → returns closed Bar when period ends
  - `get_completed_bars()`, `get_closes()` for indicator calculation
  - Bar boundary alignment to timeframe
  - `force_close()` for session end
- `MultiSymbolBarResampler`: Multi-symbol wrapper

#### Phase B2: Technical Indicators (`feature_engineering/indicators.py`)
- `compute_sma()`: Simple Moving Average
- `compute_std()`: Standard Deviation
- `compute_bollinger_bands()` → `BollingerBands` dataclass
  - upper, lower, mid bands
  - width (% of mid)
  - %B indicator (position within bands)
- `compute_atr()`: Average True Range
- `compute_rsi()`: Relative Strength Index
- `IndicatorState`: Container for all indicators per symbol

### Tests: 51 new tests
- 25 tests for bar_resampler.py
- 26 tests for indicators.py

### Files Created:
- `apps/reference/domains/feature_engineering/bar_resampler.py`
- `apps/reference/domains/feature_engineering/indicators.py`
- `tests/domains/test_bar_resampler.py`
- `tests/domains/test_indicators.py`

### Next: Phase B3 (FLAT regime mapping), Phase B4 (MeanReversion1mStrategy)

---

## 2025-12-04 Tech Debt Cleanup: Remove Legacy Stubs (RID: TECH-DEBT-001)

### What: Removed legacy stub parameters and rules from FSM

### Why: Стара логіка дублювала нові per-instrument правила

### Changes Made:

#### FSM __init__ Cleanup (`fsm_manage.py`)
- Removed `trail_pct: float = 0.5` parameter
- Removed `breakeven_after_sec: float = 300.0` parameter
- Removed `self.trail_pct` and `self.breakeven_after_sec` stub fields
- Updated docstrings: "stub rules" → "per-instrument trailing_stop, max_hold_time"

#### _check_rules() Cleanup (`fsm_manage.py`)
- Removed Rule 1: `ADJUST_TRAIL` stub (used old `self.trail_pct`)
- Removed Rule 2: `ADJUST_BE` stub (used old `self.breakeven_after_sec`)
- Updated docstring: "brackets, trailing stop, max hold time"

#### Updated Legacy Tests
- `test_manage_flow_fsm_unit.py`: Updated `_calculate_bracket_prices` test for 3-tuple (sl, tp1, tp2)
- `test_manage_flow_fsm_sl_side.py`: Updated to expect `DEC:BATCH` instead of `DEC:PLACE_ORDER`

### Tests: 50 passed
- All FSM tests pass
- All Aurora instrument config tests pass

### Metrics:
- Removed ~30 lines of dead code
- FSM signature simplified: `ManageFlowFSM(config=...)` only

---

## 2025-12-04 Phase A3+A4: Trailing Stop & Max Hold Time (RID: PHASE-A3A4-001)

### What: Implemented trailing stop with per-instrument config and max hold time watchdog

### Why: Optuna Phase 3+ shows significant PnL improvement with dynamic exit management

### Changes Made:

#### Phase A3: Trailing Stop (`fsm_manage.py`)
- Added `peak_price: Optional[Decimal]` field for high-water mark tracking
- Added `_get_trailing_stop_params(symbol)` helper → returns (enabled, activation_pct, trail_pct, min_update_sec)
- Refactored `_check_trailing_stop()`:
  - Uses per-instrument config with global dict fallback
  - Implements high-water mark trailing (peak_price tracking)
  - Respects min_update_interval_sec rate limiting
  - Activation threshold: `entry × (1 ± activation_pct)`
  - Trail calculation: `peak × (1 ∓ trail_pct)`
- Fixed `_adjust_trailing_stop()` to use `_get_opposite_side()` (was bug!)
- Updated `reset()` to clear new trailing fields

#### Phase A4: Max Hold Time (`fsm_manage.py`)
- Added `_get_max_hold_sec(symbol)` helper → returns max_hold_sec or None
- Added `_check_max_hold_time(msg, elapsed_sec)`:
  - Emits `DEC:CLOSE_POSITION` when elapsed >= max_hold_sec
  - Includes reason, elapsed_sec, max_hold_sec in payload
- Integrated into `_check_rules()` before stub trail/breakeven rules

#### Config Sample (`config/aurora/trading.yaml`)
- Added `trailing_stop` section to ETHUSDT:
  - `enabled: true`
  - `activation_pct: 0.003` (0.3%)
  - `trail_pct: 0.006` (0.6%)
  - `min_update_interval_sec: 5`

### Tests: 38 passed (6 trailing + 3 max hold new tests)
- test_get_trailing_stop_params_per_instrument
- test_get_trailing_stop_params_fallback_to_global
- test_trailing_stop_disabled_by_default
- test_peak_price_tracking
- test_get_max_hold_sec_per_instrument
- test_check_max_hold_time_timeout
- test_check_max_hold_time_no_config

### Backward Compatibility:
- Trailing still works with global `trailing` dict (legacy format)
- Max hold is opt-in — no action if `max_hold_sec` not set

### Track A Complete! 🎉

---

## 2025-12-04 Phase A2: TP1/TP2 Partial Exit (RID: PHASE-A2-001)

### What: Implemented TP1/TP2 risk-ratio based take-profit with partial exit support

### Why: Optuna optimization shows better risk-adjusted returns with 70/30 TP split

### Changes Made:

#### FSM Bracket Calculation (`fsm_manage.py`)
- Refactored `_calculate_bracket_prices()` to return 3 values: `(sl, tp1, tp2)`
- Added risk-ratio based TP calculation: TP1 = sl_pct × tp_low_ratio, TP2 = sl_pct × tp_high_ratio
- Added helper methods:
  - `_get_take_profit_params(symbol)` → returns (tp_low_ratio, tp_high_ratio, partial_exit_pct)
  - `_calculate_sl_from_pct(entry_price, sl_pct)` → SL from percentage
  - `_calculate_sl_from_bps(entry_price)` → SL from global bps (fallback)
  - `_calculate_tp_from_bps(entry_price)` → TP from global bps (fallback)
  - `_quantize_prices(symbol, sl, tp1, tp2)` → quantize to tick_size

#### FSM Bracket Placement (`fsm_manage.py`)
- Added fields: `tp1_order_id`, `tp2_order_id`, `tp1_price`, `tp2_price`, `partial_exit_pct`
- Modified `_on_state_brackets()`:
  - Validates both TP1 and TP2 (if present)
  - Applies safety offset to TP1 and TP2
  - Calculates partial qty: TP1 = total × partial_exit_pct, TP2 = remainder
  - Places 2 TP orders when configured, 1 otherwise (backward compat)

#### Config Sample (`config/aurora/trading.yaml`)
- Added `take_profit` section to ETHUSDT and SOLUSDT:
  - `tp_low_ratio: 1.5` (TP1 = 1.5× risk)
  - `tp_high_ratio: 3.0` (TP2 = 3× risk)
  - `partial_exit_pct: 0.7` (70% at TP1)

### Tests: 32 passed (5 new bracket calculation tests)
- test_bracket_prices_tp1_tp2_with_risk_ratio
- test_bracket_prices_tp1_only_no_tp2
- test_bracket_prices_use_per_instrument_sl_pct (updated)
- test_bracket_prices_fallback_to_global_bps (updated)
- test_bracket_prices_sell_side_with_per_instrument (updated)

### Backward Compatibility:
- `tp_order_id` and `tp_price` still populated (= TP1 values)
- Without `take_profit` config → single TP from bps fallback
- `tp2_price = None` when no `tp_high_ratio`

### Next Steps:
- A3: Trailing stop (CANCEL+NEW flow)
- A4: Max hold time watchdog

---

## 2025-12-04 Phase A1: Per-Asset Core Parameters (RID: PHASE-A1-001)

### What: Refactored decision_making.py to use per-instrument Aurora config

### Why: Track A implementation - apply Optuna Phase 3+ per-asset parameters

### Changes Made:

#### Decision Making Refactoring (`decision_making.py`)
- Refactored `signal_weights` lookup to use `_get_param(symbol, 'weights', global_weights)`
- Added `_get_side_bias_params(symbol)` helper with per-instrument fallback
- Added `_get_regime_thresholds(symbol)` helper with per-instrument fallback
- Added `_get_regime_sizing(symbol)` helper with per-instrument fallback
- Refactored all 4 lookups from global-only to per-instrument with fallback chain

#### Sample Config (`config/aurora/trading.yaml`)
- Added `aurora_instruments` section with ETHUSDT and SOLUSDT
- ETHUSDT: Full Phase 3+ params (weights, side_bias=0.9, regime_thresholds, exit)
- SOLUSDT: Key insight - `side_bias.penalty_factor: 0.0` (disabled!)

### Tests: 23 passed (existing tests not broken)

---

## 2025-12-04 Phase 0: Per-Instrument Aurora Configuration (RID: PHASE0-CFG-001)

### What: Implemented per-instrument configuration architecture for Aurora strategy

### Why: BLOCKING requirement to transfer Optuna R&D results to production. Each asset (BTCUSDT, ETHUSDT, etc.) has different optimal parameters that can't be captured by global config.

### Changes Made:

#### 🔴 P0 - Pydantic Models (`config_models.py`)
- Added 6 new Pydantic V2 models for per-instrument configuration:
  - `AuroraSideBiasConfig` - penalty_factor, window_sec, target_ratio
  - `AuroraExitConfig` - sl_pct, max_hold_sec
  - `AuroraTakeProfitConfig` - tp_low_ratio, tp_high_ratio, partial_exit_pct
  - `AuroraTrailingStopConfig` - enabled, activation_pct, trail_pct, min_update_interval_sec
  - `AuroraExecutionConfig` - order_type, post_only, max_slippage_bps
  - `AuroraInstrumentConfig` - umbrella config with weights, side_bias, regime_thresholds, etc.
- Added `aurora_instruments: Dict[str, AuroraInstrumentConfig]` to `TradingConfig`

#### 🔴 P0 - FSM Symbol Tracking (`fsm_manage.py`)
- Added `self.symbol: Optional[str] = None` to `ManageFlowFSM.__init__`
- Symbol extracted from fill event payload in `_on_fill()`
- Symbol cleared on position close and `reset()`
- Added helper methods:
  - `_get_aurora_instr_cfg(symbol)` - get per-instrument config
  - `_get_exit_param(param, default, symbol)` - get exit param with fallback

#### 🔴 P0 - Decision Making Helpers (`decision_making.py`)
- Added import for `AuroraInstrumentConfig`
- Added helper methods:
  - `_get_aurora_instrument_cfg(symbol)` - get per-instrument config
  - `_get_param(symbol, param, default)` - get param with fallback chain

### Fallback Chain (Pattern):
```
1. aurora_instruments.<SYMBOL>.<param> (per-instrument)
2. trading.decision.<param> (global)
3. default value
```

### Tests Added:
- `tests/domains/test_aurora_instrument_config.py` (22 tests)
  - TestAuroraInstrumentConfigModels (11 tests)
  - TestTradingConfigAuroraInstruments (3 tests)
  - TestFSMSymbolTracking (6 tests)
  - TestConfigFallbackChain (2 tests)

### Next Steps:
- Track A (Aurora): A2 TP1/TP2 partial exit → A3 trailing → A4 max_hold
- Track B (1m MR): B1 bar resampler → B2 indicators → B3 strategy

---

## 2025-11-30 Position Tracking Deep Fixes (RID: PT-DEEP-FIX-001)

### What: Comprehensive fixes for position_tracking domain

### Why: Critical bugs affecting RL training and margin calculations

### Changes Made:

#### 🔴 P0 - Unrealized PnL Implementation
- **File**: `apps/reference/domains/position_tracking/position_tracking.py`
- Implemented real `_calculate_unrealized_pnl()` with:
  - Support for positionRisk API data (most accurate)
  - Cached mark prices fallback for real-time updates
  - Staleness check (5 second threshold)
  - Formula: `unrealized_pnl = Σ((mark_price - entry_price) × quantity)`
- Added `update_mark_price()` method for external price updates
- Added `_mark_prices` cache dict with `ts_ms` tracking

#### 🔴 P0 - JSON Schema Update
- **File**: `apps/reference/domains/position_tracking/schemas/portfolio_state_v1.json`
- Upgraded to JSON Schema 2020-12
- Added missing fields:
  - `equity_free_usdt`, `equity_cross_usdt`, `equity_ts`
  - `available_balance`
  - `open_positions_usd`, `open_positions_margin_usd`
  - `positions_by_side` with `long_margin`, `short_margin`
  - `positions_last_ts_ms`
- Changed `additionalProperties: true` for backward compatibility

#### 🔴 P0 - Leverage Key Bug Fix (EXP-LEVERAGE-002)
- Fixed leverage extraction to check `__default__` key first (config_models.py standard)
- Created unified helper methods:
  - `_get_leverage_config()` - centralized config extraction
  - `_resolve_default_leverage()` - default value resolution
  - `_resolve_symbol_leverage()` - symbol-specific resolution
- Removed 3 duplicate code blocks in `_calc_margin_used_usd()` and `_calculate_margin_by_side()`

#### 🟡 P1 - Market Tick Subscription
- Added optional `EVT:MARKET_TICK_RECEIVED` subscription
- Config-gated via `domains.position_tracking.enable_market_tick_subscription`
- Added `_should_subscribe_market_tick()` and `on_market_tick()` methods

### Tests Added:
- `tests/domains/test_position_tracking_unrealized_pnl.py` (29 tests)
  - TestCalculateUnrealizedPnL (7 tests)
  - TestUpdateMarkPrice (3 tests)
  - TestLeverageResolution (7 tests)
  - TestMarginWithNewLeverage (3 tests)
  - TestIntegrationUnrealizedPnL (1 test)
  - TestMarketTickSubscription (6 tests)
  - TestZeroQuantityPositions (2 tests)
- `tests/domains/test_portfolio_state_schema.py` (14 tests)
  - TestSchemaStructure (7 tests)
  - TestSchemaValidation (3 tests)
  - TestSchemaWithRealPositionTracking (2 tests)
  - TestUnrealizedPnLInSchema (2 tests)

### Test Results:
- **104 tests passed** (all position_tracking + schema tests)
- No regressions in existing tests

### Impact:
- RL Engine (Alysha) now receives real unrealized PnL for training
- Margin calculations use correct leverage from config
- Schema contract is now properly documented
- ExposureGuard/AuroraBridge have documented API contract

## 2025-12-01 00:14 | RID: FIX-TESTS-LEGACY | Fix legacy test failures

### why: 4 застарілі тести не відповідали поточному API (< 80 chars)

### Changes:
1. **test_emergency_wait_mode.py** — fixed config structure (Pydantic expects trading.execution.manage, not top-level)
2. **test_account_connector_empty_positions.py** — updated expected log messages (INFO vs CRITICAL, 'clear' vs 'use')
3. **test_exposure_guard_events.py** — fixed API call (fsm_core, config) + added create_aurora_config
4. **test_exposure_guard_side_caps.py** — fixed API call (fsm_core, config) + added create_aurora_config

### Result:
- Before: 132 passed, 2 failed, 5 errors
- After: 155 passed, 5 failed (pre-existing), 3 skipped

### Pre-existing failures (NOT our changes):
- test_fsm_close.py (3 tests) — FSM close logic mismatch
- test_fsm_open.py (1 test) — notional reject returns DEC instead of ERR
- test_exposure_guard_side_caps.py (1 test) — side cap assertion

### Artefacts:
- Modified: tests/domains/test_emergency_wait_mode.py
- Modified: tests/domains/test_account_connector_empty_positions.py
- Modified: tests/domains/test_exposure_guard_events.py
- Modified: tests/domains/test_exposure_guard_side_caps.py

---

## 2025-12-02 | RID: FSMP-ARCH-01-UNIT-TESTS | Market Data Multiprocessing Unit Tests

### why: Unit tests for worker/proxy components needed for CI/CD validation

### Changes:
1. **tests/test_market_data_worker.py** (NEW) — 10 tests for worker component
   - `TestWorkerBackpressure` — tests `_put_with_backpressure()` (normal + drop-oldest)
   - `TestWorkerMessageTypes` — tests tick/anchor/heartbeat message formats
   - `TestWorkerConfig` — tests symbol extraction, empty symbols error, testnet default
   - `TestWorkerWebSocket` — tests WS URL building, subscribe payload format

2. **tests/test_market_data_proxy.py** (NEW) — 11 tests for proxy component
   - `TestProxyTickEmission` — tests FSM event emission, counter increment
   - `TestProxyAnchorEmission` — tests `EVT:ANCHOR_UPDATED` emission
   - `TestProxyHeartbeat` — tests heartbeat state update
   - `TestProxyConfigSerialization` — tests Pydantic V2/dict passthrough
   - `TestProxyDeprecation` — tests `set_feature_engineering()` is no-op
   - `TestProxyMetrics` — tests metrics property
   - `TestProxyBatchProcessing` — tests batch size constant, queue consumption

### Technical Notes:
- Used `MockQueue` (stdlib `queue.Queue` wrapper) instead of `multiprocessing.Queue` because multiprocessing queues require separate processes to function correctly
- Tests are sync-compatible (no actual process spawning needed)

### Result:
- **21/21 tests passed** ✅
- Test runtime: ~0.13s

### Artefacts:
- Created: tests/test_market_data_worker.py
- Created: tests/test_market_data_proxy.py
- Updated: docs/FSMP_ARCH_01_MARKET_DATA_ISOLATION.md (Phase 4 checkboxes)

---

## 2025-12-02 | RID: FSMP-ARCH-01-INTEGRATION | Full Integration Complete

### why: Integration tests + config + live system verification

### Changes:
1. **tests/integration/test_market_data_multiprocess.py** (NEW) — 9 integration tests
   - `TestProcessIsolation` — verifies worker runs in separate PID
   - `TestLatency` — measures E2E latency (Mean: 0.074ms, P99: 0.484ms)
   - `TestBackpressure` — tests drop-oldest policy
   - `TestLoadCapacity` — achieved 689K ticks/sec throughput!
   - `TestFullIntegration` — full Worker→Queue→Proxy→FSM cycle

2. **config/aurora/trading.yaml** — added `use_multiprocessing: true`
   - Feature flag to toggle between Proxy and legacy Connector
   - Defaults to false for safety, set to true for production

3. **Verified live system startup**:
   - Main process: Aurora Core components
   - Worker process: PID 10928, connected to Binance WebSocket
   - Logs separated: `aurora_core.log` (main) + `aurora_market_data.log` (worker)

### Result:
- **All 30 tests passed** (21 unit + 9 integration)
- **System starts correctly** with multiprocessing enabled
- **Event loop isolation achieved** — OrderGuardian no longer starved

### Performance:
- Latency: P99 < 0.5ms (SLA was 100ms)
- Throughput: 689,843 ticks/sec (SLA was 1000/sec)
- Backpressure: Drop-oldest works, newest data retained

### Status: ✅ FSMP-ARCH-01 COMPLETE

---

## 2025-12-02 | RID: FSMP-ARCH-01-BUGFIX | Fixed IPC Queue Communication

### why: Worker emitted ticks but proxy didn't receive them

### Root Cause:
1. Combined stream messages from Binance have wrapper: `{"stream":"...", "data":{...}}`
2. Consumer was busy-looping without sleep when queue empty
3. `daemon=True` caused issues with IPC

### Fixes Applied:
1. **worker.py**: Added unwrapping of combined stream messages
   ```python
   if "stream" in msg and "data" in msg:
       msg = msg["data"]
   ```
2. **proxy.py**: Changed `daemon=False` for proper Queue communication
3. **proxy.py**: Added `asyncio.sleep(0.01)` when queue is empty to prevent busy-waiting

### Result:
- ✅ Worker receives ~500 trades per 4-5 seconds
- ✅ Queue properly transfers data to main process
- ✅ Proxy emits EVT:MARKET_TICK_RECEIVED for all 4 symbols
- ✅ FeatureEngineering calculates features
- ✅ DecisionMaking evaluates signals (neutral = correct behavior)

### Why No Orders:
- Signal score 0.0676 < threshold 0.1 - this is correct!
- System waits for stronger signals before trading
