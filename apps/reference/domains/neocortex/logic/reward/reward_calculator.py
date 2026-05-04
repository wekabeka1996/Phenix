"""
RegimeRewardCalculator: Compute PPO reward for regime predictions.

REGIME_PIVOT_PLAN Section 3.3 — Reward Formulas.

Formula A (default): Exact match → +reward_correct * class_weight, mismatch → reward_wrong.
Formula B (opt-in):  Confusion-weighted matrix with per-pair rewards.
"""

from __future__ import annotations

# QUARANTINED: legacy_runtime
__quarantined__ = True

import logging
import math
from typing import Dict, List, Optional

from .regime_labeler import REGIME_NAMES

logger = logging.getLogger(__name__)

# Number of regime actions
NUM_ACTIONS = 5

# Formula B: Confusion reward matrix  C[predicted][realized]
# Rows = predicted action, Cols = realized regime
# NOTE: Kept as a documented legacy reference for tests/audits. Runtime Formula B
# requires an explicit matrix from config and must not fall back to this constant.
#                         T_UP    T_DOWN   MR      H_VOL   EXHAUST
REWARD_MATRIX: List[List[float]] = [
    # predicted TREND_UP
    [+1.0,   -1.0,   -0.3,   -0.8,   -0.5],
    # predicted TREND_DOWN
    [-1.0,   +1.0,   -0.3,   -0.8,   -0.5],
    # predicted MEAN_REVERSION
    [-0.3,   -0.3,   +1.0,   -0.6,   -0.3],
    # predicted HIGH_VOLATILITY  (MR penalty: -1.0)
    [-0.5,   -0.5,   -1.0,   +1.0,   +0.3],
    # predicted EXHAUSTION  (MR penalty: -1.0)
    [-0.3,   -0.3,   -1.0,   +0.3,   +1.0],
]

# Ordered action names (index → name) for class_weights lookup
ACTION_NAMES = [
    "PREDICT_TREND_UP",
    "PREDICT_TREND_DOWN",
    "PREDICT_MEAN_REVERSION",
    "PREDICT_HIGH_VOLATILITY",
    "PREDICT_EXHAUSTION",
]


def _validated_reward_matrix(reward_matrix: Optional[List[List[float]]]) -> List[List[float]]:
    if reward_matrix is None:
        raise ValueError(
            "reward_matrix is required when reward_matrix_enabled=True")
    if len(reward_matrix) != NUM_ACTIONS:
        raise ValueError(f"reward_matrix must have {NUM_ACTIONS} rows")
    validated: List[List[float]] = []
    for row_index, row in enumerate(reward_matrix):
        if len(row) != NUM_ACTIONS:
            raise ValueError(
                f"reward_matrix row {row_index} must have {NUM_ACTIONS} columns"
            )
        validated_row: List[float] = []
        for column_index, value in enumerate(row):
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError(
                    "reward_matrix values must be finite: "
                    f"row={row_index} col={column_index} value={value!r}"
                )
            validated_row.append(numeric)
        validated.append(validated_row)
    return validated


class RegimeRewardCalculator:
    """Compute reward for a regime prediction given the realized regime.

    Supports Formula A (exact match) and Formula B (confusion matrix).
    Class weights applied to correct predictions to counteract label imbalance.
    """

    def __init__(
        self,
        reward_correct: float,
        reward_wrong: float,
        reward_matrix_enabled: bool = False,
        class_weights: Optional[Dict[str, float]] = None,
        reward_matrix: Optional[List[List[float]]] = None,
    ) -> None:
        self.reward_correct = reward_correct
        self.reward_wrong = reward_wrong
        self.reward_matrix_enabled = reward_matrix_enabled

        self._reward_matrix: List[List[float]] = []
        if self.reward_matrix_enabled:
            self._reward_matrix = _validated_reward_matrix(reward_matrix)

        # Build weight vector indexed by action (0-4)
        self._class_weights: List[float] = [1.0] * NUM_ACTIONS
        if class_weights:
            for i, name in enumerate(ACTION_NAMES):
                if name in class_weights:
                    self._class_weights[i] = class_weights[name]

    @classmethod
    def from_config(cls, config) -> "RegimeRewardCalculator":
        """Construct from an OracleConfig instance."""
        return cls(
            reward_correct=config.reward_correct,
            reward_wrong=config.reward_wrong,
            reward_matrix_enabled=config.reward_matrix_enabled,
            class_weights=config.class_weights,
            reward_matrix=getattr(config, "reward_matrix", None),
        )

    def compute_reward(self, predicted_action: int, realized_regime: int) -> float:
        """Calculate reward for a single prediction.

        Args:
            predicted_action: PPO action index (0-4).
            realized_regime: Ground-truth regime index (0-4) from RegimeLabeler.

        Returns:
            Scalar reward value.
        """
        if not (0 <= predicted_action < NUM_ACTIONS):
            logger.warning(
                "Invalid predicted_action=%d, returning reward_wrong", predicted_action)
            return self.reward_wrong
        if not (0 <= realized_regime < NUM_ACTIONS):
            logger.warning(
                "Invalid realized_regime=%d, returning reward_wrong", realized_regime)
            return self.reward_wrong

        if self.reward_matrix_enabled:
            return self._formula_b(predicted_action, realized_regime)
        return self._formula_a(predicted_action, realized_regime)

    def _formula_a(self, predicted: int, realized: int) -> float:
        """Formula A: Exact match with class-weighted correct reward."""
        if predicted == realized:
            return self.reward_correct * self._class_weights[predicted]
        return self.reward_wrong

    def _formula_b(self, predicted: int, realized: int) -> float:
        """Formula B: Confusion-weighted matrix reward."""
        return self._reward_matrix[predicted][realized]
