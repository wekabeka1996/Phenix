"""Trading modes utilities for domain-specific mode resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

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
    "full_live": {domain: "live" for domain in BASE_DOMAINS},
    # NEW: Legitimize backtest mode
    "backtest": {domain: "backtest" for domain in BASE_DOMAINS},
    "hybrid_live_data_testnet_exec": {
        "market_data": "live",
        "feature_engineering": "live",
        "decision_making": "live",
        "risk_management": "testnet",
        "execution_position": "testnet",
        "audit_trail": "live",
    },
}

for profile, mapping in PROFILE_DEFAULTS.items():
    # Provide safe fallback for unknown domains
    if profile == "full_live":
        mapping.setdefault("__default__", "live")
    elif profile == "hybrid_live_data_testnet_exec":
        mapping.setdefault("__default__", "testnet")
    else:
        mapping.setdefault("__default__", "testnet")


@dataclass(frozen=True)
class EffectiveTradingModes:
    """Result of trading-mode resolution."""

    profile: str
    domain_modes: Dict[str, str]

    def for_domain(self, domain: str) -> str:
        return self.domain_modes.get(domain, self.domain_modes.get("__default__", "testnet"))


def _as_dict(section: Any) -> Dict[str, Any]:
    from collections.abc import Mapping
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
    from collections.abc import Mapping
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _canonicalize_profile(raw_mode: Any) -> str:
    """
    Canonicalize trading mode profile name.

    FAIL-CLOSED: Raises ValueError for unknown or empty modes.
    Valid profiles: full_testnet, full_live, hybrid_live_data_testnet_exec, backtest
    """
    if not isinstance(raw_mode, str) or not raw_mode.strip():
        raise ValueError("Trading mode cannot be empty or None")

    candidate = raw_mode.strip().lower()

    if candidate in PROFILE_DEFAULTS:
        return candidate

    raise ValueError(
        f"Unknown trading mode: '{candidate}'. "
        f"Valid modes: {list(PROFILE_DEFAULTS.keys())}"
    )


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
    if candidate in {"backtest", "simulation", "sim"}:
        return "backtest"
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


def compute_effective_trading_modes(config: Any) -> EffectiveTradingModes:
    """
    Compute effective trading modes from configuration.

    Reads trading.mode or trading_mode from config and resolves
    domain-specific overrides from trading.domain_configuration.

    FAIL-CLOSED: Raises ValueError for unknown/empty trading modes.
    """
    trading_section = _get_value(config, "trading", {})
    raw_mode = _get_value(trading_section, "mode",
                          _get_value(config, "trading_mode", None))

    profile = _canonicalize_profile(raw_mode)
    profile_mapping = dict(PROFILE_DEFAULTS[profile])

    overrides = _collect_domain_overrides(config, trading_section)
    for domain, domain_mode in overrides.items():
        profile_mapping[domain] = domain_mode

    return EffectiveTradingModes(profile=profile, domain_modes=profile_mapping)


def get_domain_mode_from_mapping(config: Any, domain: str) -> str:
    """Get the trading mode for a specific domain."""
    modes = compute_effective_trading_modes(config)
    return modes.for_domain(domain)
