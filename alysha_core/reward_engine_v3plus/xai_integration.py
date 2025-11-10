"""
XAI Integration for RewardEngineV3Plus

This module provides explainable AI (XAI) capabilities for the reward engine,
ensuring compatibility with existing XAI infrastructure and ISKAP-DTS framework.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import math
import statistics

from .data_types import TotalRewardResult, RewardComponentResult
from .utils import RewardEngineConfig


logger = logging.getLogger(__name__)


class RewardEngineXAI:
    """
    XAI integration layer for RewardEngineV3Plus.

    Provides explainable AI capabilities including:
    - Component importance analysis
    - Decision explanation generation
    - XAI trace logging
    - Integration with existing XAI infrastructure
    """

    def __init__(self, config: RewardEngineConfig):
        """
        Initialize XAI integration.

        Args:
            config: RewardEngineConfig instance with access to master_config.yaml
        """
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Завантажуємо конфігурацію XAI з центрального конфігу
        self.xai_config = self.config.get_component_config("xai_engine")
        if not self.xai_config:
            raise ValueError("alysha_reward_engine.xai_engine section not found in configuration")

        self.xai_enabled = self.xai_config.get("enabled", False)

        if not self.xai_enabled:
            self.logger.info("RewardEngineXAI is disabled in the configuration.")
            return

        # Налаштування XAI з конфігурації БЕЗ hardcode fallbacks
        try:
            self.explainability_threshold = self.xai_config["explainability_threshold"]
            self.feature_importance_min = self.xai_config["feature_importance_min"]
            self.save_explanations = self.xai_config["save_explanations"]
            log_dir = self.config.get("logging.log_dir", "logs")
            self.explanation_log_path = Path(log_dir) / "xai"
            self.explanation_log_path.mkdir(parents=True, exist_ok=True)
        except KeyError as e:
            self.logger.error(f"Missing required XAI configuration parameter: {e}")
            raise ValueError(f"Missing required XAI configuration parameter: {e}") from e

        self.logger.info("RewardEngineXAI initialized successfully")

    def generate_explanation(self, reward_result: TotalRewardResult) -> Dict[str, Any]:
        """
        Generate comprehensive explanation for reward calculation.

        Args:
            reward_result: Result from RewardEngineV3Plus

        Returns:
            Dictionary with detailed explanation
        """
        if not self.xai_enabled:
            return self._create_disabled_explanation()

        try:
            # Component analysis
            component_analysis = self._analyze_components(reward_result.component_rewards)

            # Importance scoring
            importance_scores = self._calculate_importance_scores(reward_result.component_rewards)

            # Generate textual explanation
            explanation_text = self._generate_explanation_text(
                reward_result.total_reward, component_analysis, importance_scores
            )

            # Feature importance analysis
            feature_importance = self._analyze_feature_importance(reward_result)

            # Decision factors
            decision_factors = self._extract_decision_factors(reward_result)

            explanation = {
                "trace_id": f"reward_engine_{int(datetime.now().timestamp())}",
                "timestamp_utc": datetime.utcnow().isoformat(),
                "component_source": "RewardEngineV3Plus",
                "event_type": "REWARD_CALCULATION",
                "total_reward": reward_result.total_reward,
                "component_breakdown": component_analysis,
                "importance_scores": importance_scores,
                "explanation_text": explanation_text,
                "feature_importance": feature_importance,
                "decision_factors": decision_factors,
                "explainability_score": self._calculate_explainability_score(importance_scores),
                "confidence_score": self._calculate_confidence_score(reward_result),
                "metadata": {
                    "engine_version": "V3Plus",
                    "adaptive_weights": reward_result.adaptive_weights,
                    "normalization_stats": reward_result.normalization_stats,
                    "timestamp": reward_result.timestamp,
                },
            }

            # Log explanation if enabled
            if self.save_explanations:
                self._log_explanation(explanation)

            return explanation

        except Exception as e:
            self.logger.error(f"Error generating explanation: {e}", exc_info=True)
            return self._create_error_explanation(str(e))

    def _analyze_components(
        self, component_rewards: Dict[str, RewardComponentResult]
    ) -> Dict[str, Any]:
        """Analyze individual reward components."""
        analysis = {}

        for component_name, result in component_rewards.items():
            # Використовуємо raw_value для аналізу внеску
            value = result.raw_value

            analysis[component_name] = {
                "value": value,
                "normalized_value": result.normalized_value,
                "contribution_percent": 0.0,  # Will be calculated later
                "impact_level": self._classify_impact_level(value),
                "direction": "positive" if value > 0 else "negative" if value < 0 else "neutral",
            }

        # Calculate contribution percentages
        total_abs = sum(abs(comp["value"]) for comp in analysis.values())
        if total_abs > 0:
            for comp in analysis.values():
                comp["contribution_percent"] = abs(comp["value"]) / total_abs * 100

        return analysis

    def _calculate_importance_scores(
        self, component_rewards: Dict[str, RewardComponentResult]
    ) -> Dict[str, float]:
        """Calculate importance scores for each component."""
        values = {name: abs(result.raw_value) for name, result in component_rewards.items()}

        # Normalize to importance scores
        total = sum(values.values())
        if total == 0:
            return {name: 0.0 for name in values}

        return {name: value / total for name, value in values.items()}

    def _generate_explanation_text(
        self,
        total_reward: float,
        component_analysis: Dict[str, Any],
        importance_scores: Dict[str, float],
    ) -> str:
        """Generate human-readable explanation text."""

        explanation_parts = [f"Total reward: {total_reward:.4f}"]

        # Sort components by importance
        sorted_components = sorted(
            component_analysis.items(), key=lambda x: importance_scores.get(x[0], 0), reverse=True
        )

        # Describe top contributing components
        top_components = sorted_components[:3]  # Top 3 components

        for component_name, analysis in top_components:
            importance = importance_scores.get(component_name, 0)
            if importance > self.feature_importance_min:
                value = analysis["value"]
                direction = analysis["direction"]
                contribution = analysis["contribution_percent"]

                if direction == "positive":
                    explanation_parts.append(
                        f"{component_name.title()} contributes positively ({value:.4f}, "
                        f"{contribution:.1f}% of total impact)"
                    )
                elif direction == "negative":
                    explanation_parts.append(
                        f"{component_name.title()} has negative impact ({value:.4f}, "
                        f"{contribution:.1f}% of total impact)"
                    )

        # Overall assessment
        if total_reward > 0.1:
            explanation_parts.append("Overall assessment: Positive reward signal")
        elif total_reward < -0.1:
            explanation_parts.append("Overall assessment: Negative reward signal")
        else:
            explanation_parts.append("Overall assessment: Neutral reward signal")

        return ". ".join(explanation_parts) + "."

    def _analyze_feature_importance(self, reward_result: TotalRewardResult) -> Dict[str, float]:
        """Analyze feature importance using SHAP-like methodology."""
        feature_importance = {}

        # Extract component contributions
        for component_name, result in reward_result.component_rewards.items():
            feature_importance[f"{component_name}_component"] = abs(result.raw_value)

        # Add adaptive weight importance
        for weight_name, weight_value in reward_result.adaptive_weights.items():
            feature_importance[f"{weight_name}_weight"] = abs(weight_value - 1.0)

        # Normalize
        total = sum(feature_importance.values())
        if total > 0:
            feature_importance = {k: v / total for k, v in feature_importance.items()}

        return feature_importance

    def _extract_decision_factors(self, reward_result: TotalRewardResult) -> List[Dict[str, Any]]:
        """Extract key decision factors that influenced the reward."""
        factors = []

        # Component-based factors
        for component_name, result in reward_result.component_rewards.items():
            if abs(result.raw_value) > self.feature_importance_min:
                factors.append(
                    {
                        "factor_type": "component",
                        "factor_name": component_name,
                        "influence": result.raw_value,
                        "description": f"{component_name.title()} component contribution",
                    }
                )

        # Weight adaptation factors
        for weight_name, weight_value in reward_result.adaptive_weights.items():
            if abs(weight_value - 1.0) > 0.1:  # Significant deviation from default
                factors.append(
                    {
                        "factor_type": "weight_adaptation",
                        "factor_name": weight_name,
                        "influence": weight_value - 1.0,
                        "description": f"Adaptive weight adjustment for {weight_name}",
                    }
                )

        # Sort by absolute influence
        factors.sort(key=lambda x: abs(x["influence"]), reverse=True)

        return factors[:5]  # Top 5 factors

    def _classify_impact_level(self, value: float) -> str:
        """Classify impact level based on value magnitude."""
        abs_value = abs(value)
        if abs_value > 1.0:
            return "high"
        elif abs_value > 0.1:
            return "medium"
        elif abs_value > 0.01:
            return "low"
        else:
            return "minimal"

    def _calculate_explainability_score(self, importance_scores: Dict[str, float]) -> float:
        """Calculate how explainable the decision is."""
        # Higher score when importance is concentrated in fewer components
        if not importance_scores:
            return 0.0

        # Calculate entropy (lower entropy = more explainable)
        entropy = -sum(
            score * math.log(score + 1e-8) for score in importance_scores.values() if score > 0
        )

        # Convert to explainability score (0-1, higher is more explainable)
        max_entropy = math.log(len(importance_scores)) if len(importance_scores) > 1 else 1.0
        if max_entropy == 0:
            return 1.0

        return 1.0 - (entropy / max_entropy)

    def _calculate_confidence_score(self, reward_result: TotalRewardResult) -> float:
        """Calculate confidence in the reward calculation."""
        # Simple confidence based on component consistency
        values = [res.raw_value for res in reward_result.component_rewards.values()]

        if not values:
            return 0.0

        # Higher confidence when components are more consistent
        if len(values) > 1:
            mean_val = statistics.mean(values)
            std_val = statistics.stdev(values)
            if abs(mean_val) > 1e-8:
                cv = std_val / abs(mean_val)  # Coefficient of variation
                confidence = max(0.0, 1.0 - cv)
            else:
                confidence = 0.5
        else:
            confidence = 0.8

        return min(1.0, confidence)

    def _log_explanation(self, explanation: Dict[str, Any]) -> None:
        """Log explanation to file for audit and analysis."""
        try:
            log_file = self.explanation_log_path / "reward_explanations.jsonl"

            # Create log entry
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": explanation["trace_id"],
                "total_reward": explanation["total_reward"],
                "explainability_score": explanation["explainability_score"],
                "confidence_score": explanation["confidence_score"],
                "top_components": dict(list(explanation["importance_scores"].items())[:3]),
                "explanation_summary": (
                    explanation["explanation_text"][:200] + "..."
                    if len(explanation["explanation_text"]) > 200
                    else explanation["explanation_text"]
                ),
            }

            # Append to log file
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            self.logger.error(f"Failed to log explanation: {e}")

    def _create_error_explanation(self, error_msg: str) -> Dict[str, Any]:
        """Create explanation for error cases."""
        return {
            "trace_id": f"error_{int(datetime.now().timestamp())}",
            "timestamp_utc": datetime.utcnow().isoformat(),
            "component_source": "RewardEngineV3Plus",
            "event_type": "REWARD_CALCULATION_ERROR",
            "error_message": error_msg,
            "explainability_score": 0.0,
            "confidence_score": 0.0,
            "explanation_text": f"Error in reward calculation: {error_msg}",
        }

    def _create_disabled_explanation(self) -> Dict[str, Any]:
        """Create a standard explanation for when XAI is disabled."""
        return {
            "trace_id": f"disabled_{int(datetime.now().timestamp())}",
            "timestamp_utc": datetime.utcnow().isoformat(),
            "component_source": "RewardEngineV3Plus",
            "event_type": "XAI_DISABLED",
            "error_message": "XAI is disabled in the configuration.",
            "explainability_score": 0.0,
            "confidence_score": 0.0,
            "explanation_text": "XAI functionality is disabled.",
        }

    def create_xai_trace(
        self, reward_result: TotalRewardResult, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create XAI trace compatible with existing XAI infrastructure.

        Args:
            reward_result: Result from reward engine
            context: Additional context information

        Returns:
            XAI trace in standard format
        """
        if not self.xai_enabled:
            return self._create_disabled_explanation()

        explanation = self.generate_explanation(reward_result)

        # Create XAI trace in standard format
        xai_trace = {
            "trace_id": explanation["trace_id"],
            "timestamp_event_utc": explanation["timestamp_utc"],
            "component_source": "RewardEngineV3Plus",
            "event_type": "REWARD_CALCULATION",
            # Standard XAI fields
            "feature_importance": explanation.get("feature_importance", {}),
            "explanation_text": explanation.get("explanation_text", "N/A"),
            "explainability_score": explanation.get("explainability_score", 0.0),
            "confidence_score": explanation.get("confidence_score", 0.0),
            # Reward engine specific fields
            "total_reward": explanation.get("total_reward", 0.0),
            "component_breakdown": explanation.get("component_breakdown", {}),
            "decision_factors": explanation.get("decision_factors", []),
            # Context
            "context": context or {},
            "metadata": explanation.get("metadata", {}),
        }

        return xai_trace

    def is_explainable(self, explanation: Dict[str, Any]) -> bool:
        """Check if the explanation meets explainability threshold."""
        if not self.xai_enabled:
            return False
        return explanation.get("explainability_score", 0.0) >= self.explainability_threshold
