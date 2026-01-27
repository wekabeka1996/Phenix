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


def _valid_decision_kwargs():
    return {
        "testnet": None,
        "production": None,
        "signal_threshold": 0.25,
        "cooldown_sec": None,
        "side_bias_min_score": None,
        "side_bias_penalty_factor": None,
        "side_bias_target_ratio": None,
        "side_bias_window_sec": None,
        "retry_ttl_ms": 5000,
        "retry_max_count": 3,
        "retry_backoff_factor": 1.5,
        "signal_weights": {
            "obi": 0.2,
            "tfi": 0.2,
            "delta_price": 0.2,
            "ema_bias": 0.2,
            "volume_spike": 0.2,
            "volatility_state": 0.0,
            "depth_imbalance": 0.0,
            "macro_sync": 0.0,
            "macro_resid": 0.0,
        },
        "signals": {
            "normalize_signals_mode": "off",
            "enable_new_metrics": True,
            "delta_price_cap_pct": 0.02,
        },
        "direction_strength_scoring": {
            "directional_features": ["delta_price"],
            "strength_features": [],
            "strength_alpha": 0.5,
            "strength_cap": 1.0,
        },
        "kelly": {
            "base_probability": 0.5,
            "kelly_cap": 0.25,
            "kelly_alpha": 0.8,
            "payoff_ratio_r": 1.5,
        },
        "qos": {
            "exposure_block_cooldown_sec": 30,
            "symbol_cooldown_sec": 1,
            "max_intents_per_minute_per_symbol": 60,
            "mode": "shadow",
            "enforce": False,
        },
        "bar_gating": None,
        "behavior_fsm": None,
        "roi_exit": None,
        "mean_reversion": None,
        "regime_thresholds": {},
        "regime_threshold_multipliers": {},
        "symbols_to_track": None,
        "neutral_threshold": None,
    }


def _valid_execution_kwargs():
    # TASK-ZOMBIE-FIX / PURGE-DIRTY-DOZEN: Removed dead fields
    return {
        "manage": None,
        "exposure": None,
        "watchdog": None,
        "fallback": None,
        "limit_orders": None,
        "orders": None,
        "fsm_periodic_cleanup_enabled": False,
        "cooldown_after_close_ms": 0,
        "anti_race_close_ms": 250,
        # Removed: open_order_type, min_post_interval_per_symbol_ms (PURGE-DIRTY-DOZEN)
        "order_params": None,
        "preflight_backoff_ms": None,
        "allow_trade_with_guardian_tidy_only": None,
        "order_guardian": None,
    }


def _valid_market_data_kwargs():
    # PURGE-DIRTY-DOZEN: Removed api_call_limits (dead stub, REST replaced by WebSocket)
    return {
        "poll_interval_sec": 3.0,
        "use_multiprocessing": False,
        "websocket_streams": ["kline_1m"],
        # Removed: api_call_limits (PURGE-DIRTY-DOZEN)
        "macro_sync": None,
    }


def _valid_exposure_kwargs():
    # TASK-ZOMBIE-FIX: Removed dead fields (max_side_utilization_pct, per_symbol_cap_pct, 
    # pending_reservation_ttl_sec, positions_stale_ttl_sec)
    return {
        "max_equity_utilization_pct": 0.30,
        "max_portfolio_fraction": 0.95,
        # Removed: max_side_utilization_pct (TASK-ZOMBIE-FIX)
        "max_directional_ratio": 20.0,
        # Removed: per_symbol_cap_pct (TASK-ZOMBIE-FIX)
        "pending_ttl_sec": 90,
        # Removed: pending_reservation_ttl_sec (TASK-ZOMBIE-FIX)
        "post_fill_hold_ttl_sec": 5,
        # Removed: positions_stale_ttl_sec (duplicate, SSOT is domains.position_tracking)
        "leverage_defaults": {"long": 1, "short": 1},
        "count_pending_orders": True,
        "exclude_reduce_only": True,
    }


