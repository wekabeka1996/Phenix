"""
Configuration-driven sizing policy resolver.

This module provides dual-mode resolvers for sizing domain configurations,
supporting both config v2 (domains/sizing.yaml) and legacy (trading.decision.*) sources.
"""

import logging
from typing import Any, Optional, Dict, Mapping

from apps.reference.config_models import SizingPolicy

logger = logging.getLogger(__name__)


def _get_v2_sizing_cfg(cfg: Any) -> Optional[Dict[str, Any]]:
    """
    Повертає sizing-конфіг з cfg.config_v2.domains["sizing"], якщо він існує і не порожній.
    Якщо v2-конфіг відсутній або порожній — повертає None.
    """
    # Check if cfg is AuroraConfig with config_v2
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None
    domains = cfg.config_v2.domains
    if not isinstance(domains, dict) or "sizing" not in domains:
        return None
    sizing_cfg = domains["sizing"]
    if not isinstance(sizing_cfg, dict) or not sizing_cfg:
        return None
    return sizing_cfg


def _build_sizing_from_legacy(cfg: Any, symbol: str) -> SizingPolicy:
    """
    Читає всі потрібні поля для sizing з legacy trading.yaml (та інших legacy-конфігів),
    формує SizingPolicy. Семантика — 1:1 з поточною реалізацією.
    """
    # Extract sizing config from AuroraConfig or dict
    position_sizing = {}
    kelly = {}

    if hasattr(cfg, 'trading') and hasattr(cfg.trading, 'decision'):
        decision_cfg = cfg.trading.decision
        if hasattr(decision_cfg, 'position_sizing'):
            ps = decision_cfg.position_sizing
            if hasattr(ps, 'model_dump'):
                position_sizing = ps.model_dump()
            else:
                position_sizing = dict(ps) if hasattr(ps, '__dict__') else {}
        if hasattr(decision_cfg, 'kelly'):
            k = decision_cfg.kelly
            if hasattr(k, 'model_dump'):
                kelly = k.model_dump()
            else:
                kelly = dict(k) if hasattr(k, '__dict__') else {}
    elif isinstance(cfg, dict) and 'trading' in cfg and 'decision' in cfg['trading']:
        decision_cfg = cfg['trading']['decision']
        position_sizing = decision_cfg.get('position_sizing', {})
        kelly = decision_cfg.get('kelly', {})

    # Build policy
    risk_fraction_q = position_sizing.get('risk_fraction_q')
    mode = "fixed_risk_pct" if risk_fraction_q else "legacy_10pct"
    max_risk_pct = (risk_fraction_q * 100) if risk_fraction_q else 10.0
    max_risk_usd = 50.0  # Default, as not specified in legacy
    min_notional_usd = position_sizing.get('min_position_size_usd', 10.0)
    max_notional_usd = position_sizing.get('liquidity_based_cap_usd', 10000.0)
    liquidity_kappa = position_sizing.get('liquidity_kappa', 1.0)
    liquidity_kappa_mode = position_sizing.get(
        'liquidity_kappa_mode', 'static')

    return SizingPolicy(
        mode=mode,
        max_risk_pct=max_risk_pct,
        max_risk_usd=max_risk_usd,
        min_notional_usd=min_notional_usd,
        max_notional_usd=max_notional_usd,
        liquidity_kappa=liquidity_kappa,
        liquidity_kappa_mode=liquidity_kappa_mode,
        kelly=kelly if kelly else None,
        source="legacy"
    )


def _build_sizing_from_v2(v2_cfg: Mapping[str, Any], cfg: Any, symbol: str, regime: Optional[str] = None) -> SizingPolicy:
    """
    Будує SizingPolicy з config/domains/sizing.yaml.
    Враховує defaults, symbols[symbol], regimes (якщо є і якщо режим потрібен).
    """
    # Validate that v2 config has required fields
    defaults = v2_cfg.get("defaults", {})
    if not defaults:
        raise ValueError("v2 sizing config missing defaults section")

    # Get symbol overrides
    symbols = v2_cfg.get("symbols", {})
    symbol_cfg = symbols.get(symbol, {}) if symbols else {}

    # Get regime overrides
    regimes = v2_cfg.get("regimes", {})
    regime_cfg = regimes.get(regime, {}) if regime and regimes else {}

    # Merge: defaults -> symbol -> regime
    merged = dict(defaults)
    merged.update(symbol_cfg)
    merged.update(regime_cfg)

    # Validate required fields
    mode = merged.get("mode", "fixed_risk_pct")
    max_risk_pct = merged.get("max_risk_pct", 1.0)
    max_risk_usd = merged.get("max_risk_usd", 50.0)
    min_notional_usd = merged.get("min_notional_usd", 10.0)
    max_notional_usd = merged.get("max_notional_usd", 10000.0)
    liquidity_kappa = merged.get("liquidity_kappa", 1.0)
    liquidity_kappa_mode = merged.get("liquidity_kappa_mode", "static")
    kelly = merged.get("kelly")

    # Basic validation
    if max_risk_pct <= 0 or max_risk_usd <= 0 or min_notional_usd <= 0 or max_notional_usd <= 0:
        raise ValueError(
            f"Invalid sizing values: max_risk_pct={max_risk_pct}, max_risk_usd={max_risk_usd}, min_notional_usd={min_notional_usd}, max_notional_usd={max_notional_usd}")

    return SizingPolicy(
        mode=mode,
        max_risk_pct=max_risk_pct,
        max_risk_usd=max_risk_usd,
        min_notional_usd=min_notional_usd,
        max_notional_usd=max_notional_usd,
        liquidity_kappa=liquidity_kappa,
        liquidity_kappa_mode=liquidity_kappa_mode,
        kelly=kelly,
        source="config_v2"
    )


def resolve_sizing_policy(cfg: Any, symbol: str, regime: Optional[str] = None) -> SizingPolicy:
    """
    Resolve SizingPolicy with config v2 support and legacy fallback.

    Priority: config v2 (domains/sizing.yaml) -> legacy (trading.decision.*)
    """
    v2_cfg = _get_v2_sizing_cfg(cfg)
    if v2_cfg is not None:
        try:
            policy = _build_sizing_from_v2(v2_cfg, cfg, symbol, regime)
            return policy
        except Exception as e:
            logger.warning(
                "Failed to build sizing policy from v2, falling back to legacy: %s", e)
            return _build_sizing_from_legacy(cfg, symbol)
    else:
        return _build_sizing_from_legacy(cfg, symbol)
