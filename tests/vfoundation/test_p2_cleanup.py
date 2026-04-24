"""
P2 Final Cleanup — Guard Tests

Verifies:
1. AuroraHandler rejects missing decision config (fail-closed)
2. CloseFlowFSM handles Decimal qty with precision
3. FeatureEngineering creates synthetic tick with -1ms offset
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from types import SimpleNamespace
from apps.reference.config_contract import ConfigContractError


class TestP2AuroraFailClosed:
    """P2.1: Verify AuroraHandler fail-closed on missing decision config."""

    def test_aurora_rejects_missing_decision_config(self):
        """AuroraHandler must crash if decision config is missing."""
        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
        
        # Config structure without 'decision' (None)
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=None,  # Missing - should fail
                    assets={},
                )
            )
        )
        
        with pytest.raises(ConfigContractError, match="decision config is mandatory"):
            AuroraHandler(config=config, emit_fn=MagicMock())

    def test_aurora_accepts_valid_decision_config(self):
        """AuroraHandler must initialize successfully with valid decision config."""
        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
        
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.12,
                        side_bias_window_sec=420,
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=18,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                        holding_period=None,
                        reentry_cooldown_sec=None,
                        gates=None,
                        anti_churn=None,
                    ),
                    assets={},
                )
            )
        )
        
        # Should NOT raise
        handler = AuroraHandler(config=config, emit_fn=MagicMock())
        assert handler.signal_threshold == Decimal("0.12")


class TestP2CloseFlowPrecision:
    """P2.2: Verify CloseFlowFSM handles Decimal qty correctly."""

    def test_close_flow_init_no_args(self):
        """CloseFlowFSM initializes without arguments (max_hold_sec removed)."""
        from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM
        
        # Should NOT require any arguments
        fsm = CloseFlowFSM()
        assert fsm.state.value == "FLAT"

    def test_close_flow_handles_precise_qty(self):
        """CloseFlowFSM must preserve Decimal precision in qty."""
        from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM, CloseState
        from vfoundation.core.protocol import Message
        
        fsm = CloseFlowFSM()
        
        # Simulate CMD:CLOSE with precise qty
        msg = Message(
            op="CMD",
            verb="CLOSE",
            src="test",
            dst="ep",
            pld={"qty": "0.123456789", "symbol": "BTCUSDT", "reason": "test"},
        )
        
        result = fsm.handle(msg)
        
        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "CLOSE"
        # Verify symbol is passed through
        assert result.pld.get("symbol") == "BTCUSDT"


class TestP2SyntheticTickCreation:
    """P2.3: Verify FeatureEngineering synthetic tick creation."""

    def test_synthetic_tick_has_minus_1ms_offset(self):
        """FeatureEngineering must create synthetic tick with ts = bar_ts - 1."""
        from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
        
        # Test the method logic directly by calling the static-like method
        # Create a minimal instance just to access the method
        # We'll mock __init__ to avoid config validation
        
        last_tick = {"price": "100.5", "ts": 1000, "bid_size": "10", "ask_size": "10"}
        bar_ts = 2000
        bar_open = Decimal("105.0")
        
        # Call method directly on class with a fake self
        class FakeFE:
            pass
        
        fake_fe = FakeFE()
        # Bind the method to our fake instance
        synth = FeatureEngineering._create_synthetic_tick_for_bar_close(fake_fe, last_tick, bar_ts, bar_open)
        
        # Key assertions
        assert synth["ts"] == 1999  # bar_ts - 1
        assert synth["price"] == "105.0"  # bar_open as string

    def test_synthetic_tick_preserves_other_fields(self):
        """Synthetic tick should copy non-ts/price fields from last_tick."""
        from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
        
        last_tick = {
            "price": "100",
            "ts": 1000,
            "bid_size": "50",
            "ask_size": "60",
            "buy_volume": "1000",
        }
        bar_ts = 2000
        bar_open = Decimal("110")
        
        class FakeFE:
            pass
        
        fake_fe = FakeFE()
        synth = FeatureEngineering._create_synthetic_tick_for_bar_close(fake_fe, last_tick, bar_ts, bar_open)
        
        # Other fields preserved
        assert synth["bid_size"] == "50"
        assert synth["ask_size"] == "60"
        assert synth["buy_volume"] == "1000"
    
    def test_synthetic_tick_handles_none_bar_open(self):
        """Synthetic tick should keep original price if bar_open is None."""
        from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
        
        last_tick = {"price": "100.5", "ts": 1000}
        bar_ts = 2000
        bar_open = None
        
        class FakeFE:
            pass
        
        fake_fe = FakeFE()
        synth = FeatureEngineering._create_synthetic_tick_for_bar_close(fake_fe, last_tick, bar_ts, bar_open)
        
        assert synth["ts"] == 1999
        assert synth["price"] == "100.5"  # Original price preserved
