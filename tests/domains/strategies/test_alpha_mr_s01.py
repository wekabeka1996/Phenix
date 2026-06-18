from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.reference.config.strategies.alpha_mr_s01 import AlphaMrS01StrategyConfig
from apps.reference.domains.decision_making.contracts.core_models import (
    ProcessStrategyCmd,
    WarmupState,
)
from apps.reference.domains.alpha_search.models.mean_reversion import MeanReversionAlphaModel
from apps.reference.domains.strategies.runtimes.alpha_mr_s01.handler import AlphaMrS01Handler
from apps.reference.domains.strategies.scoring.weighted_mean_reversion import (
    WeightedMeanReversionConfig,
    WeightedMeanReversionScorer,
)


def _strategy_config(**overrides):
    data = {
        "enabled": False,
        "mode": "disabled",
        "source_scenario_id": "S01_MR_RSI_HEAVY",
        "strategy_version": "1.0.0",
        "timeframe_sec": 300,
        "threshold": 0.08,
        "weights": {"bb": 0.25, "rsi": 0.55, "sma": 0.10, "stoch": 0.10},
        "rsi": {"oversold": 28, "overbought": 72},
        "sma": {"deviation_normalizer": 0.05},
        "stochastic": {"oversold_zone": 20, "overbought_zone": 80, "signal_strength": 0.3},
        "volume": {
            "enabled": True,
            "confirm_multiplier": 1.2,
            "contradict_multiplier": 0.8,
            "high_threshold": 1.5,
            "low_threshold": 0.7,
        },
        "bb_width": {
            "min_width": 0.001,
            "max_width": 0.19,
            "narrow_penalty_enabled": True,
            "narrow_threshold": 0.02,
            "narrow_penalty": 0.7,
            "wide_boost_enabled": True,
            "wide_threshold": 0.05,
            "max_multiplier": 1.5,
        },
        "safety": {
            "allowed_regimes": ["LOW_VOLATILITY", "MEAN_REVERSION", "FLAT_LOW"],
            "forbid_uncertain": True,
            "cooldown_sec": 60,
            "signal_ttl_ms": 300000,
            "missing_component_policy": "suppress",
            "max_intents_per_symbol_hour": None,
        },
        "assets": {"BNBUSDT": {"enabled": True}},
    }
    data.update(overrides)
    return AlphaMrS01StrategyConfig.model_validate(data)


def _scorer_config():
    cfg = _strategy_config(enabled=True, mode="shadow")
    return WeightedMeanReversionConfig(
        bb_weight=Decimal(str(cfg.weights.bb)),
        rsi_weight=Decimal(str(cfg.weights.rsi)),
        sma_weight=Decimal(str(cfg.weights.sma)),
        stoch_weight=Decimal(str(cfg.weights.stoch)),
        threshold=Decimal(str(cfg.threshold)),
        rsi_oversold=Decimal(str(cfg.rsi.oversold)),
        rsi_overbought=Decimal(str(cfg.rsi.overbought)),
        sma_deviation_normalizer=Decimal(str(cfg.sma.deviation_normalizer)),
        stoch_oversold_zone=Decimal(str(cfg.stochastic.oversold_zone)),
        stoch_overbought_zone=Decimal(str(cfg.stochastic.overbought_zone)),
        stoch_signal_strength=Decimal(str(cfg.stochastic.signal_strength)),
        volume_enabled=cfg.volume.enabled,
        volume_confirm_multiplier=Decimal(str(cfg.volume.confirm_multiplier)),
        volume_contradict_multiplier=Decimal(str(cfg.volume.contradict_multiplier)),
        volume_high_threshold=Decimal(str(cfg.volume.high_threshold)),
        volume_low_threshold=Decimal(str(cfg.volume.low_threshold)),
        bb_min_width=Decimal(str(cfg.bb_width.min_width)),
        bb_max_width=Decimal(str(cfg.bb_width.max_width)),
        bb_narrow_penalty_enabled=cfg.bb_width.narrow_penalty_enabled,
        bb_narrow_threshold=Decimal(str(cfg.bb_width.narrow_threshold)),
        bb_narrow_penalty=Decimal(str(cfg.bb_width.narrow_penalty)),
        bb_wide_boost_enabled=cfg.bb_width.wide_boost_enabled,
        bb_wide_threshold=Decimal(str(cfg.bb_width.wide_threshold)),
        bb_max_multiplier=Decimal(str(cfg.bb_width.max_multiplier)),
    )


