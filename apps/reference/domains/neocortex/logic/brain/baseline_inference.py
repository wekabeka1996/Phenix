from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


class BaselineArtifactError(ValueError):
    """Serialized baseline artifact is missing a required contract field."""


class BaselinePredictionError(ValueError):
    """Baseline inference could not produce a valid decision."""


REPO_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_BASELINE_MODEL_PATH = REPO_ROOT / "data" / \
    "checkpoints" / "baseline_logreg_v1.pkl"


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _feature_name(name: str) -> str:
    return f"f_{name}"


def _add_feature(features: dict[str, Any], name: str, value: Any) -> None:
    if value is None:
        return
    feature_name = _feature_name(name)
    if isinstance(value, bool):
        features[feature_name] = float(value)
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric_value = float(value)
        if math.isfinite(numeric_value):
            features[feature_name] = numeric_value
        return
    coerced_numeric = _safe_float(value)
    if coerced_numeric is not None and not isinstance(value, str):
        features[feature_name] = coerced_numeric
        return
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            features[feature_name] = stripped.upper() if len(
                stripped) <= 64 else stripped[:64]


def _flatten_scalars(value: Any, prefix: str, features: dict[str, Any]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten_scalars(
                item, f"{prefix}__{key}" if prefix else str(key), features)
        return
    if isinstance(value, (list, tuple)):
        numeric_values = [
            float(item)
            for item in value
            if isinstance(item, (int, float)) and math.isfinite(float(item))
        ]
        if numeric_values:
            _add_feature(features, f"{prefix}__len", len(numeric_values))
            _add_feature(features, f"{prefix}__mean",
                         float(np.mean(numeric_values)))
            _add_feature(features, f"{prefix}__std",
                         float(np.std(numeric_values)))
            _add_feature(features, f"{prefix}__min",
                         float(np.min(numeric_values)))
            _add_feature(features, f"{prefix}__max",
                         float(np.max(numeric_values)))
        return
    _add_feature(features, prefix, value)


class BaselineController:
    """Runtime loader for the serialized dumb-baseline toxicity model."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_BASELINE_MODEL_PATH,
        *,
        threshold: float | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        try:
            artifact = joblib.load(self.model_path)
        except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
            raise BaselineArtifactError(
                f"failed to load baseline artifact: {self.model_path}"
            ) from error
        if not isinstance(artifact, dict):
            raise BaselineArtifactError("baseline artifact must be a dict")
        model = artifact.get("model")
        if model is None or not hasattr(model, "predict_proba"):
            raise BaselineArtifactError(
                "baseline artifact missing predict_proba model")
        self.model: Any = model
        raw_columns = artifact.get("feature_columns") or []
        self.feature_columns = [str(column) for column in raw_columns]
        if not self.feature_columns:
            raise BaselineArtifactError(
                "baseline artifact missing feature_columns")
        artifact_threshold = _safe_float(artifact.get("threshold"))
        configured_threshold = _safe_float(threshold)
        if configured_threshold is not None:
            self.threshold = configured_threshold
        elif artifact_threshold is not None:
            self.threshold = artifact_threshold
        else:
            raise BaselineArtifactError(
                "baseline toxicity threshold must be provided by config or artifact"
            )

    def predict_intent(self, state_vector: np.ndarray) -> str:
        vector = np.asarray(state_vector, dtype=object)
        if vector.ndim == 0:
            vector = vector.reshape(1)
        if vector.ndim > 1:
            vector = vector.reshape(-1)
        if len(vector) != len(self.feature_columns):
            raise BaselinePredictionError(
                f"state_vector length {len(vector)} does not match model feature count {len(self.feature_columns)}"
            )
        frame = pd.DataFrame([vector.tolist()], columns=self.feature_columns)
        toxic_probability = self.predict_toxic_probability(frame)
        return "BLOCK" if toxic_probability > self.threshold else "ALLOW"

    def predict_toxic_probability(self, feature_frame: pd.DataFrame) -> float:
        probabilities = self.model.predict_proba(feature_frame)
        classes = getattr(self.model, "classes_", None)
        if classes is None and hasattr(self.model, "named_steps"):
            final_model = self.model.named_steps.get("model")
            classes = getattr(final_model, "classes_", None)
        if classes is None:
            raise BaselinePredictionError(
                "baseline model classes_ is required")
        class_values = list(classes)
        if 1 not in class_values:
            raise BaselinePredictionError(
                "baseline model classes_ does not contain toxic class 1")
        toxic_index = class_values.index(1)
        return float(probabilities[0][toxic_index])

    def state_vector_from_snapshot(self, snapshot: Mapping[str, object]) -> np.ndarray:
        features = self._features_from_snapshot(snapshot)
        ordered_values = [features.get(column, np.nan)
                          for column in self.feature_columns]
        return np.asarray(ordered_values, dtype=object)

    def _features_from_snapshot(self, snapshot: Mapping[str, object]) -> dict[str, Any]:
        features: dict[str, Any] = {}
        if not isinstance(snapshot, dict):
            return features

        _add_feature(features, "symbol", snapshot.get("symbol"))
        _add_feature(
            features,
            "snapshot_contract",
            snapshot.get("snapshot_contract")
            or snapshot.get("schema_passport_id")
            or "MISSING",
        )
        _add_feature(
            features,
            "trigger_event_type",
            snapshot.get("trigger_event_type")
            or snapshot.get("source_event_name")
            or "MISSING",
        )

        intent_raw = snapshot.get("intent")
        if not isinstance(intent_raw, dict):
            intent_raw = snapshot.get("candidate_intent_summary")
        intent = intent_raw if isinstance(intent_raw, dict) else {}
        _add_feature(features, "intent__side", intent.get("side"))
        _add_feature(features, "intent__reduce_only",
                     intent.get("reduce_only"))
        _add_feature(features, "intent__proposed_action",
                     intent.get("proposed_action"))
        _add_feature(features, "intent__strategy_id",
                     intent.get("strategy_id"))
        _add_feature(features, "intent__quantity", intent.get("quantity"))

        observation_raw = snapshot.get("observation")
        observation = observation_raw if isinstance(
            observation_raw, dict) else {}
        if not observation:
            market_features = snapshot.get("market_features")
            if isinstance(market_features, dict):
                observation = {"features": market_features}
        raw_features = observation.get("features") if isinstance(
            observation.get("features"), dict) else {}
        _flatten_scalars(raw_features, "observation__features", features)

        safety_gate_raw = snapshot.get("safety_gate")
        if not isinstance(safety_gate_raw, dict):
            safety_gate_raw = snapshot.get("gate_trace_summary")
        safety_gate = safety_gate_raw if isinstance(
            safety_gate_raw, dict) else {}
        _flatten_scalars(safety_gate, "safety_gate", features)

        regime_state_raw = snapshot.get("regime_state")
        regime_state = regime_state_raw if isinstance(
            regime_state_raw, dict) else {}
        _flatten_scalars(regime_state, "regime_state", features)

        portfolio_position_raw = snapshot.get("portfolio_position")
        if not isinstance(portfolio_position_raw, dict):
            portfolio_position_raw = snapshot.get("portfolio_state")
        portfolio_position = (
            portfolio_position_raw
            if isinstance(portfolio_position_raw, dict)
            else {}
        )
        _flatten_scalars(portfolio_position, "portfolio_position", features)
        return features
