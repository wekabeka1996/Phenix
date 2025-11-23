# -*- coding: utf-8 -*-
"""
Tests for hybrid adapter behavior in manage_config.py (V2 + legacy dual-path).

Validates that the resolver correctly prioritizes V2 config when available and
falls back to legacy dict navigation when V2 is absent or fails parsing.

**Test Coverage:**
1. V2 path works: config with config_v2.domains['execution']['manage'] uses _build_manage_from_v2
2. Legacy path works: config without config_v2 uses _build_manage_from_legacy
3. Hybrid priority: config with both paths prefers V2 over legacy
4. V2 fallback on exception: V2 parsing error triggers legacy fallback (except ConfigError)

Related: EP-CONFIG-MANAGE-HYBRID-S5 (hybrid adapter documentation task)
"""

from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_position.manage_config import (
    ExecutionManageConfig,
    clear_manage_config_cache,
    resolve_execution_manage_config,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear resolver cache before each test to ensure isolation."""
    clear_manage_config_cache()
    yield
    clear_manage_config_cache()


def _build_v2_manage_dict() -> Dict[str, Any]:
    """Build minimal V2 manage config dict for testing."""
    return {
        "auto": True,
        "mode": "legacy",
        "orphan_monitor": {"enabled": True, "poll_interval_ms": 2000},
        "quick_profit": {
            "enabled": True,
            "mode": "fixed_usd",
            "target_usd": "5.0",
            "priority": "highest",
            "ignore_other_rules": False,
        },
        "trailing": {
            "enable": False,
            "activation_profit_atr_k": 1.0,
            "cooldown_sec": 0.0,
            "step_bps": "0",
        },
        "emergency": {"enabled": False, "min_health_score": 0.3},
        "brackets": {
            "enable": False,
            "oco_emulation": False,
            "working_type_default": "MARK_PRICE",
            "price_protect": False,
            "keep_single_bracket_set": True,
            "atomic_close": True,
            "bracket_tracking": True,
            "retry": {"backoff_ms": [120, 250, 400], "max_attempts": 3, "fallback_to_limit": True},
            "aggregated_oco": {
                "enabled": False,
                "aggregated_only_mode": False,
                "recalc_on_scale_in": True,
                "recalc_on_partial_close": False,
                "ttl_protect_new_bracket_ms": 3000,
                "allow_unprotected_position": False,
                "watchdog": {
                    "enabled": False,
                    "grace": {"cancel_orphan_legs_ms": 500, "attempt_recovery_before_cancel_ms": 200},
                },
            },
        },
        "guardian": {
            "unified": True,
            "emit_tidy_event": True,
            "poll_interval_ms": 500,
            "cleanup_ttl_ms": 6000,
            "symbol_cooldown_ms": 4000,
        },
        "watchdog": {
            "ack_ttl_ms": 8000,
            "fill_ttl_ms": 30000,
            "check_interval_ms": 1000,
            "timeouts": {"ack_ttl_ms": 8000, "fill_ttl_ms": 30000, "check_interval_ms": 1000},
        },
        "positions": {"ws_snapshot": {"enabled": True, "mode": "periodic", "poll_interval_ms": 5000}},
    }


def _build_legacy_config_dict() -> Dict[str, Any]:
    """Build legacy config dict (trading.execution.manage structure) for testing."""
    return {
        "trading": {
            "execution": {
                "manage": {
                    "auto": False,
                    "mode": "legacy",
                    "orphan_monitor": {"enabled": False, "poll_interval_ms": 3000},
                    "quick_profit": {
                        "enabled": False,
                        "mode": "fixed_usd",
                        "target_usd": "2.0",
                        "priority": "highest",
                        "ignore_other_rules": False,
                    },
                    "trailing": {"enable": False, "activation_profit_atr_k": 1.0, "cooldown_sec": 0.0, "step_bps": "0"},
                    "emergency": {"enabled": False, "min_health_score": 0.3},
                    "guardian": {
                        "unified": True,
                        "emit_tidy_event": True,
                        "poll_interval_ms": 500,
                        "cleanup_ttl_ms": 6000,
                        "symbol_cooldown_ms": 4000,
                    },
                    "watchdog": {"ack_ttl_ms": 8000, "fill_ttl_ms": 30000, "check_interval_ms": 1000},
                    "positions": {"ws_snapshot": {"enabled": False, "mode": "periodic", "poll_interval_ms": 5000}},
                },
                "brackets": {
                    "enable": False,
                    "oco_emulation": False,
                    "working_type_default": "MARK_PRICE",
                    "price_protect": False,
                    "keep_single_bracket_set": True,
                    "atomic_close": True,
                    "bracket_tracking": True,
                    "retry": {"backoff_ms": [120, 250, 400], "max_attempts": 3, "fallback_to_limit": True},
                    "aggregated_oco": {
                        "enabled": False,
                        "aggregated_only_mode": False,
                        "recalc_on_scale_in": True,
                        "recalc_on_partial_close": False,
                        "ttl_protect_new_bracket_ms": 3000,
                        "allow_unprotected_position": False,
                        "watchdog": {
                            "enabled": False,
                            "grace": {"cancel_orphan_legs_ms": 500, "attempt_recovery_before_cancel_ms": 200},
                        },
                    },
                },
            }
        }
    }


class TestManageConfigHybridV2Path:
    """Test V2 config path (primary): config with config_v2.domains['execution']['manage']."""

    def test_v2_path_used_when_v2_config_present(self):
        """V2 config detected → _build_manage_from_v2 called → source='config_v2'."""
        v2_manage = _build_v2_manage_dict()
        cfg = MagicMock()
        cfg.config_v2 = MagicMock()
        cfg.config_v2.domains = {"execution": MagicMock(manage=v2_manage)}

        result = resolve_execution_manage_config(cfg)

        assert isinstance(result, ExecutionManageConfig)
        assert result.source == "config_v2", "V2 config should set source='config_v2'"
        assert result.auto is True, "V2 manage.auto=True should be used"
        assert result.quick_profit.enabled is True, "V2 quick_profit.enabled=True should be used"
        assert result.quick_profit.target_usd == Decimal(
            "5.0"), "V2 quick_profit.target_usd=5.0 should be used"

    def test_v2_path_with_pydantic_model_dump(self):
        """V2 config as Pydantic model → model_dump() called → source='config_v2'."""
        v2_manage = _build_v2_manage_dict()
        manage_mock = MagicMock()
        manage_mock.model_dump.return_value = v2_manage

        cfg = MagicMock()
        cfg.config_v2 = MagicMock()
        cfg.config_v2.domains = {"execution": MagicMock(manage=manage_mock)}

        result = resolve_execution_manage_config(cfg)

        assert result.source == "config_v2"
        manage_mock.model_dump.assert_called_once()


class TestManageConfigHybridLegacyPath:
    """Test legacy config path (fallback): config without config_v2."""

    def test_legacy_path_used_when_no_v2_config(self):
        """No config_v2 → _get_v2_execution_manage_cfg returns None → _build_manage_from_legacy called → source='legacy'."""
        cfg = _build_legacy_config_dict()

        result = resolve_execution_manage_config(cfg)

        assert isinstance(result, ExecutionManageConfig)
        assert result.source == "legacy", "Legacy config should set source='legacy'"
        assert result.auto is False, "Legacy manage.auto=False should be used"
        assert result.quick_profit.enabled is False, "Legacy quick_profit.enabled=False should be used"
        assert result.orphan_monitor.enabled is False, "Legacy orphan_monitor.enabled=False should be used"

    def test_legacy_path_when_v2_domains_missing(self):
        """config_v2 exists but domains=None → _get_v2_execution_manage_cfg returns None → legacy fallback."""
        cfg = _build_legacy_config_dict()
        cfg["config_v2"] = {"domains": None}

        result = resolve_execution_manage_config(cfg)

        assert result.source == "legacy"

    def test_legacy_path_when_execution_domain_missing(self):
        """config_v2.domains exists but 'execution' missing → legacy fallback."""
        cfg = _build_legacy_config_dict()
        cfg["config_v2"] = {"domains": {}}

        result = resolve_execution_manage_config(cfg)

        assert result.source == "legacy"

    def test_legacy_path_when_manage_missing(self):
        """config_v2.domains['execution'] exists but 'manage' missing → legacy fallback."""
        cfg = _build_legacy_config_dict()
        cfg["config_v2"] = {"domains": {"execution": {}}}

        result = resolve_execution_manage_config(cfg)

        assert result.source == "legacy"


class TestManageConfigHybridPriority:
    """Test hybrid priority: V2 takes precedence when both V2 and legacy paths available."""

    def test_v2_priority_over_legacy_when_both_present(self):
        """Config with both V2 and legacy paths → V2 takes priority → source='config_v2'."""
        v2_manage = _build_v2_manage_dict()
        v2_manage["auto"] = True
        v2_manage["quick_profit"]["target_usd"] = "10.0"

        legacy = _build_legacy_config_dict()
        legacy["trading"]["execution"]["manage"]["auto"] = False
        legacy["trading"]["execution"]["manage"]["quick_profit"]["target_usd"] = "2.0"

        cfg_mock = MagicMock()
        cfg_mock.config_v2 = MagicMock()
        cfg_mock.config_v2.domains = {"execution": MagicMock(manage=v2_manage)}
        # Also expose legacy path attributes (not used due to V2 priority)
        cfg_mock.trading = legacy["trading"]

        result = resolve_execution_manage_config(cfg_mock)

        assert result.source == "config_v2", "V2 should take priority when both paths available"
        assert result.auto is True, "V2 auto=True should win over legacy auto=False"
        assert result.quick_profit.target_usd == Decimal(
            "10.0"), "V2 target_usd=10.0 should win over legacy 2.0"


class TestManageConfigHybridFallback:
    """Test V2 → legacy fallback on exceptions (except ConfigError which bubbles up)."""

    def test_v2_exception_triggers_legacy_fallback(self):
        """V2 parsing raises generic Exception → fallback to legacy → source='legacy'."""
        # Create V2 config that will fail during _build_manage_from_v2 (not during _get_v2_execution_manage_cfg)
        # We'll patch _build_manage_from_v2 to raise ValueError to simulate parsing error

        legacy = _build_legacy_config_dict()
        v2_manage = _build_v2_manage_dict()

        cfg_mock = MagicMock()
        cfg_mock.config_v2 = MagicMock()
        cfg_mock.config_v2.domains = {"execution": MagicMock(manage=v2_manage)}
        cfg_mock.trading = legacy["trading"]

        with patch("apps.reference.domains.execution_position.manage_config._build_manage_from_v2") as mock_v2_build:
            # Make _build_manage_from_v2 raise ValueError to trigger fallback
            mock_v2_build.side_effect = ValueError(
                "Simulated V2 parsing error")

            result = resolve_execution_manage_config(cfg_mock)

            # Should fallback to legacy due to V2 parsing error
            assert result.source == "legacy", "Should fallback to legacy when V2 parsing fails"
            mock_v2_build.assert_called_once()  # Verify V2 was attempted

    def test_v2_config_error_bubbles_up(self):
        """V2 parsing raises ConfigError → NOT caught → propagates to caller."""
        from vfoundation.errors import ConfigError

        v2_manage = _build_v2_manage_dict()
        # Invalid: requires aggregated_oco.enabled=true
        v2_manage["mode"] = "aggregated_only"

        cfg = MagicMock()
        cfg.config_v2 = MagicMock()
        cfg.config_v2.domains = {"execution": MagicMock(manage=v2_manage)}

        with pytest.raises(ConfigError):
            resolve_execution_manage_config(cfg)


class TestManageConfigCaching:
    """Test resolver caching behavior (same config object → cached result)."""

    def test_caching_returns_same_result_for_same_object(self):
        """Same config object → cached result returned (no re-resolution)."""
        v2_manage = _build_v2_manage_dict()
        cfg = MagicMock()
        cfg.config_v2 = MagicMock()
        cfg.config_v2.domains = {"execution": MagicMock(manage=v2_manage)}

        result1 = resolve_execution_manage_config(cfg)
        result2 = resolve_execution_manage_config(cfg)

        assert result1 is result2, "Same config object should return cached result"

    def test_cache_invalidated_for_different_object(self):
        """Different config object (even if id() reused) → cache invalidated → new resolution."""
        v2_manage1 = _build_v2_manage_dict()
        cfg1 = MagicMock()
        cfg1.config_v2 = MagicMock()
        cfg1.config_v2.domains = {"execution": MagicMock(manage=v2_manage1)}

        result1 = resolve_execution_manage_config(cfg1)

        v2_manage2 = _build_v2_manage_dict()
        v2_manage2["auto"] = False
        cfg2 = MagicMock()
        cfg2.config_v2 = MagicMock()
        cfg2.config_v2.domains = {"execution": MagicMock(manage=v2_manage2)}

        result2 = resolve_execution_manage_config(cfg2)

        # Results should differ based on config differences
        assert result1.auto is True
        assert result2.auto is False
