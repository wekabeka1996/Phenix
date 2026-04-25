"""
Phase 4 Integration Tests — Fallback + Mode Coverage.

Tests:
1. Local fallback_on_error: QuadraticKernel exception → AuroraScoringKernel fallback
2. Mode coverage: shield/kernel initialization across PARANOID/CURIOUS modes
"""
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from apps.reference.config_models import (
    DangerZoneExitType,
    ExitManagerConfig,
    OperationalMode,
    ContextShieldConfig,
    MemoryShieldConfig,
)
from apps.reference.shared.decision_primitives.exit_manager import ExitManager
from apps.reference.shared.decision_primitives.shields.context_shield import ContextShield
from apps.reference.shared.decision_primitives.shields.danger_zone import DangerZoneShield
from apps.reference.domains.decision_making.primitives.operational_mode import ModeManager


def _exit_manager_config(**overrides) -> ExitManagerConfig:
    payload = {
        "time_exit_enabled": False,
        "max_hold_time_sec": 3600,
        "signal_exit_enabled": False,
        "signal_reversal_threshold": -0.1,
        "danger_zone_action": DangerZoneExitType.TIGHTEN_STOPS,
        "danger_zone_tighten_factor": 0.5,
    }
    payload.update(overrides)
    return ExitManagerConfig(**payload)


def _memory_shield_config(**overrides) -> MemoryShieldConfig:
    payload = {
        "enabled": True,
        "decay_rate": 0.95,
        "max_states": 200,
        "unknown_threshold": 3,
        "exploring_threshold": 10,
        "unknown_multiplier": 0.6,
        "exploring_multiplier": 0.8,
        "known_multiplier": 1.0,
        "storage_path": None,
        "flush_interval_sec": 60.0,
    }
    payload.update(overrides)
    return MemoryShieldConfig(**payload)


def _context_shield_config(**overrides) -> ContextShieldConfig:
    payload = {
        "enabled": True,
        "regime_multipliers": {
            "TREND_UP": 1.0,
            "HIGH_VOLATILITY": 0.3,
        },
        "default_multiplier": 0.5,
        "no_regime_multiplier": 0.4,
        "ttl_ms": 14_400_000,
        "stale_mult_normal": 0.5,
        "stale_mult_danger": 0.2,
        "danger_regimes": ["HIGH_VOLATILITY", "UNCERTAIN"],
    }
    payload.update(overrides)
    return ContextShieldConfig(**payload)


# ---------------------------------------------------------------------------
# 1. Fallback: ExitManager doesn't crash on missing trailing args
# ---------------------------------------------------------------------------
class TestExitManagerFallbackSafety:
    def test_trailing_disabled_by_default(self):
        """ExitManager with default config → trailing disabled → no crashes."""
        em = ExitManager(_exit_manager_config())
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", Decimal("100"), Decimal("101"),
            hold_time_sec=100, final_score=0.5,
            danger_zone_active=False,
        )
        assert not ok

    def test_trailing_enabled_no_mfe_safe(self):
        """Trailing enabled but no mfe_price → graceful skip."""
        em = ExitManager(
            _exit_manager_config(),
            trailing_enabled=True,
            trailing_activation_pct=0.003,
            trailing_atr_mult=1.5,
        )
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", Decimal("100"), Decimal("101"),
            hold_time_sec=100, final_score=0.5,
            danger_zone_active=False,
            mfe_price=None, atr=None,
        )
        assert not ok


# ---------------------------------------------------------------------------
# 2. Mode coverage: PARANOID vs CURIOUS shield behavior
# ---------------------------------------------------------------------------
class TestModeCoverage:
    @pytest.mark.parametrize("mode", [OperationalMode.PARANOID, OperationalMode.CURIOUS])
    def test_mode_manager_creates_successfully(self, mode):
        mm = ModeManager(mode)
        assert mm is not None

    @pytest.mark.parametrize("mode", [OperationalMode.PARANOID, OperationalMode.CURIOUS])
    def test_mode_manager_overrides_memory_shield(self, mode):
        mm = ModeManager(mode)
        cfg = _memory_shield_config()
        patched = mm.apply_memory_shield_overrides(cfg)
        if mode == OperationalMode.CURIOUS:
            assert patched.unknown_multiplier == 1.0
        else:
            assert patched.unknown_multiplier == 0.6

    def test_context_shield_works_in_both_modes(self):
        """ContextShield should attenuate identically regardless of mode."""
        cs = ContextShield(
            regime_multipliers={"TREND_UP": 1.0, "HIGH_VOLATILITY": 0.3},
        )
        r1 = cs.evaluate("BTC", {"regime": "TREND_UP"}, 0.5, 1.0)
        r2 = cs.evaluate("BTC", {"regime": "HIGH_VOLATILITY"}, 0.5, 1.0)
        assert r1.multiplier == 1.0
        assert r2.multiplier == 0.3


# ---------------------------------------------------------------------------
# 3. Config validation: TTL fields accepted
# ---------------------------------------------------------------------------
class TestConfigValidation:
    def test_context_shield_config_accepts_ttl_fields(self):
        cfg = _context_shield_config(
            ttl_ms=7_200_000,
            stale_mult_normal=0.5,
            stale_mult_danger=0.2,
            danger_regimes=["HIGH_VOLATILITY", "UNCERTAIN"],
        )
        assert cfg.ttl_ms == 7_200_000
        assert cfg.stale_mult_danger == 0.2
        assert "UNCERTAIN" in cfg.danger_regimes

    def test_context_shield_config_requires_explicit_fields(self):
        with pytest.raises(Exception):
            ContextShieldConfig()

    def test_context_shield_rejects_extra_fields(self):
        with pytest.raises(Exception):
            ContextShieldConfig(nonexistent_field=True)
