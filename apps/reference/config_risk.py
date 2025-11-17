"""Configuration-driven risk management resolvers."""

import logging
from typing import Any, Optional, Dict, Mapping

from apps.reference.config_models import (
    RiskSoftLimits,
    RiskScoreWeights,
    TradingAllowedThresholds,
)
from apps.reference.domains.risk_management.daily_gate import DailyRiskState

logger = logging.getLogger(__name__)


def _get_v2_risk_cfg(cfg: Any) -> Optional[Dict[str, Any]]:
    """
    Повертає risk-конфіг з cfg.config_v2.domains["risk"], якщо він існує і не порожній.
    Якщо v2-конфіг відсутній або порожній — повертає None.
    """
    # Check if cfg is AuroraConfig with config_v2
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None
    domains = cfg.config_v2.domains
    if not isinstance(domains, dict) or "risk" not in domains:
        return None
    risk_cfg = domains["risk"]
    if not isinstance(risk_cfg, dict) or not risk_cfg:
        return None
    return risk_cfg


def _extract_legacy_risk(cfg: Any) -> Mapping[str, Any]:
    """Return trading.risk section (dict-like) from AuroraConfig or raw dict."""
    if hasattr(cfg, "trading") and getattr(cfg.trading, "risk", None):
        return cfg.trading.risk
    if isinstance(cfg, dict):
        return cfg.get("trading", {}).get("risk", {})
    return {}


