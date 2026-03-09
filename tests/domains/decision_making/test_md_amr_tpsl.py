"""
MD-AMR-TPSL-01: Unit tests for regime-based TP/SL computation in MDAMRHandler.

Tests are isolated — no real FSM, no real config loader.
Handler instance is created via object.__new__ to bypass __init__.
"""
from __future__ import annotations

import types
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRSignal
from vfoundation.core.protocol import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler() -> MDAMRHandler:
    """Return a bare MDAMRHandler with minimal state — no __init__ call."""
    h = object.__new__(MDAMRHandler)
    h.logger = MagicMock()
    h.mlog = MagicMock()
    h.fsm = MagicMock()
    h.config = MagicMock()
    h._enabled = True
    h._enabled_symbols = {"BTCUSDT", "ETHUSDT", "DOGEUSDT"}
    h._cfg = MagicMock()
    h._strategies = {}
    h._last_features = {}
    h._position_qty = {}
    h._bars_held = {}
    h._deferred = {}
    h._macro_block_until_ms = {}
    h._regime = {}
    h._rest_hydrated = False
    h._rest_last_bar_ts_ms = {}
    h._last_ingested_bar_ts_ms = {}
    h._pending_close = {}
    h._last_close_ts = {}
    h._gtx_retries = {}
    h._entries_at_ts = {}
    h.mandatory_warmup_until = 0
    h._timeframe_sec = 900
    return h


def _btc_asset_cfg() -> types.SimpleNamespace:
    """Simulates MDAMRAssetConfig for BTCUSDT with exit/regime_tpsl."""
    tpsl_cfg = types.SimpleNamespace(
        enabled=True,
        mode="pct_mult",
        sl_mult={"DEFAULT": 1.0, "LOW_VOLATILITY": 0.80, "HIGH_VOLATILITY": 1.30,
                 "TREND_UP": 1.00, "TREND_DOWN": 1.00},
        tp_mult={"DEFAULT": 1.5, "LOW_VOLATILITY": 1.50, "HIGH_VOLATILITY": 1.60,
                 "TREND_UP": 3.50, "TREND_DOWN": 3.50},
        min_sl_pct=0.003,
        max_sl_pct=0.060,
        min_tp_rr=0.5,
        max_tp_rr=5.0,
        min_dist_bps=15,
    )
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.005, tp_rr=1.0, regime_tpsl=tpsl_cfg)
    return types.SimpleNamespace(exit=exit_cfg, cooldown_sec=60)


def _eth_asset_cfg() -> types.SimpleNamespace:
    """Simulates MDAMRAssetConfig for ETHUSDT with exit/regime_tpsl."""
    tpsl_cfg = types.SimpleNamespace(
        enabled=True,
        mode="pct_mult",
        sl_mult={"DEFAULT": 1.0, "FLAT_LOW": 0.65, "LOW_VOLATILITY": 0.70,
                 "FLAT_NORMAL": 0.80, "MEAN_REVERSION": 0.90, "TREND_UP": 1.05,
                 "TREND_DOWN": 1.05, "HIGH_VOLATILITY": 1.30, "UNCERTAIN": 1.00},
        tp_mult={"DEFAULT": 1.0, "FLAT_LOW": 0.70, "LOW_VOLATILITY": 0.75,
                 "FLAT_NORMAL": 0.85, "MEAN_REVERSION": 0.80, "TREND_UP": 1.20,
                 "TREND_DOWN": 1.20, "HIGH_VOLATILITY": 1.60, "UNCERTAIN": 1.00},
        min_sl_pct=0.002,
        max_sl_pct=0.015,
        min_tp_rr=0.3,
        max_tp_rr=3.5,
        min_dist_bps=12,
    )
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.019, tp_rr=0.4, regime_tpsl=tpsl_cfg)
    return types.SimpleNamespace(exit=exit_cfg, cooldown_sec=60)