class TestTopLevelForbidEnforcement:
    """Contract tests: all top-level configs have extra='forbid'."""
    
    def test_decision_config_forbid_rejects_unknown_keys_strict(self):
        """DecisionConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = DecisionConfig(**_valid_decision_kwargs())
        assert valid_config.signal_threshold == 0.25
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            DecisionConfig(**_valid_decision_kwargs(), unknown_field="should_fail")
        assert "field required" not in str(exc_info.value).lower()
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_manage_config_forbid_rejects_unknown_keys_strict(self):
        """ManageConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK (failsafe removed in TASK-ZOMBIE-FIX)
        valid_config = ManageConfig(brackets=None, emergency=None, auto=True, orphan_monitor=None)
        assert valid_config.auto is True
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            ManageConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_execution_config_forbid_rejects_unknown_keys_strict(self):
        """ExecutionConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = ExecutionConfig(**_valid_execution_kwargs())
        assert valid_config.fsm_periodic_cleanup_enabled is False
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            ExecutionConfig(**_valid_execution_kwargs(), unknown_field="should_fail")
        assert "field required" not in str(exc_info.value).lower()
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_market_data_config_forbid_rejects_unknown_keys_strict(self):
        """MarketDataConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = MarketDataConfig(**_valid_market_data_kwargs())
        assert valid_config.poll_interval_sec == 3.0
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            MarketDataConfig(**_valid_market_data_kwargs(), unknown_field="should_fail")
        assert "field required" not in str(exc_info.value).lower()
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_exposure_config_forbid_rejects_unknown_keys_strict(self):
        """ExposureConfig rejects unknown keys (extra='forbid')."""
        # Valid config OK
        valid_config = ExposureConfig(**_valid_exposure_kwargs())
        assert valid_config.max_equity_utilization_pct == 0.30
        
        # Unknown key rejected
        with pytest.raises(ValidationError) as exc_info:
            ExposureConfig(**_valid_exposure_kwargs(), unknown_field="should_fail")
        assert "field required" not in str(exc_info.value).lower()
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()


class TestExplicitFieldsPresent:
    """Verify all explicitly documented fields exist in models."""
    
    def test_decision_config_has_all_known_fields(self):
        """DecisionConfig has all consumption-proven fields."""
        config = DecisionConfig(**_valid_decision_kwargs())
        
        # Core fields
        assert hasattr(config, 'signal_threshold')
        assert hasattr(config, 'signal_weights')
        assert hasattr(config, 'signals')
        assert hasattr(config, 'kelly')
        assert hasattr(config, 'qos')
        # SIZING-MARGIN-FIRST-SSOT-02: sizing is SSOT in instruments.*, not DecisionConfig
        assert not hasattr(config, 'position_sizing')
        
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
        config = ExecutionConfig(**_valid_execution_kwargs())
        
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
        
        # PURGE-DIRTY-DOZEN: Removed dead fields - these should NOT exist now
        # open_order_type, min_post_interval_per_symbol_ms removed
        assert hasattr(config, 'order_params')
        assert hasattr(config, 'preflight_backoff_ms')
        assert hasattr(config, 'allow_trade_with_guardian_tidy_only')
        assert hasattr(config, 'order_guardian')
    
    def test_exposure_config_has_all_known_fields(self):
        """ExposureConfig has all consumption-proven fields."""
        config = ExposureConfig(**_valid_exposure_kwargs())
        
        assert hasattr(config, 'max_equity_utilization_pct')
        assert hasattr(config, 'max_portfolio_fraction')
        # TASK-ZOMBIE-FIX: Removed dead fields
        # max_side_utilization_pct, per_symbol_cap_pct, pending_reservation_ttl_sec, positions_stale_ttl_sec removed
        assert hasattr(config, 'max_directional_ratio')
        assert hasattr(config, 'pending_ttl_sec')
        assert hasattr(config, 'post_fill_hold_ttl_sec')
        assert hasattr(config, 'leverage_defaults')
        assert hasattr(config, 'count_pending_orders')
        assert hasattr(config, 'exclude_reduce_only')
    
    def test_market_data_config_has_all_known_fields(self):
        """MarketDataConfig has all consumption-proven fields."""
        config = MarketDataConfig(**_valid_market_data_kwargs())
        
        assert hasattr(config, 'poll_interval_sec')
        assert hasattr(config, 'use_multiprocessing')
        assert hasattr(config, 'websocket_streams')
        # PURGE-DIRTY-DOZEN: Removed api_call_limits
        assert hasattr(config, 'macro_sync')


class TestDeprecatedFieldsOptional:
    """Deprecated fields should be Optional and have default None."""
    
    def test_decision_config_deprecated_fields_optional(self):
        """DecisionConfig deprecated fields are Optional."""
        config = DecisionConfig(**_valid_decision_kwargs())
        
        # Deprecated fields
        assert config.cooldown_sec is None  # Use per-instrument instead
        assert config.symbols_to_track is None  # Use instruments SSOT
    
    def test_execution_config_deprecated_fields_optional(self):
        """ExecutionConfig deprecated fields are Optional.
        
        PURGE-DIRTY-DOZEN: open_order_type, min_post_interval_per_symbol_ms removed.
        """
        config = ExecutionConfig(**_valid_execution_kwargs())
        
        # Remaining optional fields (dead fields already purged)
        assert config.order_params is None
        assert config.preflight_backoff_ms is None
        assert config.allow_trade_with_guardian_tidy_only is None
        assert config.order_guardian is None
