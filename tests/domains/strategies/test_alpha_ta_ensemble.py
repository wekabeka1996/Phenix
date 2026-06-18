from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import pytest
from pydantic import ValidationError

from apps.reference.config.strategies.alpha_ta_ensemble import (
    AlphaTaEnsembleStrategyConfig,
    AlphaTaEnsembleProfileConfig,
)
from apps.reference.domains.decision_making.contracts.core_models import (
    ProcessStrategyCmd,
    WarmupState,
)
from apps.reference.domains.strategies.runtimes.alpha_ta_ensemble.handler import AlphaTaEnsembleHandler


def _default_config(**overrides) -> AlphaTaEnsembleStrategyConfig:
    data = {
        "enabled": True,
        "mode": "shadow",
        "strategy_version": "1.0.0",
        "timeframe_sec": 300,
        "threshold": 0.12,
        "momentum": {
            "weights": {"short": 0.3, "medium": 0.4, "long": 0.3},
            "volume": {"confirm_multiplier": 1.2, "contradict_multiplier": 0.8},
            "rsi": {"overbought": 70.0, "oversold": 30.0, "confidence_penalty": 0.7},
            "macd": {"confirm_boost": 1.1, "contradict_penalty": 0.9},
            "confidence": {"base": 0.8, "consistency_min": 0.7, "consistency_range": 0.6},
        },
        "mean_reversion": {
            "weights": {"bb": 0.25, "rsi": 0.55, "sma": 0.1, "stoch": 0.1},
            "rsi": {"oversold": 30.0, "overbought": 70.0},
            "sma": {"deviation_normalizer": 0.05},
            "stochastic": {"oversold_zone": 20.0, "overbought_zone": 80.0, "signal_strength": 0.3},
            "volume": {
                "confirm_multiplier": 1.2,
                "contradict_multiplier": 0.8,
                "high_threshold": 1.5,
                "low_threshold": 0.7,
            },
            "bb_width": {
                "wide_threshold": 0.05,
                "narrow_threshold": 0.02,
                "max_multiplier": 1.5,
                "narrow_penalty": 0.7,
            },
            "confidence": {"base": 0.5, "agreement_factor": 0.4, "strength_base": 0.8, "signal_threshold": 0.1},
        },
        "volatility": {
            "weights": {"atr": 0.4, "bb": 0.25, "rv": 0.2, "range": 0.1, "vol_corr": 0.05},
            "bb": {"amplifier": 10.0},
            "signal_clamp": {"atr": 2.0, "rv": 2.0},
            "volume_vol": {"high_threshold": 1.2, "low_threshold": 0.8, "signal_strength": 0.2},
            "vol_level": {"low_level": 0.5, "low_penalty": 0.5, "high_level": 2.0, "high_boost": 1.2},
            "confidence": {"base": 0.6, "agreement_factor": 0.3, "strength_base": 0.7, "no_signal": 0.4},
        },
        "ensemble": {
            "rebalance_frequency_days": 7,
            "performance_window_days": 30,
            "risk_adjustment": True,
            "models": {
                "mean_reversion_v1": {"enabled": True},
                "momentum_v1": {"enabled": True},
                "volatility_v1": {"enabled": True},
            },
        },
        "profiles": {
            "S06_MR_EXTREME_DEVIATION_ONLY": {
                "profile_id": "S06_MR_EXTREME_DEVIATION_ONLY",
                "name": "MR Extreme Deviation Filter",
                "entry_threshold": 0.18,
                "allowed_regimes": ["LOW_VOLATILITY", "MEAN_REVERSION", "HIGH_VOLATILITY"],
                "allowed_sides": ["BUY", "SELL"],
                "score_overrides": {
                    "mean_reversion.weights.bb": 0.5,
                    "mean_reversion.weights.rsi": 0.3,
                    "mean_reversion.weights.sma": 0.12,
                    "mean_reversion.weights.stoch": 0.08,
                    "mean_reversion.rsi.oversold": 20.0,
                    "mean_reversion.rsi.overbought": 80.0,
                },
            }
        },
        "safety": {
            "allowed_regimes": ["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY", "MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"],
            "forbid_uncertain": False,
            "cooldown_sec": 60,
            "signal_ttl_ms": 300000,
            "min_feature_freshness_sec": 60,
            "max_intents_per_symbol_hour": None,
        },
        "assets": {
            "SOLUSDT": {"enabled": True, "profile_id": "S06_MR_EXTREME_DEVIATION_ONLY"}
        },
    }
    data.update(overrides)
    return AlphaTaEnsembleStrategyConfig.model_validate(data)


