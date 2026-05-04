import pytest
from collections import deque
from apps.reference.domains.system_stress.system_stress_overlay import _SymbolStressState

def test_z_robust_none_equals_z():
    baseline = deque([1.0, 2.0, 3.0, 4.0, 5.0])
    x = 6.0
    z_none = _SymbolStressState._z_robust(x, baseline, method="none")
    z_old = _SymbolStressState._z(x, baseline)
    assert z_none == z_old

def test_z_robust_mad_basic():
    # baseline: 1, 2, 3, 4, 5. median=3.0, MAD=1.0. x=6.0.
    # z_mad = 0.6745 * (6 - 3) / 1.0 = 2.0235
    baseline = deque([1.0, 2.0, 3.0, 4.0, 5.0])
    x = 6.0
    z_mad = _SymbolStressState._z_robust(x, baseline, method="mad")
    assert pytest.approx(z_mad, 0.001) == 2.0235

def test_z_robust_mad_lt_eps_returns_zero():
    baseline = deque([1.0, 1.0, 1.0, 1.0, 1.0])
    x = 2.0
    z_mad = _SymbolStressState._z_robust(x, baseline, method="mad")
    assert z_mad == 0.0

def test_z_robust_short_baseline_returns_zero():
    baseline = deque([1.0])
    x = 2.0
    z_mad = _SymbolStressState._z_robust(x, baseline, method="mad")
    assert z_mad == 0.0

def test_z_robust_clamp():
    baseline = deque([1.0, 2.0, 3.0, 4.0, 5.0]) # median=3, MAD=1
    x = 100.0 # Without clamp: 0.6745 * 97 = ~65.4
    z_mad = _SymbolStressState._z_robust(x, baseline, method="mad", clamp=10.0)
    assert z_mad == 10.0
    
    x_low = -100.0
    z_mad_low = _SymbolStressState._z_robust(x_low, baseline, method="mad", clamp=10.0)
    assert z_mad_low == -10.0
