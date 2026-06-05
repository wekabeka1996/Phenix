from __future__ import annotations

from typing import Any

from .models import CanonicalEntry, GateDecision, ScenarioRuntime


def _normalize_intent_side(side: str) -> str:
    upper = str(side or "").upper()
    if upper in {"BUY", "LONG"}:
        return "LONG"
    if upper in {"SELL", "SHORT"}:
        return "SHORT"
    return upper


def _resolve_min_conf(entry: CanonicalEntry, ds_cfg: dict[str, Any]) -> float:
    by_regime = ds_cfg.get("min_regime_confidence_by_regime") or {}
    if isinstance(by_regime, dict):
        if entry.regime_at_entry in by_regime:
            return float(by_regime[entry.regime_at_entry])
        if "DEFAULT" in by_regime:
            return float(by_regime["DEFAULT"])
    fallback = entry.resolved_min_regime_confidence
    if fallback is not None:
        return float(fallback)
    return float(ds_cfg.get("min_regime_confidence", ds_cfg.get("min_confidence", 0.0)) or 0.0)


def _resolve_hard_veto(entry: CanonicalEntry, ds_cfg: dict[str, Any]) -> int:
    by_regime = ds_cfg.get("hard_veto_consecutive_bars_by_regime") or {}
    if isinstance(by_regime, dict) and entry.regime_at_entry in by_regime:
        return int(by_regime[entry.regime_at_entry])
    return int(ds_cfg.get("hard_veto_consecutive_bars", 0) or 0)


def evaluate_nrr026(entry: CanonicalEntry, runtime: ScenarioRuntime) -> GateDecision:
    ds_cfg = runtime.config.get("directional_sanity") or {}
    trend_dir = str(entry.trend_dir or "").upper()
    if trend_dir not in {"UP", "DOWN"}:
        return GateDecision(
            allowed=False,
            gate_id="NRR026",
            reason="INSUFFICIENT_TREND_CONFIRMATION",
            detail="trend_dir_missing_or_unknown",
            support_quality="missing_surface_fail_closed",
        )
    effective_conf = max(float(entry.regime_confidence_at_entry or 0.0), float(entry.trend_confidence or 0.0))
    min_conf = _resolve_min_conf(entry, ds_cfg)
    if effective_conf < min_conf:
        return GateDecision(
            allowed=False,
            gate_id="NRR026",
            reason="INSUFFICIENT_TREND_CONFIRMATION",
            detail=f"effective_conf={effective_conf:.6f} < min_conf={min_conf:.6f}",
            support_quality="runtime_parity",
        )
    return GateDecision(
        allowed=True,
        gate_id="NRR026",
        reason="ALLOW",
        detail=f"effective_conf={effective_conf:.6f} >= min_conf={min_conf:.6f}",
        support_quality="runtime_parity",
    )


def evaluate_nrr027(entry: CanonicalEntry, runtime: ScenarioRuntime) -> GateDecision:
    ds_cfg = runtime.config.get("directional_sanity") or {}
    trend_dir = str(entry.trend_dir or "").upper()
    trend_run_length = entry.trend_run_length
    if trend_run_length is None:
        return GateDecision(
            allowed=False,
            gate_id="NRR027",
            reason="DIRECTIONAL_SANITY_MISSING_SURFACE",
            detail="trend_run_length_missing",
            support_quality="missing_surface_fail_closed",
        )
    hard_veto = _resolve_hard_veto(entry, ds_cfg)
    intent_side = _normalize_intent_side(entry.side)
    blocked = False
    if trend_dir == "DOWN" and intent_side == "LONG" and trend_run_length >= hard_veto:
        blocked = True
    if trend_dir == "UP" and intent_side == "SHORT" and trend_run_length >= hard_veto:
        blocked = True
    if blocked:
        return GateDecision(
            allowed=False,
            gate_id="NRR027",
            reason="DIRECTIONAL_SANITY_BLOCKED",
            detail=f"trend_dir={trend_dir} trend_run_length={trend_run_length} hard_veto={hard_veto}",
            support_quality="runtime_parity",
        )
    return GateDecision(
        allowed=True,
        gate_id="NRR027",
        reason="ALLOW",
        detail=f"trend_dir={trend_dir or 'UNKNOWN'} trend_run_length={trend_run_length} hard_veto={hard_veto}",
        support_quality="runtime_parity" if trend_dir in {"UP", "DOWN"} else "partial_surface",
    )


