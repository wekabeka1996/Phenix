"""
Unit tests for Aurora Minimum Holding Period logic (Anti-Churn Gate).

Tests:
1. Exit blocked within holding period
2. Exit allowed after holding period
3. Emergency override within holding period
4. Flip blocked within holding period
5. Flip allowed after holding period
6. Per-symbol config override
7. Feature disabled behavior
8. Fail-open when entry_timestamp is None

RFC: docs/RFC_min_duration_logic.md
"""
import decimal
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# Create a minimal ScoringResult for testing
@dataclass
class MockScoringResult:
    """Mock ScoringResult for testing."""
    score: decimal.Decimal
    side: str
    thr_buy: decimal.Decimal = decimal.Decimal("0.1")
    thr_sell: decimal.Decimal = decimal.Decimal("0.1")
    why_chain: List[str] = None
    psi_vector: Dict[str, Any] = None
    regime: Optional[str] = None
    deferred: bool = False
    defer_reason: Optional[str] = None
    
    def __post_init__(self):
        if self.why_chain is None:
            self.why_chain = []
        if self.psi_vector is None:
            self.psi_vector = {}


def create_mock_config(
    holding_period_enabled: bool = True,
    min_duration_sec: float = 30.0,
    emergency_threshold: float = 0.7,
    apply_to_flips: bool = True,
    per_symbol_overrides: Optional[Dict[str, Dict]] = None,
):
    """Create a mock config object for AuroraHandler."""
    # Create holding_period config
    hp_cfg = MagicMock()
    hp_cfg.enabled = holding_period_enabled
    hp_cfg.min_duration_sec = min_duration_sec
    hp_cfg.emergency_exit_threshold = emergency_threshold
    hp_cfg.apply_to_flips = apply_to_flips
    
    # Create decision config
    decision = MagicMock()
    decision.signal_threshold = 0.1
    decision.side_bias_window_sec = 420
    decision.side_bias_target_ratio = 0.72
    decision.side_bias_penalty_factor = 0.25
    decision.side_bias_min_intents = 18
    decision.regime_threshold_multipliers = {"DEFAULT": 1.0}
    decision.operational_mode = "paranoid"
    decision.neutral_threshold = 0.05
    decision.holding_period = hp_cfg
    decision.direction_strength_scoring = None
    decision.signals = None
    decision.gates = None
    decision.anti_churn = None
    decision.reentry_cooldown_sec = None
    decision.scoring_version = "quadratic"
    decision.scoring_engine = None
    decision.quadratic_rollout = None
    decision.exit = None
    decision.execution = None
    decision.dashboard = None
    
    # Create assets config with per-symbol overrides
    assets = {}
    if per_symbol_overrides:
        for symbol, overrides in per_symbol_overrides.items():
            asset = MagicMock()
            asset.enabled = True
            if "holding_period" in overrides:
                hp_override = MagicMock()
                hp_override.min_duration_sec = overrides["holding_period"].get("min_duration_sec")
                hp_override.emergency_exit_threshold = overrides["holding_period"].get("emergency_exit_threshold")
                asset.holding_period = hp_override
            else:
                asset.holding_period = None
            asset.signal_threshold = None
            asset.neutral_threshold = None
            asset.weights = None
            asset.feature_neutrals = None
            asset.essential_features = None
            assets[symbol] = asset
    
    # Build full config
    aurora = MagicMock()
    aurora.timeframe_sec = 300
    aurora.decision = decision
    aurora.assets = assets
    
    strategies = MagicMock()
    strategies.aurora = aurora
    
    config = MagicMock()
    config.strategies = strategies
    
    return config


class ControllableClock:
    """A controllable clock for testing monotonic time."""
    def __init__(self, start: float = 0.0):
        self._time = start
    
    def __call__(self) -> float:
        return self._time
    
    def set(self, t: float) -> None:
        self._time = t
    
    def advance(self, delta: float) -> None:
        self._time += delta


def create_handler_with_config(config, clock: ControllableClock = None):
    """Create AuroraHandler with given config and optional controllable clock."""
    from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
    
    emit_fn = MagicMock()
    kwargs = {"config": config, "emit_fn": emit_fn, "strategy_id": "aurora"}
    if clock is not None:
        kwargs["monotonic_fn"] = clock
    handler = AuroraHandler(**kwargs)
    return handler