def _features(**overrides):
    data = {
        "bb_position": 0.05,
        "bb_width": 0.04,
        "rsi_14": 22,
        "price_sma_20_deviation": -0.03,
        "volume_sma_ratio": 1.0,
        "stoch_k": 15,
        "stoch_d": 10,
        "price": 594.77,
    }
    data.update(overrides)
    return data


def _cmd(features=None, regime="LOW_VOLATILITY"):
    return ProcessStrategyCmd(
        symbol="BNBUSDT",
        tf_sec=300,
        bar_close_ts=1_780_000_000_000,
        rid="rid-test",
        features=features or _features(),
        warmup=WarmupState(full_ready=True, ticks_seen=100, ready={}, reasons=()),
        raw={"regime": regime, "ts_ms": 1_780_000_000_000},
        price_motion=None,
        structural_regime=regime,
    )


class _Bus:
    def __init__(self):
        self.listeners = []
        self.emitted = []

    def listen(self, name, handler):
        self.listeners.append((name, handler))

    def emit(self, name, payload=None, **kwargs):
        self.emitted.append((name, payload, kwargs))


def test_config_rejects_extra_fields_and_invalid_weights():
    with pytest.raises(Exception):
        _strategy_config(extra_field=True)
    with pytest.raises(Exception):
        _strategy_config(weights={"bb": 0.5, "rsi": 0.5, "sma": 0.5, "stoch": 0.5})
    with pytest.raises(Exception):
        _strategy_config(mode="live")


def test_weighted_scorer_matches_s01_formula_for_buy_signal():
    result = WeightedMeanReversionScorer(_scorer_config()).score(_features())
    assert result.allowed is True
    assert result.side == "BUY"
    assert result.components["bb"] == Decimal("0.90")
    assert result.components["rsi"] == Decimal("1.0")
    assert result.components["sma"] == Decimal("0.6")
    assert result.components["stoch"] == Decimal("0.3")
    assert result.final_score == Decimal("0.865")


def test_weighted_scorer_matches_alpha_search_s01_model_score_and_confidence():
    cfg = _strategy_config(enabled=True, mode="testnet_candidate")
    alpha_model = MeanReversionAlphaModel(
        {
            "weights": {
                "bb": cfg.weights.bb,
                "rsi": cfg.weights.rsi,
                "sma": cfg.weights.sma,
                "stoch": cfg.weights.stoch,
            },
            "rsi": {
                "oversold": cfg.rsi.oversold,
                "overbought": cfg.rsi.overbought,
            },
            "sma": {"deviation_normalizer": cfg.sma.deviation_normalizer},
            "stochastic": {
                "oversold_zone": cfg.stochastic.oversold_zone,
                "overbought_zone": cfg.stochastic.overbought_zone,
                "signal_strength": cfg.stochastic.signal_strength,
            },
            "volume": {
                "confirm_multiplier": cfg.volume.confirm_multiplier,
                "contradict_multiplier": cfg.volume.contradict_multiplier,
                "high_threshold": cfg.volume.high_threshold,
                "low_threshold": cfg.volume.low_threshold,
            },
            "bb_width": {
                "wide_threshold": cfg.bb_width.wide_threshold,
                "narrow_threshold": cfg.bb_width.narrow_threshold,
                "max_multiplier": cfg.bb_width.max_multiplier,
                "narrow_penalty": cfg.bb_width.narrow_penalty,
            },
        }
    )
    features = _features()

    live_result = WeightedMeanReversionScorer(_scorer_config()).score(features)
    alpha_result = alpha_model.calculate_alpha(
        symbol="BNBUSDT",
        market_data={},
        features=features,
        context={},
    )

    assert live_result.final_score == alpha_result.score
    assert live_result.confidence == alpha_result.confidence


