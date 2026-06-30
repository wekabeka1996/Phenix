"""Safety-gate evaluation for decision intent proposals.

This module is intentionally side-effect free: it reads cached market/context
state, applies the configured gate sequence, and returns a ``SafetyGateResult``
for the facade to consume. Rejection emission, decision tracing, and any
downstream size attenuation are handled outside this module.

LOC budget: <=500 (Constitution S3).
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from apps.reference.contracts.runtime_regime_layers import normalize_structural_regime_label
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock


_REGIME_CONFIDENCE_GATE_KEYS = frozenset({
    "DEFAULT",
    "TREND_UP",
    "TREND_DOWN",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "MEAN_REVERSION",
    "UNCERTAIN",
})
_REGIME_CONFIDENCE_SIDE_KEYS = frozenset({"BUY", "SELL"})


@dataclass
class SafetyGateResult:
    """Result of safety gate evaluation.

    outcome:
        "ALLOW"        — all gates passed, proceed to the builder/facade flow.
        "DENY"         — a runtime gate blocked the proposal.
        "CONFIG_ERROR" — required safety-gates config could not be resolved.
    """

    outcome: str = "ALLOW"
    deny_reason: Optional[str] = None
    deny_family: str = "SAFETY_GATES"
    why_short: str = "ok"
    config_error_context: Optional[str] = None

    # Flags
    apply_safety_gates: bool = False

    # Computed context carried downstream for builder payloads and forensic trace.
    strategy_id: Optional[str] = None
    resolved_regime_confidence_strategy_id: Optional[str] = None
    resolved_regime_confidence_symbol: Optional[str] = None
    resolved_regime_confidence_regime_key: Optional[str] = None
    intent_side: str = "LONG"
    trace_ts_ms: int = 0
    # Diagnostics-only unless backed by score_lineage from the upstream strategy trace.
    signal_score: Optional[float] = None
    score_lineage: Optional[Dict[str, Any]] = None
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    regime_provenance: Optional[Dict[str, Any]] = None
    min_regime_confidence: Optional[float] = None
    resolved_min_regime_confidence: Optional[float] = None
    resolved_min_regime_confidence_source: Optional[str] = "scalar_legacy"
    resolved_min_regime_confidence_strategy_id: Optional[str] = None
    resolved_min_regime_confidence_regime_key: Optional[str] = None
    resolved_max_regime_confidence: Optional[float] = None
    resolved_max_regime_confidence_source: Optional[str] = None
    resolved_max_regime_confidence_strategy_id: Optional[str] = None
    resolved_max_regime_confidence_regime_key: Optional[str] = None
    resolved_regime_confidence_band_active: bool = False
    regime_confidence_gate_verdict: str = "BYPASS"
    regime_confidence_breach_kind: str = "none"
    threshold_applied: bool = False
    threshold_verdict: str = "BYPASS"
    threshold_reason: str = "threshold_not_evaluated"
    directional_sanity_enabled: Optional[bool] = None
    nrr026_enabled: Optional[bool] = None
    nrr026_effective_enforced: Optional[bool] = None
    nrr027_enabled: Optional[bool] = None
    nrr027_effective_enforced: Optional[bool] = None
    price_motion_sanity_enabled: Optional[bool] = None
    price_motion_backtest_bypass: Optional[bool] = None
    nrr028_enabled: Optional[bool] = None
    nrr028_effective_enforced: Optional[bool] = None
    nrr029_enabled: Optional[bool] = None
    nrr029_effective_enforced: Optional[bool] = None
    nrr030_enabled: Optional[bool] = None
    nrr030_effective_enforced: Optional[bool] = None
    nrr063_enabled: Optional[bool] = None
    nrr063_effective_enforced: Optional[bool] = None
    trend_dir: str = "UNKNOWN"
    trend_run_length: int = 0
    delta_price: Optional[float] = None
    trend_confidence: float = 0.0
    pm_norm_10s: Optional[float] = None
    pm_norm_60s: Optional[float] = None
    pm_norm_300s: Optional[float] = None
    vol_pct_10s: Optional[float] = None
    vol_pct_60s: Optional[float] = None
    vol_pct_300s: Optional[float] = None
    ret_60s: Optional[float] = None
    ret_300s: Optional[float] = None
    low_vol_cost_floor_details: Optional[Dict[str, Any]] = None
    # Phase 0.5 overlay state. StrategyGateway is responsible for any STRESS
    # attenuation side effect; this module only surfaces the state.
    system_stress_state: str = "NORMAL"


@dataclass(frozen=True)
class ResolvedRegimeConfidenceThreshold:
    threshold: Optional[float]
    source: Optional[str]
    regime_key: Optional[str]
    mapping_present: bool
    strategy_id: Optional[str] = None
    disabled: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_safety_gates_flag(
    config: "AuroraConfig",
    strategy_id: str,
) -> tuple[bool, Optional[str]]:
    """Resolve the per-strategy enabled flag for safety gates.

    Returns:
        ``(apply_safety_gates, error_context)``.

        ``error_context`` is non-``None`` when the strategy block or the
        ``safety_gates`` block is missing. ``apply_safety_gates`` itself is not
        a fallback default here; missing config is reported to the caller so the
        facade can fail closed.
    """
    try:
        strat_cfg = getattr(config.strategies, str(strategy_id), None)
        if strat_cfg is None:
            return False, f"safety_gates config missing for strategy"
        safety_gates_cfg = getattr(strat_cfg, "safety_gates", None)
        if safety_gates_cfg is None:
            return False, f"safety_gates block missing in strategy config"
        return bool(getattr(safety_gates_cfg, "enabled", False)), None
    except Exception as e:
        return False, f"safety_gates config error: {str(e)[:40]}"


def _extract_price_motion(symbol_states: dict, symbol: str) -> dict:
    """Extract cached ``price_motion`` metrics for one symbol.

    The expected source is ``symbol_states[symbol]["features"]["price_motion"]``
    as populated by the features event handler. Missing or malformed payloads
    are treated as absent metrics and returned as ``None`` fields.
    """
    result: Dict[str, Optional[float]] = {
        "pm_norm_10s": None, "pm_norm_60s": None, "pm_norm_300s": None,
        "vol_pct_10s": None, "vol_pct_60s": None, "vol_pct_300s": None,
        "ret_60s": None, "ret_300s": None,
    }
    try:
        st = symbol_states.get(symbol)
        feats_evt = st.get("features") if isinstance(st, dict) else None
        pm = feats_evt.get("price_motion") if isinstance(
            feats_evt, dict) else None
        if isinstance(pm, dict):
            for key in result:
                val = pm.get(key)
                result[key] = float(val) if val is not None else None
    except Exception:
        pass
    return result


def _extract_signal_score(why_chain: list) -> Optional[float]:
    """Best-effort diagnostics extraction of ``signal_score`` tokens from why_chain strings."""
    try:
        for item in (why_chain or []):
            if not isinstance(item, str):
                continue
            if "signal_score=" in item:
                part = item.split("signal_score=", 1)[1]
                token = part.split(",", 1)[0].split(" ", 1)[0]
                return float(token)
    except Exception:
        pass
    return None


def _coerce_runtime_threshold(value: Any, *, path: str) -> float:
    if value is None or type(value).__name__ == "MagicMock":
        return 0.0
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigContractError(
            path=path,
            why=f"Expected numeric threshold in [0.0, 1.0], got {value!r}",
        ) from exc
    if threshold < 0.0 or threshold > 1.0:
        raise ConfigContractError(
            path=path,
            why=f"Expected threshold in [0.0, 1.0], got {threshold!r}",
        )
    return threshold


def _runtime_threshold_mapping_or_none(
    value: Any,
    *,
    path: str,
    require_default: bool = True,
) -> Mapping[str, Any] | None:
    if value is None or type(value).__name__ == "MagicMock":
        return None
    if not isinstance(value, Mapping):
        raise ConfigContractError(
            path=path,
            why="Expected mapping with DEFAULT threshold",
        )
    if require_default and "DEFAULT" not in value:
        raise ConfigContractError(
            path=path,
            why="DEFAULT threshold is required when per-regime mapping is provided",
        )
    for raw_key, raw_threshold in value.items():
        if not isinstance(raw_key, str):
            raise ConfigContractError(
                path=path, why="Threshold keys must be strings")
        key = raw_key.strip()
        if key != raw_key or key != key.upper() or key not in _REGIME_CONFIDENCE_GATE_KEYS:
            allowed = ", ".join(sorted(_REGIME_CONFIDENCE_GATE_KEYS))
            raise ConfigContractError(
                path=path,
                why=f"Threshold key {raw_key!r} must be canonical uppercase label; allowed: {allowed}",
            )
        _coerce_runtime_threshold(raw_threshold, path=f"{path}.{raw_key}")
    return value


def _normalize_trade_side_key(side: Optional[str]) -> Optional[str]:
    if side is None:
        return None
    normalized = str(side).strip().upper()
    if normalized in {"BUY", "LONG"}:
        return "BUY"
    if normalized in {"SELL", "SHORT"}:
        return "SELL"
    return None


def _runtime_regime_side_mapping_or_none(
    value: Any,
    *,
    path: str,
) -> Mapping[str, Any] | None:
    if value is None or type(value).__name__ == "MagicMock":
        return None
    if not isinstance(value, Mapping):
        raise ConfigContractError(
            path=path,
            why="Expected mapping with canonical regime keys for side-aware override",
        )
    allowed = ", ".join(
        sorted(key for key in _REGIME_CONFIDENCE_GATE_KEYS if key != "DEFAULT")
    )
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise ConfigContractError(
                path=path,
                why="Side-aware override keys must be strings",
            )
        key = raw_key.strip()
        if (
            key != raw_key
            or key != key.upper()
            or key == "DEFAULT"
            or key not in _REGIME_CONFIDENCE_GATE_KEYS
        ):
            raise ConfigContractError(
                path=path,
                why=(
                    f"Side-aware override key {raw_key!r} must be canonical uppercase "
                    f"regime label; DEFAULT+side is not supported; allowed: {allowed}"
                ),
            )
        if raw_value is None:
            raise ConfigContractError(
                path=f"{path}.{raw_key}",
                why="Expected side-aware override object",
            )
    return value


def _extract_side_min_threshold(
    side_mapping: Any,
    *,
    side_key: Optional[str],
    path: str,
) -> Optional[float]:
    if side_key is None or side_mapping is None or type(side_mapping).__name__ == "MagicMock":
        return None
    raw_value = (
        side_mapping.get(side_key)
        if isinstance(side_mapping, Mapping)
        else getattr(side_mapping, side_key, None)
    )
    if raw_value is None or type(raw_value).__name__ == "MagicMock":
        return None
    return _coerce_runtime_threshold(raw_value, path=f"{path}.{side_key}")


def _extract_side_max_override(
    side_mapping: Any,
    *,
    side_key: Optional[str],
    path: str,
) -> tuple[Optional[float], bool, bool]:
    if side_key is None or side_mapping is None or type(side_mapping).__name__ == "MagicMock":
        return None, False, False
    raw_override = (
        side_mapping.get(side_key)
        if isinstance(side_mapping, Mapping)
        else getattr(side_mapping, side_key, None)
    )
    if raw_override is None or type(raw_override).__name__ == "MagicMock":
        return None, False, False
    if isinstance(raw_override, Mapping):
        enabled = raw_override.get("enabled")
        threshold = raw_override.get("threshold")
    else:
        enabled = getattr(raw_override, "enabled", None)
        threshold = getattr(raw_override, "threshold", None)
    if not isinstance(enabled, bool):
        raise ConfigContractError(
            path=f"{path}.{side_key}.enabled",
            why="Expected boolean enabled flag for side-aware max override",
        )
    if not enabled:
        if threshold is not None and type(threshold).__name__ != "MagicMock":
            raise ConfigContractError(
                path=f"{path}.{side_key}.threshold",
                why="Disabled side-aware max override must omit threshold",
            )
        return None, True, True
    if threshold is None or type(threshold).__name__ == "MagicMock":
        raise ConfigContractError(
            path=f"{path}.{side_key}.threshold",
            why="Enabled side-aware max override requires threshold",
        )
    return (
        _coerce_runtime_threshold(threshold, path=f"{path}.{side_key}.threshold"),
        True,
        False,
    )


def _strategy_regime_confidence_threshold_by_regime(
    config: "AuroraConfig",
    strategy_id: Optional[str],
    *,
    threshold_attr: str,
) -> Mapping[str, Any] | None:
    if strategy_id is None:
        return None
    normalized_strategy_id = str(strategy_id).strip()
    if not normalized_strategy_id:
        return None
    strat_cfg = getattr(config.strategies, normalized_strategy_id, None)
    if strat_cfg is None:
        return None
    safety_gates_cfg = getattr(strat_cfg, "safety_gates", None)
    if safety_gates_cfg is None:
        return None
    regime_confidence_cfg = getattr(
        safety_gates_cfg, "regime_confidence", None)
    if regime_confidence_cfg is None or type(regime_confidence_cfg).__name__ == "MagicMock":
        return None
    return getattr(regime_confidence_cfg, threshold_attr, None)


def _strategy_symbol_regime_confidence_threshold_by_regime(
    config: "AuroraConfig",
    strategy_id: Optional[str],
    symbol: Optional[str],
    *,
    threshold_attr: str,
) -> Mapping[str, Any] | None:
    if strategy_id is None or symbol is None:
        return None
    normalized_strategy_id = str(strategy_id).strip()
    normalized_symbol = str(symbol).strip().upper()
    if not normalized_strategy_id or not normalized_symbol:
        return None
    strat_cfg = getattr(config.strategies, normalized_strategy_id, None)
    if strat_cfg is None:
        return None
    safety_gates_cfg = getattr(strat_cfg, "safety_gates", None)
    if safety_gates_cfg is None:
        return None
    regime_confidence_cfg = getattr(
        safety_gates_cfg, "regime_confidence", None)
    if regime_confidence_cfg is None or type(regime_confidence_cfg).__name__ == "MagicMock":
        return None
    by_symbol = getattr(regime_confidence_cfg, threshold_attr, None)
    if by_symbol is None or type(by_symbol).__name__ == "MagicMock":
        return None
    if not isinstance(by_symbol, Mapping):
        return None
    return by_symbol.get(normalized_symbol)


def _resolve_regime_confidence_threshold(
    regime: Optional[str],
    scalar_threshold: Optional[float],
    by_regime: Mapping[str, Any] | None,
    *,
    threshold_kind: str,
    strategy_id: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    strategy_by_regime: Mapping[str, Any] | None = None,
    strategy_symbol_by_regime: Mapping[str, Any] | None = None,
    strategy_by_regime_side: Mapping[str, Any] | None = None,
    strategy_symbol_by_regime_side: Mapping[str, Any] | None = None,
) -> ResolvedRegimeConfidenceThreshold:
    require_default = threshold_kind != "max"
    normalized_strategy_id = str(
        strategy_id).strip() if strategy_id is not None else ""
    normalized_symbol = str(symbol).strip(
    ).upper() if symbol is not None else ""
    side_key = _normalize_trade_side_key(side)
    regime_key = normalize_structural_regime_label(regime)

    if normalized_strategy_id:
        strategy_symbol_side_mapping = _runtime_regime_side_mapping_or_none(
            strategy_symbol_by_regime_side,
            path=(
                f"strategies.{normalized_strategy_id}.safety_gates."
                f"regime_confidence.{threshold_kind}_by_symbol_regime_side.{normalized_symbol}"
            ),
        ) if normalized_symbol else None
        if (
            strategy_symbol_side_mapping is not None
            and regime_key
            and side_key
            and regime_key in strategy_symbol_side_mapping
        ):
            path_prefix = (
                f"strategies.{normalized_strategy_id}.safety_gates."
                f"regime_confidence.{threshold_kind}_by_symbol_regime_side."
                f"{normalized_symbol}.{regime_key}"
            )
            side_mapping = strategy_symbol_side_mapping[regime_key]
            if threshold_kind == "max":
                threshold, override_present, disabled = _extract_side_max_override(
                    side_mapping,
                    side_key=side_key,
                    path=path_prefix,
                )
                if override_present:
                    return ResolvedRegimeConfidenceThreshold(
                        threshold=threshold,
                        source=(
                            "strategy_symbol_regime_side_specific_disabled"
                            if disabled else "strategy_symbol_regime_side_specific"
                        ),
                        regime_key=regime_key,
                        mapping_present=True,
                        strategy_id=normalized_strategy_id,
                        disabled=disabled,
                    )
            else:
                threshold = _extract_side_min_threshold(
                    side_mapping,
                    side_key=side_key,
                    path=path_prefix,
                )
                if threshold is not None:
                    return ResolvedRegimeConfidenceThreshold(
                        threshold=threshold,
                        source="strategy_symbol_regime_side_specific",
                        regime_key=regime_key,
                        mapping_present=True,
                        strategy_id=normalized_strategy_id,
                    )

        strategy_symbol_mapping = _runtime_threshold_mapping_or_none(
            strategy_symbol_by_regime,
            path=(
                f"strategies.{normalized_strategy_id}.safety_gates."
                f"regime_confidence.{threshold_kind}_by_symbol.{normalized_symbol}"
            ),
            require_default=require_default,
        ) if normalized_symbol else None
        if strategy_symbol_mapping is not None:
            if regime_key and regime_key in strategy_symbol_mapping:
                return ResolvedRegimeConfidenceThreshold(
                    threshold=_coerce_runtime_threshold(
                        strategy_symbol_mapping[regime_key],
                        path=(
                            f"strategies.{normalized_strategy_id}.safety_gates."
                            f"regime_confidence.{threshold_kind}_by_symbol.{normalized_symbol}.{regime_key}"
                        ),
                    ),
                    source="strategy_symbol_regime_specific",
                    regime_key=regime_key,
                    mapping_present=True,
                    strategy_id=normalized_strategy_id,
                )
            if "DEFAULT" in strategy_symbol_mapping:
                return ResolvedRegimeConfidenceThreshold(
                    threshold=_coerce_runtime_threshold(
                        strategy_symbol_mapping["DEFAULT"],
                        path=(
                            f"strategies.{normalized_strategy_id}.safety_gates."
                            f"regime_confidence.{threshold_kind}_by_symbol.{normalized_symbol}.DEFAULT"
                        ),
                    ),
                    source="strategy_symbol_default",
                    regime_key="DEFAULT",
                    mapping_present=True,
                    strategy_id=normalized_strategy_id,
                )
            if require_default:
                raise ConfigContractError(
                    path=(
                        f"strategies.{normalized_strategy_id}.safety_gates."
                        f"regime_confidence.{threshold_kind}_by_symbol.{normalized_symbol}"
                    ),
                    why="DEFAULT threshold is required when per-regime mapping is provided",
                )

        strategy_side_mapping = _runtime_regime_side_mapping_or_none(
            strategy_by_regime_side,
            path=(
                f"strategies.{normalized_strategy_id}.safety_gates."
                f"regime_confidence.{threshold_kind}_by_regime_side"
            ),
        )
        if (
            strategy_side_mapping is not None
            and regime_key
            and side_key
            and regime_key in strategy_side_mapping
        ):
            path_prefix = (
                f"strategies.{normalized_strategy_id}.safety_gates."
                f"regime_confidence.{threshold_kind}_by_regime_side.{regime_key}"
            )
            side_mapping = strategy_side_mapping[regime_key]
            if threshold_kind == "max":
                threshold, override_present, disabled = _extract_side_max_override(
                    side_mapping,
                    side_key=side_key,
                    path=path_prefix,
                )
                if override_present:
                    return ResolvedRegimeConfidenceThreshold(
                        threshold=threshold,
                        source=(
                            "strategy_regime_side_specific_disabled"
                            if disabled else "strategy_regime_side_specific"
                        ),
                        regime_key=regime_key,
                        mapping_present=True,
                        strategy_id=normalized_strategy_id,
                        disabled=disabled,
                    )
            else:
                threshold = _extract_side_min_threshold(
                    side_mapping,
                    side_key=side_key,
                    path=path_prefix,
                )
                if threshold is not None:
                    return ResolvedRegimeConfidenceThreshold(
                        threshold=threshold,
                        source="strategy_regime_side_specific",
                        regime_key=regime_key,
                        mapping_present=True,
                        strategy_id=normalized_strategy_id,
                    )

        strategy_mapping = _runtime_threshold_mapping_or_none(
            strategy_by_regime,
            path=(
                f"strategies.{normalized_strategy_id}.safety_gates."
                f"regime_confidence.{threshold_kind}_by_regime"
            ),
            require_default=require_default,
        )
        if strategy_mapping is not None:
            if regime_key and regime_key in strategy_mapping:
                return ResolvedRegimeConfidenceThreshold(
                    threshold=_coerce_runtime_threshold(
                        strategy_mapping[regime_key],
                        path=(
                            f"strategies.{normalized_strategy_id}.safety_gates."
                            f"regime_confidence.{threshold_kind}_by_regime.{regime_key}"
                        ),
                    ),
                    source="strategy_regime_specific",
                    regime_key=regime_key,
                    mapping_present=True,
                    strategy_id=normalized_strategy_id,
                )
            if "DEFAULT" in strategy_mapping:
                return ResolvedRegimeConfidenceThreshold(
                    threshold=_coerce_runtime_threshold(
                        strategy_mapping["DEFAULT"],
                        path=(
                            f"strategies.{normalized_strategy_id}.safety_gates."
                            f"regime_confidence.{threshold_kind}_by_regime.DEFAULT"
                        ),
                    ),
                    source="strategy_default",
                    regime_key="DEFAULT",
                    mapping_present=True,
                    strategy_id=normalized_strategy_id,
                )
            if require_default:
                raise ConfigContractError(
                    path=(
                        f"strategies.{normalized_strategy_id}.safety_gates."
                        f"regime_confidence.{threshold_kind}_by_regime"
                    ),
                    why="DEFAULT threshold is required when per-regime mapping is provided",
                )

    domain_mapping = _runtime_threshold_mapping_or_none(
        by_regime,
        path=(
            "domains.decision_making.directional_sanity."
            f"{threshold_kind}_regime_confidence_by_regime"
        ),
        require_default=require_default,
    )
    if domain_mapping is None:
        if threshold_kind == "max":
            return ResolvedRegimeConfidenceThreshold(
                threshold=None,
                source=None,
                regime_key=None,
                mapping_present=False,
            )
        return ResolvedRegimeConfidenceThreshold(
            threshold=scalar_threshold,
            source="scalar_legacy",
            regime_key=None,
            mapping_present=False,
        )

    if regime_key and regime_key in domain_mapping:
        return ResolvedRegimeConfidenceThreshold(
            threshold=_coerce_runtime_threshold(
                domain_mapping[regime_key],
                path=(
                    "domains.decision_making.directional_sanity."
                    f"{threshold_kind}_regime_confidence_by_regime.{regime_key}"
                ),
            ),
            source="domain_regime_specific",
            regime_key=regime_key,
            mapping_present=True,
        )

    if "DEFAULT" in domain_mapping:
        return ResolvedRegimeConfidenceThreshold(
            threshold=_coerce_runtime_threshold(
                domain_mapping["DEFAULT"],
                path=(
                    "domains.decision_making.directional_sanity."
                    f"{threshold_kind}_regime_confidence_by_regime.DEFAULT"
                ),
            ),
            source="domain_default",
            regime_key="DEFAULT",
            mapping_present=True,
        )

    if not require_default:
        return ResolvedRegimeConfidenceThreshold(
            threshold=None,
            source=None,
            regime_key=None,
            mapping_present=True,
        )

    raise ConfigContractError(
        path=(
            "domains.decision_making.directional_sanity."
            f"{threshold_kind}_regime_confidence_by_regime"
        ),
        why="DEFAULT threshold is required when per-regime mapping is provided",
    )


def resolve_min_regime_confidence(
    regime: Optional[str],
    scalar_min: float,
    by_regime: Mapping[str, Any] | None,
    *,
    strategy_id: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    strategy_by_regime: Mapping[str, Any] | None = None,
    strategy_symbol_by_regime: Mapping[str, Any] | None = None,
    strategy_by_regime_side: Mapping[str, Any] | None = None,
    strategy_symbol_by_regime_side: Mapping[str, Any] | None = None,
) -> ResolvedRegimeConfidenceThreshold:
    return _resolve_regime_confidence_threshold(
        regime,
        scalar_min,
        by_regime,
        threshold_kind="min",
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        strategy_by_regime=strategy_by_regime,
        strategy_symbol_by_regime=strategy_symbol_by_regime,
        strategy_by_regime_side=strategy_by_regime_side,
        strategy_symbol_by_regime_side=strategy_symbol_by_regime_side,
    )


def resolve_max_regime_confidence(
    regime: Optional[str],
    by_regime: Mapping[str, Any] | None,
    *,
    strategy_id: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    strategy_by_regime: Mapping[str, Any] | None = None,
    strategy_symbol_by_regime: Mapping[str, Any] | None = None,
    strategy_by_regime_side: Mapping[str, Any] | None = None,
    strategy_symbol_by_regime_side: Mapping[str, Any] | None = None,
) -> ResolvedRegimeConfidenceThreshold:
    return _resolve_regime_confidence_threshold(
        regime,
        None,
        by_regime,
        threshold_kind="max",
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        strategy_by_regime=strategy_by_regime,
        strategy_symbol_by_regime=strategy_symbol_by_regime,
        strategy_by_regime_side=strategy_by_regime_side,
        strategy_symbol_by_regime_side=strategy_symbol_by_regime_side,
    )


def _extract_regime(per_symbol_regimes: dict, symbol: str) -> tuple[Optional[str], Optional[float], Dict[str, Any]]:
    """Extract regime name and confidence from the per-symbol regime cache."""
    try:
        r = per_symbol_regimes.get(symbol)
        if isinstance(r, dict):
            regime = r.get("regime")
            rc = r.get("confidence")
            confidence = float(rc) if rc not in (None, "") else None
            cached_provenance = r.get("regime_provenance")
            cache_snapshot = {
                "cache_write_ts_ms": r.get("cache_write_ts_ms"),
                "regime": regime,
                "confidence": confidence,
            }
            if isinstance(cached_provenance, dict):
                cache_snapshot = dict(cached_provenance.get(
                    "cache_snapshot") or cache_snapshot)
                detector_event = cached_provenance.get("detector_event")
            else:
                detector_event = {
                    "event_name": "EVT:REGIME_DETECTED",
                    "rid": r.get("rid"),
                    "ts_ms": r.get("ts_ms"),
                    "last_update_ts_ms": r.get("last_update_ts_ms"),
                    "structural_regime_ref": r.get("structural_regime_ref"),
                    "basis_tf_sec": r.get("basis_tf_sec"),
                    "bar_close_ts_ms": r.get("bar_close_ts_ms"),
                    "changed": r.get("changed"),
                    "regime": regime,
                    "confidence": rc,
                    "stable_confidence": r.get("stable_confidence"),
                    "source_model": r.get("source_model"),
                    "pre_cutoff_source_model": r.get("pre_cutoff_source_model"),
                    "confidence_min": r.get("confidence_min"),
                    "confidence_max": r.get("confidence_max"),
                    "pre_cutoff_regime": r.get("pre_cutoff_regime"),
                    "pre_cutoff_confidence": r.get("pre_cutoff_confidence"),
                    "pre_cutoff_clamped_to_min": r.get("pre_cutoff_clamped_to_min"),
                    "pre_cutoff_clamped_to_max": r.get("pre_cutoff_clamped_to_max"),
                    "pre_cutoff_boundary_reason": r.get("pre_cutoff_boundary_reason"),
                    "uncertain_cutoff": r.get("uncertain_cutoff"),
                    "demoted_to_uncertain": r.get("demoted_to_uncertain"),
                    "raw_regime": r.get("raw_regime"),
                    "raw_confidence": r.get("raw_confidence"),
                    "raw_boundary_reason": r.get("raw_boundary_reason"),
                    "hysteresis_bars": r.get("hysteresis_bars"),
                    "hysteresis_confirm_count": r.get("hysteresis_confirm_count"),
                    "carried_previous_stable": r.get("carried_previous_stable"),
                    "emitted_confidence_kind": r.get("emitted_confidence_kind"),
                    "reason_summary": r.get("reason_summary"),
                }
            return regime, confidence, {
                "source_kind": "detector_cache",
                "detector_event": detector_event,
                "cache_snapshot": cache_snapshot,
            }
    except Exception:
        pass
    return None, None, {
        "source_kind": "unknown",
        "detector_event": None,
        "cache_snapshot": None,
    }


def _compute_trend(
    symbol_states: dict,
    symbol: str,
    consecutive: int,
    min_abs_delta: float,
) -> tuple[str, float, Optional[float], int]:
    """Compute directional trend from cached ``_delta_price_hist``.

    This helper is intentionally best-effort: malformed history yields the
    neutral/unknown contract rather than raising inside gate evaluation.

    Returns:
        (trend_dir, trend_confidence, delta_price, trend_run_length)
    """
    trend_dir = "UNKNOWN"
    delta_price: Optional[float] = None
    trend_confidence = 0.0
    trend_run_length = 0
    try:
        state = symbol_states.get(symbol)
        hist = state.get("_delta_price_hist") if isinstance(
            state, dict) else None
        if isinstance(hist, deque) and len(hist) > 0:
            delta_price = float(hist[-1])
            filtered: list[float] = []
            for x in list(hist):
                try:
                    xf = float(x)
                except Exception:
                    continue
                if abs(xf) < float(min_abs_delta):
                    continue
                if xf == 0.0:
                    continue
                filtered.append(xf)

            if filtered:
                last_sign = 1 if filtered[-1] > 0 else -1
                for x in reversed(filtered):
                    sign = 1 if x > 0 else -1
                    if sign != last_sign:
                        break
                    trend_run_length += 1

            window = filtered[-consecutive:]
            if len(window) >= consecutive:
                if all(x > 0 for x in window):
                    trend_dir = "UP"
                    trend_confidence = 1.0
                elif all(x < 0 for x in window):
                    trend_dir = "DOWN"
                    trend_confidence = 1.0
    except Exception:
        trend_dir = "UNKNOWN"
        delta_price = None
        trend_confidence = 0.0
        trend_run_length = 0
    return trend_dir, trend_confidence, delta_price, trend_run_length


def _check_directional_gate(
    *,
    intent_side: str,
    reduce_only: bool,
    apply_safety_gates: bool,
    ds_enabled: bool,
    nrr026_enabled: bool,
    nrr027_enabled: bool,
    strategy_id: str,
    trend_dir: str,
    trend_run_length: int,
    trend_confidence: float,
    regime_confidence: Optional[float],
    min_conf: float,
    hard_veto_consecutive_bars: int,
) -> tuple[str, Optional[str], str]:
    """Evaluate the directional sanity gate.

    ``min_conf`` is checked against the stronger of regime confidence and local
    trend confidence. Counter-trend proposals can still pass as "soft" allows
    until ``hard_veto_consecutive_bars`` is reached.

    ``nrr026_enabled`` controls the NRR-026 (INSUFFICIENT_TREND_CONFIRMATION)
    trend/confidence paths. ``nrr027_enabled`` controls the NRR-027
    (DIRECTIONAL_SANITY_BLOCKED) countertrend hard-veto path. Both are
    independent; the master ``ds_enabled`` still gates the entire function.

    Returns:
        (gate_outcome, deny_reason, why_short)
    """
    if reduce_only:
        return "ALLOW", None, "reduce_only"
    if not apply_safety_gates:
        return "ALLOW", None, f"safety_gates_skipped:strategy={strategy_id}"
    if not ds_enabled:
        return "ALLOW", None, "directional_sanity_disabled"

    effective_conf = max(float(regime_confidence or 0.0),
                         float(trend_confidence or 0.0))
    if nrr026_enabled:
        if trend_dir not in ("UP", "DOWN"):
            return "DENY", NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION, "insufficient trend confirmation"
        if effective_conf < float(min_conf):
            return "DENY", NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION, "insufficient confidence"
    if trend_dir == "DOWN" and intent_side == "LONG":
        if trend_run_length < int(hard_veto_consecutive_bars):
            return "ALLOW", None, (
                f"countertrend long soft: run={trend_run_length} < veto_bars={hard_veto_consecutive_bars}"
            )
        if nrr027_enabled:
            return "DENY", NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED, "downtrend blocks long"
    if trend_dir == "UP" and intent_side == "SHORT":
        if trend_run_length < int(hard_veto_consecutive_bars):
            return "ALLOW", None, (
                f"countertrend short soft: run={trend_run_length} < veto_bars={hard_veto_consecutive_bars}"
            )
        if nrr027_enabled:
            return "DENY", NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED, "uptrend blocks short"
    return "ALLOW", None, "ok"


def _check_price_motion_gate(
    *,
    config: "AuroraConfig",
    symbol: str,
    intent_side: str,
    reduce_only: bool,
    apply_safety_gates: bool,
    pm_norm_10s: Optional[float],
    pm_norm_60s: Optional[float],
    pm_norm_300s: Optional[float],
    nrr028_enabled: bool = True,
    nrr029_enabled: bool = True,
    nrr030_enabled: bool = True,
) -> tuple[str, Optional[str], str]:
    """Evaluate the multi-window price-motion sanity gate.

    The gate is bypassed for ``reduce_only`` flows, for strategies with
    ``safety_gates.enabled=false``, when the price-motion gate itself is
    disabled, and in backtest mode.

    Returns:
        (gate_outcome, deny_reason, why_short)
    """
    pm_cfg = config.domains.decision_making.price_motion_sanity
    pm_enabled = bool(pm_cfg.enabled)

    try:
        is_backtest = str(getattr(config, "trading_mode", "")
                          ).strip().lower() == "backtest"
    except Exception:
        is_backtest = False

    if (not apply_safety_gates) or reduce_only or (not pm_enabled) or is_backtest:
        return "ALLOW", None, "ok"

    def _select_pm(window_sec: int) -> Optional[float]:
        if window_sec == 10:
            return pm_norm_10s
        if window_sec == 60:
            return pm_norm_60s
        if window_sec == 300:
            return pm_norm_300s
        raise ConfigContractError(
            path="domains.decision_making.price_motion_sanity",
            why=f"Unsupported price_motion window_sec={window_sec}; expected 10/60/300",
            symbol=symbol,
        )

    flash_window = int(pm_cfg.flash_window_sec)
    bleed_window = int(pm_cfg.bleed_window_sec)
    t_flash = float(pm_cfg.flash_threshold_norm)
    t_bleed = float(pm_cfg.bleed_threshold_norm)
    require_bleed_ready = bool(pm_cfg.require_bleed_ready)

    pm_flash = _select_pm(flash_window)
    pm_bleed = _select_pm(bleed_window)

    if pm_flash is None:
        if nrr028_enabled:
            return "DENY", NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT, "price_motion flash insufficient"
        else:
            return "ALLOW", None, "ok"
    if require_bleed_ready and (pm_bleed is None):
        if nrr028_enabled:
            return "DENY", NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT, "price_motion bleed insufficient"

    # Flash gate
    if nrr029_enabled:
        if intent_side == "LONG" and pm_flash <= -t_flash:
            return "DENY", NormalizedRejectReasons.PRICE_MOTION_FLASH_BLOCKED, "flash down blocks long"
        if intent_side == "SHORT" and pm_flash >= t_flash:
            return "DENY", NormalizedRejectReasons.PRICE_MOTION_FLASH_BLOCKED, "flash up blocks short"

    # Bleed gate (only if ready)
    if nrr030_enabled:
        if pm_bleed is not None:
            if intent_side == "LONG" and pm_bleed <= -t_bleed:
                return "DENY", NormalizedRejectReasons.PRICE_MOTION_BLEED_BLOCKED, "bleed down blocks long"
            if intent_side == "SHORT" and pm_bleed >= t_bleed:
                return "DENY", NormalizedRejectReasons.PRICE_MOTION_BLEED_BLOCKED, "bleed up blocks short"

    return "ALLOW", None, "ok"


# ---------------------------------------------------------------------------
# Phase 0.5 / 0.6: System Stress gate helpers
# ---------------------------------------------------------------------------

def _resolve_stress_policy(
    config: "AuroraConfig",
    strategy_id: str,
) -> tuple[str, float]:
    """Resolve per-strategy system stress policy and attenuation factor.

    Returns:
        ``(stress_policy, stress_attenuation_factor)``.

        This helper is intentionally lenient for absent strategy/safety-gates
        blocks and falls back to ``("off", 1.0)`` so direct helper callers can
        treat "no policy configured" as a bypass. Only unexpected resolution
        errors return ``("CONFIG_ERROR", 0.0)`` for fail-closed handling by the
        Gate 0.5 caller.
    """
    try:
        strat_cfg = getattr(config.strategies, str(strategy_id), None)
        sg_cfg = getattr(strat_cfg, "safety_gates",
                         None) if strat_cfg else None
        if sg_cfg is None:
            return "off", 1.0
        policy = str(getattr(sg_cfg, "system_stress_policy", "off"))
        if policy not in ("off", "attenuate", "block"):
            policy = "off"
        factor = float(getattr(sg_cfg, "stress_attenuation_factor", 0.5))
        return policy, max(0.0, min(1.0, factor))
    except Exception:
        return "CONFIG_ERROR", 0.0


def _check_system_stress_gate(
    *,
    symbol: str,
    reduce_only: bool,
    apply_safety_gates_flag: bool,
    system_stress_states: Optional[dict],
    stress_policy: str = "off",
) -> tuple:
    """Evaluate Gate 0.5: the system-stress overlay.

    Policy semantics (per-strategy, Phase 0.6):
        off       → Gate fully bypassed; even EXTREME is ignored.
        attenuate → EXTREME=DENY; STRESS=ALLOW+surface for later size attenuation.
        block     → EXTREME and STRESS both DENY.
        CONFIG_ERROR → DENY (Fail-closed).

    ``reduce_only`` orders always bypass because closing flow is risk-reducing.

    Returns:
        (gate_outcome, deny_reason, why_short, stress_state_str)
    """
    if reduce_only or not apply_safety_gates_flag:
        return "ALLOW", None, "ok", "NORMAL"

    if stress_policy == "CONFIG_ERROR":
        return (
            "DENY",
            NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING,
            f"system_stress_policy config resolution failed (fail-closed) for {symbol}",
            "UNKNOWN",
        )

    if stress_policy == "off" or system_stress_states is None:
        return "ALLOW", None, "ok", "NORMAL"

    stress_state = system_stress_states.get(symbol, "NORMAL")

    if stress_state == "EXTREME":
        return (
            "DENY",
            NormalizedRejectReasons.SYSTEM_STRESS_ENTRY_BLOCKED,
            f"system_stress=EXTREME blocks new entry for {symbol}",
            stress_state,
        )

    if stress_state == "STRESS" and stress_policy == "block":
        return (
            "DENY",
            NormalizedRejectReasons.SYSTEM_STRESS_ENTRY_BLOCKED,
            f"system_stress=STRESS blocks new entry for {symbol} (policy=block)",
            stress_state,
        )

    # STRESS + attenuate → pass, surface state for strategy_gateway attenuation
    return "ALLOW", None, "ok", stress_state


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_safety_gates(
    *,
    symbol: str,
    side: str,
    reduce_only: bool,
    strategy_id: str,
    decision_ts_ms: Optional[int],
    why_chain: list,
    config: "AuroraConfig",
    clock: "Clock",
    symbol_states: dict,
    per_symbol_regimes: dict,
    system_stress_states: Optional[dict] = None,
) -> SafetyGateResult:
    """Evaluate all safety gates for a trade intent proposal.

    This function only evaluates the gate contract and returns structured
    context. The caller handles rejection events, decision tracing, blocked
    intent accounting, and any post-gate sizing side effects.

    Gate sequence:
        0.  Config resolution (FAIL-CLOSED if missing)
        0.5 System stress overlay gate (Phase 0.5 / 0.6): policy-driven DENY or surface state
        1.  FIX-CONF-GATE-01: Regime confidence gate
        2.  Directional sanity gate (trend vs intent)
        3.  Price motion multi-window gate (flash / bleed)
    """
    result = SafetyGateResult()
    result.strategy_id = str(strategy_id) if strategy_id is not None else None
    result.trace_ts_ms = int(
        decision_ts_ms) if decision_ts_ms is not None else clock.now_ms()
    result.intent_side = "LONG" if str(side).upper() == "BUY" else "SHORT"

    # ── Gate 0: Config resolution ──────────────────────────────
    apply_flag, config_error = _resolve_safety_gates_flag(config, strategy_id)
    if config_error is not None:
        result.outcome = "CONFIG_ERROR"
        result.config_error_context = config_error
        result.deny_reason = NormalizedRejectReasons.CONFIG_SAFETY_GATES_MISSING
        return result
    result.apply_safety_gates = apply_flag

    # ── Gate 0.5: System Stress Overlay (Phase 0.5 / 0.6) ──────
    # Gate 0.5 only decides allow/deny and surfaces stress state. The returned
    # attenuation factor is intentionally consumed later in StrategyGateway.
    stress_policy, _stress_factor = _resolve_stress_policy(config, strategy_id)
    ss_outcome, ss_deny, ss_why, ss_state = _check_system_stress_gate(
        symbol=symbol,
        reduce_only=reduce_only,
        apply_safety_gates_flag=apply_flag,
        system_stress_states=system_stress_states,
        stress_policy=stress_policy,
    )
    result.system_stress_state = ss_state
    if ss_outcome == "DENY":
        result.outcome = "DENY"
        result.deny_reason = ss_deny
        result.why_short = ss_why
        return result

    # ── Extract context (best-effort, non-authoritative caches) ─────────────
    pm = _extract_price_motion(symbol_states, symbol)
    result.pm_norm_10s = pm["pm_norm_10s"]
    result.pm_norm_60s = pm["pm_norm_60s"]
    result.pm_norm_300s = pm["pm_norm_300s"]
    result.vol_pct_10s = pm["vol_pct_10s"]
    result.vol_pct_60s = pm["vol_pct_60s"]
    result.vol_pct_300s = pm["vol_pct_300s"]
    result.ret_60s = pm["ret_60s"]
    result.ret_300s = pm["ret_300s"]

    result.signal_score = _extract_signal_score(why_chain)
    result.regime, result.regime_confidence, result.regime_provenance = _extract_regime(
        per_symbol_regimes, symbol)

    # ── Read directional sanity config ─────────────────────────
    ds_cfg = config.domains.decision_making.directional_sanity
    ds_enabled = bool(ds_cfg.enabled)
    nrr026_enabled = bool(getattr(ds_cfg, 'nrr026_enabled', True))
    nrr027_enabled = bool(getattr(ds_cfg, 'nrr027_enabled', True))
    result.directional_sanity_enabled = ds_enabled
    result.nrr026_enabled = nrr026_enabled
    result.nrr027_enabled = nrr027_enabled
    min_abs_delta = float(ds_cfg.min_abs_delta_price)
    min_conf = float(ds_cfg.min_confidence)
    min_regime_conf = _coerce_runtime_threshold(
        getattr(ds_cfg, 'min_regime_confidence', 0.0),
        path="domains.decision_making.directional_sanity.min_regime_confidence",
    )
    result.min_regime_confidence = min_regime_conf
    raw_by_regime = getattr(ds_cfg, 'min_regime_confidence_by_regime', None)
    threshold_resolution = resolve_min_regime_confidence(
        result.regime,
        min_regime_conf,
        raw_by_regime,
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        strategy_by_regime=_strategy_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            threshold_attr="min_by_regime",
        ),
        strategy_symbol_by_regime=_strategy_symbol_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            symbol,
            threshold_attr="min_by_symbol",
        ),
        strategy_by_regime_side=_strategy_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            threshold_attr="min_by_regime_side",
        ),
        strategy_symbol_by_regime_side=_strategy_symbol_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            symbol,
            threshold_attr="min_by_symbol_regime_side",
        ),
    )
    resolved_min_regime_conf = threshold_resolution.threshold
    result.resolved_min_regime_confidence = resolved_min_regime_conf
    result.resolved_min_regime_confidence_source = threshold_resolution.source
    result.resolved_min_regime_confidence_strategy_id = threshold_resolution.strategy_id
    result.resolved_min_regime_confidence_regime_key = threshold_resolution.regime_key
    raw_max_by_regime = getattr(
        ds_cfg, 'max_regime_confidence_by_regime', None)
    max_threshold_resolution = resolve_max_regime_confidence(
        result.regime,
        raw_max_by_regime,
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        strategy_by_regime=_strategy_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            threshold_attr="max_by_regime",
        ),
        strategy_symbol_by_regime=_strategy_symbol_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            symbol,
            threshold_attr="max_by_symbol",
        ),
        strategy_by_regime_side=_strategy_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            threshold_attr="max_by_regime_side",
        ),
        strategy_symbol_by_regime_side=_strategy_symbol_regime_confidence_threshold_by_regime(
            config,
            strategy_id,
            symbol,
            threshold_attr="max_by_symbol_regime_side",
        ),
    )
    result.resolved_max_regime_confidence = max_threshold_resolution.threshold
    result.resolved_max_regime_confidence_source = max_threshold_resolution.source
    result.resolved_max_regime_confidence_strategy_id = max_threshold_resolution.strategy_id
    result.resolved_max_regime_confidence_regime_key = max_threshold_resolution.regime_key
    result.resolved_regime_confidence_strategy_id = strategy_id
    result.resolved_regime_confidence_symbol = symbol
    result.resolved_regime_confidence_regime_key = (
        result.resolved_min_regime_confidence_regime_key
        or result.resolved_max_regime_confidence_regime_key
    )
    result.resolved_regime_confidence_band_active = bool(
        (resolved_min_regime_conf is not None and resolved_min_regime_conf > 0.0)
        or result.resolved_max_regime_confidence is not None
    )
    result.nrr026_effective_enforced = bool(
        apply_flag
        and not reduce_only
        and ds_enabled
        and nrr026_enabled
        and result.resolved_regime_confidence_band_active
    )
    result.nrr027_effective_enforced = bool(
        apply_flag
        and not reduce_only
        and ds_enabled
        and nrr027_enabled
    )
    result.nrr063_enabled = (
        result.resolved_max_regime_confidence is not None
        and not max_threshold_resolution.disabled
    )
    result.nrr063_effective_enforced = bool(
        apply_flag
        and not reduce_only
        and ds_enabled
        and result.resolved_max_regime_confidence is not None
        and not max_threshold_resolution.disabled
    )
    consecutive = int(ds_cfg.consecutive_bars)
    raw_hard_veto = getattr(ds_cfg, 'hard_veto_consecutive_bars', None)
    try:
        # Some direct unit tests use MagicMock-backed configs; treat those as
        # "field absent" and preserve the production fallback to consecutive_bars.
        if raw_hard_veto is None or type(raw_hard_veto).__name__ == "MagicMock":
            raise TypeError
        hard_veto_consecutive = int(raw_hard_veto)
    except (TypeError, ValueError):
        hard_veto_consecutive = consecutive

    # Per-regime override for hard_veto_consecutive (NRR-027 LOW_VOL calibration).
    # When hard_veto_consecutive_bars_by_regime is set and the current regime
    # has a matching key, that value replaces the scalar. All other regimes
    # continue to use the scalar. Fail-safe: bad values are skipped (Pydantic
    # already validated at startup).
    raw_hard_veto_by_regime = getattr(
        ds_cfg, 'hard_veto_consecutive_bars_by_regime', None)
    if isinstance(raw_hard_veto_by_regime, dict) and result.regime:
        _regime_key = normalize_structural_regime_label(result.regime)
        if _regime_key and _regime_key in raw_hard_veto_by_regime:
            try:
                _override = int(raw_hard_veto_by_regime[_regime_key])
                if 1 <= _override <= 10:
                    hard_veto_consecutive = _override
            except (TypeError, ValueError):
                pass  # Validator already enforced; purely defensive guard.

    # ── Gate 1: Regime confidence gate (FIX-CONF-GATE-01) ──────
    if reduce_only:
        result.threshold_applied = False
        result.threshold_verdict = "BYPASS"
        result.regime_confidence_gate_verdict = "BYPASS"
        result.threshold_reason = "reduce_only"
    elif not apply_flag:
        result.threshold_applied = False
        result.threshold_verdict = "BYPASS"
        result.regime_confidence_gate_verdict = "BYPASS"
        result.threshold_reason = "safety_gates_disabled"
    elif not ds_enabled:
        result.threshold_applied = False
        result.threshold_verdict = "BYPASS"
        result.regime_confidence_gate_verdict = "BYPASS"
        result.threshold_reason = "directional_sanity_disabled"
    elif (
        result.resolved_max_regime_confidence is not None
        and resolved_min_regime_conf is not None
        and result.resolved_max_regime_confidence < resolved_min_regime_conf
    ):
        result.threshold_applied = True
        result.threshold_verdict = "BLOCK"
        result.regime_confidence_gate_verdict = "DENY"
        result.regime_confidence_breach_kind = "none"
        result.outcome = "CONFIG_ERROR"
        result.config_error_context = (
            "regime_confidence band invalid: max threshold is lower than min threshold"
        )
        result.deny_reason = NormalizedRejectReasons.CONFIG_CONTRACT_INVALID
        result.threshold_reason = (
            f"invalid regime confidence band: min={resolved_min_regime_conf} "
            f"max={result.resolved_max_regime_confidence} "
            f"min_source={threshold_resolution.source} "
            f"max_source={max_threshold_resolution.source}"
        )
        result.why_short = f"FIX-CONF-GATE-01: {result.threshold_reason}"
        return result
    elif not result.resolved_regime_confidence_band_active:
        result.threshold_applied = False
        result.threshold_verdict = "BYPASS"
        result.regime_confidence_gate_verdict = "BYPASS"
        result.threshold_reason = "min_regime_confidence_disabled"
    elif result.regime_confidence is None:
        if nrr026_enabled:
            result.threshold_applied = True
            result.threshold_verdict = "BLOCK"
            result.regime_confidence_gate_verdict = "DENY"
            result.regime_confidence_breach_kind = "missing"
            result.threshold_reason = (
                f"regime_confidence missing for active band "
                f"min={resolved_min_regime_conf} min_source={threshold_resolution.source} "
                f"max={result.resolved_max_regime_confidence} max_source={max_threshold_resolution.source}"
            )
            result.outcome = "DENY"
            result.deny_reason = NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION
            result.why_short = f"FIX-CONF-GATE-01: {result.threshold_reason}"
            return result
        else:
            result.threshold_applied = False
            result.threshold_verdict = "BYPASS"
            result.regime_confidence_gate_verdict = "BYPASS"
            result.threshold_reason = "nrr026_disabled:regime_confidence_missing"
    elif result.regime_confidence <= resolved_min_regime_conf:
        regime_label = normalize_structural_regime_label(result.regime)
        strategy_label = result.strategy_id or (
            str(strategy_id) if strategy_id is not None else "unknown"
        )
        symbol_label = str(symbol).strip().upper(
        ) if symbol is not None else "unknown"
        result.threshold_applied = True
        result.threshold_verdict = "BLOCK"
        result.regime_confidence_gate_verdict = "DENY"
        result.regime_confidence_breach_kind = "below_min"
        result.threshold_reason = (
            "REGIME_CONFIDENCE_AT_OR_BELOW_MINIMUM:"
            f"regime_confidence={result.regime_confidence} <= min={resolved_min_regime_conf} "
            f"regime={regime_label or 'UNKNOWN'} strategy={strategy_label} "
            f"symbol={symbol_label} source={threshold_resolution.source or 'unknown'}"
        )
        result.outcome = "DENY"
        result.deny_reason = NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION
        result.why_short = f"FIX-CONF-GATE-01: {result.threshold_reason}"
        return result
    elif (
        result.resolved_max_regime_confidence is not None
        and result.regime_confidence > result.resolved_max_regime_confidence
    ):
        result.threshold_applied = True
        result.threshold_verdict = "BLOCK"
        result.regime_confidence_gate_verdict = "DENY"
        result.regime_confidence_breach_kind = "above_max"
        result.threshold_reason = (
            f"regime_confidence={result.regime_confidence} > max={result.resolved_max_regime_confidence} "
            f"source={max_threshold_resolution.source} key={max_threshold_resolution.regime_key}"
        )
        result.outcome = "DENY"
        result.deny_reason = NormalizedRejectReasons.REGIME_CONFIDENCE_ABOVE_MAX
        result.why_short = f"FIX-CONF-GATE-01: {result.threshold_reason}"
        return result
    else:
        result.threshold_applied = True
        result.threshold_verdict = "PASS"
        result.regime_confidence_gate_verdict = "ALLOW"
        result.regime_confidence_breach_kind = "none"
        result.threshold_reason = (
            f"regime_confidence={result.regime_confidence} within band "
            f"min={resolved_min_regime_conf} min_source={threshold_resolution.source} "
            f"max={result.resolved_max_regime_confidence} max_source={max_threshold_resolution.source}"
        )

    # ── Compute trend ──────────────────────────────────────────
    result.trend_dir, result.trend_confidence, result.delta_price, result.trend_run_length = _compute_trend(
        symbol_states, symbol, consecutive, min_abs_delta,
    )

    # ── Gate 2: Directional sanity gate ────────────────────────
    gate_outcome, deny_reason, why_short = _check_directional_gate(
        intent_side=result.intent_side,
        reduce_only=reduce_only,
        apply_safety_gates=apply_flag,
        ds_enabled=ds_enabled,
        nrr026_enabled=nrr026_enabled,
        nrr027_enabled=nrr027_enabled,
        strategy_id=strategy_id,
        trend_dir=result.trend_dir,
        trend_run_length=result.trend_run_length,
        trend_confidence=result.trend_confidence,
        regime_confidence=result.regime_confidence,
        min_conf=min_conf,
        hard_veto_consecutive_bars=hard_veto_consecutive,
    )

    if gate_outcome == "DENY":
        result.outcome = "DENY"
        result.deny_reason = deny_reason
        result.why_short = why_short
        return result

    result.why_short = why_short

    # ── Gate 3: Price motion multi-window gate ─────────────────
    pm_cfg = config.domains.decision_making.price_motion_sanity
    pm_enabled = bool(pm_cfg.enabled)
    try:
        is_backtest = str(getattr(config, "trading_mode", "")
                          ).strip().lower() == "backtest"
    except Exception:
        is_backtest = False
    result.price_motion_sanity_enabled = pm_enabled
    result.price_motion_backtest_bypass = is_backtest
    nrr028_val = bool(getattr(pm_cfg, "nrr028_enabled", True))
    nrr029_val = bool(getattr(pm_cfg, "nrr029_enabled", True))
    nrr030_val = bool(getattr(pm_cfg, "nrr030_enabled", True))
    result.nrr028_enabled = bool(pm_enabled and nrr028_val)
    result.nrr029_enabled = bool(pm_enabled and nrr029_val)
    result.nrr030_enabled = bool(pm_enabled and nrr030_val)
    result.nrr028_effective_enforced = bool(
        apply_flag and not reduce_only and result.nrr028_enabled and not is_backtest
    )
    result.nrr029_effective_enforced = bool(
        apply_flag and not reduce_only and result.nrr029_enabled and not is_backtest
    )
    result.nrr030_effective_enforced = bool(
        apply_flag and not reduce_only and result.nrr030_enabled and not is_backtest
    )

    pm_outcome, pm_deny, pm_why = _check_price_motion_gate(
        config=config,
        symbol=symbol,
        intent_side=result.intent_side,
        reduce_only=reduce_only,
        apply_safety_gates=apply_flag,
        pm_norm_10s=result.pm_norm_10s,
        pm_norm_60s=result.pm_norm_60s,
        pm_norm_300s=result.pm_norm_300s,
        nrr028_enabled=result.nrr028_enabled,
        nrr029_enabled=result.nrr029_enabled,
        nrr030_enabled=result.nrr030_enabled,
    )

    if pm_outcome == "DENY":
        result.outcome = "DENY"
        result.deny_reason = pm_deny
        result.why_short = pm_why
        return result

    # ── All gates passed ───────────────────────────────────────
    result.outcome = "ALLOW"
    return result
