"""
Regression test for fail-closed brackets config loading.

BUG FIX: Previously fsm.py had hardcoded defaults sl_bps=50, tp_bps=100
         that were used when config was missing, causing wrong TP/SL for low-price assets.

FIX: Now uses DomainConfigResolver.get_brackets_strict() which FAILS if config is missing.
"""

import pytest
from unittest.mock import MagicMock
from apps.reference.domain_config import DomainConfigResolver
from apps.reference.config_models import (
    AuroraConfig, 
    TradingConfig, 
    ExecutionConfig, 
    ManageConfig, 
    BracketsConfig,
    SLConfig,
    TPConfig,
    DomainsConfig,
    ExecutionPositionDomainConfig,
    WatchdogConfig,
    ExposureGuardConfig,
    FsmOpenConfig,
    OrderIndexConfig,
    InflightReconcileConfig,
    MetricsCollectorConfig,
    IdempotentCancelConfig,
    ExecutionUtilsConfig,
    DomainsDebugConfig,
    DecisionMakingDomainConfig,
    FeatureEngineeringDomainConfig,
    RiskManagementDomainConfig,
    PositionTrackingDomainConfig,
    # NOTE: AccountObserverDomainConfig removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
)


class TestBracketsFailClosed:
    """Test that brackets config loading is fail-closed (no defaults)."""

    def _create_minimal_domains_config(self) -> DomainsConfig:
        """Create minimal valid DomainsConfig for testing."""
        return DomainsConfig(
            debug=DomainsDebugConfig(
                disable_positions_stale_gate=False,
                disable_daily_loss_limit=False,
            ),
            decision_making=MagicMock(spec=DecisionMakingDomainConfig),
            feature_engineering=MagicMock(spec=FeatureEngineeringDomainConfig),
            risk_management=MagicMock(spec=RiskManagementDomainConfig),
            position_tracking=MagicMock(spec=PositionTrackingDomainConfig),
            # NOTE: account_observer removed (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
            execution_position=MagicMock(spec=ExecutionPositionDomainConfig),
        )

    def test_get_brackets_strict_success(self):
        """Test that valid brackets config is loaded correctly."""
        # Create config with valid brackets
        config = MagicMock(spec=AuroraConfig)
        config.domains = self._create_minimal_domains_config()
        config.trading = MagicMock(spec=TradingConfig)
        config.trading.execution = MagicMock(spec=ExecutionConfig)
        config.trading.execution.manage = MagicMock(spec=ManageConfig)
        config.trading.execution.manage.brackets = BracketsConfig(
            sl=SLConfig(fixed_bps=40),
            tp=TPConfig(fixed_bps=80),
            oco_emulation=True,
            # PURGE-DEAD-CONFIG-03: stop_loss_bps removed (dead duplicate, SSOT is sl.fixed_bps)
            offset_bps=5,
        )

        resolver = DomainConfigResolver(config)
        brackets = resolver.get_brackets_strict()

        assert brackets.sl.fixed_bps == 40
        assert brackets.tp.fixed_bps == 80

    def test_get_brackets_strict_fails_when_missing(self):
        """Test that missing brackets config raises ValueError."""
        config = MagicMock(spec=AuroraConfig)
        config.domains = self._create_minimal_domains_config()
        config.trading = None  # No trading config

        resolver = DomainConfigResolver(config)

        with pytest.raises(ValueError, match="BracketsConfig not found"):
            resolver.get_brackets_strict()

    def test_get_brackets_strict_fails_when_sl_missing(self):
        """Test that missing SL config raises ValueError."""
        config = MagicMock(spec=AuroraConfig)
        config.domains = self._create_minimal_domains_config()
        config.trading = MagicMock(spec=TradingConfig)
        config.trading.execution = MagicMock(spec=ExecutionConfig)
        config.trading.execution.manage = MagicMock(spec=ManageConfig)
        config.trading.execution.manage.brackets = MagicMock()
        config.trading.execution.manage.brackets.sl = None  # Missing SL!
        config.trading.execution.manage.brackets.tp = TPConfig(fixed_bps=80)

        resolver = DomainConfigResolver(config)

        with pytest.raises(ValueError, match="sl.fixed_bps is required"):
            resolver.get_brackets_strict()

    def test_get_brackets_strict_fails_when_tp_missing(self):
        """Test that missing TP config raises ValueError."""
        config = MagicMock(spec=AuroraConfig)
        config.domains = self._create_minimal_domains_config()
        config.trading = MagicMock(spec=TradingConfig)
        config.trading.execution = MagicMock(spec=ExecutionConfig)
        config.trading.execution.manage = MagicMock(spec=ManageConfig)
        config.trading.execution.manage.brackets = MagicMock()
        config.trading.execution.manage.brackets.sl = SLConfig(fixed_bps=40)
        config.trading.execution.manage.brackets.tp = None  # Missing TP!

        resolver = DomainConfigResolver(config)

        with pytest.raises(ValueError, match="tp.fixed_bps is required"):
            resolver.get_brackets_strict()

    def test_no_hardcoded_defaults_in_resolver(self):
        """
        Verify that resolver does NOT use any hardcoded defaults.
        
        This is the regression test for the bug where sl_bps=50, tp_bps=100
        were hardcoded and caused wrong TP/SL for DOGE.
        """
        config = MagicMock(spec=AuroraConfig)
        config.domains = self._create_minimal_domains_config()
        config.trading = MagicMock(spec=TradingConfig)
        config.trading.execution = MagicMock(spec=ExecutionConfig)
        config.trading.execution.manage = MagicMock(spec=ManageConfig)
        config.trading.execution.manage.brackets = None  # No brackets!

        resolver = DomainConfigResolver(config)

        # Should raise, NOT return hardcoded 50/100!
        with pytest.raises(ValueError):
            resolver.get_brackets_strict()

    def test_production_config_values(self):
        """Test with actual production config values from trading.yaml."""
        # Production values: sl=40, tp=80
        config = MagicMock(spec=AuroraConfig)
        config.domains = self._create_minimal_domains_config()
        config.trading = MagicMock(spec=TradingConfig)
        config.trading.execution = MagicMock(spec=ExecutionConfig)
        config.trading.execution.manage = MagicMock(spec=ManageConfig)
        config.trading.execution.manage.brackets = BracketsConfig(
            sl=SLConfig(fixed_bps=40),
            tp=TPConfig(fixed_bps=80),
            oco_emulation=True,
            # PURGE-DEAD-CONFIG-03: stop_loss_bps removed (dead duplicate, SSOT is sl.fixed_bps)
            offset_bps=5,
        )

        resolver = DomainConfigResolver(config)
        brackets = resolver.get_brackets_strict()

        # Verify production values
        assert brackets.sl.fixed_bps == 40, "Production SL should be 40 bps"
        assert brackets.tp.fixed_bps == 80, "Production TP should be 80 bps"
        
        # NOT the old hardcoded defaults!
        assert brackets.sl.fixed_bps != 50, "Should NOT use hardcoded default 50"
        assert brackets.tp.fixed_bps != 100, "Should NOT use hardcoded default 100"