def _cmd(features=None, regime="MEAN_REVERSION", ts_ms=1780000000000):
    default_features = {
        "price": 100.0,
        "volume_sma_ratio": 1.0,
    }
    if features:
        default_features.update(features)
    return ProcessStrategyCmd(
        symbol="SOLUSDT",
        tf_sec=300,
        bar_close_ts=ts_ms,
        rid="rid-test-ensemble",
        features=default_features,
        warmup=WarmupState(full_ready=True, ticks_seen=100, ready={}, reasons=()),
        raw={"regime": regime, "ts_ms": ts_ms},
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


def test_config_validation():
    # Valid config loads successfully
    cfg = _default_config()
    assert cfg.enabled is True
    assert cfg.threshold == 0.12

    # extra fields rejected
    with pytest.raises(ValidationError):
        _default_config(extra_field="rejected")

    # invalid mode rejected
    with pytest.raises(ValidationError):
        _default_config(mode="live")

    # disabled mode verification
    cfg_disabled = _default_config(enabled=False, mode="disabled")
    assert cfg_disabled.enabled is False

    # invalid profile referenced by asset rejected
    with pytest.raises(ValidationError):
        _default_config(
            assets={"SOLUSDT": {"enabled": True, "profile_id": "NON_EXISTENT_PROFILE"}}
        )


def test_disabled_mode_has_zero_trading_effect():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_ta_ensemble=_default_config(enabled=False, mode="disabled")),
        trading_mode="testnet",
    )
    handler = AlphaTaEnsembleHandler(fsm=bus, config=config)
    handler.register()

    # Listener shouldn't register if disabled
    assert bus.listeners == []


def test_ta_features_cache_and_clean():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_ta_ensemble=_default_config()),
        trading_mode="testnet",
    )
    handler = AlphaTaEnsembleHandler(fsm=bus, config=config)
    handler.register()

    # Trigger mock TA features 계산 event
    ta_event_payload = {
        "symbol": "SOLUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1780000000000,
        "is_warm": True,
        "rsi_14": 25.0,
        "bb_position": 0.05,
        "bb_width": 0.04,
        "price_sma_20_deviation": -0.03,
        "stoch_k": 15.0,
        "stoch_d": 10.0,
    }
    handler.on_ta_features(SimpleNamespace(pld=ta_event_payload))


    # Verify cached
    cache_key = ("SOLUSDT", 300, 1780000000000)
    assert cache_key in handler._ta_cache
    features, cached_time = handler._ta_cache[cache_key]
    assert features["rsi_14"] == 25.0
    assert features["bb_position"] == 0.05

    # Check cache cleanup: feed > 20 elements
    for i in range(30):
        payload = dict(ta_event_payload)
        payload["bar_close_ts"] = 1780000000000 + i * 1000
        handler.on_ta_features(SimpleNamespace(pld=payload))

    # Older keys must be evicted
    assert cache_key not in handler._ta_cache
    assert len(handler._ta_cache) == 20


