"""Tests for independent NRR-026 / NRR-027 enable/disable flags.

NRR-026 = INSUFFICIENT_TREND_CONFIRMATION (regime confidence below-min, trend/confidence checks)
NRR-027 = DIRECTIONAL_SANITY_BLOCKED (countertrend hard-veto)

Both are now individually gated by ``nrr026_enabled`` and ``nrr027_enabled``
inside ``DirectionalSanityConfig``, independent of each other.
"""
from __future__ import annotations

import pytest
from apps.reference.domains.decision_making.gates.safety_gates import _check_directional_gate
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
    NormalizedRejectReasons,
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _call(
    *,
    intent_side: str = "LONG",
    trend_dir: str = "UP",
    trend_run_length: int = 3,
    trend_confidence: float = 0.9,
    regime_confidence: float | None = 0.9,
    min_conf: float = 0.0,
    hard_veto_consecutive_bars: int = 2,
    ds_enabled: bool = True,
    nrr026_enabled: bool = True,
    nrr027_enabled: bool = True,
    reduce_only: bool = False,
    apply_safety_gates: bool = True,
) -> tuple[str, str | None, str]:
    return _check_directional_gate(
        intent_side=intent_side,
        reduce_only=reduce_only,
        apply_safety_gates=apply_safety_gates,
        ds_enabled=ds_enabled,
        nrr026_enabled=nrr026_enabled,
        nrr027_enabled=nrr027_enabled,
        strategy_id="aurora",
        trend_dir=trend_dir,
        trend_run_length=trend_run_length,
        trend_confidence=trend_confidence,
        regime_confidence=regime_confidence,
        min_conf=min_conf,
        hard_veto_consecutive_bars=hard_veto_consecutive_bars,
    )


# ─── Baseline: both enabled (existing behavior preserved) ────────────────────

class TestBothEnabled:
    """Both flags enabled — current production behaviour must be unchanged."""

    def test_allow_when_trend_matches_side(self):
        outcome, deny, _ = _call(intent_side="LONG", trend_dir="UP")
        assert outcome == "ALLOW"
        assert deny is None

    def test_nrr026_on_unknown_trend_dir(self):
        outcome, deny, _ = _call(trend_dir="UNKNOWN")
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION

    def test_nrr026_on_insufficient_confidence(self):
        outcome, deny, _ = _call(
            min_conf=0.95, trend_confidence=0.5, regime_confidence=0.5)
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION

    def test_nrr027_countertrend_hard_veto_long(self):
        # DOWN trend, LONG side, run >= veto bars → NRR-027
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=3, hard_veto_consecutive_bars=2,
        )
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED

    def test_nrr027_countertrend_soft_allow_long(self):
        # run < veto bars → soft ALLOW (not NRR-027 yet)
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=1, hard_veto_consecutive_bars=2,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_nrr027_countertrend_hard_veto_short(self):
        outcome, deny, _ = _call(
            intent_side="SHORT", trend_dir="UP",
            trend_run_length=3, hard_veto_consecutive_bars=2,
        )
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED


# ─── NRR-026 disabled, NRR-027 enabled ──────────────────────────────────────

class TestNRR026DisabledNRR027Enabled:
    """NRR-026 off: trend/confidence denials bypassed; NRR-027 countertrend veto still active."""

    def test_unknown_trend_dir_passes_when_nrr026_disabled(self):
        outcome, deny, _ = _call(trend_dir="UNKNOWN", nrr026_enabled=False)
        assert outcome == "ALLOW"
        assert deny is None

    def test_insufficient_confidence_passes_when_nrr026_disabled(self):
        outcome, deny, _ = _call(
            min_conf=0.95, trend_confidence=0.1, regime_confidence=0.1,
            nrr026_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_nrr027_countertrend_veto_still_fires_when_nrr026_disabled(self):
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=5, hard_veto_consecutive_bars=2,
            nrr026_enabled=False,
        )
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED

    def test_nrr027_soft_allow_still_works_when_nrr026_disabled(self):
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=1, hard_veto_consecutive_bars=2,
            nrr026_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_allow_on_trend_match_when_nrr026_disabled(self):
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="UP", nrr026_enabled=False)
        assert outcome == "ALLOW"
        assert deny is None


# ─── NRR-026 enabled, NRR-027 disabled ──────────────────────────────────────

