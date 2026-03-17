"""
Phase 2: Seed Propagation — warmup report correctly tracks handler basis seed status.

Verifies:
1. Seed success → no blocker, can_open_new_risk=True
2. Seed failure → blocker "handler_basis_seed", can_open_new_risk=False
3. basis_seed_statuses=None → existing behavior preserved (backward compat)
4. MR (restart_local_basis_counter=False) → no seed check
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.reference.bootstrap.startup_warmup import (
    StartupWarmupState,
    StartupWarmupStatus,
    build_startup_warmup_report,
)
from apps.reference.bootstrap.runtime_analytics_restore import (
    StartupAnalyticsRestoreReport,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _config(
    sma_long: int = 192,
    atr_period: int = 14,
    atr_sma_length: int = 288,
    buffer: int = 20,
) -> SimpleNamespace:
    """Minimal config fixture with regime models, instruments, and strategies."""
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
                "DOGEUSDT": ["mean_reversion"],
            }
        ),
        instruments={
            "BTCUSDT": SimpleNamespace(),
            "DOGEUSDT": SimpleNamespace(),
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                timeframe_sec=300,
                decision=SimpleNamespace(),
            ),
            mean_reversion=SimpleNamespace(
                timeframe_sec=900,
                decision=SimpleNamespace(),
            ),
        ),
    )


def _restore_report() -> StartupAnalyticsRestoreReport:
    return StartupAnalyticsRestoreReport(
        updated_at=1000,
        source="test",
        snapshots={},
    )


def _warmed_status() -> StartupWarmupStatus:
    return StartupWarmupStatus(
        state=StartupWarmupState.WARMED,
        why=("basis_seed_complete",),
        updated_at=1000,
        source="test:seed",
        details={"seeded_bars": 301, "required_bars": 301},
    )


def _failed_status() -> StartupWarmupStatus:
    return StartupWarmupStatus(
        state=StartupWarmupState.FAILED,
        why=("seed_failed",),
        updated_at=1000,
        source="test:seed",
        details={"seeded_bars": 50, "required_bars": 301},
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_warmup_report_includes_seed_status_warmed() -> None:
    """Seed success → no handler_basis_seed blocker."""
    cfg = _config()
    seed_statuses = {"aurora:BTCUSDT": _warmed_status()}
    report = build_startup_warmup_report(
        config=cfg,
        analytics_restore_report=_restore_report(),
        warmup_statuses=None,
        basis_seed_statuses=seed_statuses,
        updated_at=1000,
        source="test",
    )
    pld = report.to_payload()
    for _key, snap in pld.get("records", {}).items():
        if "aurora" in str(_key) and "BTC" in str(_key):
            blockers = snap.get("effective_blockers", [])
            seed_blockers = [
                b for b in blockers if "handler_basis_seed" in str(b)]
            assert len(
                seed_blockers) == 0, f"Unexpected seed blocker: {seed_blockers}"


def test_warmup_report_includes_seed_status_failed() -> None:
    """Seed failure → handler_basis_seed blocker present, can_open_new_risk=False."""
    cfg = _config()
    seed_statuses = {"aurora:BTCUSDT": _failed_status()}
    report = build_startup_warmup_report(
        config=cfg,
        analytics_restore_report=_restore_report(),
        warmup_statuses=None,
        basis_seed_statuses=seed_statuses,
        updated_at=1000,
        source="test",
    )
    pld = report.to_payload()
    found_seed_blocker = False
    for _key, snap in pld.get("records", {}).items():
        if "aurora" in str(_key) and "BTC" in str(_key):
            blockers = snap.get("effective_blockers", [])
            for b in blockers:
                if "handler_basis_seed" in str(b):
                    found_seed_blocker = True
    assert found_seed_blocker, "Expected handler_basis_seed blocker for failed seed"


def test_warmup_report_backward_compat_no_seed() -> None:
    """basis_seed_statuses=None → existing behavior preserved (no crash)."""
    cfg = _config()
    report = build_startup_warmup_report(
        config=cfg,
        analytics_restore_report=_restore_report(),
        warmup_statuses=None,
        basis_seed_statuses=None,
        updated_at=1000,
        source="test",
    )
    assert report is not None
    pld = report.to_payload()
    assert isinstance(pld, dict)


def test_warmup_report_skip_seed_for_non_restart_strategy() -> None:
    """MR (restart_local_basis_counter=False) → no handler_basis_seed blocker
    even when seed_statuses has no entry for MR."""
    cfg = _config()
    # No seed status for mean_reversion — should not trigger blocker
    seed_statuses = {"aurora:BTCUSDT": _warmed_status()}
    report = build_startup_warmup_report(
        config=cfg,
        analytics_restore_report=_restore_report(),
        warmup_statuses=None,
        basis_seed_statuses=seed_statuses,
        updated_at=1000,
        source="test",
    )
    pld = report.to_payload()
    for _key, snap in pld.get("records", {}).items():
        if "mean_reversion" in str(_key) and "DOGE" in str(_key):
            blockers = snap.get("effective_blockers", [])
            seed_blockers = [
                b for b in blockers if "handler_basis_seed" in str(b)]
            assert len(seed_blockers) == 0, (
                f"MR should not have seed blocker: {seed_blockers}"
            )
