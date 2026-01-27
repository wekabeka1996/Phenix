
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler

class DeterministicClock:
    def __init__(self, start_ts=1000.0):
        self._ts = start_ts
    def now(self):
        return self._ts
    def advance(self, seconds):
        self._ts += seconds

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    # Strategies config
    cfg.strategies = MagicMock()
    cfg.strategies.aurora = MagicMock()
    cfg.strategies.aurora.timeframe_sec = 60
    cfg.strategies.aurora.allowed_regimes = None
    cfg.strategies.aurora.enabled_symbols = None
    
    # Decision config
    decision = MagicMock()
    decision.reentry_cooldown_sec = 60.0
    decision.holding_period = MagicMock()
    decision.holding_period.min_duration_sec = 10.0
    
    # Optional configs
    decision.signals = None
    decision.direction_strength_scoring = None
    decision.anchor_shock_veto = None
    decision.anti_churn = None
    
    decision.signal_weights = {}
    decision.feature_neutrals = {}
    decision.essential_features = []
    decision.signal_threshold = 0.1
    decision.neutral_threshold = 0.05
    decision.side_bias_penalty_factor = 0.5
    decision.side_bias_window_sec = 600
    decision.side_bias_target_ratio = 0.5
    decision.side_bias_min_intents = 10
    decision.regime_threshold_multipliers = {}
    
    decision.gates = MagicMock()
    decision.gates.enabled = False
    
    cfg.strategies.aurora.decision = decision
    
    # Add instruments to assets (AuroraHandler looks here)
    # Explicitly set Optional overrides to None to allow fallback to Decision Config
    from types import SimpleNamespace as _SN
    cfg.strategies.aurora.assets = {
        "BTCUSDT": MagicMock(
            signal_threshold=0.1,
            neutral_threshold=0.05,
            enabled=True,
            reentry_cooldown_sec=None,
            holding_period=None,
            volatility_entry_logic=_SN(enabled=False),
            allowed_regimes=["LOW_VOLATILITY"],
        ),
        "ETHUSDT": MagicMock(
            signal_threshold=0.1,
            neutral_threshold=0.05,
            enabled=True,
            reentry_cooldown_sec=None,
            holding_period=None,
            volatility_entry_logic=_SN(enabled=False),
            allowed_regimes=["LOW_VOLATILITY"],
        ),
    }
    cfg.instruments = {}
    return cfg

