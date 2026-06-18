"""
Feature Log Parser

Parses feature log entries from logs/features/*.log

Format:
    TIMESTAMP - MODULE - LEVEL - Calculated features for SYMBOL: {JSON}

Example:
    2026-01-09 12:58:42,585 - ...FeatureEngineering - INFO - Calculated features for SOLUSDT: {"obi": "-0.68...", ...}
"""

import re
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import math

from apps.reference.domains.neocortex.contracts.causal_time import (
    CausalTimeDecision,
    make_causal_decision,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
    coerce_causal_time_provenance,
    is_causal_time_provenance,
)
from .wallclock import parse_log_wallclock_ms

logger = logging.getLogger(__name__)


@dataclass
class FeatureLogEntry:
    """Parsed feature log entry."""
    timestamp: float
    event_ts_ms: int
    timestamp_str: str
    symbol: str
    features: Dict[str, float]
    raw_line: str
    time_source: str = "event_ts_ms"
    time_is_causal: bool = True
    time_provenance: CausalTimeProvenance = CausalTimeProvenance.UNKNOWN
    # Phase 1 I3 fields — always set by parse_feature_log_line
    trainable: bool = False
    dataset_visibility: str = "diagnostics_only"
    reason_code: Optional[str] = None

    @property
    def event_time_is_causal(self) -> bool:
        """Compatibility alias for Phase 1 contract terminology."""
        return self.time_is_causal


# Pattern: YYYY-MM-DD HH:MM:SS,mmm - MODULE - LEVEL - Calculated features for SYMBOL: {JSON}
FEATURE_LOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})'  # Timestamp
    r' - .+? - INFO - '  # Module and level
    r'Calculated features for ([A-Z0-9]+): '  # Symbol
    r'(\{.+\})$'  # JSON payload
)

_TIME_FIELD_PRIORITY = (
    "event_ts_ms",
    "timestamp_ms",
    "timestamp",
    "ts",
)


def _normalize_epoch_to_ms(value: Any) -> Optional[int]:
    """Normalize epoch-like timestamp to integer milliseconds."""
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(numeric) or numeric <= 0.0:
        return None

    # >= ~1973 in milliseconds.
    if numeric >= 1e11:
        return int(round(numeric))

    # >= ~2001 in seconds.
    if numeric >= 1e9:
        return int(round(numeric * 1000.0))

    return None


def _extract_feature_event_ts_ms(raw_features: Dict[str, Any]) -> tuple[Optional[int], Dict[str, Any], Optional[str]]:
    """
    Extract canonical event_ts_ms from a pure JSON feature payload.

    Returns a sanitized copy with timestamp-like fields removed from the feature map.
    """
    sanitized = dict(raw_features)
    for key in _TIME_FIELD_PRIORITY:
        if key not in sanitized:
            continue
        event_ts_ms = _normalize_epoch_to_ms(sanitized.pop(key))
        if event_ts_ms is not None:
            return event_ts_ms, sanitized, key
    return None, sanitized, None