def _to_float(value: Any, default: float) -> float:
    """Best-effort float conversion with default fallback."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _ensure_mapping(section: Any) -> Mapping[str, Any]:
    if isinstance(section, Mapping):
        return section
    if hasattr(section, "model_dump"):
        return section.model_dump()
    if hasattr(section, "__dict__"):
        return section.__dict__
    return {}


def _extract_global_risk_weights(cfg: Any) -> Mapping[str, Any]:
    """Return top-level risk_score_weights mapping when present."""
    if hasattr(cfg, "risk_score_weights"):
        section = getattr(cfg, "risk_score_weights", None)
        if section:
            return _ensure_mapping(section)
    if isinstance(cfg, dict):
        section = cfg.get("risk_score_weights")
        if section:
            return _ensure_mapping(section)
    return {}


def _build_risk_from_legacy(cfg: Any) -> DailyRiskState:
    """
    Поточна логіка: читає trading.risk.* / system.* як зараз.
    Не міняєш ні значень, ні семантики — просто виносиш у функцію.
    """
    # Extract risk config from AuroraConfig or dict
    if hasattr(cfg, 'trading') and hasattr(cfg.trading, 'risk'):
        risk_cfg = cfg.trading.risk
    elif isinstance(cfg, dict) and 'risk' in cfg:
        risk_cfg = cfg['risk']
    else:
        risk_cfg = {}

    # Wrap in dict format expected by DailyRiskState
    config_dict = {"risk": risk_cfg}
    return DailyRiskState(config_dict, logger=logger)


def _build_risk_from_v2(v2_cfg: Mapping[str, Any], cfg: Any) -> DailyRiskState:
    """
    Нова логіка: будує DailyRiskState з config/domains/risk.yaml.
    """
    # Validate that v2 config has required fields
    daily_limits = v2_cfg.get("daily_limits", {})
    if not daily_limits:
        raise ValueError("v2 risk config missing daily_limits section")

    # Check if key fields are present and can be converted to valid numbers
    max_loss = daily_limits.get("max_loss_usd")
    max_drawdown = daily_limits.get("max_drawdown_pct")

    # Try to validate by attempting to build
    try:
        # Convert v2 config to the format expected by DailyRiskState
        risk_dict = dict(v2_cfg)  # Make a copy

        # Ensure it's in the format DailyRiskState expects: {"risk": {...}}
        config_dict = {"risk": risk_dict}
        state = DailyRiskState(config_dict, logger=logger)

        # Validate that we got non-default values (indicating valid config)
        if state.cfg.max_realized_loss_usd == 250.0 and state.cfg.max_drawdown_pct == 8.0:
            # All defaults, likely invalid config
            raise ValueError("v2 risk config resulted in all default values")

        return state
    except Exception as e:
        raise ValueError(f"Invalid v2 risk config: {e}") from e


def _build_soft_limits_from_v2(risk_cfg: Mapping[str, Any]) -> RiskSoftLimits:
    section = _ensure_mapping(risk_cfg.get("soft_limits"))
    if not section:
        raise ValueError("risk.soft_limits missing in config v2")

    clip_min = _to_float(section.get("clip_min_notional_usdt"), 10.0)
    dir_ratio = _to_float(section.get("directional_ratio_max"), 3.0)
    side_exp = _to_float(section.get("side_exposure_usdt"), 600.0)
    margin_exp = _to_float(section.get("margin_exposure_usdt"), 1100.0)

    if clip_min <= 0:
        raise ValueError("clip_min_notional_usdt must be > 0")
    if dir_ratio < 1.0:
        raise ValueError("directional_ratio_max must be >= 1.0")
    if side_exp <= 0 or margin_exp <= 0:
        raise ValueError("soft limit exposures must be > 0")

    return RiskSoftLimits(
        mode=str(section.get("mode", "clip")),
        clip_min_notional_usdt=clip_min,
        directional_ratio_max=dir_ratio,
        side_exposure_usdt=side_exp,
        margin_exposure_usdt=margin_exp,
        source="config_v2",
    )


def _build_soft_limits_from_legacy(cfg: Any) -> RiskSoftLimits:
    legacy = _ensure_mapping(_extract_legacy_risk(cfg))
    section = _ensure_mapping(legacy.get("soft_limits"))

    # Legacy typo support: clip_min_notional_usdt/clip_min_notional_usd
    clip_min_value = section.get("clip_min_notional_usdt") or section.get(
        "clip_min_notional_usd", 10.0)

    return RiskSoftLimits(
        mode=str(section.get("mode", "clip")),
        clip_min_notional_usdt=_to_float(clip_min_value, 10.0),
        directional_ratio_max=_to_float(
            section.get("directional_ratio_max"), 3.0),
        side_exposure_usdt=_to_float(section.get("side_exposure_usdt"), 600.0),
        margin_exposure_usdt=_to_float(
            section.get("margin_exposure_usdt"), 1100.0),
        source="legacy",
    )


def _build_score_weights_from_v2(risk_cfg: Mapping[str, Any]) -> RiskScoreWeights:
    section = _ensure_mapping(risk_cfg.get("score_weights"))
    if not section:
        raise ValueError("risk.score_weights missing in config v2")

    delta_price = _to_float(section.get("delta_price_pct"), 0.1)
    obi = _to_float(section.get("obi"), 0.3)
    tfi = _to_float(section.get("tfi"), 0.3)
    absorption = _to_float(section.get("absorption_inverse"), 0.3)

    for name, value in {
        "delta_price_pct": delta_price,
        "obi": obi,
        "tfi": tfi,
        "absorption_inverse": absorption,
    }.items():
        if value < 0:
            raise ValueError(f"risk.score_weights.{name} must be >= 0")

    return RiskScoreWeights(
        delta_price_pct=delta_price,
        obi=obi,
        tfi=tfi,
        absorption_inverse=absorption,
        source="config_v2",
    )


def _build_score_weights_from_legacy(cfg: Any) -> RiskScoreWeights:
    legacy = _ensure_mapping(_extract_legacy_risk(cfg))
    section = _ensure_mapping(legacy.get("score_weights"))

    if not section:
        section = _extract_global_risk_weights(cfg)

    # Legacy key was delta_price
    delta_price_value = section.get(
        "delta_price_pct") or section.get("delta_price")

    return RiskScoreWeights(
        delta_price_pct=_to_float(delta_price_value, 0.1),
        obi=_to_float(section.get("obi"), 0.3),
        tfi=_to_float(section.get("tfi"), 0.3),
        absorption_inverse=_to_float(section.get("absorption_inverse"), 0.3),
        source="legacy",
    )


def _build_thresholds_from_v2(risk_cfg: Mapping[str, Any]) -> TradingAllowedThresholds:
    section = _ensure_mapping(risk_cfg.get("trading_allowed_thresholds"))
    if not section:
        raise ValueError(
            "risk.trading_allowed_thresholds missing in config v2")

    max_score = _to_float(section.get("max_risk_score"), -1)
    if not 0 <= max_score <= 1:
        raise ValueError("max_risk_score must be within [0, 1]")

    overrides_cfg = _ensure_mapping(section.get("overrides"))
    overrides: Optional[Dict[str, float]] = None
    if overrides_cfg:
        overrides = {}
        for profile, value in overrides_cfg.items():
            next_value = _to_float(value, -1)
            if not 0 <= next_value <= 1:
                raise ValueError(
                    f"override {profile} must be within [0, 1], got {value}")
            overrides[profile] = next_value

    return TradingAllowedThresholds(
        max_risk_score=max_score,
        overrides=overrides,
        source="config_v2",
    )


def _build_thresholds_from_legacy(cfg: Any) -> TradingAllowedThresholds:
    legacy = _ensure_mapping(_extract_legacy_risk(cfg))
    section = _ensure_mapping(legacy.get("trading_allowed_thresholds"))
    default_score = _to_float(section.get("max_risk_score"), 0.8)

    overrides: Optional[Dict[str, float]] = None
    for profile in ("testnet", "production"):
        profile_cfg = _ensure_mapping(legacy.get(profile))
        profile_score = _to_float(profile_cfg.get("max_risk_score"), -1)
        if profile_score >= 0:
            overrides = overrides or {}
            overrides[profile] = profile_score

    return TradingAllowedThresholds(
        max_risk_score=default_score,
        overrides=overrides,
        source="legacy",
    )


def resolve_daily_risk_state(cfg: Any) -> DailyRiskState:
    """
    Resolve DailyRiskState with config v2 support and legacy fallback.

    Priority: config v2 (domains/risk.yaml) -> legacy (trading.risk.*)
    """
    v2_cfg = _get_v2_risk_cfg(cfg)
    if v2_cfg is not None:
        try:
            risk_state = _build_risk_from_v2(v2_cfg, cfg)
            return risk_state
        except Exception as e:
            logger.warning(
                "Failed to build risk state from v2, falling back to legacy: %s", e)
            return _build_risk_from_legacy(cfg)
    else:
        return _build_risk_from_legacy(cfg)


def resolve_risk_soft_limits(cfg: Any) -> RiskSoftLimits:
    """Resolve risk.soft_limits with config v2 priority."""
    v2_cfg = _get_v2_risk_cfg(cfg)
    if v2_cfg is not None:
        try:
            return _build_soft_limits_from_v2(v2_cfg)
        except Exception as exc:
            logger.warning(
                "risk.soft_limits v2 invalid (%s), falling back to legacy", exc)
    return _build_soft_limits_from_legacy(cfg)


def resolve_risk_score_weights(cfg: Any) -> RiskScoreWeights:
    """Resolve risk.score_weights with config v2 priority."""
    v2_cfg = _get_v2_risk_cfg(cfg)
    if v2_cfg is not None:
        try:
            return _build_score_weights_from_v2(v2_cfg)
        except Exception as exc:
            logger.warning(
                "risk.score_weights v2 invalid (%s), falling back to legacy", exc)
    return _build_score_weights_from_legacy(cfg)


def resolve_trading_allowed_thresholds(cfg: Any) -> TradingAllowedThresholds:
    """Resolve trading_allowed_thresholds with config v2 priority."""
    v2_cfg = _get_v2_risk_cfg(cfg)
    if v2_cfg is not None:
        try:
            return _build_thresholds_from_v2(v2_cfg)
        except Exception as exc:
            logger.warning(
                "risk.trading_allowed_thresholds v2 invalid (%s), falling back to legacy", exc)
    return _build_thresholds_from_legacy(cfg)
