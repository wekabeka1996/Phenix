"""
Shadow Run Engine - Replays feature logs through decision logic to simulate P&L.

This engine allows testing alternative configurations (weights, thresholds) 
against historical feature data without risking real capital.

Now includes price_motion multi-window gates (Flash/Bleed) matching production
DecisionMaking behavior from PRICE-MOTION-V1 implementation.

Usage:
    from apps.research.shadow_run.shadow_engine import ShadowEngine
    
    engine = ShadowEngine(
        feature_logs_dir="logs/features",
        config_path="configs/aurora.yaml",  # or provide config dict
        symbols=["ETHUSDT", "BTCUSDT"],
    )
    
    # Enable price_motion gates (default: enabled)
    engine.pm_gates_enabled = True
    engine.pm_k_vol = 2.0
    engine.pm_flash_threshold = 1.0
    engine.pm_bleed_threshold = 0.7
    
    results = engine.run()
    results.print_summary()
"""

import json
import os
import statistics
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal, Tuple, Deque
from datetime import datetime
import yaml


# =============================================================================
# PRICE MOTION CALCULATOR (mirrors production price_motion.py)
# =============================================================================

class PriceMotionCalculator:
    """
    Calculates price motion features for shadow run.
    
    Matches production logic from apps/reference/domains/feature_engineering/price_motion.py:
    - ret_window = (price_now / price_then) - 1
    - vol_pct_window = median(|returns|)  (robust vol proxy)
    - pm_norm_window = clip(ret / (k_vol * vol_pct), -1, 1)
    """
    
    def __init__(
        self,
        k_vol: float = 2.0,
        windows_sec: Tuple[int, int, int] = (10, 60, 300),
        history_size: int = 500,
    ):
        self.k_vol = k_vol
        self.windows_sec = windows_sec
        self.history_size = history_size
        
        # Price history: list of (ts_ms, price) tuples
        self.price_history: Deque[Tuple[int, Decimal]] = deque(maxlen=history_size)
    
    def reset(self):
        """Clear price history (call between symbols)."""
        self.price_history.clear()
    
    def update(self, ts_ms: int, price: Decimal) -> Dict[str, Optional[float]]:
        """
        Update history and compute price_motion block.
        
        Returns dict with ret_*, vol_pct_*, pm_norm_* for each window.
        """
        if ts_ms <= 0 or price <= 0:
            return self._empty_block()
        
        self.price_history.append((ts_ms, price))
        
        result: Dict[str, Optional[float]] = {}
        
        for w in self.windows_sec:
            key_ret = f"ret_{w}s"
            key_vol = f"vol_pct_{w}s"
            key_pm = f"pm_norm_{w}s"
            
            start_ts = ts_ms - w * 1000
            p_then = self._price_at_or_before(start_ts)
            
            if p_then is None or p_then <= 0:
                result[key_ret] = None
                result[key_vol] = None
                result[key_pm] = None
                continue
            
            ret = float((price / p_then) - Decimal("1"))
            result[key_ret] = ret
            
            prices_window = self._prices_in_window(start_ts, ts_ms)
            vol = self._robust_vol(prices_window)
            
            if vol is None or vol <= 0:
                result[key_vol] = None
                result[key_pm] = None
                continue
            
            result[key_vol] = vol
            
            denom = self.k_vol * vol
            if denom <= 0:
                result[key_pm] = None
                continue
            
            pm = ret / denom
            pm = max(-1.0, min(1.0, pm))  # clip
            result[key_pm] = pm
        
        return result
    
    def _empty_block(self) -> Dict[str, Optional[float]]:
        """Return empty price_motion block."""
        return {
            "ret_10s": None, "ret_60s": None, "ret_300s": None,
            "vol_pct_10s": None, "vol_pct_60s": None, "vol_pct_300s": None,
            "pm_norm_10s": None, "pm_norm_60s": None, "pm_norm_300s": None,
        }
    
    def _price_at_or_before(self, target_ts: int) -> Optional[Decimal]:
        """Find price at or before target timestamp."""
        for ts, price in reversed(self.price_history):
            if ts <= target_ts:
                return price
        return None
    
    def _prices_in_window(self, start_ts: int, end_ts: int) -> List[Decimal]:
        """Get all prices in [start_ts, end_ts] range."""
        return [p for ts, p in self.price_history if start_ts <= ts <= end_ts]
    
    def _robust_vol(self, prices: List[Decimal]) -> Optional[float]:
        """Compute robust volatility = median(|returns|)."""
        if len(prices) < 3:
            return None
        
        abs_rets = []
        prev = prices[0]
        for p in prices[1:]:
            if prev > 0 and p > 0:
                r = float((p / prev) - Decimal("1"))
                abs_rets.append(abs(r))
            prev = p
        
        if len(abs_rets) < 2:
            return None
        
        return statistics.median(abs_rets)


