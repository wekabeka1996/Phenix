"""
Phase 5: MR Liquidity Gate — fail-closed return instead of RuntimeError.

Verifies:
1. Missing kappa → returns False (not raises)
2. kappa < kappa_min → returns False
3. kappa >= kappa_min → returns True
4. Gate disabled → returns True regardless of kappa
"""
from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.strategies.runtimes.mean_reversion.handler import MeanReversionHandler


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_mr_handler(
    gate_enabled: bool = True,
    kappa_min: float = 0.5,
) -> MeanReversionHandler:
    """Build a minimal MR handler with configurable liquidity gate."""
    handler = object.__new__(MeanReversionHandler)
    handler.logger = logging.getLogger("test.mr.liquidity_gate")
    handler._liquidity_kappa_map = {}
    handler._mr_config = SimpleNamespace(
        liquidity_gate=SimpleNamespace(
            enabled=gate_enabled,
            kappa_min=kappa_min,
        ),
        assets=SimpleNamespace(get=lambda sym: None),
    )
    # Give assets a dict-like .get
    handler._mr_config.assets = {}
    return handler


# ── tests ─────────────────────────────────────────────────────────────────────

def test_kappa_none_returns_false_not_raises() -> None:
    """Missing kappa → returns False (fail-closed), no RuntimeError."""
    handler = _make_mr_handler(gate_enabled=True, kappa_min=0.5)
    # kappa not in cache
    result = handler._check_liquidity_gate("DOGEUSDT")
    assert result is False


def test_kappa_below_min_returns_false() -> None:
    """kappa < kappa_min → returns False."""
    handler = _make_mr_handler(gate_enabled=True, kappa_min=0.5)
    handler._liquidity_kappa_map["DOGEUSDT"] = Decimal("0.3")
    result = handler._check_liquidity_gate("DOGEUSDT")
    assert result is False


def test_kappa_above_min_returns_true() -> None:
    """kappa >= kappa_min → returns True."""
    handler = _make_mr_handler(gate_enabled=True, kappa_min=0.5)
    handler._liquidity_kappa_map["DOGEUSDT"] = Decimal("0.8")
    result = handler._check_liquidity_gate("DOGEUSDT")
    assert result is True


def test_gate_disabled_always_passes() -> None:
    """gate_cfg.enabled=False → returns True regardless of kappa."""
    handler = _make_mr_handler(gate_enabled=False, kappa_min=0.5)
    # No kappa in cache should still pass
    result = handler._check_liquidity_gate("DOGEUSDT")
    assert result is True