def test_reentry_cooldown_basic(mock_config):
    """I-REENTRY-01: Verify reentry blocked during cooldown."""
    clock = DeterministicClock(start_ts=5000.0)
    emit_mock = MagicMock()
    
    handler = AuroraHandler(
        config=mock_config,
        emit_fn=emit_mock,
        monotonic_fn=clock.now,
        wall_time_fn=clock.now
    )
    handler.strategies_registry = None
    handler.timeframe_sec = 60
    handler._symbol_states["BTCUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states["BTCUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    
    # --- PROACTIVE GUARD MOCKING ---
    handler._is_symbol_enabled = MagicMock(return_value=True)
    handler._is_regime_allowed = MagicMock(return_value=True)
    
    # Setup Mock Kernel (CLASS MOCK)
    handler.scoring_kernel_cls = MagicMock()
    
    symbol = "BTCUSDT"
    state = handler._symbol_states[symbol]
    state.last_regime_heartbeat_ms = int(clock.now() * 1000)
    state.regime = "LOW_VOLATILITY"
    state.regime_effective = "LOW_VOLATILITY"
    
    event = {
        "symbol": symbol,
        "features": {"price": 100, "atr": 10},
        "tf_sec": 60,
        "warmup": {"full_ready": True},
        "bar_close_ts": int(clock.now()),
        "bar": {"close": 100, "open": 100, "high": 100, "low": 100, "volume": 10},
    }

    # 1. Init state (Buy)

    # Return BUY
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="BUY",
        score=Decimal("0.8"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=[],
        psi_vector={},
        regime=None,
        deferred=False,
    )
    handler.on_process_strategy(event)

    # Simulate execution fill (AuroraHandler position tracking is SSOT from EVT:TRADE_EXECUTED)
    handler.on_trade_executed({"symbol": symbol, "side": "buy", "quantity": "1"})
    assert state.position_side == "buy"
    state.entry_timestamp = clock.now() - 100

    # 2. Exit (Neutral)
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="",
        score=Decimal("0.0"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=[],
        psi_vector={},
        regime=None,
        deferred=False,
    )
    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    assert state.position_side == ""
    assert state.last_exit_timestamp == 5000.0

    # 3. Re-entry too soon (30s < 60s)
    clock.advance(30.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="BUY",
        score=Decimal("0.5"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=[],
        psi_vector={},
        regime=None,
        deferred=False,
    )
    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    # Verify BLOCKED
    # emit_mock calls are Call objects. args[0] is tuple of args. args[0][0] is type.
    types = [c.args[0] for c in emit_mock.call_args_list]
    assert "EVT:STRATEGY_DECISION_BLOCKED" in types
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in types

    # 4. Re-entry allowed (total 61s)
    clock.advance(31.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()
    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    types = [c.args[0] for c in emit_mock.call_args_list]
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in types

def test_reentry_cooldown_regime_multiplier(mock_config):
    """I-FLIP-01/02: Verify regime multiplier affects cooldown."""
    
    # Setup Config Objects for Anti-Churn
    ac = MagicMock()
    ac.enabled = True
    ac.time_multipliers = {
        "HIGH_VOLATILITY": 0.5,
        "LOW_VOLATILITY": 2.0
    }
    ri = MagicMock()
    ri.confirm_window_sec = 90.0
    ri.confirm_window_same_severity_sec = 5.0
    ri.immediate_risk_off = True
    ri.severity_map = {}
    ac.regime_inertia = ri
    
    mock_config.strategies.aurora.decision.anti_churn = ac
    mock_config.strategies.aurora.decision.reentry_cooldown_sec = 10.0
    
    clock = DeterministicClock(start_ts=1000.0)
    emit_mock = MagicMock()
    handler = AuroraHandler(
        config=mock_config, emit_fn=emit_mock, monotonic_fn=clock.now, wall_time_fn=clock.now
    )
    handler.strategies_registry = None
    handler.timeframe_sec = 60
    handler._symbol_states["BTCUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states["BTCUSDT"].regime = "LOW_VOLATILITY"
    
    # --- PROACTIVE GUARD MOCKING ---
    handler._is_symbol_enabled = MagicMock(return_value=True)
    handler._is_regime_allowed = MagicMock(return_value=True)
    
    # Setup Mock Kernel
    handler.scoring_kernel_cls = MagicMock()
    
    symbol = "BTCUSDT"
    event = {
        "symbol": symbol,
        "features": {"price": 100, "atr": 10},
        "tf_sec": 60,
        "warmup": {"full_ready": True},
        "bar_close_ts": int(clock.now()),
        "bar": {"close": 100, "open": 100, "high": 100, "low": 100, "volume": 10},
    }

    # Init
    state = handler._symbol_states[symbol]

    # Helper to force exit tracking
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="",
        score=Decimal("0.0"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=[],
        psi_vector={},
        regime=None,
        deferred=False,
    )

    # Force state
    state.regime = "LOW_VOLATILITY"
    state.regime_effective = "LOW_VOLATILITY"
    state.position_side = "buy"
    state.entry_timestamp = 0.0

    # Exit
    handler.on_process_strategy(event)
    assert state.last_exit_timestamp == 1000.0, f"Exit failed. State: {state}"

    # Re-entry at 15s (Blocked: 10s * 2.0 = 20s required)
    clock.advance(15.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="BUY",
        score=Decimal("0.5"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=[],
        psi_vector={},
        regime=None,
        deferred=False,
    )
    emit_mock.reset_mock()
    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    types = [c.args[0] for c in emit_mock.call_args_list]
    assert "EVT:STRATEGY_DECISION_BLOCKED" in types

    # Re-entry at 21s (Allowed)
    clock.advance(6.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()
    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    types = [c.args[0] for c in emit_mock.call_args_list]
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" in types
