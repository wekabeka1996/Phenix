# Optuna Integration Implementation Plan

**Created**: 2025-12-03  
**Target**: Integrate 3m/5m Optuna results into Aurora production  
**Status**: Implementation Roadmap

---

## Executive Summary

This document provides a **complete technical plan** for integrating the profitable Optuna-optimized parameters (SOL: +$173, ETH: +$76, XRP: +$29, DOGE: +$5) into the Aurora production system.

**Estimated Effort**: 2-3 weeks for complete integration  
**Core Changes**: 6 files to modify, 2 new files to create  
**Risk Level**: MEDIUM (requires testing before production)

---

## 📋 Gap Analysis Summary

### Missing Capabilities

| Feature | Status | Impact | Priority |
|---|---|---|---|
| Per-Asset Config Override | ❌ Missing | HIGH | P0 |
| OBI/TFI Windows | ❌ Missing | HIGH | P0 |
| Regime Allow-List | ❌ Missing | HIGH | P0 |
| Time-Based Exit | ❌ Missing | MEDIUM | P1 |
| Per-Asset SL | ⚠️ Partial | MEDIUM | P1 |
| Multi-Timeframe | ❌ Missing | LOW | P2 |

---

## 🛠️ Implementation Roadmap

### Phase 1: Per-Asset Configuration (Priority: P0)

**Goal**: Allow symbol-specific parameter overrides.

#### File 1: `config/aurora/trading.yaml`

**Location**: Lines 17-106  
**Action**: Add per-asset override structure

```yaml
trading:
  # Global defaults (apply to all symbols unless overridden)
  decision:
    signal_threshold: 0.10
    max_risk_score: 0.90
    
  instruments:
    BTCUSDT:
      symbol: "BTCUSDT"
      step_size: "0.001"
      tick_size: "0.10"
      
      # ====== OPTUNA OVERRIDES (NEW!) ======
      timeframe: "5m"  # NEW: Timeframe identifier
      
      decision:  # NEW: Per-asset decision params
        signal_threshold: 0.220
        max_risk_score: 0.526
        
      feature_engineering:  # NEW: Per-asset feature params
        ema:
          period_short: 8
          period_long: 20
        volume:
          window_sec: 240
          sma_length: 5
        liquidity:
          depth_half: 750.0
          kappa_min: 0.152
        obi:  # NEW: OBI smoothing window
          window_sec: 290
        tfi:  # NEW: TFI smoothing window
          window_sec: 80
          
      signal_weights:  # NEW: Per-asset signal weights
        weight_ema: 0.233
        weight_volume: 0.367
        weight_macro: 0.277
        weight_liquidity: 0.182
        weight_obi: 0.187
        weight_tfi: 0.277
        
      allowed_regimes:  # NEW: Regime filter
        - TREND_UP
        - TREND_DOWN
        
      brackets:  # NEW: Per-asset SL override
        sl_pct: 0.683  # 0.683% stop loss
        
      exit:  # NEW: Time-based exit
        max_hold_sec: 720  # 12 minutes
        
    SOLUSDT:
      symbol: "SOLUSDT"
      step_size: "0.01"
      tick_size: "0.01"
      timeframe: "3m"
      
      decision:
        signal_threshold: 0.110
        max_risk_score: 0.784
        
      feature_engineering:
        ema:
          period_short: 7
          period_long: 25
        volume:
          window_sec: 280
          sma_length: 16
        liquidity:
          depth_half: 3000.0
          kappa_min: 0.345
        obi:
          window_sec: 70
        tfi:
          window_sec: 160
          
      signal_weights:
        weight_ema: 0.467
        weight_volume: 0.242
        weight_macro: 0.138
        weight_liquidity: 0.138
        weight_obi: 0.344
        weight_tfi: 0.363
        
      allowed_regimes:
        - TREND_DOWN
        
      brackets:
        sl_pct: 0.526  # 0.526% stop loss
        
      exit:
        max_hold_sec: 660  # 11 minutes
        
    # ... ETHUSDT, XRPUSDT, DOGEUSDT (similar structure)
```

