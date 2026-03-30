"""
SUBPACK-B: End-to-End proof that price_motion flows through _on_process_strategy()
and the microstructure veto fires correctly on the REAL handler path.

These tests exercise the actual _on_process_strategy() entrypoint (not helpers).
The strategy's on_bar() is mocked to return actionable signals so we can isolate
the veto overlay behavior without setting up full Bollinger Band state.

Required proofs:
1. LONG candidate + adverse TFI + adverse continuation => BLOCKED (toxic flow)
2. LONG candidate + adverse TFI + absorption (wick) => ALLOWED past veto
3. SHORT candidate + adverse TFI + adverse continuation => BLOCKED (toxic flow)
4. SHORT candidate + adverse TFI + absorption (wick) => ALLOWED past veto
5. Missing TFI in features => fail-closed block on real path
6. OBI confirm-only semantics on real path
7. price_motion absent from CMD payload => veto still executes (conservative block)
8. Zero-range bar => conservative block on real path
"""
from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

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
        readiness_min_bars=1,
        missing_policy="block",
    )
    base.update(overrides)
    return MRMicrostructureVetoConfig(**base)


def _make_actionable_signal(symbol: str, signal_type_name: str, bar: Any):
    """Build a minimal MRSignal-like object that is_signal=True."""
    from apps.reference.domains.decision_making.strategy_bridge import (
        MRSignal, MRSignalType,
    )
    sig_type = MRSignalType.LONG if signal_type_name == "LONG" else MRSignalType.SHORT
    return MRSignal(
        signal_type=sig_type,
        symbol=symbol,
        price=bar.close,
        bar=bar,
        timestamp_ms=1000000,
        why=f"e2e_test_{signal_type_name.lower()}",
    )


class _FakeFSM:
    """Minimal FSM mock that records emitted events."""

    def __init__(self):
        self.emitted: List[tuple] = []

    def emit(self, event_type: str, payload: Any = None, **kwargs):
        self.emitted.append((event_type, payload, kwargs))


def _build_e2e_handler(
    symbol: str = "DOGEUSDT",
    veto_cfg: MRMicrostructureVetoConfig | None = None,
    tfi_ema_init: float | None = None,
    tfi_bar_count: int = 10,
) -> tuple[MeanReversionHandler, _FakeFSM]:
    """Build a minimal handler via object.__new__ with enough state for _on_process_strategy."""
    handler = object.__new__(MeanReversionHandler)
    handler.logger = logging.getLogger("test.mr.e2e_price_motion")
    handler.mlog = logging.getLogger("test.mr.e2e_price_motion.mlog")
    handler.bar_logger = None  # skip _log_bar

    fsm = _FakeFSM()
    handler.fsm = fsm

    handler._enabled = True
    handler.timeframe_sec = 60
    handler._enabled_symbols = {symbol}
    handler._per_symbol_regime = {}
    handler._regime_ts_ms = {}
    handler._regime_confidence = {}

    handler._stats = {
        "ticks_seen": 0,
        "ticks_dropped_missing_ts": 0,
        "ticks_dropped_out_of_order": 0,
        "ticks_dropped_invalid_price": 0,
        "bars_completed": 0,
        "signals_emitted": 0,
        "neutral_bars": 0,
        "bar_logging_errors": 0,
        "tick_processing_errors": 0,
        "regime_processing_errors": 0,
        "bars_received": 0,
        "bars_rejected_wrong_tf": 0,
        "bars_rejected_missing_tf": 0,
        "bars_rejected_missing_bar": 0,
    }

    # Features/price_motion caches — populated by CMD payload during test
    handler._last_cmd_features = {}
    handler._last_cmd_price_motion = {}

    # Liquidity kappa
    handler._liquidity_kappa_map = {}

    # Microstructure veto state
    handler._tfi_ema = {}
    handler._tfi_bar_count = {}
    handler._microstructure_veto_configs = {}
    if veto_cfg is not None:
        handler._microstructure_veto_configs[symbol] = veto_cfg

    if tfi_ema_init is not None:
        handler._tfi_ema[symbol] = tfi_ema_init
        handler._tfi_bar_count[symbol] = tfi_bar_count

    # Directional bias — disabled for veto-only tests
    handler._directional_bias_configs = {}
    handler._funding_rate = {}

    # Signal tracking
    handler._signal_counts = {}
    handler._last_signal_time = {}

    # Emit throttling
    handler._last_block_reason = {}
    handler._last_block_ts_ms = {}

    # Strategy — will be set per-test with mock
    handler._strategies = {}

    # Analytics restore snapshots (needed by _emit_signal)
    handler._analytics_restore_snapshots = {}

    # Position query (not needed for veto path)
    handler._position_queries = None
    handler._latest_portfolio = None
    handler._latest_exposure_summary = None
    handler._mr_config = None
    handler._last_tick_ts_ms = {}
    handler._last_counted_bar_end_ts_ms = {}
    handler._objective_blocked_ts_ms = {}
    handler._objective_cancel_replace_ts_ms = {}
    handler._objective_reentry_ts_ms = {}
    handler._position_qty = {}
    handler._last_close_ts = {}

    return handler, fsm