def evaluate_nrr028(entry: CanonicalEntry, runtime: ScenarioRuntime) -> GateDecision:
    pm_cfg = runtime.config.get("price_motion_sanity") or {}
    require_bleed_ready = bool(pm_cfg.get("require_bleed_ready", False))
    if entry.pm_norm_60s is None and require_bleed_ready:
        return GateDecision(
            allowed=False,
            gate_id="NRR028",
            reason="PRICE_MOTION_INSUFFICIENT",
            detail="pm_norm_60s_missing_with_require_bleed_ready",
            support_quality="missing_surface_fail_closed",
        )
    if entry.pm_norm_10s is None:
        return GateDecision(
            allowed=False,
            gate_id="NRR028",
            reason="PRICE_MOTION_INSUFFICIENT",
            detail="pm_norm_10s_missing",
            support_quality="missing_surface_fail_closed",
        )
    return GateDecision(
        allowed=True,
        gate_id="NRR028",
        reason="ALLOW",
        detail="price_motion_ready",
        support_quality="runtime_parity",
    )


def evaluate_nrr029(entry: CanonicalEntry, runtime: ScenarioRuntime) -> GateDecision:
    pm_cfg = runtime.config.get("price_motion_sanity") or {}
    threshold = pm_cfg.get("flash_threshold_norm")
    if entry.pm_norm_10s is None or threshold is None:
        return GateDecision(
            allowed=False,
            gate_id="NRR029",
            reason="PRICE_MOTION_FLASH_BLOCKED_MISSING_SURFACE",
            detail="pm_norm_10s_or_threshold_missing",
            support_quality="missing_surface_fail_closed",
        )
    threshold = float(threshold)
    intent_side = _normalize_intent_side(entry.side)
    blocked = (
        (intent_side == "LONG" and entry.pm_norm_10s <= -threshold)
        or (intent_side == "SHORT" and entry.pm_norm_10s >= threshold)
    )
    if blocked:
        return GateDecision(
            allowed=False,
            gate_id="NRR029",
            reason="PRICE_MOTION_FLASH_BLOCKED",
            detail=f"pm_norm_10s={entry.pm_norm_10s:.6f} threshold={threshold:.6f}",
            support_quality="runtime_parity",
        )
    return GateDecision(
        allowed=True,
        gate_id="NRR029",
        reason="ALLOW",
        detail=f"pm_norm_10s={entry.pm_norm_10s:.6f} threshold={threshold:.6f}",
        support_quality="runtime_parity",
    )


def evaluate_nrr030(entry: CanonicalEntry, runtime: ScenarioRuntime) -> GateDecision:
    pm_cfg = runtime.config.get("price_motion_sanity") or {}
    threshold = pm_cfg.get("bleed_threshold_norm")
    if entry.pm_norm_60s is None or threshold is None:
        return GateDecision(
            allowed=False,
            gate_id="NRR030",
            reason="PRICE_MOTION_BLEED_BLOCKED_MISSING_SURFACE",
            detail="pm_norm_60s_or_threshold_missing",
            support_quality="missing_surface_fail_closed",
        )
    threshold = float(threshold)
    intent_side = _normalize_intent_side(entry.side)
    blocked = (
        (intent_side == "LONG" and entry.pm_norm_60s <= -threshold)
        or (intent_side == "SHORT" and entry.pm_norm_60s >= threshold)
    )
    if blocked:
        return GateDecision(
            allowed=False,
            gate_id="NRR030",
            reason="PRICE_MOTION_BLEED_BLOCKED",
            detail=f"pm_norm_60s={entry.pm_norm_60s:.6f} threshold={threshold:.6f}",
            support_quality="runtime_parity",
        )
    return GateDecision(
        allowed=True,
        gate_id="NRR030",
        reason="ALLOW",
        detail=f"pm_norm_60s={entry.pm_norm_60s:.6f} threshold={threshold:.6f}",
        support_quality="runtime_parity",
    )


def evaluate_gate(entry: CanonicalEntry, runtime: ScenarioRuntime, gate_id: str) -> GateDecision:
    gate_id = gate_id.upper()
    if gate_id == "NRR026":
        return evaluate_nrr026(entry, runtime)
    if gate_id == "NRR027":
        return evaluate_nrr027(entry, runtime)
    if gate_id == "NRR028":
        return evaluate_nrr028(entry, runtime)
    if gate_id == "NRR029":
        return evaluate_nrr029(entry, runtime)
    if gate_id == "NRR030":
        return evaluate_nrr030(entry, runtime)
    raise ValueError(f"Unsupported gate id: {gate_id}")


def evaluate_gate_chain(
    entry: CanonicalEntry,
    runtime: ScenarioRuntime,
    gate_ids: tuple[str, ...],
) -> GateDecision:
    for gate_id in gate_ids:
        decision = evaluate_gate(entry, runtime, gate_id)
        if not decision.allowed:
            return decision
    return GateDecision(
        allowed=True,
        gate_id="+" .join(gate_ids) if gate_ids else "ALLOW_ALL",
        reason="ALLOW",
        detail="all_gates_passed" if gate_ids else "no_entry_filters",
        support_quality="runtime_parity" if gate_ids else "not_applicable",
    )
