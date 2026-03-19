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
    hot = SimpleNamespace(
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
    )
    state = SimpleNamespace(hot=hot, cold=SimpleNamespace())
    fe._get_symbol_state = lambda symbol: state
    fe._init_symbol_state = lambda symbol: fe.symbol_states.__setitem__(
        symbol,
        state,
    )
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
    fe._price_motion_sanity_cfg = SimpleNamespace(
        k_vol=1.0,
        pm_norm_clip_abs=10.0,
    )
    fe._compute_pillars_for_emit = lambda **kwargs: None
    fe._try_warmup_seed_atr = lambda *args, **kwargs: None
    fe._log_features_to_file = lambda *args, **kwargs: None
    monkeypatch.setattr(
        "apps.reference.domains.feature_engineering.feature_engineering.compute_price_motion_block",
        lambda *args, **kwargs: {
            "ret_10s": 0.0,
            "ret_60s": 0.0,
            "ret_300s": 0.0,
            "vol_pct_10s": 0.0,
            "vol_pct_60s": 0.0,
            "vol_pct_300s": 0.0,
            "pm_norm_10s": 0.0,
            "pm_norm_60s": 0.0,
            "pm_norm_300s": 0.0,
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


def _bar_payload(symbol: str, tf_sec: int, start_ts_ms: int, end_ts_ms: int) -> dict:
    return {
        "symbol": symbol,
        "timeframe_sec": tf_sec,
        "start_ts_ms": start_ts_ms,
        "end_ts_ms": end_ts_ms,
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "volume": "1000.0",
        "is_candidate": False,
    }


def test_tick_path_emits_tick_verb_and_null_bar(monkeypatch):
    from apps.reference.domains.feature_engineering.contracts import validate_tick_features_payload_v1

    fe = _build_minimal_fe(monkeypatch)
    symbol = "BTCUSDT"
    now_ms = 1_700_000_000_000

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=0,
        current_tick=_tick(symbol, now_ms, "100.0"),
        last_tick=_tick(symbol, now_ms - 1000, "99.5"),
        emit_events=True,
    )

    assert accepted is True
    assert fe.fsm.emitted, "Expected tick emission"

    event_name, payload, why, _ = fe.fsm.emitted[-1]
    assert event_name == "EVT:TICK_FEATURES_CALCULATED"
    assert why == "features_calculated"
    assert payload["tf_sec"] == 0
    assert payload["bar"] is None
    assert payload["source_mode"] == "live"
    assert isinstance(payload.get("price_motion"), dict)

    model = validate_tick_features_payload_v1(payload)
    assert model.tf_sec == 0
    assert model.bar is None


def test_bar_path_emits_bar_verb_and_bar_payload(monkeypatch):
    from apps.reference.domains.feature_engineering.contracts import validate_bar_features_payload_v1

    fe = _build_minimal_fe(monkeypatch)
    symbol = "BTCUSDT"
    current_ts = 1_700_000_000_000
    bar_start = current_ts - 180_000
    bar_end = current_ts - 1

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=180,
        current_tick=_tick(symbol, current_ts, "100.0"),
        last_tick=_tick(symbol, current_ts - 1000, "99.5"),
        bar_data=_bar_payload(symbol, 180, bar_start, bar_end),
        emit_events=True,
    )

    assert accepted is True
    assert fe.fsm.emitted, "Expected bar emission"

    event_name, payload, why, _ = fe.fsm.emitted[-1]
    assert event_name == "EVT:FEATURES_CALCULATED"
    assert why == "features_calculated"
    assert payload["tf_sec"] == 180
    assert payload["bar"] is not None
    assert payload["source_mode"] == "live"
    assert isinstance(payload.get("price_motion"), dict)
    assert payload.get("bar_identity") is not None
    assert payload.get("close_boundary_ts_ms") is not None

    model = validate_bar_features_payload_v1(payload)
    assert model.tf_sec == 180
    assert model.bar["timeframe_sec"] == 180


def test_bad_dt_tick_path_emits_tick_verb(monkeypatch):
    from apps.reference.domains.feature_engineering.contracts import validate_tick_features_payload_v1

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
    assert fe.fsm.emitted, "Expected bad_dt tick emission"

    event_name, payload, why, _ = fe.fsm.emitted[-1]
    assert event_name == "EVT:TICK_FEATURES_CALCULATED"
    assert why == "features_degraded_bad_dt"
    assert payload["tf_sec"] == 0
    assert payload["bar"] is None
    assert payload["price_motion"] is None
    assert payload["source_mode"] == "live"
    assert payload["data_quality"]["drops"] == ["bad_dt"]

    model = validate_tick_features_payload_v1(payload)
    assert model.tf_sec == 0
    assert model.bar is None
    assert model.price_motion is None
