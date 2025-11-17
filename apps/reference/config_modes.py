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


def _build_legacy_mode_mapping_from_v2(modes_cfg: Mapping[str, Any], profile_name: str) -> Dict[str, Any]:
    """
    Будує структуру, еквівалентну legacy trading.domain_configuration + trading.mode,
    на базі config v2 (modes.yaml).
    """
    profiles = modes_cfg.get("profiles", {})
    if profile_name not in profiles:
        # Fallback to default if profile not found
        if "default" in profiles:
            profile_name = "default"
        elif profiles:
            profile_name = next(iter(profiles.keys()))
        else:
            raise ValueError("No profiles found in v2 modes config")

    profile = profiles[profile_name]
    if not isinstance(profile, dict):
        raise ValueError(f"Invalid profile structure for {profile_name}")

    # Extract trading_mode and domains
    trading_mode = profile.get("trading_mode", "testnet")
    domains = profile.get("domains", {})

    # Build legacy-like structure
    legacy_like = {
        "trading": {
            "mode": trading_mode,
            "domain_configuration": {}
        }
    }

    # Convert domains to legacy format
    for domain, mode in domains.items():
        legacy_like["trading"]["domain_configuration"][domain] = {
            "trading_mode": mode
        }

    return legacy_like


def _compute_effective_trading_modes_from_legacy_like(legacy_like_cfg: Dict[str, Any], cfg: Any) -> EffectiveTradingModes:
    """
    Compute modes using legacy logic but with provided legacy-like config.
    """
    # Temporarily patch the config for legacy function
    original_trading = getattr(cfg, 'trading', None)
    original_trading_mode = getattr(cfg, 'trading_mode', None)

    # Set the legacy-like values
    if hasattr(cfg, 'trading'):
        cfg.trading = legacy_like_cfg.get('trading', {})
    else:
        cfg['trading'] = legacy_like_cfg.get('trading', {})

    if 'trading_mode' in legacy_like_cfg.get('trading', {}):
        cfg['trading_mode'] = legacy_like_cfg['trading']['mode']

    try:
        result = _legacy_compute_effective_trading_modes(cfg)
        return result
    finally:
        # Restore original values
        if hasattr(cfg, 'trading'):
            cfg.trading = original_trading
        if hasattr(cfg, 'trading_mode'):
            cfg.trading_mode = original_trading_mode
        elif 'trading_mode' in cfg:
            del cfg['trading_mode']


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
            legacy_like_cfg = _build_legacy_mode_mapping_from_v2(
                v2_cfg, profile)
            result = _compute_effective_trading_modes_from_legacy_like(
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
