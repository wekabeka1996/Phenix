"""
Tests for Feature Engineering Configuration (Pydantic validation + Resolver).

Tests cover:
1. Pydantic model validation (valid and invalid configs)
2. FeatureEngineeringConfig wrapper
3. Integration with DomainConfigResolver
"""

import pytest
from decimal import Decimal
from pydantic import ValidationError

from apps.reference.config_models import (
    EmaConfigDetailed,
    VolumeConfigDetailed,
    VolatilityConfigDetailed,
    LiquidityConfigDetailed,
    EmaBiasConfig,
    VolumeSpikeConfig,
    MacroSyncMetricsConfig,
    FeatureEngineeringDomainConfig,
    VolatilityStateConfig,
    DepthImbalanceConfig,
    DeltaPriceConfig,
)


# ============================================================================
# EMA Config Tests
# ============================================================================

class TestEmaConfigDetailed:
    """Tests for EMA configuration validation."""
    
    def test_defaults(self):
        """Test default values."""
        cfg = EmaConfigDetailed()
        assert cfg.period_short == 3
        assert cfg.period_long == 7
    
    def test_valid_custom_values(self):
        """Test valid custom periods."""
        cfg = EmaConfigDetailed(period_short=5, period_long=20)
        assert cfg.period_short == 5
        assert cfg.period_long == 20
    
    def test_period_long_must_be_greater_than_short(self):
        """Test that period_long > period_short is enforced."""
        with pytest.raises(ValidationError) as exc_info:
            EmaConfigDetailed(period_short=10, period_long=5)
        assert "period_long" in str(exc_info.value)
    
    def test_period_long_equals_short_fails(self):
        """Test that period_long == period_short fails."""
        with pytest.raises(ValidationError):
            EmaConfigDetailed(period_short=7, period_long=7)
    
    def test_period_short_min_boundary(self):
        """Test period_short >= 1."""
        cfg = EmaConfigDetailed(period_short=1, period_long=2)
        assert cfg.period_short == 1
        
        with pytest.raises(ValidationError):
            EmaConfigDetailed(period_short=0, period_long=5)
    
    def test_period_long_max_boundary(self):
        """Test period_long <= 200."""
        cfg = EmaConfigDetailed(period_short=50, period_long=200)
        assert cfg.period_long == 200
        
        with pytest.raises(ValidationError):
            EmaConfigDetailed(period_short=50, period_long=201)


# ============================================================================
# Volume Config Tests
# ============================================================================

class TestVolumeConfigDetailed:
    """Tests for Volume configuration validation."""
    
    def test_defaults(self):
        """Test default values."""
        cfg = VolumeConfigDetailed()
        assert cfg.sma_length == 5
        assert cfg.window_sec == 60
    
    def test_valid_custom_values(self):
        """Test valid custom values."""
        cfg = VolumeConfigDetailed(sma_length=10, window_sec=120)
        assert cfg.sma_length == 10
        assert cfg.window_sec == 120
    
    def test_sma_length_boundaries(self):
        """Test sma_length boundaries [2, 100]."""
        cfg = VolumeConfigDetailed(sma_length=2)
        assert cfg.sma_length == 2
        
        cfg = VolumeConfigDetailed(sma_length=100)
        assert cfg.sma_length == 100
        
        with pytest.raises(ValidationError):
            VolumeConfigDetailed(sma_length=1)
        
        with pytest.raises(ValidationError):
            VolumeConfigDetailed(sma_length=101)
    
    def test_window_sec_boundaries(self):
        """Test window_sec boundaries [1, 3600]."""
        cfg = VolumeConfigDetailed(window_sec=1)
        assert cfg.window_sec == 1
        
        cfg = VolumeConfigDetailed(window_sec=3600)
        assert cfg.window_sec == 3600
        
        with pytest.raises(ValidationError):
            VolumeConfigDetailed(window_sec=0)
        
        with pytest.raises(ValidationError):
            VolumeConfigDetailed(window_sec=3601)


# ============================================================================
# Liquidity Config Tests
# ============================================================================

