#!/usr/bin/env python3
"""Tests for dual-mode exposure policy resolver with config v2 support."""

import pytest
from decimal import Decimal
from unittest.mock import patch
from pathlib import Path

import yaml

from apps.reference.config_exposure_policy import (
    resolve_exposure_policy,
    ExposurePolicy,
    _get_v2_exposure_config,
)
from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2


class TestExposurePolicyV2:
    """Test dual-mode exposure policy resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        # Create a mock config with legacy structure
        mock_config = {
            "trading": {
                "execution": {
                    "exposure": {
                        "max_equity_utilization_pct": "0.25",
                        "max_portfolio_fraction": "0.30",
                        "max_directional_ratio": "3.0",
                        "max_side_utilization_pct": {"long": "0.15", "short": "0.10"},
                        "per_symbol_cap_pct": "0.10",
                        "pending_ttl_sec": 120,
                        "leverage_defaults": {"default": 25, "BTCUSDT": 15},
                    },
                    "fallback": {
                        "policy": "reduce_risk",
                        "risk_reduction_pct": "0.3",
                        "backoff_ms": [100, 200, 500],
                        "max_attempts": 5,
                        "enabled": False,
                    },
                }
            }
        }

        policy = resolve_exposure_policy(mock_config)

        assert isinstance(policy, ExposurePolicy)
        assert policy.source == "legacy"
        assert policy.caps.max_equity_utilization_ratio == Decimal("0.25")
        assert policy.caps.max_portfolio_fraction == Decimal("0.30")
        assert policy.caps.max_directional_ratio == Decimal("3.0")
        assert policy.caps.max_side_utilization_ratio["long"] == Decimal(
            "0.15")
        assert policy.caps.max_side_utilization_ratio["short"] == Decimal(
            "0.10")
        assert policy.caps.per_symbol_cap_ratio == Decimal("0.10")
        assert policy.reservations.pending_ttl_sec == 120
        assert policy.leverage_defaults.default == Decimal("25")
        assert policy.leverage_defaults.per_symbol["BTCUSDT"] == Decimal("15")
        assert policy.fallback.policy == "reduce_risk"
        assert policy.fallback.risk_reduction_pct == Decimal("0.3")
        assert policy.fallback.backoff_ms == (100, 200, 500)
        assert policy.fallback.max_attempts == 5
        assert not policy.fallback.enabled

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        # Create AuroraConfig with both legacy and v2
        mock_config = AuroraConfig(
            trading={
                "execution": {
                    "exposure": {
                        "max_equity_utilization_pct": "0.25",  # legacy value
                    }
                }
            },
            config_v2=ConfigV2(
                domains={
                    "execution": {
                        "exposure": {
                            "max_equity_utilization_pct": "0.35",  # v2 value
                            "max_portfolio_fraction": "0.40",
                            "max_directional_ratio": "4.0",
                            "leverage_defaults": {"default": 30},
                        }
                    }
                }
            )
        )

        policy = resolve_exposure_policy(mock_config)

        assert isinstance(policy, ExposurePolicy)
        assert policy.source == "config_v2"
        assert policy.caps.max_equity_utilization_ratio == Decimal(
            "0.35")  # v2 wins
        assert policy.caps.max_portfolio_fraction == Decimal("0.40")
        assert policy.caps.max_directional_ratio == Decimal("4.0")
        assert policy.leverage_defaults.default == Decimal("30")

    def test_v2_fallback_on_error(self):
        """Test that invalid v2 config falls back to legacy."""
        # Create config with invalid v2 (non-dict leverage_cfg to cause TypeError)
        mock_config = AuroraConfig(
            trading={
                "execution": {
                    "exposure": {
                        "max_equity_utilization_pct": "0.25",
                        "max_portfolio_fraction": "0.30",
                    }
                }
            },
            config_v2=ConfigV2(
                domains={
                    "execution": {
                        "exposure": "not_a_dict"  # This will cause ValueError in _build_policy_from_v2
                    }
                }
            )
        )

        policy = resolve_exposure_policy(mock_config)

        # Should fallback to legacy
        assert isinstance(policy, ExposurePolicy)
        assert policy.source == "legacy"
        assert policy.caps.max_equity_utilization_ratio == Decimal("0.25")
        assert policy.caps.max_portfolio_fraction == Decimal("0.30")

    def test_v2_helper_function(self):
        """Test the _get_v2_exposure_config helper."""
        # No config_v2
        config1 = AuroraConfig()
        assert _get_v2_exposure_config(config1) is None

        # config_v2 but no domains
        config2 = AuroraConfig(config_v2=ConfigV2())
        assert _get_v2_exposure_config(config2) is None

        # domains but no execution
        config3 = AuroraConfig(config_v2=ConfigV2(domains={"other": {}}))
        assert _get_v2_exposure_config(config3) is None

        # execution but no exposure
        config4 = AuroraConfig(config_v2=ConfigV2(domains={"execution": {}}))
        assert _get_v2_exposure_config(config4) is None

        # valid exposure config
        config5 = AuroraConfig(
            config_v2=ConfigV2(
                domains={
                    "execution": {
                        "exposure": {"max_equity_utilization_pct": "0.5"}
                    }
                }
            )
        )
        exposure_cfg = _get_v2_exposure_config(config5)
        assert exposure_cfg == {"max_equity_utilization_pct": "0.5"}

    def test_v2_ttls_override_defaults(self):
        """Ensure TTL fields come from config v2 and differ from defaults."""
        cfg = AuroraConfig(
            trading={},
            config_v2=ConfigV2(
                domains={
                    "execution": {
                        "exposure": {
                            "pending_ttl_sec": 30,
                            "post_fill_hold_ttl_sec": 9,
                            "positions_stale_ttl_sec": 4,
                        }
                    }
                }
            ),
        )

        policy = resolve_exposure_policy(cfg)

        assert policy.source == "config_v2"
        assert policy.reservations.pending_ttl_sec == 30
        assert policy.reservations.post_fill_hold_ttl_sec == 9
        assert policy.reservations.positions_stale_ttl_sec == 4

    def test_v2_fallback_block_used(self):
        cfg = AuroraConfig(
            trading={},
            config_v2=ConfigV2(
                domains={
                    "execution": {
                        "exposure": {
                            "max_equity_utilization_pct": "0.25",
                        },
                        "fallback": {
                            "policy": "reduce_risk",
                            "risk_reduction_pct": "0.3",
                            "backoff_ms": [100, 200, 400],
                            "max_attempts": 5,
                            "enabled": False,
                        },
                    }
                }
            ),
        )

        policy = resolve_exposure_policy(cfg)

        assert policy.source == "config_v2"
        assert policy.fallback.policy == "reduce_risk"
        assert policy.fallback.risk_reduction_pct == Decimal("0.3")
        assert policy.fallback.backoff_ms == (100, 200, 400)
        assert policy.fallback.max_attempts == 5
        assert policy.fallback.enabled is False

    def test_repository_execution_yaml_exposure_ttls(self):
        """Ensure TTL overrides are sourced from config/domains/execution.yaml."""
        execution_yaml = Path(__file__).resolve(
        ).parents[3] / "config" / "domains" / "execution.yaml"
        if not execution_yaml.exists():
            execution_yaml = Path(__file__).resolve(
            ).parents[2] / "config" / "domains" / "execution.yaml"
        execution_cfg = yaml.safe_load(
            execution_yaml.read_text(encoding="utf-8"))

        cfg = AuroraConfig(
            config_v2=ConfigV2(domains={"execution": execution_cfg})
        )

        policy = resolve_exposure_policy(cfg)

        assert policy.source == "config_v2"
        assert policy.reservations.pending_ttl_sec == execution_cfg["exposure"]["pending_ttl_sec"]
        assert policy.reservations.post_fill_hold_ttl_sec == execution_cfg[
            "exposure"]["post_fill_hold_ttl_sec"]
        assert policy.reservations.positions_stale_ttl_sec == execution_cfg[
            "exposure"]["positions_stale_ttl_sec"]