def _flatten_and_coerce_features(raw: Dict[str, Any]) -> Dict[str, float]:
    """
    Flatten nested feature dicts and coerce leaf values to float.

    Examples:
      {"volatility": {"atr_14": null}} -> {"volatility_atr_14": 0.0}
      {"volatility.atr_14": "1.23"} -> {"volatility_atr_14": 1.23}
    """
    out: Dict[str, float] = {}

    def _coerce(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0

    def _emit(key: str, value: Any) -> None:
        if key not in out:
            out[key] = _coerce(value)

    def _recurse(prefix_parts: list[str], obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and "." in k:
                    parts = [p for p in k.split(".") if p]
                else:
                    parts = [str(k)]
                _recurse(prefix_parts + parts, v)
            return

        flat_key = "_".join([p for p in prefix_parts if p])
        _emit(flat_key, obj)

    _recurse([], raw)
    return out


def parse_feature_log_line(
    line: str,
    symbol: str | None = None,
    *,
    missing_timestamp_policy: str = "fail_closed",
    synthetic_event_ts_ms: Optional[int] = None,
) -> Optional[FeatureLogEntry]:
    """
    Parse a single feature log line.

    Supports two formats:
    1. Pure JSON: {"obi": "0.5", "tfi": "0.9", ...}
    2. Full log: TIMESTAMP - MODULE - INFO - Calculated features for SYMBOL: {JSON}

    Args:
        line: Raw log line
        symbol: Symbol name (used for pure JSON format)

    Returns:
        FeatureLogEntry if successful, None otherwise
    """
    line = line.strip()
    if not line:
        return None

    # Try pure JSON format first (new format in logs/features/*.log)
    if line.startswith('{'):
        try:
            raw_features = json.loads(line)
            if not isinstance(raw_features, dict):
                return None

            explicit_provenance = CausalTimeProvenance.UNKNOWN
            for key in (
                "time_provenance",
                "causal_time_provenance",
                "event_time_provenance",
                "time_source",
                "event_time_source",
            ):
                explicit_provenance = coerce_causal_time_provenance(
                    raw_features.get(key)
                )
                if explicit_provenance != CausalTimeProvenance.UNKNOWN:
                    break

            event_ts_ms, sanitized_features, time_source = _extract_feature_event_ts_ms(
                raw_features
            )
            time_provenance = explicit_provenance
            if event_ts_ms is None:
                if missing_timestamp_policy == "legacy_non_causal_file_offset":
                    event_ts_ms = _normalize_epoch_to_ms(synthetic_event_ts_ms)
                    time_source = "legacy_non_causal_file_offset"
                    time_provenance = CausalTimeProvenance.FILE_OFFSET_LEGACY
                    if event_ts_ms is not None:
                        record_failure_outcome(
                            FailureOutcomeTaxonomy.LEGACY_DIAGNOSTIC_ONLY,
                            "NON_CAUSAL_TIME",
                            source="neocortex.ingest.parsers.feature_parser.parse_feature_log_line",
                            detail=symbol or "UNKNOWN",
                            message="legacy non-causal feature row",
                            recoverable=True,
                            fallback_applied=False,
                        )
                elif missing_timestamp_policy != "fail_closed":
                    raise ValueError(
                        f"Unsupported missing_timestamp_policy={missing_timestamp_policy!r}"
                    )
            elif time_provenance == CausalTimeProvenance.UNKNOWN:
                time_provenance = CausalTimeProvenance.AURORA_EVENT

            if event_ts_ms is None:
                record_failure_outcome(
                    FailureOutcomeTaxonomy.SKIP_ROW,
                    "MISSING_REQUIRED_STATE",
                    source="neocortex.ingest.parsers.feature_parser.parse_feature_log_line",
                    detail=symbol or "UNKNOWN",
                    message="feature row missing causal timestamp",
                    recoverable=True,
                    fallback_applied=False,
                )
                logger.warning(
                    "Rejecting feature row without causal timestamp: symbol=%s policy=%s",
                    symbol or "UNKNOWN",
                    missing_timestamp_policy,
                )
                return None

            features = _flatten_and_coerce_features(sanitized_features)

            decision_json: CausalTimeDecision = make_causal_decision(
                event_ts_ms, time_provenance)
            return FeatureLogEntry(
                timestamp=event_ts_ms / 1000.0,
                event_ts_ms=event_ts_ms,
                timestamp_str="",
                symbol=symbol or "UNKNOWN",
                features=features,
                raw_line=line,
                time_source=time_source or "event_ts_ms",
                time_is_causal=decision_json.event_time_is_causal,
                time_provenance=time_provenance,
                trainable=decision_json.trainable,
                dataset_visibility=decision_json.dataset_visibility,
                reason_code=decision_json.reason_code,
            )
        except json.JSONDecodeError as error:
            record_failure_outcome(
                FailureOutcomeTaxonomy.SKIP_ROW,
                "MALFORMED_JSON",
                source="neocortex.ingest.parsers.feature_parser.parse_feature_log_line",
                detail=type(error).__name__,
                message="malformed feature JSON payload",
                recoverable=True,
                fallback_applied=False,
            )
            pass

    # Try full log format (TIMESTAMP - MODULE - INFO - ...)
    match = FEATURE_LOG_PATTERN.match(line)
    if match:
        timestamp_str = match.group(1)
        parsed_symbol = match.group(2)
        json_str = match.group(3)

        try:
            # Parse timestamp
            event_ts_ms = parse_log_wallclock_ms(timestamp_str)
            if event_ts_ms is None:
                raise ValueError("invalid log timestamp or AURORA_LOG_TIMEZONE")
            timestamp = event_ts_ms / 1000.0

            # Parse JSON features
            raw_features = json.loads(json_str)
            if not isinstance(raw_features, dict):
                return None

            features = _flatten_and_coerce_features(raw_features)

            decision_log: CausalTimeDecision = make_causal_decision(
                event_ts_ms, CausalTimeProvenance.CAPTURED_WALLCLOCK
            )
            return FeatureLogEntry(
                timestamp=timestamp,
                event_ts_ms=event_ts_ms,
                timestamp_str=timestamp_str,
                symbol=parsed_symbol,
                features=features,
                raw_line=line,
                time_source="log_timestamp",
                time_is_causal=False,
                time_provenance=CausalTimeProvenance.CAPTURED_WALLCLOCK,
                trainable=decision_log.trainable,
                dataset_visibility=decision_log.dataset_visibility,
                reason_code=decision_log.reason_code,
            )

        except json.JSONDecodeError as error:
            record_failure_outcome(
                FailureOutcomeTaxonomy.SKIP_ROW,
                "MALFORMED_JSON",
                source="neocortex.ingest.parsers.feature_parser.parse_feature_log_line",
                detail=type(error).__name__,
                message="malformed feature log JSON payload",
                recoverable=True,
                fallback_applied=False,
            )
            logger.debug(f"Failed to parse feature log: {error}")
            return None
        except ValueError as error:
            record_failure_outcome(
                FailureOutcomeTaxonomy.SKIP_ROW,
                "MISSING_REQUIRED_STATE",
                source="neocortex.ingest.parsers.feature_parser.parse_feature_log_line",
                detail=type(error).__name__,
                message=str(error),
                recoverable=True,
                fallback_applied=False,
            )
            logger.debug(f"Failed to parse feature log: {error}")
            return None

    return None


def parse_feature_log_file(file_path: str) -> list:
    """
    Parse an entire feature log file.

    Args:
        file_path: Path to log file

    Returns:
        List of FeatureLogEntry objects
    """
    entries = []
    with open(file_path, 'r') as f:
        for line in f:
            entry = parse_feature_log_line(line)
            if entry:
                entries.append(entry)
    return entries
