from decimal import Decimal
from types import SimpleNamespace


class _DummyFsm:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, *_args, **_kwargs) -> None:
        return

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))


def _make_tick(*, symbol: str, ts: int, price: str) -> dict:
    return {
        "symbol": symbol,
        "ts": ts,
        "price": price,
        "bid_size": "1",
        "ask_size": "1",
        "buy_volume": "1",
        "sell_volume": "1",
        "bid": price,
        "ask": price,
    }


def test_on_bar_closed_injects_wall_ts_ms_for_bar_events(monkeypatch):
    from apps.reference.config_loader import get_config
    from apps.reference.domains.feature_engineering.bar_resampler import Bar
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    fsm = _DummyFsm()
    fe = FeatureEngineering(fsm=fsm, config=get_config())
    monkeypatch.setattr(fe, "_log_features_to_file", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        "apps.reference.domains.feature_engineering.feature_engineering.time.time",
        lambda: 1234.567,
    )

    captured: dict[str, dict] = {}

    def _capture(symbol, tf_sec, current_tick, last_tick, bar_data=None, emit_events=True):
        captured["current_tick"] = dict(current_tick)
        captured["last_tick"] = dict(last_tick)
        return False

    monkeypatch.setattr(fe, "_calculate_and_emit_features_for_tf", _capture)

    bar = Bar(
        symbol="BTCUSDT",
        timeframe_sec=300,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
        trade_count=5,
        start_ts_ms=1_000_000,
        end_ts_ms=1_300_000,
        gap_bars_skipped=0,
        is_gap_bar=False,
    )

    fe.on_bar_closed(SimpleNamespace(pld={"bar": bar}))

    assert captured["current_tick"]["ts"] == 1_300_000
    assert captured["current_tick"]["wall_ts_ms"] == 1_234_567
    assert captured["last_tick"]["ts"] < captured["current_tick"]["ts"]


def test_bar_path_uses_wall_ts_for_macro_resid_anchor_lookup(monkeypatch):
    from apps.reference.config_loader import get_config
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    fsm = _DummyFsm()
    fe = FeatureEngineering(fsm=fsm, config=get_config())
    monkeypatch.setattr(fe, "_log_features_to_file", lambda *_a, **_kw: None)

    lookup: dict[str, int] = {}

    def _capture_lookup(anchor: str, *, current_ts_ms: int):
        lookup["current_ts_ms"] = int(current_ts_ms)
        return None

    monkeypatch.setattr(fe, "_latest_anchor_price_pair_before", _capture_lookup)

    symbol = "SOLUSDT"
    fe._anchor_last_ts_ms["BTCUSDT"] = 1_500

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=300,
        current_tick={
            **_make_tick(symbol=symbol, ts=1_000, price="101"),
            "wall_ts_ms": 2_000,
        },
        last_tick=_make_tick(symbol=symbol, ts=500, price="100"),
        emit_events=False,
    )

    hot = fe._get_symbol_state(symbol).hot

    assert accepted is True
    assert lookup["current_ts_ms"] == 2_000
    assert hot.macro_resid_not_ready_reason == "insufficient_anchor_samples:BTCUSDT"


def test_tick_path_preserves_future_anchor_guard_for_macro_resid(monkeypatch):
    from apps.reference.config_loader import get_config
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    fsm = _DummyFsm()
    fe = FeatureEngineering(fsm=fsm, config=get_config())
    monkeypatch.setattr(fe, "_log_features_to_file", lambda *_a, **_kw: None)

    lookup: dict[str, int] = {}

    def _capture_lookup(anchor: str, *, current_ts_ms: int):
        lookup["current_ts_ms"] = int(current_ts_ms)
        return None

    monkeypatch.setattr(fe, "_latest_anchor_price_pair_before", _capture_lookup)

    symbol = "SOLUSDT"
    fe._anchor_last_ts_ms["BTCUSDT"] = 1_500

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=300,
        current_tick=_make_tick(symbol=symbol, ts=1_000, price="101"),
        last_tick=_make_tick(symbol=symbol, ts=500, price="100"),
        emit_events=False,
    )

    hot = fe._get_symbol_state(symbol).hot

    assert accepted is True
    assert lookup["current_ts_ms"] == 1_000
    assert hot.macro_resid_not_ready_reason == "anchor_from_future:BTCUSDT"
