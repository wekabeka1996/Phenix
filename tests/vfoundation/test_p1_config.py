"""
P1 Config Extraction — Guard Tests

Verifies:
1. FallbackConfig schema has required fields
2. ExposureGuard rejects missing fallback config (fail-closed)
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock
from apps.reference.config_models import FallbackConfig
from apps.reference.config_contract import ConfigContractError


class TestP1FallbackConfigSchema:
    """P1.1: Verify FallbackConfig Pydantic model matches the current fail-closed facade."""

    def test_fallback_config_schema_basic(self):
        """FallbackConfig facade now requires only the explicit fail-closed policy."""
        cfg = FallbackConfig(policy="fail_closed")
        assert cfg.policy == "fail_closed"

    def test_fallback_config_requires_policy(self):
        """FallbackConfig rejects omitted policy values."""
        with pytest.raises(Exception):
            FallbackConfig()

    def test_fallback_config_rejects_invalid_policy(self):
        """FallbackConfig rejects unknown policy values."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            FallbackConfig(policy="unknown_policy")


class TestP1ExposureGuardFallbackConfig:
    """P1.3: Verify ExposureGuard reads fallback from config."""

    def test_exposure_guard_rejects_missing_fallback_config(self):
        """ExposureGuard must raise ConfigContractError if fallback config is missing."""
        from apps.reference.domains.execution_position.exposure_guard import ExposureGuard

        # Build mock config - same pattern as test_fail_closed_config.py
        mock_config = MagicMock()

        # Setup ExposureGuard domain config (required for __init__)
        eg_config = MagicMock()
        eg_config.max_equity_utilization_pct = 100
        eg_config.max_portfolio_fraction = 1.0
        eg_config.max_long_utilization_pct = 100
        eg_config.max_short_utilization_pct = 100
        eg_config.max_concentration_pct = 50
        eg_config.max_directional_ratio = 5.0
        eg_config.pending_ttl_sec = 60
        eg_config.post_fill_ttl_sec = 30
        eg_config.stale_ttl_sec = 300
        mock_config.domains.execution_position.exposure_guard = eg_config

        # P1: fallback is None (MISSING)
        mock_config.domains.execution_position.fallback = None

        # Setup leverage config (P0 requirement)
        mock_config.trading.execution.exposure.leverage_defaults = {
            "__default__": 20}
        mock_config.trading.execution.exposure.count_pending_orders = True
        mock_config.trading.execution.exposure.exclude_reduce_only = False

        # Setup trading.risk as dict (required by soft_clip loader)
        mock_config.trading.risk = {
            "soft_limits": {
                "mode": "clip",
                "clip_min_notional_usdt": 5,
                "directional_ratio_max": 3.0,
                "side_exposure_usdt": 10000,
                "margin_exposure_usdt": 5000,
            }
        }

        mock_config.instruments = {}

        with pytest.raises(ConfigContractError, match="fallback"):
            ExposureGuard(fsm_core=MagicMock(), config=mock_config)

    def test_exposure_guard_loads_fallback_from_config(self):
        """ExposureGuard must read fallback config from domains.execution_position.fallback."""
        from apps.reference.domains.execution_position.exposure_guard import ExposureGuard

        # Build mock config - same pattern as test_fail_closed_config.py
        mock_config = MagicMock()

        # Setup ExposureGuard domain config
        eg_config = MagicMock()
        eg_config.max_equity_utilization_pct = 100
        eg_config.max_portfolio_fraction = 1.0
        eg_config.max_long_utilization_pct = 100
        eg_config.max_short_utilization_pct = 100
        eg_config.max_concentration_pct = 50
        eg_config.max_directional_ratio = 5.0
        eg_config.pending_ttl_sec = 60
        eg_config.post_fill_ttl_sec = 30
        eg_config.stale_ttl_sec = 300
        mock_config.domains.execution_position.exposure_guard = eg_config

        # P1: Provide valid fallback config
        mock_fallback = MagicMock()
        mock_fallback.policy = "fail_closed"
        mock_fallback.risk_reduction_pct = Decimal("0.5")
        mock_fallback.backoff_ms = [200, 500, 1000]
        mock_config.domains.execution_position.fallback = mock_fallback

        # Setup leverage config (P0 requirement)
        mock_config.trading.execution.exposure.leverage_defaults = {
            "__default__": 20}
        mock_config.trading.execution.exposure.count_pending_orders = True
        mock_config.trading.execution.exposure.exclude_reduce_only = False

        # Setup trading.risk as dict
        mock_config.trading.risk = {
            "soft_limits": {
                "mode": "clip",
                "clip_min_notional_usdt": 5,
                "directional_ratio_max": 3.0,
                "side_exposure_usdt": 10000,
                "margin_exposure_usdt": 5000,
            }
        }

        mock_config.instruments = {}

        # This should NOT raise - fallback config is provided
        guard = ExposureGuard(fsm_core=MagicMock(), config=mock_config)

        # Verify fallback config was loaded from config, not hardcode
        assert guard.fallback_config["policy"] == "fail_closed"
        assert set(guard.fallback_config) == {"policy"}
