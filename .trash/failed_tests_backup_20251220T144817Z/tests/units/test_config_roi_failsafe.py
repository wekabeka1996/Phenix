import pytest
from apps.reference.config_models import AuroraConfig, TradingConfig, DecisionConfig, ManageConfig, ROIExitConfig, FailsafeConfig

class TestConfigROIFailsafe:
    def test_roi_exit_config_defaults(self):
        config = ROIExitConfig()
        assert config.enabled is True
        assert config.target_roi_pct == 50.0

    def test_failsafe_config_defaults(self):
        config = FailsafeConfig()
        assert config.max_hold_sec == 86400

    def test_integration_in_aurora_config(self):
        data = {
            "trading_mode": "testnet",
            "trading": {
                "decision": {
                    "roi_exit": {
                        "enabled": False,
                        "target_roi_pct": 25.0
                    }
                },
                "execution": {
                    "manage": {
                        "failsafe": {
                            "max_hold_sec": 3600
                        }
                    }
                }
            }
        }
        config = AuroraConfig(**data)
        
        # Check ROI Exit
        assert config.trading.decision.roi_exit is not None
        assert config.trading.decision.roi_exit.enabled is False
        assert config.trading.decision.roi_exit.target_roi_pct == 25.0
        
        # Check Failsafe
        assert config.trading.execution.manage.failsafe is not None
        assert config.trading.execution.manage.failsafe.max_hold_sec == 3600

    def test_loading_from_yaml_structure(self):
        # Simulate the structure loaded from YAML
        yaml_data = {
            "trading_mode": "testnet",
            "trading": {
                "decision": {
                    "roi_exit": {
                        "enabled": True,
                        "target_roi_pct": 60.0
                    }
                },
                "execution": {
                    "manage": {
                        "failsafe": {
                            "max_hold_sec": 7200
                        }
                    }
                }
            }
        }
        config = AuroraConfig(**yaml_data)
        assert config.trading.decision.roi_exit.target_roi_pct == 60.0
        assert config.trading.execution.manage.failsafe.max_hold_sec == 7200
