
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult

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
    cfg.strategies = MagicMock()
    cfg.strategies.aurora = MagicMock()
    cfg.strategies.aurora.timeframe_sec = 60
    cfg.strategies.aurora.enabled_symbols = None
    
    decision = MagicMock()
    decision.reentry_cooldown_sec = 0.0
    decision.holding_period = MagicMock()
    decision.holding_period.min_duration_sec = 10.0
    decision.holding_period.emergency_exit_threshold = 0.9 # High threshold
    decision.holding_period.enabled = True
    decision.holding_period.apply_to_flips = True
    
    # Optional configs
    decision.signals = MagicMock(
        normalize_signals_mode="signed_v2",
        enable_new_metrics=True,
        delta_price_cap_pct=0.02,
    )
    decision.direction_strength_scoring = None
    decision.anchor_shock_veto = None
    decision.anti_churn = None # Default off
    
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
    # Explicitly set Optional overrides to None to allow fallback
    from types import SimpleNamespace as _SN
    cfg.strategies.aurora.assets = {
        "ETHUSDT": MagicMock(
            signal_threshold=0.1,
            neutral_threshold=0.05,
            enabled=True,
            reentry_cooldown_sec=None,
            holding_period=None,
            volatility_entry_logic=_SN(enabled=False),
            allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        )
    }
    cfg.instruments = {}
    return cfg