class TestLiquidityConfigDetailed:
    """Tests for Liquidity configuration validation."""
    
    def test_defaults(self):
        """Test default values."""
        cfg = LiquidityConfigDetailed()
        assert cfg.depth_half == 1000.0
        assert cfg.kappa_min == 0.3
        assert cfg.kappa_max == 1.0
    
    def test_kappa_max_must_be_gte_kappa_min(self):
        """Test that kappa_max >= kappa_min is enforced."""
        # Valid: max > min
        cfg = LiquidityConfigDetailed(kappa_min=0.2, kappa_max=0.8)
        assert cfg.kappa_min == 0.2
        assert cfg.kappa_max == 0.8
        
        # Valid: max == min
        cfg = LiquidityConfigDetailed(kappa_min=0.5, kappa_max=0.5)
        assert cfg.kappa_min == cfg.kappa_max
        
        # Invalid: max < min
        with pytest.raises(ValidationError):
            LiquidityConfigDetailed(kappa_min=0.8, kappa_max=0.2)
    
    def test_depth_half_positive(self):
        """Test depth_half must be positive."""
        cfg = LiquidityConfigDetailed(depth_half=0.1)
        assert cfg.depth_half == 0.1
        
        with pytest.raises(ValidationError):
            LiquidityConfigDetailed(depth_half=0)
        
        with pytest.raises(ValidationError):
            LiquidityConfigDetailed(depth_half=-100)


# ============================================================================
# Macro Sync Config Tests
# ============================================================================

class TestMacroSyncMetricsConfig:
    """Tests for Macro Sync configuration validation."""
    
    def test_defaults(self):
        """Test default values."""
        cfg = MacroSyncMetricsConfig()
        assert cfg.enabled is True
        assert cfg.window == 60
        assert cfg.min_buffer_size == 3
        assert cfg.anchors == ["BTCUSDT", "ETHUSDT"]
    
    def test_anchors_must_end_with_usdt(self):
        """Test that anchors must end with USDT."""
        # Valid anchors
        cfg = MacroSyncMetricsConfig(anchors=["SOLUSDT", "BNBUSDT"])
        assert len(cfg.anchors) == 2
        
        # Invalid anchor format
        with pytest.raises(ValidationError) as exc_info:
            MacroSyncMetricsConfig(anchors=["BTCETH", "ETHUSDT"])
        assert "USDT" in str(exc_info.value)
    
    def test_anchors_must_have_at_least_one(self):
        """Test that at least one anchor is required."""
        with pytest.raises(ValidationError):
            MacroSyncMetricsConfig(anchors=[])
    
    def test_window_boundaries(self):
        """Test window boundaries [10, 1000]."""
        cfg = MacroSyncMetricsConfig(window=10)
        assert cfg.window == 10
        
        cfg = MacroSyncMetricsConfig(window=1000)
        assert cfg.window == 1000
        
        with pytest.raises(ValidationError):
            MacroSyncMetricsConfig(window=9)
        
        with pytest.raises(ValidationError):
            MacroSyncMetricsConfig(window=1001)


# ============================================================================
# FeatureEngineeringDomainConfig Tests
# ============================================================================

