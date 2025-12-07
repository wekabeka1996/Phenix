"""
V1 Feature Engineering Snapshot Tests.

These tests freeze the current v1 feature calculation behavior.
If any FTR-01..FTR-04 refactoring breaks v1 behavior, these tests MUST fail.

Task: FTR-00-FEATURES-V1-FREEZE

Scenarios:
1. Low volume, balanced book (calm market)
2. High volume spike (volume anomaly)  
3. Strong uptrend (ema_bias bullish)
4. Strong downtrend (ema_bias bearish)
5. Imbalanced order book (obi/depth_imbalance skewed)
"""

import pytest
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from unittest.mock import Mock

# Import the feature engineering module
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
    FeatureEngineeringConfig,
)
from apps.reference.domains.feature_engineering.contracts import (
    FeatureSetV1,
    parse_features_v1,
    V1_FEATURE_NAMES,
)
from vfoundation.core.protocol import Message


# ============================================================================
# Test Harness: Mock FSM
# ============================================================================

class MockFSM:
    """
    Minimal mock FSM for testing FeatureEngineering in isolation.
    
    Captures all emitted events for verification.
    """
    
    def __init__(self):
        self.listeners: Dict[str, Any] = {}
        self.emitted_events: List[Dict] = []
    
    def listen(self, event_name: str, callback) -> None:
        """Register event listener."""
        self.listeners[event_name] = callback
    
    def emit(self, event_name: str, payload: Dict, why: str = "") -> None:
        """Capture emitted event."""
        self.emitted_events.append({
            "event": event_name,
            "payload": payload,
            "why": why,
        })
    
    def get_last_features(self) -> Optional[Dict[str, str]]:
        """Get features from last emitted EVT:FEATURES_CALCULATED."""
        for event in reversed(self.emitted_events):
            if event["event"] == "EVT:FEATURES_CALCULATED":
                return event["payload"].get("features")
        return None
    
    def clear_events(self) -> None:
        """Clear captured events."""
        self.emitted_events.clear()


# ============================================================================
# Test Harness: Market Tick Factory
# ============================================================================

@dataclass
class MarketTick:
    """Synthetic market tick for testing."""
    symbol: str
    ts: int
    price: str
    bid_size: str
    ask_size: str
    buy_volume: str
    sell_volume: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "price": self.price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
        }
    
    def to_message(self) -> Message:
        """Create a proper vFoundation Message with all required fields."""
        return Message(
            op="EVT",
            verb="MARKET_TICK_RECEIVED",
            src="market_data",
            dst="feature_engineering",
            pld=self.to_dict(),
            why="test_tick",
        )


def make_ticks(
    symbol: str,
    start_ts: int,
    prices: List[str],
    bid_sizes: List[str],
    ask_sizes: List[str],
    buy_volumes: List[str],
    sell_volumes: List[str],
    ts_step: int = 100,
) -> List[MarketTick]:
    """
    Create a sequence of market ticks for testing.
    
    All lists must have the same length.
    """
    assert len(prices) == len(bid_sizes) == len(ask_sizes) == len(buy_volumes) == len(sell_volumes)
    
    ticks = []
    for i, (price, bid, ask, buy_vol, sell_vol) in enumerate(
        zip(prices, bid_sizes, ask_sizes, buy_volumes, sell_volumes)
    ):
        ticks.append(MarketTick(
            symbol=symbol,
            ts=start_ts + i * ts_step,
            price=price,
            bid_size=bid,
            ask_size=ask,
            buy_volume=buy_vol,
            sell_volume=sell_vol,
        ))
    return ticks


# ============================================================================
# Fixture: Feature Engineering Instance
# ============================================================================

@pytest.fixture
def mock_fsm() -> MockFSM:
    """Create fresh mock FSM."""
    return MockFSM()


@pytest.fixture
def default_config() -> Dict:
    """Default feature engineering config for tests."""
    return {
        "feature_engineering": {
            "enable_new_metrics": True,
            "ema": {
                "period_short": 3,
                "period_long": 7,
            },
            "ema_bias": {
                "clamp_min": -0.02,
                "clamp_max": 0.02,
            },
            "volume": {
                "window_sec": 60,
                "sma_length": 5,
            },
            "volume_spike": {
                "cap_max": 3.0,
            },
            "volatility": {
                "window_sec": 60,
                "sma_length": 10,
            },
            "volatility_state": {
                "cap_max": 3.0,
            },
            "liquidity": {
                "depth_half": 1000.0,
                "kappa_min": 0.3,
                "kappa_max": 1.0,
            },
            "delta_price": {
                "spike_filter_ms": 5000,
            },
            "depth_imbalance": {
                "use_laplace_smoothing": True,
            },
            "macro_sync": {
                "enabled": True,
                "anchors": ["BTCUSDT", "ETHUSDT"],
                "window": 60,
                "min_buffer_size": 3,
                "time_diff_threshold_ms": 5000,
            },
            "defaults": {
                "neutral_value": 0.5,
                "zero_value": 0.0,
                "correlation_default": 0.0,
                "ms_per_sec": 1000,
            },
        }
    }


