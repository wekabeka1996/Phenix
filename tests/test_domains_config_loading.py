"""
Tests for domains configuration loading.

Verifies that ConfigLoader correctly loads and merges domains.yaml
and that all domain configurations are accessible via Pydantic models.
"""

import pytest
from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig


class TestDomainsConfigLoading:
    """Test loading of domain-specific configurations."""
    
    def test_config_loader_loads_domains_yaml(self):
        """Test that ConfigLoader loads domains.yaml successfully."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        # Verify config was loaded
        assert config is not None
        assert isinstance(config, AuroraConfig)
        
        # Verify domains attribute exists
        assert hasattr(config, 'domains') or hasattr(config.trading, 'domains')
    
    def test_decision_making_config(self):
        """Test DecisionMaking domain config loading."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        # Get domains config
        domains = config.domains if hasattr(config, 'domains') else config.trading.domains
        
        # Position sizing
        assert domains.decision_making.position_sizing.min_position_size_usd == 10
        assert domains.decision_making.position_sizing.liquidity_based_cap_usd == 10000
        
        # QoS
        assert domains.decision_making.qos.exposure_block_cooldown_sec == 10
        assert domains.decision_making.qos.symbol_cooldown_sec == 3
        assert domains.decision_making.qos.max_intents_per_minute_per_symbol == 6
        assert domains.decision_making.qos.mode == "defer"
        
        # Features TTL
        assert domains.decision_making.features.ttl_sec == 5
        
        # Bar gating
        assert domains.decision_making.bar_gating.bar_ms == 900000  # 15 minutes
        
        # Behavior FSM
        assert domains.decision_making.behavior_fsm.high_vol_multiplier == 2.0
        assert domains.decision_making.behavior_fsm.low_vol_multiplier == 0.5
    
    def test_feature_engineering_config(self):
        """Test FeatureEngineering domain config loading."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        domains = config.domains if hasattr(config, 'domains') else config.trading.domains
        
        # EMA
        assert domains.feature_engineering.ema.period_short == 3
        assert domains.feature_engineering.ema.period_long == 7
        
        # Volume
        assert domains.feature_engineering.volume.sma_length == 5
        assert domains.feature_engineering.volume.window_sec == 60
        
        # Volatility
        assert domains.feature_engineering.volatility.sma_length == 10
        assert domains.feature_engineering.volatility.window_sec == 60
        
        # Liquidity
        assert domains.feature_engineering.liquidity.depth_half == 1000
        assert domains.feature_engineering.liquidity.kappa_min == 0.3
        assert domains.feature_engineering.liquidity.kappa_max == 1.0
    
    def test_execution_position_config(self):
        """Test ExecutionPosition domain config loading."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        domains = config.domains if hasattr(config, 'domains') else config.trading.domains
        
        # Watchdog
        assert domains.execution_position.watchdog.ack_ttl_ms == 8000
        assert domains.execution_position.watchdog.fill_ttl_ms == 30000
        assert domains.execution_position.watchdog.rps_limit == 10
        
        # Exposure Guard
        assert domains.execution_position.exposure_guard.pending_ttl_sec == 90
        assert domains.execution_position.exposure_guard.post_fill_ttl_sec == 5
        assert domains.execution_position.exposure_guard.stale_ttl_sec == 5
        
        # FSM Open
        assert domains.execution_position.fsm_open.idempotency_window_sec == 60
        
        # Order Index
        assert domains.execution_position.order_index.ttl_sec == 3600
        
        # Metrics Collector
        assert domains.execution_position.metrics_collector.window_size_minutes == 60
        
        # Idempotent Cancel
        assert domains.execution_position.idempotent_cancel.max_retries == 2
    
    def test_risk_management_config(self):
        """Test RiskManagement domain config loading."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        domains = config.domains if hasattr(config, 'domains') else config.trading.domains
        
        # Risk score weights
        assert domains.risk_management.risk_score_weights.delta_price_pct == 0.1
        assert domains.risk_management.risk_score_weights.obi == 0.3
        assert domains.risk_management.risk_score_weights.tfi == 0.3
        assert domains.risk_management.risk_score_weights.absorption_inverse == 0.3
        
        # Trading allowed thresholds
        assert domains.risk_management.trading_allowed_thresholds.max_risk_score == 0.8
        
        # Validation
        assert domains.risk_management.validation.total_weight_min == 0.5
        assert domains.risk_management.validation.total_weight_max == 2.0
    
    def test_account_observer_config(self):
        """Test AccountObserver domain config loading."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        domains = config.domains if hasattr(config, 'domains') else config.trading.domains
        
        assert domains.account_observer.poll_interval_sec == 5
        assert domains.account_observer.trade_limit == 10
        assert domains.account_observer.symbols == []
    
    def test_position_tracking_config(self):
        """Test PositionTracking domain config loading."""
        loader = ConfigLoader()
        config = loader.load_config()
        
        domains = config.domains if hasattr(config, 'domains') else config.trading.domains
        
        assert domains.position_tracking.precision.quantity_min_threshold == 1e-9
        assert domains.position_tracking.precision.flat_position_threshold == 1e-12
        assert domains.position_tracking.precision.decimal_places == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
