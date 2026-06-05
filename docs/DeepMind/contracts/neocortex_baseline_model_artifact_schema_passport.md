# Neocortex Baseline Model Artifact Schema Passport

```yaml
passport_id: "neocortex.baseline_model_artifact_schema.v1"
scope: "Serialized dumb-baseline toxicity model used by the shadow-baseline hot path"
artifact_path: "data/checkpoints/baseline_logreg_v1.pkl"
required_fields:
  - name: "artifact_version"
    purpose: "Artifact lineage / build identity"
    required: true
  - name: "schema_passport"
    purpose: "Explicit contract version and required metadata"
    required: true
  - name: "model"
    purpose: "Predict_proba-capable estimator or pipeline"
    required: true
  - name: "feature_columns"
    purpose: "Ordered input schema used by predict_intent()"
    required: true
  - name: "feature_names"
    purpose: "Alias of feature_columns for audit/reporting"
    required: false
  - name: "threshold"
    purpose: "Decision threshold for toxic probability"
    required: true
  - name: "threshold_provenance"
    purpose: "Why the threshold value is the one used at runtime"
    required: true
  - name: "toxic_label"
    purpose: "Toxic class semantic label, expected to be 1"
    required: true
  - name: "sentinel_policy"
    purpose: "Fail-closed policy describing no synthetic FLAT / zero-latent fallback"
    required: true
  - name: "training"
    purpose: "Training metadata and audit notes"
    required: false
model_contract:
  predict_proba_required: true
  classes_required: true
  toxic_class: 1
failure_behavior:
  missing_artifact: "typed BaselineArtifactError"
  corrupt_artifact: "typed BaselineArtifactError"
  missing_threshold: "typed BaselineArtifactError"
  missing_classes: "typed BaselinePredictionError"
  missing_toxic_class_1: "typed BaselinePredictionError"
  no_synthetic_flat: true
  no_zero_latent: true
  no_default_threshold: true
threshold_provenance:
  accepted_values:
    - "training.tail_holdout"
    - "training.calibration_search"
    - "artifact_embedded"
  rule: "The loader must prefer an explicit configured threshold, then artifact threshold, and reject missing provenance."
```

## Notes

- The passport documents the serialized baseline artifact shipped with the repo and the temp artifacts used in tests.
- The controller remains fail-closed: missing or corrupt artifacts raise typed errors instead of returning neutral business values.
