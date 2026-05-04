"""Aurora pure math layer — Package 2.

This module owns ONLY numeric transformations for the Aurora scoring path:
- linear input scaling and clamping
- signed score transforms (quadratic, linear, soft_power)
- shield attenuation (numeric multiplication, NOT policy gating)

It does NOT decide:
- buy vs sell
- neutral vs actionable
- hysteresis state transitions
- regime-conditioned thresholds
- side-bias penalties
- any business interpretation of score

All functions are pure: no side effects, no state, no config awareness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AuroraMathInput:
    """Prepared numeric inputs for the Aurora math transform.

    All values must already be resolved and validated upstream.
    Missing or invalid inputs should be caught BEFORE constructing this object.
    """
    s_linear: float
    source: str  # "arg" or "feature:pillar_sum"
    score_multiplier: float = 1.0
    admission_mode: str = "quadratic"
    admission_power: Optional[float] = None
    sizing_mode: str = "quadratic"
    sizing_power: Optional[float] = None
    admission_shield_floor: float = 0.0

    # Shield inputs — the shield function itself is math (attenuation),
    # the decision to enable it is policy (handled upstream).
    symbol: str = ""
    features: Dict[str, Any] = field(default_factory=dict)
    pillar_contribs: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuroraMathOutput:
    """Pure numeric result from the Aurora math transform.

    Contains NO side decision, NO threshold interpretation, NO policy.
    The caller (policy or orchestration) uses these numbers to make decisions.
    """
    # Raw linear input
    s_linear: float
    source: str

    # Scaled and clamped
    s_scaled_raw: float
    s_clamped: float
    clamped: bool

    # Pre-shield transforms
    admission_pre_shield: float
    sizing_pre_shield: float

    # Shield attenuation (numeric)
    shield_multiplier: float
    admission_shield_multiplier: float
    shield_reasons: List[str]

    # Post-shield scores — the PRIMARY numeric outputs
    decision_score: float
    sizing_score: float

    # Transform config echo (for tracing)
    score_multiplier: float
    admission_mode: str
    admission_power: Optional[float]
    sizing_mode: str
    sizing_power: Optional[float]
    admission_shield_floor: float

    # Explainability sub-payload
    pillar_contribs: Dict[str, float]


# Type alias for the shield callable.
# (symbol, features, pillar_sum, raw_exposure) -> (multiplier, reasons)
ShieldFn = Callable[
    [str, Dict[str, Any], float, float],
    tuple[float, List[str]],
]


def _null_shield(
    symbol: str,
    features: Dict[str, Any],
    pillar_sum: float,
    raw_exposure: float,
) -> tuple[float, List[str]]:
    """Pass-through shield: no attenuation."""
    return 1.0, []


# ---------------------------------------------------------------------------
# Pure math functions
# ---------------------------------------------------------------------------

def transform_signed_score(
    value: float,
    *,
    mode: str,
    power: Optional[float],
) -> float:
    """Transform a signed score magnitude under the configured geometry mode.

    Supported modes:
    - ``quadratic``: sign(x) * |x|^2
    - ``linear``: x unchanged
    - ``soft_power``: sign(x) * |x|^power

    Raises ValueError on unsupported mode or missing power for soft_power.
    """
    sign = 1.0 if value >= 0 else -1.0
    magnitude = abs(value)

    if mode == "quadratic":
        return sign * (magnitude ** 2)
    if mode == "linear":
        return value
    if mode == "soft_power":
        if power is None:
            raise ValueError("soft_power transform requires explicit power")
        return sign * (magnitude ** float(power))
    raise ValueError(f"unsupported transform mode: {mode}")


def scale_and_clamp(s_linear: float, multiplier: float) -> tuple[float, float, bool]:
    """Scale linear input by multiplier and clamp to [-1, 1].

    Returns (scaled_raw, clamped_value, was_clamped).
    """
    s_scaled_raw = s_linear * multiplier
    s_clamped = max(-1.0, min(1.0, s_scaled_raw))
    return s_scaled_raw, s_clamped, s_scaled_raw != s_clamped


def apply_shield_attenuation(
    *,
    admission_pre_shield: float,
    sizing_pre_shield: float,
    shield_multiplier: float,
    admission_shield_floor: float,
) -> tuple[float, float, float]:
    """Apply shield attenuation to admission and sizing scores.

    Returns (decision_score, sizing_score, admission_shield_multiplier).

    Hard veto (shield_mult=0) forces both to zero. The admission floor only
    lifts a non-zero attenuation — never overrides a hard veto.
    """
    shield_mult = max(0.0, min(1.0, shield_multiplier))

    if shield_mult == 0.0:
        admission_shield_mult = 0.0
    else:
        admission_shield_mult = max(
            shield_mult,
            max(0.0, min(1.0, admission_shield_floor)),
        )

    decision_score = admission_pre_shield * admission_shield_mult
    sizing_score = sizing_pre_shield * shield_mult

    return decision_score, sizing_score, admission_shield_mult


# ---------------------------------------------------------------------------
# Top-level math entry point
# ---------------------------------------------------------------------------

def compute_aurora_math(
    inp: AuroraMathInput,
    shield_fn: Optional[ShieldFn] = None,
) -> AuroraMathOutput:
    """Execute the full Aurora math transform pipeline.

    Pipeline:
    1. scale_and_clamp(s_linear, multiplier)
    2. transform admission and sizing scores
    3. shield attenuation
    4. return numeric outputs

    This function is PURE: no side effects, no policy decisions.
    It may raise ValueError on invalid transform modes.
    """
    _shield = shield_fn or _null_shield

    # Step 1: Scale and clamp
    s_scaled_raw, s_clamped, clamped = scale_and_clamp(
        inp.s_linear, inp.score_multiplier
    )

    # Step 2: Transform
    admission_pre_shield = transform_signed_score(
        s_clamped, mode=inp.admission_mode, power=inp.admission_power
    )
    sizing_pre_shield = transform_signed_score(
        s_clamped, mode=inp.sizing_mode, power=inp.sizing_power
    )

    # Step 3: Shield (numeric attenuation)
    shield_mult, shield_reasons = _shield(
        inp.symbol, inp.features, inp.s_linear, sizing_pre_shield
    )
    shield_mult = max(0.0, min(1.0, shield_mult))

    decision_score, sizing_score, admission_shield_mult = apply_shield_attenuation(
        admission_pre_shield=admission_pre_shield,
        sizing_pre_shield=sizing_pre_shield,
        shield_multiplier=shield_mult,
        admission_shield_floor=inp.admission_shield_floor,
    )

    return AuroraMathOutput(
        s_linear=inp.s_linear,
        source=inp.source,
        s_scaled_raw=s_scaled_raw,
        s_clamped=s_clamped,
        clamped=clamped,
        admission_pre_shield=admission_pre_shield,
        sizing_pre_shield=sizing_pre_shield,
        shield_multiplier=shield_mult,
        admission_shield_multiplier=admission_shield_mult,
        shield_reasons=list(shield_reasons),
        decision_score=decision_score,
        sizing_score=sizing_score,
        score_multiplier=inp.score_multiplier,
        admission_mode=inp.admission_mode,
        admission_power=inp.admission_power,
        sizing_mode=inp.sizing_mode,
        sizing_power=inp.sizing_power,
        admission_shield_floor=inp.admission_shield_floor,
        pillar_contribs=dict(inp.pillar_contribs),
    )
