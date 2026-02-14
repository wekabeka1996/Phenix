"""
REG-FIX-01 Tests: BAR-ONLY SSOT for RegimeDetector.

Tests:
1. Regime updates only on basis_tf_sec bars (tick events ignored)
2. No double-clocking at bar close
3. Missing uncertain_cutoff fails config load
4. Time discipline (Clock migration)
"""

import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.core.time.clock import MockClock


class TestRegimeBarOnlyFilter:
    """Test that RegimeDetector only processes basis_tf_sec events."""

    @pytest.fixture
    def mock_fsm(self):
        """Create mock FSM."""
        fsm = MagicMock()
        fsm.emit = MagicMock()
        fsm.listen = MagicMock()
        return fsm

    @pytest.fixture
    def mock_config(self):
        """Create minimal config with required regime fields."""
        return SimpleNamespace(
            basis_tf_sec=300,  # 5-minute bars
            uncertain_cutoff=0.35,
            hysteresis_bars=3,
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(
                    sma_short_period=10,
                    sma_long_period=50,
                    confidence_multiplier=20.0,
                    confidence_min=0.5,
                    confidence_max=0.95,
                ),
                volatility=SimpleNamespace(
                    enabled=False,
                    atr_period=14,
                    atr_sma_length=100,
                    allow_close_to_close_atr=True,
                    threshold_multiplier=2.0,
                    low_vol_multiplier=0.5,
                    high_vol_confidence_multiplier=2.0,
                    low_vol_confidence_multiplier=3.0,
                ),
                mean_reversion=SimpleNamespace(
                    threshold=0.005,
                    confidence_multiplier=100.0,
                ),
            ),
            system=SimpleNamespace(
                market_data=SimpleNamespace(tick_ttl_ms=5000),
            ),
        )

    @pytest.fixture
    def mock_message(self):
        """Factory for creating mock Message objects."""
        def _make(verb: str, pld: dict):
            return SimpleNamespace(verb=verb, pld=pld)
        return _make

    def test_regime_updates_only_on_basis_bar(self, mock_fsm, mock_config, mock_message):
        """Regime should only update when tf_sec matches basis_tf_sec."""
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

        clock = MockClock(start_ms=1000000)
        detector = RegimeDetector(mock_config, mock_fsm, clock=clock)

        # Tick-level event (tf_sec=0) should be IGNORED
        tick_event = mock_message("FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "ts": 1000000,
            "tf_sec": 0,  # Tick level
            "features": {"price": "50000"},
        })
        detector.handle_event(tick_event)
        assert mock_fsm.emit.call_count == 0, "Tick events should not trigger regime emission"

        # Bar event (tf_sec=300) should be PROCESSED
        bar_event = mock_message("FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "ts": 1000000,
            "tf_sec": 300,  # 5-minute bar
            "features": {"price": "50000"},
        })
        detector.handle_event(bar_event)
        assert mock_fsm.emit.call_count == 1, "Bar events should trigger regime emission"
        
        call_args = mock_fsm.emit.call_args
        assert call_args[0][0] == "EVT:REGIME_DETECTED"

    def test_no_double_clocking_at_bar_close(self, mock_fsm, mock_config, mock_message):
        """Only one regime update per bar, even if multiple events arrive."""
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

        clock = MockClock(start_ms=1000000)
        detector = RegimeDetector(mock_config, mock_fsm, clock=clock)

        # First bar event
        bar_event_1 = mock_message("FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "ts": 1000000,
            "tf_sec": 300,
            "features": {"price": "50000"},
        })
        detector.handle_event(bar_event_1)
        
        # Tick event (should be ignored, NOT counted)
        tick_event = mock_message("FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "ts": 1000100,
            "tf_sec": 0,
            "features": {"price": "50001"},
        })
        detector.handle_event(tick_event)
        
        # Second bar event (5 mins later)
        bar_event_2 = mock_message("FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "ts": 1300000,
            "tf_sec": 300,
            "features": {"price": "50100"},
        })
        detector.handle_event(bar_event_2)

        # Should have exactly 2 regime emissions (one per bar)
        assert mock_fsm.emit.call_count == 2, "Should have exactly 2 regime emissions for 2 bars"

    def test_different_tf_sec_ignored(self, mock_fsm, mock_config, mock_message):
        """Non-basis timeframes should be ignored."""
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

        clock = MockClock(start_ms=1000000)
        detector = RegimeDetector(mock_config, mock_fsm, clock=clock)

        # 1-minute bar (tf_sec=60) - not basis_tf_sec=300
        event_1m = mock_message("FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "ts": 1000000,
            "tf_sec": 60,  # 1-minute bar
            "features": {"price": "50000"},
        })
        detector.handle_event(event_1m)
        assert mock_fsm.emit.call_count == 0, "Non-basis tf_sec should be ignored"


