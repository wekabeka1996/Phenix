# Plan: Add Missing TA Features for ta_ensemble

## Problem
`ta_ensemble` always returns `score=0.0, confidence=0.42` because:
1. **12 of 21 features are never computed** (bb_position, atr_14, realized_volatility, etc.)
2. **Naming bug**: augmenter produces `stochastic_k`/`stochastic_d`, models expect `stoch_k`/`stoch_d`
3. Models fall back to neutral defaults → all three return score=0 → ensemble averages to 0.0

## Files to modify

| # | File | Action |
|---|------|--------|
| 1 | `backtest_engine/feature_augmenter.py` | Add 12 missing feature computations + fix stoch naming |
| 2 | `apps/reference/domains/feature_engineering/feature_engineering.py` | Add new keys to `aug_keys` pass-through (2 locations) |

---

## Step 1: Add missing features to `feature_augmenter.py`

### 1a. New functions to add (after `compute_rsi`, before class):

**`compute_bollinger_features`** — bb_position, bb_width, bb_width_change:
```python
def compute_bollinger_features(
    df: pl.DataFrame,
    close_col: str = "close",
    window: int = 20,
    num_std: float = 2.0,
) -> pl.DataFrame:
    close = df[close_col].cast(pl.Float64)
    mid = close.rolling_mean(window_size=window)
    std = close.rolling_std(window_size=window)
    upper = mid + num_std * std
    lower = mid - num_std * std
    band_range = upper - lower
    # bb_position = %B = (close - lower) / (upper - lower)
    bb_position = pl.when(band_range > 0).then(
        (close - lower) / band_range
    ).otherwise(0.5)
    # bb_width = (upper - lower) / mid
    bb_width = pl.when(mid > 0).then(band_range / mid).otherwise(0.0)
    # bb_width_change = bb_width - bb_width_prev
    bb_width_change = bb_width - bb_width.shift(1)
    return df.with_columns([
        bb_position.alias("bb_position"),
        bb_width.alias("bb_width"),
        bb_width_change.fill_null(0.0).alias("bb_width_change"),
    ])
```

**`compute_atr_features`** — atr_14, atr_ratio:
```python
def compute_atr_features(
    df: pl.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    period: int = 14,
    ratio_window: int = 100,
) -> pl.DataFrame:
    high = df[high_col].cast(pl.Float64)
    low = df[low_col].cast(pl.Float64)
    close = df[close_col].cast(pl.Float64)
    prev_close = close.shift(1)
    tr = pl.max_horizontal(
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    )
    atr = tr.ewm_mean(span=period, adjust=False)
    atr_avg = atr.rolling_mean(window_size=ratio_window)
    atr_ratio = pl.when(atr_avg > 0).then(atr / atr_avg).otherwise(1.0)
    return df.with_columns([
        atr.alias("atr_14"),
        atr_ratio.fill_null(1.0).alias("atr_ratio"),
    ])
```

**`compute_volatility_features`** — realized_volatility_1h, realized_volatility_1d, volume_volatility_ratio, price_range_ratio:
```python
def compute_volatility_features(
    df: pl.DataFrame,
    close_col: str = "close",
    high_col: str = "high",
    low_col: str = "low",
    volume_col: str = "volume",
) -> pl.DataFrame:
    close = df[close_col].cast(pl.Float64)
    high = df[high_col].cast(pl.Float64)
    low = df[low_col].cast(pl.Float64)
    volume = df[volume_col].cast(pl.Float64)
    log_returns = (close / close.shift(1)).log()
    # realized_volatility = std of log returns over window
    rv_1h = log_returns.rolling_std(window_size=60).fill_null(0.0)
    rv_1d = log_returns.rolling_std(window_size=1440).fill_null(0.0)
    # price_range_ratio = current range / avg range
    bar_range = high - low
    avg_range = bar_range.rolling_mean(window_size=100)
    price_range_ratio = pl.when(avg_range > 0).then(
        bar_range / avg_range
    ).otherwise(1.0)
    # volume_volatility_ratio = vol_sma_ratio * rv_normalize
    vol_sma = volume.rolling_mean(window_size=20)
    vol_ratio = pl.when(vol_sma > 0).then(volume / vol_sma).otherwise(1.0)
    rv_norm = pl.when(rv_1d > 0).then(rv_1h / rv_1d).otherwise(1.0)
    volume_volatility_ratio = vol_ratio * rv_norm
    return df.with_columns([
        rv_1h.alias("realized_volatility_1h"),
        rv_1d.alias("realized_volatility_1d"),
        price_range_ratio.fill_null(1.0).alias("price_range_ratio"),
        volume_volatility_ratio.fill_null(1.0).alias("volume_volatility_ratio"),
    ])
```

