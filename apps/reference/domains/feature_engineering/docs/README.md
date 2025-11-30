# Feature Engineering Domain

## Overview

The `feature_engineering` domain is the **Signal component** of the trading system - the "eyes" that transform raw market data into meaningful features for decision making. This domain is critical for alpha generation as it produces the primary inputs for trading signals.

## Role in System Architecture

```
MarketData (EVT:MARKET_TICK_RECEIVED)
        ↓
   FeatureEngineering
        ↓
   EVT:FEATURES_CALCULATED
        ↓
   decision_making / risk_strategy
```

**Key responsibilities:**
- Real-time feature extraction from market tick data
- Stateful computation per trading symbol
- Normalization of features to [0,1] or [-1,1] ranges
- Macro correlation analysis with anchor symbols (BTC, ETH)

## Components

### Core Component
- **`feature_engineering.py`** (~611 LOC) - Main FSM component with Phase 1 metrics
- **`feature_engineering_phase1.py`** (~454 LOC) - Legacy Phase 1 implementation (deprecated, kept for reference)

### Supporting Files
- **`__init__.py`** - Package exports
- **`domain_dict.json`** - Domain metadata, events imports/exports
- **`schemas/features_calculated_v1.json`** - JSON Schema for output event

## Features Computed

### Base Features (always active)
| Feature | Formula | Range | Description |
|---------|---------|-------|-------------|
| **OBI** | `(bid_size - ask_size) / depth` | [-1, 1] | Order Book Imbalance |
| **TFI** | `(buy_vol - sell_vol) / total_flow` | [-1, 1] | Trade Flow Imbalance |
| **Delta Price** | `price - prev_price` (if Δt < 5s) | ℝ | Price change with spike filter |
| **Liquidity Kappa** | `depth / (depth + depth_half)` | [0.3, 1.0] | Normalized liquidity |

### Phase 1 Features (configurable)
| Feature | Formula | Range | Description |
|---------|---------|-------|-------------|
| **EMA Bias** | `(EMA3 - EMA7) / EMA7` → normalized | [0, 1] | Short-term trend indicator |
| **Volume Spike** | `current_vol / SMA(vol, 5)` → capped at 3x | [0, 1] | Volume anomaly detection |
| **Volatility State** | `current_range / SMA(range, 10)` → capped at 3x | [0, 1] | Current vs historical volatility |
| **Depth Imbalance** | `(asks + ε) / (bids + ε)` → transformed | [0, 1] | Liquidity distribution |
| **Macro Sync** | `Pearson(symbol_returns, anchor_returns)` | [0, 1] | Correlation with BTC/ETH |

## Event Contract

### Input: EVT:MARKET_TICK_RECEIVED
```json
{
  "symbol": "BTCUSDT",
  "ts": 1640995200000,
  "price": "45000.50",
  "bid_size": "12.5",
  "ask_size": "8.3",
  "buy_volume": "2.1",
  "sell_volume": "1.8"
}
```

### Output: EVT:FEATURES_CALCULATED
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "features": {
    "obi": "0.2012",
    "tfi": "0.0769",
    "delta_price": "25.50",
    "liquidity_kappa": "0.8234",
    "ema_bias": "0.65",
    "volume_spike": "0.45",
    "volatility_state": "0.78",
    "depth_imbalance": "0.52",
    "macro_sync": "0.71"
  }
}
```

## Configuration

```yaml
trading:
  feature_engineering:
    enable_new_metrics: true
    ema:
      period_short: 3
      period_long: 7
    volume:
      window_sec: 60
      sma_length: 5
    volatility:
      window_sec: 60
      sma_length: 10
    liquidity:
      depth_half: 1000
  market_data:
    macro_sync:
      enabled: true
      anchors: ["BTCUSDT", "ETHUSDT"]
      window: 60
```

## Test Coverage

| Test Category | Tests | Status |
|---------------|-------|--------|
| Unit tests (basic features) | 5 | ✅ PASSED |
| Unit tests (math validation) | 1 | ✅ PASSED |
| Payload validation | 1 | ✅ PASSED |
| Integration (domain config) | 1 | ✅ PASSED |
| **TOTAL** | **8** | **✅ ALL PASSED** |

## Usage

```python
from apps.reference.domains.feature_engineering import FeatureEngineering

# Initialize
fe = FeatureEngineering(fsm=fsm_core, config=config, feature_store=store)

# Start listening to market ticks
fe.start()

# Component will automatically:
# 1. Listen for EVT:MARKET_TICK_RECEIVED
# 2. Calculate features on each tick
# 3. Emit EVT:FEATURES_CALCULATED
```

## Dependencies

- **vFoundation**: FSM core, Message protocol
- **decimal**: Precise financial calculations
- **statistics**: Pearson correlation
- **collections.deque**: Sliding window buffers

## Related Domains

- **Upstream**: `market_data` → provides tick data
- **Downstream**: `decision_making`, `risk_strategy` → consume features
- **Storage**: `feature_store` → persists calculated features
