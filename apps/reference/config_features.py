"""
FeatureEngineering domain resolver that now requires config v2.

Legacy inline defaults are kept for historical reference but are no longer used
by the resolver path. All consumers must supply config/domains/features.yaml as
generated via the vFoundation schema tooling (see docs/config_v2/specification.md).
"""

import logging
from typing import Any, Dict, Mapping, Optional, List

from apps.reference.config_models import AuroraConfig, FeatureEngineeringConfig

logger = logging.getLogger(__name__)


def _get_v2_features_cfg(cfg: AuroraConfig) -> Optional[Mapping[str, Any]]:
    """Return cfg.config_v2.domains["features"] if present and not empty, else None."""
    if cfg.config_v2 and cfg.config_v2.domains and "features" in cfg.config_v2.domains:
        features_cfg = cfg.config_v2.domains["features"]
        if features_cfg:  # Not empty
            return features_cfg
    return None


def _build_features_from_legacy(cfg: AuroraConfig) -> FeatureEngineeringConfig:
    """Build FeatureEngineeringConfig from legacy config/aurora/trading.yaml."""
    # Load legacy trading.yaml
    # From trading.yaml feature_engineering section
    enable_new_metrics = True
    ema_period_short = 3
    ema_period_long = 7
    ema_bias_clamp = 0.02
    volume_window_sec = 60
    volume_sma_length = 5
    volume_spike_cap = 3.0
    volatility_window_sec = 60
    volatility_sma_length = 10
    volatility_ratio_cap = 3.0
    liquidity_depth_half = 1000.0
    liquidity_kappa_min = 0.3
    liquidity_kappa_max = 1.0

    # From trading.yaml market_data.macro_sync section
    macro_sync_enabled = True
    macro_sync_anchors = ["BTCUSDT", "ETHUSDT"]
    macro_sync_window = 60

    return FeatureEngineeringConfig(
        enable_new_metrics=enable_new_metrics,
        ema_period_short=ema_period_short,
        ema_period_long=ema_period_long,
        ema_bias_clamp=ema_bias_clamp,
        volume_window_sec=volume_window_sec,
        volume_sma_length=volume_sma_length,
        volume_spike_cap=volume_spike_cap,
        volatility_window_sec=volatility_window_sec,
        volatility_sma_length=volatility_sma_length,
        volatility_ratio_cap=volatility_ratio_cap,
        liquidity_depth_half=liquidity_depth_half,
        liquidity_kappa_min=liquidity_kappa_min,
        liquidity_kappa_max=liquidity_kappa_max,
        macro_sync_enabled=macro_sync_enabled,
        macro_sync_anchors=macro_sync_anchors,
        macro_sync_window=macro_sync_window,
        source="legacy"
    )