**`compute_sma_features`** — price_sma_20_deviation, volume_sma_ratio:
```python
def compute_sma_features(
    df: pl.DataFrame,
    close_col: str = "close",
    volume_col: str = "volume",
    sma_window: int = 20,
) -> pl.DataFrame:
    close = df[close_col].cast(pl.Float64)
    volume = df[volume_col].cast(pl.Float64)
    sma_20 = close.rolling_mean(window_size=sma_window)
    price_sma_20_deviation = pl.when(sma_20 > 0).then(
        (close - sma_20) / sma_20
    ).otherwise(0.0)
    vol_sma = volume.rolling_mean(window_size=sma_window)
    volume_sma_ratio = pl.when(vol_sma > 0).then(
        volume / vol_sma
    ).otherwise(1.0)
    return df.with_columns([
        price_sma_20_deviation.fill_null(0.0).alias("price_sma_20_deviation"),
        volume_sma_ratio.fill_null(1.0).alias("volume_sma_ratio"),
    ])
```

### 1b. Fix stochastic naming in `compute_stochastic` (line 115-117):

Change:
```python
    return df.with_columns([
        stoch_k.alias("stochastic_k"),
        stoch_d.alias("stochastic_d"),
    ])
```
To:
```python
    return df.with_columns([
        stoch_k.alias("stoch_k"),
        stoch_d.alias("stoch_d"),
    ])
```

### 1c. Call new functions in `augment()` method (after line 306):

```python
            symbol_df = compute_bollinger_features(symbol_df)
            symbol_df = compute_atr_features(symbol_df)
            symbol_df = compute_volatility_features(symbol_df)
            symbol_df = compute_sma_features(symbol_df)
```

### 1d. Update `get_feature_names()` (line 328-341):

Add new feature names and fix stochastic naming.

### 1e. Update log message in `augment()` (line 320-323):

Update the feature names list in the log.

---

## Step 2: Update `feature_engineering.py` aug_keys pass-through

Two locations (lines 611 and 909) — add all new feature names and fix stochastic naming:

```python
aug_keys = [
    "macd_line", "macd_signal", "macd_histogram",
    "stoch_k", "stoch_d",
    "price_momentum_5m", "price_momentum_1h", "price_momentum_1d",
    "volume_momentum_5m", "rsi_14",
    # Bollinger / volatility / SMA features
    "bb_position", "bb_width", "bb_width_change",
    "atr_14", "atr_ratio",
    "realized_volatility_1h", "realized_volatility_1d",
    "volume_volatility_ratio", "price_range_ratio",
    "price_sma_20_deviation", "volume_sma_ratio",
]
```

---

## Step 3: Update DEFAULT_CONFIG in BacktestFeatureAugmenter

Add config keys for new indicators:
```python
DEFAULT_CONFIG = {
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "stochastic": {"k_period": 14, "d_period": 3},
    "rsi": {"period": 14},
    "momentum": {"windows_bars": [5, 60, 1440]},
    "volume_momentum": {"window": 5},
    "bollinger": {"window": 20, "num_std": 2.0},
    "atr": {"period": 14, "ratio_window": 100},
    "sma": {"window": 20},
}
```

---

## Verification

1. `python -c "from backtest_engine.feature_augmenter import BacktestFeatureAugmenter; print('OK')"`
2. `python -c "from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering; print('OK')"`
3. `pytest tests/domains/alpha_search/ -v` — all alpha_search tests pass
4. `pytest tests/domains/feature_engineering/ -v` — FE tests pass
5. Quick smoke test with minimal DataFrame:
```python
import polars as pl
from backtest_engine.feature_augmenter import BacktestFeatureAugmenter
df = pl.DataFrame({
    "ts": list(range(2000)),
    "symbol": ["BTCUSDT"] * 2000,
    "open": [100.0 + i*0.01 for i in range(2000)],
    "high": [100.5 + i*0.01 for i in range(2000)],
    "low": [99.5 + i*0.01 for i in range(2000)],
    "close": [100.0 + i*0.01 for i in range(2000)],
    "volume": [1000.0 + i for i in range(2000)],
})
aug = BacktestFeatureAugmenter(df)
result = aug.augment()
# Check all 21 features exist
for col in ["bb_position", "bb_width", "bb_width_change", "atr_14", "atr_ratio",
            "realized_volatility_1h", "realized_volatility_1d", "price_range_ratio",
            "volume_volatility_ratio", "price_sma_20_deviation", "volume_sma_ratio",
            "stoch_k", "stoch_d", "rsi_14", "macd_signal"]:
    assert col in result.columns, f"Missing: {col}"
    last_val = result[col][-1]
    print(f"  {col} = {last_val}")
print("ALL FEATURES PRESENT")
```
