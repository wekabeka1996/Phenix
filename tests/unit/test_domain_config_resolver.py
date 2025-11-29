"""
Unit tests for DomainConfigResolver.

Tests cover:
- Initialization and type validation
- All domain accessors (execution_position, decision_making, etc.)
- Fallback behavior (root vs trading.domains)
- Legacy deprecated accessors
- Edge cases and error handling
- Factory functions

Target coverage: 90%+
"""

import pytest
import warnings
from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.reference.domain_config import (
    DomainConfigResolver,
    create_resolver,
    create_resolver_from_dict,
)
from apps.reference.config_models import (
    AuroraConfig,
    DomainsConfig,
    TradingConfig,
    ExecutionPositionDomainConfig,
    ExposureGuardConfig,
    WatchdogConfig,
    FsmOpenConfig,
    OrderIndexConfig,
    MetricsCollectorConfig,
    IdempotentCancelConfig,
    ExecutionUtilsConfig,
    DecisionMakingDomainConfig,
    FeatureEngineeringDomainConfig,
    RiskManagementDomainConfig,
    PositionTrackingDomainConfig,
    AccountObserverDomainConfig,
    ExecutionConfig,
    ExposureConfig,
    ManageConfig,
    BracketsConfig,
)


class TestDomainConfigResolverInit:
    """Tests for DomainConfigResolver initialization."""

    def test_init_with_aurora_config(self):
        """Should initialize successfully with valid AuroraConfig."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        assert resolver is not None
        assert resolver.trading_mode == "testnet"

    def test_init_rejects_dict(self):
        """Should raise TypeError if dict is passed instead of AuroraConfig."""
        with pytest.raises(TypeError) as exc_info:
            DomainConfigResolver({"trading_mode": "testnet"})
        
        assert "DomainConfigResolver requires AuroraConfig" in str(exc_info.value)
        assert "got dict" in str(exc_info.value)

    def test_init_rejects_none(self):
        """Should raise TypeError if None is passed."""
        with pytest.raises(TypeError):
            DomainConfigResolver(None)

    def test_init_with_root_domains(self):
        """Should use root-level domains config when available."""
        domains = DomainsConfig(
            execution_position=ExecutionPositionDomainConfig(
                watchdog=WatchdogConfig(ack_ttl_ms=5000)
            )
        )
        config = AuroraConfig(trading_mode="testnet", domains=domains)
        resolver = DomainConfigResolver(config)
        
        assert resolver.get_watchdog().ack_ttl_ms == 5000

    def test_init_with_trading_domains_fallback(self):
        """Should fallback to trading.domains when root domains is None."""
        domains = DomainsConfig(
            execution_position=ExecutionPositionDomainConfig(
                watchdog=WatchdogConfig(ack_ttl_ms=7000)
            )
        )
        trading = TradingConfig(mode="testnet", domains=domains)
        config = AuroraConfig(trading_mode="testnet", trading=trading, domains=None)
        resolver = DomainConfigResolver(config)
        
        assert resolver.get_watchdog().ack_ttl_ms == 7000

    def test_init_uses_defaults_when_no_domains(self):
        """Should use default DomainsConfig when neither root nor trading domains exist."""
        # Create config where trading has no domains attribute
        trading = TradingConfig(mode="testnet")
        trading.domains = None  # Explicitly remove domains
        config = AuroraConfig(trading_mode="testnet", domains=None, trading=trading)
        resolver = DomainConfigResolver(config)
        
        # Should get default values
        assert resolver.get_watchdog().ack_ttl_ms == 8000  # default
        assert resolver.get_exposure_guard().pending_ttl_sec == 90  # default


class TestExecutionPositionAccessors:
    """Tests for execution_position domain accessors."""

    @pytest.fixture
    def resolver_with_custom_config(self):
        """Create resolver with custom execution_position config."""
        domains = DomainsConfig(
            execution_position=ExecutionPositionDomainConfig(
                watchdog=WatchdogConfig(
                    ack_ttl_ms=3000,
                    fill_ttl_ms=15000,
                    check_interval_ms=500,
                    rps_limit=5
                ),
                exposure_guard=ExposureGuardConfig(
                    pending_ttl_sec=60,
                    post_fill_ttl_sec=10,
                    stale_ttl_sec=3,
                    max_equity_utilization_pct=0.15,
                    max_portfolio_fraction=0.25,
                    max_long_utilization_pct=0.18,
                    max_short_utilization_pct=0.12,
                    max_directional_ratio=3.0,
                    max_concentration_pct=0.05
                ),
                fsm_open=FsmOpenConfig(idempotency_window_sec=120),
                order_index=OrderIndexConfig(ttl_sec=7200),
                metrics_collector=MetricsCollectorConfig(
                    window_size_minutes=30,
                    recent_rejections_minutes=10
                ),
                idempotent_cancel=IdempotentCancelConfig(max_retries=5),
                utils=ExecutionUtilsConfig(
                    client_order_id_max_length=64,
                    basis_points_base=10000.0
                )
            )
        )
        config = AuroraConfig(trading_mode="testnet", domains=domains)
        return DomainConfigResolver(config)

    def test_get_execution_position(self, resolver_with_custom_config):
        """Should return complete ExecutionPositionDomainConfig."""
        ep = resolver_with_custom_config.get_execution_position()
        
        assert isinstance(ep, ExecutionPositionDomainConfig)
        assert ep.watchdog.ack_ttl_ms == 3000

    def test_get_execution_position_caching(self, resolver_with_custom_config):
        """Should cache execution_position config for performance."""
        ep1 = resolver_with_custom_config.get_execution_position()
        ep2 = resolver_with_custom_config.get_execution_position()
        
        assert ep1 is ep2  # Same object (cached)

    def test_get_exposure_guard(self, resolver_with_custom_config):
        """Should return ExposureGuardConfig with all fields."""
        eg = resolver_with_custom_config.get_exposure_guard()
        
        assert isinstance(eg, ExposureGuardConfig)
        assert eg.pending_ttl_sec == 60
        assert eg.post_fill_ttl_sec == 10
        assert eg.stale_ttl_sec == 3
        assert eg.max_equity_utilization_pct == 0.15
        assert eg.max_portfolio_fraction == 0.25
        assert eg.max_long_utilization_pct == 0.18
        assert eg.max_short_utilization_pct == 0.12
        assert eg.max_directional_ratio == 3.0
        assert eg.max_concentration_pct == 0.05

    def test_get_watchdog(self, resolver_with_custom_config):
        """Should return WatchdogConfig with all fields."""
        wd = resolver_with_custom_config.get_watchdog()
        
        assert isinstance(wd, WatchdogConfig)
        assert wd.ack_ttl_ms == 3000
        assert wd.fill_ttl_ms == 15000
        assert wd.check_interval_ms == 500
        assert wd.rps_limit == 5

    def test_get_fsm_open(self, resolver_with_custom_config):
        """Should return FsmOpenConfig."""
        fsm = resolver_with_custom_config.get_fsm_open()
        
        assert isinstance(fsm, FsmOpenConfig)
        assert fsm.idempotency_window_sec == 120

    def test_get_order_index(self, resolver_with_custom_config):
        """Should return OrderIndexConfig."""
        oi = resolver_with_custom_config.get_order_index()
        
        assert isinstance(oi, OrderIndexConfig)
        assert oi.ttl_sec == 7200

    def test_get_metrics_collector(self, resolver_with_custom_config):
        """Should return MetricsCollectorConfig."""
        mc = resolver_with_custom_config.get_metrics_collector()
        
        assert isinstance(mc, MetricsCollectorConfig)
        assert mc.window_size_minutes == 30
        assert mc.recent_rejections_minutes == 10

    def test_get_idempotent_cancel(self, resolver_with_custom_config):
        """Should return IdempotentCancelConfig."""
        ic = resolver_with_custom_config.get_idempotent_cancel()
        
        assert isinstance(ic, IdempotentCancelConfig)
        assert ic.max_retries == 5

    def test_get_execution_utils(self, resolver_with_custom_config):
        """Should return ExecutionUtilsConfig."""
        utils = resolver_with_custom_config.get_execution_utils()
        
        assert isinstance(utils, ExecutionUtilsConfig)
        assert utils.client_order_id_max_length == 64
        assert utils.basis_points_base == 10000.0


class TestOtherDomainAccessors:
    """Tests for other domain accessors."""

    @pytest.fixture
    def resolver_with_all_domains(self):
        """Create resolver with all domains configured."""
        domains = DomainsConfig()  # Uses all defaults
        config = AuroraConfig(trading_mode="production", domains=domains)
        return DomainConfigResolver(config)

    def test_get_decision_making(self, resolver_with_all_domains):
        """Should return DecisionMakingDomainConfig."""
        dm = resolver_with_all_domains.get_decision_making()
        
        assert isinstance(dm, DecisionMakingDomainConfig)
        assert dm.position_sizing is not None
        assert dm.qos is not None

    def test_get_feature_engineering(self, resolver_with_all_domains):
        """Should return FeatureEngineeringDomainConfig."""
        fe = resolver_with_all_domains.get_feature_engineering()
        
        assert isinstance(fe, FeatureEngineeringDomainConfig)
        assert fe.ema is not None
        assert fe.volume is not None

    def test_get_risk_management(self, resolver_with_all_domains):
        """Should return RiskManagementDomainConfig."""
        rm = resolver_with_all_domains.get_risk_management()
        
        assert isinstance(rm, RiskManagementDomainConfig)
        assert rm.risk_score_weights is not None

    def test_get_position_tracking(self, resolver_with_all_domains):
        """Should return PositionTrackingDomainConfig."""
        pt = resolver_with_all_domains.get_position_tracking()
        
        assert isinstance(pt, PositionTrackingDomainConfig)
        assert pt.precision is not None

    def test_get_account_observer(self, resolver_with_all_domains):
        """Should return AccountObserverDomainConfig."""
        ao = resolver_with_all_domains.get_account_observer()
        
        assert isinstance(ao, AccountObserverDomainConfig)
        assert ao.poll_interval_sec == 5  # default


class TestLegacyAccessors:
    """Tests for deprecated legacy accessors."""

    @pytest.fixture
    def resolver_with_legacy_config(self):
        """Create resolver with legacy trading.execution config."""
        execution = ExecutionConfig(
            exposure=ExposureConfig(
                max_equity_utilization_pct=0.30,
                pending_ttl_sec=45
            ),
            manage=ManageConfig(
                brackets=BracketsConfig(
                    stop_loss_bps=100,
                    offset_bps=10
                ),
                auto=True
            )
        )
        trading = TradingConfig(mode="testnet", execution=execution)
        config = AuroraConfig(trading_mode="testnet", trading=trading)
        return DomainConfigResolver(config)

    def test_get_legacy_exposure_warns(self, resolver_with_legacy_config):
        """Should emit DeprecationWarning when accessing legacy exposure."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            exp = resolver_with_legacy_config.get_legacy_exposure()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_legacy_exposure() is deprecated" in str(w[0].message)
            assert exp is not None
            assert exp.max_equity_utilization_pct == 0.30

    def test_get_legacy_brackets_warns(self, resolver_with_legacy_config):
        """Should emit DeprecationWarning when accessing legacy brackets."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            brackets = resolver_with_legacy_config.get_legacy_brackets()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_legacy_brackets() is deprecated" in str(w[0].message)
            assert brackets is not None
            assert brackets.stop_loss_bps == 100

    def test_get_legacy_manage_warns(self, resolver_with_legacy_config):
        """Should emit DeprecationWarning when accessing legacy manage."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            manage = resolver_with_legacy_config.get_legacy_manage()
            
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_legacy_manage() is deprecated" in str(w[0].message)
            assert manage is not None
            assert manage.auto is True

    def test_get_legacy_exposure_returns_none_when_missing(self):
        """Should return None when legacy exposure is not configured."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            exp = resolver.get_legacy_exposure()
            assert exp is None

    def test_get_legacy_brackets_returns_none_when_missing(self):
        """Should return None when legacy brackets is not configured."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            brackets = resolver.get_legacy_brackets()
            assert brackets is None

    def test_get_legacy_manage_returns_none_when_missing(self):
        """Should return None when legacy manage is not configured."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            manage = resolver.get_legacy_manage()
            assert manage is None


class TestUtilityMethods:
    """Tests for utility methods and properties."""

    def test_trading_mode_property(self):
        """Should expose trading_mode as property."""
        config = AuroraConfig(trading_mode="production")
        resolver = DomainConfigResolver(config)
        
        assert resolver.trading_mode == "production"

    def test_raw_config_property(self):
        """Should expose underlying AuroraConfig via raw_config."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        assert resolver.raw_config is config

    def test_repr(self):
        """Should have informative repr."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        repr_str = repr(resolver)
        assert "DomainConfigResolver" in repr_str
        assert "testnet" in repr_str


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_resolver(self):
        """Should create resolver from AuroraConfig."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = create_resolver(config)
        
        assert isinstance(resolver, DomainConfigResolver)
        assert resolver.trading_mode == "testnet"

    def test_create_resolver_from_dict(self):
        """Should create resolver from dict with Pydantic validation."""
        config_dict = {
            "trading_mode": "testnet",
            "domains": {
                "execution_position": {
                    "watchdog": {
                        "ack_ttl_ms": 4000
                    }
                }
            }
        }
        resolver = create_resolver_from_dict(config_dict)
        
        assert isinstance(resolver, DomainConfigResolver)
        assert resolver.get_watchdog().ack_ttl_ms == 4000

    def test_create_resolver_from_dict_validates(self):
        """Should raise ValidationError for invalid dict."""
        from pydantic import ValidationError
        
        invalid_dict = {
            "trading_mode": "invalid_mode_xyz"  # Invalid mode
        }
        
        with pytest.raises(ValidationError):
            create_resolver_from_dict(invalid_dict)


