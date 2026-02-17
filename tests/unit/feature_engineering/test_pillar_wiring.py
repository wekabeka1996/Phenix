from unittest.mock import MagicMock

from apps.reference.config_loader import get_config
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering


class _DummyFSM:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, *_args, **_kwargs) -> None:
        return

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))


def _make_bar_payload(symbol: str, tf_sec: int, ts_ms: int) -> dict:
    return {
        "symbol": symbol,
        "timeframe_sec": tf_sec,
        "open": "100.0",
        "high": "103.0",
        "low": "99.0",
        "close": "102.0",
        "volume": "10.0",
        "end_ts_ms": ts_ms,
    }


def _make_ticks(symbol: str, ts_ms: int) -> tuple[dict, dict]:
    current_tick = {
        "symbol": symbol,
        "ts": ts_ms,
        "price": "102.0",
        "bid_size": "10.0",
        "ask_size": "9.0",
        "buy_volume": "6.0",
        "sell_volume": "4.0",
        "best_bid": "101.9",
        "best_ask": "102.1",
        "bid": "101.9",
        "ask": "102.1",
        "rsi_14": "55.0",
    }
    last_tick = {
        "symbol": symbol,
        "ts": ts_ms - 1000,
        "price": "100.0",
        "bid_size": "10.0",
        "ask_size": "9.0",
        "buy_volume": "6.0",
        "sell_volume": "4.0",
        "best_bid": "99.9",
        "best_ask": "100.1",
        "bid": "99.9",
        "ask": "100.1",
    }
    return current_tick, last_tick


def _last_features_payload(fsm: _DummyFSM) -> dict:
    feature_events = [item for item in fsm.emitted if item[0] == "EVT:FEATURES_CALCULATED"]
    assert feature_events, "Expected EVT:FEATURES_CALCULATED emission"
    return feature_events[-1][1]


def _build_fe() -> tuple[FeatureEngineering, _DummyFSM]:
    cfg = get_config()
    fsm = _DummyFSM()
    fe = FeatureEngineering(fsm=fsm, config=cfg)
    fe._log_features_to_file = MagicMock()
    return fe, fsm


def test_pillar_wiring_happy_path_emits_expected_keys() -> None:
    fe, fsm = _build_fe()
    symbol = "BTCUSDT"
    tf_sec = 300
    ts_ms = 1_700_000_000_000
    bar_data = _make_bar_payload(symbol=symbol, tf_sec=tf_sec, ts_ms=ts_ms)
    current_tick, last_tick = _make_ticks(symbol=symbol, ts_ms=ts_ms)

    fe.calc_engine.compute_pillars = MagicMock(
        return_value={
            "pillar_sum": 0.42,
            "pillar_tactician": 0.30,
            "pillar_operator": 0.60,
            "pillar_strategist": 0.10,
            "pillar_contribs": {"tactician": 0.09, "operator": 0.24, "strategist": 0.03},
        }
    )

    fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=tf_sec,
        current_tick=current_tick,
        last_tick=last_tick,
        bar_data=bar_data,
    )

    payload = _last_features_payload(fsm)
    features = payload["features"]
    assert features["pillar_sum"] == 0.42
    assert features["pillar_tactician"] == 0.30
    assert features["pillar_operator"] == 0.60
    assert features["pillar_strategist"] == 0.10
    assert features["pillar_contribs"] == {"tactician": 0.09, "operator": 0.24, "strategist": 0.03}
    assert "obi" in features  # Existing feature still present


def test_pillar_wiring_warmup_none_keeps_payload_without_pillar_keys() -> None:
    fe, fsm = _build_fe()
    symbol = "BTCUSDT"
    tf_sec = 300
    ts_ms = 1_700_000_000_000
    bar_data = _make_bar_payload(symbol=symbol, tf_sec=tf_sec, ts_ms=ts_ms)
    current_tick, last_tick = _make_ticks(symbol=symbol, ts_ms=ts_ms)

    fe.calc_engine.compute_pillars = MagicMock(return_value=None)

    fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=tf_sec,
        current_tick=current_tick,
        last_tick=last_tick,
        bar_data=bar_data,
    )

    payload = _last_features_payload(fsm)
    features = payload["features"]
    assert "pillar_sum" not in features
    assert "pillar_tactician" not in features
    assert "pillar_operator" not in features
    assert "pillar_strategist" not in features
    assert "pillar_contribs" not in features


def test_pillar_wiring_does_not_break_existing_pass_through_feature() -> None:
    fe, fsm = _build_fe()
    symbol = "BTCUSDT"
    tf_sec = 300
    ts_ms = 1_700_000_000_000
    bar_data = _make_bar_payload(symbol=symbol, tf_sec=tf_sec, ts_ms=ts_ms)
    current_tick, last_tick = _make_ticks(symbol=symbol, ts_ms=ts_ms)

    fe.calc_engine.compute_pillars = MagicMock(
        return_value={
            "pillar_sum": 0.22,
            "pillar_tactician": 0.11,
            "pillar_operator": 0.22,
            "pillar_strategist": -0.11,
            "pillar_contribs": {"tactician": 0.03},
        }
    )

    fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=tf_sec,
        current_tick=current_tick,
        last_tick=last_tick,
        bar_data=bar_data,
    )

    payload = _last_features_payload(fsm)
    features = payload["features"]
    assert features.get("rsi_14") is not None
    assert "pillar_sum" in features
