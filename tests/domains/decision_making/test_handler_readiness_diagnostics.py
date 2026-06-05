"""
Phase 7: Handler Readiness Diagnostics — bars_seen and basis_required in output.

Verifies:
1. aurora get_readiness_diagnostics() includes bars_seen and bars_required
2. md_amr get_readiness_diagnostics() includes bars_seen and bars_required
3. bars_seen reflects actual counter from _bars_seen_since_restart
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_aurora_handler(bars_seen: dict | None = None) -> AuroraHandler:
    handler = object.__new__(AuroraHandler)
    handler.logger = logging.getLogger("tests.aurora.diagnostics")
    handler.strategy_id = "aurora"
    handler.timeframe_sec = 300
    handler.config = SimpleNamespace()
    handler._enabled_symbols = {"BTCUSDT"}
    handler._bars_seen_since_restart = bars_seen or {"BTCUSDT": 42}
    return handler


def _make_md_amr_handler(bars_seen: dict | None = None) -> MDAMRHandler:
    handler = object.__new__(MDAMRHandler)
    handler.logger = logging.getLogger("tests.md_amr.diagnostics")
    handler.mlog = logging.getLogger("tests.md_amr.diagnostics")
    handler.config = SimpleNamespace()
    handler._cfg = SimpleNamespace(
        timeframe_sec=900,
        llm_gate=SimpleNamespace(
            enabled=False, sentiment_block_threshold=0.0, block_ttl_sec=0),
    )
    handler._enabled_symbols = {"ETHUSDT"}
    handler._bars_seen_since_restart = bars_seen or {"ETHUSDT": 15}
    return handler


def _mock_profile(basis_required: int = 301):
    return SimpleNamespace(
        basis_required_bars=basis_required,
        restart_local_basis_counter=True,
        needs_regime=True,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_aurora_diagnostics_includes_bars_seen() -> None:
    """aurora diagnostics must include bars_seen and bars_required."""
    handler = _make_aurora_handler(bars_seen={"BTCUSDT": 150})

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=_mock_profile(basis_required=301),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    diag = results[0]
    assert diag["bars_seen"] == 150
    assert diag["bars_required"] == 301
    assert diag["ready"] is False  # 150 < 301


def test_md_amr_diagnostics_includes_bars_seen() -> None:
    """md_amr diagnostics must include bars_seen and bars_required."""
    handler = _make_md_amr_handler(bars_seen={"ETHUSDT": 96})

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=_mock_profile(basis_required=96),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    diag = results[0]
    assert diag["bars_seen"] == 96
    assert diag["bars_required"] == 96
    assert diag["ready"] is True  # 96 >= 96


def test_aurora_diagnostics_after_full_seed() -> None:
    """After seed with 301 bars, diagnostics reports ready=True."""
    handler = _make_aurora_handler(bars_seen={"BTCUSDT": 301})

    with patch(
        "apps.reference.contracts.strategy_compatibility_matrix.get_active_strategy_profile",
        return_value=_mock_profile(basis_required=301),
    ):
        results = handler.get_readiness_diagnostics()

    assert len(results) == 1
    diag = results[0]
    assert diag["bars_seen"] == 301
    assert diag["bars_required"] == 301
    assert diag["ready"] is True
