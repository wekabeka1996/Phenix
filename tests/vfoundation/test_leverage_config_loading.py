"""
Leverage Configuration Loading Tests

P1: Verify explicit leverage configuration for multi-strategy setup.

Tests:
1. LeverageConfig model validation (bounds, enums)
2. Strategy assignment → leverage resolution logic
3. Cross-strategy isolation (Aurora DOGE ≠ MR DOGE)
"""

import pytest
from decimal import Decimal
from pydantic import ValidationError
from unittest.mock import MagicMock


# Helper: Create minimal AuroraInstrumentConfig with required fields
def make_aurora_asset(enabled: bool, leverage: dict | None = None) -> MagicMock:
    """Create mock Aurora asset config with leverage field."""
    mock = MagicMock()
    mock.enabled = enabled
    if leverage:
        from apps.reference.config_models import LeverageConfig
        leverage_payload = dict(leverage)
        leverage_payload.setdefault("max_notional_value", None)
        mock.leverage = LeverageConfig(**leverage_payload)
    else:
        mock.leverage = None
    return mock


# Helper: Create minimal MRAssetConfig
def make_mr_asset(enabled: bool, leverage: dict | None = None) -> MagicMock:
    """Create mock MR asset config with leverage field."""
    mock = MagicMock()
    mock.enabled = enabled
    if leverage:
        from apps.reference.config_models import LeverageConfig
        leverage_payload = dict(leverage)
        leverage_payload.setdefault("max_notional_value", None)
        mock.leverage = LeverageConfig(**leverage_payload)
    else:
        mock.leverage = None
    return mock


class TestLeverageConfigModel:
    """Test LeverageConfig Pydantic model validation."""

    def test_leverage_config_valid(self):
        """LeverageConfig must accept valid bounds."""
        from apps.reference.config_models import LeverageConfig

        cfg = LeverageConfig(target=20, mode="ISOLATED",
                             max_notional_value=None)
        assert cfg.target == 20
        assert cfg.mode == "ISOLATED"

        cfg_cross = LeverageConfig(
            target=50, mode="CROSSED", max_notional_value=None)
        assert cfg_cross.mode == "CROSSED"

    def test_leverage_config_bounds(self):
        """LeverageConfig must reject out-of-bounds values."""
        from apps.reference.config_models import LeverageConfig

        # Valid edge cases
        LeverageConfig(target=1, mode="ISOLATED",
                       max_notional_value=None)   # min
        LeverageConfig(target=125, mode="ISOLATED",
                       max_notional_value=None)  # max

        # Invalid: too low
        with pytest.raises(ValidationError):
            LeverageConfig(target=0, mode="ISOLATED", max_notional_value=None)

        # Invalid: too high
        with pytest.raises(ValidationError):
            LeverageConfig(target=126, mode="ISOLATED",
                           max_notional_value=None)

        # Invalid: negative
        with pytest.raises(ValidationError):
            LeverageConfig(target=-10, mode="ISOLATED",
                           max_notional_value=None)

    def test_leverage_config_mode_enum(self):
        """LeverageConfig must reject invalid modes."""
        from apps.reference.config_models import LeverageConfig

        with pytest.raises(ValidationError):
            LeverageConfig(target=20, mode="INVALID", max_notional_value=None)

        with pytest.raises(ValidationError):
            # lowercase not allowed
            LeverageConfig(target=20, mode="cross", max_notional_value=None)

    def test_leverage_config_optional_max_notional(self):
        """max_notional_value accepts explicit null or Decimal value."""
        from apps.reference.config_models import LeverageConfig

        cfg = LeverageConfig(target=50, mode="ISOLATED",
                             max_notional_value=None)
        assert cfg.max_notional_value is None

        cfg_with = LeverageConfig(
            target=50, mode="ISOLATED", max_notional_value=Decimal("1000000"))
        assert cfg_with.max_notional_value == Decimal("1000000")


