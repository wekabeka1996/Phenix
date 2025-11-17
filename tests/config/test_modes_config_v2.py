#!/usr/bin/env python3
"""Tests for dual-mode trading modes config resolver with config v2 support."""

import pytest
from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.utils.trading_modes import (
    compute_effective_trading_modes,
    get_domain_mode_from_mapping,
)


class TestModesConfigV2:
    """Test dual-mode trading modes resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        # Mock legacy config
        mock_config = {
            "trading": {
                "mode": "shadow_live",
                "domain_configuration": {
                    "execution_position": {
                        "trading_mode": "live"
                    }
                }
            }
        }

        cfg = mock_config
        modes = compute_effective_trading_modes(cfg)

        assert modes.profile == "shadow_live"
        assert modes.for_domain("execution_position") == "live"
        # from profile default
        assert modes.for_domain("risk_management") == "testnet"

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "mode": "full_testnet",
                "domain_configuration": {
                    "execution_position": {
                        "trading_mode": "live"
                    }
                }
            }
        }

        v2_data = {
            "modes": {
                "profiles": {
                    "full_testnet": {
                        "trading_mode": "full_live",
                        "domains": {
                            "execution_position": "testnet",  # v2 value
                            "risk_management": "live"
                        }
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        modes = compute_effective_trading_modes(cfg)

        assert modes.profile == "full_live"  # v2 value
        assert modes.for_domain("execution_position") == "testnet"  # v2 value
        assert modes.for_domain("risk_management") == "live"  # v2 value

    def test_v2_fallback_on_missing_modes(self):
        """Test fallback to legacy when modes not in v2."""
        mock_config = {
            "trading": {
                "mode": "full_testnet",
                "domain_configuration": {
                    "execution_position": {
                        "trading_mode": "live"
                    }
                }
            }
        }

        v2_data = {
            "domains": {  # Different section
                "execution": {}
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        modes = compute_effective_trading_modes(cfg)

        assert modes.profile == "full_testnet"  # legacy value
        assert modes.for_domain("execution_position") == "live"  # legacy value

    def test_v2_fallback_on_invalid_config(self):
        """Test fallback when v2 config is invalid."""
        mock_config = {
            "trading": {
                "mode": "full_testnet",
            }
        }

        v2_data = {
            "modes": {
                "profiles": {}  # Empty profiles
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        modes = compute_effective_trading_modes(cfg)

        assert modes.profile == "full_testnet"  # legacy fallback

    def test_get_domain_mode_from_mapping_v2(self):
        """Test get_domain_mode_from_mapping uses v2."""
        mock_config = {
            "trading": {
                "mode": "full_testnet",
            }
        }

        v2_data = {
            "modes": {
                "profiles": {
                    "full_testnet": {
                        "trading_mode": "full_live",
                        "domains": {
                            "execution_position": "live"
                        }
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))

        mode = get_domain_mode_from_mapping(cfg, "execution_position")
        assert mode == "live"  # v2 value

        mode_default = get_domain_mode_from_mapping(cfg, "unknown_domain")
        assert mode_default == "live"  # profile default