**Implementation Steps**:
1. Add `instruments.<SYMBOL>.decision.*` section
2. Add `instruments.<SYMBOL>.feature_engineering.*` section
3. Add `instruments.<SYMBOL>.signal_weights.*` section
4. Add `instruments.<SYMBOL>.allowed_regimes` list
5. Add `instruments.<SYMBOL>.exit.max_hold_sec` parameter

---

### Phase 2: Feature Engineering Updates (Priority: P0)

#### File 2: `apps/reference/domains/feature_engineering/types.py`

**Location**: Add new properties  
**Action**: Add accessor methods for per-asset configs

```python
class FeatureEngineeringConfig:
    # Existing code...
    
    def __init__(self, cfg, symbol: str = None):
        self._cfg = cfg
        self._symbol = symbol  # NEW: Track current symbol
    
    # NEW: Get symbol-specific config with fallback to global
    def _get_symbol_config(self, *keys, default=None):
        """Get config value, checking symbol override first."""
        if self._symbol:
            try:
                # Try symbol-specific path first
                symbol_cfg = self._cfg
                for key in ['instruments', self._symbol, 'feature_engineering'] + list(keys):
                    if hasattr(symbol_cfg, key):
                        symbol_cfg = getattr(symbol_cfg, key)
                    elif isinstance(symbol_cfg, dict):
                        symbol_cfg = symbol_cfg.get(key)
                    else:
                        break
                else:
                    return symbol_cfg
            except (AttributeError, KeyError):
                pass
        
        # Fallback to global config
        current = self._cfg
        for key in keys:
            if hasattr(current, key):
                current = getattr(current, key)
            elif isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current
    
    @property
    def ema_period_short(self) -> int:
        return self._get_symbol_config('ema', 'period_short', default=3)
    
    @property
    def ema_period_long(self) -> int:
        return self._get_symbol_config('ema', 'period_long', default=7)
    
    @property
    def volume_window_sec(self) -> int:
        return self._get_symbol_config('volume', 'window_sec', default=60)
    
    # NEW: OBI window accessor
    @property
    def obi_window_sec(self) -> int:
        return self._get_symbol_config('obi', 'window_sec', default=60)
    
    # NEW: TFI window accessor
    @property
    def tfi_window_sec(self) -> int:
        return self._get_symbol_config('tfi', 'window_sec', default=60)
```

**Implementation Steps**:
1. Add `_symbol` tracking to `__init__`
2. Add `_get_symbol_config` helper method
3. Update all existing properties to use `_get_symbol_config`
4. Add `obi_window_sec` and `tfi_window_sec` properties

#### File 3: `apps/reference/domains/feature_engineering/feature_engineering.py`

**Location**: Line ~150-200 (feature calculation)  
**Action**: Pass symbol to config and add OBI/TFI smoothing

