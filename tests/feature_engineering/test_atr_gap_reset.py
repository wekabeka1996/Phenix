from __future__ import annotations

import decimal
import json
from collections import deque
from pathlib import Path

from apps.reference.config_loader import get_config
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.feature_engineering.types import BarVolatilityState


class _Bus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict | None, str | None]] = []

    def listen(self, *_args, **_kwargs) -> None:
        return None

    def emit(self, event_name: str, payload=None, why=None, **_kwargs) -> None:
        self.emitted.append((event_name, payload, why))


def _build_tick(symbol: str, ts_ms: int, price: str) -> dict:
    return {
        "symbol": symbol,
        "ts": ts_ms,
        "price": price,
        "bid_size": "10",
        "ask_size": "9",
        "buy_volume": "4",
        "sell_volume": "3",
    }


def _build_bar(symbol: str, ts_ms: int, **overrides) -> dict:
    bar = {
        "symbol": symbol,
        "timeframe_sec": 300,
        "start_ts_ms": ts_ms - 300_000,
        "end_ts_ms": ts_ms,
        "open": "100",
        "high": "102",
        "low": "99",
        "close": "101",
        "volume": "50",
    }
    bar.update(overrides)
    return bar


def _make_fe(tmp_path: Path) -> tuple[FeatureEngineering, _Bus]:
    bus = _Bus()
    fe = FeatureEngineering(fsm=bus, config=get_config())
    fe._feature_logs_dir = str(tmp_path / "feature_logs")
    fe._ohlc_invalid_log_path = str(tmp_path / "ohlc_invalid.jsonl")
    fe._log_features_to_file = lambda *_a, **_kw: None
    return fe, bus


def test_gap_detected_resets_tr_buffer_and_ignores_precomputed_atr_pct(tmp_path: Path, monkeypatch) -> None:
    fe, bus = _make_fe(tmp_path)
    monkeypatch.setattr(
        type(fe.cfg),
        "compute_warmup_full_ready_for_symbol",
        lambda self, **_kwargs: True,
    )
    symbol = "BTCUSDT"
    tf_sec = 300
    vol_state = BarVolatilityState(
        atr_window=3,
        tr_buffer=deque([1.0, 1.0, 1.0]),
        prev_close=decimal.Decimal("100"),
        last_atr=1.0,
        atr_ready=True,
    )
    fe._bar_volatility_states[(symbol, tf_sec)] = vol_state

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=tf_sec,
        current_tick=_build_tick(symbol, 1_700_000_300_000, "101"),
        last_tick=_build_tick(symbol, 1_700_000_299_000, "100"),
        bar_data=_build_bar(
            symbol,
            1_700_000_300_000,
            gap_bars_skipped=2,
            is_gap_bar=True,
            atr_pct=0.99,
        ),
        emit_events=True,
    )

    assert accepted is True
    cmd_payload = next(payload for event_name, payload, _ in bus.emitted if event_name == "CMD:PROCESS_STRATEGY")
    assert cmd_payload["gap_state"] == "GAP_DETECTED"
    assert cmd_payload["features"]["volatility"]["atr_ready"] is False
    assert cmd_payload["features"]["volatility"]["atr_pct"] is None
    assert list(vol_state.tr_buffer) == [3.0]


def test_invalid_ohlc_emits_invalid_event_and_skips_feature_emission(tmp_path: Path, monkeypatch) -> None:
    fe, bus = _make_fe(tmp_path)
    monkeypatch.setattr(
        type(fe.cfg),
        "compute_warmup_full_ready_for_symbol",
        lambda self, **_kwargs: True,
    )
    symbol = "BTCUSDT"
    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=300,
        current_tick=_build_tick(symbol, 1_700_000_300_000, "101"),
        last_tick=_build_tick(symbol, 1_700_000_299_000, "100"),
        bar_data=_build_bar(symbol, 1_700_000_300_000, low="0"),
        emit_events=True,
    )

    assert accepted is False
    emitted_names = [name for name, *_ in bus.emitted]
    assert "EVT:OHLC_INVALID" in emitted_names
    assert "EVT:FEATURES_CALCULATED" not in emitted_names
    assert "CMD:PROCESS_STRATEGY" not in emitted_names
    payload = json.loads(Path(fe._ohlc_invalid_log_path).read_text(encoding="utf-8").strip())
    assert payload["reason"] == "ZERO_LOW"


def test_negative_precomputed_atr_pct_is_ignored(tmp_path: Path, monkeypatch) -> None:
    fe, bus = _make_fe(tmp_path)
    monkeypatch.setattr(
        type(fe.cfg),
        "compute_warmup_full_ready_for_symbol",
        lambda self, **_kwargs: True,
    )
    symbol = "BTCUSDT"
    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=300,
        current_tick=_build_tick(symbol, 1_700_000_600_000, "101"),
        last_tick=_build_tick(symbol, 1_700_000_599_000, "100"),
        bar_data=_build_bar(symbol, 1_700_000_600_000, atr_pct=-0.25),
        emit_events=True,
    )

    assert accepted is True
    cmd_payload = next(payload for event_name, payload, _ in bus.emitted if event_name == "CMD:PROCESS_STRATEGY")
    assert cmd_payload["features"]["volatility"]["atr_pct"] is None
    assert cmd_payload["features"]["volatility"]["atr_ready"] is False


def test_bar_volatility_state_uses_bounded_deque_maxlen() -> None:
    state = BarVolatilityState(atr_window=3)
    state.update_tr(1.0)
    state.update_tr(2.0)
    state.update_tr(3.0)
    state.update_tr(4.0)

    assert list(state.tr_buffer) == [2.0, 3.0, 4.0]
    assert state.atr_ready is True
    assert state.last_atr == 3.0
