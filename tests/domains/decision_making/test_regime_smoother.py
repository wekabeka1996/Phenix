import pytest
from decimal import Decimal
from typing import Any
from apps.reference.domains.decision_making.gates.regime_smoother import RegimeMultiplierSmoother

class MockConfig:
    def __init__(self, enabled=True, method="ema", ema_alpha=0.3, ramp_bars=6):
        self.enabled = enabled
        self.method = method
        self.ema_alpha = ema_alpha
        self.ramp_bars = ramp_bars

def test_disabled_returns_raw():
    cfg = MockConfig(enabled=False)
    smoother = RegimeMultiplierSmoother(cfg)
    assert smoother.step(Decimal("1.5"), "BTCUSDT") == Decimal("1.5")

def test_ema_convergence():
    cfg = MockConfig(enabled=True, method="ema", ema_alpha=0.3)
    smoother = RegimeMultiplierSmoother(cfg)
    
    # Init
    smoother.step(Decimal("0.85"), "BTCUSDT")
    
    # Change to 1.30
    res1 = smoother.step(Decimal("1.30"), "BTCUSDT")
    assert res1 == Decimal("0.3") * Decimal("1.30") + Decimal("0.7") * Decimal("0.85")
    
    # Converges within ceil(1/0.3)=4 bars
    res2 = smoother.step(Decimal("1.30"), "BTCUSDT")
    res3 = smoother.step(Decimal("1.30"), "BTCUSDT")
    res4 = smoother.step(Decimal("1.30"), "BTCUSDT")
    res5 = smoother.step(Decimal("1.30"), "BTCUSDT")
    
    assert abs(res5 - Decimal("1.30")) < Decimal("0.1")

def test_ema_max_step():
    cfg = MockConfig(enabled=True, method="ema", ema_alpha=0.3)
    smoother = RegimeMultiplierSmoother(cfg)
    smoother.step(Decimal("1.0"), "BTCUSDT")
    res1 = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res1 - Decimal("1.0") <= Decimal("0.3") * Decimal("1.0")

def test_ema_stable_regime_noop():
    cfg = MockConfig(enabled=True, method="ema", ema_alpha=0.3)
    smoother = RegimeMultiplierSmoother(cfg)
    smoother.step(Decimal("1.0"), "BTCUSDT")
    res = smoother.step(Decimal("1.0"), "BTCUSDT")
    assert res == Decimal("1.0")

def test_linear_ramp_convergence():
    cfg = MockConfig(enabled=True, method="linear_ramp", ramp_bars=4)
    smoother = RegimeMultiplierSmoother(cfg)
    
    smoother.step(Decimal("1.0"), "BTCUSDT")
    # Step 1: 1.0 + (2.0 - 1.0)*1/4 = 1.25
    res1 = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res1 == Decimal("1.25")
    # Step 2: 1.50
    res2 = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res2 == Decimal("1.50")
    # Step 3: 1.75
    res3 = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res3 == Decimal("1.75")
    # Step 4: 2.00
    res4 = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res4 == Decimal("2.00")
    # Step 5: cap at 2.00
    res5 = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res5 == Decimal("2.00")

def test_per_symbol_isolation():
    cfg = MockConfig(enabled=True, method="ema", ema_alpha=0.5)
    smoother = RegimeMultiplierSmoother(cfg)
    smoother.step(Decimal("1.0"), "BTCUSDT")
    smoother.step(Decimal("1.0"), "ETHUSDT")
    
    res_btc = smoother.step(Decimal("2.0"), "BTCUSDT")
    assert res_btc == Decimal("1.5")
    
    res_eth = smoother.step(Decimal("1.0"), "ETHUSDT")
    assert res_eth == Decimal("1.0")