```python
class FeatureEngineering:
    def __init__(self, fsm, config, feature_store=None):
        # ... existing code ...
        
        # Create per-symbol config instances
        self.symbol_configs = {}  # NEW: Per-symbol config cache
    
    def _get_symbol_config(self, symbol: str):
        """Get or create symbol-specific config."""
        if symbol not in self.symbol_configs:
            self.symbol_configs[symbol] = FeatureEngineeringConfig(
                self.config, 
                symbol=symbol
            )
        return self.symbol_configs[symbol]
    
    def _calculate_and_emit_features(self, symbol: str, current_tick: dict, last_tick: dict):
        # Get symbol-specific config
        cfg = self._get_symbol_config(symbol)
        
        # ... existing OBI/TFI calculation ...
        raw_obi = (bid_size - ask_size) / (bid_size + ask_size)
        raw_tfi = (buy_volume - sell_volume) / (buy_volume + sell_volume)
        
        # NEW: Apply smoothing windows
        state = self.symbol_states[symbol]
        
        # OBI smoothing (rolling average)
        if 'obi_buffer' not in state:
            state['obi_buffer'] = []
        state['obi_buffer'].append(float(raw_obi))
        
        # Keep window size based on config
        max_obi_samples = cfg.obi_window_sec // 60  # Assume 1-minute ticks
        if len(state['obi_buffer']) > max_obi_samples:
            state['obi_buffer'].pop(0)
        
        smoothed_obi = sum(state['obi_buffer']) / len(state['obi_buffer'])
        
        # TFI smoothing (rolling average)
        if 'tfi_buffer' not in state:
            state['tfi_buffer'] = []
        state['tfi_buffer'].append(float(raw_tfi))
        
        max_tfi_samples = cfg.tfi_window_sec // 60
        if len(state['tfi_buffer']) > max_tfi_samples:
            state['tfi_buffer'].pop(0)
        
        smoothed_tfi = sum(state['tfi_buffer']) / len(state['tfi_buffer'])
        
        features['obi'] = str(smoothed_obi)
        features['tfi'] = str(smoothed_tfi)
```

**Implementation Steps**:
1. Create `symbol_configs` cache in `__init__`
2. Add `_get_symbol_config` method
3. Add OBI/TFI buffering to `symbol_states`
4. Implement rolling window smoothing

---

### Phase 3: Decision Making Updates (Priority: P0)

#### File 4: `apps/reference/domains/decision_making/decision_making.py`

**Location**: Line ~300-400 (signal evaluation)  
**Action**: Add regime filtering and per-asset signal weights

```python
class DecisionMaking:
    def _make_decision_for_symbol(self, symbol: str):
        # ... existing code ...
        
        # NEW: Get allowed regimes for this symbol
        allowed_regimes = self._get_allowed_regimes(symbol)
        
        # NEW: Check current regime against allow-list
        current_regime = self.latest_regimes.get(symbol, {}).get('regime')
        if current_regime and current_regime not in allowed_regimes:
            self.dlog.rejected(
                symbol=symbol,
                reason=f"REGIME_NOT_ALLOWED:{current_regime}",
                details=f"Allowed: {allowed_regimes}"
            )
            return  # Skip this symbol
        
        # Get symbol-specific signal weights
        weights = self._get_signal_weights(symbol)
        
        # Compute weighted signal
        signal = (
            weights['weight_ema'] * features.get('ema_bias', 0.5) +
            weights['weight_volume'] * features.get('volume_spike', 0.5) +
            weights['weight_macro'] * features.get('macro_sync', 0.5) +
            weights['weight_liquidity'] * features.get('depth_imbalance', 0.5) +
            weights['weight_obi'] * features.get('obi', 0) +
            weights['weight_tfi'] * features.get('tfi', 0)
        )
        
        # Normalize signal
        total_weight = sum(weights.values())
        signal = signal / total_weight if total_weight > 0 else 0.5
        
        # Get symbol-specific threshold
        threshold = self._get_signal_threshold(symbol)
        
        # ... rest of decision logic ...
    
    def _get_allowed_regimes(self, symbol: str) -> list:
        """Get allowed regimes for symbol."""
        try:
            # Try symbol-specific config
            symbol_cfg = self.config.trading.instruments.get(symbol, {})
            if 'allowed_regimes' in symbol_cfg:
                return symbol_cfg['allowed_regimes']
        except (AttributeError, KeyError):
            pass
        
        # Default: all regimes allowed
        return ['TREND_UP', 'TREND_DOWN', 'MEAN_REVERSION', 'LOW_VOLATILITY', 'HIGH_VOLATILITY']
    
    def _get_signal_weights(self, symbol: str) -> dict:
        """Get signal weights for symbol."""
        try:
            # Try symbol-specific config
            symbol_cfg = self.config.trading.instruments.get(symbol, {})
            if 'signal_weights' in symbol_cfg:
                return symbol_cfg['signal_weights']
        except (AttributeError, KeyError):
            pass
        
        # Fallback to global weights
        return self.config.trading.decision.signal_weights
    
    def _get_signal_threshold(self, symbol: str) -> float:
        """Get signal threshold for symbol."""
        try:
            # Try symbol-specific config
            symbol_cfg = self.config.trading.instruments.get(symbol, {})
            if 'decision' in symbol_cfg and 'signal_threshold' in symbol_cfg['decision']:
                return symbol_cfg['decision']['signal_threshold']
        except (AttributeError, KeyError):
            pass
        
        # Fallback to global threshold
        return self.config.trading.decision.signal_threshold
```