def _build_features_from_v2(v2_cfg: Mapping[str, Any]) -> FeatureEngineeringConfig:
    """Build FeatureEngineeringConfig from config/domains/features.yaml."""
    # Validate v2 config
    global_cfg = v2_cfg.get("global", {})
    enable_new_metrics = global_cfg.get("enable_new_metrics", True)
    if not isinstance(enable_new_metrics, bool):
        raise ValueError(
            f"enable_new_metrics must be bool, got {enable_new_metrics}")

    windows_cfg = v2_cfg.get("windows", {})
    ema_cfg = windows_cfg.get("ema", {})
    ema_period_short = ema_cfg.get("period_short", 3)
    ema_period_long = ema_cfg.get("period_long", 7)
    if ema_period_short <= 0 or ema_period_long <= 0:
        raise ValueError(
            f"EMA periods must be > 0, got short={ema_period_short}, long={ema_period_long}")

    volume_cfg = windows_cfg.get("volume", {})
    volume_window_sec = volume_cfg.get("window_sec", 60)
    volume_sma_length = volume_cfg.get("sma_length", 5)
    if volume_window_sec <= 0 or volume_sma_length <= 0:
        raise ValueError(
            f"Volume params must be > 0, got window_sec={volume_window_sec}, sma_length={volume_sma_length}")

    volatility_cfg = windows_cfg.get("volatility", {})
    volatility_window_sec = volatility_cfg.get("window_sec", 60)
    volatility_sma_length = volatility_cfg.get("sma_length", 10)
    if volatility_window_sec <= 0 or volatility_sma_length <= 0:
        raise ValueError(
            f"Volatility params must be > 0, got window_sec={volatility_window_sec}, sma_length={volatility_sma_length}")

    features_cfg = v2_cfg.get("features", {})
    ema_bias_clamp = features_cfg.get("ema", {}).get("bias_clamp", 0.02)
    volume_spike_cap = features_cfg.get("volume", {}).get("spike_cap", 3.0)
    volatility_ratio_cap = features_cfg.get(
        "volatility", {}).get("ratio_cap", 3.0)
    liquidity_cfg = features_cfg.get("liquidity", {})
    liquidity_depth_half = liquidity_cfg.get("depth_half", 1000.0)
    liquidity_kappa_min = liquidity_cfg.get("kappa_min", 0.3)
    liquidity_kappa_max = liquidity_cfg.get("kappa_max", 1.0)

    if ema_bias_clamp <= 0 or volume_spike_cap <= 0 or volatility_ratio_cap <= 0:
        raise ValueError(
            f"Feature caps must be > 0, got ema_bias_clamp={ema_bias_clamp}, volume_spike_cap={volume_spike_cap}, volatility_ratio_cap={volatility_ratio_cap}")
    if liquidity_depth_half <= 0:
        raise ValueError(
            f"liquidity_depth_half must be > 0, got {liquidity_depth_half}")
    if not (0 <= liquidity_kappa_min <= liquidity_kappa_max <= 1):
        raise ValueError(
            f"liquidity kappa must satisfy 0 <= min <= max <= 1, got min={liquidity_kappa_min}, max={liquidity_kappa_max}")

    macro_sync_cfg = v2_cfg.get("macro_sync", {})
    macro_sync_enabled = macro_sync_cfg.get("enabled", True)
    macro_sync_anchors = macro_sync_cfg.get("anchors", ["BTCUSDT", "ETHUSDT"])
    macro_sync_window = macro_sync_cfg.get("window", 60)

    if not isinstance(macro_sync_enabled, bool):
        raise ValueError(
            f"macro_sync.enabled must be bool, got {macro_sync_enabled}")
    if not isinstance(macro_sync_anchors, list) or not all(isinstance(a, str) for a in macro_sync_anchors):
        raise ValueError(
            f"macro_sync.anchors must be list of strings, got {macro_sync_anchors}")
    if macro_sync_window <= 0:
        raise ValueError(
            f"macro_sync.window must be > 0, got {macro_sync_window}")

    return FeatureEngineeringConfig(
        enable_new_metrics=enable_new_metrics,
        ema_period_short=ema_period_short,
        ema_period_long=ema_period_long,
        ema_bias_clamp=ema_bias_clamp,
        volume_window_sec=volume_window_sec,
        volume_sma_length=volume_sma_length,
        volume_spike_cap=volume_spike_cap,
        volatility_window_sec=volatility_window_sec,
        volatility_sma_length=volatility_sma_length,
        volatility_ratio_cap=volatility_ratio_cap,
        liquidity_depth_half=liquidity_depth_half,
        liquidity_kappa_min=liquidity_kappa_min,
        liquidity_kappa_max=liquidity_kappa_max,
        macro_sync_enabled=macro_sync_enabled,
        macro_sync_anchors=macro_sync_anchors,
        macro_sync_window=macro_sync_window,
        source="config_v2"
    )


def resolve_feature_engineering_config(cfg: AuroraConfig) -> FeatureEngineeringConfig:
    """Resolve FeatureEngineeringConfig using config v2 domains only."""
    v2_cfg = _get_v2_features_cfg(cfg)
    if v2_cfg is None:
        msg = (
            "AuroraConfig.config_v2.domains['features'] is missing or empty. "
            "Regenerate config/domains/features.yaml via vfound schema and "
            "ensure docs/config_v2/specification.md is applied before loading."
        )
        logger.error(msg)
        raise ValueError(msg)

    try:
        return _build_features_from_v2(v2_cfg)
    except Exception as exc:
        msg = (
            "Invalid config/domains/features.yaml payload according to "
            "docs/config_v2/specification.md"
        )
        logger.error("%s: %s", msg, exc)
        raise ValueError(msg) from exc