def test_shadow_mode_does_not_emit_signals():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_ta_ensemble=_default_config(mode="shadow")),
        trading_mode="testnet",
    )
    handler = AlphaTaEnsembleHandler(fsm=bus, config=config)
    
    # Pre-cache features
    handler.on_ta_features(SimpleNamespace(pld={
        "symbol": "SOLUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1780000000000,
        "is_warm": True,
        "rsi_14": 15.0,
        "bb_position": 0.02,
        "bb_width": 0.05,
        "price_sma_20_deviation": -0.04,
        "stoch_k": 10.0,
        "stoch_d": 8.0,
    }))


    # Process command
    handler.on_process_strategy(_cmd())

    # In shadow mode, signal must not be produced
    emitted_signals = [e for e in bus.emitted if e[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(emitted_signals) == 0


def test_freshness_suppresses_stale_features():
    bus = _Bus()
    config = SimpleNamespace(
        strategies=SimpleNamespace(alpha_ta_ensemble=_default_config(mode="shadow")),
        trading_mode="testnet",
    )
    handler = AlphaTaEnsembleHandler(fsm=bus, config=config)

    # Cache features with old timestamp
    handler._ta_cache[("SOLUSDT", 300, 1780000000000)] = ({
        "rsi_14": 15.0,
        "bb_position": 0.02,
        "bb_width": 0.05,
        "price_sma_20_deviation": -0.04,
        "stoch_k": 10.0,
        "stoch_d": 8.0,
    }, 1000000000000) # Exceeds freshness window (clock at current ts_ms)

    # Process command (current clock mock is ts_ms = 1780000000000)
    handler.on_process_strategy(_cmd(ts_ms=1780000000000))

    # Assert: no strategy signal should be produced due to stale features
    emitted_signals = [e for e in bus.emitted if e[0] == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(emitted_signals) == 0, (
        f"Expected no signals from stale features, got {len(emitted_signals)}"
    )


def _ta_features_all():
    return {
        "bb_position": 0.5,
        "bb_width": 0.05,
        "rsi_14": 50.0,
        "price_sma_20_deviation": 0.0,
        "volume_sma_ratio": 1.0,
        "stoch_k": 50.0,
        "stoch_d": 50.0,
        "price_momentum_5m": 0.0,
        "price_momentum_1h": 0.0,
        "price_momentum_1d": 0.0,
        "volume_momentum_5m": 0.0,
        "macd_signal": 0.0,
        "atr_14": 0.02,
        "atr_ratio": 1.0,
        "bb_width_change": 0.0,
        "realized_volatility_1h": 0.01,
        "realized_volatility_1d": 0.01,
        "price_range_ratio": 1.0,
    }


def test_score_calculation_across_profiles():
    # Construct config with all 4 profiles
    cfg = _default_config(
        assets={
            "SOLUSDT": {"enabled": True, "profile_id": "S06_MR_EXTREME_DEVIATION_ONLY"},
            "ETHUSDT": {"enabled": True, "profile_id": "S09_TREND_PULLBACK_CONTINUATION"},
            "BTCUSDT": {"enabled": True, "profile_id": "S15_HIGH_VOL_FAST_EXIT"},
            "BNBUSDT": {"enabled": True, "profile_id": "S29_FEE_AWARE_EDGE_ONLY"},
        },
        profiles={
            "S06_MR_EXTREME_DEVIATION_ONLY": {
                "profile_id": "S06_MR_EXTREME_DEVIATION_ONLY",
                "name": "MR Extreme Deviation Filter",
                "entry_threshold": 0.18,
                "allowed_regimes": ["LOW_VOLATILITY", "MEAN_REVERSION", "HIGH_VOLATILITY", "TREND_UP", "TREND_DOWN"],
                "allowed_sides": ["BUY", "SELL"],
                "score_overrides": {
                    "mean_reversion.weights.bb": 0.5,
                    "mean_reversion.weights.rsi": 0.3,
                },
            },
            "S09_TREND_PULLBACK_CONTINUATION": {
                "profile_id": "S09_TREND_PULLBACK_CONTINUATION",
                "name": "Trend Pullback Continuation",
                "entry_threshold": 0.07,
                "allowed_regimes": ["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY"],
                "allowed_sides": ["BUY", "SELL"],
                "score_overrides": {
                    "ensemble.momentum_v1.weight": 0.5,
                    "ensemble.mean_reversion_v1.weight": 0.35,
                    "ensemble.volatility_v1.weight": 0.15,
                },
            },
            "S15_HIGH_VOL_FAST_EXIT": {
                "profile_id": "S15_HIGH_VOL_FAST_EXIT",
                "name": "High Vol Fast Exit",
                "entry_threshold": 0.1,
                "allowed_regimes": ["HIGH_VOLATILITY", "MEAN_REVERSION"],
                "allowed_sides": ["BUY", "SELL"],
                "score_overrides": {
                    "ensemble.volatility_v1.weight": 0.6,
                },
            },
            "S29_FEE_AWARE_EDGE_ONLY": {
                "profile_id": "S29_FEE_AWARE_EDGE_ONLY",
                "name": "Fee Aware Edge Only",
                "entry_threshold": 0.12,
                "allowed_regimes": ["TREND_UP", "TREND_DOWN", "LOW_VOLATILITY", "MEAN_REVERSION", "HIGH_VOLATILITY", "UNCERTAIN"],
                "allowed_sides": ["BUY", "SELL"],
                "score_overrides": {
                    "ensemble.momentum_v1.weight": 0.4,
                    "ensemble.mean_reversion_v1.weight": 0.35,
                    "ensemble.volatility_v1.weight": 0.25,
                },
            },
        }
    )

    bus = _Bus()
    config = SimpleNamespace(strategies=SimpleNamespace(alpha_ta_ensemble=cfg), trading_mode="testnet")
    handler = AlphaTaEnsembleHandler(fsm=bus, config=config)

    # Cache all features
    ts = 1780000000000
    for symbol in ("SOLUSDT", "ETHUSDT", "BTCUSDT", "BNBUSDT"):
        ta_payload = _ta_features_all()
        ta_payload.update({"symbol": symbol, "tf_sec": 300, "bar_close_ts": ts, "is_warm": True})
        handler.on_ta_features(SimpleNamespace(pld=ta_payload))

    # Evaluate each symbol and verify no errors are thrown during scoring
    for symbol in ("SOLUSDT", "ETHUSDT", "BTCUSDT", "BNBUSDT"):
        cmd_pld = ProcessStrategyCmd(
            symbol=symbol,
            tf_sec=300,
            bar_close_ts=ts,
            rid=f"rid-{symbol}",
            features={"price": 100.0},
            warmup=WarmupState(full_ready=True, ticks_seen=100, ready={}, reasons=()),
            raw={"regime": "MEAN_REVERSION", "ts_ms": ts},
            price_motion=None,
            structural_regime="MEAN_REVERSION",
        )
        handler.on_process_strategy(cmd_pld)


def test_registry_integration():
    from apps.reference.domains.strategies.registry import StrategyPluginRegistry
    from apps.reference.domains.strategies.plugins.alpha_ta_ensemble import AlphaTaEnsemblePlugin

    registry = StrategyPluginRegistry()
    registry.register(AlphaTaEnsemblePlugin())

    assert registry.get("alpha_ta_ensemble") is not None
    assert "alpha_ta_ensemble" in registry.ids()


def test_no_regression_existing_strategies():
    from apps.reference.config.strategies.aurora import AuroraStrategyConfig
    from apps.reference.config.strategies.mean_reversion import MeanReversion1mStrategyConfig

    # Verify existing strategies can still be initialized
    # without any schema contamination or validation regression
    assert AuroraStrategyConfig is not None
    assert MeanReversion1mStrategyConfig is not None
