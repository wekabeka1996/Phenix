"""
Tests for FAIL-CLOSED config loading policy in DecisionMaking domain.

SSOT: All configuration values must come from YAML via Pydantic validation.
No hardcoded defaults in runtime code. If config is missing, fail immediately.

Tests cover:
1. risk_skew config (max_skew_sec, max_defer_count, defer_cooldown_sec, defer_window_sec, until_refresh_retry_sec)
2. risk_gate config (threshold_pct_testnet, threshold_pct_production, min_intents_for_check)
3. side_bias config (penalty_factor, window_sec, target_ratio)
4. positions_stale_ttl_sec
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from pathlib import Path
import logging
import yaml


def _attach_dm_config_resolver(dm, cfg) -> None:
    """Attach DMConfigResolver for tests that bypass DecisionMaking.__init__."""
    from apps.reference.domains.decision_making.core.config_resolver import DMConfigResolver

    dm.config = cfg
    dm.strategies_registry = None
    dm._arb_signal_buffer = {}
    dm._arb_window_winner = {}
    dm.flip_global_enabled = True
    dm.logger = logging.getLogger("tests.decision_making_fail_closed")
    dm._cfg = DMConfigResolver(
        config=cfg,
        strategies_registry=None,
        arb_signal_buffer=dm._arb_signal_buffer,
        arb_window_winner=dm._arb_window_winner,
        flip_global_enabled=dm.flip_global_enabled,
        logger=dm.logger,
    )


class TestFailClosedRiskSkew:
    """Test risk_skew config is required (no hardcoded defaults)."""

    def test_get_risk_skew_config_fails_without_config(self):
        """_get_risk_skew_config should fail if risk_skew key is missing."""
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        # Create nested mock without spec to allow attribute assignment
        cfg = MagicMock()
        cfg.domains.decision_making.risk_skew.max_skew_sec = None  # Missing!
        
        with patch.object(DecisionMaking, '__init__', lambda x, y, z: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.config = cfg
            
            with pytest.raises(ValueError, match="risk_skew.*max_skew_sec.*required"):
                dm._get_risk_skew_config("max_skew_sec")

    def test_get_risk_skew_config_returns_value_when_present(self):
        """_get_risk_skew_config should return value from config."""
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        
        cfg = MagicMock()
        cfg.domains.decision_making.risk_skew.max_skew_sec = 10
        cfg.domains.decision_making.risk_skew.defer_window_sec = 120
        
        with patch.object(DecisionMaking, '__init__', lambda x, y, z: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.config = cfg
            
            assert dm._get_risk_skew_config("max_skew_sec") == 10
            assert dm._get_risk_skew_config("defer_window_sec") == 120


class TestFailClosedSideBias:
    """Test side_bias config is required (no hardcoded defaults)."""

    def test_get_side_bias_params_fails_without_config(self):
        """_get_side_bias_params should fail if side_bias is missing."""
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        from apps.reference.domains.decision_making.core.config_resolver import DMConfigResolver

        cfg = MagicMock()
        cfg.strategies.aurora.decision.side_bias_penalty_factor = None  # Missing!
        cfg.strategies.aurora.decision.side_bias_window_sec = 60
        cfg.strategies.aurora.decision.side_bias_target_ratio = 0.6
        cfg.strategies.aurora.assets = {}

        with patch.object(DecisionMaking, '__init__', lambda x, y, z: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.config = cfg
            dm.strategies_registry = None
            dm._arb_signal_buffer = {}
            dm._arb_window_winner = {}
            dm.flip_global_enabled = True
            dm.logger = logging.getLogger("tests.decision_making_fail_closed")
            dm._cfg = DMConfigResolver(
                config=cfg,
                strategies_registry=None,
                arb_signal_buffer=dm._arb_signal_buffer,
                arb_window_winner=dm._arb_window_winner,
                flip_global_enabled=dm.flip_global_enabled,
                logger=dm.logger,
            )

            with pytest.raises(ValueError, match="side_bias_penalty_factor.*required"):
                dm._get_side_bias_params("BTCUSDT")

    def test_get_side_bias_params_returns_values_when_present(self):
        """_get_side_bias_params should return values from config."""
        from apps.reference.domains.decision_making.core.facade import DecisionMaking
        from apps.reference.domains.decision_making.core.config_resolver import DMConfigResolver

        cfg = MagicMock()
        cfg.strategies.aurora.decision.side_bias_penalty_factor = 0.5
        cfg.strategies.aurora.decision.side_bias_window_sec = 60
        cfg.strategies.aurora.decision.side_bias_target_ratio = 0.6
        cfg.strategies.aurora.decision.side_bias_min_intents = 18
        cfg.strategies.aurora.assets = {}

        with patch.object(DecisionMaking, '__init__', lambda x, y, z: None):
            dm = DecisionMaking.__new__(DecisionMaking)
            dm.config = cfg
            dm.strategies_registry = None
            dm._arb_signal_buffer = {}
            dm._arb_window_winner = {}
            dm.flip_global_enabled = True
            dm.logger = logging.getLogger("tests.decision_making_fail_closed")
            dm._cfg = DMConfigResolver(
                config=cfg,
                strategies_registry=None,
                arb_signal_buffer=dm._arb_signal_buffer,
                arb_window_winner=dm._arb_window_winner,
                flip_global_enabled=dm.flip_global_enabled,
                logger=dm.logger,
            )

            penalty, window, target, min_intents = dm._get_side_bias_params("BTCUSDT")
            assert penalty == 0.5
            assert window == 60
            assert target == 0.6
            assert min_intents == 18


class TestFailClosedProductionConfig:
    """Test that production config loads successfully with all values."""

    def test_production_config_has_risk_skew_values(self):
        """Production config must have all risk_skew values."""
        from apps.reference.config_loader import get_config
        
        cfg = get_config()
        risk_skew = cfg.domains.decision_making.risk_skew
        
        assert risk_skew.max_skew_sec == 5
        assert risk_skew.max_defer_count == 3
        assert risk_skew.defer_cooldown_sec == 2
        assert risk_skew.defer_window_sec == 60
        assert risk_skew.until_refresh_retry_sec == 30

    def test_production_config_has_risk_gate_values(self):
        """Production config must have all risk_gate values."""
        from apps.reference.config_loader import get_config
        
        cfg = get_config()
        risk_gate = cfg.domains.decision_making.risk_gate
        
        assert risk_gate.threshold_pct_testnet == 20.0
        assert risk_gate.threshold_pct_production == 50.0
        assert risk_gate.min_intents_for_check == 10

    def test_production_config_has_side_bias_values(self):
        """Production config must have side_bias values."""
        from apps.reference.config_loader import get_config
        
        cfg = get_config()
        dm = cfg.strategies.aurora.decision

        aurora_path = (
            Path(__file__).resolve().parents[2]
            / "config"
            / "aurora"
            / "strategies"
            / "aurora.yaml"
        )
        raw = yaml.safe_load(aurora_path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        decision = raw.get("aurora", {}).get("decision", {})
        assert isinstance(decision, dict)

        assert dm.side_bias_penalty_factor == pytest.approx(float(decision["side_bias_penalty_factor"]))
        assert dm.side_bias_window_sec == int(decision["side_bias_window_sec"])
        assert dm.side_bias_target_ratio == pytest.approx(float(decision["side_bias_target_ratio"]))
        assert dm.side_bias_min_intents == int(decision["side_bias_min_intents"])

    def test_production_config_has_positions_stale_ttl(self):
        """Production config must have positions_stale_ttl_sec."""
        from apps.reference.config_loader import get_config
        
        cfg = get_config()
        
        assert cfg.domains.position_tracking.positions_stale_ttl_sec == 15


class TestNoHardcodedDefaults:
    """Verify no hardcoded defaults exist in production code."""

    def test_no_fallback_patterns_in_decision_making(self):
        """decision_making.py should not have fallback default patterns."""
        from pathlib import Path
        
        dm_path = Path(__file__).parent.parent.parent / "apps/reference/domains/decision_making/decision_making.py"
        content = dm_path.read_text()
        
        # Should NOT find old fallback patterns
        assert "default_penalty = 0.50" not in content
        assert "default_window = 60" not in content
        assert "default_target = 0.60" not in content
        assert "else 5.0" not in content  # stale_ttl fallback
        assert "20.0 if mode == \"testnet\" else 50.0" not in content  # threshold fallback

    def test_get_risk_skew_config_no_default_param(self):
        """_get_risk_skew_config should not accept default parameter."""
        from pathlib import Path
        
        dm_path = Path(__file__).parent.parent.parent / "apps/reference/domains/decision_making/decision_making.py"
        content = dm_path.read_text()
        
        # Method signature should NOT have default parameter
        assert "def _get_risk_skew_config(self, key: str, default:" not in content
        # Should have fail-closed signature
        assert "def _get_risk_skew_config(self, key: str) -> Any:" in content