def _make_cmd_event(
    symbol: str = "DOGEUSDT",
    tf_sec: int = 60,
    bar_close_ts: int = 1700000000000,
    bar_data: dict | None = None,
    features: dict | None = None,
    price_motion: dict | None = None,
    regime: dict | None = None,
) -> SimpleNamespace:
    """Build a Message-like event with .pld dict for _on_process_strategy."""
    if bar_data is None:
        bar_data = {
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
            "volume": 1000.0, "start_ts_ms": 1700000000000 - 60000,
            "trade_count": 50,
        }
    if features is None:
        features = {}

    pld = {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "bar": bar_data,
        "features": features,
        "warmup": {"full_ready": True},
        "regime": regime,
    }
    if price_motion is not None:
        pld["price_motion"] = price_motion

    return SimpleNamespace(pld=pld)


def _setup_strategy_mock(handler, symbol, signal_to_return):
    """Install a mock strategy that returns the given signal from on_bar()."""
    mock_strategy = MagicMock()
    mock_strategy.on_bar.return_value = signal_to_return
    mock_strategy.get_regime.return_value = "FLAT_NORMAL"
    mock_strategy.set_regime = MagicMock()
    # config needs entry_threshold_long/short for R3 finally block
    mock_strategy.config = SimpleNamespace(
        entry_threshold_long=None,
        entry_threshold_short=None,
        allowed_regimes=["FLAT_NORMAL"],
    )
    handler._strategies[symbol] = mock_strategy
    return mock_strategy


# ── Bar helper (Decimal-based to match real Bar) ─────────────────────────────

def _bar_from_dict(bar_data: dict):
    """Import real Bar type and construct."""
    from apps.reference.shared.types import Bar
    return Bar(
        symbol="DOGEUSDT",
        timeframe_sec=60,
        open=Decimal(str(bar_data.get("open", 0))),
        high=Decimal(str(bar_data.get("high", 0))),
        low=Decimal(str(bar_data.get("low", 0))),
        close=Decimal(str(bar_data.get("close", 0))),
        volume=Decimal(str(bar_data.get("volume", 0))),
        start_ts_ms=bar_data.get("start_ts_ms", 0),
        end_ts_ms=bar_data.get("bar_close_ts", 1700000000000),
        trade_count=bar_data.get("trade_count", 0),
    )


# ============================================================================
# 1. LONG + adverse TFI + adverse continuation => BLOCKED
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_toxic_flow_blocks_long(mock_blocked, mock_rejected):
    """Real _on_process_strategy path: adverse TFI + continuation => LONG blocked."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    bar_data = {"open": 100.0, "high": 100.2, "low": 99.5, "close": 99.6,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "-0.5", "obi": "0.1"},
        price_motion={"ret_10s": -0.001,
                      "ret_60s": -0.002, "ret_300s": -0.003},
        bar_data=bar_data,
    )

    handler._on_process_strategy(event)

    # Veto should have blocked — check that STRATEGY_DECISION_BLOCKED was emitted
    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) >= 1, f"Expected STRATEGY_DECISION_BLOCKED, got: {[e[0] for e in fsm.emitted]}"

    # No EVT:STRATEGY_SIGNAL_PRODUCED should be emitted
    signal_events = [e for e in fsm.emitted if e[0]
                     == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(signal_events) == 0, "Signal should NOT be emitted when veto blocks"


# ============================================================================
# 2. LONG + adverse TFI + absorption (wick) => ALLOWED
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_absorption_allows_long(mock_blocked, mock_rejected):
    """Real _on_process_strategy path: adverse TFI + absorption wick => LONG allowed."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    # Large lower wick: absorption of selling pressure
    bar_data = {"open": 100.2, "high": 101.0, "low": 98.0, "close": 100.5,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    mock_strategy = _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "-0.5", "obi": "0.1"},
        price_motion={"ret_10s": 0.0, "ret_60s": 0.0001, "ret_300s": 0.0},
        bar_data=bar_data,
    )

    # Mock liquidity gate and _emit_signal to isolate veto path
    # (proving veto ALLOWS is the goal — _emit_signal internals tested elsewhere)
    handler._check_liquidity_gate = MagicMock(return_value=True)
    handler._emit_signal = MagicMock()

    handler._on_process_strategy(event)

    # Should NOT be blocked — no STRATEGY_DECISION_BLOCKED
    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) == 0, f"Veto should NOT block absorption, got: {blocked_events}"

    # _emit_signal should be called (signal passed veto + liquidity gate)
    assert handler._emit_signal.called, "Absorption-allowed signal should reach _emit_signal"


