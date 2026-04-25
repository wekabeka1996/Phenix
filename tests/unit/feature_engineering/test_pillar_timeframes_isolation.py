from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.reference.config_loader import get_config
from apps.reference.config_models import (
    FeatureEngineeringDomainConfig,
    OperatorConfig,
    PillarsConfig,
    StrategistConfig,
    TacticianConfig,
)
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering


class _DummyFSM:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, *_args, **_kwargs) -> None:
        return

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        self.emitted.append((event_name, payload or {}, why, data_ref))


def _bar(symbol: str, tf_sec: int, ts_ms: int, close: str) -> dict:
    return {
        "symbol": symbol,
        "timeframe_sec": tf_sec,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": "10.0",
        "end_ts_ms": ts_ms,
    }


def test_config_allows_d1_for_pillars_but_rejects_it_for_emit_timeframes() -> None:
    pillars_cfg = PillarsConfig(
        enabled=True,
        tactician=TacticianConfig(
            enabled=True,
            timeframe_sec=900,
            roc_period=14,
            sensitivity=1.0,
            min_bars=20,
        ),
        operator=OperatorConfig(
            enabled=True,
            timeframe_sec=14400,
            linreg_period=20,
            adx_period=14,
            sensitivity=1.0,
            min_bars=40,
        ),
        strategist=StrategistConfig(
            enabled=True,
            timeframe_sec=86400,
            sma_period=200,
            sensitivity=1.0,
            min_bars=200,
        ),
        weights={
            "tactician": 0.3,
            "operator": 0.4,
            "strategist": 0.3,
        },
        backfill={
            "enabled": True,
            "d1_candles": 200,
            "h4_candles": 80,
            "m15_candles": 40,
        },
    )
    assert pillars_cfg.strategist.timeframe_sec == 86400

    cfg = get_config()
    fe_payload = cfg.domains.feature_engineering.model_dump(mode="python")
    fe_payload["enabled_timeframes_sec"] = [300, 86400]

    with pytest.raises(ValidationError):
        FeatureEngineeringDomainConfig.model_validate(fe_payload)


def test_pillar_internal_timeframes_update_without_emitting_events() -> None:
    cfg = get_config().model_copy(deep=True)
    cfg.domains.feature_engineering.enabled_timeframes_sec = [300]
    if cfg.domains.feature_engineering.pillars is None:
        cfg.domains.feature_engineering.pillars = PillarsConfig()
    cfg.domains.feature_engineering.pillars.tactician.timeframe_sec = 300
    cfg.domains.feature_engineering.pillars.operator.timeframe_sec = 14400
    cfg.domains.feature_engineering.pillars.strategist.timeframe_sec = 86400

    fsm = _DummyFSM()
    fe = FeatureEngineering(fsm=fsm, config=cfg)
    fe._log_features_to_file = lambda *_args, **_kwargs: None

    def _fake_compute_pillars(*args):
        # Force FE adapter fallback path: compute_pillars(state)
        if len(args) == 3:
            raise TypeError("state-only compute_pillars signature")
        state = args[0]
        return {
            "pillar_sum": 0.33,
            "tactician": 0.2 if len(state.m15_closes) > 0 else 0.0,
            "operator": 0.4 if len(state.h4_closes) > 0 else 0.0,
            "strategist": 0.1 if len(state.d1_closes) > 0 else 0.0,
            "pillar_contribs": {"operator": 0.16},
        }

    fe.calc_engine.compute_pillars = _fake_compute_pillars

    symbol = "BTCUSDT"
    fe.on_bar_closed(SimpleNamespace(
        pld={"bar": _bar(symbol, 14400, 1_700_000_000_000, "100.0")}))

    assert symbol in fe._pillar_states
    assert len(fe._pillar_states[symbol].h4_closes) == 1
    assert not any(name == "EVT:FEATURES_CALCULATED" for name,
                   *_ in fsm.emitted)
    assert not any(name == "CMD:PROCESS_STRATEGY" for name, *_ in fsm.emitted)

    fe.on_bar_closed(SimpleNamespace(
        pld={"bar": _bar(symbol, 300, 1_700_000_300_000, "101.0")}))

    feature_events = [item for item in fsm.emitted if item[0]
                      == "EVT:FEATURES_CALCULATED"]
    assert feature_events, "Expected FEATURES_CALCULATED for emit timeframe"
    features = feature_events[-1][1]["features"]
    assert "pillar_sum" in features
    assert "pillar_tactician" in features
    assert "pillar_operator" in features
    assert "pillar_strategist" in features
    assert "pillar_contribs" in features
