"""
CFG-DICT-ANY-BURN-13: Typed Runtime Configs Tests

Перевіряє:
1. DecisionModeOverrideConfig: accept consumed keys, reject unknown
2. KlinesConfig: typed interval/limit
3. EmergencyConfig/OrphanMonitorConfig: strict validation
4. ExecutionConfig.watchdog: typed WatchdogConfig
"""

import pytest
from pydantic import ValidationError
from apps.reference.config_models import (
    DecisionConfig,
    DecisionModeOverrideConfig,
    ManageConfig,
    EmergencyConfig,
    OrphanMonitorConfig,
    ExecutionConfig,
    WatchdogConfig,
    # PURGE-DIRTY-DOZEN: Removed ApiCallLimits, KlinesConfig (dead stubs) - 2026-01-25
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
            "macro_resid": 0.0,
        },
        "signals": {
            "normalize_signals_mode": "off",
            "enable_new_metrics": True,
            "delta_price_cap_pct": 0.005,
        },
        "direction_strength_scoring": {
            "directional_features": ["delta_price"],
            "strength_features": ["volume_spike"],
            "strength_alpha": 0.5,
            "strength_cap": 1.5,
        },
        "kelly": {
            "base_probability": 0.5,
            "kelly_cap": 0.25,
            "kelly_alpha": 0.8,
            "payoff_ratio_r": 1.5,
            "p_min": 0.45,
            "p_max": 0.65,
            "uplift_factor": 0.2,
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
    return {
        "manage": None,
        "exposure": None,
        "watchdog": None,
        "fallback": None,
        "limit_orders": None,
        "orders": None,
        "fsm_periodic_cleanup_enabled": False,
        "cooldown_after_close_ms": 1000,
        "anti_race_close_ms": 250,
        # PURGE-DIRTY-DOZEN: Removed open_order_type, min_post_interval_per_symbol_ms
        "order_params": None,
        "preflight_backoff_ms": None,
        "allow_trade_with_guardian_tidy_only": None,
        "order_guardian": None,
    }


class TestDecisionModeOverrides:
    """A: DecisionConfig testnet/production overrides - typed."""
    
    def test_decision_overrides_accept_consumed_keys_only(self):
        """DecisionModeOverrideConfig accepts known override keys."""
        # Known pattern: signal_threshold override (from config_loader.py L120-140)
        override = DecisionModeOverrideConfig(signal_threshold=0.15)
        assert override.signal_threshold == 0.15

        # Unknown keys are forbidden (extra='forbid')
        with pytest.raises(ValidationError) as exc_info:
            DecisionModeOverrideConfig(signal_threshold=0.25, custom_field="not_allowed")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_decision_config_forbid_unknown_top_level(self):
        """DecisionConfig top-level has extra='forbid' (all fields explicit).
        
        CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: DecisionConfig now extra='forbid' (no unknown keys)."""
        # This SHOULD raise - extra='forbid' at top level
        with pytest.raises(ValidationError) as exc_info:
            DecisionConfig(**_valid_decision_kwargs(), unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_decision_overrides_optional_ok(self):
        """DecisionConfig.testnet/production are optional."""
        config = DecisionConfig(**_valid_decision_kwargs())
        assert config.testnet is None
        assert config.production is None

        base = dict(_valid_decision_kwargs())
        base.pop("testnet", None)
        base.pop("production", None)
        config_with_overrides = DecisionConfig(
            **base,
            testnet={"signal_threshold": 0.15},
            production={"signal_threshold": 0.25},
        )
        assert config_with_overrides.testnet.signal_threshold == 0.15
        assert config_with_overrides.production.signal_threshold == 0.25


# PURGE-DIRTY-DOZEN: Removed TestKlinesConfig class (ApiCallLimits, KlinesConfig deleted) - 2026-01-25


class TestManageConfigTyped:
    """C: ManageConfig emergency/orphan_monitor - typed."""
    
    def test_emergency_config_strict_stub(self):
        """EmergencyConfig is strict typed config."""
        emergency = EmergencyConfig(enabled=False, wait_mode_bars=1)
        assert emergency.enabled is False
        
        # extra='forbid' - reject unknown
        with pytest.raises(ValidationError) as exc_info:
            EmergencyConfig(enabled=False, wait_mode_bars=1, unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_orphan_monitor_config_temporary_allow(self):
        """OrphanMonitorConfig rejects unknown fields (extra='forbid')."""
        # All required fields must be provided
        orphan = OrphanMonitorConfig(
            enabled=True,
            run_on_startup=False,
            periodic_interval_sec=60,
            min_order_age_sec=30,
            batch_cancel_limit=10,
            rate_limit_per_min=20,
        )
        assert orphan.enabled is True

        with pytest.raises(ValidationError) as exc_info:
            OrphanMonitorConfig(
                enabled=True,
                run_on_startup=False,
                periodic_interval_sec=60,
                min_order_age_sec=30,
                batch_cancel_limit=10,
                rate_limit_per_min=20,
                unknown_field="should_fail",
            )
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_manage_config_forbid_unknown(self):
        """ManageConfig top-level has extra='forbid' (all fields typed).
        
        CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: ManageConfig now forbid."""
        manage = ManageConfig(brackets=None, emergency=None, auto=True, orphan_monitor=None)
        assert manage.auto is True
        
        # extra='forbid' at top level
        with pytest.raises(ValidationError) as exc_info:
            ManageConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()


class TestExecutionConfigTyped:
    """C: ExecutionConfig.watchdog - typed WatchdogConfig."""
    
    def test_watchdog_config_typed(self):
        """ExecutionConfig.watchdog is WatchdogConfig (not Dict[str, Any])."""
        watchdog = WatchdogConfig(ack_ttl_ms=5000, fill_ttl_ms=20000, check_interval_ms=1000, rps_limit=15)
        assert watchdog.ack_ttl_ms == 5000
        assert watchdog.fill_ttl_ms == 20000
        assert watchdog.rps_limit == 15
    
    def test_watchdog_config_forbid_unknown(self):
        """WatchdogConfig rejects unknown fields (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            WatchdogConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_execution_config_uses_typed_watchdog(self):
        """ExecutionConfig.watchdog is Optional[WatchdogConfig]."""
        execution = ExecutionConfig(**_valid_execution_kwargs())
        assert execution.watchdog is None

        base = dict(_valid_execution_kwargs())
        base.pop("watchdog", None)
        execution_with_watchdog = ExecutionConfig(
            **base,
            watchdog={"ack_ttl_ms": 8000, "fill_ttl_ms": 30000, "check_interval_ms": 1000, "rps_limit": 10},
        )
        assert isinstance(execution_with_watchdog.watchdog, WatchdogConfig)
        assert execution_with_watchdog.watchdog.ack_ttl_ms == 8000
    
    def test_execution_config_forbid_unknown(self):
        """ExecutionConfig top-level has extra='forbid' (all fields explicit).
        
        CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: ExecutionConfig now forbid."""
        # extra='forbid' - reject unknown
        with pytest.raises(ValidationError) as exc_info:
            ExecutionConfig(**_valid_execution_kwargs(), unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()


class TestE2ERegressionTypedConfigs:
    """D: Regression test - no Dict[str, Any] in runtime configs."""
    
    def test_no_dict_any_in_decision_config(self):
        """DecisionConfig: testnet/production are DecisionModeOverrideConfig (not Dict)."""
        base = dict(_valid_decision_kwargs())
        base.pop("testnet", None)
        config = DecisionConfig(**base, testnet={"signal_threshold": 0.1})
        assert isinstance(config.testnet, DecisionModeOverrideConfig)
        assert not isinstance(config.testnet, dict)  # Pydantic model, not raw dict
    
    def test_no_dict_any_in_manage_config(self):
        """ManageConfig: emergency/orphan_monitor are typed (not Dict)."""
        # TASK-ZOMBIE-FIX: Removed failsafe field
        manage = ManageConfig(brackets=None, emergency={"enabled": True, "wait_mode_bars": 1}, auto=True, orphan_monitor=None)
        assert isinstance(manage.emergency, EmergencyConfig)
        
        manage_orphan = ManageConfig(
            brackets=None,
            emergency=None,
            auto=True,
            orphan_monitor={
                "enabled": False,
                "run_on_startup": False,
                "periodic_interval_sec": 60,
                "min_order_age_sec": 30,
                "batch_cancel_limit": 10,
                "rate_limit_per_min": 20,
            },
        )
        assert isinstance(manage_orphan.orphan_monitor, OrphanMonitorConfig)
    
    def test_no_dict_any_in_execution_config(self):
        """ExecutionConfig: watchdog is WatchdogConfig (not Dict)."""
        base = dict(_valid_execution_kwargs())
        base.pop("watchdog", None)
        execution = ExecutionConfig(
            **base,
            watchdog={"ack_ttl_ms": 7000, "fill_ttl_ms": 20000, "check_interval_ms": 1000, "rps_limit": 10},
        )
        assert isinstance(execution.watchdog, WatchdogConfig)
    
    # PURGE-DIRTY-DOZEN: Removed test_no_dict_any_in_api_call_limits (ApiCallLimits deleted) - 2026-01-25
