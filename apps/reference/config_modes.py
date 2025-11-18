"""
Configuration-driven trading modes resolution.

This module provides dual-mode resolvers for trading modes and domain configurations,
supporting both config v2 (modes.yaml) and legacy (trading.mode + trading.domain_configuration) sources.
"""

import logging
from typing import Any, Optional, Dict, Mapping

from apps.reference.utils.trading_modes import (
    EffectiveTradingModes,
    compute_effective_trading_modes as _legacy_compute_effective_trading_modes,
    get_domain_mode_from_mapping as _legacy_get_domain_mode_from_mapping,
    _canonicalize_profile,
    build_legacy_mode_mapping_from_v2,
    compute_effective_trading_modes_from_legacy_like,
)

logger = logging.getLogger(__name__)


def _get_v2_modes_cfg(cfg: Any) -> Optional[Dict[str, Any]]:
    """
    Повертає cfg.config_v2.modes, якщо він існує і непорожній.
    Якщо v2-config для modes відсутній — повертає None.
    """
    # Check if cfg is AuroraConfig with config_v2
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None
    modes = cfg.config_v2.modes
    if not isinstance(modes, dict) or not modes:
        return None
    return modes


def compute_effective_trading_modes(cfg: Any) -> EffectiveTradingModes:
    """
    Compute effective trading modes with config v2 support and legacy fallback.

    Priority: config v2 (modes.yaml) -> legacy (trading.mode + trading.domain_configuration)
    """
    v2_cfg = _get_v2_modes_cfg(cfg)
    if v2_cfg is not None:
        try:
            # Get profile from legacy to use in v2
            trading_section = getattr(cfg, 'trading', {}) if hasattr(
                cfg, 'trading') else cfg.get('trading', {})
            profile = _canonicalize_profile(
                trading_section.get('mode', cfg.get(
                    'trading_mode', 'full_testnet'))
            )
            legacy_like_cfg = build_legacy_mode_mapping_from_v2(
                v2_cfg, profile)
            result = compute_effective_trading_modes_from_legacy_like(
                legacy_like_cfg, cfg)
            return result
        except Exception as e:
            logger.warning(
                "Failed to build trading modes from v2, falling back to legacy: %s", e)
            return _legacy_compute_effective_trading_modes(cfg)
    else:
        return _legacy_compute_effective_trading_modes(cfg)


def get_domain_mode_from_mapping(cfg: Any, domain: str) -> str:
    """
    Get domain mode from effective trading modes mapping.

    Uses the dual-mode compute_effective_trading_modes internally.
    """
    modes = compute_effective_trading_modes(cfg)
    return modes.for_domain(domain)