class TestDefaultValues:
    """Tests for default configuration values."""

    @pytest.fixture
    def resolver_defaults(self):
        """Create resolver with all defaults."""
        config = AuroraConfig(trading_mode="testnet")
        return DomainConfigResolver(config)

    def test_exposure_guard_defaults(self, resolver_defaults):
        """Should have correct default values for ExposureGuard."""
        eg = resolver_defaults.get_exposure_guard()
        
        assert eg.pending_ttl_sec == 90
        assert eg.post_fill_ttl_sec == 5
        assert eg.stale_ttl_sec == 5
        assert eg.max_equity_utilization_pct == 0.20
        assert eg.max_portfolio_fraction == 0.20
        assert eg.max_long_utilization_pct == 0.20
        assert eg.max_short_utilization_pct == 0.20
        assert eg.max_directional_ratio == 2.0
        assert eg.max_concentration_pct == 0.10
        assert eg.pending_timeout_sec == 5

    def test_watchdog_defaults(self, resolver_defaults):
        """Should have correct default values for Watchdog."""
        wd = resolver_defaults.get_watchdog()
        
        assert wd.ack_ttl_ms == 8000
        assert wd.fill_ttl_ms == 30000
        assert wd.check_interval_ms == 1000
        assert wd.rps_limit == 10

    def test_fsm_open_defaults(self, resolver_defaults):
        """Should have correct default values for FSM Open."""
        fsm = resolver_defaults.get_fsm_open()
        
        assert fsm.idempotency_window_sec == 60

    def test_order_index_defaults(self, resolver_defaults):
        """Should have correct default values for Order Index."""
        oi = resolver_defaults.get_order_index()
        
        assert oi.ttl_sec == 3600

    def test_metrics_collector_defaults(self, resolver_defaults):
        """Should have correct default values for Metrics Collector."""
        mc = resolver_defaults.get_metrics_collector()
        
        assert mc.window_size_minutes == 60
        assert mc.recent_rejections_minutes == 5

    def test_idempotent_cancel_defaults(self, resolver_defaults):
        """Should have correct default values for Idempotent Cancel."""
        ic = resolver_defaults.get_idempotent_cancel()
        
        assert ic.max_retries == 2

    def test_execution_utils_defaults(self, resolver_defaults):
        """Should have correct default values for Execution Utils."""
        utils = resolver_defaults.get_execution_utils()
        
        assert utils.client_order_id_max_length == 32
        assert utils.basis_points_base == 10000.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_slots_optimization(self):
        """Should use __slots__ for memory efficiency."""
        assert hasattr(DomainConfigResolver, '__slots__')
        assert '_config' in DomainConfigResolver.__slots__
        assert '_domains' in DomainConfigResolver.__slots__

    def test_multiple_resolvers_independent(self):
        """Multiple resolvers should be independent."""
        config1 = AuroraConfig(trading_mode="testnet")
        config2 = AuroraConfig(
            trading_mode="production",
            domains=DomainsConfig(
                execution_position=ExecutionPositionDomainConfig(
                    watchdog=WatchdogConfig(ack_ttl_ms=1000)
                )
            )
        )
        
        resolver1 = DomainConfigResolver(config1)
        resolver2 = DomainConfigResolver(config2)
        
        assert resolver1.trading_mode == "testnet"
        assert resolver2.trading_mode == "production"
        assert resolver1.get_watchdog().ack_ttl_ms == 8000  # default
        assert resolver2.get_watchdog().ack_ttl_ms == 1000  # custom

    def test_config_immutability(self):
        """Resolver should not modify original config."""
        domains = DomainsConfig()
        config = AuroraConfig(trading_mode="testnet", domains=domains)
        original_mode = config.trading_mode
        
        resolver = DomainConfigResolver(config)
        _ = resolver.get_execution_position()
        _ = resolver.get_watchdog()
        
        assert config.trading_mode == original_mode