# ============================================================================
# 3. SHORT + adverse TFI + adverse continuation => BLOCKED
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_toxic_flow_blocks_short(mock_blocked, mock_rejected):
    """Real _on_process_strategy path: adverse TFI + continuation => SHORT blocked."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=0.4)

    bar_data = {"open": 100.0, "high": 100.8, "low": 100.0, "close": 100.7,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "SHORT", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "0.5", "obi": "-0.1"},
        price_motion={"ret_10s": 0.001, "ret_60s": 0.002, "ret_300s": 0.003},
        bar_data=bar_data,
    )

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) >= 1, f"Expected SHORT blocked, got: {[e[0] for e in fsm.emitted]}"

    signal_events = [e for e in fsm.emitted if e[0]
                     == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(
        signal_events) == 0, "Signal should NOT be emitted when SHORT veto blocks"


# ============================================================================
# 4. SHORT + adverse TFI + absorption (wick) => ALLOWED
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_absorption_allows_short(mock_blocked, mock_rejected):
    """Real _on_process_strategy path: adverse TFI + absorption wick => SHORT allowed."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=0.4)

    # Large upper wick: absorption of buying pressure
    bar_data = {"open": 100.2, "high": 103.0, "low": 99.5, "close": 100.0,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "SHORT", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "0.5", "obi": "-0.1"},
        price_motion={"ret_10s": 0.0, "ret_60s": -0.0001, "ret_300s": 0.0},
        bar_data=bar_data,
    )

    handler._check_liquidity_gate = MagicMock(return_value=True)
    handler._emit_signal = MagicMock()

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(blocked_events) == 0, "Absorption should allow SHORT signal"

    assert handler._emit_signal.called, "Absorption-allowed SHORT signal should reach _emit_signal"


# ============================================================================
# 5. Missing TFI => fail-closed on real path
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_missing_tfi_fail_closed(mock_blocked, mock_rejected):
    """Real path: no TFI in features => microstructure veto blocks unconditionally."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg)

    bar_data = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    # Features WITHOUT tfi
    event = _make_cmd_event(
        features={"obi": "0.1"},
        price_motion={"ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0},
        bar_data=bar_data,
    )

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(blocked_events) >= 1, "Missing TFI must trigger fail-closed block"

    signal_events = [e for e in fsm.emitted if e[0]
                     == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(signal_events) == 0


# ============================================================================
# 6. OBI confirm-only semantics on real path
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_obi_confirm_only_allows(mock_blocked, mock_rejected):
    """Real path: adverse TFI but non-adverse OBI => OBI doesn't confirm => ALLOWED."""
    cfg = _valid_veto_cfg(obi_confirm_enabled=True)
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    bar_data = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    # TFI adverse, OBI NOT adverse (positive for LONG)
    event = _make_cmd_event(
        features={"tfi": "-0.5", "obi": "0.1"},
        price_motion={"ret_10s": -0.001,
                      "ret_60s": -0.002, "ret_300s": -0.003},
        bar_data=bar_data,
    )

    handler._check_liquidity_gate = MagicMock(return_value=True)
    handler._emit_signal = MagicMock()

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) == 0, "Non-adverse OBI should NOT confirm toxic flow"

    assert handler._emit_signal.called, "OBI-unconfirmed signal should reach _emit_signal"