@dataclass
class Trade:
    """Represents a single trade."""
    symbol: str
    entry_time: int  # timestamp ms
    exit_time: Optional[int] = None
    entry_price: Decimal = Decimal("0")
    exit_price: Decimal = Decimal("0")
    side: Literal["long", "short"] = "long"
    size_usd: Decimal = Decimal("100")  # notional
    pnl: Decimal = Decimal("0")
    exit_reason: str = ""
    entry_score: Decimal = Decimal("0")
    entry_features: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class Position:
    """Represents an open position."""
    symbol: str
    side: Literal["long", "short"]
    entry_price: Decimal
    entry_time: int
    size_usd: Decimal
    entry_score: Decimal
    entry_features: Dict[str, Any]
    
    # Exit management
    sl_price: Decimal = Decimal("0")
    tp_price: Decimal = Decimal("0")


@dataclass
class ShadowResults:
    """Results of a shadow run."""
    symbol: str
    trades: List[Trade]
    total_pnl: Decimal = Decimal("0")
    win_rate: float = 0.0
    total_trades: int = 0
    long_trades: int = 0
    short_trades: int = 0
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    
    # PRICE-MOTION-V1: Gate statistics
    pm_blocked_count: int = 0
    pm_blocked_reasons: Dict[str, int] = field(default_factory=dict)
    
    def print_summary(self):
        """Print human-readable summary."""
        print(f"\n{'='*60}")
        print(f"  SHADOW RUN RESULTS: {self.symbol}")
        print(f"{'='*60}")
        print(f"  Total Trades:    {self.total_trades}")
        print(f"  Long/Short:      {self.long_trades} / {self.short_trades}")
        print(f"  Win Rate:        {self.win_rate:.1%}")
        print(f"  Total P&L:       ${float(self.total_pnl):+.2f}")
        print(f"  Avg Win:         ${float(self.avg_win):+.2f}")
        print(f"  Avg Loss:        ${float(self.avg_loss):.2f}")
        print(f"  Profit Factor:   {self.profit_factor:.2f}")
        print(f"  Max Drawdown:    ${float(self.max_drawdown):.2f}")
        print(f"  Sharpe:          {self.sharpe_ratio:.2f}")
        
        # Price Motion gate stats
        if self.pm_blocked_count > 0:
            print(f"  {'─'*40}")
            print(f"  PM Gates Blocked: {self.pm_blocked_count}")
            for reason, count in self.pm_blocked_reasons.items():
                print(f"    - {reason}: {count}")
        
        print(f"{'='*60}\n")
        
        
