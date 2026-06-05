"""
Phase 6: md_amr Basis Decoupling — regime removed from md_amr basis_required_bars.

Verifies:
1. md_amr basis_required_bars == max(channel_window, atr_window + atr_stats_window - 1, dir_score history) == 96
2. md_amr needs_regime == True (regime tracked separately via warmup)
3. aurora basis unchanged (still uses regime_detector_required_bars)
4. MR restart_local_basis_counter unchanged
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.reference.contracts.strategy_compatibility_matrix import (
    build_active_strategy_compatibility_profiles,
    regime_detector_required_bars,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _config(
    sma_long: int = 192,
    atr_period: int = 14,
    atr_sma_length: int = 288,
    buffer: int = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        basis_import_buffer=buffer,
        regime=SimpleNamespace(
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(sma_long_period=sma_long),
                volatility=SimpleNamespace(
                    atr_period=atr_period, atr_sma_length=atr_sma_length),
            )
        ),
        domains=SimpleNamespace(
            feature_engineering=SimpleNamespace(
                pillars=SimpleNamespace(
                    enabled=True,
                    backfill=SimpleNamespace(
                        enabled=True, d1_candles=200, h4_candles=100, m15_candles=50),
                )
            )
        ),
        strategies_registry=SimpleNamespace(
            assignments={
                "BTCUSDT": ["aurora"],
                "ETHUSDT": ["md_amr"],
                "DOGEUSDT": ["mean_reversion"],
            }
        ),
        instruments={
            "BTCUSDT": SimpleNamespace(),
            "ETHUSDT": SimpleNamespace(),
            "DOGEUSDT": SimpleNamespace(),
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300, decision=SimpleNamespace()),
            md_amr=SimpleNamespace(
                timeframe_sec=900,
                channel_window_bars=12,
                atr_window=14,
                atr_stats_window=64,
                decision=SimpleNamespace(),
            ),
            mean_reversion=SimpleNamespace(
                timeframe_sec=900, decision=SimpleNamespace()),
        ),
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_md_amr_basis_equals_own_data_needs() -> None:
    """md_amr basis_required_bars == max(12, 14 + 64 - 1, 96) == 96, NOT 301."""
    cfg = _config()
    profiles = build_active_strategy_compatibility_profiles(cfg)
    md_amr_profile = profiles.get("md_amr")
    assert md_amr_profile is not None, "md_amr profile not found"
    assert md_amr_profile.basis_required_bars == 96, (
        f"Expected 96, got {md_amr_profile.basis_required_bars}. "
        "md_amr should NOT include regime_detector_required_bars."
    )


def test_md_amr_regime_tracked_separately() -> None:
    """md_amr needs_regime == True → regime tracked via warmup, not basis bars."""
    cfg = _config()
    profiles = build_active_strategy_compatibility_profiles(cfg)
    md_amr_profile = profiles.get("md_amr")
    assert md_amr_profile is not None
    assert md_amr_profile.needs_regime is True, (
        "md_amr must have needs_regime=True (regime warmup tracked separately)"
    )


def test_aurora_basis_unchanged() -> None:
    """aurora still includes regime_detector_required_bars in its basis."""
    cfg = _config()
    profiles = build_active_strategy_compatibility_profiles(cfg)
    aurora_profile = profiles.get("aurora")
    assert aurora_profile is not None
    canonical = regime_detector_required_bars(cfg)
    assert aurora_profile.basis_required_bars >= canonical, (
        f"aurora basis {aurora_profile.basis_required_bars} < regime canonical {canonical}"
    )


def test_mr_basis_unchanged() -> None:
    """MR restart_local_basis_counter should remain False (no local counter)."""
    cfg = _config()
    profiles = build_active_strategy_compatibility_profiles(cfg)
    mr_profile = profiles.get("mean_reversion")
    assert mr_profile is not None
    assert mr_profile.restart_local_basis_counter is False, (
        "mean_reversion should NOT restart local basis counter"
    )
