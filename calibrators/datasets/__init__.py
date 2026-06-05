"""Canonical dataset schemas for calibration work.

This module provides typed, versioned dataset contracts for offline calibration.
Schemas are separated from builders and runtime to enable independent evolution.

Schemas are OFFLINE ONLY - they document data structures for batch calibration,
not runtime event schemas. No production code should import these models.
"""

from calibrators.datasets.schema_registry import (
    get_schema_model,
    list_schema_ids,
    schema_version_for,
    validate_row,
    validate_rows,
)
from calibrators.datasets.schemas import (
    CalibrationFeatureSnapshotRowV1,
    CalibrationLowVolGateRowV1,
    CalibrationMarketBarRowV1,
    CalibrationOracleRegimeLabelRowV1,
    CalibrationRealizedTradeRowV1,
    CalibrationTradeDecisionRowV1,
    CalibrationWalkforwardManifestV1,
)

__all__ = [
    # Schemas
    "CalibrationMarketBarRowV1",
    "CalibrationFeatureSnapshotRowV1",
    "CalibrationOracleRegimeLabelRowV1",
    "CalibrationTradeDecisionRowV1",
    "CalibrationRealizedTradeRowV1",
    "CalibrationLowVolGateRowV1",
    "CalibrationWalkforwardManifestV1",
    # Registry
    "list_schema_ids",
    "get_schema_model",
    "validate_row",
    "validate_rows",
    "schema_version_for",
]
