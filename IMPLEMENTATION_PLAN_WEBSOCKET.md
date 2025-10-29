# Plan: Implement Real-time Feature Calculation via WebSocket

## Current State

- ❌ Features calculated from **CONSTANT** values (bid_size=1, ask_size=1, buy_vol=volume/2, sell_vol=volume/2)
- ❌ OBI always ≈ 0, TFI always ≈ 0
- ❌ System uses only REST API klines (updates every 5 seconds)
- ✅ Config already defines needed WebSocket streams (bookTicker, trade)

## Architecture

### Data Sources

**bookTicker stream** → OBI (Order Book Imbalance)
```
{
  "s": "BTCUSDT",
  "b": "113956.50",   // bid price
  "B": "2.5",         // bid size (quantité) ✅ LIVE
  "a": "113957.00",   // ask price  
  "A": "3.2"          // ask size ✅ LIVE
}
```

**trade stream** → TFI (Trade Flow Imbalance) + delta_price
```
{
  "s": "BTCUSDT",
  "p": "113956.50",
  "q": "0.5",
  "T": 1698764512345,
  "m": false          // is buyer maker? (false = sell, true = buy)
}
```

### Feature Calculation

**OBI** = (bid_size - ask_size) / (bid_size + ask_size)
- Range: [-1, 1]
- +1 = strong buy pressure
- -1 = strong sell pressure
- 0 = balanced

**TFI** = (buy_trades - sell_trades) / total_trades (over 1-min window)
- Range: [-1, 1]
- +1 = strong buy flow
- -1 = strong sell flow

**delta_price** = (current - previous) / previous
- Already working from klines

## Implementation Steps

### Step 1: Create WebSocket Data Aggregator

File: `apps/reference/domains/market_data/websocket_aggregator.py`

```python
class WebSocketAggregator:
    def __init__(self, fsm, config, symbols):
        self.fsm = fsm
        self.config = config
        self.symbols = symbols
        
        # Per-symbol state
        self.state = {
            symbol: {
                'bid_size': Decimal(0),      # Latest from bookTicker
                'ask_size': Decimal(0),      # Latest from bookTicker
                'bid_price': Decimal(0),
                'ask_price': Decimal(0),
                'buy_trades': 0,             # Count over 1-min window
                'sell_trades': 0,            # Count over 1-min window
                'trades_window_start': None,
                'latest_price': Decimal(0)
            }
            for symbol in symbols
        }
    
    def on_bookTicker(self, symbol: str, bid_size: str, ask_size: str, ...):
        """Called when bookTicker stream updates."""
        self.state[symbol]['bid_size'] = Decimal(bid_size)
        self.state[symbol]['ask_size'] = Decimal(ask_size)
        # Emit feature update
    
    def on_trade(self, symbol: str, price: str, is_buyer_maker: bool, ...):
        """Called when trade stream updates."""
        if is_buyer_maker:
            self.state[symbol]['sell_trades'] += 1  # maker is seller
        else:
            self.state[symbol]['buy_trades'] += 1   # maker is buyer
        
        # Emit feature update if window complete
```

### Step 2: Add WebSocket Support to BinanceAdapter

File: `vfoundation/adapters/binance_adapter.py`

Add methods:
```python
async def subscribe_to_stream(self, stream_name: str, callback: callable):
    """Subscribe to a WebSocket stream."""
    
async def listen_bookTicker(self, symbols: List[str], callback: callable):
    """Subscribe to bookTicker stream."""
    
async def listen_trades(self, symbols: List[str], callback: callable):
    """Subscribe to trade stream."""
```

### Step 3: Update MarketDataConnector

File: `apps/reference/domains/market_data/market_data_connector.py`

- Create WebSocketAggregator instance
- Connect to WebSocket streams on start
- Emit EVT:FEATURES_UPDATED more frequently (every 1-2 sec, not 5 sec)
- Add DEBUG logging for bid_size, ask_size, buy_vol, sell_vol

### Step 4: Add Verification Tests

File: `tests/test_websocket_feature_calculation.py`

```python
def test_obi_varies_with_book():
    """Verify OBI changes with different bid/ask sizes."""
    
def test_tfi_varies_with_trades():
    """Verify TFI changes with buy/sell trade distribution."""
    
def test_features_not_constant():
    """Verify features are NOT constant values."""
```

### Step 5: Update Logging

Add to `feature_engineering.py`:

```python
self.logger.debug(f"Feature calc for {symbol}: "
    f"bid={bid_size}, ask={ask_size} → OBI={obi:.4f} | "
    f"buy_vol={buy_volume}, sell_vol={sell_volume} → TFI={tfi:.4f} | "
    f"price={price}, prev={prev_price} → delta_price={delta_price:.6f}")
```

## Expected Results

### Before (Current - Broken)
```
bid_size=1, ask_size=1 → OBI=0.0000
buy_vol=500, sell_vol=500 → TFI=0.0000
Signal = 0.0000 × 0.6 + 0.0000 × 0.35 + delta × 0.05 ≈ 0.0000 ❌
```

### After (Fixed)
```
bid_size=2.5, ask_size=3.2 → OBI=-0.1176 (sell pressure)
buy_trades=32, sell_trades=28 → TFI=0.0667 (slight buy flow)
Signal = -0.1176 × 0.6 + 0.0667 × 0.35 + delta × 0.05 ≈ 0.0 to ±0.3 ✅
```

Features VARY with market conditions!

## Timeline

- [ ] Create WebSocketAggregator (15 min)
- [ ] Add WebSocket methods to BinanceAdapter (20 min)
- [ ] Update MarketDataConnector (20 min)
- [ ] Add DEBUG logging (10 min)
- [ ] Test & verify (15 min)

**Total: ~80 minutes**

## Dependencies

- `aiohttp` (already installed)
- WebSocket support in BinanceAdapter
- Python asyncio (standard lib)

## Testing Strategy

1. Unit test: OBI formula with known values
2. Unit test: TFI formula with known values
3. Integration test: Verify features vary over time
4. E2E test: Verify signals are generated with varying values