def test_weighted_scorer_suppresses_missing_component():
    features = _features()
    features.pop("rsi_14")
    result = WeightedMeanReversionScorer(_scorer_config()).score(features)
    assert result.allowed is False
    assert result.reason == "missing_components:rsi_14"


def test_disabled_mode_registers_no_listener():
    bus = _Bus()
    config = SimpleNamespace(strategies=SimpleNamespace(alpha_mr_s01=_strategy_config()), trading_mode="testnet")
    AlphaMrS01Handler(fsm=bus, config=config).register()
    assert bus.listeners == []


def test_shadow_mode_does_not_emit_strategy_signal():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="shadow")),
        trading_mode="testnet",
    )
    handler = AlphaMrS01Handler(fsm=bus, config=config)
    handler.on_process_strategy(_cmd())
    assert not [event for event in bus.emitted if event[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]


def test_active_mode_registers_ta_features_and_process_strategy_listeners():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="shadow")),
        trading_mode="testnet",
    )

    AlphaMrS01Handler(fsm=bus, config=config).register()

    assert [name for name, _handler in bus.listeners] == [
        "EVT:TA_FEATURES_CALCULATED",
        "CMD:PROCESS_STRATEGY",
    ]


def test_handler_merges_same_bar_ta_features_before_scoring():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="testnet_candidate")),
        trading_mode="testnet",
    )
    handler = AlphaMrS01Handler(fsm=bus, config=config)
    handler.on_ta_features(
        SimpleNamespace(
            pld={
                "symbol": "BNBUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1_780_000_000_000,
                "is_warm": True,
                **_features(),
            }
        )
    )

    handler.on_process_strategy(_cmd(features={"price": 594.77}))

    signals = [payload for event, payload, _ in bus.emitted if event == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(signals) == 1
    assert signals[0]["side"] == "BUY"


def test_testnet_candidate_emits_standard_strategy_signal():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="testnet_candidate")),
        trading_mode="testnet",
    )
    handler = AlphaMrS01Handler(fsm=bus, config=config)
    handler.on_process_strategy(_cmd())
    signals = [payload for event, payload, _ in bus.emitted if event == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(signals) == 1
    assert signals[0]["strategy_id"] == "alpha_mr_s01"
    assert signals[0]["source_scenario_id"] == "S01_MR_RSI_HEAVY"
    assert signals[0]["side"] == "BUY"
    assert signals[0]["price_ctx"]["entry_price"] == "594.77"


def test_testnet_candidate_blocks_production_mode():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="testnet_candidate")),
        trading_mode="production",
    )
    handler = AlphaMrS01Handler(fsm=bus, config=config)
    handler.on_process_strategy(_cmd())
    assert not [event for event in bus.emitted if event[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]


def test_testnet_candidate_suppresses_missing_entry_price():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="testnet_candidate")),
        trading_mode="testnet",
    )
    features = _features()
    features.pop("price")
    handler = AlphaMrS01Handler(fsm=bus, config=config)
    handler.on_process_strategy(_cmd(features=features))
    assert not [event for event in bus.emitted if event[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]


def test_invalid_boundary_payload_is_dropped_fail_closed():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_mr_s01=_strategy_config(enabled=True, mode="testnet_candidate")),
        trading_mode="testnet",
    )
    handler = AlphaMrS01Handler(fsm=bus, config=config)
    handler.on_process_strategy(SimpleNamespace(pld={"tf_sec": 300, "features": _features()}))
    assert not [event for event in bus.emitted if event[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
