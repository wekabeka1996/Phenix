# Alpha Search: Externalize Hardcoded Parameters

## Goal

Create `config/alpha_search_system.yaml` with ALL hardcoded model parameters and silent defaults from the alpha_search domain. Add Pydantic models, wire into models, and test.

## Architecture

- **`config/alpha_search.yaml`** — operational config (providers, triggers, cache, virtual_trader)
- **`config/alpha_search_system.yaml`** — model tuning params (weights, thresholds, multipliers)
- Models receive their params via `config` dict from `AlphaModel.__init__(config)`
- `backtest_plugin._create_provider_model()` loads system config and passes relevant section

## Discovered Hardcoded Parameters (67 total)

### momentum.py (13 params)
- `short_weight=0.3`, `medium_weight=0.4`, `long_weight=0.3`
- `volume_confirm_multiplier=1.2`, `volume_contradict_multiplier=0.8`
- `rsi_overbought=70`, `rsi_oversold=30`, `rsi_confidence_penalty=0.7`
- `macd_confirm_boost=1.1`, `macd_contradict_penalty=0.9`
- `base_confidence=0.8`, `consistency_min=0.7`, `consistency_range=0.6`

### mean_reversion.py (21 params)
- Signal weights: `bb=0.4`, `rsi=0.3`, `sma=0.2`, `stoch=0.1`
- `rsi_oversold=30`, `rsi_overbought=70`
- `sma_deviation_normalizer=0.05`
- Stochastic: `oversold_zone=20`, `overbought_zone=80`, `signal_strength=0.3`
- Volume: `confirm_multiplier=1.2`, `contradict_multiplier=0.8`, `high_threshold=1.5`, `low_threshold=0.7`
- BB width: `wide_threshold=0.05`, `narrow_threshold=0.02`, `max_multiplier=1.5`, `narrow_penalty=0.7`
- Confidence: `base=0.5`, `agreement_factor=0.4`, `strength_base=0.8`, `signal_threshold=0.1`

### volatility.py (18 params)
- Signal weights: `atr=0.4`, `bb=0.25`, `rv=0.2`, `range=0.1`, `vol_corr=0.05`
- `bb_amplifier=10`, `atr_signal_clamp=2.0`, `rv_signal_clamp=2.0`
- Volume-vol: `high_threshold=1.2`, `low_threshold=0.8`, `signal_strength=0.2`
- Vol level: `low_level=0.5`, `low_penalty=0.5`, `high_level=2.0`, `high_boost=1.2`
- Confidence: `base=0.6`, `agreement_factor=0.3`, `strength_base=0.7`, `no_signal_confidence=0.4`

### ensemble.py (5 params)
- `max_history=100`, `confidence_threshold=0.1`
- `pnl_normalizer=100.0`, `min_performance_score=0.1`, `variance_cap=0.5`

### backtest_plugin.py (2 params)
- `default_tf_sec=300`, `why_chain_limit=5`

---

## Implementation Steps

### Step 1: Create `config/alpha_search_system.yaml` (NEW)

YAML file organized by component with all 67 discovered params. Each param has an inline comment with the default value source.

```yaml
alpha_search_system:
  momentum:
    weights: { short: 0.3, medium: 0.4, long: 0.3 }
    volume: { confirm_multiplier: 1.2, contradict_multiplier: 0.8 }
    rsi: { overbought: 70, oversold: 30, confidence_penalty: 0.7 }
    macd: { confirm_boost: 1.1, contradict_penalty: 0.9 }
    confidence: { base: 0.8, consistency_min: 0.7, consistency_range: 0.6 }

  mean_reversion:
    weights: { bb: 0.4, rsi: 0.3, sma: 0.2, stoch: 0.1 }
    rsi: { oversold: 30, overbought: 70 }
    sma: { deviation_normalizer: 0.05 }
    stochastic: { oversold_zone: 20, overbought_zone: 80, signal_strength: 0.3 }
    volume: { confirm_multiplier: 1.2, contradict_multiplier: 0.8, high_threshold: 1.5, low_threshold: 0.7 }
    bb_width: { wide_threshold: 0.05, narrow_threshold: 0.02, max_multiplier: 1.5, narrow_penalty: 0.7 }
    confidence: { base: 0.5, agreement_factor: 0.4, strength_base: 0.8, signal_threshold: 0.1 }

  volatility:
    weights: { atr: 0.4, bb: 0.25, rv: 0.2, range: 0.1, vol_corr: 0.05 }
    bb: { amplifier: 10 }
    signal_clamp: { atr: 2.0, rv: 2.0 }
    volume_vol: { high_threshold: 1.2, low_threshold: 0.8, signal_strength: 0.2 }
    vol_level: { low_level: 0.5, low_penalty: 0.5, high_level: 2.0, high_boost: 1.2 }
    confidence: { base: 0.6, agreement_factor: 0.3, strength_base: 0.7, no_signal: 0.4 }

  ensemble:
    max_history: 100
    confidence_threshold: 0.1
    pnl_normalizer: 100.0
    min_performance_score: 0.1
    variance_cap: 0.5

  plugin:
    default_tf_sec: 300
    why_chain_limit: 5
```

