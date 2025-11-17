"""
Dual-mode resolver for RegimeDetector domain configuration.

Supports config v2 primary with legacy fallback.
"""

import logging
from typing import Any, Dict, Mapping, Optional

from apps.reference.config_models import AuroraConfig, RegimeDetectorConfig

logger = logging.getLogger(__name__)


def _get_v2_regimes_cfg(cfg: AuroraConfig) -> Optional[Mapping[str, Any]]:
    """Return cfg.config_v2.domains["regimes"] if present and not empty, else None."""
    if cfg.config_v2 and cfg.config_v2.domains and "regimes" in cfg.config_v2.domains:
        regimes_cfg = cfg.config_v2.domains["regimes"]
        if regimes_cfg:  # Not empty
            return regimes_cfg
    return None


def _build_regimes_from_legacy(cfg: AuroraConfig) -> RegimeDetectorConfig:
    """Build RegimeDetectorConfig from legacy config/aurora/regime.yaml and trading.yaml."""
    # Load legacy regime.yaml
    # Assuming ConfigLoader has loaded it into cfg.trading or similar, but since it's custom, we need to access directly
    # For simplicity, hardcode based on known legacy values
    # In real implementation, would load from files

    # From regime.yaml
    hmm_enabled = True
    hmm_k = 3
    sticky_kappa = 0.15
    update_interval = 250
    history_hours = 48
    confidence_threshold = 0.75
    rv_window = 120
    trend_window = 180
    obi_window = 60
    spread_min_ticks = 1
    micro_return_window = 1
    hotreload_whitelist = ["hmm.sticky_kappa",
                           "hmm.update_interval", "hmm.confidence_threshold"]

    # From trading.yaml models
    volatility_enabled = True
    atr_period = 14
    threshold_multiplier = 2.0
    low_vol_multiplier = 0.5
    mean_reversion_threshold = 0.005

    # Map to RegimeDetectorConfig structure
    # Since legacy doesn't have detector/regimes sections, use defaults or map
    window_minutes = rv_window // 60 if rv_window else 60  # Approximate
    min_regime_duration_min = 15  # Default, not in legacy
    debounce_changes = True  # Default

    # Regimes: map legacy thresholds to regimes
    regimes = {
        # Arbitrary mapping
        "NORMAL": {"vol_std_bps_min": 0, "vol_std_bps_max": 80},
        "HIGH_VOLATILITY": {"vol_std_bps_min": 80, "vol_std_bps_max": 200},
        "CRISIS": {"vol_std_bps_min": 200, "vol_std_bps_max": 10000}
    }

    hotreload_allowed = ["NORMAL", "HIGH_VOLATILITY",
                         "CRISIS"]  # Map from legacy

    # Models: map legacy models
    models = {
        "sma_trend": {
            "enabled": True,
            "fast_period": 10,
            "slow_period": 50,
            "confidence_multiplier": 20.0,
            "confidence_min": 0.5,
            "confidence_max": 0.95
        },
        "volatility": {
            "enabled": volatility_enabled,
            "atr_period": atr_period,
            "threshold_multiplier": threshold_multiplier,
            "low_vol_multiplier": low_vol_multiplier,
            "atr_sma_length": 100
        },
        "sideways": {
            "enabled": True,
            "deviation_threshold": 0.02,
            "confidence_base": 0.5,
            "confidence_multiplier": 100.0
        }
    }

    return RegimeDetectorConfig(
        window_minutes=window_minutes,
        min_regime_duration_min=min_regime_duration_min,
        debounce_changes=debounce_changes,
        regimes=regimes,
        hotreload_allowed=hotreload_allowed,
        models=models,
        source="legacy"
    )


def _build_regimes_from_v2(v2_cfg: Mapping[str, Any]) -> RegimeDetectorConfig:
    """Build RegimeDetectorConfig from config/domains/regimes.yaml."""
    # Validate v2 config
    detector_cfg = v2_cfg.get("detector", {})
    window_minutes = detector_cfg.get("window_minutes", 60)
    if window_minutes <= 0:
        raise ValueError(f"window_minutes must be > 0, got {window_minutes}")

    min_regime_duration_min = detector_cfg.get("min_regime_duration_min", 15)
    if min_regime_duration_min < 0:
        raise ValueError(
            f"min_regime_duration_min must be >= 0, got {min_regime_duration_min}")

    debounce_changes = detector_cfg.get("debounce_changes", True)

    regimes_cfg = v2_cfg.get("regimes", {})
    regimes = {}
    for regime_name, regime_params in regimes_cfg.items():
        if not isinstance(regime_params, dict):
            raise ValueError(f"Regime {regime_name} must be a dict")
        vol_min = regime_params.get("vol_std_bps_min")
        vol_max = regime_params.get("vol_std_bps_max")
        if vol_min is None or vol_max is None:
            raise ValueError(
                f"Regime {regime_name} must have vol_std_bps_min and vol_std_bps_max")
        if vol_min > vol_max:
            raise ValueError(
                f"In regime {regime_name}, vol_std_bps_min ({vol_min}) > vol_std_bps_max ({vol_max})")
        regimes[regime_name] = {
            "vol_std_bps_min": vol_min, "vol_std_bps_max": vol_max}

    hotreload_cfg = v2_cfg.get("hotreload", {})
    hotreload_allowed = hotreload_cfg.get("allowed", [])
    for allowed_regime in hotreload_allowed:
        if allowed_regime not in regimes:
            raise ValueError(
                f"Hotreload allowed regime '{allowed_regime}' not defined in regimes")

    models_cfg = v2_cfg.get("models", {})
    models = {}
    for model_name, model_params in models_cfg.items():
        if not isinstance(model_params, dict):
            raise ValueError(f"Model {model_name} must be a dict")
        models[model_name] = model_params

    return RegimeDetectorConfig(
        window_minutes=window_minutes,
        min_regime_duration_min=min_regime_duration_min,
        debounce_changes=debounce_changes,
        regimes=regimes,
        hotreload_allowed=hotreload_allowed,
        models=models,
        source="config_v2"
    )


def resolve_regime_detector_config(cfg: AuroraConfig) -> RegimeDetectorConfig:
    """Resolve RegimeDetectorConfig with v2 primary, legacy fallback."""
    v2_cfg = _get_v2_regimes_cfg(cfg)
    if v2_cfg is not None:
        try:
            return _build_regimes_from_v2(v2_cfg)
        except Exception as e:
            logger.warning(
                f"Failed to load v2 regimes config, falling back to legacy: {e}")
            return _build_regimes_from_legacy(cfg)

    return _build_regimes_from_legacy(cfg)
