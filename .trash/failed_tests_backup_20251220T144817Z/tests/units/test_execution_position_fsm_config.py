import pytest
from unittest.mock import MagicMock
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.config_models import AuroraConfig

class TestExecPosFSMConfig:
    def test_init_with_dict_config(self):
        """Test initialization with a dictionary config."""
        config = {
            "trading": {
                "execution": {
                    "watchdog": {
                        "ack_ttl_ms": 1000,
                        "fill_ttl_ms": 5000,
                        "check_interval_ms": 100
                    }
                }
            }
        }
        fsm = ExecPosFSM(config, fsm=MagicMock())
        
        # It should be converted to AuroraConfig
        assert isinstance(fsm.config, AuroraConfig)
        
        # Check if watchdog config was correctly resolved
        assert fsm.watchdog.ack_ttl_ms == 1000
        assert fsm.watchdog.fill_ttl_ms == 5000

    def test_init_with_aurora_config(self):
        """Test initialization with an AuroraConfig object."""
        config_dict = {
            "trading": {
                "execution": {
                    "watchdog": {
                        "ack_ttl_ms": 2000,
                        "fill_ttl_ms": 6000
                    }
                }
            }
        }
        aurora_config = AuroraConfig(**config_dict)
        
        fsm = ExecPosFSM(aurora_config, fsm=MagicMock())
        
        assert fsm.config is aurora_config
        assert fsm.watchdog.ack_ttl_ms == 2000
        assert fsm.watchdog.fill_ttl_ms == 6000

    def test_get_config_value_mixed(self):
        """Test _get_config_value with mixed dict/object structure."""
        config = {
            "trading": {
                "execution": {
                    "order_guardian": {
                        "poll_interval_ms": 999
                    }
                }
            }
        }
        fsm = ExecPosFSM(config, fsm=MagicMock())
        
        # Test deep access
        val = fsm._get_config_value(["trading", "execution", "order_guardian", "poll_interval_ms"])
        assert val == 999
        
        # Test missing key
        val = fsm._get_config_value(["trading", "execution", "non_existent"], default="default")
        assert val == "default"

    def test_orphan_config_extraction(self):
        """Test that orphan_monitor config is correctly extracted."""
        config = {
            "trading": {
                "execution": {
                    "manage": {
                        "orphan_monitor": {
                            "enabled": False,
                            "periodic_interval_sec": 123
                        }
                    }
                }
            }
        }
        fsm = ExecPosFSM(config, fsm=MagicMock())
        
        assert fsm._orphan_cfg["enabled"] is False
        assert fsm._orphan_cfg["periodic_interval_sec"] == 123

    def test_init_shadow_mode_config(self):
        """Test initialization in shadow mode with AuroraConfig."""
        config_dict = {
            "trading": {
                "execution": {
                    "order_guardian": {
                        "poll_interval_ms": 777
                    }
                }
            }
        }
        aurora_config = AuroraConfig(**config_dict)
        
        # Initialize in shadow mode
        fsm = ExecPosFSM(aurora_config, fsm=MagicMock(), shadow_mode=True)
        
        # Check if OrderGuardian was initialized with correct poll interval
        # Note: In shadow mode, OrderGuardian is initialized with adapter=None
        assert fsm.order_guardian is not None
        # Accessing private attribute for verification, assuming it's stored there or passed to init
        # Based on OrderGuardian init: self.poll_interval_ms = poll_interval_ms
        # The domain wrapper stores the implementation in _impl
        assert fsm.order_guardian._impl.poll_interval_ms == 777
