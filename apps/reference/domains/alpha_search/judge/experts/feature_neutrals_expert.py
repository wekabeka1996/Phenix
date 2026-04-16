"""
LLM Judge Phase 2 — Feature Neutrals Expert (Layer 1: Pure Scoring)

Revives the legacy direction-strength composite formula as an explicit shadow
expert. Returns AlphaScore only — no event emission, no logging, no
ExpertOutput construction.

Formula:
  dir  = SUM(w_dir * (x - neutral)) / SUM(|w_dir|)
  str  = SUM(w_str * (x - neutral)) / SUM(|w_str|)
  str_clamped = clamp(str, 0, strength_cap)
  final = dir * (1 + strength_alpha * str_clamped)

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md §12.2
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.reference.domains.alpha_search.alpha_model import AlphaModel, AlphaScore
from apps.reference.domains.alpha_search.judge.config_models import (
    FeatureNeutralsExpertConfig,
)

LOG = logging.getLogger(__name__)


def _weighted_centered_score(
    features: Dict[str, Any],
    weights: Dict[str, float],
    neutrals: Dict[str, float],
    essential: set,
) -> tuple:
    """Compute weighted centered score for a subset of features.

    Returns (score, wabs, contributions, deferred_feature_or_None).
    """
    score_raw = 0.0
    wabs_total = 0.0
    contributions: List[str] = []

    for feat, w in weights.items():
        if w == 0:
            continue
        if feat not in features or features[feat] is None:
            if feat in essential:
                return 0.0, 0.0, [], feat
            continue
        x = float(features[feat])
        n = float(neutrals.get(feat, 0.0))
        centered = x - n
        contrib = w * centered
        score_raw += contrib
        wabs_total += abs(w)
        contributions.append(f"{feat}: w={w:.3f} c={centered:.4f} → {contrib:.4f}")

    if wabs_total == 0:
        return 0.0, 0.0, contributions, None

    return score_raw / wabs_total, wabs_total, contributions, None


class FeatureNeutralsExpert(AlphaModel):
    """Direction-strength composite expert.

    Pure scoring unit. Receives features from calculate_alpha(), computes
    score via the recovered legacy direction-strength formula, returns
    AlphaScore.
    """

    def __init__(self, expert_config: FeatureNeutralsExpertConfig):
        self._expert_config = expert_config
        super().__init__(config=expert_config.model_dump())

    def get_model_name(self) -> str:
        return self._expert_config.expert_id

    def get_required_features(self) -> List[str]:
        all_weights = self._expert_config.signal_weights
        return [f for f, w in all_weights.items() if w != 0]

    def calculate_alpha(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        features: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AlphaScore:
        cfg = self._expert_config
        weights = cfg.signal_weights
        neutrals = cfg.feature_neutrals
        essential = set(cfg.essential_features)
        threshold = cfg.signal_threshold
        dir_set = set(cfg.directional_features)
        str_set = set(cfg.strength_features)

        reasoning: List[str] = []

        # Fail-closed: no features
        if not features:
            return self._unknown_score(symbol, ["NRR-NO-FEATURES"])

        # Fail-closed: no directional features configured
        if not dir_set:
            return self._unknown_score(symbol, ["NRR-NO-DIRECTIONAL-FEATURES"])

        # Check essential feature readiness
        for feat in essential:
            if feat not in features or features[feat] is None:
                return self._unknown_score(symbol, [f"DEFER:{feat}"])

        # Partition weights
        w_dir = {f: w for f, w in weights.items() if f in dir_set}
        w_str = {f: w for f, w in weights.items() if f in str_set}

        # Compute directional score
        dir_essential = essential & dir_set
        dir_score, dir_wabs, dir_contribs, deferred = _weighted_centered_score(
            features, w_dir, neutrals, dir_essential
        )
        if deferred:
            return self._unknown_score(symbol, [f"DEFER:{deferred}"])

        if dir_wabs == 0:
            return self._unknown_score(symbol, ["NRR-ALL-DIR-WEIGHTS-ZERO"])

        reasoning.append(f"dir_score={dir_score:.4f}")
        reasoning.extend([f"[dir] {c}" for c in dir_contribs])

        # Compute strength score (no essential requirement for strength)
        str_score, str_wabs, str_contribs, _ = _weighted_centered_score(
            features, w_str, neutrals, set()
        )
        strength_clamped = max(0.0, min(str_score, cfg.strength_cap))

        reasoning.append(
            f"str_score={str_score:.4f} → clamped={strength_clamped:.4f}"
        )
        reasoning.extend([f"[str] {c}" for c in str_contribs])

        # Composite
        final = dir_score * (1.0 + cfg.strength_alpha * strength_clamped)
        reasoning.append(
            f"composite: {dir_score:.4f} * (1 + {cfg.strength_alpha} * "
            f"{strength_clamped:.4f}) = {final:.4f}"
        )

        # Map to verdict direction
        if final > threshold:
            direction = "LONG"
            reasoning.append(
                f"final={final:.4f} > threshold={threshold} → OPEN_LONG"
            )
        elif final < -threshold:
            direction = "SHORT"
            reasoning.append(
                f"final={final:.4f} < -{threshold} → OPEN_SHORT"
            )
        else:
            direction = "NEUTRAL"
            reasoning.append(
                f"|final|={abs(final):.4f} <= threshold={threshold} → NO_ENTRY"
            )

        confidence = min(1.0, abs(final))
        clamped_score = max(-1.0, min(1.0, final))

        all_used = [
            f for f in weights if weights[f] != 0 and f in features
        ]

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=Decimal(str(round(clamped_score, 8))),
            confidence=Decimal(str(round(confidence, 8))),
            features_used=all_used,
            why=reasoning,
        )

    def _unknown_score(self, symbol: str, reasons: List[str]) -> AlphaScore:
        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=Decimal("0"),
            confidence=Decimal("0"),
            features_used=[],
            why=reasons,
        )
