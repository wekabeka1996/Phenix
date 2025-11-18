from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

BASE_DOMAINS = (
    "market_data",
    "feature_engineering",
    "decision_making",
    "risk_management",
    "execution_position",
    "audit_trail",
)

PROFILE_DEFAULTS: Dict[str, Dict[str, str]] = {
    "full_testnet": {domain: "testnet" for domain in BASE_DOMAINS},
    "shadow_live": {
        "market_data": "live",
        "feature_engineering": "live",
        "decision_making": "live",
        "risk_management": "testnet",
        "execution_position": "testnet",
        "audit_trail": "live",
    },
    "full_live": {domain: "live" for domain in BASE_DOMAINS},
}

for profile, mapping in PROFILE_DEFAULTS.items():
    # Provide safe fallback for unknown domains
    if profile == "full_live":
        mapping.setdefault("__default__", "live")
    else:
        mapping.setdefault("__default__", "testnet")

LEGACY_MODE_ALIASES = {
    "hybrid_live_data_testnet_exec": "shadow_live",
    "hybrid_live_data_testnet_execution": "shadow_live",
    "hybrid": "shadow_live",
    "testnet": "full_testnet",
    "dev": "full_testnet",
    "production": "full_live",
    "live": "full_live",
}


@dataclass(frozen=True)
class EffectiveTradingModes:
    """Result of trading-mode resolution."""

    profile: str
    domain_modes: Dict[str, str]

    def for_domain(self, domain: str) -> str:
        return self.domain_modes.get(domain, self.domain_modes.get("__default__", "testnet"))


def _as_dict(section: Any) -> Dict[str, Any]:
    if isinstance(section, Mapping):
        return dict(section)
    if hasattr(section, "model_dump"):
        try:
            dumped = section.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:  # pragma: no cover - best effort fallback
            pass
    raw = getattr(section, "__dict__", None)
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    return {}


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _canonicalize_profile(raw_mode: Any) -> str:
    if isinstance(raw_mode, str):
        candidate = raw_mode.strip().lower()
        if not candidate:
            return "full_testnet"
        if candidate in PROFILE_DEFAULTS:
            return candidate
        return LEGACY_MODE_ALIASES.get(candidate, "full_testnet")
    return "full_testnet"


def _normalize_domain_mode(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip().lower()
    if not candidate:
        return ""
    if candidate in {"live", "full_live", "production"}:
        return "live"
    if candidate in {"testnet", "full_testnet", "dev"}:
        return "testnet"
    if candidate in {"shadow_live", "hybrid", "hybrid_live_data_testnet_exec", "hybrid_live_data_testnet_execution"}:
        # Domain-level shadow means follow profile defaults; treat as empty override
        return ""
    return candidate


def _collect_domain_overrides(config: Any, trading_section: Any) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    candidates = [
        _get_value(trading_section, "domain_configuration", {}),
        _get_value(config, "domain_configuration", {}),
    ]
    for candidate in candidates:
        candidate_dict = _as_dict(candidate)
        for domain, payload in candidate_dict.items():
            payload_dict = _as_dict(payload)
            raw_mode = _get_value(payload_dict, "trading_mode", None)
            normalized = _normalize_domain_mode(raw_mode)
            if normalized:
                overrides[domain] = normalized
    return overrides


def _get_v2_modes_cfg(config: Any) -> Optional[Dict[str, Any]]:
    """
    Повертає config_v2.modes, якщо він існує і непорожній.
    Якщо v2-config для modes відсутній — повертає None.
    """
    # Check if config is AuroraConfig with config_v2
    if not hasattr(config, 'config_v2') or config.config_v2 is None:
        return None
    modes = config.config_v2.modes
    if not isinstance(modes, dict) or not modes:
        return None
    return modes


def build_legacy_mode_mapping_from_v2(modes_cfg: Mapping[str, Any], profile_name: str) -> Dict[str, Any]:
    """
    Будує структуру, еквівалентну legacy trading.domain_configuration + trading.mode,
    на базі config v2 (modes.yaml).
    Used by config v2 migration.
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


# Alias for backward compatibility
_build_legacy_mode_mapping_from_v2 = build_legacy_mode_mapping_from_v2



def compute_effective_trading_modes_from_legacy_like(legacy_like_cfg: Dict[str, Any], config: Any) -> EffectiveTradingModes:
    """
    Compute modes using legacy logic but with provided legacy-like config.
    Used by config v2 migration to ensure proper Pydantic handling.
    """
    dict_config = {
        "trading": legacy_like_cfg.get("trading", {}),
        "trading_mode": legacy_like_cfg["trading"]["mode"]
    }
    return _compute_effective_trading_modes_legacy(dict_config)


def _compute_effective_trading_modes_legacy(config: Any) -> EffectiveTradingModes:
    """Legacy implementation of compute_effective_trading_modes."""
    trading_section = _get_value(config, "trading", {})
    profile = _canonicalize_profile(_get_value(
        trading_section, "mode", _get_value(config, "trading_mode", None)))
    profile_mapping = dict(PROFILE_DEFAULTS.get(
        profile, PROFILE_DEFAULTS["full_testnet"]))
    overrides = _collect_domain_overrides(config, trading_section)
    for domain, domain_mode in overrides.items():
        profile_mapping[domain] = domain_mode
    return EffectiveTradingModes(profile=profile, domain_modes=profile_mapping)


def compute_effective_trading_modes(config: Any) -> EffectiveTradingModes:
    """
    Compute effective trading modes with config v2 support and legacy fallback.

    Priority: config v2 (modes.yaml) -> legacy (trading.mode + trading.domain_configuration)
    """
    v2_cfg = _get_v2_modes_cfg(config)
    if v2_cfg is not None:
        try:
            # Get profile from legacy to use in v2
            trading_section = _get_value(config, "trading", {})
            profile = _canonicalize_profile(_get_value(
                trading_section, "mode", _get_value(config, "trading_mode", None)))
            legacy_like_cfg = build_legacy_mode_mapping_from_v2(
                v2_cfg, profile)
            result = compute_effective_trading_modes_from_legacy_like(
                legacy_like_cfg, config)
            return result
        except Exception as e:
            # Log warning and fallback to legacy
            # Note: No logger available here, so just fallback silently
            pass

    # Legacy path
    return _compute_effective_trading_modes_legacy(config)


def get_domain_mode_from_mapping(config: Any, domain: str) -> str:
    modes = compute_effective_trading_modes(config)
    return modes.for_domain(domain)
