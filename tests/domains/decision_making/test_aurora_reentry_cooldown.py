import logging
import pytest
import time
from unittest.mock import MagicMock, patch
from decimal import Decimal
from types import SimpleNamespace

from apps.reference.domains.decision_making.aurora_handler import (
    AuroraHandler,
    SymbolState,
)
from apps.reference.domains.decision_making.aurora_scoring_kernel import ScoringResult

# Setup logger to suppress noise during tests
logging.basicConfig(level=logging.ERROR)

@pytest.fixture
def mock_emit():
    return MagicMock()

@pytest.fixture
def mock_config():
    from types import SimpleNamespace
    config = SimpleNamespace()
    config.strategies = SimpleNamespace()
    config.strategies.aurora = SimpleNamespace()
    config.strategies.aurora.timeframe_sec = 300
    config.strategies.aurora.decision = SimpleNamespace()
    config.strategies.aurora.decision.signals = SimpleNamespace()
    config.strategies.aurora.decision.signals.normalize_signals_mode = "signed_v2"
    config.strategies.aurora.decision.signals.enable_new_metrics = True
    config.strategies.aurora.decision.signals.delta_price_cap_pct = "0.005"
    config.strategies.aurora.decision.neutral_threshold = "0.05"
    config.strategies.aurora.decision.signal_threshold = "0.1"
    
    # Explicitly False to avoid MagicMock truthiness trap
    config.strategies.aurora.decision.holding_period = SimpleNamespace(enabled=False)
    config.strategies.aurora.decision.anti_churn = SimpleNamespace(enabled=False)
    config.strategies.aurora.decision.gates = SimpleNamespace(enabled=False)
    
    config.strategies.aurora.decision.reentry_cooldown_sec = 60
    
    config.strategies.aurora.assets = {}
    return config

@pytest.fixture
def handler(mock_config, mock_emit, manual_clock):
    h = AuroraHandler(
        config=mock_config, 
        emit_fn=mock_emit,
        monotonic_fn=manual_clock,
        wall_time_fn=manual_clock.now_sec
    )
    h._is_symbol_enabled = lambda s: True
    h._get_instrument_config = lambda s: MagicMock(
        reentry_cooldown_sec=None,
        signal_threshold=None,
        neutral_threshold=None,
        holding_period=None,
        volatility_entry_logic=SimpleNamespace(enabled=False),
        allowed_regimes=["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY"],
    )
    h._check_warmup = lambda s: True
    state = SymbolState()
    # DM-CRITICAL-PATCHES-02: Inject heartbeat to satisfy liveness guard
    state.last_regime_heartbeat_ms = int(time.time() * 1000)
    state.regime = "TREND_UP"
    h._symbol_states["BTCUSDT"] = state
    # Explicitly disable holding period to prevent interference in other tests
    h.holding_period_enabled = False
    return h

class TestReentryCooldown:

    def _make_cmd(self, symbol, price=10000):
        return {
            "symbol": symbol,
            "tf_sec": 300,
            "bar_close_ts": 1234567890,
            "bar": {
                "close": price, "open": price, "high": price, "low": price, "volume": 100
            },
            "features": {"price": price, "atr": 10},
            "warmup": {"full_ready": True}
        }

    def test_exit_tracking(self, handler, manual_clock):
        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        
        state.position_side = "buy"
        state.last_signal_side = "buy"
        
        cmd = self._make_cmd(symbol)
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.02"),
            side="",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
            deferred=False, defer_reason=None
        )
        handler.scoring_kernel_cls = MockKernel
        
        handler.on_process_strategy(cmd)
        
        assert state.position_side == ""
        assert state.last_exit_timestamp == manual_clock.monotonic()

    def test_block_reentry_within_cooldown(self, handler, mock_emit, manual_clock):
        symbol = "BTCUSDT"
        now = manual_clock.monotonic()
        
        state = handler._symbol_states[symbol]
        state.last_exit_timestamp = now - 10
        state.position_side = ""
        
        cmd = self._make_cmd(symbol)
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.8"),
            side="buy",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
            deferred=False, defer_reason=None
        )
        handler.scoring_kernel_cls = MockKernel
        
        handler.on_process_strategy(cmd)
        
        blocked_calls = [
            c for c in mock_emit.call_args_list 
            if c[0][0] == "EVT:STRATEGY_DECISION_BLOCKED" and c[0][1]["reason_code"] == "REENTRY_COOLDOWN"
        ]
        assert len(blocked_calls) == 1
        
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 0

    def test_allow_reentry_after_cooldown(self, handler, mock_emit, manual_clock):
        symbol = "BTCUSDT"
        now = manual_clock.monotonic()
        
        state = handler._symbol_states[symbol]
        state.last_exit_timestamp = now - 65
        state.position_side = ""
        # Refresh heartbeat to pass liveness guard
        state.last_regime_heartbeat_ms = int(manual_clock.now_sec() * 1000)
        
        cmd = self._make_cmd(symbol)
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.8"),
            side="buy",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
            deferred=False, defer_reason=None
        )
        handler.scoring_kernel_cls = MockKernel
        
        handler.on_process_strategy(cmd)
        
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 1

    def test_per_symbol_cooldown_override(self, handler, mock_emit, manual_clock):
        symbol = "FAST_BTC"
        handler._symbol_states[symbol] = SymbolState()
        state = handler._symbol_states[symbol]
        state.last_regime_heartbeat_ms = int(manual_clock.now_sec() * 1000)
        state.regime = "TREND_UP"
        
        mock_instr_cfg = MagicMock()
        mock_instr_cfg.reentry_cooldown_sec = 30
        mock_instr_cfg.volatility_entry_logic = SimpleNamespace(enabled=False)
        mock_instr_cfg.signal_threshold = None 
        mock_instr_cfg.neutral_threshold = None
        mock_instr_cfg.holding_period = None
        mock_instr_cfg.allowed_regimes = ["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY"]
        
        handler._get_instrument_config = lambda s: mock_instr_cfg if s == symbol else MagicMock(reentry_cooldown_sec=None)
        
        now = manual_clock.monotonic()
        state.last_exit_timestamp = now - 35
        state.position_side = ""
        
        cmd = self._make_cmd(symbol)
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.8"),
            side="buy",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
            deferred=False, defer_reason=None
        )
        handler.scoring_kernel_cls = MockKernel
        
        handler.on_process_strategy(cmd)
        
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 1

    def test_holding_period_forced_hold_preserves_side(self, handler, mock_emit, manual_clock):
        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        
        now = manual_clock.monotonic()
        state.position_side = "buy"
        state.entry_timestamp = now - 5
        # Refresh heartbeat to pass liveness guard
        state.last_regime_heartbeat_ms = int(manual_clock.now_sec() * 1000)
        
        handler.holding_period_enabled = True
        handler.default_min_duration_sec = 30
        
        cmd = self._make_cmd(symbol)
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("-0.5"),
            side="sell",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
            deferred=False, defer_reason=None
        )
        handler.scoring_kernel_cls = MockKernel
        
        assert handler.holding_period_enabled == True
        
        handler.on_process_strategy(cmd)
        
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 1
        
        emitted_signal = produced_calls[0][0][1]
        assert emitted_signal["side"] == "BUY"
