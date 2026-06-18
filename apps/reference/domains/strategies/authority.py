from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any, Iterable

from apps.reference.contracts.runtime_regime_layers import canonical_structural_regime_label


FINANCIAL_MODES = frozenset({"testnet_candidate", "runtime"})


def canonical_signal_regime(payload: Mapping[str, Any]) -> str:
    raw_regime = payload.get("regime")
    candidates = [payload.get("structural_regime")]
    if isinstance(raw_regime, Mapping):
        candidates.extend([raw_regime.get("regime"), raw_regime.get("overall_regime")])
    else:
        candidates.append(raw_regime)
    regime_ctx = payload.get("regime_ctx")
    if isinstance(regime_ctx, Mapping):
        candidates.append(regime_ctx.get("regime"))
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        normalized = canonical_structural_regime_label(candidate)
        if normalized != "UNCERTAIN" or candidate.strip().upper() == "UNCERTAIN":
            return normalized
    return "UNCERTAIN"


def resolve_strategy_mode(strategy_cfg: Any) -> str:
    raw = str(getattr(strategy_cfg, "mode", "disabled") or "disabled").strip().lower()
    aliases = {"live": "runtime", "observe": "shadow", "observe_only": "shadow"}
    return aliases.get(raw, raw)


def assigned_symbols_by_strategy(assignments: Any) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    if not isinstance(assignments, dict):
        return {}
    for symbol, strategy_ids in assignments.items():
        if not isinstance(strategy_ids, list):
            continue
        for strategy_id in strategy_ids:
            if isinstance(strategy_id, str) and strategy_id:
                result[strategy_id].add(str(symbol).upper())
    return dict(result)


def _execution_blockers(execution: Any) -> list[str]:
    if execution is None:
        return ["EXECUTION_POLICY_MISSING"]
    blockers: list[str] = []
    entry_type = str(getattr(execution, "entry_order_type", "") or "").upper()
    entry_tif = getattr(execution, "entry_tif", None)
    if entry_type not in {"LIMIT", "MARKET"}:
        blockers.append("EXECUTION_ENTRY_TYPE_INVALID")
    elif entry_type == "LIMIT" and entry_tif is None:
        blockers.append("EXECUTION_ENTRY_TIF_MISSING")
    elif entry_type == "MARKET" and entry_tif is not None:
        blockers.append("EXECUTION_MARKET_ENTRY_TIF_FORBIDDEN")
    exit_type = str(getattr(execution, "exit_order_type", "") or "").upper()
    exit_tif = getattr(execution, "exit_tif", None)
    if exit_type and exit_type not in {"LIMIT", "MARKET"}:
        blockers.append("EXECUTION_EXIT_TYPE_INVALID")
    elif exit_type == "LIMIT" and exit_tif is None:
        blockers.append("EXECUTION_EXIT_TIF_MISSING")
    elif exit_type == "MARKET" and exit_tif is not None:
        blockers.append("EXECUTION_MARKET_EXIT_TIF_FORBIDDEN")
    return blockers


def _allowed_regimes(strategy_cfg: Any, symbol: str | None = None) -> set[str]:
    asset = None
    assets = getattr(strategy_cfg, "assets", None)
    if symbol and isinstance(assets, dict):
        asset = assets.get(symbol)
    for candidate in (
        getattr(asset, "allowed_regimes", None),
        getattr(strategy_cfg, "allowed_regimes", None),
        getattr(getattr(strategy_cfg, "safety", None), "allowed_regimes", None),
        getattr(getattr(strategy_cfg, "decision", None), "regime_thresholds", None),
    ):
        if isinstance(candidate, dict) and candidate:
            return {str(item).upper() for item in candidate}
        if isinstance(candidate, list) and candidate:
            return {str(item).upper() for item in candidate}
    profile_id = getattr(asset, "profile_id", None)
    profiles = getattr(strategy_cfg, "profiles", None)
    if profile_id and isinstance(profiles, dict):
        profile = profiles.get(profile_id)
        regimes = getattr(profile, "allowed_regimes", None)
        if isinstance(regimes, list):
            return {str(item).upper() for item in regimes}
    return set()


