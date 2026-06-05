from typing import Any, Dict, Optional


def _base_features_aurora() -> Dict[str, Any]:
    return {
        "obi": 0.12,
        "delta_price": 0.003,
        "macro_resid": 0.05,
        "tfi": 0.4,
        "ema_bias": 0.002,
        "volume_spike": 1.3,
        "volatility_state": 0.8,
        "depth_imbalance": 0.15,
        "macro_sync": True,
        "close": 96000.0,
    }


def _base_features_mr() -> Dict[str, Any]:
    return {
        "bb_position": 0.3,
        "bb_width": 0.02,
        "rsi_14": 45.0,
        "price_sma_20_deviation": -0.005,
        "stoch_k": 35.0,
        "stoch_d": 38.0,
        "volume_ratio": 1.1,
        "close": 96000.0,
    }


def _base_features_full() -> Dict[str, Any]:
    features = _base_features_aurora()
    features.update(_base_features_mr())
    features.update(
        {
            "momentum_5": 0.002,
            "momentum_60": 0.005,
            "momentum_1440": 0.01,
            "volume_momentum": 1.1,
            "macd_histogram": 0.0005,
            "atr_pct": 0.015,
            "realized_volatility": 0.012,
            "range_pct": 0.018,
            "price": 96000.0,
        }
    )
    return features


def make_snapshot(
    *,
    symbol: str = "BTCUSDT",
    price: float = 96000.0,
    ts_ms: int = 1740000000000,
    bar_close_ts: int = 1740000000000,
    tf_sec: int = 300,
    features: Optional[Dict[str, Any]] = None,
    regime: str = "DEFAULT",
    warmup_status: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    return {
        "ts_ms": ts_ms,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "price": price,
        "features": features or _base_features_full(),
        "regime": regime,
        "warmup_status": warmup_status or {},
    }
