import logging
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import time

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
    config = MagicMock()
    # Basic signals config
    config.strategies.aurora.decision.signals.delta_price_cap_pct = "0.005"
    config.strategies.aurora.decision.neutral_threshold = "0.05"
    config.strategies.aurora.decision.signal_threshold = "0.1"
    
    # Defaults
    config.strategies.aurora.decision.holding_period.enabled = False
    
    # Re-entry defaults
    config.strategies.aurora.decision.reentry_cooldown_sec = 60
    
    # Instrument config (default mock)
    def get_instrument_config(symbol):
        cfg = MagicMock()
        cfg.reentry_cooldown_sec = None  # Use global default
        cfg.holding_period = None
        return cfg
    
    # This must be attached to the actual handler instance in tests due to how _get_instrument_config works
    # We'll patch AuroraHandler._get_instrument_config mostly
    return config

@pytest.fixture
def handler(mock_config, mock_emit):
    # Initialize with mocked config
    h = AuroraHandler(config=mock_config, emit_fn=mock_emit)
    # Monkeypatch _is_symbol_enabled to always return True for test symbols
    h._is_symbol_enabled = lambda s: True
    # Monkeypatch _get_instrument_config
    h._get_instrument_config = lambda s: MagicMock(
        reentry_cooldown_sec=None,
        signal_threshold=None,
        neutral_threshold=None,
        holding_period=None
    )
    # Monkeypatch _check_warmup to always allow processing
    h._check_warmup = lambda s: True
    
    # Setup initial state for BTCUSDT
    h._symbol_states["BTCUSDT"] = SymbolState()
    # Explicitly disable holding period to prevent interference
    h.holding_period_enabled = False
    return h

class TestReentryCooldown:

    def test_exit_tracking(self, handler):
        """Verify that transitioning from position to neutral tracks exit timestamp."""
        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        
        # 1. Setup: In a LONG position
        state.position_side = "buy"
        state.last_signal_side = "buy"
        
        # 2. Event: Neutral signal (EXIT)
        event = {
            "symbol": symbol,
            "features": {"price": 10000},
            "warmup": {"full_ready": True}
        }
        
        # Dependency Injection
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.02"), # Below 0.05 threshold
            side="",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
        )
        handler.scoring_kernel_cls = MockKernel
        
        # Action
        handler.on_features_calculated(event)
        
        # 3. Assertions
        assert state.position_side == ""
        assert state.last_exit_timestamp is not None
        assert state.last_exit_timestamp > 0

    def test_block_reentry_within_cooldown(self, handler, mock_emit):
        """Verify entry is blocked if within cooldown period."""
        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        
        # 1. Setup: Recently exited
        now = time.time()
        state.last_exit_timestamp = now - 10 # Exited 10s ago
        state.position_side = "" # Flat
        
        # 2. Event: Strong BUY signal
        event = {
            "symbol": symbol,
            "features": {"price": 10000},
            "warmup": {"full_ready": True}
        }
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.8"), # Strong buy
            side="buy",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
        )
        handler.scoring_kernel_cls = MockKernel
        
        # Action
        handler.on_features_calculated(event)
        
        # 3. Assertions
        # Expect EVT:STRATEGY_DECISION_BLOCKED
        blocked_calls = [
            c for c in mock_emit.call_args_list 
            if c[0][0] == "EVT:STRATEGY_DECISION_BLOCKED" and c[0][1]["reason_code"] == "REENTRY_COOLDOWN"
        ]
        assert len(blocked_calls) == 1
        
        # Should NOT have emitted PRODUCED
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 0

    def test_allow_reentry_after_cooldown(self, handler, mock_emit):
        """Verify entry is allowed after cooldown period expires."""
        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        
        # 1. Setup: Exited long ago
        now = time.time()
        state.last_exit_timestamp = now - 65 # Exited 65s ago (default cooldown 60s)
        state.position_side = ""
        
        # 2. Event: Strong BUY signal
        event = {
            "symbol": symbol,
            "features": {"price": 10000},
            "warmup": {"full_ready": True}
        }
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.8"),
            side="buy",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
        )
        handler.scoring_kernel_cls = MockKernel
        
        # Action
        handler.on_features_calculated(event)
        
        # 3. Assertions
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 1

    def test_per_symbol_cooldown_override(self, handler, mock_emit):
        """Verify per-symbol config overrides global cooldown."""
        symbol = "FAST_BTC"
        handler._symbol_states[symbol] = SymbolState()
        state = handler._symbol_states[symbol]
        
        # Override config for this symbol -> 30s cooldown
        mock_instr_cfg = MagicMock()
        mock_instr_cfg.reentry_cooldown_sec = 30
        mock_instr_cfg.signal_threshold = None # Fix Decimal error
        mock_instr_cfg.neutral_threshold = None
        mock_instr_cfg.holding_period = None
        
        # Patch just for this test
        handler._get_instrument_config = lambda s: mock_instr_cfg if s == symbol else MagicMock(reentry_cooldown_sec=None)
        
        # Setup: Exited 35s ago (Valid for 30s override, Invalid for 60s global)
        now = time.time()
        state.last_exit_timestamp = now - 35
        state.position_side = ""
        
        event = {
            "symbol": symbol,
            "features": {"price": 10000},
            "warmup": {"full_ready": True}
        }
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("0.8"),
            side="buy",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
        )
        handler.scoring_kernel_cls = MockKernel
        
        handler.on_features_calculated(event)
        
        # Assertion: Should be allowed
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 1

    def test_holding_period_forced_hold_preserves_side(self, handler, mock_emit):
        """Verify that holding period logic forces signal side to persist (Fix for suppression bug)."""
        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        
        # 1. Setup: In position, entered recently
        now = time.time()
        state.position_side = "buy"
        state.entry_timestamp = now - 5 # Entered 5s ago
        # Enable holding period
        handler.holding_period_enabled = True
        handler.default_min_duration_sec = 30
        
        # 2. Event: FLIP signal (Sell)
        event = {
            "symbol": symbol,
            "features": {"price": 10000},
            "warmup": {"full_ready": True}
        }
        
        MockKernel = MagicMock()
        MockKernel.compute.return_value = ScoringResult(
            score=Decimal("-0.5"), # Moderate SELL (below emergency threshold 0.7)
            side="sell",
            thr_buy=Decimal("0.1"), thr_sell=Decimal("0.1"),
        )
        handler.scoring_kernel_cls = MockKernel
        
        # Check that test-specific enabled overrides fixture
        assert handler.holding_period_enabled == True
        
        # Action
        handler.on_features_calculated(event)
        
        # 3. Assertions
        # Should emit signal with SIDE="buy" (forced hold), NOT "sell" and NOT nothing
        produced_calls = [c for c in mock_emit.call_args_list if c[0][0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
        assert len(produced_calls) == 1
        
        emitted_signal = produced_calls[0][0][1] # The event dict
        assert emitted_signal["side"] == "BUY" # PRODUCED emits UPPER CASE side ("BUY"/"SELL")