class TestIntegrationWithRealYaml:
    """Integration tests simulating real YAML config loading."""

    def test_realistic_config_structure(self):
        """Should work with realistic config structure from YAML."""
        # Simulates what ConfigLoader.load_config() produces
        config_dict = {
            "trading_mode": "testnet",
            "binance_api": {
                "testnet": {
                    "api_key": "test_key",
                    "api_secret": "test_secret"
                }
            },
            "trading": {
                "mode": "testnet",
                "instruments": {}
            },
            "domains": {
                "execution_position": {
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000
                    },
                    "exposure_guard": {
                        "pending_ttl_sec": 90,
                        "max_equity_utilization_pct": 0.95
                    }
                },
                "decision_making": {
                    "qos": {
                        "mode": "defer",
                        "enforce": False
                    }
                }
            }
        }
        
        resolver = create_resolver_from_dict(config_dict)
        
        assert resolver.trading_mode == "testnet"
        assert resolver.get_watchdog().ack_ttl_ms == 8000
        assert resolver.get_exposure_guard().max_equity_utilization_pct == 0.95
        assert resolver.get_decision_making().qos.mode == "defer"


class TestAttributeErrorBranches:
    """Tests for AttributeError exception branches in legacy accessors."""

    def test_legacy_exposure_attribute_error_branch(self):
        """Should handle AttributeError in get_legacy_exposure."""
        # Create a config with a mock trading that raises AttributeError
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        # Patch trading to raise AttributeError on attribute access
        class BadTrading:
            def __getattribute__(self, name):
                if name == 'execution':
                    raise AttributeError("Simulated error")
                return super().__getattribute__(name)
        
        resolver._config.trading = BadTrading()
        
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = resolver.get_legacy_exposure()
            assert result is None  # Should return None, not raise

    def test_legacy_brackets_attribute_error_branch(self):
        """Should handle AttributeError in get_legacy_brackets."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        class BadTrading:
            def __getattribute__(self, name):
                if name == 'execution':
                    raise AttributeError("Simulated error")
                return super().__getattribute__(name)
        
        resolver._config.trading = BadTrading()
        
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = resolver.get_legacy_brackets()
            assert result is None

    def test_legacy_manage_attribute_error_branch(self):
        """Should handle AttributeError in get_legacy_manage."""
        config = AuroraConfig(trading_mode="testnet")
        resolver = DomainConfigResolver(config)
        
        class BadTrading:
            def __getattribute__(self, name):
                if name == 'execution':
                    raise AttributeError("Simulated error")
                return super().__getattribute__(name)
        
        resolver._config.trading = BadTrading()
        
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = resolver.get_legacy_manage()
            assert result is None

    def test_resolve_domains_attribute_error_on_trading(self):
        """Should handle trading.domains access gracefully when trading has issues."""
        config = AuroraConfig(trading_mode="testnet", domains=None)
        resolver = DomainConfigResolver(config)
        
        # Should have used defaults since root domains is None and trading.domains doesn't exist
        assert resolver.get_watchdog().ack_ttl_ms == 8000  # default value

    def test_resolve_domains_uses_trading_domains_when_root_is_none(self):
        """Should use trading.domains when root domains is None."""
        # Create config where root domains is None but trading.domains exists
        domains = DomainsConfig(
            execution_position=ExecutionPositionDomainConfig(
                watchdog=WatchdogConfig(ack_ttl_ms=9999)
            )
        )
        trading = TradingConfig(mode="testnet", domains=domains)
        
        # Explicitly set root domains to None
        config = AuroraConfig(trading_mode="testnet", trading=trading, domains=None)
        resolver = DomainConfigResolver(config)
        
        # Should use trading.domains fallback
        assert resolver.get_watchdog().ack_ttl_ms == 9999
