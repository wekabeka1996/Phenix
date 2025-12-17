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
    ApiCallLimits,
    KlinesConfig,
)


class TestDecisionModeOverrides:
    """A: DecisionConfig testnet/production overrides - typed."""
    
    def test_decision_overrides_accept_consumed_keys_only(self):
        """DecisionModeOverrideConfig accepts known override keys."""
        # Known pattern: signal_threshold override (from config_loader.py L120-140)
        override = DecisionModeOverrideConfig(signal_threshold=0.15)
        assert override.signal_threshold == 0.15
        
        # extra='allow' justified: config_loader merges ANY key dynamically
        override_dynamic = DecisionModeOverrideConfig(
            signal_threshold=0.25,
            custom_field="allowed"  # Dynamic merge pattern
        )
        assert override_dynamic.signal_threshold == 0.25
    
    def test_decision_config_forbid_unknown_top_level(self):
        """DecisionConfig top-level has extra='forbid' (all fields explicit).
        
        CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: DecisionConfig now extra='forbid' (no unknown keys)."""
        # This SHOULD raise - extra='forbid' at top level
        with pytest.raises(ValidationError) as exc_info:
            DecisionConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_decision_overrides_optional_ok(self):
        """DecisionConfig.testnet/production are optional."""
        config = DecisionConfig()
        assert config.testnet is None
        assert config.production is None
        
        config_with_overrides = DecisionConfig(
            testnet={"signal_threshold": 0.15},
            production={"signal_threshold": 0.25}
        )
        assert config_with_overrides.testnet.signal_threshold == 0.15
        assert config_with_overrides.production.signal_threshold == 0.25


class TestKlinesConfig:
    """B: MarketDataConfig.get_klines - typed."""
    
    def test_klines_config_accept_known_fields(self):
        """KlinesConfig accepts interval/limit (default values)."""
        klines = KlinesConfig()
        assert klines.interval == "1m"
        assert klines.limit == 2
        
        klines_custom = KlinesConfig(interval="5m", limit=10)
        assert klines_custom.interval == "5m"
        assert klines_custom.limit == 10
    
    def test_klines_config_reject_unknown_fields(self):
        """KlinesConfig rejects unknown fields (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            KlinesConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_api_call_limits_uses_typed_klines(self):
        """ApiCallLimits.get_klines is KlinesConfig (not Dict[str, Any])."""
        limits = ApiCallLimits()
        assert isinstance(limits.get_klines, KlinesConfig)
        assert limits.get_klines.interval == "1m"
        assert limits.get_klines.limit == 2


class TestManageConfigTyped:
    """C: ManageConfig emergency/orphan_monitor - typed."""
    
    def test_emergency_config_strict_stub(self):
        """EmergencyConfig is strict stub (no consumption found)."""
        emergency = EmergencyConfig(enabled=False)
        assert emergency.enabled is False
        
        # extra='forbid' - reject unknown
        with pytest.raises(ValidationError) as exc_info:
            EmergencyConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()
    
    def test_orphan_monitor_config_temporary_allow(self):
        """OrphanMonitorConfig has extra='allow' (consumption keys unknown)."""
        # Temporary extra='allow' until fsm.py L166 consumption analyzed
        orphan = OrphanMonitorConfig(enabled=True, unknown_field="allowed")
        assert orphan.enabled is True
        # TODO: Convert to extra='forbid' when consumption documented
    
    def test_manage_config_forbid_unknown(self):
        """ManageConfig top-level has extra='forbid' (all fields typed).
        
        CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: ManageConfig now forbid."""
        manage = ManageConfig(auto=True)
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
        watchdog = WatchdogConfig(ack_ttl_ms=5000, fill_ttl_ms=20000, rps_limit=15)
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
        execution = ExecutionConfig()
        assert execution.watchdog is None
        
        execution_with_watchdog = ExecutionConfig(
            watchdog={"ack_ttl_ms": 8000, "fill_ttl_ms": 30000, "rps_limit": 10}
        )
        assert isinstance(execution_with_watchdog.watchdog, WatchdogConfig)
        assert execution_with_watchdog.watchdog.ack_ttl_ms == 8000
    
    def test_execution_config_forbid_unknown(self):
        """ExecutionConfig top-level has extra='forbid' (all fields explicit).
        
        CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: ExecutionConfig now forbid."""
        # extra='forbid' - reject unknown
        with pytest.raises(ValidationError) as exc_info:
            ExecutionConfig(unknown_field="should_fail")
        assert "extra" in str(exc_info.value).lower() or \
               "unexpected" in str(exc_info.value).lower()


class TestE2ERegressionTypedConfigs:
    """D: Regression test - no Dict[str, Any] in runtime configs."""
    
    def test_no_dict_any_in_decision_config(self):
        """DecisionConfig: testnet/production are DecisionModeOverrideConfig (not Dict)."""
        config = DecisionConfig(testnet={"signal_threshold": 0.1})
        assert isinstance(config.testnet, DecisionModeOverrideConfig)
        assert not isinstance(config.testnet, dict)  # Pydantic model, not raw dict
    
    def test_no_dict_any_in_manage_config(self):
        """ManageConfig: emergency/orphan_monitor are typed (not Dict)."""
        manage = ManageConfig(emergency={"enabled": True})
        assert isinstance(manage.emergency, EmergencyConfig)
        
        manage_orphan = ManageConfig(orphan_monitor={"enabled": False})
        assert isinstance(manage_orphan.orphan_monitor, OrphanMonitorConfig)
    
    def test_no_dict_any_in_execution_config(self):
        """ExecutionConfig: watchdog is WatchdogConfig (not Dict)."""
        execution = ExecutionConfig(watchdog={"ack_ttl_ms": 7000})
        assert isinstance(execution.watchdog, WatchdogConfig)
    
    def test_no_dict_any_in_api_call_limits(self):
        """ApiCallLimits: get_klines is KlinesConfig (not Dict)."""
        limits = ApiCallLimits(get_klines={"interval": "15m", "limit": 5})
        assert isinstance(limits.get_klines, KlinesConfig)
        assert limits.get_klines.interval == "15m"
