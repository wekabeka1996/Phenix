"""
PACK-3 Validation: Vector 1 Microstructure Veto — behavioral tests at MR handler level.

Required tests (from spec):
1. toxic_flow_down blocks LONG
2. toxic_flow_up blocks SHORT
3. absorption_long allows
4. absorption_short allows
5. missing_tfi fail-closed
6. missing_obi fail-closed when confirm enabled
7. ema warmup not_ready block
8. OBI confirm-only semantics
Plus additional edge cases.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from apps.reference.config_models import MRMicrostructureVetoConfig
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler


# ── Helpers ──────────────────────────────────────────────────────────────────

def _valid_veto_cfg(**overrides) -> MRMicrostructureVetoConfig:
    base = dict(
        enabled=True,
        tfi_ema_span=5,
        tfi_adverse_threshold=0.3,
        obi_confirm_enabled=False,
        obi_adverse_threshold=0.3,
        price_reaction_lookback_sec=60,
        price_continuation_threshold=0.001,
        absorption_wick_ratio_min=0.4,
        absorption_rebound_threshold=0.0005,
        readiness_min_bars=1,  # 1 for easier testing
        missing_policy="block",
    )
    base.update(overrides)
    return MRMicrostructureVetoConfig(**base)


def _make_handler(
    symbol: str = "DOGEUSDT",
    veto_cfg: MRMicrostructureVetoConfig | None = None,
    features: Dict[str, Any] | None = None,
    tfi_ema_init: float | None = None,
    tfi_bar_count: int = 10,
) -> MeanReversionHandler:
    """Build minimal MR handler for microstructure veto testing."""
    handler = object.__new__(MeanReversionHandler)
    handler.logger = logging.getLogger("test.mr.microstructure_veto")
    handler._last_cmd_features = {}
    handler._tfi_ema = {}
    handler._tfi_bar_count = {}
    handler._microstructure_veto_configs = {}

    if veto_cfg is not None:
        handler._microstructure_veto_configs[symbol] = veto_cfg

    if features is not None:
        handler._last_cmd_features[symbol] = features

    if tfi_ema_init is not None:
        handler._tfi_ema[symbol] = tfi_ema_init
        handler._tfi_bar_count[symbol] = tfi_bar_count

    return handler


def _make_bar(
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
) -> SimpleNamespace:
    return SimpleNamespace(open=open_, high=high, low=low, close=close)


# ── 1. toxic_flow_down blocks LONG ──────────────────────────────────────────

def test_toxic_flow_down_blocks_long():
    """Strongly negative TFI + adverse price continuation → LONG blocked."""
    cfg = _valid_veto_cfg()
    # TFI = -0.5 (strong selling), price dropped (ret_60s = -0.002 = continuation)
    features = {
        "tfi": "-0.5",
        "price_motion": {"ret_60s": -0.002},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,  # already adverse
    )
    bar = _make_bar(open_=100.0, high=100.2, low=99.5, close=99.6)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "TOXIC_FLOW" in reason


# ── 2. toxic_flow_up blocks SHORT ───────────────────────────────────────────

def test_toxic_flow_up_blocks_short():
    """Strongly positive TFI + adverse price continuation → SHORT blocked."""
    cfg = _valid_veto_cfg()
    # TFI = +0.5 (strong buying), price rose (ret_60s = +0.002 = continuation)
    features = {
        "tfi": "0.5",
        "price_motion": {"ret_60s": 0.002},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=0.4,
    )
    bar = _make_bar(open_=100.0, high=100.8, low=100.0, close=100.7)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "SHORT", bar)
    assert allowed is False
    assert "TOXIC_FLOW" in reason


# ── 3. absorption_long allows ───────────────────────────────────────────────

def test_absorption_long_allows():
    """Selling pressure absorbed (large lower wick) → LONG allowed."""
    cfg = _valid_veto_cfg()
    # TFI = -0.5 (selling pressure) but bar shows absorption (big lower wick)
    features = {
        "tfi": "-0.5",
        "price_motion": {"ret_60s": 0.0001},  # tiny, not continuation
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,
    )
    # Large lower wick: low=98, close=100.5, high=101, open=100.2
    # Lower wick = min(100.2, 100.5) - 98 = 2.2, range = 101-98 = 3.0, ratio = 0.73
    bar = _make_bar(open_=100.2, high=101.0, low=98.0, close=100.5)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is True


# ── 4. absorption_short allows ──────────────────────────────────────────────

def test_absorption_short_allows():
    """Buying pressure absorbed (large upper wick) → SHORT allowed."""
    cfg = _valid_veto_cfg()
    # TFI = +0.5 (buying pressure) but bar shows absorption (big upper wick)
    features = {
        "tfi": "0.5",
        "price_motion": {"ret_60s": -0.0001},  # tiny, not continuation
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=0.4,
    )
    # Large upper wick: high=103, open=100.2, close=100.0, low=99.5
    # Upper wick = 103 - max(100.2, 100.0) = 2.8, range = 103-99.5 = 3.5, ratio = 0.8
    bar = _make_bar(open_=100.2, high=103.0, low=99.5, close=100.0)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "SHORT", bar)
    assert allowed is True


# ── 5. missing_tfi fail-closed ──────────────────────────────────────────────

def test_missing_tfi_blocks_when_policy_block():
    """Missing TFI in features → fail-closed (block) when missing_policy='block'."""
    cfg = _valid_veto_cfg(missing_policy="block")
    features = {"obi": "0.1"}  # TFI absent
    handler = _make_handler(veto_cfg=cfg, features=features)
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "TFI_MISSING" in reason


def test_missing_tfi_allows_when_policy_skip():
    """Missing TFI → allowed when missing_policy='skip' (fail-open)."""
    cfg = _valid_veto_cfg(missing_policy="skip")
    features = {"obi": "0.1"}  # TFI absent
    handler = _make_handler(veto_cfg=cfg, features=features)
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is True


# ── 6. missing_obi fail-closed when confirm enabled ────────────────────────

def test_missing_obi_blocks_when_confirm_enabled():
    """Missing OBI + obi_confirm_enabled=True → fail-closed."""
    cfg = _valid_veto_cfg(obi_confirm_enabled=True)
    # TFI is adverse, OBI is missing
    features = {
        "tfi": "-0.5",
        # no "obi" key
        "price_motion": {"ret_60s": -0.002},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,
    )
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "OBI_MISSING" in reason


# ── 7. ema warmup not_ready block ──────────────────────────────────────────

def test_warmup_not_ready_blocks():
    """Fewer bars than readiness_min_bars → NOT_READY block."""
    cfg = _valid_veto_cfg(readiness_min_bars=5)
    features = {
        "tfi": "-0.2",
        "price_motion": {"ret_60s": 0.0},
    }
    # Start with NO prior TFI EMA history (first bar)
    handler = _make_handler(veto_cfg=cfg, features=features)
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "NOT_READY" in reason


# ── 8. OBI confirm-only semantics ──────────────────────────────────────────

def test_obi_confirm_only_not_sole_driver():
    """Adverse TFI but non-adverse OBI → allowed (OBI doesn't confirm toxic flow)."""
    cfg = _valid_veto_cfg(obi_confirm_enabled=True)
    # TFI is adverse, but OBI is NOT adverse (positive for LONG direction)
    features = {
        "tfi": "-0.5",
        "obi": "0.1",  # Not adverse (below threshold)
        "price_motion": {"ret_60s": -0.002},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,
    )
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is True  # OBI didn't confirm → not toxic


def test_obi_confirms_adverse_flow_blocks():
    """Adverse TFI + adverse OBI + continuation → blocked."""
    cfg = _valid_veto_cfg(obi_confirm_enabled=True)
    features = {
        "tfi": "-0.5",
        "obi": "-0.5",  # Also adverse for LONG
        "price_motion": {"ret_60s": -0.002},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,
    )
    bar = _make_bar(open_=100.0, high=100.1, low=99.3, close=99.4)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "TOXIC_FLOW" in reason


# ── Additional edge cases ────────────────────────────────────────────────────

def test_non_adverse_tfi_allows():
    """TFI within threshold → allowed (no adverse flow detected)."""
    cfg = _valid_veto_cfg(tfi_adverse_threshold=0.3)
    features = {
        "tfi": "-0.1",  # Below threshold
        "price_motion": {"ret_60s": -0.005},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.1,
    )
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is True


def test_veto_disabled_always_allows():
    """When veto not configured for symbol → always allowed."""
    handler = _make_handler(veto_cfg=None)
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is True
    assert reason == ""


def test_rebound_allows_despite_adverse_tfi():
    """Adverse TFI but favorable price rebound → absorption → allowed."""
    cfg = _valid_veto_cfg()
    # TFI adverse but price rebounding favorably
    features = {
        "tfi": "-0.5",
        "price_motion": {"ret_60s": 0.001},  # >= absorption_rebound_threshold
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,
    )
    bar = _make_bar(open_=99.5, high=100.5, low=99.0, close=100.3)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is True


def test_no_features_cached_blocks():
    """No features cached for symbol → TFI missing → fail-closed."""
    cfg = _valid_veto_cfg(missing_policy="block")
    handler = _make_handler(veto_cfg=cfg, features=None)
    bar = _make_bar()

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "TFI_MISSING" in reason


def test_zero_range_bar_blocks():
    """Zero-range bar (high == low) with adverse TFI → conservative block."""
    cfg = _valid_veto_cfg()
    features = {
        "tfi": "-0.5",
        "price_motion": {"ret_60s": 0.0},
    }
    handler = _make_handler(
        veto_cfg=cfg,
        features=features,
        tfi_ema_init=-0.4,
    )
    bar = _make_bar(open_=100.0, high=100.0, low=100.0, close=100.0)

    allowed, reason = handler._check_microstructure_veto(
        "DOGEUSDT", "LONG", bar)
    assert allowed is False
    assert "ZERO_RANGE" in reason
