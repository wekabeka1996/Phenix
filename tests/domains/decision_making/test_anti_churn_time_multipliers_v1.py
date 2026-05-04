
import pytest
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.strategies = MagicMock()
    cfg.strategies.aurora = MagicMock()
    cfg.strategies.aurora.timeframe_sec = 60
    cfg.strategies.aurora.enabled_symbols = None
    
    decision = MagicMock()
    decision.reentry_cooldown_sec = 60.0 # Default
    
    # Anti-Churn Config
    ac = MagicMock()
    ac.enabled = True
    ac.time_multipliers = {
        "HIGH_VOLATILITY": 0.5,
        "LOW_VOLATILITY": 2.0,
        "TREND_UP": 0.8
    }
    
    # Regime Inertia Config
    ri = MagicMock()
    ri.confirm_window_sec = 90.0
    ri.confirm_window_same_severity_sec = 5.0
    ri.immediate_risk_off = True
    ri.severity_map = {
        "LOW_VOLATILITY": 1,
        "TREND_UP": 2,
        "HIGH_VOLATILITY": 3
    }
    ac.regime_inertia = ri
    
    decision.anti_churn = ac
    
    # Other Configs
    decision.holding_period = MagicMock()
    decision.holding_period.enabled = True
    decision.holding_period.min_duration_sec = 10.0
    
    decision.signals = None
    decision.direction_strength_scoring = None
    decision.anchor_shock_veto = None
    
    decision.signal_weights = {}
    decision.feature_neutrals = {}
    decision.essential_features = []
    decision.signal_threshold = 0.1
    decision.neutral_threshold = 0.05
    decision.side_bias_penalty_factor = 0.5
    decision.side_bias_window_sec = 600
    decision.side_bias_target_ratio = 0.5
    decision.side_bias_min_intents = 10
    decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
    decision.operational_mode = "paranoid"
    decision.scoring_version = "quadratic"
    decision.scoring_engine = None
    decision.quadratic_rollout = None
    decision.execution = None
    decision.exit = None
    decision.dashboard = None
    
    decision.gates = MagicMock()
    decision.gates.enabled = False
    
    cfg.strategies.aurora.decision = decision
    
    # Assets
    cfg.strategies.aurora.assets = {
        "BTCUSDT": MagicMock(signal_threshold=0.1, neutral_threshold=0.05, enabled=True)
    }
    cfg.instruments = {}
    return cfg

class DeterministicClock:
    def __init__(self, start_ts=1000.0):
        self._ts = start_ts
    def now(self):
        return self._ts
    def advance(self, seconds):
        self._ts += seconds

def test_time_multiplier_logic(mock_config):
    """I-AC-01: Verify multipliers load and apply."""
    clock = DeterministicClock()
    emit_mock = MagicMock()
    handler = AuroraHandler(
        config=mock_config, 
        emit_fn=emit_mock,
        monotonic_fn=clock.now,
        wall_time_fn=clock.now
    )
    handler.strategies_registry = None
    
    # Verify loaded
    assert handler.anti_churn_enabled is True
    assert handler.time_multipliers["HIGH_VOLATILITY"] == 0.5
    
    # Verify helper logic
    assert handler._get_time_multiplier("HIGH_VOLATILITY") == 0.5
    assert handler._get_time_multiplier("LOW_VOLATILITY") == 2.0
    assert handler._get_time_multiplier("UNKNOWN") == 1.0 # Default
    assert handler._get_time_multiplier(None) == 1.0

def test_regime_inertia_update(mock_config):
    """I-AC-02: Verify inertia logic (immediate risk-off vs delayed risk-on)."""
    clock = DeterministicClock(start_ts=1000.0)
    emit_mock = MagicMock()
    handler = AuroraHandler(
        config=mock_config, 
        emit_fn=emit_mock,
        monotonic_fn=clock.now,
        wall_time_fn=clock.now
    )
    
    symbol = "BTCUSDT"
    
    # 1. Initial State: LOW_VOLATILITY (Severity 1)
    handler._update_effective_regime(symbol, "LOW_VOLATILITY")
    state = handler._symbol_states[symbol]
    
    assert state.regime_effective == "LOW_VOLATILITY"
    
    # 2. Risk-Off Event: HIGH_VOLATILITY (Severity 3)
    # expect IMMEDIATE switch (Sev 3 > 1)
    clock.advance(1.0) # only 1s passed
    handler._update_effective_regime(symbol, "HIGH_VOLATILITY")
    
    assert state.regime_effective == "HIGH_VOLATILITY"
    assert state.regime_raw == "HIGH_VOLATILITY"
    
    # 3. Risk-On Event: TREND_UP (Severity 2)
    # expect DELAYED switch (Sev 2 < 3)
    # Window is 90s
    clock.advance(1.0)
    handler._update_effective_regime(symbol, "TREND_UP")
    
    # Should stay HIGH_VOLATILITY (only 1s in TREND_UP raw)
    assert state.regime_raw == "TREND_UP"
    assert state.regime_effective == "HIGH_VOLATILITY"
    
    # 4. Advance 89s (Total 90s from change?) No
    # raw change happened at 1000+1+1 = 1002.
    # we need 90s stability.
    clock.advance(89.0) # Now at 1002+89 = 1091. 
    # Logic checks `now - raw_change_ts`.
    # raw_change_ts was set at 1002.
    # 1091 - 1002 = 89 < 90.
    
    handler._update_effective_regime(symbol, "TREND_UP")
    assert state.regime_effective == "HIGH_VOLATILITY"
    
    # 5. Advance 2s (Total 91s)
    clock.advance(2.0)
    handler._update_effective_regime(symbol, "TREND_UP")
    
    # Should switch
    assert state.regime_effective == "TREND_UP"