class TestFeatureEngineeringDomainConfig:
    """Tests for complete Feature Engineering domain configuration."""
    
    def test_defaults(self):
        """Test all defaults are set correctly."""
        cfg = FeatureEngineeringDomainConfig()
        
        assert cfg.enable_new_metrics is True
        assert cfg.ema.period_short == 3
        assert cfg.ema.period_long == 7
        assert cfg.volume.sma_length == 5
        assert cfg.volatility.sma_length == 10
        assert cfg.liquidity.depth_half == 1000.0
        assert cfg.macro_sync.enabled is True
    
    def test_nested_config_validation(self):
        """Test that nested configs are validated."""
        # Invalid EMA config should fail
        with pytest.raises(ValidationError):
            FeatureEngineeringDomainConfig(
                ema={"period_short": 10, "period_long": 5}  # Invalid: long < short
            )
    
    def test_get_ema_alpha_helper(self):
        """Test EMA alpha calculation helper."""
        cfg = FeatureEngineeringDomainConfig(
            ema={"period_short": 3, "period_long": 7}
        )
        
        # Alpha = 2 / (period + 1)
        assert cfg.get_ema_alpha("short") == pytest.approx(0.5, rel=1e-6)  # 2/4
        assert cfg.get_ema_alpha("long") == pytest.approx(0.25, rel=1e-6)  # 2/8
    
    def test_from_dict(self):
        """Test creating config from dict."""
        config_dict = {
            "enable_new_metrics": False,
            "ema": {"period_short": 5, "period_long": 15},
            "volume": {"sma_length": 10, "window_sec": 120},
            "macro_sync": {"enabled": False, "window": 30}
        }
        
        cfg = FeatureEngineeringDomainConfig(**config_dict)
        
        assert cfg.enable_new_metrics is False
        assert cfg.ema.period_short == 5
        assert cfg.ema.period_long == 15
        assert cfg.volume.sma_length == 10
        assert cfg.macro_sync.enabled is False
    
    def test_forbid_extra_fields(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureEngineeringDomainConfig(unknown_field="value")
        assert "extra" in str(exc_info.value).lower()
    
    def test_defaults_config_present(self):
        """Test that defaults config is present and has correct values."""
        cfg = FeatureEngineeringDomainConfig()
        
        # Defaults config should be present
        assert hasattr(cfg, 'defaults')
        assert cfg.defaults.neutral_value == 0.5
        assert cfg.defaults.zero_value == 0.0
        assert cfg.defaults.correlation_default == 0.0
        assert cfg.defaults.ms_per_sec == 1000
    
    def test_defaults_config_validation(self):
        """Test that defaults config validates boundaries."""
        from apps.reference.config_models import FeatureDefaultsConfig
        
        # neutral_value must be in [0, 1]
        with pytest.raises(ValidationError):
            FeatureDefaultsConfig(neutral_value=1.5)
        
        # zero_value must be in [0, 1]
        with pytest.raises(ValidationError):
            FeatureDefaultsConfig(zero_value=-0.1)
        
        # correlation_default must be in [-1, 1]
        with pytest.raises(ValidationError):
            FeatureDefaultsConfig(correlation_default=2.0)


# ============================================================================
# FeatureEngineeringConfig Wrapper Tests
# ============================================================================

class TestFeatureEngineeringConfigWrapper:
    """Tests for the FeatureEngineeringConfig wrapper class."""
    
    def test_from_dict(self):
        """Test creating wrapper from dict."""
        from apps.reference.domains.feature_engineering.feature_engineering import (
            FeatureEngineeringConfig,
        )
        
        config_dict = {
            "feature_engineering": {
                "enable_new_metrics": True,
                "ema": {"period_short": 5, "period_long": 10}
            }
        }
        
        wrapper = FeatureEngineeringConfig(config_dict)
        
        assert wrapper.enable_new_metrics is True
        assert wrapper.ema_period_short == 5
        assert wrapper.ema_period_long == 10
    
    def test_from_nested_dict_domains_path(self):
        """Test dict with domains.feature_engineering path."""
        from apps.reference.domains.feature_engineering.feature_engineering import (
            FeatureEngineeringConfig,
        )
        
        config_dict = {
            "domains": {
                "feature_engineering": {
                    "enable_new_metrics": False,
                    "volume": {"window_sec": 120}
                }
            }
        }
        
        wrapper = FeatureEngineeringConfig(config_dict)
        
        assert wrapper.enable_new_metrics is False
        assert wrapper.volume_window_sec == 120
    
    def test_from_nested_dict_trading_path(self):
        """Test dict with trading.feature_engineering path."""
        from apps.reference.domains.feature_engineering.feature_engineering import (
            FeatureEngineeringConfig,
        )
        
        config_dict = {
            "trading": {
                "feature_engineering": {
                    "liquidity": {"depth_half": 2000}
                }
            }
        }
        
        wrapper = FeatureEngineeringConfig(config_dict)
        
        assert wrapper.depth_half == Decimal("2000")
    
    def test_typed_accessors(self):
        """Test all typed accessors return correct types."""
        from apps.reference.domains.feature_engineering.feature_engineering import (
            FeatureEngineeringConfig,
        )
        
        wrapper = FeatureEngineeringConfig({})
        
        # Boolean accessors
        assert isinstance(wrapper.enable_new_metrics, bool)
        assert isinstance(wrapper.macro_sync_enabled, bool)
        
        # Int accessors
        assert isinstance(wrapper.ema_period_short, int)
        assert isinstance(wrapper.volume_sma_length, int)
        assert isinstance(wrapper.volatility_window_ms, int)
        
        # Float accessors
        assert isinstance(wrapper.ema_short_alpha, float)
        assert isinstance(wrapper.ema_long_alpha, float)
        
        # Decimal accessors
        assert isinstance(wrapper.depth_half, Decimal)
        assert isinstance(wrapper.kappa_min, Decimal)
        assert isinstance(wrapper.volume_spike_cap, Decimal)
        
        # List accessors
        assert isinstance(wrapper.macro_sync_anchors, list)
        
        # Default values accessors (no more magic numbers!)
        assert isinstance(wrapper.neutral_value, Decimal)
        assert isinstance(wrapper.zero_value, Decimal)
        assert isinstance(wrapper.correlation_default, float)
        assert isinstance(wrapper.ms_per_sec, int)
        
        # Check actual default values
        assert wrapper.neutral_value == Decimal("0.5")
        assert wrapper.zero_value == Decimal("0.0")
        assert wrapper.correlation_default == 0.0
        assert wrapper.ms_per_sec == 1000
    
    def test_computed_properties(self):
        """Test computed properties like ema_alpha."""
        from apps.reference.domains.feature_engineering.feature_engineering import (
            FeatureEngineeringConfig,
        )
        
        config_dict = {
            "feature_engineering": {
                "ema": {"period_short": 4, "period_long": 9}
            }
        }
        
        wrapper = FeatureEngineeringConfig(config_dict)
        
        # Alpha = 2 / (period + 1)
        assert wrapper.ema_short_alpha == pytest.approx(0.4, rel=1e-6)  # 2/5
        assert wrapper.ema_long_alpha == pytest.approx(0.2, rel=1e-6)   # 2/10
        
        # Window in ms
        assert wrapper.volume_window_ms == wrapper.volume_window_sec * 1000


# ============================================================================
# Integration with DomainConfigResolver Tests
# ============================================================================

class TestDomainConfigResolverIntegration:
    """Tests for integration with DomainConfigResolver."""
    
    def test_resolver_returns_typed_config(self):
        """Test that resolver returns FeatureEngineeringDomainConfig."""
        from apps.reference.config_models import AuroraConfig, DomainsConfig
        from apps.reference.domain_config import DomainConfigResolver
        
        # Create minimal AuroraConfig
        aurora_config = AuroraConfig(
            domains=DomainsConfig(
                feature_engineering=FeatureEngineeringDomainConfig(
                    enable_new_metrics=False
                )
            )
        )
        
        resolver = DomainConfigResolver(aurora_config)
        fe_config = resolver.get_feature_engineering()
        
        assert isinstance(fe_config, FeatureEngineeringDomainConfig)
        assert fe_config.enable_new_metrics is False
    
    def test_wrapper_from_resolver(self):
        """Test FeatureEngineeringConfig from resolver."""
        from apps.reference.config_models import AuroraConfig, DomainsConfig
        from apps.reference.domain_config import DomainConfigResolver
        from apps.reference.domains.feature_engineering.feature_engineering import (
            FeatureEngineeringConfig,
        )
        
        aurora_config = AuroraConfig(
            domains=DomainsConfig(
                feature_engineering=FeatureEngineeringDomainConfig(
                    ema=EmaConfigDetailed(period_short=6, period_long=12)
                )
            )
        )
        
        resolver = DomainConfigResolver(aurora_config)
        wrapper = FeatureEngineeringConfig(resolver)
        
        assert wrapper.ema_period_short == 6
        assert wrapper.ema_period_long == 12