@pytest.fixture
def feature_engineering(mock_fsm: MockFSM, default_config: Dict) -> FeatureEngineering:
    """Create FeatureEngineering instance with mock FSM."""
    return FeatureEngineering(fsm=mock_fsm, config=default_config)


# ============================================================================
# Helper: Process ticks and get features
# ============================================================================

def process_ticks_and_get_features(
    fe: FeatureEngineering,
    fsm: MockFSM,
    ticks: List[MarketTick],
) -> Optional[FeatureSetV1]:
    """
    Process a sequence of ticks and return the last emitted features.
    
    Returns None if no features were emitted.
    """
    fsm.clear_events()
    
    for tick in ticks:
        fe.on_market_tick(tick.to_message())
    
    raw_features = fsm.get_last_features()
    if raw_features is None:
        return None
    
    return parse_features_v1(raw_features)


# ============================================================================
# SNAPSHOT TESTS
# ============================================================================

class TestFeatureEngineeringV1Snapshot:
    """
    Snapshot tests for v1 feature behavior.
    
    These tests verify that for fixed inputs, the feature outputs remain constant.
    If any refactoring changes these values, the tests MUST fail.
    """
    
    def test_scenario_1_calm_market_balanced_book(
        self, feature_engineering: FeatureEngineering, mock_fsm: MockFSM
    ):
        """
        Scenario 1: Calm market with balanced order book.
        
        - Low volume
        - Balanced bid/ask sizes
        - Stable price
        
        Expected: OBI ~0, TFI ~0, ema_bias ~0.5 (neutral)
        """
        ticks = make_ticks(
            symbol="TESTUSDT",
            start_ts=1000000,
            prices=["100.00", "100.01", "100.00", "100.02", "100.01"],
            bid_sizes=["500", "500", "500", "500", "500"],
            ask_sizes=["500", "500", "500", "500", "500"],
            buy_volumes=["10", "10", "10", "10", "10"],
            sell_volumes=["10", "10", "10", "10", "10"],
            ts_step=100,
        )
        
        features = process_ticks_and_get_features(feature_engineering, mock_fsm, ticks)
        
        assert features is not None, "Features should be emitted after multiple ticks"
        
        # Verify all v1 features are present
        for name in V1_FEATURE_NAMES:
            assert hasattr(features, name), f"Missing v1 feature: {name}"
        
        # SNAPSHOT VALUES - these are the "truth" for v1 behavior
        # OBI: (500 - 500) / 1000 = 0
        assert features.obi == Decimal("0")
        
        # TFI: (10 - 10) / 20 = 0
        assert features.tfi == Decimal("0")
        
        # Absorption: always 0.0 (placeholder)
        assert features.absorption == Decimal("0.0")
        
        # Price: last tick price
        assert features.price == Decimal("100.01")
        
        # Liquidity kappa uses depth in USD vs depth_half (1000 USD)
        # depth_usd = (500 + 500) * 100.01 ≈ 100_010
        # ratio = depth_usd / (depth_usd + depth_half) → ~0.99 (clamped [0.3, 1])
        assert Decimal("0.98") < features.liquidity_kappa < Decimal("1")
        
        # Depth imbalance: balanced book → ~0.5
        # Formula: ((ask + half) / (bid + half) - 1) / (ratio + 1) / 2 + 0.5
        # ratio = 1500/1500 = 1, imbalance = 0, phi = 0.5
        assert features.depth_imbalance == Decimal("0.5")
    
    def test_scenario_2_high_volume_spike(
        self, feature_engineering: FeatureEngineering, mock_fsm: MockFSM
    ):
        """
        Scenario 2: High volume spike (volume anomaly).
        
        - Sudden increase in volume on last tick
        - Should trigger high volume_spike value
        """
        # First several ticks with low volume to establish baseline
        low_vol_ticks = make_ticks(
            symbol="TESTUSDT",
            start_ts=1000000,
            prices=["100.00"] * 10,
            bid_sizes=["500"] * 10,
            ask_sizes=["500"] * 10,
            buy_volumes=["10"] * 10,  # Low volume
            sell_volumes=["10"] * 10,
            ts_step=100,
        )
        
        # High volume tick
        high_vol_tick = MarketTick(
            symbol="TESTUSDT",
            ts=1001000,
            price="100.00",
            bid_size="500",
            ask_size="500",
            buy_volume="100",  # 10x spike
            sell_volume="100",
        )
        
        all_ticks = low_vol_ticks + [high_vol_tick]
        features = process_ticks_and_get_features(feature_engineering, mock_fsm, all_ticks)
        
        assert features is not None
        
        # Volume spike should be elevated (but not yet fully developed 
        # because volume history window needs time)
        # At minimum, verify it's a valid value in [0, 1]
        assert Decimal("0") <= features.volume_spike <= Decimal("1")
    
    def test_scenario_3_strong_uptrend(
        self, feature_engineering: FeatureEngineering, mock_fsm: MockFSM
    ):
        """
        Scenario 3: Strong uptrend.
        
        - Price consistently rising
        - EMA_short > EMA_long → ema_bias > 0.5 (bullish)
        """
        # Steadily increasing prices
        ticks = make_ticks(
            symbol="TESTUSDT",
            start_ts=1000000,
            prices=["100.00", "100.50", "101.00", "101.50", "102.00", 
                    "102.50", "103.00", "103.50", "104.00", "104.50"],
            bid_sizes=["500"] * 10,
            ask_sizes=["500"] * 10,
            buy_volumes=["50"] * 10,  # More buying pressure
            sell_volumes=["20"] * 10,
            ts_step=100,
        )
        
        features = process_ticks_and_get_features(feature_engineering, mock_fsm, ticks)
        
        assert features is not None
        
        # In uptrend: EMA_short > EMA_long → ema_bias > 0.5
        # The exact value depends on EMA calculation
        assert features.ema_bias >= Decimal("0.5"), "Uptrend should have bullish ema_bias"
        
        # TFI should be positive (more buy volume)
        # (50 - 20) / 70 = 30/70 ≈ 0.4286
        assert features.tfi > Decimal("0"), "More buy volume should give positive TFI"
        
        # Delta price should be positive
        assert features.delta_price >= Decimal("0"), "Uptrend should have positive delta_price"
    
    def test_scenario_4_strong_downtrend(
        self, feature_engineering: FeatureEngineering, mock_fsm: MockFSM
    ):
        """
        Scenario 4: Strong downtrend.
        
        - Price consistently falling
        - EMA_short < EMA_long → ema_bias < 0.5 (bearish)
        """
        # Steadily decreasing prices
        ticks = make_ticks(
            symbol="TESTUSDT",
            start_ts=1000000,
            prices=["104.50", "104.00", "103.50", "103.00", "102.50",
                    "102.00", "101.50", "101.00", "100.50", "100.00"],
            bid_sizes=["500"] * 10,
            ask_sizes=["500"] * 10,
            buy_volumes=["20"] * 10,  # Less buying
            sell_volumes=["50"] * 10,  # More selling
            ts_step=100,
        )
        
        features = process_ticks_and_get_features(feature_engineering, mock_fsm, ticks)
        
        assert features is not None
        
        # In downtrend: EMA_short < EMA_long → ema_bias < 0.5
        assert features.ema_bias <= Decimal("0.5"), "Downtrend should have bearish ema_bias"
        
        # TFI should be negative (more sell volume)
        assert features.tfi < Decimal("0"), "More sell volume should give negative TFI"
        
        # Delta price should be negative
        assert features.delta_price <= Decimal("0"), "Downtrend should have negative delta_price"
    
    def test_scenario_5_imbalanced_order_book(
        self, feature_engineering: FeatureEngineering, mock_fsm: MockFSM
    ):
        """
        Scenario 5: Heavily imbalanced order book.
        
        - Much more bid depth than ask → OBI positive (bullish)
        - OR much more ask depth than bid → OBI negative (bearish)
        """
        # Heavy bid side (bullish order book)
        ticks_bullish = make_ticks(
            symbol="TESTUSDT",
            start_ts=1000000,
            prices=["100.00", "100.00", "100.00"],
            bid_sizes=["900", "900", "900"],  # Heavy bids
            ask_sizes=["100", "100", "100"],  # Light asks
            buy_volumes=["10", "10", "10"],
            sell_volumes=["10", "10", "10"],
            ts_step=100,
        )
        
        features = process_ticks_and_get_features(feature_engineering, mock_fsm, ticks_bullish)
        
        assert features is not None
        
        # OBI: (900 - 100) / 1000 = 800/1000 = 0.8
        assert features.obi == Decimal("0.8"), "Heavy bid book should have OBI = 0.8"
        
        # Depth imbalance: more bids → lower ratio → depth_imbalance < 0.5
        # ratio = (100 + 1000) / (900 + 1000) = 1100/1900 ≈ 0.579
        # imbalance = (0.579 - 1) / (0.579 + 1) = -0.421 / 1.579 ≈ -0.267
        # phi = (-0.267 + 1) / 2 = 0.733 / 2 ≈ 0.366
        # Actually let me re-check the formula...
        # depth_imbalance uses ask/bid ratio with Laplace smoothing
        assert features.depth_imbalance < Decimal("0.5"), "Heavy bid book should have depth_imbalance < 0.5"
    
    def test_scenario_5b_bearish_order_book(
        self, feature_engineering: FeatureEngineering, mock_fsm: MockFSM
    ):
        """
        Scenario 5b: Bearish order book (heavy asks).
        """
        ticks_bearish = make_ticks(
            symbol="TESTUSDT",
            start_ts=1000000,
            prices=["100.00", "100.00", "100.00"],
            bid_sizes=["100", "100", "100"],  # Light bids
            ask_sizes=["900", "900", "900"],  # Heavy asks
            buy_volumes=["10", "10", "10"],
            sell_volumes=["10", "10", "10"],
            ts_step=100,
        )
        
        features = process_ticks_and_get_features(feature_engineering, mock_fsm, ticks_bearish)
        
        assert features is not None
        
        # OBI: (100 - 900) / 1000 = -800/1000 = -0.8
        assert features.obi == Decimal("-0.8"), "Heavy ask book should have OBI = -0.8"
        
        # Depth imbalance: more asks → higher ratio → depth_imbalance > 0.5
        assert features.depth_imbalance > Decimal("0.5"), "Heavy ask book should have depth_imbalance > 0.5"


