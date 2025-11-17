#!/usr/bin/env python3
"""Tests for dual-mode decision config resolver with config v2 support."""

import pytest
from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.config_decision import (
    resolve_decision_policy,
    _build_decision_from_v2,
    _build_decision_from_legacy,
)


class TestDecisionConfigV2:
    """Test dual-mode decision config resolution."""

    def test_legacy_only_behavior(self):
        """Test that legacy config works without v2."""
        # Mock legacy config as dict (not AuroraConfig to avoid Pydantic)
        mock_config = {
            "trading": {
                "decision": {
                    "signal_threshold": 0.10,
                    "neutral_threshold": 0.18,
                    "qos": {
                        "max_intents_per_minute_per_symbol": 60,
                        "symbol_intent_cooldown_sec": 1,
                        "exposure_block_cooldown_sec": 30,
                    }
                }
            }
        }

        policy = resolve_decision_policy(mock_config)

        assert policy.source == "legacy"
        assert policy.signal_threshold == 0.10
        assert policy.neutral_threshold == 0.18
        assert policy.max_intents_per_minute_per_symbol == 60
        assert policy.symbol_intent_cooldown_sec == 1
        assert policy.exposure_block_cooldown_sec == 30

    def test_v2_config_priority(self):
        """Test that v2 config takes priority over legacy."""
        mock_config = {
            "trading": {
                "decision": {
                    "signal_threshold": 0.05,  # legacy value
                    "qos": {
                        "max_intents_per_minute_per_symbol": 30,  # legacy value
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "decision": {
                    "thresholds": {
                        "signal_threshold": 0.10,
                        "neutral_threshold": 0.18,
                    },
                    "qos": {
                        "max_intents_per_minute_per_symbol": 60,
                        "symbol_intent_cooldown_sec": 1,
                        "exposure_block_cooldown_sec": 30,
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        policy = resolve_decision_policy(cfg)

        assert policy.source == "config_v2"
        assert policy.signal_threshold == 0.10  # v2 value
        assert policy.neutral_threshold == 0.18  # v2 value
        assert policy.max_intents_per_minute_per_symbol == 60  # v2 value
        assert policy.symbol_intent_cooldown_sec == 1
        assert policy.exposure_block_cooldown_sec == 30

    def test_v2_fallback_on_missing_decision_domain(self):
        """Test fallback to legacy when decision domain not in v2."""
        mock_config = {
            "trading": {
                "decision": {
                    "signal_threshold": 0.15,
                    "qos": {
                        "max_intents_per_minute_per_symbol": 50,
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
        policy = resolve_decision_policy(cfg)

        assert policy.source == "legacy"
        assert policy.signal_threshold == 0.15  # legacy value
        assert policy.max_intents_per_minute_per_symbol == 50  # legacy value

    def test_v2_fallback_on_invalid_config(self):
        """Test fallback when v2 config is invalid."""
        mock_config = {
            "trading": {
                "decision": {
                    "signal_threshold": 0.10,
                    "qos": {
                        "max_intents_per_minute_per_symbol": 60,
                    }
                }
            }
        }

        v2_data = {
            "domains": {
                "decision": {
                    "thresholds": {
                        "signal_threshold": -0.1,  # Invalid negative value
                    }
                }
            }
        }

        cfg = AuroraConfig(
            trading=mock_config["trading"], config_v2=ConfigV2(**v2_data))
        policy = resolve_decision_policy(cfg)

        # Should fallback to legacy
        assert policy.source == "legacy"
        assert policy.signal_threshold == 0.10  # legacy value