### Step 2: Add Pydantic system config models to `config_models.py`

Add new Pydantic models at the end of `config_models.py` (before the loader functions):

- `MomentumSystemConfig` — all momentum model params (13 fields)
- `MeanReversionSystemConfig` — all mean reversion params (21 fields)
- `VolatilitySystemConfig` — all volatility params (18 fields)
- `EnsembleSystemConfig` — ensemble tuning params (5 fields)
- `PluginSystemConfig` — plugin-level params (2 fields)
- `AlphaSearchSystemConfig` — root model with all above sections

Add `load_system_config(config_path) -> AlphaSearchSystemConfig` loader function.
Add `get_default_system_config() -> AlphaSearchSystemConfig` fallback.

All Pydantic models use `extra="forbid"` (strict) and sane defaults matching current hardcoded values.

### Step 3: Wire system config into models

**3a. `backtest_plugin.py`** changes:
- In `__init__()`: load system config from `config/alpha_search_system.yaml` (with fallback to defaults)
- In `_create_provider_model()`: pass relevant config section to model constructors

**3b. `models/momentum.py`** changes:
- In `calculate_alpha()`: read all 13 params from `self.config` dict instead of hardcoded Decimal literals
- In `_calculate_consistency()`: read `consistency_min` and `consistency_range` from config

**3c. `models/mean_reversion.py`** changes:
- In `calculate_alpha()`: read all 21 params from `self.config`
- In `_calculate_confidence()`: read `signal_threshold`, `base`, `agreement_factor`, `strength_base`

**3d. `models/volatility.py`** changes:
- In `calculate_alpha()`: read all 18 params from `self.config`
- In `_calculate_confidence()`: read `no_signal_confidence`, `base`, `agreement_factor`, `strength_base`

**3e. `ensemble.py`** changes:
- In `_combine_scores()`: read `why_chain_limit` from config (currently hardcoded `[:10]`)
- In `_update_performance_tracking()`: read `max_history` (currently hardcoded `100`)
- In `generate_signal()`: read `confidence_threshold` (currently hardcoded `0.1`)
- In `_rebalance_weights()`: read `min_performance_score`, `variance_cap`
- In `on_trade_result()`: read `pnl_normalizer` (currently hardcoded `100.0`)

**Key pattern**: Each model reads from `self.config.get("key", DEFAULT)` so it works both with and without system config (backwards compatible).

### Step 4: Add tests

**File**: `tests/domains/alpha_search/test_system_config.py` (NEW)

Tests:
1. `test_system_config_loads_from_yaml` — load actual `config/alpha_search_system.yaml`, verify no validation errors
2. `test_system_config_default_matches_hardcoded` — verify `get_default_system_config()` produces same values as current hardcoded defaults
3. `test_system_config_strict_rejects_unknown` — verify `extra="forbid"` catches typos
4. `test_momentum_uses_config_params` — create MomentumAlphaModel with custom config, verify different weights produce different scores
5. `test_mean_reversion_uses_config_params` — same for MeanReversionAlphaModel
6. `test_volatility_uses_config_params` — same for VolatilityAlphaModel
7. `test_ensemble_uses_config_params` — verify custom `max_history`, `confidence_threshold` etc.
8. `test_all_system_fields_present_in_yaml` — parse YAML, compare field sets against Pydantic model fields

### Step 5: Run full test suite

```bash
pytest tests/domains/alpha_search/ -v
```

All 41+ existing tests must still pass (backwards compatible defaults).

---

## Files to Modify

| File | Action |
|------|--------|
| `config/alpha_search_system.yaml` | NEW — all 67 externalized params |
| `apps/reference/domains/alpha_search/config_models.py` | ADD — 6 Pydantic system config models + loader |
| `apps/reference/domains/alpha_search/backtest_plugin.py` | MODIFY — load system config, pass to models |
| `apps/reference/domains/alpha_search/models/momentum.py` | MODIFY — read params from self.config |
| `apps/reference/domains/alpha_search/models/mean_reversion.py` | MODIFY — read params from self.config |
| `apps/reference/domains/alpha_search/models/volatility.py` | MODIFY — read params from self.config |
| `apps/reference/domains/alpha_search/ensemble.py` | MODIFY — read params from self.config |
| `tests/domains/alpha_search/test_system_config.py` | NEW — 8 tests |

## Verification

1. `pytest tests/domains/alpha_search/ -v` — all tests pass
2. Load `config/alpha_search_system.yaml` in Python — no validation errors
3. Change a param in YAML → verify model output changes (no more hardcoded values)