class TestHoldingPeriodBlocking:
    """Test exit blocking within holding period."""
    
    def test_exit_blocked_at_t_plus_10s(self):
        """
        Test that soft exit is blocked at T+10s (within 30s holding period).
        
        Scenario:
        - Entry at T=0
        - Flip signal at T=10s
        - Expected: BLOCKED (time_in_position=10s < min_duration=30s)
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
            emergency_threshold=0.7,
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 10 seconds
        clock.advance(10)  # T=1010
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),  # Flip signal (opposite direction)
            side="sell",
        )
        
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is True
    
    def test_exit_allowed_at_t_plus_31s(self):
        """
        Test that soft exit is allowed at T+31s (after 30s holding period).
        
        Scenario:
        - Entry at T=0
        - Flip signal at T=31s
        - Expected: ALLOWED (time_in_position=31s >= min_duration=30s)
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 31 seconds
        clock.advance(31)  # T=1031
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),
            side="sell",
        )
        
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is False
    
    def test_emergency_override_at_t_plus_5s(self):
        """
        Test that emergency exit is allowed even at T+5s.
        
        Scenario:
        - Entry at T=0
        - Score drops to -0.85 (|score| > 0.7 emergency threshold)
        - Flip signal at T=5s
        - Expected: ALLOWED (emergency override)
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
            emergency_threshold=0.7,
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 5 seconds
        clock.advance(5)  # T=1005
        result = MockScoringResult(
            score=decimal.Decimal("-0.85"),  # Emergency level!
            side="sell",
        )
        
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is False  # Emergency override


class TestFlipBehavior:
    """Test flip signal handling with holding period."""
    
    def test_flip_blocked_within_holding_period(self):
        """
        Test that flip (buy→sell) is blocked within holding period.
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
            apply_to_flips=True,
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("BTCUSDT", "buy")
        
        # Advance time by 15 seconds
        clock.advance(15)  # T=1015
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),  # Flip signal
            side="sell",
        )
        
        should_suppress = handler._should_suppress_soft_exit(
            "BTCUSDT", result, is_flip=True
        )
        
        assert should_suppress is True
    
    def test_flip_allowed_when_apply_to_flips_false(self):
        """
        Test that flip is allowed when apply_to_flips=False.
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
            apply_to_flips=False,  # Don't apply to flips
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("BTCUSDT", "buy")
        
        # Advance time by 10 seconds (within holding period)
        clock.advance(10)  # T=1010
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),
            side="sell",
        )
        
        # Should NOT suppress because apply_to_flips=False
        should_suppress = handler._should_suppress_soft_exit(
            "BTCUSDT", result, is_flip=True
        )
        assert should_suppress is False


class TestConfigOverride:
    """Test per-symbol configuration override."""
    
    def test_per_symbol_min_duration(self):
        """
        Test that per-symbol min_duration_sec overrides global.
        
        Config:
        - Global: min_duration_sec = 30
        - ETHUSDT: min_duration_sec = 45
        
        At T+35s: global would allow, per-symbol should block.
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
            per_symbol_overrides={
                "ETHUSDT": {
                    "holding_period": {
                        "min_duration_sec": 45.0,
                    }
                }
            }
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 35 seconds
        clock.advance(35)  # T=1035
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),
            side="sell",
        )
        
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        # Per-symbol: 45s, time_in_position: 35s → should block
        assert should_suppress is True
    
    def test_per_symbol_emergency_threshold(self):
        """
        Test that per-symbol emergency_exit_threshold overrides global.
        
        Config:
        - Global: emergency_exit_threshold = 0.7
        - ETHUSDT: emergency_exit_threshold = 0.5
        
        Score = -0.6: global would NOT trigger, per-symbol SHOULD trigger.
        """
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
            emergency_threshold=0.7,  # Global
            per_symbol_overrides={
                "ETHUSDT": {
                    "holding_period": {
                        "emergency_exit_threshold": 0.5,  # Lower threshold
                    }
                }
            }
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 5 seconds
        clock.advance(5)  # T=1005
        result = MockScoringResult(
            score=decimal.Decimal("-0.6"),  # Between 0.5 and 0.7
            side="sell",
        )
        
        # Per-symbol threshold is 0.5, |score|=0.6 >= 0.5 → emergency override
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is False  # Emergency override triggered


class TestFeatureDisabled:
    """Test behavior when holding period feature is disabled."""
    
    def test_exit_allowed_when_disabled(self):
        """Exit always allowed when holding_period.enabled = false."""
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=False,  # Disabled
            min_duration_sec=30.0,
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 5 seconds (well within holding period)
        clock.advance(5)  # T=1005
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),
            side="sell",
        )
        
        # Feature disabled → never suppress
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is False


