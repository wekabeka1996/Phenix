"""Schema registry and validation helpers for calibration datasets.

Provides fail-closed validation for dataset rows against registered schemas.
Unknown schemas, missing required fields, extra fields, and invalid timestamps
all raise exceptions.
"""

from typing import Any, Type

from pydantic import BaseModel, ValidationError

from calibrators.datasets.schemas import (
    CalibrationFeatureSnapshotRowV1,
    CalibrationLowVolGateRowV1,
    CalibrationMarketBarRowV1,
    CalibrationOracleRegimeLabelRowV1,
    CalibrationRealizedTradeRowV1,
    CalibrationTradeDecisionRowV1,
    CalibrationWalkforwardManifestV1,
)


# Schema registry: maps schema_id to Pydantic model and version
_SCHEMA_REGISTRY = {
    "calibration_market_bar_dataset_v1": {
        "model": CalibrationMarketBarRowV1,
        "version": "1.0.0",
    },
    "calibration_feature_snapshot_dataset_v1": {
        "model": CalibrationFeatureSnapshotRowV1,
        "version": "1.0.0",
    },
    "calibration_oracle_regime_labels_v1": {
        "model": CalibrationOracleRegimeLabelRowV1,
        "version": "1.0.0",
    },
    "calibration_trade_decision_dataset_v1": {
        "model": CalibrationTradeDecisionRowV1,
        "version": "1.0.0",
    },
    "calibration_realized_trade_dataset_v1": {
        "model": CalibrationRealizedTradeRowV1,
        "version": "1.0.0",
    },
    "calibration_low_vol_gate_dataset_v1": {
        "model": CalibrationLowVolGateRowV1,
        "version": "1.0.0",
    },
    "calibration_walkforward_manifest_v1": {
        "model": CalibrationWalkforwardManifestV1,
        "version": "1.0.0",
    },
}


def list_schema_ids() -> list[str]:
    """Return list of registered schema IDs in order."""
    return sorted(_SCHEMA_REGISTRY.keys())


def get_schema_model(schema_id: str) -> Type[BaseModel]:
    """Get Pydantic model for given schema_id.

    Raises:
        KeyError: If schema_id not registered.
    """
    if schema_id not in _SCHEMA_REGISTRY:
        raise KeyError(
            f"Unknown schema_id: {schema_id!r}. "
            f"Registered schemas: {list_schema_ids()}"
        )
    return _SCHEMA_REGISTRY[schema_id]["model"]


def schema_version_for(schema_id: str) -> str:
    """Get schema version string for schema_id.

    Raises:
        KeyError: If schema_id not registered.
    """
    if schema_id not in _SCHEMA_REGISTRY:
        raise KeyError(
            f"Unknown schema_id: {schema_id!r}. "
            f"Registered schemas: {list_schema_ids()}"
        )
    return _SCHEMA_REGISTRY[schema_id]["version"]


def validate_row(schema_id: str, row_dict: dict[str, Any]) -> BaseModel:
    """Validate single row against schema.

    Fail closed: raises on unknown schema, missing required field, extra field,
    or type mismatch.

    Args:
        schema_id: Schema identifier.
        row_dict: Row data as dict.

    Returns:
        Validated Pydantic model instance.

    Raises:
        KeyError: Unknown schema_id.
        ValidationError: Row fails schema validation.
    """
    model_cls = get_schema_model(schema_id)
    try:
        return model_cls(**row_dict)
    except ValidationError as e:
        raise ValidationError.from_exception_data(
            model_cls.__name__, e.errors()
        ) from e


def validate_rows(schema_id: str, rows: list[dict[str, Any]]) -> list[BaseModel]:
    """Validate multiple rows against schema.

    Fail closed: raises on first validation failure.

    Args:
        schema_id: Schema identifier.
        rows: List of row dicts.

    Returns:
        List of validated Pydantic model instances.

    Raises:
        KeyError: Unknown schema_id.
        ValidationError: Any row fails schema validation.
    """
    validated = []
    for i, row_dict in enumerate(rows):
        try:
            validated.append(validate_row(schema_id, row_dict))
        except ValidationError as e:
            raise ValidationError.from_exception_data(
                f"Row {i}",
                e.errors(),
            ) from e
    return validated
