# tests/integration/test_market_data_to_features_flow.py
"""
Integration test: MarketDataConnector → FeatureEngineering → EVT:FEATURES_CALCULATED

Tests the flow: live market data → features calculation → features event emission
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from vfoundation.core import FSMCore
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering


class TestMarketDataToFeaturesFlow:
    """Test the complete flow from market data to features calculation."""

    def test_features_calculation_from_market_ticks(self):
        """Test that FeatureEngineering calculates features from market tick events."""
        # Arrange
        fsm = FSMCore()
        config = {"trading": {}}

        # Create FeatureEngineering domain
        feature_engineering = FeatureEngineering(fsm, config)

        # Mock the emit method to capture events
        emitted_events = []

        def mock_emit(event_name, payload=None, why=None, **kwargs):
            emitted_events.append({
                'event': event_name,
                'payload': payload,
                'why': why
            })

        fsm.emit = mock_emit

        # Act: Simulate first market tick (no features calculated yet)
        from vfoundation.core.protocol import Message

        first_tick_msg = Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="market_data",
            dst="feature_engineering",
            pld={
                "symbol": "BTCUSDT",
                "bid": "50000.0",
                "ask": "50001.0",
                "bid_size": "10.0",
                "ask_size": "15.0",
                "buy_volume": "100.0",
                "sell_volume": "80.0",
                "price": "50000.5",
                "ts": 1000
            }
        )

        # Emit first tick - should not trigger features (no previous tick)
        feature_engineering.on_market_tick(first_tick_msg)

        # Check that no FEATURES_CALCULATED event was emitted
        features_events = [e for e in emitted_events if e['event'] == 'EVT:FEATURES_CALCULATED']
        assert len(features_events) == 0, "No features should be calculated on first tick"

        # Act: Simulate second market tick
        second_tick_msg = Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="market_data",
            dst="feature_engineering",
            pld={
                "symbol": "BTCUSDT",
                "bid": "50001.0",
                "ask": "50002.0",
                "bid_size": "12.0",
                "ask_size": "18.0",
                "buy_volume": "120.0",
                "sell_volume": "90.0",
                "price": "50001.5",
                "ts": 1500  # 500ms difference instead of 1000ms
            }
        )

        # Emit second tick - should trigger features calculation
        feature_engineering.on_market_tick(second_tick_msg)

        # Assert: Check that FEATURES_CALCULATED event was emitted
        features_events = [e for e in emitted_events if e['event'] == 'EVT:FEATURES_CALCULATED']
        assert len(features_events) == 1, f"Expected 1 FEATURES_CALCULATED event, got {len(features_events)}"

        event = features_events[0]
        payload = event['payload']

        # Validate payload structure
        assert payload['symbol'] == 'BTCUSDT'
        assert 'features' in payload
        assert 'ts' in payload

        features = payload['features']

        # Validate that expected features are present and are strings (as per implementation)
        expected_features = ['obi', 'tfi', 'delta_price', 'absorption', 'price']
        for feature in expected_features:
            assert feature in features, f"Feature {feature} missing from payload"
            assert isinstance(features[feature], str), f"Feature {feature} should be string"

        # Validate feature values are reasonable
        obi = float(features['obi'])
        tfi = float(features['tfi'])
        delta_price = float(features['delta_price'])
        price = float(features['price'])

        # OBI = (bid_size - ask_size) / (bid_size + ask_size)
        # For second tick: (12 - 18) / (12 + 18) = (-6) / 30 = -0.2
        expected_obi = (12 - 18) / (12 + 18)
        assert abs(obi - expected_obi) < 0.001, f"OBI calculation incorrect: expected {expected_obi}, got {obi}"

        # TFI = (buy_volume - sell_volume) / (buy_volume + sell_volume)
        # For second tick: (120 - 90) / (120 + 90) = 30 / 210 ≈ 0.1429
        expected_tfi = (120 - 90) / (120 + 90)
        assert abs(tfi - expected_tfi) < 0.001, f"TFI calculation incorrect: expected {expected_tfi}, got {tfi}"

        # Delta price = current_price - prev_price = 50001.5 - 50000.5 = 1.0
        assert abs(delta_price - 1.0) < 0.001, f"Delta price incorrect: expected 1.0, got {delta_price}"

        # Price should be current price
        assert abs(price - 50001.5) < 0.001, f"Price incorrect: expected 50001.5, got {price}"

        print(f"✅ Test passed: Features calculated correctly: OBI={obi:.3f}, TFI={tfi:.3f}, delta_price={delta_price}")


if __name__ == "__main__":
    test = TestMarketDataToFeaturesFlow()
    test.test_market_tick_triggers_features_calculation()
    print("✅ All tests passed!")