**Implementation Steps**:
1. Add `_get_allowed_regimes` method
2. Add regime filtering before signal evaluation
3. Add `_get_signal_weights` method with symbol override
4. Add `_get_signal_threshold` method with symbol override
5. Update signal calculation to use per-asset weights

---

### Phase 4: Execution Updates (Priority: P1)

#### File 5: `apps/reference/domains/execution_position/fsm_manage.py`

**Location**: Add new methods  
**Action**: Implement time-based exit and per-asset SL

```python
class FSMManage:
    def _check_exit_conditions(self, symbol: str, position: dict):
        """Check all exit conditions (SL, TP, Time)."""
        # ... existing SL/TP logic ...
        
        # NEW: Time-based exit
        if self._should_time_exit(symbol, position):
            self._close_position(symbol, reason="TIME_EXIT")
            return
    
    def _should_time_exit(self, symbol: str, position: dict) -> bool:
        """Check if position should be closed due to time limit."""
        # Get symbol-specific max_hold_sec
        max_hold_sec = self._get_max_hold_sec(symbol)
        if max_hold_sec is None:
            return False
        
        # Calculate hold duration
        entry_time = position.get('entry_time')  # Unix timestamp (ms)
        current_time = int(time.time() * 1000)
        hold_duration_sec = (current_time - entry_time) / 1000
        
        return hold_duration_sec >= max_hold_sec
    
    def _get_max_hold_sec(self, symbol: str) -> Optional[int]:
        """Get max hold time for symbol."""
        try:
            symbol_cfg = self.config.trading.instruments.get(symbol, {})
            if 'exit' in symbol_cfg and 'max_hold_sec' in symbol_cfg['exit']:
                return symbol_cfg['exit']['max_hold_sec']
        except (AttributeError, KeyError):
            pass
        return None  # No time limit
    
    def _get_sl_pct(self, symbol: str) -> float:
        """Get stop loss percentage for symbol."""
        try:
            symbol_cfg = self.config.trading.instruments.get(symbol, {})
            if 'brackets' in symbol_cfg and 'sl_pct' in symbol_cfg['brackets']:
                return symbol_cfg['brackets']['sl_pct']
        except (AttributeError, KeyError):
            pass
        
        # Fallback to global bps → percentage
        sl_bps = self.config.trading.execution.manage.brackets.sl.fixed_bps
        return sl_bps / 100.0  # 40 bps → 0.4%
    
    def _calculate_bracket_prices(self, symbol: str, side: str, entry_price: Decimal):
        """Calculate SL/TP prices using per-asset SL."""
        sl_pct = self._get_sl_pct(symbol)
        
        if side == "BUY":
            sl_price = entry_price * (1 - Decimal(str(sl_pct / 100)))
        else:  # SELL
            sl_price = entry_price * (1 + Decimal(str(sl_pct / 100)))
        
        # ... TP calculation ...
        
        return sl_price, tp_price
```

**Implementation Steps**:
1. Add `_should_time_exit` method
2. Add `_get_max_hold_sec` helper
3. Call `_should_time_exit` in main loop or event handler
4. Add `_get_sl_pct` method for per-asset SL
5. Update `_calculate_bracket_prices` to use `_get_sl_pct`

