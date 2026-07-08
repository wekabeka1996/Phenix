"""Read-only exchange-filter parity governance and append-safe drift history."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .contracts import FilterParityAcknowledgementV0
from .exchange_info import CACHE_REF, PARITY_REF, REQUIRED_FIELDS, compare_filter_parity


HISTORY_FILENAME = "filter_parity_history_v1.jsonl"
ACK_FILENAME = "filter_parity_operator_acknowledgements_v0.json"
HISTORY_REF = "aurora-publication://filter-parity/history/v1"
ACK_REF = "aurora-operator://filter-parity/acknowledgements/v0"
CONFIG_REF = "aurora://config/instruments#precision"
MAX_HISTORY_BYTES = 4 * 1024 * 1024
MAX_ACK_BYTES = 64 * 1024
MAX_CONSERVATIVE_ACK_MS = 30 * 24 * 60 * 60 * 1000

Transition = Literal["new", "unchanged", "worsened", "improved", "resolved"]


class OperatorAckAuthoredProvenanceV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["operator_authored_offline_file"] = "operator_authored_offline_file"
    format_version: Literal["v0"] = "v0"
    detached_signature: Optional[str] = Field(default=None, max_length=512)
    operator_note_hash: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class OperatorParityAcknowledgementInputV0(BaseModel):
    """Strict operator-authored entry. Identity is explicit and never inferred."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["operator-parity-acknowledgement/v0"] = "operator-parity-acknowledgement/v0"
    ack_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")
    operator_id: str = Field(min_length=2, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")
    operator_display_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    created_ts_ms: int = Field(ge=0)
    expires_ts_ms: int = Field(ge=0)
    symbol: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$")
    venue: str
    environment: str
    state_ref: str
    parity_status: Literal[
        "match", "conservative_mismatch", "risky_mismatch", "missing", "stale", "unavailable"
    ]
    compatibility_assessment: Literal[
        "exact_match", "compatible_conservative", "incompatible_or_looser", "not_assessable"
    ]
    ack_status: Literal[
        "acknowledged_conservative", "acknowledged_requires_review", "rejected", "not_required"
    ]
    ack_reason: str = Field(min_length=8, max_length=512)
    review_required_by_ts_ms: int = Field(ge=0)
    provenance: OperatorAckAuthoredProvenanceV0

    @model_validator(mode="after")
    def validate_lifecycle_and_semantics(self):
        if self.expires_ts_ms <= self.created_ts_ms:
            raise ValueError("expires_ts_ms must be after created_ts_ms")
        if not self.created_ts_ms <= self.review_required_by_ts_ms <= self.expires_ts_ms:
            raise ValueError("review_required_by_ts_ms must be within acknowledgement lifetime")
        if (
            self.parity_status == "conservative_mismatch"
            and self.expires_ts_ms - self.created_ts_ms > MAX_CONSERVATIVE_ACK_MS
        ):
            raise ValueError("conservative acknowledgement lifetime exceeds 30 days")
        if self.ack_status == "acknowledged_conservative" and (
            self.parity_status != "conservative_mismatch"
            or self.compatibility_assessment != "compatible_conservative"
        ):
            raise ValueError("acknowledged_conservative requires a compatible conservative mismatch")
        if self.ack_status == "not_required" and self.parity_status != "match":
            raise ValueError("not_required is only valid for a match")
        if self.parity_status in {"missing", "stale", "unavailable"} and self.ack_status not in {"rejected"}:
            raise ValueError("missing/stale/unavailable parity cannot be acknowledged")
        return self


class OperatorAckProvenanceV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledgement_file_ref: str
    normalized_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    loaded_ts_ms: int = Field(ge=0)
    matching_state_ref: str
    authored: OperatorAckAuthoredProvenanceV0


class OperatorParityAcknowledgementV0(OperatorParityAcknowledgementInputV0):
    """Validated runtime record with computed offline-file provenance."""

    file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal[
        "valid", "expired", "state_mismatch", "rejected", "invalid_semantics"
    ]
    invalid_reason: Optional[str] = Field(default=None, max_length=256)
    validated_provenance: OperatorAckProvenanceV0


class OperatorParityAcknowledgementsFileV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["filter-parity-operator-acknowledgements/v0"] = "filter-parity-operator-acknowledgements/v0"
    acknowledgements: list[OperatorParityAcknowledgementInputV0] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def unique_ack_ids(self):
        ids = [item.ack_id for item in self.acknowledgements]
        if len(ids) != len(set(ids)):
            raise ValueError("ack_id values must be unique")
        return self


@dataclass(frozen=True)
class AckLoadResult:
    acknowledgement: Optional[OperatorParityAcknowledgementV0]
    validation_status: str
    invalid_reason: Optional[str] = None
    provenance_ref: Optional[str] = None
    file_hash: Optional[str] = None


class FilterParityHistoryRowV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["filter-parity-history/v1"] = "filter-parity-history/v1"
    observation_id: str
    timestamp_ms: int
    symbol: str
    venue: str
    environment: str
    exchange_metadata_ref: str
    configured_metadata_ref: str
    state_ref: str
    parity_status: str
    severity: str
    compatibility_assessment: str
    transition: Transition
    acknowledgement_state: str
    acknowledgement_validation_status: str = "missing"
    acknowledgement_id: Optional[str] = None
    operator_id: Optional[str] = None
    acknowledgement_provenance_ref: Optional[str] = None
    requires_yaml_review: bool
    requires_execution_block_before_authority: bool
    source_refs: list[str] = Field(default_factory=list, max_length=4)


def _canonical_hash(values: Mapping[str, Optional[str]]) -> str:
    encoded = json.dumps(dict(values), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ref(prefix: str, values: Mapping[str, Optional[str]]) -> str:
    return f"{prefix}/sha256:{_canonical_hash(values)}"


def _configured(runtime: Any | None, symbol: str) -> Any | None:
    instruments = getattr(getattr(runtime, "config", None), "instruments", None)
    return instruments.get(symbol) if isinstance(instruments, Mapping) else None


def _values(owner: Any | None) -> dict[str, Optional[str]]:
    result: dict[str, Optional[str]] = {}
    for name in REQUIRED_FIELDS:
        raw = getattr(owner, name, None) if owner is not None else None
        try:
            value = Decimal(str(raw)) if raw is not None else None
            result[name] = format(value, "f") if value is not None and value.is_finite() else None
        except (InvalidOperation, TypeError, ValueError):
            result[name] = None
    return result


def _classification(parity: Any) -> tuple[str, str, str, bool, bool]:
    if parity.severity == "match":
        return "match", "info", "exact_match", False, False
    if parity.severity == "minor_mismatch":
        return "conservative_mismatch", "warning", "compatible_conservative", False, False
    if parity.severity == "material_mismatch":
        return "risky_mismatch", "critical", "incompatible_or_looser", True, True
    if parity.severity == "stale_exchange_info":
        return "stale", "unavailable", "not_assessable", False, True
    if parity.severity in {"exchange_missing", "configured_missing"}:
        return "missing", "unavailable", "not_assessable", parity.severity == "configured_missing", True
    return "unavailable", "unavailable", "not_assessable", False, True


def _differences(parity: Any, configured: Mapping[str, Optional[str]]) -> list[str]:
    rows: list[str] = []
    for name in REQUIRED_FIELDS:
        state = parity.fields.get(name)
        if state != "match":
            rows.append(f"{name}:{configured.get(name) or 'missing'}->{parity.exchange_values.get(name) or 'missing'}")
    return rows[:4]


def _rank(status: str) -> int:
    return {
        "match": 0,
        "conservative_mismatch": 1,
        "stale": 2,
        "missing": 3,
        "unavailable": 3,
        "risky_mismatch": 4,
    }.get(status, 3)


def _normalized_document_hash(document: BaseModel) -> str:
    payload = json.dumps(
        document.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_operator_acknowledgement(
    entry: OperatorParityAcknowledgementInputV0,
    *,
    expected_symbol: str,
    expected_venue: str,
    expected_environment: str,
    expected_state_ref: str,
    expected_parity_status: str,
    expected_compatibility: str,
    observed_ts_ms: int,
    file_hash: str,
) -> OperatorParityAcknowledgementV0:
    """Validate identity, exact state, expiry and semantics without granting authority."""

    validation_status = "valid"
    invalid_reason = None
    if entry.symbol != expected_symbol:
        validation_status, invalid_reason = "rejected", "wrong_symbol"
    elif entry.venue != expected_venue:
        validation_status, invalid_reason = "rejected", "wrong_venue"
    elif entry.environment != expected_environment:
        validation_status, invalid_reason = "rejected", "wrong_environment"
    elif (
        entry.state_ref != expected_state_ref
        or entry.parity_status != expected_parity_status
        or entry.compatibility_assessment != expected_compatibility
    ):
        validation_status, invalid_reason = "state_mismatch", "exact_parity_state_mismatch"
    elif entry.created_ts_ms > observed_ts_ms:
        validation_status, invalid_reason = "invalid_semantics", "created_timestamp_is_in_future"
    elif observed_ts_ms > min(entry.expires_ts_ms, entry.review_required_by_ts_ms):
        validation_status, invalid_reason = "expired", "review_or_acknowledgement_expired"
    elif expected_parity_status in {"missing", "stale", "unavailable"}:
        validation_status, invalid_reason = "rejected", "parity_state_not_acknowledgeable"
    elif expected_parity_status == "risky_mismatch" and entry.ack_status not in {
        "acknowledged_requires_review", "rejected"
    }:
        validation_status, invalid_reason = "rejected", "risky_mismatch_cannot_be_normalized"
    elif expected_parity_status == "conservative_mismatch" and entry.ack_status not in {
        "acknowledged_conservative", "acknowledged_requires_review", "rejected"
    }:
        validation_status, invalid_reason = "rejected", "invalid_conservative_ack_status"

    file_ref = f"{ACK_REF}#sha256:{file_hash}"
    return OperatorParityAcknowledgementV0(
        **entry.model_dump(mode="python"),
        file_hash=file_hash,
        validation_status=validation_status,
        invalid_reason=invalid_reason,
        validated_provenance=OperatorAckProvenanceV0(
            acknowledgement_file_ref=file_ref,
            normalized_file_sha256=file_hash,
            loaded_ts_ms=observed_ts_ms,
            matching_state_ref=expected_state_ref,
            authored=entry.provenance,
        ),
    )


class FilterParityHistoryStore:
    """Small JSONL owner. It never writes YAML or exchange payloads."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.path = self.directory / HISTORY_FILENAME
        self.ack_path = self.directory / ACK_FILENAME
        self._lock = threading.RLock()

    def _rows(self) -> list[FilterParityHistoryRowV1]:
        try:
            if self.path.stat().st_size > MAX_HISTORY_BYTES:
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[FilterParityHistoryRowV1] = []
        for line in lines:
            try:
                rows.append(FilterParityHistoryRowV1.model_validate_json(line))
            except (ValidationError, ValueError):
                continue
        return rows

    def _ack(
        self,
        *,
        symbol: str,
        environment: str,
        state_ref: str,
        parity_status: str,
        compatibility_assessment: str,
        observed_ts_ms: int,
    ) -> AckLoadResult:
        try:
            if self.ack_path.stat().st_size > MAX_ACK_BYTES:
                return AckLoadResult(None, "invalid_file", "acknowledgement_file_oversized")
            doc = OperatorParityAcknowledgementsFileV0.model_validate_json(
                self.ack_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return AckLoadResult(None, "missing", "operator_acknowledgement_file_missing")
        except (OSError, ValidationError, ValueError):
            return AckLoadResult(None, "invalid_file", "operator_acknowledgement_file_invalid")
        file_hash = _normalized_document_hash(doc)
        provenance_ref = f"{ACK_REF}#sha256:{file_hash}"
        matches = [item for item in doc.acknowledgements if item.symbol == symbol]
        if not matches:
            return AckLoadResult(
                None, "missing", "symbol_acknowledgement_missing", provenance_ref, file_hash
            )
        entry = max(matches, key=lambda item: item.created_ts_ms)
        acknowledgement = validate_operator_acknowledgement(
            entry,
            expected_symbol=symbol,
            expected_venue="binance_usdm",
            expected_environment=environment,
            expected_state_ref=state_ref,
            expected_parity_status=parity_status,
            expected_compatibility=compatibility_assessment,
            observed_ts_ms=observed_ts_ms,
            file_hash=file_hash,
        )
        return AckLoadResult(
            acknowledgement,
            acknowledgement.validation_status,
            acknowledgement.invalid_reason,
            provenance_ref,
            file_hash,
        )

    def observe(
        self,
        *,
        symbol: str,
        runtime: Any | None,
        exchange: Any | None,
        environment: str,
        observed_ts_ms: int,
    ) -> FilterParityAcknowledgementV0:
        symbol = symbol.upper()
        configured_owner = _configured(runtime, symbol)
        configured_values = _values(configured_owner)
        exchange_values = _values(exchange)
        parity = compare_filter_parity(symbol, configured_owner, exchange)
        status, severity, compatibility, yaml_review, execution_block = _classification(parity)
        configured_ref = _ref(CONFIG_REF, configured_values)
        exchange_ref = _ref(CACHE_REF, exchange_values)
        state_ref = _ref(
            PARITY_REF,
            {"configured": configured_ref, "exchange": exchange_ref, "status": status},
        )

        with self._lock:
            rows = self._rows()
            symbol_rows = [row for row in rows if row.symbol == symbol and row.environment == environment]
            same_state = [row for row in symbol_rows if row.state_ref == state_ref]
            first_seen = min((row.timestamp_ms for row in same_state), default=observed_ts_ms)
            previous = symbol_rows[-1] if symbol_rows else None
            ack_result = (
                AckLoadResult(None, "not_required")
                if status == "match"
                else self._ack(
                    symbol=symbol,
                    environment=environment,
                    state_ref=state_ref,
                    parity_status=status,
                    compatibility_assessment=compatibility,
                    observed_ts_ms=observed_ts_ms,
                )
            )
            ack = ack_result.acknowledgement
            if status == "match":
                ack_status = "not_required"
            elif ack is not None and ack_result.validation_status == "valid":
                ack_status = ack.ack_status
            elif ack_result.validation_status in {"expired", "state_mismatch"}:
                ack_status = "expired"
            elif ack_result.validation_status == "rejected":
                ack_status = "rejected"
            else:
                ack_status = "unacknowledged"

            model = FilterParityAcknowledgementV0(
                symbol=symbol,
                venue="binance_usdm",
                environment=environment,
                parity_status=status,
                severity=severity,
                first_seen_ts_ms=first_seen,
                last_seen_ts_ms=observed_ts_ms,
                configured_values=configured_values,
                exchange_values=exchange_values,
                difference_summary=_differences(parity, configured_values),
                compatibility_assessment=compatibility,
                operator_ack_status=ack_status,
                operator_ack_ts_ms=ack.created_ts_ms if ack else None,
                operator_ack_note=ack.ack_reason if ack else None,
                operator_ack_id=ack.ack_id if ack else None,
                operator_id=ack.operator_id if ack else None,
                operator_display_name=ack.operator_display_name if ack else None,
                operator_ack_expires_ts_ms=ack.expires_ts_ms if ack else None,
                operator_review_required_by_ts_ms=(
                    ack.review_required_by_ts_ms if ack else None
                ),
                operator_ack_reason=ack.ack_reason if ack else None,
                operator_ack_validation_status=ack_result.validation_status,
                operator_ack_invalid_reason=ack_result.invalid_reason,
                operator_ack_provenance_ref=ack_result.provenance_ref,
                operator_ack_file_hash=ack_result.file_hash,
                requires_yaml_review=yaml_review,
                requires_execution_block_before_authority=execution_block,
                configured_metadata_ref=configured_ref,
                exchange_metadata_ref=exchange_ref,
                state_ref=state_ref,
                raw_ref=PARITY_REF,
                history_ref=HISTORY_REF,
            )
            transition: Transition
            if previous is None:
                transition = "new"
            elif previous.state_ref == state_ref:
                transition = "unchanged"
            elif status == "match":
                transition = "resolved"
            elif _rank(status) > _rank(previous.parity_status):
                transition = "worsened"
            else:
                transition = "improved"
            observation_id = hashlib.sha256(
                f"{observed_ts_ms}|{symbol}|{environment}|{state_ref}|{ack_status}|{ack_result.validation_status}".encode("utf-8")
            ).hexdigest()
            if not any(row.observation_id == observation_id for row in rows):
                row = FilterParityHistoryRowV1(
                    observation_id=observation_id,
                    timestamp_ms=observed_ts_ms,
                    symbol=symbol,
                    venue="binance_usdm",
                    environment=environment,
                    exchange_metadata_ref=exchange_ref,
                    configured_metadata_ref=configured_ref,
                    state_ref=state_ref,
                    parity_status=status,
                    severity=severity,
                    compatibility_assessment=compatibility,
                    transition=transition,
                    acknowledgement_state=ack_status,
                    acknowledgement_validation_status=ack_result.validation_status,
                    acknowledgement_id=ack.ack_id if ack else None,
                    operator_id=ack.operator_id if ack else None,
                    acknowledgement_provenance_ref=ack_result.provenance_ref,
                    requires_yaml_review=yaml_review,
                    requires_execution_block_before_authority=execution_block,
                    source_refs=[CONFIG_REF, CACHE_REF, PARITY_REF],
                )
                self.directory.mkdir(parents=True, exist_ok=True)
                payload = (row.model_dump_json() + "\n").encode("utf-8")
                descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
                try:
                    os.write(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            return model

    def observe_many(
        self,
        *,
        symbols: Iterable[str],
        runtime: Any | None,
        public_exchange_info: Any | None,
        observed_ts_ms: int,
    ) -> list[FilterParityAcknowledgementV0]:
        environment = str(getattr(public_exchange_info, "environment", "unavailable"))
        result = []
        for raw_symbol in symbols:
            symbol = str(raw_symbol).strip().upper()
            if not symbol:
                continue
            exchange = (
                public_exchange_info.get_symbol(symbol, observed_ts_ms)
                if public_exchange_info is not None else None
            )
            result.append(self.observe(
                symbol=symbol,
                runtime=runtime,
                exchange=exchange,
                environment=environment,
                observed_ts_ms=observed_ts_ms,
            ))
        return result


__all__ = [
    "ACK_FILENAME",
    "ACK_REF",
    "FilterParityHistoryRowV1",
    "FilterParityHistoryStore",
    "HISTORY_FILENAME",
    "HISTORY_REF",
    "OperatorAckAuthoredProvenanceV0",
    "OperatorAckProvenanceV0",
    "OperatorParityAcknowledgementV0",
    "OperatorParityAcknowledgementInputV0",
    "OperatorParityAcknowledgementsFileV0",
    "validate_operator_acknowledgement",
]
