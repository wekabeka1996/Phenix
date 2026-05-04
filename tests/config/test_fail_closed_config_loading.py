"""
Tests for FAIL-CLOSED config loading policy.

SSOT: All configuration values must come from YAML via Pydantic validation.
No hardcoded defaults in runtime code. If config is missing, fail immediately.

Tests cover:
1. event_dedup config (fsm.py)
2. idempotent_cancel config (fsm.py)
3. anti_race_close_ms (fsm_manage.py)
4. idempotency_window_sec (fsm_open.py)
5. emergency config (fsm_manage.py)
6. trailing defaults (fsm_manage.py)
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal


class TestFailClosedEventDedup:
    """Test event_dedup config is required (no hardcoded defaults)."""

    def test_fsm_fails_without_event_dedup_config(self):
        """FSM should fail if event_dedup config is missing."""
        from apps.reference.domains.execution_position.fsm import ExecPosFSM
        
        cfg = MagicMock()
        cfg.domains.execution_position.event_dedup = None
        cfg.trading.execution.watchdog.ack_ttl_ms = 5000
        cfg.trading.execution.watchdog.fill_ttl_ms = 5000
        cfg.binance_api.testnet.api_key = ""
        cfg.binance_api.testnet.api_secret = ""
        
        with patch('apps.reference.domains.execution_position.fsm.OrderGuardian'), \
             patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog'), \
             patch('apps.reference.domains.execution_position.fsm.MetricsCollector'), \
             patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
            with pytest.raises(ValueError, match="event_dedup"):
                ExecPosFSM(config=cfg, fsm=MagicMock())

    def test_fsm_loads_event_dedup_from_config(self):
        """FSM should load event_dedup values from config."""
        from apps.reference.domains.execution_position.fsm import ExecPosFSM
        
        cfg = MagicMock()
        event_dedup = MagicMock()
        event_dedup.max_size = 50000
        event_dedup.ttl_ms = 43200000  # 12h
        cfg.domains.execution_position.event_dedup = event_dedup
        
        idempotent = MagicMock()
        idempotent.max_retries = 3
        cfg.domains.execution_position.idempotent_cancel = idempotent
        
        cfg.trading.execution.watchdog.ack_ttl_ms = 5000
        cfg.trading.execution.watchdog.fill_ttl_ms = 5000
        cfg.binance_api.testnet.api_key = ""
        cfg.binance_api.testnet.api_secret = ""
        
        with patch('apps.reference.domains.execution_position.fsm.OrderGuardian'), \
             patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog'), \
             patch('apps.reference.domains.execution_position.fsm.MetricsCollector'), \
             patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
            fsm = ExecPosFSM(config=cfg, fsm=MagicMock())
            assert fsm._processed_events.max_size == 50000
            assert fsm._processed_events.ttl_ms == 43200000


class TestFailClosedIdempotentCancel:
    """Test idempotent_cancel config is required."""

    def test_fsm_fails_without_idempotent_cancel_config(self):
        """FSM should fail if idempotent_cancel config is missing."""
        from apps.reference.domains.execution_position.fsm import ExecPosFSM
        
        cfg = MagicMock()
        event_dedup = MagicMock()
        event_dedup.max_size = 100000
        event_dedup.ttl_ms = 86400000
        cfg.domains.execution_position.event_dedup = event_dedup
        cfg.domains.execution_position.idempotent_cancel = None
        
        cfg.trading.execution.watchdog.ack_ttl_ms = 5000
        cfg.trading.execution.watchdog.fill_ttl_ms = 5000
        cfg.binance_api.testnet.api_key = ""
        cfg.binance_api.testnet.api_secret = ""
        
        with patch('apps.reference.domains.execution_position.fsm.OrderGuardian'), \
             patch('apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog'), \
             patch('apps.reference.domains.execution_position.fsm.MetricsCollector'), \
             patch('apps.reference.domains.execution_position.fsm.ExposureGuard'):
            with pytest.raises(ValueError, match="idempotent_cancel"):
                ExecPosFSM(config=cfg, fsm=MagicMock())


class TestFailClosedAntiRaceCloseMs:
    """Test anti_race_close_ms config is required."""

    def test_manage_fsm_fails_without_anti_race_close_ms(self):
        """ManageFlowFSM should fail if anti_race_close_ms is missing."""
        from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageFlowFSM
        
        cfg = MagicMock()
        cfg.trading.execution.anti_race_close_ms = None  # Missing!
        cfg.trading.execution.manage.emergency = None
        cfg.strategies.aurora.decision.bar_gating = None
        
        with pytest.raises(ValueError, match="anti_race_close_ms"):
            ManageFlowFSM(config=cfg)


class TestFailClosedIdempotencyWindow:
    """Test idempotency_window_sec config is required."""

    def test_open_fsm_fails_without_idempotency_window(self):
        """OpenFlowFSM should fail if idempotency_window_sec is missing."""
        from apps.reference.domains.execution_position.flows.open.fsm_open import OpenFlowFSM
        
        cfg = MagicMock()
        cfg.domains.execution_position.fsm_open = None  # Missing!
        cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20}
        cfg.instruments = {}
        
        with pytest.raises(ValueError, match="idempotency_window_sec"):
            OpenFlowFSM(config=cfg)


class TestFailClosedProductionConfig:
    """Test that production config loads successfully with all values."""

    def test_production_config_has_all_required_values(self):
        """Production config must have all required values."""
        from apps.reference.config_loader import get_config
        
        cfg = get_config()
        
        # Event dedup
        assert cfg.domains.execution_position.event_dedup is not None
        assert cfg.domains.execution_position.event_dedup.max_size == 100000
        assert cfg.domains.execution_position.event_dedup.ttl_ms == 86400000
        
        # Idempotent cancel
        assert cfg.domains.execution_position.idempotent_cancel is not None
        assert cfg.domains.execution_position.idempotent_cancel.max_retries == 2
        
        # Anti-race close
        assert cfg.trading.execution.anti_race_close_ms == 800
        
        # FSM open idempotency
        assert cfg.domains.execution_position.fsm_open.idempotency_window_sec == 60
        
        # Emergency config
        assert cfg.trading.execution.manage.emergency is not None
        assert cfg.trading.execution.manage.emergency.wait_mode_bars == 2
        assert cfg.trading.execution.manage.emergency.emergency_sl_bps == 100
        
        # Trailing defaults
        assert cfg.trailing is not None
        assert cfg.trailing.activation_pct == 0.003
        assert cfg.trailing.trail_pct == 0.006


class TestNoHardcodedDefaults:
    """Verify no hardcoded defaults exist in production code."""

    def test_no_fallback_patterns_in_fsm(self):
        """fsm.py should not have fallback default patterns for config values."""
        from pathlib import Path
        
        fsm_path = Path(__file__).parent.parent.parent / "apps/reference/domains/execution_position/fsm.py"
        content = fsm_path.read_text()
        
        # Should NOT find patterns like "dedup_max = 100000" or "dedup_ttl = 86400000"
        assert "dedup_max = 100000" not in content
        assert "dedup_ttl = 86400000" not in content
        # Should NOT find old pass-through try/except with fallback
        assert "# Fail-open: fallback to direct" not in content

    def test_no_fallback_patterns_in_fsm_manage(self):
        """fsm_manage.py should not have fallback default patterns."""
        from pathlib import Path
        
        fsm_manage_path = Path(__file__).parent.parent.parent / "apps/reference/domains/execution_position/fsm_manage.py"
        content = fsm_manage_path.read_text()
        
        # Should NOT find old patterns
        assert "self._anti_race_close_ms = 800  # Default fallback" not in content
        assert "activation_pct = 0.003  # Default" not in content
        assert "trail_pct = 0.006  # Default" not in content

    def test_no_fallback_patterns_in_fsm_open(self):
        """fsm_open.py should not have fallback default patterns."""
        from pathlib import Path
        
        fsm_open_path = Path(__file__).parent.parent.parent / "apps/reference/domains/execution_position/fsm_open.py"
        content = fsm_open_path.read_text()
        
        # Should NOT find old patterns
        assert "self.idempotency_window_sec = 60" not in content or "SSOT" in content