class TestUncertainCutoff:
    """Test uncertain_cutoff behavior."""

    @pytest.fixture
    def mock_fsm(self):
        fsm = MagicMock()
        fsm.emit = MagicMock()
        fsm.listen = MagicMock()
        return fsm

    @pytest.fixture
    def mock_config_low_cutoff(self):
        """Config with low uncertain_cutoff to allow weak regimes."""
        return SimpleNamespace(
            basis_tf_sec=300,
            uncertain_cutoff=0.1,  # Very low
            hysteresis_bars=3,
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(
                    sma_short_period=2,
                    sma_long_period=3,
                    confidence_multiplier=20.0,
                    confidence_min=0.5,
                    confidence_max=0.95,
                ),
                volatility=SimpleNamespace(enabled=False, atr_period=14, atr_sma_length=100,
                    allow_close_to_close_atr=True, threshold_multiplier=2.0,
                    low_vol_multiplier=0.5, high_vol_confidence_multiplier=2.0,
                    low_vol_confidence_multiplier=3.0),
                mean_reversion=SimpleNamespace(threshold=0.005, confidence_multiplier=100.0),
            ),
            system=SimpleNamespace(market_data=SimpleNamespace(tick_ttl_ms=5000)),
        )

    @pytest.fixture
    def mock_config_high_cutoff(self):
        """Config with high uncertain_cutoff to demote weak regimes."""
        return SimpleNamespace(
            basis_tf_sec=300,
            uncertain_cutoff=0.99,  # Very high - almost all will be demoted
            hysteresis_bars=3,
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(
                    sma_short_period=2,
                    sma_long_period=3,
                    confidence_multiplier=20.0,
                    confidence_min=0.5,
                    confidence_max=0.95,
                ),
                volatility=SimpleNamespace(enabled=False, atr_period=14, atr_sma_length=100,
                    allow_close_to_close_atr=True, threshold_multiplier=2.0,
                    low_vol_multiplier=0.5, high_vol_confidence_multiplier=2.0,
                    low_vol_confidence_multiplier=3.0),
                mean_reversion=SimpleNamespace(threshold=0.005, confidence_multiplier=100.0),
            ),
            system=SimpleNamespace(market_data=SimpleNamespace(tick_ttl_ms=5000)),
        )

    def test_uncertain_cutoff_demotes_low_confidence_trend(
        self, mock_fsm, mock_config_high_cutoff
    ):
        """Low confidence regime should be demoted to UNCERTAIN."""
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

        clock = MockClock(start_ms=1000000)
        detector = RegimeDetector(mock_config_high_cutoff, mock_fsm, clock=clock)

        # Feed enough data to build SMAs
        for i in range(5):
            event = SimpleNamespace(
                verb="FEATURES_CALCULATED",
                pld={
                    "symbol": "BTCUSDT",
                    "ts": 1000000 + i * 300000,
                    "tf_sec": 300,
                    "features": {"price": str(50000 + i * 100)},  # Trending up
                },
            )
            detector.handle_event(event)

        # Last emission should be UNCERTAIN (demoted due to high cutoff)
        last_call = mock_fsm.emit.call_args_list[-1]
        payload = last_call[0][1]
        
        # With cutoff=0.99, even strong trends get demoted
        assert payload["regime"] == "UNCERTAIN", f"Expected UNCERTAIN, got {payload['regime']}"


class TestMissingConfigFails:
    """Test that missing required config fields fail startup."""

    def test_missing_basis_tf_sec_fails_config_load(self):
        """Config without basis_tf_sec should fail validation."""
        from pydantic import ValidationError
        from apps.reference.config_models import AuroraConfig

        # Minimal config WITHOUT basis_tf_sec
        minimal_config = {
            "trading_mode": "testnet",
            "trading": {"mode": "testnet"},
            # ... other required fields omitted for brevity
            # The key is that basis_tf_sec is missing
        }

        # This test verifies the Pydantic model requires basis_tf_sec
        # We can't easily construct full AuroraConfig, so we verify field definition
        import inspect
        from apps.reference.config_models import AuroraConfig as ConfigModel
        
        fields = ConfigModel.model_fields
        assert "basis_tf_sec" in fields, "basis_tf_sec should be a required field"
        assert "uncertain_cutoff" in fields, "uncertain_cutoff should be a required field"
        
        # Verify no defaults (required)
        basis_field = fields["basis_tf_sec"]
        uncertain_field = fields["uncertain_cutoff"]
        
        # In Pydantic v2, required fields have is_required() = True
        assert basis_field.is_required(), "basis_tf_sec should be required (no default)"
        assert uncertain_field.is_required(), "uncertain_cutoff should be required (no default)"


class TestClockMigration:
    """Test Clock abstraction in RegimeDetector."""

    def test_uses_injected_clock(self):
        """RegimeDetector should use injected Clock for time operations."""
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector

        fsm = MagicMock()
        fsm.emit = MagicMock()
        fsm.listen = MagicMock()

        config = SimpleNamespace(
            basis_tf_sec=300,
            uncertain_cutoff=0.35,
            hysteresis_bars=3,
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(
                    sma_short_period=10, sma_long_period=50,
                    confidence_multiplier=20.0, confidence_min=0.5, confidence_max=0.95,
                ),
                volatility=SimpleNamespace(
                    enabled=False, atr_period=14, atr_sma_length=100,
                    allow_close_to_close_atr=True, threshold_multiplier=2.0,
                    low_vol_multiplier=0.5, high_vol_confidence_multiplier=2.0,
                    low_vol_confidence_multiplier=3.0,
                ),
                mean_reversion=SimpleNamespace(threshold=0.005, confidence_multiplier=100.0),
            ),
            system=SimpleNamespace(market_data=SimpleNamespace(tick_ttl_ms=5000)),
        )

        # Inject mock clock at specific time
        mock_clock = MockClock(start_ms=1234567890123)
        detector = RegimeDetector(config, fsm, clock=mock_clock)

        assert detector._clock is mock_clock, "Should use injected clock"
        assert detector._clock.now_ms() == 1234567890123

    def test_no_time_module_in_regime_detector(self):
        """RegimeDetector should not use time.time() directly."""
        import ast
        from pathlib import Path

        regime_detector_path = Path(__file__).parent.parent.parent.parent / \
            "apps/reference/domains/regime_detector/regime_detector.py"

        source = regime_detector_path.read_text()
        tree = ast.parse(source)

        time_time_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and 
                        node.func.value.id == "time" and 
                        node.func.attr == "time"):
                        time_time_calls.append(node.lineno)

        assert len(time_time_calls) == 0, \
            f"Found time.time() calls at lines {time_time_calls}. Use Clock abstraction."
