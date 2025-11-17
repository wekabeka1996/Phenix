"""
Tests for dual-mode regime detector config resolver.
"""

import pytest
from unittest.mock import patch

from apps.reference.config_models import AuroraConfig, ConfigV2
from apps.reference.config_regimes import resolve_regime_detector_config


class TestRegimeConfigV2:
    """Test regime detector config v2 resolver."""

    def test_legacy_only(self):
        """Test legacy-only config (no v2)."""
        cfg = AuroraConfig()
        # No config_v2

        result = resolve_regime_detector_config(cfg)

        assert result.source == "legacy"
        assert result.window_minutes == 2  # rv_window // 60
        assert result.min_regime_duration_min == 15
        assert result.debounce_changes is True
        assert "NORMAL" in result.regimes
        assert "HIGH_VOLATILITY" in result.regimes
        assert "CRISIS" in result.regimes
        assert result.hotreload_allowed == [
            "NORMAL", "HIGH_VOLATILITY", "CRISIS"]

    def test_v2_priority(self):
        """Test v2 config takes priority."""
        cfg = AuroraConfig()
        cfg.config_v2 = ConfigV2()
        cfg.config_v2.domains = {
            "regimes": {
                "detector": {
                    "window_minutes": 5,
                    "min_regime_duration_min": 10,
                    "debounce_changes": False
                },
                "regimes": {
                    "CALM": {"vol_std_bps_min": 0, "vol_std_bps_max": 50},
                    "VOLATILE": {"vol_std_bps_min": 50, "vol_std_bps_max": 150}
                },
                "hotreload": {
                    "allowed": ["CALM", "VOLATILE"]
                }
            }
        }

        result = resolve_regime_detector_config(cfg)

        assert result.source == "config_v2"
        assert result.window_minutes == 5
        assert result.min_regime_duration_min == 10
        assert result.debounce_changes is False
        assert result.regimes == {
            "CALM": {"vol_std_bps_min": 0, "vol_std_bps_max": 50},
            "VOLATILE": {"vol_std_bps_min": 50, "vol_std_bps_max": 150}
        }
        assert result.hotreload_allowed == ["CALM", "VOLATILE"]

    def test_invalid_v2_fallback(self):
        """Test invalid v2 config falls back to legacy."""
        cfg = AuroraConfig()
        cfg.config_v2 = ConfigV2()
        cfg.config_v2.domains = {
            "regimes": {
                "detector": {
                    "window_minutes": -1  # Invalid
                }
            }
        }

        result = resolve_regime_detector_config(cfg)

        assert result.source == "legacy"  # Fallback

    def test_v2_validation_window_minutes(self):
        """Test v2 validation for window_minutes."""
        cfg = AuroraConfig()
        cfg.config_v2 = ConfigV2()
        cfg.config_v2.domains = {
            "regimes": {
                "detector": {"window_minutes": 0}  # Invalid
            }
        }

        result = resolve_regime_detector_config(cfg)
        assert result.source == "legacy"  # Fallback on invalid

    def test_v2_validation_min_duration(self):
        """Test v2 validation for min_regime_duration_min."""
        cfg = AuroraConfig()
        cfg.config_v2 = ConfigV2()
        cfg.config_v2.domains = {
            "regimes": {
                "detector": {"min_regime_duration_min": -1}  # Invalid
            }
        }

        result = resolve_regime_detector_config(cfg)
        assert result.source == "legacy"  # Fallback on invalid

    def test_v2_validation_regime_bounds(self):
        """Test v2 validation for regime vol_std_bps min > max."""
        cfg = AuroraConfig()
        cfg.config_v2 = ConfigV2()
        cfg.config_v2.domains = {
            "regimes": {
                "regimes": {
                    # Invalid
                    "TEST": {"vol_std_bps_min": 100, "vol_std_bps_max": 50}
                }
            }
        }

        result = resolve_regime_detector_config(cfg)
        assert result.source == "legacy"  # Fallback on invalid

    def test_v2_validation_hotreload_allowed(self):
        """Test v2 validation for hotreload allowed not in regimes."""
        cfg = AuroraConfig()
        cfg.config_v2 = ConfigV2()
        cfg.config_v2.domains = {
            "regimes": {
                "regimes": {
                    "NORMAL": {"vol_std_bps_min": 0, "vol_std_bps_max": 80}
                },
                "hotreload": {
                    "allowed": ["NORMAL", "UNKNOWN"]  # UNKNOWN not in regimes
                }
            }
        }

        result = resolve_regime_detector_config(cfg)
        assert result.source == "legacy"  # Fallback on invalid