def _doge_asset_cfg() -> types.SimpleNamespace:
    """Simulates MDAMRAssetConfig for DOGEUSDT (averaged values)."""
    tpsl_cfg = types.SimpleNamespace(
        enabled=True,
        mode="pct_mult",
        sl_mult={"DEFAULT": 1.00, "FLAT_LOW": 0.62, "LOW_VOLATILITY": 0.72,
                 "FLAT_NORMAL": 0.78, "MEAN_REVERSION": 0.88,
                 "TREND_UP": 1.07, "TREND_DOWN": 1.07,
                 "HIGH_VOLATILITY": 1.30, "UNCERTAIN": 1.00},
        tp_mult={"DEFAULT": 1.20, "FLAT_LOW": 0.68, "LOW_VOLATILITY": 1.00,
                 "FLAT_NORMAL": 0.85, "MEAN_REVERSION": 0.78,
                 "TREND_UP": 2.00, "TREND_DOWN": 2.00,
                 "HIGH_VOLATILITY": 1.60, "UNCERTAIN": 1.00},
        min_sl_pct=0.0025,
        max_sl_pct=0.030,
        min_tp_rr=0.35,
        max_tp_rr=4.0,
        min_dist_bps=15,
    )
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.013, tp_rr=0.60, regime_tpsl=tpsl_cfg)
    return types.SimpleNamespace(exit=exit_cfg, cooldown_sec=60)


# ---------------------------------------------------------------------------
# Test 1: BUY entry, BTC config, DEFAULT regime
# ---------------------------------------------------------------------------

def test_buy_entry_btc_default_regime():
    h = _make_handler()
    entry = Decimal("50000")
    result = h._compute_tpsl("BTCUSDT", entry, "BUY",
                             "DEFAULT", _btc_asset_cfg())

    assert result is not None
    stop = result["stop_price"]
    target = result["target_price"]
    assert stop < entry, "stop must be below entry for BUY"
    assert target > entry, "target must be above entry for BUY"

    ctx = result["tpsl_ctx"]
    assert ctx["mode"] == "pct_mult"
    assert ctx["regime_used"] == "DEFAULT"
    # DEFAULT: sl_mult=1.0, tp_mult=1.5 → sl_pct_eff=0.005, tp_rr_eff=1.5
    assert abs(ctx["sl_pct_eff"] - 0.005) < 1e-9
    assert abs(ctx["tp_rr_eff"] - 1.5) < 1e-9
    # stop = 50000 * (1 - 0.005) = 49750
    assert abs(float(stop) - 49750.0) < 0.01
    # target = 50000 * (1 + 0.005*1.5) = 50375
    assert abs(float(target) - 50375.0) < 0.01


# ---------------------------------------------------------------------------
# Test 2: SELL entry, ETH config, TREND_UP regime
# ---------------------------------------------------------------------------

def test_sell_entry_eth_trend_up():
    h = _make_handler()
    entry = Decimal("3000")
    result = h._compute_tpsl("ETHUSDT", entry, "SELL",
                             "TREND_UP", _eth_asset_cfg())

    assert result is not None
    stop = result["stop_price"]
    target = result["target_price"]
    assert stop > entry, "stop must be above entry for SELL"
    assert target < entry, "target must be below entry for SELL"

    ctx = result["tpsl_ctx"]
    # TREND_UP: sl_mult=1.05, tp_mult=1.20
    assert abs(ctx["sl_pct_eff"] - 0.019 * 1.05) < 1e-9
    assert abs(ctx["tp_rr_eff"] - 0.4 * 1.20) < 1e-9


# ---------------------------------------------------------------------------
# Test 3: No exit config → None
# ---------------------------------------------------------------------------

def test_no_exit_config_returns_none():
    h = _make_handler()
    asset_cfg = types.SimpleNamespace(exit=None)
    result = h._compute_tpsl("BTCUSDT", Decimal(
        "50000"), "BUY", "DEFAULT", asset_cfg)
    assert result is None


# ---------------------------------------------------------------------------
# Test 4: regime_tpsl.enabled = False → None
# ---------------------------------------------------------------------------

