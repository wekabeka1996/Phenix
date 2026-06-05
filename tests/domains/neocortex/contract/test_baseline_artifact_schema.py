from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest

from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineArtifactError,
    BaselineController,
    BaselinePredictionError,
)


BASELINE_ARTIFACT_PATH = Path("data/checkpoints/baseline_logreg_v1.pkl")


class _PredictProbaModel:
    classes_ = np.array([0, 1])

    def predict_proba(self, _frame):
        return np.array([[0.4, 0.6]])


class _NoClassesModel:
    def predict_proba(self, _frame):
        return np.array([[0.4, 0.6]])


class _NoToxicClassModel:
    classes_ = np.array([0])

    def predict_proba(self, _frame):
        return np.array([[1.0]])


def test_real_artifact_exposes_schema_passport() -> None:
    artifact = joblib.load(BASELINE_ARTIFACT_PATH)
    assert artifact["artifact_version"] == "baseline_logreg_v1"
    assert artifact["feature_columns"]
    assert artifact["feature_names"] == artifact["feature_columns"]
    assert artifact["threshold"] == 0.835
    assert artifact["toxic_label"] == 1
    schema_passport = artifact["schema_passport"]
    assert schema_passport["passport_id"] == "neocortex.baseline_model_artifact_schema.v1"
    assert schema_passport["sentinel_policy"] == "fail_closed_no_synthetic_flat"
    assert artifact["threshold_provenance"] == schema_passport["threshold_provenance"]


def test_missing_artifact_raises_typed_error(tmp_path: Path) -> None:
    with pytest.raises(BaselineArtifactError):
        BaselineController(tmp_path / "missing.pkl")


def test_corrupt_artifact_raises_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.pkl"
    path.write_text("not a joblib artifact", encoding="utf-8")
    with pytest.raises(BaselineArtifactError):
        BaselineController(path)


def test_missing_threshold_raises_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "missing-threshold.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": _PredictProbaModel(),
            "feature_columns": ["f_symbol"],
        },
        path,
    )
    with pytest.raises(BaselineArtifactError, match="threshold"):
        BaselineController(path)


def test_missing_classes_raises_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "missing-classes.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": _NoClassesModel(),
            "feature_columns": ["f_symbol"],
            "threshold": 0.5,
        },
        path,
    )
    controller = BaselineController(path)
    with pytest.raises(BaselinePredictionError, match="classes_ is required"):
        controller.predict_intent(np.array(["BTC"]))


def test_missing_toxic_class_raises_typed_error(tmp_path: Path) -> None:
    path = tmp_path / "missing-toxic-class.pkl"
    joblib.dump(
        {
            "artifact_version": "test",
            "model": _NoToxicClassModel(),
            "feature_columns": ["f_symbol"],
            "threshold": 0.5,
        },
        path,
    )
    controller = BaselineController(path)
    with pytest.raises(BaselinePredictionError, match="toxic class 1"):
        controller.predict_intent(np.array(["BTC"]))