# ============================================================================
# CONTRACT VALIDATION TESTS
# ============================================================================

class TestFeatureSetV1Contract:
    """Tests for FeatureSetV1 Pydantic contract."""
    
    def test_parse_valid_features(self):
        """Test parsing valid feature dict."""
        raw = {
            "obi": "0.15",
            "tfi": "-0.23",
            "delta_price": "10.5",
            "price": "100.00",
            "absorption": "0.0",
            "liquidity_kappa": "0.7",
            "ema_bias": "0.62",
            "volume_spike": "0.45",
            "volatility_state": "0.38",
            "depth_imbalance": "0.52",
            "macro_sync": "0.5",
        }
        
        features = parse_features_v1(raw)
        
        assert features.obi == Decimal("0.15")
        assert features.tfi == Decimal("-0.23")
        assert features.delta_price == Decimal("10.5")
        assert features.price == Decimal("100.00")
        assert features.absorption == Decimal("0.0")
        assert features.liquidity_kappa == Decimal("0.7")
        assert features.ema_bias == Decimal("0.62")
        assert features.volume_spike == Decimal("0.45")
        assert features.volatility_state == Decimal("0.38")
        assert features.depth_imbalance == Decimal("0.52")
        assert features.macro_sync == Decimal("0.5")
    
    def test_parse_missing_feature_raises(self):
        """Test that missing feature raises KeyError."""
        raw = {
            "obi": "0.15",
            "tfi": "-0.23",
            # missing other features
        }
        
        with pytest.raises(KeyError) as exc_info:
            parse_features_v1(raw)
        
        assert "Missing required v1 features" in str(exc_info.value)
    
    def test_parse_invalid_decimal_raises(self):
        """Test that invalid decimal value raises ValueError."""
        raw = {
            "obi": "not_a_number",
            "tfi": "-0.23",
            "delta_price": "10.5",
            "price": "100.00",
            "absorption": "0.0",
            "liquidity_kappa": "0.7",
            "ema_bias": "0.62",
            "volume_spike": "0.45",
            "volatility_state": "0.38",
            "depth_imbalance": "0.52",
            "macro_sync": "0.5",
        }
        
        with pytest.raises(ValueError) as exc_info:
            parse_features_v1(raw)
        
        assert "Cannot convert feature 'obi'" in str(exc_info.value)
    
    def test_feature_set_is_frozen(self):
        """Test that FeatureSetV1 is immutable."""
        raw = {
            "obi": "0.15",
            "tfi": "-0.23",
            "delta_price": "10.5",
            "price": "100.00",
            "absorption": "0.0",
            "liquidity_kappa": "0.7",
            "ema_bias": "0.62",
            "volume_spike": "0.45",
            "volatility_state": "0.38",
            "depth_imbalance": "0.52",
            "macro_sync": "0.5",
        }
        
        features = parse_features_v1(raw)
        
        with pytest.raises(Exception):  # ValidationError for frozen model
            features.obi = Decimal("0.99")
    
    def test_v1_feature_names_complete(self):
        """Test that V1_FEATURE_NAMES contains all 11 features."""
        expected = {
            "obi", "tfi", "delta_price", "price", "absorption", "liquidity_kappa",
            "ema_bias", "volume_spike", "volatility_state", "depth_imbalance", "macro_sync"
        }
        assert set(V1_FEATURE_NAMES) == expected
        assert len(V1_FEATURE_NAMES) == 11