def test_regime_tpsl_disabled_returns_none():
    h = _make_handler()
    tpsl_cfg = types.SimpleNamespace(enabled=False)
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.005, tp_rr=1.0, regime_tpsl=tpsl_cfg)
    asset_cfg = types.SimpleNamespace(exit=exit_cfg)
    result = h._compute_tpsl("BTCUSDT", Decimal(
        "50000"), "BUY", "DEFAULT", asset_cfg)
    assert result is None


# ---------------------------------------------------------------------------
# Test 5: Guardrail — SL clamped UP to min_sl_pct
# ---------------------------------------------------------------------------

def test_guardrail_sl_clamp_min():
    h = _make_handler()
    # sl_pct = 0.0001 → sl_pct_eff = 0.0001 (below min_sl_pct=0.003)
    tpsl_cfg = types.SimpleNamespace(
        enabled=True,
        sl_mult={"DEFAULT": 1.0},
        tp_mult={"DEFAULT": 2.0},
        min_sl_pct=0.003,
        max_sl_pct=0.060,
        min_tp_rr=0.3,
        max_tp_rr=5.0,
        min_dist_bps=5,
    )
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.0001, tp_rr=2.0, regime_tpsl=tpsl_cfg)
    asset_cfg = types.SimpleNamespace(exit=exit_cfg)
    entry = Decimal("10000")
    result = h._compute_tpsl("BTCUSDT", entry, "BUY", "DEFAULT", asset_cfg)

    assert result is not None
    sl_dist = float((entry - result["stop_price"]) / entry)
    assert sl_dist >= 0.003 - \
        1e-9, f"SL dist {sl_dist:.6f} should be >= min_sl_pct 0.003"
    assert result["tpsl_ctx"].get("guardrail_sl_clamp") == "min"


# ---------------------------------------------------------------------------
# Test 6: Guardrail — SL clamped DOWN to max_sl_pct
# ---------------------------------------------------------------------------

def test_guardrail_sl_clamp_max():
    h = _make_handler()
    # sl_pct = 0.10 → sl_pct_eff = 0.10 (above max_sl_pct=0.060)
    tpsl_cfg = types.SimpleNamespace(
        enabled=True,
        sl_mult={"DEFAULT": 1.0},
        tp_mult={"DEFAULT": 1.5},
        min_sl_pct=0.003,
        max_sl_pct=0.060,
        min_tp_rr=0.3,
        max_tp_rr=5.0,
        min_dist_bps=5,
    )
    exit_cfg = types.SimpleNamespace(
        sl_pct=0.10, tp_rr=1.5, regime_tpsl=tpsl_cfg)
    asset_cfg = types.SimpleNamespace(exit=exit_cfg)
    entry = Decimal("10000")
    result = h._compute_tpsl("BTCUSDT", entry, "BUY", "DEFAULT", asset_cfg)

    assert result is not None
    sl_dist = float((entry - result["stop_price"]) / entry)
    assert sl_dist <= 0.060 + \
        1e-9, f"SL dist {sl_dist:.6f} should be <= max_sl_pct 0.060"
    assert result["tpsl_ctx"].get("guardrail_sl_clamp") == "max"


# ---------------------------------------------------------------------------
# Test 7: Non-ENTRY intent → no tpsl injected in payload
# ---------------------------------------------------------------------------

def _make_signal(intent_kind: str = "FULL_CLOSE") -> MDAMRSignal:
    return MDAMRSignal(
        intent_kind=intent_kind,
        side="SELL",
        reason_code="MAX_HOLD_BARS",
        signal_score=-0.8,
        conf_ratio=0.9,
        scaleout_fraction=None,
        price_ref=Decimal("50000"),
        channel_state={"upper": 51000.0, "lower": 49000.0, "mid": 50000.0},
        atr=250.0,
        dir_score=-0.5,
        trace={},
    )


