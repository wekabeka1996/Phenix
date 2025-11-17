#!/usr/bin/env python3
"""Tests for dual-mode sizing config resolver with config v2 support."""

import pytest
from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.config_sizing import (
    resolve_sizing_policy,
    _build_sizing_from_v2,
    _build_sizing_from_legacy,
)


class TestSizingConfigV2:
    """Test dual-mode sizing config resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        # Mock legacy config as dict (not AuroraConfig to avoid Pydantic)
        mock_config = {
            "trading": {
                "decision": {
                    "position_sizing": {
                        "min_position_size_usd": 10.0,
                        "liquidity_based_cap_usd": 10000.0,
                        "risk_fraction_q": 0.01,
                        "liquidity_kappa": 1.0,
                        "liquidity_kappa_mode": "dynamic",
                    },
                    "kelly": {
                        "base_probability": 0.55,
                        "kelly_cap": 0.25,
                        "kelly_alpha": 0.8,
                        "payoff_ratio_r": 2.0,
                    }
                }
            }
        }

        policy = resolve_sizing_policy(mock_config, "BTCUSDT")

        assert policy.source == "legacy"
        assert policy.mode == "fixed_risk_pct"
        assert policy.max_risk_pct == 1.0
        assert policy.max_risk_usd == 50.0
        assert policy.min_notional_usd == 10.0
        assert policy.max_notional_usd == 10000.0
        assert policy.liquidity_kappa == 1.0
        assert policy.liquidity_kappa_mode == "dynamic"
        assert policy.kelly is not None

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "decision": {
                    "position_sizing": {
                        "min_position_size_usd": 5.0,  # legacy value
                        "liquidity_based_cap_usd": 5000.0,  # legacy value
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "sizing": {
                    "defaults": {
                        "mode": "fixed_risk_pct",
                        "max_risk_pct": 2.0,
                        "max_risk_usd": 100.0,
                        "min_notional_usd": 20.0,
                        "max_notional_usd": 20000.0,
                        "liquidity_kappa": 1.5,
                        "liquidity_kappa_mode": "static",
                        "kelly": {
                            "base_probability": 0.6,
                            "kelly_cap": 0.3,
                        }
                    },
                    "symbols": {},
                    "regimes": {}
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        policy = resolve_sizing_policy(cfg, "BTCUSDT")

        assert policy.source == "config_v2"
        assert policy.mode == "fixed_risk_pct"
        assert policy.max_risk_pct == 2.0  # v2 value
        assert policy.max_risk_usd == 100.0  # v2 value
        assert policy.min_notional_usd == 20.0  # v2 value
        assert policy.max_notional_usd == 20000.0  # v2 value
        assert policy.liquidity_kappa == 1.5
        assert policy.liquidity_kappa_mode == "static"
        assert policy.kelly["base_probability"] == 0.6

    def test_v2_fallback_on_missing_sizing_domain(self):
        """Test fallback to legacy when sizing domain not in v2."""
        mock_config = {
            "trading": {
                "decision": {
                    "position_sizing": {
                        "min_position_size_usd": 15.0,
                        "liquidity_based_cap_usd": 15000.0,
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "execution": {  # Different domain
                    "some": "config"
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        policy = resolve_sizing_policy(cfg, "BTCUSDT")

        assert policy.source == "legacy"
        assert policy.min_notional_usd == 15.0  # legacy value
        assert policy.max_notional_usd == 15000.0  # legacy value

    def test_v2_fallback_on_invalid_config(self):
        """Test fallback when v2 config is invalid."""
        mock_config = {
            "trading": {
                "decision": {
                    "position_sizing": {
                        "min_position_size_usd": 10.0,
                        "liquidity_based_cap_usd": 10000.0,
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "sizing": {
                    "defaults": {
                        "max_risk_pct": -1.0,  # Invalid negative value
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        policy = resolve_sizing_policy(cfg, "BTCUSDT")

        # Should fallback to legacy
        assert policy.source == "legacy"
        # legacy fallback (10% since no risk_fraction_q)
        assert policy.max_risk_pct == 10.0
