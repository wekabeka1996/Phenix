"""
CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Contract Tests for extra='forbid' Enforcement

Перевіряє, що top-level configs (Decision/Manage/Execution/MarketData/Exposure)
мають extra='forbid' та відхиляють невідомі ключі.
"""

import pytest
from pydantic import ValidationError
from apps.reference.config_models import (
    DecisionConfig,
    ManageConfig,
    ExecutionConfig,
    MarketDataConfig,
    ExposureConfig,
)


class TestTopLevelForbidEnforcement:
    """Contract tests: all top-level configs have extra='forbid'."""
    
    def test_decision_config_forbid_rejects_unknown_keys_strict(self):
        """DecisionConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = DecisionConfig(signal_threshold=0.25)
        assert valid_config.signal_threshold == 0.25
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            DecisionConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_manage_config_forbid_rejects_unknown_keys_strict(self):
        """ManageConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = ManageConfig(auto=True)
        assert valid_config.auto is True
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            ManageConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_execution_config_forbid_rejects_unknown_keys_strict(self):
        """ExecutionConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = ExecutionConfig(fsm_periodic_cleanup_enabled=False)
        assert valid_config.fsm_periodic_cleanup_enabled is False
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            ExecutionConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_market_data_config_forbid_rejects_unknown_keys_strict(self):
        """MarketDataConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = MarketDataConfig(poll_interval_sec=3.0)
        assert valid_config.poll_interval_sec == 3.0
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            MarketDataConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_exposure_config_forbid_rejects_unknown_keys_strict(self):
        """ExposureConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = ExposureConfig(max_equity_utilization_pct=0.30)
        assert valid_config.max_equity_utilization_pct == 0.30
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            ExposureConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()


class TestExplicitFieldsPresent:
    """Verify all explicitly documented fields exist in models."""
    
    def test_decision_config_has_all_known_fields(self):
        """DecisionConfig has all consumption-proven fields."""
        config = DecisionConfig()
        
        # Core fields
        assert hasattr(config, 'signal_threshold')
        assert hasattr(config, 'signal_weights')
        assert hasattr(config, 'signals')
        assert hasattr(config, 'position_sizing')
        assert hasattr(config, 'kelly')
        assert hasattr(config, 'qos')
        
        # Optional domain configs
        assert hasattr(config, 'bar_gating')
        assert hasattr(config, 'behavior_fsm')
        assert hasattr(config, 'roi_exit')
        assert hasattr(config, 'mean_reversion')
        
        # Mode overrides
        assert hasattr(config, 'testnet')
        assert hasattr(config, 'production')
        
        # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Newly added fields
        assert hasattr(config, 'cooldown_sec')
        assert hasattr(config, 'side_bias_min_score')
        assert hasattr(config, 'side_bias_penalty_factor')
        assert hasattr(config, 'side_bias_target_ratio')
        assert hasattr(config, 'side_bias_window_sec')
        assert hasattr(config, 'regime_threshold_multipliers')
        assert hasattr(config, 'symbols_to_track')
        assert hasattr(config, 'neutral_threshold')
    
    def test_execution_config_has_all_known_fields(self):
        """ExecutionConfig has all consumption-proven fields."""
        config = ExecutionConfig()
        
        # Core fields
        assert hasattr(config, 'manage')
        assert hasattr(config, 'exposure')
        assert hasattr(config, 'watchdog')
        
        # CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Newly typed
        assert hasattr(config, 'fallback')
        assert hasattr(config, 'limit_orders')
        assert hasattr(config, 'orders')
        assert hasattr(config, 'fsm_periodic_cleanup_enabled')
        assert hasattr(config, 'anti_race_close_ms')
        
        # DEPRECATED fields (kept for backward compat)
        assert hasattr(config, 'open_order_type')
        assert hasattr(config, 'order_params')
        assert hasattr(config, 'preflight_backoff_ms')
        assert hasattr(config, 'min_post_interval_per_symbol_ms')
        assert hasattr(config, 'allow_trade_with_guardian_tidy_only')
        assert hasattr(config, 'order_guardian')
    
    def test_exposure_config_has_all_known_fields(self):
        """ExposureConfig has all consumption-proven fields."""
        config = ExposureConfig()
        
        assert hasattr(config, 'max_equity_utilization_pct')
        assert hasattr(config, 'max_portfolio_fraction')
        assert hasattr(config, 'max_side_utilization_pct')
        assert hasattr(config, 'max_directional_ratio')
        assert hasattr(config, 'per_symbol_cap_pct')
        assert hasattr(config, 'pending_ttl_sec')
        assert hasattr(config, 'pending_reservation_ttl_sec')
        assert hasattr(config, 'post_fill_hold_ttl_sec')
        assert hasattr(config, 'positions_stale_ttl_sec')
        assert hasattr(config, 'leverage_defaults')
        assert hasattr(config, 'count_pending_orders')
        assert hasattr(config, 'exclude_reduce_only')
    
    def test_market_data_config_has_all_known_fields(self):
        """MarketDataConfig has all consumption-proven fields."""
        config = MarketDataConfig()
        
        assert hasattr(config, 'poll_interval_sec')
        assert hasattr(config, 'use_multiprocessing')
        assert hasattr(config, 'websocket_streams')
        assert hasattr(config, 'api_call_limits')
        assert hasattr(config, 'macro_sync')


class TestDeprecatedFieldsOptional:
    """Deprecated fields should be Optional and have default None."""
    
    def test_decision_config_deprecated_fields_optional(self):
        """DecisionConfig deprecated fields are Optional."""
        config = DecisionConfig()
        
        # Deprecated fields
        assert config.cooldown_sec is None  # Use per-instrument instead
        assert config.symbols_to_track is None  # Use instruments SSOT
    
    def test_execution_config_deprecated_fields_optional(self):
        """ExecutionConfig deprecated fields are Optional."""
        config = ExecutionConfig()
        
        # Dead fields (no consumption found)
        assert config.open_order_type is None
        assert config.order_params is None
        assert config.preflight_backoff_ms is None
        assert config.min_post_interval_per_symbol_ms is None
        assert config.allow_trade_with_guardian_tidy_only is None
        assert config.order_guardian is None