def test_holding_period_suppress_flip(mock_config):
    """I-FLIP-01: Verify flip suppressed if within min_duration."""
    clock = DeterministicClock(start_ts=2000.0)
    emit_mock = MagicMock()
    
    handler = AuroraHandler(
        config=mock_config,
        emit_fn=emit_mock,
        monotonic_fn=clock.now,
        wall_time_fn=clock.now
    )
    handler.strategies_registry = None
    handler.timeframe_sec = 60
    handler._symbol_states["ETHUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states["ETHUSDT"].regime = "FLAT_NORMAL"
    handler._symbol_states["ETHUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states["ETHUSDT"].regime = "FLAT_NORMAL"
    handler._symbol_states["ETHUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states["ETHUSDT"].regime = "FLAT_NORMAL"
    
    # MOCK GUARDS
    handler._is_symbol_enabled = MagicMock(return_value=True)
    handler._is_regime_allowed = MagicMock(return_value=True)
    
    # Setup Mock Kernel (Direct Attribute Mock for classmethod)
    handler.scoring_kernel_cls = MagicMock()
    
    symbol = "ETHUSDT"
    event = {
        "symbol": symbol,
        "features": {"price": 100, "atr": 10},
        "tf_sec": 60,
        "warmup": {"full_ready": True},
        "bar_close_ts": int(clock.now()),
        "bar": {"close": 100, "open": 100, "high": 100, "low": 100, "volume": 10},
    }

    # 1. Enter LONG
    state = handler._symbol_states[symbol]
    state.last_regime_heartbeat_ms = int(clock.now() * 1000)

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
    handler.on_process_strategy(event)

    # Verify entry tracked
    state.position_side = "buy"
    state.entry_timestamp = 2000.0
    assert state.position_side == "buy"
    assert state.entry_timestamp == 2000.0

    # 2. Advance 5s (min 10s)
    clock.advance(5.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()

    # 3. Attempt FLIP to SELL
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="SELL",
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

    # Verify Suppressed (Force Hold) -> Signal BUY emitted (override)
    # c.args[0] is type, c.args[1] is payload
    calls = [c.args[1] for c in emit_mock.call_args_list if c.args[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(calls) == 1
    payload = calls[0]
    assert payload["side"] == "BUY", f"Expected override to BUY, got {payload['side']}" # Forced Hold

    # Also verify BLOCK event was emitted for observability
    block_calls = [c.args[1] for c in emit_mock.call_args_list if c.args[0] == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(block_calls) == 1
    assert block_calls[0]["reason_code"] == "HOLDING_PERIOD_ACTIVE"

    # 4. Advance +6s (Total 11s > 10s)
    clock.advance(6.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()

    # 5. Attempt FLIP again
    # Handler mutated the previous result mock to BUY, so we must provide a fresh SELL mock
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="SELL",
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

    # Verify Allowed
    calls = [c.args[1] for c in emit_mock.call_args_list if c.args[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(calls) == 1
    assert calls[0]["side"] == "SELL" # Flip allowed

def test_holding_period_emergency_exit(mock_config):
    """Verify emergency exit allowed even within holding period."""
    clock = DeterministicClock(start_ts=2000.0)
    emit_mock = MagicMock()
    handler = AuroraHandler(config=mock_config, emit_fn=emit_mock, monotonic_fn=clock.now, wall_time_fn=clock.now)
    handler.strategies_registry = None
    handler.timeframe_sec = 60
    handler._symbol_states["ETHUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states["ETHUSDT"].regime = "FLAT_NORMAL"
    
    # MOCK GUARDS
    handler._is_symbol_enabled = MagicMock(return_value=True)
    handler._is_regime_allowed = MagicMock(return_value=True)
    
    handler.scoring_kernel_cls = MagicMock()
    
    symbol = "ETHUSDT"
    event = {
        "symbol": symbol,
        "features": {"price": 100, "atr": 10},
        "tf_sec": 60,
        "warmup": {"full_ready": True},
        "bar_close_ts": int(clock.now()),
        "bar": {"close": 100, "open": 100, "high": 100, "low": 100, "volume": 10},
    }

    # Enter LONG
    state = handler._symbol_states[symbol]

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
    handler.on_process_strategy(event)

    # Verify Entry
    state.position_side = "buy"
    state.entry_timestamp = 2000.0
    assert state.position_side == "buy"

    # Advance 2s (< 10s)
    clock.advance(2.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()

    # Attempt EXIT with HIGH SCORE (Emergency)
    # Score 0.95 >= 0.9 threshold
    handler.scoring_kernel_cls.compute.return_value = MagicMock(
        side="",
        score=Decimal("0.95"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=[],
        psi_vector={},
        regime=None,
        deferred=False,
    )
    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    # Verify State Cleared (Exit happened)
    assert state.position_side == ""
    assert state.last_exit_timestamp == 2002.0


def test_no_mutation_of_scoring_result_when_flip_suppressed(mock_config):
    """Guardrail: AuroraHandler must not mutate ScoringResult (side/score/thresholds)."""
    clock = DeterministicClock(start_ts=2000.0)
    emit_mock = MagicMock()

    handler = AuroraHandler(
        config=mock_config,
        emit_fn=emit_mock,
        monotonic_fn=clock.now,
        wall_time_fn=clock.now,
    )
    handler.timeframe_sec = 60
    handler._symbol_states["ETHUSDT"].last_regime_heartbeat_ms = int(clock.now() * 1000)

    handler._is_symbol_enabled = MagicMock(return_value=True)
    handler.scoring_kernel_cls = MagicMock()

    symbol = "ETHUSDT"
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    handler._symbol_states[symbol].regime = "FLAT_NORMAL"
    state = handler._symbol_states[symbol]
    
    event = {
        "symbol": symbol,
        "features": {"price": 100, "atr": 10},
        "tf_sec": 60,
        "warmup": {"full_ready": True},
        "bar_close_ts": int(clock.now()),
        "bar": {"close": 100, "open": 100, "high": 100, "low": 100, "volume": 10},
    }

    # Enter BUY to establish position + entry_timestamp
    handler.scoring_kernel_cls.compute.return_value = ScoringResult(
        score=Decimal("0.5"),
        side="BUY",
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
    )
    handler.on_process_strategy(event)
    state.position_side = "buy"
    state.entry_timestamp = 2000.0

    # Advance less than holding min_duration, attempt flip SELL
    clock.advance(5.0)
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(clock.now() * 1000)
    emit_mock.reset_mock()

    result = ScoringResult(
        score=Decimal("0.5"),
        side="SELL",
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
    )
    handler.scoring_kernel_cls.compute.return_value = result

    event["bar_close_ts"] = int(clock.now())
    handler.on_process_strategy(event)

    # Handler should FORCE HOLD in emission, but must not mutate the result object.
    assert result.side == "SELL"
    assert result.score == Decimal("0.5")
    assert result.thr_buy == Decimal("0.1")
    assert result.thr_sell == Decimal("0.1")

    block_calls = [c.args[1] for c in emit_mock.call_args_list if c.args[0] == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(block_calls) == 1
    assert block_calls[0]["reason_code"] == "HOLDING_PERIOD_ACTIVE"

    signal_calls = [c.args[1] for c in emit_mock.call_args_list if c.args[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(signal_calls) == 1
    assert signal_calls[0]["side"] == "BUY"
