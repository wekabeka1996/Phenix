"""
Configuration-driven decision policy resolver.

This module provides dual-mode resolvers for decision domain configurations,
supporting both config v2 (domains/decision.yaml) and legacy (trading.decision.*) sources.
"""

import logging
from typing import Any, Optional, Mapping

from apps.reference.config_models import DecisionPolicy

logger = logging.getLogger(__name__)


def _get_v2_decision_cfg(cfg: Any) -> Optional[Mapping[str, Any]]:
    """
    Повертає cfg.config_v2.domains["decision"], якщо він існує і не порожній.
    Якщо v2-конфіг відсутній або порожній — повертає None.
    """
    # Check if cfg is AuroraConfig with config_v2
    if not hasattr(cfg, 'config_v2') or cfg.config_v2 is None:
        return None
    domains = cfg.config_v2.domains
    if not isinstance(domains, dict) or "decision" not in domains:
        return None
    decision_cfg = domains["decision"]
    if not isinstance(decision_cfg, dict) or not decision_cfg:
        return None
    return decision_cfg


def _build_decision_from_legacy(cfg: Any) -> DecisionPolicy:
    """
    Читає всі потрібні поля для decision з legacy trading.yaml,
    формує DecisionPolicy. Семантика — 1:1 з поточною реалізацією.
    """
    # Extract decision config from AuroraConfig or dict
    if hasattr(cfg, 'trading') and hasattr(cfg.trading, 'decision'):
        decision_cfg = cfg.trading.decision
    elif isinstance(cfg, dict) and 'trading' in cfg and 'decision' in cfg['trading']:
        decision_cfg = cfg['trading']['decision']
    else:
        decision_cfg = {}

    # Get qos
    qos = {}
    if hasattr(decision_cfg, 'qos'):
        qos = decision_cfg.qos
    elif isinstance(decision_cfg, dict) and 'qos' in decision_cfg:
        qos = decision_cfg['qos']

    # Build policy
    signal_threshold = decision_cfg.get('signal_threshold', 0.2) if isinstance(
        decision_cfg, dict) else getattr(decision_cfg, 'signal_threshold', 0.2)
    neutral_threshold = decision_cfg.get('neutral_threshold', 0.3) if isinstance(
        decision_cfg, dict) else getattr(decision_cfg, 'neutral_threshold', 0.3)
    max_intents_per_minute_per_symbol = qos.get('max_intents_per_minute_per_symbol', 10) if isinstance(
        qos, dict) else getattr(qos, 'max_intents_per_minute_per_symbol', 10)
    symbol_intent_cooldown_sec = qos.get('symbol_intent_cooldown_sec', 3) if isinstance(
        qos, dict) else getattr(qos, 'symbol_intent_cooldown_sec', 3)
    exposure_block_cooldown_sec = qos.get('exposure_block_cooldown_sec', 60) if isinstance(
        qos, dict) else getattr(qos, 'exposure_block_cooldown_sec', 60)

    return DecisionPolicy(
        signal_threshold=signal_threshold,
        neutral_threshold=neutral_threshold,
        max_intents_per_minute_per_symbol=max_intents_per_minute_per_symbol,
        symbol_intent_cooldown_sec=symbol_intent_cooldown_sec,
        exposure_block_cooldown_sec=exposure_block_cooldown_sec,
        source="legacy"
    )


def _build_decision_from_v2(v2_cfg: Mapping[str, Any]) -> DecisionPolicy:
    """
    Будує DecisionPolicy з config/domains/decision.yaml.
    """
    # Validate that v2 config has required fields
    thresholds = v2_cfg.get("thresholds", {})
    qos = v2_cfg.get("qos", {})

    # Get values
    signal_threshold = thresholds.get("signal_threshold", 0.2)
    neutral_threshold = thresholds.get("neutral_threshold", 0.3)
    max_intents_per_minute_per_symbol = qos.get(
        "max_intents_per_minute_per_symbol", 10)
    symbol_intent_cooldown_sec = qos.get("symbol_intent_cooldown_sec", 3)
    exposure_block_cooldown_sec = qos.get("exposure_block_cooldown_sec", 60)

    # Basic validation
    if signal_threshold < 0 or neutral_threshold < 0 or max_intents_per_minute_per_symbol < 0 or symbol_intent_cooldown_sec < 0 or exposure_block_cooldown_sec < 0:
        raise ValueError("Invalid decision values: must be non-negative")

    return DecisionPolicy(
        signal_threshold=signal_threshold,
        neutral_threshold=neutral_threshold,
        max_intents_per_minute_per_symbol=max_intents_per_minute_per_symbol,
        symbol_intent_cooldown_sec=symbol_intent_cooldown_sec,
        exposure_block_cooldown_sec=exposure_block_cooldown_sec,
        source="config_v2"
    )


def resolve_decision_policy(cfg: Any) -> DecisionPolicy:
    """
    Resolve DecisionPolicy with config v2 support and legacy fallback.

    Priority: config v2 (domains/decision.yaml) -> legacy (trading.decision.*)
    """
    v2_cfg = _get_v2_decision_cfg(cfg)
    if v2_cfg is not None:
        try:
            policy = _build_decision_from_v2(v2_cfg)
            return policy
        except Exception as e:
            logger.warning(
                "Failed to build decision policy from v2, falling back to legacy: %s", e)
            return _build_decision_from_legacy(cfg)
    else:
        return _build_decision_from_legacy(cfg)
