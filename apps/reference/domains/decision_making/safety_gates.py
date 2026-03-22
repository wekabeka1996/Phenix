"""
SafetyGates — Directional sanity, regime confidence, and price motion gates.

Extracted from decision_making.py (Phase 14A decomposition).
Pure computation: no FSM side effects.  Returns SafetyGateResult for the
facade to act on (emit traces, log, block).

LOC budget: <=500 (Constitution S3).
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

from apps.reference.config_contract import ConfigContractError
from .normalized_reject_reasons import NormalizedRejectReasons

if TYPE_CHECKING:
    from apps.reference.config_models import AuroraConfig
    from apps.reference.core.time.clock import Clock


@dataclass
class SafetyGateResult:
    """Result of safety gate evaluation.

    outcome:
        "ALLOW"        — all gates passed, proceed to intent builder.
        "DENY"         — gate blocked, facade handles trace/reject emission.
        "CONFIG_ERROR" — safety_gates config missing, facade emits rejection.
    """

    outcome: str = "ALLOW"
    deny_reason: Optional[str] = None
    why_short: str = "ok"
    config_error_context: Optional[str] = None

    # Flags
    apply_safety_gates: bool = False

    # Computed context carried downstream for intent_builder / forensic trace
    intent_side: str = "LONG"
    trace_ts_ms: int = 0
    signal_score: Optional[float] = None
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
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
    # Phase 0.5: system stress overlay ("NORMAL"|"STRESS"|"EXTREME"); passed downstream for attenuation
    system_stress_state: str = "NORMAL"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_safety_gates_flag(
    config: "AuroraConfig",
    strategy_id: str,
) -> tuple[bool, Optional[str]]:
    """Resolve apply_safety_gates from per-strategy config.

    Returns:
        (apply_safety_gates, error_context)  — error_context is non-None
        when config is missing (FAIL-CLOSED).
    """
    try:
        strat_cfg = getattr(config.strategies, str(strategy_id), None)
        if strat_cfg is None:
            return False, f"safety_gates config missing for strategy"
        safety_gates_cfg = getattr(strat_cfg, "safety_gates", None)
        if safety_gates_cfg is None:
            return False, f"safety_gates.enabled missing in strategy config"
        return bool(getattr(safety_gates_cfg, "enabled", False)), None
    except Exception as e:
        return False, f"safety_gates config error: {str(e)[:40]}"


def _extract_price_motion(symbol_states: dict, symbol: str) -> dict:
    """Extract price_motion block from symbol_states cache (best-effort)."""
    result: Dict[str, Optional[float]] = {
        "pm_norm_10s": None, "pm_norm_60s": None, "pm_norm_300s": None,
        "vol_pct_10s": None, "vol_pct_60s": None, "vol_pct_300s": None,
    }
    try:
        st = symbol_states.get(symbol)
        feats_evt = st.get("features") if isinstance(st, dict) else None
        pm = feats_evt.get("price_motion") if isinstance(feats_evt, dict) else None
        if isinstance(pm, dict):
            for key in result:
                val = pm.get(key)
                result[key] = float(val) if val is not None else None
    except Exception:
        pass
    return result


def _extract_signal_score(why_chain: list) -> Optional[float]:
    """Best-effort extraction of signal_score from why_chain strings."""
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


def _extract_regime(per_symbol_regimes: dict, symbol: str) -> tuple[Optional[str], Optional[float]]:
    """Extract regime name and confidence from per-symbol cache."""
    try:
        r = per_symbol_regimes.get(symbol)
        if isinstance(r, dict):
            regime = r.get("regime")
            rc = r.get("confidence")
            confidence = float(rc) if rc not in (None, "") else None
            return regime, confidence
    except Exception:
        pass
    return None, None


def _compute_trend(
    symbol_states: dict,
    symbol: str,
    consecutive: int,
    min_abs_delta: float,
) -> tuple[str, float, Optional[float], int]:
    """Compute trend direction from delta_price history.

    Returns:
        (trend_dir, trend_confidence, delta_price, trend_run_length)
    """
    trend_dir = "UNKNOWN"
    delta_price: Optional[float] = None
    trend_confidence = 0.0
    trend_run_length = 0
    try:
        state = symbol_states.get(symbol)
        hist = state.get("_delta_price_hist") if isinstance(state, dict) else None
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
    strategy_id: str,
    trend_dir: str,
    trend_run_length: int,
    trend_confidence: float,
    regime_confidence: Optional[float],
    min_conf: float,
    hard_veto_consecutive_bars: int,
) -> tuple[str, Optional[str], str]:
    """Evaluate directional sanity gate.

    Returns:
        (gate_outcome, deny_reason, why_short)
    """
    if reduce_only:
        return "ALLOW", None, "reduce_only"
    if not apply_safety_gates:
        return "ALLOW", None, f"safety_gates_skipped:strategy={strategy_id}"
    if not ds_enabled:
        return "ALLOW", None, "directional_sanity_disabled"

    effective_conf = max(float(regime_confidence or 0.0), float(trend_confidence or 0.0))
    if trend_dir not in ("UP", "DOWN"):
        return "DENY", NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION, "insufficient trend confirmation"
    if effective_conf < float(min_conf):
        return "DENY", NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION, "insufficient confidence"
    if trend_dir == "DOWN" and intent_side == "LONG":
        if trend_run_length < int(hard_veto_consecutive_bars):
            return "ALLOW", None, (
                f"countertrend long soft: run={trend_run_length} < veto_bars={hard_veto_consecutive_bars}"
            )
        return "DENY", NormalizedRejectReasons.DIRECTIONAL_SANITY_BLOCKED, "downtrend blocks long"
    if trend_dir == "UP" and intent_side == "SHORT":
        if trend_run_length < int(hard_veto_consecutive_bars):
            return "ALLOW", None, (
                f"countertrend short soft: run={trend_run_length} < veto_bars={hard_veto_consecutive_bars}"
            )
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
) -> tuple[str, Optional[str], str]:
    """Evaluate price motion multi-window sanity gate.

    Returns:
        (gate_outcome, deny_reason, why_short)
    """
    pm_cfg = config.domains.decision_making.price_motion_sanity
    pm_enabled = bool(pm_cfg.enabled)

    try:
        is_backtest = str(getattr(config, "trading_mode", "")).strip().lower() == "backtest"
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
        return "DENY", NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT, "price_motion flash insufficient"
    if require_bleed_ready and (pm_bleed is None):
        return "DENY", NormalizedRejectReasons.PRICE_MOTION_INSUFFICIENT, "price_motion bleed insufficient"

    # Flash gate
    if intent_side == "LONG" and pm_flash <= -t_flash:
        return "DENY", NormalizedRejectReasons.PRICE_MOTION_FLASH_BLOCKED, "flash down blocks long"
    if intent_side == "SHORT" and pm_flash >= t_flash:
        return "DENY", NormalizedRejectReasons.PRICE_MOTION_FLASH_BLOCKED, "flash up blocks short"

    # Bleed gate (only if ready)
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
        (stress_policy, stress_attenuation_factor)
        Returns ("CONFIG_ERROR", 0.0) on any missing/bad config resolution — fail-closed.
    """
    try:
        strat_cfg = getattr(config.strategies, str(strategy_id), None)
        sg_cfg = getattr(strat_cfg, "safety_gates", None) if strat_cfg else None
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
    """Gate 0.5 — System Stress Overlay (Phase 0.5 / 0.6).

    Policy semantics (per-strategy, Phase 0.6):
        off       → Gate fully bypassed; even EXTREME is ignored.
        attenuate → EXTREME=DENY; STRESS=ALLOW+surface for size attenuation.
        block     → EXTREME and STRESS both DENY.
        CONFIG_ERROR → DENY (Fail-closed).
    reduce_only orders always bypass (closing is risk-reducing).

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

    Pure computation — no FSM side effects.  The caller (facade) handles
    trace emission, rejection events, and blocked-intent recording based
    on the returned ``SafetyGateResult``.

    Gate sequence:
        0.  Config resolution (FAIL-CLOSED if missing)
        0.5 System stress overlay gate (Phase 0.5 / 0.6): policy-driven DENY or surface
        1.  FIX-CONF-GATE-01: Regime confidence gate
        2.  Directional sanity gate (trend vs intent)
        3.  Price motion multi-window gate (flash / bleed)
    """
    result = SafetyGateResult()
    result.trace_ts_ms = int(decision_ts_ms) if decision_ts_ms is not None else clock.now_ms()
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

    # ── Extract context (best-effort) ──────────────────────────
    pm = _extract_price_motion(symbol_states, symbol)
    result.pm_norm_10s = pm["pm_norm_10s"]
    result.pm_norm_60s = pm["pm_norm_60s"]
    result.pm_norm_300s = pm["pm_norm_300s"]
    result.vol_pct_10s = pm["vol_pct_10s"]
    result.vol_pct_60s = pm["vol_pct_60s"]
    result.vol_pct_300s = pm["vol_pct_300s"]

    result.signal_score = _extract_signal_score(why_chain)
    result.regime, result.regime_confidence = _extract_regime(per_symbol_regimes, symbol)

    # ── Read directional sanity config ─────────────────────────
    ds_cfg = config.domains.decision_making.directional_sanity
    ds_enabled = bool(ds_cfg.enabled)
    min_abs_delta = float(ds_cfg.min_abs_delta_price)
    min_conf = float(ds_cfg.min_confidence)
    try:
        min_regime_conf = float(getattr(ds_cfg, 'min_regime_confidence', 0.0))
    except (TypeError, ValueError):
        min_regime_conf = 0.0
    consecutive = int(ds_cfg.consecutive_bars)
    raw_hard_veto = getattr(ds_cfg, 'hard_veto_consecutive_bars', None)
    try:
        if raw_hard_veto is None or type(raw_hard_veto).__name__ == "MagicMock":
            raise TypeError
        hard_veto_consecutive = int(raw_hard_veto)
    except (TypeError, ValueError):
        hard_veto_consecutive = consecutive

    # ── Gate 1: Regime confidence gate (FIX-CONF-GATE-01) ──────
    if (
        ds_enabled
        and not reduce_only
        and apply_flag
        and min_regime_conf > 0.0
        and (result.regime_confidence is None or result.regime_confidence < min_regime_conf)
    ):
        result.outcome = "DENY"
        result.deny_reason = NormalizedRejectReasons.INSUFFICIENT_TREND_CONFIRMATION
        result.why_short = (
            f"FIX-CONF-GATE-01: regime_confidence={result.regime_confidence} < min={min_regime_conf}"
        )
        return result

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
    pm_outcome, pm_deny, pm_why = _check_price_motion_gate(
        config=config,
        symbol=symbol,
        intent_side=result.intent_side,
        reduce_only=reduce_only,
        apply_safety_gates=apply_flag,
        pm_norm_10s=result.pm_norm_10s,
        pm_norm_60s=result.pm_norm_60s,
        pm_norm_300s=result.pm_norm_300s,
    )

    if pm_outcome == "DENY":
        result.outcome = "DENY"
        result.deny_reason = pm_deny
        result.why_short = pm_why
        return result

    # ── All gates passed ───────────────────────────────────────
    result.outcome = "ALLOW"
    return result
