"""TICK-BAR-SPLIT-FIX-1: bar bad_dt must fail-closed — no event emitted.

When tf_sec > 0 (bar path) and time_diff <= 0, the handler must:
- increment data quality counters
- log WARNING
- return False
- NOT emit any event (bar=None violates BarFeaturesCalculatedPayloadV1)

Tick bad_dt (tf_sec=0) MUST still emit EVT:TICK_FEATURES_CALCULATED.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class _RecordingFsm:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, *_args, **_kwargs) -> None:
        return

    def emit(self, event_name: str, payload=None, why=None, data_ref=None, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))


def _build_minimal_fe(monkeypatch):
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    with patch.object(FeatureEngineering, "__init__", lambda self, **kw: None):
        fe = FeatureEngineering()

    fe.fsm = _RecordingFsm()
    fe.logger = MagicMock()
    fe.feature_store = None
    fe.cfg = SimpleNamespace(
        enable_new_metrics=True,
        delta_price_spike_filter_ms=5_000,
        depth_half=Decimal("1000"),
        kappa_min=Decimal("0.3"),
        kappa_max=Decimal("1.0"),
        zero_value=Decimal("0"),
        neutral_value=Decimal("0.5"),
        macro_sync_anchor_update_from_ticks=False,
        macro_sync_anchors=[],
        macro_sync_enabled=False,
        macro_resid_enabled=False,
        absorption_mode="disabled",
        large_trade_imbalance_enabled=False,
        futures_enabled=False,
        spread_health_gate_enabled=False,
        compute_warmup_full_ready_for_symbol=lambda symbol, ready_map: all(
            bool(v) for v in ready_map.values()
        ),
    )
    fe._engine = SimpleNamespace(
        sanitize_features_dict=lambda features: (features, {}, []),
    )
    fe.calc_engine = fe._engine
    fe._macro_sync_resampler = MagicMock()
    fe._macro_sync_effective_max_gap_bins = lambda tf_sec=None: 999
    monkeypatch.setattr(
        "apps.reference.domains.feature_engineering.feature_engineering.compute_price_motion_block",
        lambda *args, **kwargs: {
            "ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0,
            "vol_pct_10s": 0.0, "vol_pct_60s": 0.0, "vol_pct_300s": 0.0,
            "pm_norm_10s": 0.0, "pm_norm_60s": 0.0, "pm_norm_300s": 0.0,
        },
    )
    fe._fe_readiness_diag = {}
    fe._anchor_intake_diag = {}
    fe._ticks_seen = defaultdict(int)
    fe._last_tick_ts_ms = 0
    fe._last_obi = {}
    fe._bar_volatility_states = {}
    fe._macro_sync_anchor_ts_missing = False
    fe._anchor_last_ts_ms = {}
    fe.anchor_prices = {}
    fe.anchor_price_points = {}
    fe.symbol_states = {}
    fe.last_regime = {}
    fe._price_motion_sanity_cfg = SimpleNamespace(
        k_vol=1.0,
        pm_norm_clip_abs=10.0,
    )
    fe._compute_pillars_for_emit = lambda **kwargs: None
    fe._try_warmup_seed_atr = lambda *args, **kwargs: None
    fe._log_features_to_file = lambda *args, **kwargs: None
    fe._get_symbol_state = lambda symbol: SimpleNamespace(
        hot=SimpleNamespace(
            price_history=[],
            ema_long=Decimal("1"),
            ema_short=Decimal("1"),
            volume_spike_ready=True,
            volume_spike_not_ready_reason=None,
            volatility_state_ready=True,
            volatility_state_not_ready_reason=None,
            macro_sync_ready=True,
            macro_sync_not_ready_reason=None,
            large_trade_imbalance_ready=True,
            large_trade_imbalance_not_ready_reason=None,
            large_trade_imbalance_trades_used=0,
            large_trade_imbalance_dropped_out_of_order=0,
            macro_resid_ready=True,
            macro_resid_not_ready_reason=None,
            absorption_ready=True,
            absorption_not_ready_reason=None,
            spread_ready=True,
            spread_missing=False,
        ),
        cold=SimpleNamespace(),
    )
    fe._init_symbol_state = lambda symbol: None
    fe._update_ema = lambda *args, **kwargs: None
    fe._compute_ema_bias = lambda *args, **kwargs: Decimal("0")
    fe._update_volume_spike = lambda *args, **kwargs: None
    fe._compute_volume_spike = lambda *args, **kwargs: Decimal("0")
    fe._update_volatility_state = lambda *args, **kwargs: None
    fe._compute_volatility_state = lambda *args, **kwargs: Decimal("0")
    fe._compute_depth_imbalance = lambda *args, **kwargs: Decimal("0")
    fe._compute_macro_sync = lambda *args, **kwargs: Decimal("0")
    fe._compute_volume_zscore = lambda *args, **kwargs: Decimal("0")
    fe._compute_spread_bps = lambda *args, **kwargs: Decimal("0")
    return fe


def _tick(symbol: str, ts: int, price: str) -> dict:
    return {
        "symbol": symbol,
        "ts": ts,
        "price": price,
        "bid_size": "10",
        "ask_size": "10",
        "buy_volume": "5",
        "sell_volume": "5",
        "bid": price,
        "ask": price,
    }


class TestBarBadDtFailClosed:
    """FIX-1: bar bad_dt (tf_sec>0, time_diff<=0) must not emit any event."""

    def test_bar_bad_dt_no_emit(self, monkeypatch):
        """Bar path with identical timestamps must return False and emit nothing."""
        fe = _build_minimal_fe(monkeypatch)
        symbol = "BTCUSDT"
        now_ms = 1_700_000_000_000

        accepted = fe._calculate_and_emit_features_for_tf(
            symbol=symbol,
            tf_sec=300,
            current_tick=_tick(symbol, now_ms, "100.0"),
            last_tick=_tick(symbol, now_ms, "100.0"),  # time_diff=0
            emit_events=True,
        )

        assert accepted is False
        assert len(fe.fsm.emitted) == 0, (
            "bar bad_dt must not emit any event (bar=None violates bar contract)"
        )

    def test_bar_bad_dt_negative_time_diff_no_emit(self, monkeypatch):
        """Bar path with negative time_diff must return False and emit nothing."""
        fe = _build_minimal_fe(monkeypatch)
        symbol = "BTCUSDT"
        now_ms = 1_700_000_000_000

        accepted = fe._calculate_and_emit_features_for_tf(
            symbol=symbol,
            tf_sec=300,
            current_tick=_tick(symbol, now_ms - 500, "100.0"),
            last_tick=_tick(symbol, now_ms, "100.0"),  # time_diff=-500
            emit_events=True,
        )

        assert accepted is False
        assert len(fe.fsm.emitted) == 0

    def test_bar_bad_dt_warning_logged(self, monkeypatch):
        """Bar bad_dt must log a WARNING for observability."""
        fe = _build_minimal_fe(monkeypatch)
        symbol = "BTCUSDT"
        now_ms = 1_700_000_000_000

        fe._calculate_and_emit_features_for_tf(
            symbol=symbol,
            tf_sec=300,
            current_tick=_tick(symbol, now_ms, "100.0"),
            last_tick=_tick(symbol, now_ms, "100.0"),
            emit_events=True,
        )

        assert fe.logger.warning.called, "bar bad_dt must log WARNING"
        call_args = fe.logger.warning.call_args[0][0]
        assert "bar bad_dt fail-closed" in call_args

    def test_tick_bad_dt_still_emits(self, monkeypatch):
        """Tick path (tf_sec=0) bad_dt must STILL emit EVT:TICK_FEATURES_CALCULATED."""
        fe = _build_minimal_fe(monkeypatch)
        symbol = "BTCUSDT"
        now_ms = 1_700_000_000_000

        accepted = fe._calculate_and_emit_features_for_tf(
            symbol=symbol,
            tf_sec=0,
            current_tick=_tick(symbol, now_ms, "100.0"),
            last_tick=_tick(symbol, now_ms, "100.0"),
            emit_events=True,
        )

        assert accepted is False
        assert len(fe.fsm.emitted) == 1, "tick bad_dt must still emit"
        event_name, payload, why, _ = fe.fsm.emitted[0]
        assert event_name == "EVT:TICK_FEATURES_CALCULATED"
        assert why == "features_degraded_bad_dt"
        assert payload["bar"] is None
        assert payload["tf_sec"] == 0