@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_obi_confirms_blocks(mock_blocked, mock_rejected):
    """Real path: adverse TFI + adverse OBI + continuation => BLOCKED."""
    cfg = _valid_veto_cfg(obi_confirm_enabled=True)
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    bar_data = {"open": 100.0, "high": 100.1, "low": 99.3, "close": 99.4,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "-0.5", "obi": "-0.5"},
        price_motion={"ret_10s": -0.001,
                      "ret_60s": -0.002, "ret_300s": -0.003},
        bar_data=bar_data,
    )

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) >= 1, "Both TFI and OBI adverse + continuation should block"


# ============================================================================
# 7. price_motion absent from CMD => conservative block on adverse TFI
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_missing_price_motion_conservative_block(mock_blocked, mock_rejected):
    """Real path: no price_motion in CMD => no continuation/rebound info => ambiguous block."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    # Bar with no significant wicks either (no absorption evidence)
    bar_data = {"open": 100.0, "high": 100.2, "low": 99.8, "close": 99.9,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    # NO price_motion in event payload
    event = _make_cmd_event(
        features={"tfi": "-0.5"},
        price_motion=None,  # explicitly absent
        bar_data=bar_data,
    )

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) >= 1, "Missing price_motion + adverse TFI => ambiguous block"


# ============================================================================
# 8. Zero-range bar => conservative block on real path
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_zero_range_bar_blocks(mock_blocked, mock_rejected):
    """Real path: zero-range bar (high == low) + adverse TFI => ZERO_RANGE block."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    bar_data = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "-0.5"},
        price_motion={"ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0},
        bar_data=bar_data,
    )

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(
        blocked_events) >= 1, "Zero-range bar must trigger conservative block"


# ============================================================================
# 9. price_motion cached in dedicated _last_cmd_price_motion (not features)
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_price_motion_cached_in_dedicated_dict(mock_blocked, mock_rejected):
    """Prove price_motion is cached in handler._last_cmd_price_motion, NOT in features."""
    cfg = _valid_veto_cfg()
    handler, fsm = _build_e2e_handler(veto_cfg=cfg, tfi_ema_init=-0.4)

    bar_data = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    pm = {"ret_10s": 0.001, "ret_60s": 0.001, "ret_300s": 0.001}
    event = _make_cmd_event(
        features={"tfi": "-0.5"},
        price_motion=pm,
        bar_data=bar_data,
    )

    handler._check_liquidity_gate = MagicMock(return_value=True)

    handler._on_process_strategy(event)

    # Verify price_motion landed in dedicated cache
    assert "DOGEUSDT" in handler._last_cmd_price_motion
    cached_pm = handler._last_cmd_price_motion["DOGEUSDT"]
    assert cached_pm.get("ret_60s") == 0.001

    # Verify features dict does NOT contain price_motion
    cached_features = handler._last_cmd_features.get("DOGEUSDT", {})
    assert "price_motion" not in cached_features


# ============================================================================
# 10. Veto disabled => signal passes through unimpeded on real path
# ============================================================================

@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_trade_intent_rejected")
@patch("apps.reference.domains.decision_making.mean_reversion_handler.write_strategy_decision_blocked")
def test_e2e_veto_disabled_passes(mock_blocked, mock_rejected):
    """Real path: no veto config for symbol => signal emitted without veto."""
    handler, fsm = _build_e2e_handler(veto_cfg=None)

    bar_data = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
                "volume": 1000, "start_ts_ms": 1699999940000, "trade_count": 50}
    bar_obj = _bar_from_dict(bar_data)
    signal = _make_actionable_signal("DOGEUSDT", "LONG", bar_obj)
    _setup_strategy_mock(handler, "DOGEUSDT", signal)

    event = _make_cmd_event(
        features={"tfi": "-0.8"},  # Would be very adverse, but veto disabled
        price_motion={"ret_10s": -0.005, "ret_60s": -0.01, "ret_300s": -0.02},
        bar_data=bar_data,
    )

    handler._check_liquidity_gate = MagicMock(return_value=True)
    handler._emit_signal = MagicMock()

    handler._on_process_strategy(event)

    blocked_events = [e for e in fsm.emitted if e[0]
                      == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert len(blocked_events) == 0, "Disabled veto should not block"

    assert handler._emit_signal.called, "Signal should reach _emit_signal when veto disabled"