---

## ⚠️ Phase 5: Multi-Timeframe (Priority: P2 - Optional)

**Note**: This is OPTIONAL. Aurora currently works on tick data. Multi-timeframe requires significant architectural changes and is only needed if you want a "true" 3m/5m bar-based bot.

#### File 6 (NEW): `apps/reference/domains/feature_engineering/bar_resampler.py`

```python
from collections import deque
from decimal import Decimal
import time

class BarResampler:
    """Resample tick data into OHLCV bars."""
    
    def __init__(self, timeframe_sec: int):
        self.timeframe_sec = timeframe_sec
        self.current_bar = None
        self.completed_bars = deque(maxlen=100)
    
    def add_tick(self, price: Decimal, volume: Decimal, timestamp: int):
        """Add tick and update current bar."""
        if self.current_bar is None or self._is_new_bar(timestamp):
            # Close current bar if exists
            if self.current_bar:
                self.completed_bars.append(self.current_bar)
            
            # Start new bar
            self.current_bar = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume,
                'start_ts': timestamp
            }
        else:
            # Update current bar
            self.current_bar['high'] = max(self.current_bar['high'], price)
            self.current_bar['low'] = min(self.current_bar['low'], price)
            self.current_bar['close'] = price
            self.current_bar['volume'] += volume
    
    def _is_new_bar(self, timestamp: int) -> bool:
        """Check if timestamp starts a new bar."""
        bar_start = self.current_bar['start_ts']
        return (timestamp - bar_start) >= (self.timeframe_sec * 1000)
    
    def get_latest_closed_bar(self) -> dict:
        """Get most recently completed bar."""
        return self.completed_bars[-1] if self.completed_bars else None
```

**Integration**: Modify `feature_engineering.py` to use bar data instead of tick data for 3m/5m symbols.

---

## ✅ Testing Checklist

### Unit Tests
- [ ] Test per-asset config loading
- [ ] Test regime allow-list filtering
- [ ] Test OBI/TFI smoothing windows
- [ ] Test time-based exit logic
- [ ] Test per-asset SL calculation

### Integration Tests
- [ ] Run backtest with new config (use `apps/research/aurora_optuna/backtest_engine_aurora.py`)
- [ ] Verify PnL matches Optuna results (±5%)
- [ ] Test on testnet for 48 hours
- [ ] Monitor logs for config errors

### Production Validation
- [ ] Paper trading 1 week (no real money)
- [ ] Compare live signals vs backtest
- [ ] Walk-forward validation on Feb 2024 data

---

## 📁 File Summary

| File | Lines to Add | Lines to Modify | Complexity |
|---|---|---|---|
| `config/aurora/trading.yaml` | ~200 | 0 | LOW |
| `feature_engineering/types.py` | ~50 | ~20 | MEDIUM |
| `feature_engineering/feature_engineering.py` | ~60 | ~10 | MEDIUM |
| `decision_making/decision_making.py` | ~80 | ~30 | HIGH |
| `execution_position/fsm_manage.py` | ~60 | ~20 | MEDIUM |
| `feature_engineering/bar_resampler.py` (NEW) | ~100 | 0 | LOW |
| **TOTAL** | **~550** | **~80** | **MEDIUM** |

---

## 🚀 Deployment Sequence

1. **Week 1**: Implement Phase 1-3 (Config + Features + Decision)
2. **Week 2**: Implement Phase 4 (Execution), write tests
3. **Week 3**: Integration testing, testnet validation
4. **Week 4+**: Production deployment (gradual rollout)

---

## 📞 Next Steps

1. Review this plan with team
2. Create GitHub issues for each phase
3. Start with Phase 1 (Config) as it's non-breaking
4. Run integration tests after each phase

**Questions? Ping research team on Slack.**