def test_non_entry_intent_no_tpsl():
    """FULL_CLOSE signal must NOT inject stop_price/target_price into payload."""
    h = _make_handler()

    # Set up a mock strategy that returns a FULL_CLOSE signal
    mock_strategy = MagicMock()
    signal = _make_signal(intent_kind="FULL_CLOSE")
    mock_strategy.on_bar.return_value = {"status": "SIGNAL", "signal": signal}
    h._strategies["BTCUSDT"] = mock_strategy

    # Position is open so FULL_CLOSE is reachable
    h._position_qty["BTCUSDT"] = Decimal("0.1")
    h._bars_held["BTCUSDT"] = 5

    # warmup is done (mandatory_warmup_until=0 <  now_ms which is >> 0)
    # We need mandatory_warmup_until to be in the past
    h.mandatory_warmup_until = 0

    # Set up cfg mock for concentration_guard, llm_gate, etc.
    h._cfg.timeframe_sec = 900  # property reads this; MagicMock default would return 1
    h._cfg.llm_gate = types.SimpleNamespace(enabled=False)
    h._cfg.concentration_guard = types.SimpleNamespace(enabled=False)
    h._cfg.assets = {"BTCUSDT": _btc_asset_cfg()}
    h._cfg.defer_ttl_sec = 60
    h._enabled_symbols = {"BTCUSDT"}
    h._last_ingested_bar_ts_ms["BTCUSDT"] = 0

    # Build a fake CMD:PROCESS_STRATEGY event
    bar_ts = 1_700_000_000_000  # some past timestamp
    event_pld = {
        "symbol": "BTCUSDT",
        "tf_sec": 900,
        "bar": {
            "open": "50100", "high": "50200", "low": "49900", "close": "50000",
            "volume": "10", "start_ts_ms": bar_ts - 900_000, "end_ts_ms": bar_ts,
        },
        "bar_close_ts": bar_ts,
        "features": {},
        "warmup": {"full_ready": True},
    }
    event = MagicMock()
    event.pld = event_pld

    h._on_process_strategy(event)

    # fsm.emit should have been called
    assert h.fsm.emit.called, "fsm.emit should have been called"
    call_args = h.fsm.emit.call_args
    # emit(event_name, payload=payload, ...) → keyword arg
    payload = call_args.kwargs.get("payload")
    if payload is None:
        # fallback: positional (event_name, payload_dict)
        pos = call_args.args
        payload = pos[1] if len(pos) > 1 else None

    assert payload is not None, "payload should not be None"
    price_ctx = payload.get("price_ctx", {})
    assert "stop_price" not in price_ctx, \
        f"stop_price must NOT be in price_ctx for FULL_CLOSE, got: {price_ctx}"
    assert "target_price" not in price_ctx, \
        f"target_price must NOT be in price_ctx for FULL_CLOSE, got: {price_ctx}"


# ---------------------------------------------------------------------------
# Test 8: DOGE averaged config, MEAN_REVERSION regime
# ---------------------------------------------------------------------------

def test_doge_averaged_config():
    h = _make_handler()
    entry = Decimal("0.15000")
    result = h._compute_tpsl("DOGEUSDT", entry, "BUY",
                             "MEAN_REVERSION", _doge_asset_cfg())

    assert result is not None
    ctx = result["tpsl_ctx"]
    # MEAN_REVERSION: sl_mult=0.88, tp_mult=0.78
    expected_sl_mult = 0.88
    expected_tp_mult = 0.78
    assert abs(ctx["sl_mult"] - expected_sl_mult) < 1e-9
    assert abs(ctx["tp_mult"] - expected_tp_mult) < 1e-9

    # sl_pct_eff = 0.013 * 0.88 = 0.01144
    # tp_rr_eff = 0.60 * 0.78 = 0.468
    expected_sl_eff = 0.013 * 0.88
    expected_tp_rr_eff = 0.60 * 0.78
    assert abs(ctx["sl_pct_eff"] - expected_sl_eff) < 1e-9
    assert abs(ctx["tp_rr_eff"] - expected_tp_rr_eff) < 1e-9

    # stop < entry (BUY)
    assert result["stop_price"] < entry
    # target > entry (BUY)
    assert result["target_price"] > entry