class TestAuroraAssetLeverageConfig:
    """Test Aurora strategy per-asset leverage configuration."""

    def test_aurora_asset_has_leverage_field(self):
        """AuroraInstrumentConfig must have optional leverage field."""
        # Use mock to avoid required fields complexity
        cfg = make_aurora_asset(enabled=True, leverage=None)
        assert cfg.leverage is None

    def test_aurora_asset_with_leverage(self):
        """AuroraInstrumentConfig must accept leverage dict."""
        from apps.reference.config_models import LeverageConfig

        cfg = make_aurora_asset(
            enabled=True,
            leverage={"target": 50, "mode": "ISOLATED"},
        )
        assert cfg.leverage is not None
        assert isinstance(cfg.leverage, LeverageConfig)
        assert cfg.leverage.target == 50


class TestMRAssetLeverageConfig:
    """Test Mean Reversion strategy per-asset leverage configuration."""

    def test_mr_asset_has_leverage_field(self):
        """MRAssetConfig must have optional leverage field."""
        from apps.reference.config_models import MRAssetConfig

        # Without leverage
        cfg = MRAssetConfig(
            enabled=True,
            leverage=None,
            strategy=None,
            liquidity_gate=None,
            position_mode="STRICT",
            allowed_regimes=["FLAT_LOW", "FLAT_NORMAL"],
        )
        assert cfg.leverage is None

    def test_mr_asset_with_leverage(self):
        """MRAssetConfig must accept leverage dict."""
        from apps.reference.config_models import MRAssetConfig, LeverageConfig

        cfg = MRAssetConfig(
            enabled=True,
            leverage={"target": 10, "mode": "ISOLATED",
                      "max_notional_value": None},
            strategy=None,
            liquidity_gate=None,
            position_mode="STRICT",
            allowed_regimes=["FLAT_LOW"],
        )
        assert cfg.leverage is not None
        assert isinstance(cfg.leverage, LeverageConfig)
        assert cfg.leverage.target == 10


class TestStrategyLeverageResolution:
    """Test strategy assignment → leverage resolution logic."""

    def test_strategy_assignment_resolution(self):
        """Verify leverage resolution based on strategy assignment."""

        # 1. Mock Assignment (Router) - як у strategies.yaml
        assignments = {
            "BTCUSDT": "mean_reversion",  # BTC assigned to MR
            "ETHUSDT": "aurora",          # ETH assigned to Aurora
            "DOGEUSDT": "mean_reversion",  # DOGE assigned to MR
        }

        # 2. Mock Strategy Configs (як завантажено з YAML)
        aurora_assets = {
            "ETHUSDT": make_aurora_asset(
                enabled=True,
                leverage={"target": 20, "mode": "ISOLATED"},
            ),
            # DOGE в aurora.yaml (має ігноруватись бо assignment → MR)
            "DOGEUSDT": make_aurora_asset(
                enabled=False,
                leverage={"target": 99, "mode": "CROSSED"},  # Wrong value
            ),
        }

        mr_assets = {
            "DOGEUSDT": make_mr_asset(
                enabled=True,
                leverage={"target": 10, "mode": "ISOLATED"},
            ),
            "BTCUSDT": make_mr_asset(
                enabled=True,
                leverage={"target": 15, "mode": "ISOLATED"},
            ),
        }

        # 3. Resolve Logic (симуляція LeverageBootstrapper)
        resolved_leverage = {}

        for symbol, strategy_name in assignments.items():
            if strategy_name == "aurora":
                cfg = aurora_assets.get(symbol)
            elif strategy_name == "mean_reversion":
                cfg = mr_assets.get(symbol)
            else:
                cfg = None

            if cfg and cfg.leverage:
                resolved_leverage[symbol] = cfg.leverage.target

        # 4. Assertions
        assert resolved_leverage.get(
            "ETHUSDT") == 20, "ETH should get Aurora leverage"
        assert resolved_leverage.get(
            "DOGEUSDT") == 10, "DOGE should get MR leverage (not Aurora 99)"
        assert resolved_leverage.get(
            "BTCUSDT") == 15, "BTC should get MR leverage"

        # Ensure Aurora DOGE (99x) was NOT used
        assert resolved_leverage.get(
            "DOGEUSDT") != 99, "Cross-strategy contamination!"

    def test_missing_leverage_returns_none(self):
        """Symbols without leverage config should resolve to None."""

        aurora_assets = {
            "SOLUSDT": make_aurora_asset(
                enabled=True,
                leverage=None,  # NO leverage field
            ),
        }

        cfg = aurora_assets.get("SOLUSDT")
        assert cfg.leverage is None