def _allowed_sides(strategy_cfg: Any, symbol: str | None = None) -> set[str]:
    assets = getattr(strategy_cfg, "assets", None)
    asset = assets.get(symbol) if symbol and isinstance(assets, dict) else None
    profile_id = getattr(asset, "profile_id", None)
    profiles = getattr(strategy_cfg, "profiles", None)
    if profile_id and isinstance(profiles, dict):
        profile = profiles.get(profile_id)
        profile_sides = getattr(profile, "allowed_sides", None)
        if isinstance(profile_sides, list) and profile_sides:
            return {str(item).upper() for item in profile_sides}
    sides = getattr(strategy_cfg, "allowed_sides", None)
    if isinstance(sides, list):
        return {str(item).upper() for item in sides}
    return set()


def financial_contract_blockers(
    *,
    strategy_id: str,
    strategy_cfg: Any,
    assigned_symbols: Iterable[str],
    plugin_registered: bool,
) -> list[str]:
    blockers: list[str] = []
    if strategy_cfg is None:
        return ["STRATEGY_PROFILE_MISSING"]
    mode = resolve_strategy_mode(strategy_cfg)
    assigned_symbol_set = {str(item).upper() for item in assigned_symbols}
    if not bool(getattr(strategy_cfg, "enabled", False)):
        blockers.append("STRATEGY_DISABLED")
    if mode == "disabled":
        blockers.append("AUTHORITY_MODE_DISABLED")
    elif mode == "shadow":
        blockers.append("AUTHORITY_MODE_SHADOW")
    elif mode not in FINANCIAL_MODES:
        blockers.append(f"AUTHORITY_MODE_INVALID:{mode}")
    if mode in FINANCIAL_MODES and not assigned_symbol_set:
        blockers.append("NO_ASSIGNED_SYMBOLS")
    if not plugin_registered:
        blockers.append("PLUGIN_NOT_REGISTERED")

    blockers.extend(_execution_blockers(getattr(strategy_cfg, "execution", None)))
    decision = getattr(strategy_cfg, "decision", None)
    kelly = getattr(decision, "kelly", None)
    if kelly is None:
        blockers.append("DECISION_KELLY_MISSING")
    elif mode == "testnet_candidate" and float(getattr(kelly, "kelly_cap", 1.0)) > 0.02:
        blockers.append("TESTNET_KELLY_CAP_EXCEEDS_0_02")

    objective = getattr(strategy_cfg, "objective", None)
    objective_enabled = bool(getattr(objective, "enabled", False))
    objective_regimes = {
        str(item).upper() for item in (getattr(objective, "regimes", {}) or {})
    }
    assets = getattr(strategy_cfg, "assets", None)
    for symbol in sorted(assigned_symbol_set):
        if isinstance(assets, dict):
            asset = assets.get(symbol)
            if asset is None:
                blockers.append(f"ASSET_CONFIG_MISSING:{symbol}")
                continue
            if not bool(getattr(asset, "enabled", False)):
                blockers.append(f"ASSET_DISABLED:{symbol}")
                continue
        regimes = _allowed_regimes(strategy_cfg, symbol)
        if not regimes:
            blockers.append(f"ALLOWED_REGIMES_MISSING:{symbol}")
        sides = _allowed_sides(strategy_cfg, symbol)
        if not sides or not sides.issubset({"BUY", "SELL"}):
            blockers.append(f"ALLOWED_SIDES_MISSING_OR_INVALID:{symbol}")
        if mode in FINANCIAL_MODES:
            if not objective_enabled:
                blockers.append(f"OBJECTIVE_COVERAGE_MISSING:{symbol}")
            else:
                for regime in sorted(regimes - objective_regimes):
                    blockers.append(f"OBJECTIVE_REGIME_MISSING:{symbol}:{regime}")
    return sorted(set(blockers))


def financially_reachable(blockers: Iterable[str]) -> bool:
    return not any(True for _ in blockers)
