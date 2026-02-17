"""
Unit tests for ExitManager — Trailing Stop + Priority Chain.

Tests cover:
1. S2-TRAILING: Trailing stop activation, exit, and invariants
2. Priority: DangerZone > Trailing > Time > Signal
3. Existing behavior preservation: DZ, Time, Signal exits
"""
import pytest
from decimal import Decimal

from apps.reference.config_models import ExitManagerConfig, DangerZoneExitType
from apps.reference.domains.decision_making.exit_manager import ExitManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_em(
    *,
    trailing_enabled=False,
    trailing_activation_pct=0.003,  # 0.3%
    trailing_atr_mult=1.5,
    trailing_pct=None,
    danger_action=DangerZoneExitType.TIGHTEN_STOPS,
    time_exit_enabled=False,
    signal_exit_enabled=False,
    **kwargs,
):
    cfg = ExitManagerConfig(
        danger_zone_action=danger_action,
        time_exit_enabled=time_exit_enabled,
        signal_exit_enabled=signal_exit_enabled,
        **kwargs,
    )
    return ExitManager(
        cfg,
        trailing_enabled=trailing_enabled,
        trailing_activation_pct=trailing_activation_pct,
        trailing_atr_mult=trailing_atr_mult,
        trailing_pct=trailing_pct,
    )


D = Decimal


# ---------------------------------------------------------------------------
# 1. Trailing Stop: Activation
# ---------------------------------------------------------------------------
class TestTrailingActivation:
    def test_not_activated_below_threshold(self):
        """PnL < activation_pct → no trailing exit."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.01)
        # Long entry=100, current=100.5 → 0.5% < 1%
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("100.5"), 0, 0.0, False,
            mfe_price=D("101"), atr=D("2"),
        )
        assert not ok
        assert reason is None

    def test_activated_above_threshold(self):
        """PnL > activation_pct but above trail → no exit (just active)."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.003, trailing_atr_mult=1.5)
        # Long: entry=100, current=102, mfe=103, atr=2 → trail=103-3=100
        # current(102) > trail(100) → hold
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("102"), 0, 0.0, False,
            mfe_price=D("103"), atr=D("2"),
        )
        assert not ok

    def test_trailing_disabled_ignores(self):
        """trailing_enabled=False → skips all trailing logic."""
        em = _make_em(trailing_enabled=False)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("95"), 0, 0.0, False,
            mfe_price=D("110"), atr=D("2"),
        )
        assert not ok


# ---------------------------------------------------------------------------
# 2. Trailing Stop: Exit Triggers
# ---------------------------------------------------------------------------
class TestTrailingExit:
    def test_long_trail_exit(self):
        """LONG: price drops below trail stop → EXIT."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.003, trailing_atr_mult=1.5)
        # entry=100, mfe=110, atr=2 → trail=110-3=107
        # current=106 < 107 → EXIT
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("106"), 0, 0.0, False,
            mfe_price=D("110"), atr=D("2"),
        )
        assert ok
        assert "EXIT_TRAILING" in reason
        assert "106" in reason

    def test_short_trail_exit(self):
        """SHORT: price rises above trail stop → EXIT."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.003, trailing_atr_mult=1.5)
        # entry=100, mfe=90, atr=2 → trail=90+3=93
        # current=94 > 93 → EXIT
        ok, reason, sl = em.check_exit(
            "BTC", "SHORT", D("100"), D("94"), 0, 0.0, False,
            mfe_price=D("90"), atr=D("2"),
        )
        assert ok
        assert "EXIT_TRAILING" in reason

    def test_long_hold_above_trail(self):
        """LONG: price above trail → hold."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.003, trailing_atr_mult=1.5)
        # entry=100, mfe=110, atr=2 → trail=110-3=107
        # current=108 > 107 → hold
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("108"), 0, 0.0, False,
            mfe_price=D("110"), atr=D("2"),
        )
        assert not ok

    def test_pct_fallback_when_no_atr(self):
        """When ATR is None, use trail_pct as fallback."""
        em = _make_em(
            trailing_enabled=True,
            trailing_activation_pct=0.003,
            trailing_atr_mult=None,  # No ATR mult
            trailing_pct=0.02,       # 2% trail
        )
        # entry=100, mfe=110, trail=110*0.02=2.2, trail_stop=107.8
        # current=107 < 107.8 → EXIT
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("107"), 0, 0.0, False,
            mfe_price=D("110"), atr=None,
        )
        assert ok
        assert "EXIT_TRAILING" in reason


# ---------------------------------------------------------------------------
# 3. Trailing Stop: Invariants
# ---------------------------------------------------------------------------
class TestTrailingInvariants:
    def test_trail_never_below_entry_for_long(self):
        """LONG trail stop must be above entry. If not → skip trailing."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.001, trailing_atr_mult=10.0)
        # entry=100, mfe=105, atr=2 → trail=105-20=85 (below entry!)
        # Should NOT trigger exit even though current < trail
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("90"), 0, 0.0, False,
            mfe_price=D("105"), atr=D("2"),
        )
        assert not ok  # Trail below entry → skip

    def test_trail_never_above_entry_for_short(self):
        """SHORT trail stop must be below entry. If not → skip trailing."""
        em = _make_em(trailing_enabled=True, trailing_activation_pct=0.001, trailing_atr_mult=10.0)
        # entry=100, mfe=95, atr=2 → trail=95+20=115 (above entry!)
        ok, reason, sl = em.check_exit(
            "BTC", "SHORT", D("100"), D("110"), 0, 0.0, False,
            mfe_price=D("95"), atr=D("2"),
        )
        assert not ok  # Trail above entry → skip

    def test_no_mfe_price_skips_trailing(self):
        """If mfe_price is None → skip trailing entirely."""
        em = _make_em(trailing_enabled=True)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("90"), 0, 0.0, False,
            mfe_price=None, atr=D("2"),
        )
        assert not ok