class ShadowEngine:
    """
    Shadow run engine that replays feature logs through configurable signal logic.
    
    Key Features:
    - Replay historical features from logs/features/SYMBOL.log
    - Apply configurable signal weights and thresholds
    - Track virtual positions with TP/SL simulation
    - Generate P&L report with detailed trade log
    """
    
    def __init__(
        self,
        feature_logs_dir: str = "logs/features",
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        default_position_size_usd: Decimal = Decimal("100"),
    ):
        self.feature_logs_dir = Path(feature_logs_dir)
        self.config = config or {}
        self.config_path = config_path
        self.default_position_size_usd = default_position_size_usd
        
        # Auto-detect symbols from log files if not provided
        if symbols is None:
            symbols = self._detect_symbols()
        self.symbols = symbols
        
        # Load config from file if path provided
        if config_path and not config:
            self._load_config(config_path)
        
        # Weight overrides for testing
        self._weight_overrides: Dict[str, float] = {}
        
        # Threshold overrides
        self._threshold_override: Optional[Decimal] = None
        
        # Exit parameters (default, can be overridden)
        self.sl_pct = Decimal("0.005")  # 0.5% stop loss
        self.tp_pct = Decimal("0.01")   # 1.0% take profit
        self.max_hold_bars = 60  # Max bars to hold position
        
        # Skip first N features for warmup
        self.warmup_bars = 10
        
        # =================================================================
        # PRICE-MOTION-V1: Multi-window safety gates (match production)
        # =================================================================
        self.pm_gates_enabled = True  # Enable price_motion gates
        self.pm_k_vol = 2.0           # Normalization factor
        self.pm_flash_window_sec = 10  # Flash window (seconds)
        self.pm_bleed_window_sec = 300 # Bleed window (seconds)
        self.pm_flash_threshold = 1.0  # Block if |pm_norm| >= threshold
        self.pm_bleed_threshold = 0.7  # Block if |pm_norm| >= threshold
        self.pm_require_bleed_ready = True  # Fail-closed if bleed not ready
        
        # Price motion calculator
        self._pm_calc = PriceMotionCalculator(k_vol=self.pm_k_vol)
        
        # Stats for blocked entries
        self._pm_blocked_count = 0
        self._pm_blocked_reasons: Dict[str, int] = {}
        
    def _detect_symbols(self) -> List[str]:
        """Detect available symbols from feature log files."""
        symbols = []
        if self.feature_logs_dir.exists():
            for f in self.feature_logs_dir.glob("*.log"):
                symbols.append(f.stem)
        return sorted(symbols)
    
    def _load_config(self, path: str):
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            self.config = yaml.safe_load(f)
    
    def set_weight_override(self, feature: str, weight: float):
        """Override a specific feature weight for testing."""
        self._weight_overrides[feature] = weight
        
    def set_threshold_override(self, threshold: float):
        """Override signal threshold."""
        self._threshold_override = Decimal(str(threshold))
        
    def set_exit_params(self, sl_pct: float, tp_pct: float, max_hold: int = 60):
        """Set exit parameters."""
        self.sl_pct = Decimal(str(sl_pct))
        self.tp_pct = Decimal(str(tp_pct))
        self.max_hold_bars = max_hold
        
    def _get_signal_weights(self, symbol: str) -> Dict[str, float]:
        """
        Get signal weights with override support.
        
        Priority:
        1. Manual overrides (test mode)
        2. Per-symbol config (aurora.assets.SYMBOL.weights)
        3. Global config (trading.decision.signal_weights)
        4. Defaults
        """
        # Default weights matching production
        weights = {
            "obi": 0.10,
            "tfi": 0.10,
            "delta_price": 0.05,
            "ema_bias": 0.15,
            "volume_spike": 0.10,
            "volatility_state": 0.10,
            "depth_imbalance": 0.10,
            "macro_sync": 0.10,
            "large_trade_imbalance": 0.10,
            "liquidity_kappa": 0.05,
        }
        
        # Try to load from config
        try:
            # Check per-symbol config first
            aurora_assets = self.config.get("aurora", {}).get("assets", {})
            if symbol in aurora_assets and "weights" in aurora_assets[symbol]:
                weights.update(aurora_assets[symbol]["weights"])
            else:
                # Fall back to global weights
                global_weights = (
                    self.config.get("trading", {})
                    .get("decision", {})
                    .get("signal_weights", {})
                )
                if global_weights:
                    weights.update(global_weights)
        except Exception:
            pass
        
        # Apply manual overrides
        weights.update(self._weight_overrides)
        
        return weights
    
    def _get_signal_threshold(self, symbol: str) -> Decimal:
        """Get signal threshold."""
        if self._threshold_override is not None:
            return self._threshold_override
        
        # Try config
        try:
            per_symbol = (
                self.config.get("aurora", {})
                .get("assets", {})
                .get(symbol, {})
                .get("signal_threshold")
            )
            if per_symbol:
                return Decimal(str(per_symbol))
            
            global_th = (
                self.config.get("trading", {})
                .get("decision", {})
                .get("signal_threshold")
            )
            if global_th:
                return Decimal(str(global_th))
        except Exception:
            pass
        
        return Decimal("0.10")  # Default threshold
    
    def _load_features(self, symbol: str) -> List[Dict[str, Any]]:
        """Load feature log for a symbol."""
        log_path = self.feature_logs_dir / f"{symbol}.log"
        if not log_path.exists():
            raise FileNotFoundError(f"Feature log not found: {log_path}")
        
        features = []
        with open(log_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        features.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return features
    
    def _normalize_to_m11(self, value: Decimal) -> Decimal:
        """Normalize value assumed in [-1, 1] range."""
        # Already normalized in our logs
        return value
    
    def _calc_signal_score(
        self, 
        features: Dict[str, Any], 
        weights: Dict[str, float],
        price: Decimal,
    ) -> Decimal:
        """
        Calculate signal score from features using weighted sum.
        
        Matches production logic from decision_making.py.
        """
        score = Decimal("0")
        
        for feature_name, weight in weights.items():
            raw_value = features.get(feature_name, "0")
            try:
                value = Decimal(str(raw_value))
            except Exception:
                value = Decimal("0")
            
            # Special handling for delta_price (normalize to [-1, 1])
            if feature_name == "delta_price" and price > 0:
                dp_cap_pct = Decimal("0.02")  # 2% cap
                dp_pct = value / price
                if dp_pct > dp_cap_pct:
                    dp_pct = dp_cap_pct
                elif dp_pct < -dp_cap_pct:
                    dp_pct = -dp_cap_pct
                value = dp_pct / dp_cap_pct  # [-1, 1]
            
            # Normalize OBI/TFI from [-1, 1] to contribution
            # (production logic uses these directly)
            
            score += value * Decimal(str(weight))
        
        return score
    
    def _check_price_motion_gate(
        self,
        pm_block: Dict[str, Optional[float]],
        intent_side: Literal["long", "short"],
    ) -> Tuple[bool, str]:
        """
        Check price_motion gates (Flash + Bleed).
        
        Matches production DecisionMaking logic:
        - Flash: block LONG if pm_norm_flash <= -threshold
        - Bleed: block LONG if pm_norm_bleed <= -threshold
        - (mirror for SHORT)
        
        Returns: (allowed, block_reason)
        """
        if not self.pm_gates_enabled:
            return (True, "")
        
        # Get pm_norm for flash window
        flash_key = f"pm_norm_{self.pm_flash_window_sec}s"
        bleed_key = f"pm_norm_{self.pm_bleed_window_sec}s"
        
        pm_flash = pm_block.get(flash_key)
        pm_bleed = pm_block.get(bleed_key)
        
        # Fail-closed: insufficient data
        if pm_flash is None:
            return (False, "PM_FLASH_INSUFFICIENT")
        
        if self.pm_require_bleed_ready and pm_bleed is None:
            return (False, "PM_BLEED_INSUFFICIENT")
        
        # Flash gate
        if intent_side == "long" and pm_flash <= -self.pm_flash_threshold:
            return (False, "PM_FLASH_BLOCKED_LONG")
        elif intent_side == "short" and pm_flash >= self.pm_flash_threshold:
            return (False, "PM_FLASH_BLOCKED_SHORT")
        
        # Bleed gate (only if ready)
        if pm_bleed is not None:
            if intent_side == "long" and pm_bleed <= -self.pm_bleed_threshold:
                return (False, "PM_BLEED_BLOCKED_LONG")
            elif intent_side == "short" and pm_bleed >= self.pm_bleed_threshold:
                return (False, "PM_BLEED_BLOCKED_SHORT")
        
        return (True, "")
    
    def _check_exit(
        self, 
        position: Position, 
        current_price: Decimal,
        bar_index: int,
        entry_bar: int,
    ) -> Optional[tuple[str, Decimal]]:
        """
        Check if position should be closed.
        
        Returns: (reason, exit_price) or None
        """
        price_change_pct = (current_price - position.entry_price) / position.entry_price
        
        if position.side == "short":
            price_change_pct = -price_change_pct
        
        # Take Profit
        if price_change_pct >= self.tp_pct:
            return ("TP", current_price)
        
        # Stop Loss
        if price_change_pct <= -self.sl_pct:
            return ("SL", current_price)
        
        # Max hold time
        if bar_index - entry_bar >= self.max_hold_bars:
            return ("MAX_HOLD", current_price)
        
        return None
    
    def run_symbol(self, symbol: str) -> ShadowResults:
        """Run shadow simulation for a single symbol."""
        features_list = self._load_features(symbol)
        weights = self._get_signal_weights(symbol)
        threshold = self._get_signal_threshold(symbol)
        
        trades: List[Trade] = []
        position: Optional[Position] = None
        entry_bar = 0
        
        equity_curve: List[Decimal] = [Decimal("0")]
        peak_equity = Decimal("0")
        max_dd = Decimal("0")
        
        # Reset price motion calculator for this symbol
        self._pm_calc = PriceMotionCalculator(k_vol=self.pm_k_vol)
        pm_blocked_count = 0
        pm_blocked_reasons: Dict[str, int] = {}
        
        # Simulate timestamps (1 second per bar if not in log)
        base_ts = 1704067200000  # 2024-01-01 00:00:00 UTC
        
        for bar_idx, features in enumerate(features_list):
            # Skip warmup
            if bar_idx < self.warmup_bars:
                continue
            
            try:
                price = Decimal(str(features.get("price", "0")))
            except Exception:
                continue
            
            if price <= 0:
                continue
            
            # Simulate timestamp (bar_idx * 1 second)
            ts_ms = base_ts + bar_idx * 1000
            
            # Update price motion calculator
            pm_block = self._pm_calc.update(ts_ms, price)
            
            # Check exit for open position
            if position is not None:
                exit_result = self._check_exit(position, price, bar_idx, entry_bar)
                if exit_result:
                    reason, exit_price = exit_result
                    
                    # Calculate P&L
                    if position.side == "long":
                        pnl_pct = (exit_price - position.entry_price) / position.entry_price
                    else:
                        pnl_pct = (position.entry_price - exit_price) / position.entry_price
                    
                    pnl = position.size_usd * pnl_pct
                    
                    trade = Trade(
                        symbol=symbol,
                        entry_time=position.entry_time,
                        exit_time=bar_idx,
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        side=position.side,
                        size_usd=position.size_usd,
                        pnl=pnl,
                        exit_reason=reason,
                        entry_score=position.entry_score,
                        entry_features=position.entry_features,
                    )
                    trades.append(trade)
                    
                    # Update equity curve
                    current_equity = equity_curve[-1] + pnl
                    equity_curve.append(current_equity)
                    
                    # Track drawdown
                    if current_equity > peak_equity:
                        peak_equity = current_equity
                    dd = peak_equity - current_equity
                    if dd > max_dd:
                        max_dd = dd
                    
                    position = None
            
            # Check for new entry (only if flat)
            if position is None:
                score = self._calc_signal_score(features, weights, price)
                
                side: Optional[Literal["long", "short"]] = None
                if score >= threshold:
                    side = "long"
                elif score <= -threshold:
                    side = "short"
                
                if side:
                    # ============================================================
                    # PRICE-MOTION-V1: Check gates before entry
                    # ============================================================
                    pm_allowed, pm_reason = self._check_price_motion_gate(pm_block, side)
                    
                    if not pm_allowed:
                        # Entry blocked by price_motion gate
                        pm_blocked_count += 1
                        pm_blocked_reasons[pm_reason] = pm_blocked_reasons.get(pm_reason, 0) + 1
                        continue  # Skip this entry
                    
                    # Entry allowed - open position
                    position = Position(
                        symbol=symbol,
                        side=side,
                        entry_price=price,
                        entry_time=bar_idx,
                        size_usd=self.default_position_size_usd,
                        entry_score=score,
                        entry_features=dict(features),
                    )
                    entry_bar = bar_idx
        
        # Store blocked stats
        self._pm_blocked_count = pm_blocked_count
        self._pm_blocked_reasons = pm_blocked_reasons
        
        # Close any remaining position at last price
        if position is not None and features_list:
            last_features = features_list[-1]
            try:
                last_price = Decimal(str(last_features.get("price", "0")))
            except Exception:
                last_price = position.entry_price
            
            if position.side == "long":
                pnl_pct = (last_price - position.entry_price) / position.entry_price
            else:
                pnl_pct = (position.entry_price - last_price) / position.entry_price
            
            pnl = position.size_usd * pnl_pct
            
            trade = Trade(
                symbol=symbol,
                entry_time=position.entry_time,
                exit_time=len(features_list) - 1,
                entry_price=position.entry_price,
                exit_price=last_price,
                side=position.side,
                size_usd=position.size_usd,
                pnl=pnl,
                exit_reason="EOD",
                entry_score=position.entry_score,
                entry_features=position.entry_features,
            )
            trades.append(trade)
            equity_curve.append(equity_curve[-1] + pnl)
        
        # Calculate statistics
        results = self._calc_stats(symbol, trades, max_dd, equity_curve)
        return results
    
    def _calc_stats(
        self, 
        symbol: str, 
        trades: List[Trade], 
        max_dd: Decimal,
        equity_curve: List[Decimal],
    ) -> ShadowResults:
        """Calculate performance statistics."""
        if not trades:
            return ShadowResults(symbol=symbol, trades=[])
        
        total_pnl = sum(t.pnl for t in trades)
        winners = [t for t in trades if t.pnl > 0]
        losers = [t for t in trades if t.pnl <= 0]
        
        win_rate = len(winners) / len(trades) if trades else 0
        avg_win = sum(t.pnl for t in winners) / len(winners) if winners else Decimal("0")
        avg_loss = sum(t.pnl for t in losers) / len(losers) if losers else Decimal("0")
        
        gross_profit = sum(t.pnl for t in winners)
        gross_loss = abs(sum(t.pnl for t in losers))
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        
        # Simple Sharpe approximation (annualized)
        if len(equity_curve) > 1:
            returns = [
                float(equity_curve[i] - equity_curve[i-1]) 
                for i in range(1, len(equity_curve))
            ]
            if returns:
                import statistics
                try:
                    mean_ret = statistics.mean(returns)
                    std_ret = statistics.stdev(returns) if len(returns) > 1 else 1
                    sharpe = (mean_ret / std_ret) * (252 ** 0.5) if std_ret > 0 else 0
                except Exception:
                    sharpe = 0
            else:
                sharpe = 0
        else:
            sharpe = 0
        
        long_trades = sum(1 for t in trades if t.side == "long")
        short_trades = sum(1 for t in trades if t.side == "short")
        
        return ShadowResults(
            symbol=symbol,
            trades=trades,
            total_pnl=total_pnl,
            win_rate=win_rate,
            total_trades=len(trades),
            long_trades=long_trades,
            short_trades=short_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_dd,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe,
            pm_blocked_count=self._pm_blocked_count,
            pm_blocked_reasons=dict(self._pm_blocked_reasons),
        )
    
    def run(self) -> Dict[str, ShadowResults]:
        """Run shadow simulation for all configured symbols."""
        results = {}
        for symbol in self.symbols:
            try:
                results[symbol] = self.run_symbol(symbol)
            except FileNotFoundError as e:
                print(f"⚠️  Skipping {symbol}: {e}")
            except Exception as e:
                print(f"❌ Error processing {symbol}: {e}")
        return results
    
    def run_with_overrides(
        self, 
        weight_overrides: Dict[str, float],
        threshold: Optional[float] = None,
    ) -> Dict[str, ShadowResults]:
        """
        Run with specific weight overrides (useful for optimization).
        """
        # Save current state
        old_overrides = self._weight_overrides.copy()
        old_threshold = self._threshold_override
        
        # Apply new overrides
        self._weight_overrides.update(weight_overrides)
        if threshold is not None:
            self._threshold_override = Decimal(str(threshold))
        
        try:
            results = self.run()
        finally:
            # Restore state
            self._weight_overrides = old_overrides
            self._threshold_override = old_threshold
        
        return results
    
    def compare_configs(
        self,
        config_a: Dict[str, float],
        config_b: Dict[str, float],
        label_a: str = "Config A",
        label_b: str = "Config B",
    ):
        """Compare two weight configurations side by side."""
        print(f"\n{'='*70}")
        print(f"  SHADOW RUN COMPARISON: {label_a} vs {label_b}")
        print(f"{'='*70}")
        
        results_a = self.run_with_overrides(config_a)
        results_b = self.run_with_overrides(config_b)
        
        print(f"\n{'Symbol':<12} | {'Config':<10} | {'Trades':<8} | {'Win%':<8} | {'P&L':<12} | {'PF':<6}")
        print("-" * 70)
        
        for symbol in self.symbols:
            if symbol in results_a:
                ra = results_a[symbol]
                print(f"{symbol:<12} | {label_a:<10} | {ra.total_trades:<8} | {ra.win_rate:>6.1%} | ${float(ra.total_pnl):>+10.2f} | {ra.profit_factor:>5.2f}")
            if symbol in results_b:
                rb = results_b[symbol]
                print(f"{'':<12} | {label_b:<10} | {rb.total_trades:<8} | {rb.win_rate:>6.1%} | ${float(rb.total_pnl):>+10.2f} | {rb.profit_factor:>5.2f}")
            print("-" * 70)
        
        # Aggregate
        total_a = sum(r.total_pnl for r in results_a.values())
        total_b = sum(r.total_pnl for r in results_b.values())
        
        print(f"\n{'TOTAL':<12} | {label_a:<10} | {'':<8} | {'':<8} | ${float(total_a):>+10.2f}")
        print(f"{'     ':<12} | {label_b:<10} | {'':<8} | {'':<8} | ${float(total_b):>+10.2f}")
        print(f"\n  Δ P&L: ${float(total_b - total_a):+.2f} ({label_b} - {label_a})")
        print(f"{'='*70}\n")


def main():
    """CLI entry point for shadow runs."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Shadow Run Engine - Test strategy configs on historical data")
    parser.add_argument("--logs-dir", default="logs/features", help="Feature logs directory")
    parser.add_argument("--symbols", nargs="+", help="Symbols to test (default: all)")
    parser.add_argument("--compare", action="store_true", help="Compare current vs proposed config")
    
    # Weight overrides
    parser.add_argument("--obi", type=float, help="Override OBI weight")
    parser.add_argument("--delta-price", type=float, help="Override delta_price weight")
    parser.add_argument("--threshold", type=float, help="Override signal threshold")
    
    args = parser.parse_args()
    
    engine = ShadowEngine(
        feature_logs_dir=args.logs_dir,
        symbols=args.symbols,
    )
    
    if args.compare:
        # Compare current config vs proposal from SHORT_TREND_ANALYSIS_AND_PROPOSALS.md
        current = {"obi": 0.10, "delta_price": 0.05}
        proposed = {"obi": 0.03, "delta_price": 0.15}
        
        engine.compare_configs(
            current, proposed,
            label_a="Current",
            label_b="Proposed",
        )
    else:
        # Apply any overrides
        if args.obi is not None:
            engine.set_weight_override("obi", args.obi)
        if args.delta_price is not None:
            engine.set_weight_override("delta_price", args.delta_price)
        if args.threshold is not None:
            engine.set_threshold_override(args.threshold)
        
        results = engine.run()
        
        for symbol, res in results.items():
            res.print_summary()
        
        # Print aggregate
        total_pnl = sum(r.total_pnl for r in results.values())
        total_trades = sum(r.total_trades for r in results.values())
        print(f"\n{'='*60}")
        print(f"  AGGREGATE: {total_trades} trades, P&L: ${float(total_pnl):+.2f}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
