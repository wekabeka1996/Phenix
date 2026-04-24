from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.reference.config_models import AuroraConfig
from apps.reference.domain_config import DomainConfigResolver


@dataclass(frozen=True)
class DMConfigSpec:
    """Constructor-only projection of DecisionMaking config branches."""

    strategies_registry: Any
    tca_prefs: Any
    risk_budgets: Any
    fail_closed_on_degraded_context: bool
    degraded_context_critical_keys: set[str]
    degraded_context_critical_keys_by_strategy: dict[str, set[str]]
    degraded_context_contracts_by_strategy: dict[str, dict[str, Any]]
    min_pos_size_usd: Decimal
    liq_cap_usd: Decimal
    qos_exposure_block_cooldown_sec: int
    qos_max_intents_per_minute_per_symbol: int
    qos_mode: str
    default_symbol_cooldown_sec: int
    qos_enforce: bool
    qos_apply_to_strategies: set[str]
    arming_require_regime_warmup: bool
    arming_retry_backoff_ms: int
    arming_max_attempts: int
    features_ttl_sec: float
    flip_global_enabled: bool
    bar_gating_enabled: bool
    bar_ms: int
    behavior_enabled: bool
    normalize_signals_mode: str

    @classmethod
    def load(
        cls,
        config: AuroraConfig,
        *,
        dm_cfg: Any | None = None,
    ) -> "DMConfigSpec":
        """Load the exact config-derived constructor surface without reinterpretation.

        ``dm_cfg`` exists only to preserve the historical DecisionMaking
        constructor seam where callers and tests patched the resolver inside
        decision_making.py before P3.D extracted this projection helper.
        """
        if isinstance(config, dict):
            raise TypeError("DMConfigSpec requires AuroraConfig, got dict")

        strategies_registry = None
        if hasattr(config, "strategies_registry") and config.strategies_registry:
            strategies_registry = config.strategies_registry

        trading_config = getattr(config, "trading", config)
        tca_prefs = getattr(trading_config, "tca_prefs", {})
        risk_budgets = getattr(trading_config, "risk_budgets", {})

        if dm_cfg is None:
            resolver = DomainConfigResolver(config)
            dm_cfg = resolver.get_decision_making()
        qos_cfg = dm_cfg.qos

        fail_closed_on_degraded_context = bool(
            getattr(dm_cfg, "fail_closed_on_degraded_context", False)
        )

        try:
            raw_critical_keys = list(
                getattr(dm_cfg, "degraded_context_critical_keys", []) or []
            )
        except Exception:
            raw_critical_keys = []
        degraded_context_critical_keys = {
            str(key) for key in raw_critical_keys if str(key)
        }

        try:
            raw_critical_keys_by_strategy = getattr(
                dm_cfg, "degraded_context_critical_keys_by_strategy", {}
            ) or {}
        except Exception:
            raw_critical_keys_by_strategy = {}
        degraded_context_critical_keys_by_strategy = {
            str(strategy_id): {str(key) for key in (keys or []) if str(key)}
            for strategy_id, keys in (
                raw_critical_keys_by_strategy.items()
                if isinstance(raw_critical_keys_by_strategy, dict)
                else []
            )
        }

        try:
            raw_contracts = getattr(
                dm_cfg, "degraded_context_contracts_by_strategy", {}
            ) or {}
        except Exception:
            raw_contracts = {}
        degraded_context_contracts_by_strategy: dict[str, dict[str, Any]] = {}
        if isinstance(raw_contracts, dict):
            for strategy_id, contract in raw_contracts.items():
                enabled = bool(getattr(contract, "enabled", False))
                critical_keys_raw = list(
                    getattr(contract, "critical_keys", []) or [])
                degraded_context_contracts_by_strategy[str(strategy_id)] = {
                    "enabled": enabled,
                    "critical_keys": {
                        str(key) for key in critical_keys_raw if str(key)
                    },
                }

        try:
            raw_apply_to = list(
                getattr(qos_cfg, "apply_to_strategies", []) or [])
        except Exception:
            raw_apply_to = []
        qos_apply_to_strategies = {
            str(strategy_id) for strategy_id in raw_apply_to if str(strategy_id)}

        # normalize_signals_mode is mirrored for observability and must keep the
        # partial-mock fallback exactly as the constructor currently does.
        try:
            aurora_cfg = getattr(
                getattr(config, "strategies", None), "aurora", None)
            decision_cfg = getattr(
                aurora_cfg, "decision", None) if aurora_cfg else None
            signals_cfg = getattr(decision_cfg, "signals",
                                  None) if decision_cfg else None
            normalize_signals_mode = (
                str(signals_cfg.normalize_signals_mode)
                if signals_cfg is not None
                else "signed_v2"
            )
        except Exception:
            normalize_signals_mode = "signed_v2"

        sizing_cfg = dm_cfg.position_sizing
        return cls(
            strategies_registry=strategies_registry,
            tca_prefs=tca_prefs,
            risk_budgets=risk_budgets,
            fail_closed_on_degraded_context=fail_closed_on_degraded_context,
            degraded_context_critical_keys=degraded_context_critical_keys,
            degraded_context_critical_keys_by_strategy=degraded_context_critical_keys_by_strategy,
            degraded_context_contracts_by_strategy=degraded_context_contracts_by_strategy,
            min_pos_size_usd=decimal.Decimal(
                str(sizing_cfg.min_position_size_usd)),
            liq_cap_usd=decimal.Decimal(
                str(sizing_cfg.liquidity_based_cap_usd)),
            qos_exposure_block_cooldown_sec=int(
                qos_cfg.exposure_block_cooldown_sec),
            qos_max_intents_per_minute_per_symbol=int(
                qos_cfg.max_intents_per_minute_per_symbol),
            qos_mode=str(qos_cfg.mode),
            default_symbol_cooldown_sec=int(qos_cfg.symbol_cooldown_sec),
            qos_enforce=bool(qos_cfg.enforce),
            qos_apply_to_strategies=qos_apply_to_strategies,
            arming_require_regime_warmup=bool(
                dm_cfg.arming.require_regime_warmup),
            arming_retry_backoff_ms=int(dm_cfg.arming.retry_backoff_ms),
            arming_max_attempts=int(dm_cfg.arming.max_attempts),
            features_ttl_sec=float(dm_cfg.features.ttl_sec),
            flip_global_enabled=bool(dm_cfg.flip.enabled),
            bar_gating_enabled=bool(dm_cfg.bar_gating.enable),
            bar_ms=int(dm_cfg.bar_gating.bar_ms),
            behavior_enabled=bool(dm_cfg.behavior_fsm.enable),
            normalize_signals_mode=normalize_signals_mode,
        )
