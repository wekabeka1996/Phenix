# Events - Feature Engineering Domain

**Last Updated:** 2026-01-27

---

## Event Flow

```
┌──────────────────────────────────────────────────────────────┐
│                       market_data                             │
│                    (WebSocket/REST)                           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼ EVT:MARKET_TICK_RECEIVED (Hot Path)
┌──────────────────────────────────────────────────────────────┐
│                   FeatureEngineering                          │
│                                                               │
│  1. Hot Path: Tick -> OBI, TFI, Micro-Features               │
│     -> Emit EVT:FEATURES_CALCULATED (Immediate)              │
│                                                               │
│  2. Cold Path: Funding/OI Updates -> Update State            │
│                                                               │
│  3. Bar Path: Bar Close -> Synthetic Tick -> Bar Features    │
│     -> Emit CMD:PROCESS_STRATEGY (To DecisionMaking)         │
└──────────────────────────┬──────────────────┬───────────────┘
                           │                  │
                           ▼                  ▼
              EVT:FEATURES_CALCULATED   CMD:PROCESS_STRATEGY
```

---

## Input Event: EVT:MARKET_TICK_RECEIVED

### Source
- `market_data` domain (WebSocket aggregated ticks)

### Trigger Condition
- New tick received from exchange
- Contains all required fields for feature calculation

### Payload Schema

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

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | string | ✅ | Trading pair (e.g., "BTCUSDT") |
| `ts` | integer | ✅ | Timestamp in milliseconds epoch |
| `price` | string | ✅ | Current price (decimal-encoded) |
| `bid_size` | string | ✅ | Total bid depth at best levels |
| `ask_size` | string | ✅ | Total ask depth at best levels |
| `buy_volume` | string | ✅ | Aggressive buy volume in window |
| `sell_volume` | string | ✅ | Aggressive sell volume in window |

### Behavior on Missing Fields
- **Missing `symbol`**: Event ignored, no emission
- **First tick for symbol**: Stored only, no emission (need delta)
- **Other missing fields**: Default to "0"

---

## Output Event: EVT:FEATURES_CALCULATED

### Destination
- `decision_making` - for signal evaluation
- `risk_strategy` - for risk assessment
- `analyzer` (RegimeDetector) - for regime classification
- `feature_store` - for persistence

### Trigger Condition
- Second (or later) tick received for a symbol
- All calculations completed successfully

### Payload Schema

```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "features": {
    "obi": "0.2012",
    "tfi": "0.0769",
    "delta_price": "25.50",
    "absorption": "0.0",
    "price": "45000.50",
    "liquidity_kappa": "0.8234",
    "ema_bias": "0.65",
    "volume_spike": "0.45",
    "volatility_state": "0.78",
    "depth_imbalance": "0.52",
    "macro_sync": "0.71"
  }
}
```

### Feature Descriptions

| Feature | Range | Formula | Interpretation |
|---------|-------|---------|----------------|
| `obi` | [-1, 1] | `(bid - ask) / depth` | +1 = all bids, -1 = all asks |
| `tfi` | [-1, 1] | `(buy - sell) / total` | +1 = all buys, -1 = all sells |
| `delta_price` | ℝ | `price - prev_price` | Filtered if Δt > 5s |
| `absorption` | - | Always "0.0" | Placeholder (not implemented) |
| `price` | ℝ | Current price | Pass-through |
| `liquidity_kappa` | [0.3, 1.0] | `depth / (depth + half)` | Higher = more liquid |
| `ema_bias` | [0, 1] | `(EMA3-EMA7)/EMA7` → norm | >0.5 = bullish, <0.5 = bearish |
| `volume_spike` | [0, 1] | `vol / SMA(vol, 5)` → cap | Higher = volume anomaly |
| `volatility_state` | [0, 1] | `range / SMA(range, 10)` | Higher = elevated volatility |
| `depth_imbalance` | [0, 1] | Transformed ask/bid ratio | Higher = sell pressure |
| `macro_sync` | [0, 1] | Corr with BTC/ETH | Higher = aligned with market |

---

## Feature Calculation Details

### Order Book Imbalance (OBI)

```python
depth = bid_size + ask_size
obi = (bid_size - ask_size) / depth if depth > 0 else Decimal(0)
```

**Edge cases:**
- `depth == 0`: Returns 0
- No normalization needed (naturally bounded)

### Trade Flow Imbalance (TFI)

```python
total_flow = buy_volume + sell_volume
tfi = (buy_volume - sell_volume) / total_flow if total_flow > 0 else Decimal(0)
```

**Edge cases:**
- `total_flow == 0`: Returns 0
- No normalization needed (naturally bounded)

### Delta Price

```python
time_diff = current_tick["ts"] - last_tick["ts"]
delta_price = price - prev_price if time_diff < 5000 else Decimal(0)
```

**Spike filter:** If time gap > 5 seconds, delta is set to 0 to avoid artificial spikes after reconnection.

### EMA Bias

```python
# Update EMAs
ema3 = price * alpha3 + ema3 * (1 - alpha3)  # alpha3 = 2/4 = 0.5
ema7 = price * alpha7 + ema7 * (1 - alpha7)  # alpha7 = 2/8 = 0.25

# Compute bias
bias = (ema3 - ema7) / ema7 if ema7 > 0 else Decimal(0)

# Normalize to [0,1]
bias_clamped = clamp(bias, -0.02, 0.02)
phi = (bias_clamped / 0.02 + 1) / 2
```

**Interpretation:**
- `phi > 0.5`: Short-term EMA above long-term → bullish
- `phi < 0.5`: Short-term EMA below long-term → bearish

### Volume Spike

```python
# Accumulate volume in window (60s default)
vol_window_trades += buy_vol + sell_vol

# When window closes, store and reset
vol_hist.append(vol_window_trades)

# Compute spike ratio
avg_vol = sum(vol_hist) / len(vol_hist)
spike = current_vol / avg_vol if avg_vol > 0 else 1.0

# Normalize to [0,1]
spike_capped = min(spike, 3.0)
phi = spike_capped / 3.0
```

### Macro Sync

```python
# Compute symbol returns
ret = (price - prev_price) / prev_price
returns_buffer.append(ret)

# Compute anchor returns
anchor_returns = [(p[i] - p[i-1]) / p[i-1] for i in range(1, len(p))]

# Pearson correlation
corr = pearson(returns_buffer, anchor_returns)

# Average across anchors and normalize
avg_corr = mean(correlations)
phi = (avg_corr + 1) / 2  # Map [-1,1] to [0,1]
```

---

## Error Handling

### Silent Failures
| Condition | Behavior |
|-----------|----------|
| Missing symbol | Event ignored |
| First tick | Stored, no emission |
| Calculation error | Logged, continues |
| Feature store error | Logged as warning |

### Logged Errors
```python
self.logger.error(f"Error calculating features for {symbol}: {e}")
self.logger.debug(f"Traceback: {traceback.format_exc()}")
```

---

## WHY Chain

Output events include WHY code for observability:

```python
self.fsm.emit("EVT:FEATURES_CALCULATED", payload=features_payload, why="features_calculated")
```

This enables tracing the decision path:
```
EVT:MARKET_TICK_RECEIVED → features_calculated → EVT:FEATURES_CALCULATED
```