# ---------------------------------------------------------------------------
# 4. Priority Chain
# ---------------------------------------------------------------------------
class TestPriorityChain:
    def test_danger_close_beats_trailing(self):
        """DangerZone CLOSE_POSITION has highest priority, even when trailing would exit."""
        em = _make_em(
            trailing_enabled=True,
            trailing_activation_pct=0.003,
            trailing_atr_mult=1.5,
            danger_action=DangerZoneExitType.CLOSE_POSITION,
        )
        # Both DZ and trailing would trigger — DZ should win
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("106"), 0, 0.0,
            danger_zone_active=True,
            mfe_price=D("110"), atr=D("2"),
        )
        assert ok
        assert "DANGER_ZONE" in reason
        assert "TRAILING" not in reason

    def test_trailing_beats_time(self):
        """Trailing exit fires before Time exit reaches its check."""
        em = _make_em(
            trailing_enabled=True,
            trailing_activation_pct=0.003,
            trailing_atr_mult=1.5,
            time_exit_enabled=True,
            max_hold_time_sec=100,
        )
        # Trailing would trigger (price below trail)
        # Time would also trigger (hold > 100s)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("106"), 200, 0.0,
            danger_zone_active=False,
            mfe_price=D("110"), atr=D("2"),
        )
        assert ok
        assert "TRAILING" in reason  # Trailing fires first


# ---------------------------------------------------------------------------
# 5. Existing exits (regression)
# ---------------------------------------------------------------------------
class TestExistingExits:
    def test_danger_zone_force_close(self):
        em = _make_em(danger_action=DangerZoneExitType.CLOSE_POSITION)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("99"), 0, 0.0, True,
        )
        assert ok
        assert "ForceClose" in reason

    def test_time_exit(self):
        em = _make_em(time_exit_enabled=True, max_hold_time_sec=3600)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("101"), 7200, 0.0, False,
        )
        assert ok
        assert "TIME_LIMIT" in reason

    def test_signal_reversal_long(self):
        em = _make_em(signal_exit_enabled=True, signal_reversal_threshold=-0.1)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("101"), 0, -0.5, False,
        )
        assert ok
        assert "SIGNAL_REVERSAL" in reason

    def test_no_exit_when_everything_ok(self):
        em = _make_em(time_exit_enabled=True, max_hold_time_sec=3600, signal_exit_enabled=True)
        ok, reason, sl = em.check_exit(
            "BTC", "LONG", D("100"), D("101"), 100, 0.5, False,
        )
        assert not ok
        assert reason is None
