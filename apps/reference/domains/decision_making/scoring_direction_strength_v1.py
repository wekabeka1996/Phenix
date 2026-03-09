"""
Direction/Strength split scoring wrapper (V1).

This module integrates with SignalScoreV2 WITHOUT changing its kernel logic.

Formula:
  dir      = Σ w_dir * centered(dir_feat) / Σ|w_dir|
  strength = Σ w_str * centered(str_feat) / Σ|w_str|   (clamped to [0, cap], >=0 only)
  final    = dir * (1 + strength_alpha * strength)

Normalization modes:
  - signed_v2: sign-preserving scaling for [0,1] features with neutral=0.5:
               x' = 2*x - 0.5  ⇒  (x' - 0.5) = 2*(x - 0.5) ∈ [-1,1]
               signed features (neutral=0.0) are clamped to [-1,1]
  - off:       forensic/offline passthrough; bypasses transforms. Not valid in production YAML
               (rejected by SignalsConfig Literal["signed_v2"]). Pass directly to scoring fn only.
  - legacy_v1: removed. Was forbidden in live; use 'off' for offline passthrough.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from typing import Any, Dict, List, Set

from .signal_score_v2 import SignalScoreV2, ScoreResult


@dataclass(frozen=True)
class DirectionStrengthScore:
    final_score: decimal.Decimal
    dir_score: decimal.Decimal
    strength_score: decimal.Decimal
    dir_result: ScoreResult
    strength_result: ScoreResult
    deferred: bool
    deny_reason: str | None


def _to_decimal(val: Any) -> decimal.Decimal:
    try:
        return decimal.Decimal(str(val))
    except Exception:
        return decimal.Decimal("0")


def _clamp(x: decimal.Decimal, lo: decimal.Decimal, hi: decimal.Decimal) -> decimal.Decimal:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _apply_signed_v2_transforms(
    *,
    features: Dict[str, Any],
    neutrals: Dict[str, float],
    directional_features: Set[str],
) -> Dict[str, Any]:
    out = dict(features)

    for feat in directional_features:
        if feat not in out or feat not in neutrals:
            continue

        neutral = decimal.Decimal(str(neutrals[feat]))
        raw = out[feat]

        # Preserve missing/malformed values (e.g., None) so downstream fail-closed
        # logic can treat them as missing instead of silently coercing to 0.
        if raw is None:
            continue

        try:
            x = decimal.Decimal(str(raw))
        except Exception:
            continue

        # [0,1] features with neutral 0.5: rescale to make centered component span [-1,1].
        if neutral == decimal.Decimal("0.5"):
            x01 = _clamp(x, decimal.Decimal("0"), decimal.Decimal("1"))
            out[feat] = (decimal.Decimal("2") * x01) - neutral
            continue

        # Signed features with neutral 0.0: clamp to [-1,1] (winsorize).
        if neutral == decimal.Decimal("0"):
            out[feat] = _clamp(x, decimal.Decimal("-1"), decimal.Decimal("1"))
            continue

        # Any other neutral: no transform (keep contract as-is).
        out[feat] = raw

    return out


def compute_direction_strength_score(
    *,
    features: Dict[str, Any],
    weights: Dict[str, float],
    neutrals: Dict[str, float],
    readiness: Dict[str, bool],
    essential_features: Set[str],
    normalize_mode: str,
    directional_features: List[str],
    strength_features: List[str],
    strength_alpha: float,
    strength_cap: float,
    symbol: str,
) -> DirectionStrengthScore:
    if not directional_features:
        return DirectionStrengthScore(
            final_score=decimal.Decimal("0"),
            dir_score=decimal.Decimal("0"),
            strength_score=decimal.Decimal("0"),
            dir_result=ScoreResult(
                score=decimal.Decimal("0"),
                score_raw=decimal.Decimal("0"),
                wabs=decimal.Decimal("0"),
                is_ready=False,
                deferred=True,
                reasons=[],
                missing_features=[],
                not_ready_features=[],
                contribs={},
            ),
            strength_result=ScoreResult(
                score=decimal.Decimal("0"),
                score_raw=decimal.Decimal("0"),
                wabs=decimal.Decimal("0"),
                is_ready=True,
                deferred=False,
                reasons=[],
                missing_features=[],
                not_ready_features=[],
                contribs={},
            ),
            deferred=True,
            deny_reason="NRR-NO-DIRECTIONAL-FEATURES-ACTIVE",
        )

    directional_set = set(directional_features)
    strength_set = set(strength_features)

    if normalize_mode == "signed_v2":
        features_eval = _apply_signed_v2_transforms(
            features=features, neutrals=neutrals, directional_features=directional_set
        )
    elif normalize_mode == "off":
        features_eval = features  # explicit kill-switch: passthrough with no transforms
    else:
        raise ValueError(
            f"compute_direction_strength_score: unknown normalize_mode={normalize_mode!r}. "
            f"Valid values: 'signed_v2', 'off'."
        )

    w_dir = {k: v for k, v in weights.items() if k in directional_set}
    w_str = {k: v for k, v in weights.items() if k in strength_set}

    essential_dir = set(essential_features) & directional_set

    dir_res = SignalScoreV2.calculate_score(
        features=features_eval,
        weights=w_dir,
        neutrals=neutrals,
        readiness=readiness,
        essential_features=essential_dir,
        symbol=symbol,
    )
    if dir_res.deferred:
        return DirectionStrengthScore(
            final_score=decimal.Decimal("0"),
            dir_score=decimal.Decimal("0"),
            strength_score=decimal.Decimal("0"),
            dir_result=dir_res,
            strength_result=ScoreResult(
                score=decimal.Decimal("0"),
                score_raw=decimal.Decimal("0"),
                wabs=decimal.Decimal("0"),
                is_ready=True,
                deferred=False,
                reasons=[],
                missing_features=[],
                not_ready_features=[],
                contribs={},
            ),
            deferred=True,
            deny_reason="NRR-FEATURES-NOT-READY" if dir_res.not_ready_features else "NRR-FEATURES-MISSING",
        )

    if dir_res.wabs == 0:
        return DirectionStrengthScore(
            final_score=decimal.Decimal("0"),
            dir_score=decimal.Decimal("0"),
            strength_score=decimal.Decimal("0"),
            dir_result=dir_res,
            strength_result=ScoreResult(
                score=decimal.Decimal("0"),
                score_raw=decimal.Decimal("0"),
                wabs=decimal.Decimal("0"),
                is_ready=True,
                deferred=False,
                reasons=[],
                missing_features=[],
                not_ready_features=[],
                contribs={},
            ),
            deferred=True,
            deny_reason="NRR-NO-DIRECTIONAL-FEATURES-ACTIVE",
        )

    strength_res = SignalScoreV2.calculate_score(
        features=features_eval,
        weights=w_str,
        neutrals=neutrals,
        readiness=readiness,
        essential_features=set(),
        symbol=symbol,
    )

    dir_score = dir_res.score
    strength_score = strength_res.score

    strength_score = max(decimal.Decimal("0"), strength_score)
    strength_score = min(strength_score, decimal.Decimal(str(strength_cap)))

    alpha_dec = decimal.Decimal(str(strength_alpha))
    final_score = dir_score * (decimal.Decimal("1") + (alpha_dec * strength_score))

    return DirectionStrengthScore(
        final_score=final_score,
        dir_score=dir_score,
        strength_score=strength_score,
        dir_result=dir_res,
        strength_result=strength_res,
        deferred=False,
        deny_reason=None if strength_res.wabs != 0 else "NRR-NO-STRENGTH-FEATURES-ACTIVE",
    )

