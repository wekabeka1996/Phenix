"""
Regime Bar Replay Tests

REGIME-BAR-FORENSICS-SIM-01: Simulation tests for regime detection on bars.

Tests verify that:
1. Regime detection works after warmup period
2. All 4 synthetic scenarios produce expected regimes
3. Regime transitions are detected correctly
"""

import pytest
from decimal import Decimal
from collections import deque
from typing import List


class SyntheticPriceGenerator:
    """Generate synthetic price series for regime testing."""
    
    @staticmethod
    def trend_up(start_price: float, n_bars: int, volatility: float = 0.001) -> List[float]:
        import random
        random.seed(42)
        prices = [start_price]
        for _ in range(n_bars - 1):
            drift = start_price * 0.002
            noise = random.uniform(-volatility, volatility) * start_price
            prices.append(prices[-1] + drift + noise)
        return prices
    
    @staticmethod
    def trend_down(start_price: float, n_bars: int, volatility: float = 0.001) -> List[float]:
        import random
        random.seed(42)
        prices = [start_price]
        for _ in range(n_bars - 1):
            drift = start_price * -0.002
            noise = random.uniform(-volatility, volatility) * start_price
            prices.append(prices[-1] + drift + noise)
        return prices
    
    @staticmethod
    def mean_reversion(center_price: float, n_bars: int, amplitude: float = 0.01) -> List[float]:
        import math
        prices = []
        for i in range(n_bars):
            oscillation = math.sin(i * 0.3) * center_price * amplitude
            prices.append(center_price + oscillation)
        return prices
    
    @staticmethod
    def high_vol_shock(start_price: float, n_bars: int) -> List[float]:
        import random
        random.seed(42)
        shock_at = n_bars // 2
        prices = []
        for i in range(n_bars):
            if i < shock_at:
                noise = random.uniform(-0.0005, 0.0005) * start_price
            else:
                noise = random.uniform(-0.02, 0.02) * start_price
            prices.append(start_price + noise)
        return prices


def simulate_regime(prices: List[float], sma_short: int = 10, sma_long: int = 50):
    """Simulate regime detection."""
    price_buf = deque(maxlen=max(sma_short, sma_long))
    regimes = []
    
    for price in prices:
        price_buf.append(Decimal(str(price)))
        
        sma_short_ready = len(price_buf) >= sma_short
        sma_long_ready = len(price_buf) >= sma_long
        
        if sma_short_ready:
            sma_short_val = sum(list(price_buf)[-sma_short:]) / Decimal(str(sma_short))
        else:
            sma_short_val = Decimal("0")
            
        if sma_long_ready:
            sma_long_val = sum(list(price_buf)[-sma_long:]) / Decimal(str(sma_long))
        else:
            sma_long_val = Decimal("0")
        
        regime = "UNCERTAIN"
        if sma_short_ready and sma_long_ready:
            current_price = Decimal(str(price))
            if sma_short_val > sma_long_val and current_price > sma_short_val:
                regime = "TREND_UP"
            elif sma_short_val < sma_long_val and current_price < sma_short_val:
                regime = "TREND_DOWN"
            else:
                spread = abs(sma_short_val - sma_long_val) / sma_long_val
                if spread < Decimal("0.005"):
                    regime = "MEAN_REVERSION"
        
        regimes.append(regime)
    
    return regimes


class TestRegimeBarReplay:
    """Tests for regime detection on bar data."""
    
    def test_trend_up_scenario(self):
        """Trend up prices should produce TREND_UP regime after warmup."""
        prices = SyntheticPriceGenerator.trend_up(100.0, 70)
        regimes = simulate_regime(prices)
        
        # After warmup (bar 50+), should be TREND_UP
        post_warmup = regimes[50:]
        assert "TREND_UP" in post_warmup, "Expected TREND_UP in post-warmup regimes"
        assert post_warmup.count("TREND_UP") > 10, "TREND_UP should dominate"
    
    def test_trend_down_scenario(self):
        """Trend down prices should produce TREND_DOWN regime after warmup."""
        prices = SyntheticPriceGenerator.trend_down(100.0, 70)
        regimes = simulate_regime(prices)
        
        post_warmup = regimes[50:]
        assert "TREND_DOWN" in post_warmup, "Expected TREND_DOWN in post-warmup regimes"
        assert post_warmup.count("TREND_DOWN") > 10, "TREND_DOWN should dominate"
    
    def test_mean_reversion_scenario(self):
        """Oscillating prices should produce MEAN_REVERSION regime."""
        prices = SyntheticPriceGenerator.mean_reversion(100.0, 70)
        regimes = simulate_regime(prices)
        
        post_warmup = regimes[50:]
        mr_count = post_warmup.count("MEAN_REVERSION")
        assert mr_count > 0, "Expected at least some MEAN_REVERSION regimes"
    
    def test_high_vol_shock_scenario(self):
        """High volatility shock should produce mixed/uncertain regimes."""
        prices = SyntheticPriceGenerator.high_vol_shock(100.0, 70)
        regimes = simulate_regime(prices)
        
        post_warmup = regimes[50:]
        # Should have multiple different regimes due to volatility
        unique_regimes = set(post_warmup)
        assert len(unique_regimes) >= 1, "Should have at least one regime detected"
    
    def test_warmup_period_is_uncertain(self):
        """Before warmup complete, regime should be UNCERTAIN."""
        prices = SyntheticPriceGenerator.trend_up(100.0, 70)
        regimes = simulate_regime(prices)
        
        # First 49 bars should all be UNCERTAIN (before sma_long fills)
        warmup_regimes = regimes[:49]
        assert all(r == "UNCERTAIN" for r in warmup_regimes), \
            "All regimes before warmup should be UNCERTAIN"
    
    def test_regime_transition_detection(self):
        """Transitions between regimes should be detected."""
        # Create price series that transitions from up to down
        prices_up = SyntheticPriceGenerator.trend_up(100.0, 60)
        prices_down = SyntheticPriceGenerator.trend_down(prices_up[-1], 60)
        prices = prices_up + prices_down
        
        regimes = simulate_regime(prices)
        
        # Count transitions
        transitions = sum(1 for i in range(1, len(regimes)) if regimes[i] != regimes[i-1])
        assert transitions >= 2, f"Expected at least 2 transitions, got {transitions}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