class TestFailOpen:
    """Test fail-open behavior when entry_timestamp is unknown."""
    
    def test_exit_allowed_when_no_entry_tracked(self):
        """
        Test that exit is allowed when entry_timestamp is None.
        
        This is the fail-open behavior: if we don't know when entry happened
        (e.g., after restart), allow the exit rather than blocking indefinitely.
        """
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
        )
        handler = create_handler_with_config(config)
        
        # Do NOT track entry - simulating unknown state after restart
        # Just set position_side to simulate that we know we have a position
        state = handler._symbol_states["ETHUSDT"]
        state.position_side = "buy"
        state.entry_timestamp = None  # Unknown!
        
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),
            side="sell",
        )
        
        # Should NOT suppress because entry_timestamp is None (fail-open)
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is False


class TestHelperMethods:
    """Test helper methods for holding period."""
    
    def test_track_entry_sets_timestamp_and_side(self):
        """Test that _track_entry correctly sets entry_timestamp and position_side."""
        test_time = 1234567890.123
        clock = ControllableClock(start=test_time)
        config = create_mock_config()
        handler = create_handler_with_config(config, clock=clock)
        
        handler._track_entry("BTCUSDT", "BUY")
        
        state = handler._symbol_states["BTCUSDT"]
        assert state.entry_timestamp == test_time
        assert state.position_side == "buy"
    
    def test_clear_entry_resets_state(self):
        """Test that _clear_entry correctly resets entry tracking."""
        clock = ControllableClock(start=1000.0)
        config = create_mock_config()
        handler = create_handler_with_config(config, clock=clock)
        
        # First, track an entry
        handler._track_entry("BTCUSDT", "buy")
        
        # Then clear it
        handler._clear_entry("BTCUSDT")
        
        state = handler._symbol_states["BTCUSDT"]
        assert state.entry_timestamp is None
        assert state.position_side == ""
    
    def test_is_emergency_exit_threshold_check(self):
        """Test emergency exit threshold calculation."""
        config = create_mock_config(
            holding_period_enabled=True,
            emergency_threshold=0.7,
        )
        handler = create_handler_with_config(config)
        
        # Below threshold
        assert handler._is_emergency_exit(decimal.Decimal("0.5"), "ETHUSDT") is False
        assert handler._is_emergency_exit(decimal.Decimal("-0.5"), "ETHUSDT") is False
        
        # At threshold
        assert handler._is_emergency_exit(decimal.Decimal("0.7"), "ETHUSDT") is True
        assert handler._is_emergency_exit(decimal.Decimal("-0.7"), "ETHUSDT") is True
        
        # Above threshold
        assert handler._is_emergency_exit(decimal.Decimal("0.9"), "ETHUSDT") is True
        assert handler._is_emergency_exit(decimal.Decimal("-0.9"), "ETHUSDT") is True
    
    def test_get_min_duration_sec_fallback(self):
        """Test min_duration_sec fallback to global."""
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
        )
        handler = create_handler_with_config(config)
        
        # Symbol without per-symbol override should use global
        duration = handler._get_min_duration_sec("UNKNOWN_SYMBOL")
        assert duration == 30.0
    
    def test_get_emergency_threshold_fallback(self):
        """Test emergency_exit_threshold fallback to global."""
        config = create_mock_config(
            holding_period_enabled=True,
            emergency_threshold=0.7,
        )
        handler = create_handler_with_config(config)
        
        # Symbol without per-symbol override should use global
        threshold = handler._get_emergency_threshold("UNKNOWN_SYMBOL")
        assert threshold == 0.7


class TestEmitBlocked:
    """Test that blocked events are emitted correctly."""
    
    def test_blocked_event_emitted_when_suppressed(self):
        """Test that EVT:STRATEGY_DECISION_BLOCKED is emitted when exit is suppressed."""
        clock = ControllableClock(start=1000.0)
        config = create_mock_config(
            holding_period_enabled=True,
            min_duration_sec=30.0,
        )
        handler = create_handler_with_config(config, clock=clock)
        
        # Simulate entry at T=1000
        handler._track_entry("ETHUSDT", "buy")
        
        # Advance time by 10 seconds
        clock.advance(10)  # T=1010
        result = MockScoringResult(
            score=decimal.Decimal("-0.15"),
            side="sell",
        )
        
        should_suppress = handler._should_suppress_soft_exit("ETHUSDT", result, is_flip=True)
        
        assert should_suppress is True
        
        # Check that emit_fn was called with EVT:STRATEGY_DECISION_BLOCKED
        handler.emit_fn.assert_called()
        call_args = handler.emit_fn.call_args
        event_name = call_args[0][0]
        payload = call_args[0][1]
        
        assert event_name == "EVT:STRATEGY_DECISION_BLOCKED"
        assert payload["reason_code"] == "HOLDING_PERIOD_ACTIVE"
        assert payload["symbol"] == "ETHUSDT"
        assert "time_in_position_sec" in payload["details"]
        assert "min_duration_sec" in payload["details"]