class TestNRR026EnabledNRR027Disabled:
    """NRR-027 off: countertrend veto bypassed; NRR-026 confidence/trend checks still active."""

    def test_unknown_trend_dir_still_denied_when_nrr027_disabled(self):
        outcome, deny, _ = _call(trend_dir="UNKNOWN", nrr027_enabled=False)
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION

    def test_insufficient_confidence_still_denied_when_nrr027_disabled(self):
        outcome, deny, _ = _call(
            min_conf=0.95, trend_confidence=0.1, regime_confidence=0.1,
            nrr027_enabled=False,
        )
        assert outcome == "DENY"
        assert deny == NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION

    def test_countertrend_hard_veto_passes_when_nrr027_disabled(self):
        # Even with run >= veto bars, no NRR-027 fired
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=5, hard_veto_consecutive_bars=2,
            nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_countertrend_short_passes_when_nrr027_disabled(self):
        outcome, deny, _ = _call(
            intent_side="SHORT", trend_dir="UP",
            trend_run_length=5, hard_veto_consecutive_bars=2,
            nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_soft_allow_window_unchanged_when_nrr027_disabled(self):
        # Under veto bars is soft-allow regardless; disabling nrr027 just extends it to full veto
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=1, hard_veto_consecutive_bars=2,
            nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None


# ─── Both disabled ───────────────────────────────────────────────────────────

class TestBothDisabled:
    """Both NRR-026 and NRR-027 off: entire directional content passes through."""

    def test_unknown_trend_passes(self):
        outcome, deny, _ = _call(
            trend_dir="UNKNOWN", nrr026_enabled=False, nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_zero_confidence_passes(self):
        outcome, deny, _ = _call(
            min_conf=1.0, trend_confidence=0.0, regime_confidence=0.0,
            nrr026_enabled=False, nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_countertrend_long_passes(self):
        outcome, deny, _ = _call(
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=10, hard_veto_consecutive_bars=2,
            nrr026_enabled=False, nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None

    def test_countertrend_short_passes(self):
        outcome, deny, _ = _call(
            intent_side="SHORT", trend_dir="UP",
            trend_run_length=10, hard_veto_consecutive_bars=2,
            nrr026_enabled=False, nrr027_enabled=False,
        )
        assert outcome == "ALLOW"
        assert deny is None


# ─── Master ds_enabled=False overrides both sub-flags ───────────────────────

class TestMasterSwitchOverride:
    """ds_enabled=False must bypass everything regardless of sub-flags."""

    def test_ds_disabled_overrides_nrr026_nrr027_enabled(self):
        outcome, deny, why = _call(
            ds_enabled=False, nrr026_enabled=True, nrr027_enabled=True,
            trend_dir="UNKNOWN",
        )
        assert outcome == "ALLOW"
        assert deny is None
        assert "disabled" in why

    def test_ds_disabled_overrides_nrr027(self):
        outcome, deny, _ = _call(
            ds_enabled=False, nrr027_enabled=True,
            intent_side="LONG", trend_dir="DOWN",
            trend_run_length=10, hard_veto_consecutive_bars=2,
        )
        assert outcome == "ALLOW"
        assert deny is None


# ─── Config model accepts both flags ─────────────────────────────────────────

class TestConfigModel:
    """DirectionalSanityConfig must accept nrr026_enabled / nrr027_enabled."""

    def _base_kwargs(self):
        return dict(
            enabled=True,
            min_abs_delta_price=0.0,
            min_confidence=0.0,
            min_regime_confidence=0.35,
            hard_veto_consecutive_bars=2,
            consecutive_bars=1,
        )

    def test_both_defaults_to_true(self):
        from apps.reference.config.domains.decision_making import DirectionalSanityConfig
        cfg = DirectionalSanityConfig(**self._base_kwargs())
        assert cfg.nrr026_enabled is True
        assert cfg.nrr027_enabled is True

    def test_nrr026_can_be_set_false(self):
        from apps.reference.config.domains.decision_making import DirectionalSanityConfig
        cfg = DirectionalSanityConfig(
            **self._base_kwargs(), nrr026_enabled=False)
        assert cfg.nrr026_enabled is False
        assert cfg.nrr027_enabled is True

    def test_nrr027_can_be_set_false(self):
        from apps.reference.config.domains.decision_making import DirectionalSanityConfig
        cfg = DirectionalSanityConfig(
            **self._base_kwargs(), nrr027_enabled=False)
        assert cfg.nrr026_enabled is True
        assert cfg.nrr027_enabled is False

    def test_both_can_be_false(self):
        from apps.reference.config.domains.decision_making import DirectionalSanityConfig
        cfg = DirectionalSanityConfig(
            **self._base_kwargs(), nrr026_enabled=False, nrr027_enabled=False
        )
        assert cfg.nrr026_enabled is False
        assert cfg.nrr027_enabled is False
