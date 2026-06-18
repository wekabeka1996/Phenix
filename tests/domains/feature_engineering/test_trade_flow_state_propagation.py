from tests.domains.feature_engineering.test_feature_contract_split import (
    _bar_payload,
    _build_minimal_fe,
    _tick,
)


def test_feature_engineering_preserves_trade_flow_metadata(monkeypatch):
    from apps.reference.domains.feature_engineering.contracts import validate_bar_features_payload_v1

    fe = _build_minimal_fe(monkeypatch)
    symbol = "BTCUSDT"
    current_ts = 1_700_000_000_000
    bar_start = current_ts - 180_000
    bar_end = current_ts - 1
    current_tick = _tick(symbol, current_ts, "100.0")
    current_tick.update(
        {
            "trade_flow_state": "degraded",
            "trade_flow_age_ms": 61_000,
            "trade_flow_last_trade_ts_ms": current_ts - 61_000,
            "trade_flow_window_sec": 60,
        }
    )

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=180,
        current_tick=current_tick,
        last_tick=_tick(symbol, current_ts - 1000, "99.5"),
        bar_data=_bar_payload(symbol, 180, bar_start, bar_end),
        emit_events=True,
    )

    assert accepted is True
    event_name, payload, _why, _ = fe.fsm.emitted[-1]
    assert event_name == "EVT:FEATURES_CALCULATED"
    assert payload["trade_flow_state"] == "degraded"
    assert payload["trade_flow_age_ms"] == 61_000
    assert payload["trade_flow_last_trade_ts_ms"] == current_ts - 61_000
    assert payload["trade_flow_window_sec"] == 60

    model = validate_bar_features_payload_v1(payload)
    assert model.trade_flow_state == "degraded"
    assert model.trade_flow_age_ms == 61_000


def test_feature_engineering_old_payload_without_trade_flow_metadata_still_validates(monkeypatch):
    from apps.reference.domains.feature_engineering.contracts import validate_bar_features_payload_v1

    fe = _build_minimal_fe(monkeypatch)
    symbol = "BTCUSDT"
    current_ts = 1_700_000_000_000

    accepted = fe._calculate_and_emit_features_for_tf(
        symbol=symbol,
        tf_sec=180,
        current_tick=_tick(symbol, current_ts, "100.0"),
        last_tick=_tick(symbol, current_ts - 1000, "99.5"),
        bar_data=_bar_payload(symbol, 180, current_ts - 180_000, current_ts - 1),
        emit_events=True,
    )

    assert accepted is True
    _event_name, payload, _why, _ = fe.fsm.emitted[-1]
    assert "trade_flow_state" not in payload
    validate_bar_features_payload_v1(payload)
