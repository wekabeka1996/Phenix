"""
LLM Judge Phase 2 — Signal Weights Expert (Layer 1: Pure Scoring)

Revives the legacy flat weighted-centering formula (SignalScoreV2) as an
explicit shadow expert. Returns AlphaScore only — no event emission, no
logging, no ExpertOutput construction.

Formula: score = SUM(w[f] * (x[f] - neutral[f])) / SUM(|w[f]|)

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE2_IMPLEMENTATION_BLUEPRINT.md §12.1
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from apps.reference.domains.alpha_search.alpha_model import AlphaModel, AlphaScore
from apps.reference.domains.alpha_search.judge.config_models import (
    SignalWeightsExpertConfig,
)

LOG = logging.getLogger(__name__)


class SignalWeightsExpert(AlphaModel):
    """Flat weighted-centering expert.

    Pure scoring unit. Receives features from calculate_alpha(), computes
    score via the recovered legacy formula, returns AlphaScore.
    """

    def __init__(self, expert_config: SignalWeightsExpertConfig):
        self._expert_config = expert_config
        super().__init__(config=expert_config.model_dump())

    def get_model_name(self) -> str:
        return self._expert_config.expert_id

    def get_required_features(self) -> List[str]:
        return [
            f
            for f, w in self._expert_config.signal_weights.items()
            if w != 0
        ]

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

        reasoning: List[str] = []

        # Fail-closed: no features
        if not features:
            return self._unknown_score(symbol, ["NRR-NO-FEATURES"])

        # Check essential feature readiness
        for feat in essential:
            if feat not in features or features[feat] is None:
                return self._unknown_score(
                    symbol, [f"DEFER:{feat}"]
                )

        # Compute weighted centered score
        score_raw = 0.0
        wabs_total = 0.0
        active_feature_count = 0
        contributions: List[str] = []
        features_used: List[str] = []

        for feat, w in weights.items():
            if w == 0:
                continue
            if feat not in features or features[feat] is None:
                continue  # skip missing non-essential features
            x = float(features[feat])
            n = float(neutrals.get(feat, 0.0))
            centered = x - n
            contrib = w * centered
            score_raw += contrib
            wabs_total += abs(w)
            active_feature_count += 1
            features_used.append(feat)
            contributions.append(f"{feat}: w={w:.3f} c={centered:.4f} → {contrib:.4f}")

        # Fail-closed: all weights zero or no active features
        if wabs_total == 0:
            return self._unknown_score(symbol, ["NRR-ALL-WEIGHTS-ZERO"])
        if active_feature_count < cfg.min_active_features:
            return self._unknown_score(
                symbol,
                [
                    "NRR-INSUFFICIENT-ACTIVE-FEATURES:"
                    f"{active_feature_count}/{cfg.min_active_features}"
                ],
            )

        score = score_raw / wabs_total

        # Map to verdict direction
        if score > threshold:
            direction = "LONG"
            reasoning.append(f"score={score:.4f} > threshold={threshold} → OPEN_LONG")
        elif score < -threshold:
            direction = "SHORT"
            reasoning.append(f"score={score:.4f} < -{threshold} → OPEN_SHORT")
        else:
            direction = "NEUTRAL"
            reasoning.append(f"|score|={abs(score):.4f} <= threshold={threshold} → NO_ENTRY")

        reasoning.extend(contributions)

        confidence = min(1.0, abs(score))

        # Clamp score to [-1, 1]
        clamped_score = max(-1.0, min(1.0, score))

        return AlphaScore(
            model_name=self.name,
            symbol=symbol,
            score=Decimal(str(round(clamped_score, 8))),
            confidence=Decimal(str(round(confidence, 8))),
            features_used=features_used,
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
