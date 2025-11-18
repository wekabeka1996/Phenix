import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.soft_clip import SoftClipEngine, SoftLimitConfig, ClipResult, RegimeAdaptationConfig

@pytest.fixture
def soft_clip_config():
    return SoftLimitConfig(
        mode="clip",
        clip_min_notional_usdt=Decimal("10"),
        directional_ratio_max=Decimal("3.0"),
        side_exposure_usdt=Decimal("600"),
        margin_exposure_usdt=Decimal("1100")
    )

@pytest.fixture
def engine(soft_clip_config):
    return SoftClipEngine(soft_clip_config)

def test_initialization(engine, soft_clip_config):
    assert engine.config == soft_clip_config
    assert engine.logger is not None

def test_calculate_clipped_size_no_limits_hit(engine):
    # Setup: plenty of room
    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("100"),
        short_margin=Decimal("100"),
        total_margin_exposure=Decimal("200"),
        symbol_leverage=Decimal("10")
    )

    assert result.allowed is True
    assert result.reason == "OK"
    assert result.clipped_notional == Decimal("100")
    assert result.original_notional == Decimal("100")
    assert "DIRECTIONAL_OK" in result.clip_reasons

def test_calculate_clipped_size_margin_limit_hit(engine):
    # Config: margin_exposure_usdt = 1100
    # Current: 1000
    # Available: 100
    # Leverage: 10 -> Max Notional = 1000
    # Requested: 2000

    result = engine.calculate_clipped_size(
        notional_usd=Decimal("2000"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("500"),
        short_margin=Decimal("500"),
        total_margin_exposure=Decimal("1000"),
        symbol_leverage=Decimal("10")
    )

    assert result.allowed is True
    assert result.reason == "CLIPPED"
    assert result.clipped_notional == Decimal("1000") # 100 * 10
    assert any("MARGIN_AVAILABLE" in r for r in result.clip_reasons)

def test_calculate_clipped_size_side_limit_hit(engine):
    # Config: side_exposure_usdt = 600
    # Current Long: 500
    # Current Short: 500 (Balanced to avoid Directional Ratio limit)
    # Available Side: 100
    # Leverage: 10 -> Max Notional = 1000
    # Requested: 2000

    result = engine.calculate_clipped_size(
        notional_usd=Decimal("2000"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("500"),
        short_margin=Decimal("500"),
        total_margin_exposure=Decimal("1000"),
        symbol_leverage=Decimal("10")
    )

    assert result.allowed is True
    assert result.reason == "CLIPPED"
    assert result.clipped_notional == Decimal("1000")
    assert any("SIDE_AVAILABLE" in r for r in result.clip_reasons)

def test_calculate_clipped_size_directional_ratio_hit(engine):
    # Config: directional_ratio_max = 3.0
    # Current: Long 300, Short 100 (Ratio 3.0)
    # Adding Long will increase ratio > 3.0
    # Current impl sets delta to 0 if violated

    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("300"),
        short_margin=Decimal("100"),
        total_margin_exposure=Decimal("400"),
        symbol_leverage=Decimal("10")
    )

    # New Long Margin would be 300 + 10 = 310
    # Ratio 310/100 = 3.1 > 3.0
    # Should be clipped to 0 -> Rejected because < min_notional

    assert result.allowed is False
    assert result.reason == "BELOW_CLIP_MIN"
    assert "DIRECTIONAL_RATIO_EXCEEDED" in result.clip_reasons

def test_calculate_clipped_size_below_min_notional(engine):
    # Config: clip_min_notional_usdt = 10
    # Margin Limit allows only 5 USDT

    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("500"),
        short_margin=Decimal("500"),
        total_margin_exposure=Decimal("1099.5"), # 0.5 available
        symbol_leverage=Decimal("10") # 5 USDT notional available
    )

    assert result.allowed is False
    assert result.reason == "BELOW_CLIP_MIN"
    assert result.clipped_notional is None

def test_calculate_clipped_size_overrides(engine):
    # Override limits via arguments

    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("100"),
        short_margin=Decimal("100"),
        total_margin_exposure=Decimal("200"),
        symbol_leverage=Decimal("10"),
        margin_limit=Decimal("205") # Only 5 margin available -> 50 notional
    )

    assert result.allowed is True
    assert result.clipped_notional == Decimal("50")
    assert result.reason == "CLIPPED"

def test_regime_adaptation_config_defaults():
    config = RegimeAdaptationConfig()
    assert config.bounds == [Decimal("2.0"), Decimal("4.0")]

    config_custom = RegimeAdaptationConfig(bounds=[Decimal("1.0"), Decimal("5.0")])
    assert config_custom.bounds == [Decimal("1.0"), Decimal("5.0")]

def test_margin_limit_reached_zero_delta(engine):
    # Margin limit exactly reached
    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("100"),
        short_margin=Decimal("100"),
        total_margin_exposure=Decimal("1100"), # Limit is 1100
        symbol_leverage=Decimal("10")
    )

    assert result.allowed is False
    assert result.reason == "BELOW_CLIP_MIN"
    assert "MARGIN_LIMIT_REACHED" in result.clip_reasons

def test_side_limit_reached_zero_delta(engine):
    # Side limit exactly reached
    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("600"), # Limit is 600
        short_margin=Decimal("100"),
        total_margin_exposure=Decimal("700"),
        symbol_leverage=Decimal("10")
    )

    assert result.allowed is False
    assert result.reason == "BELOW_CLIP_MIN"
    assert "SIDE_LIMIT_REACHED" in result.clip_reasons

def test_calculate_clipped_size_from_zero_position(engine):
    # Start with 0 position
    # Long: 0, Short: 0
    # Add Long
    # New Long > 0, New Short = 0 -> Min Margin = 0
    # Should hit the else block for min_margin <= 0

    result = engine.calculate_clipped_size(
        notional_usd=Decimal("100"),
        symbol="BTCUSDT",
        order_side="BUY",
        long_margin=Decimal("0"),
        short_margin=Decimal("0"),
        total_margin_exposure=Decimal("0"),
        symbol_leverage=Decimal("10")
    )

    assert result.allowed is True
    assert result.reason == "OK"
    assert "DIRECTIONAL_OK" in result.clip_reasons
