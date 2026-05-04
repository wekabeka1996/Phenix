"""Calibration dataset shaping and JSONL writing for Phase 5 Package 5D."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence

from jsonschema import Draft7Validator
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .disagreement_analyzer import determine_optimal_action

if TYPE_CHECKING:
    from .config_models import SimulatorConfig
    from .simulator_engine import CorrelatedVerdictOutcome

_SCHEMA_PATH = Path(__file__).resolve().parent / \
    "schemas" / "calibration_dataset_v1.json"

CalibrationCohort = Literal[
    "CORRECT_ENTRY",
    "INCORRECT_ENTRY",
    "CORRECT_ABSTAIN",
    "MISSED_OPPORTUNITY",
    "INCONCLUSIVE",
]


def _classify_cohort(
    *,
    entry_verdict: str,
    optimal_action: str,
) -> CalibrationCohort:
    if entry_verdict in {"UNKNOWN", "SUPPRESS"}:
        return "INCONCLUSIVE"
    if entry_verdict == "NO_ENTRY":
        if optimal_action == "NO_ENTRY":
            return "CORRECT_ABSTAIN"
        return "MISSED_OPPORTUNITY"
    if entry_verdict in {"OPEN_LONG", "OPEN_SHORT"}:
        if entry_verdict == optimal_action:
            return "CORRECT_ENTRY"
        return "INCORRECT_ENTRY"
    raise ValueError(f"Unsupported entry_verdict: {entry_verdict}")


class CalibrationRecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    tf_sec: int = Field(..., gt=0)
    bar_close_ts: int = Field(..., gt=0)
    verdict_id: str = Field(..., min_length=1)
    entry_verdict: Literal[
        "OPEN_LONG",
        "OPEN_SHORT",
        "NO_ENTRY",
        "UNKNOWN",
        "SUPPRESS",
    ]
    confidence: float
    dissent_noted: bool
    matched_trade: bool
    raw_return: float | None = None
    fee_cost: float | None = None
    slippage_cost: float | None = None
    net_return: float | None = None
    optimal_action: Literal["OPEN_LONG", "OPEN_SHORT", "NO_ENTRY"]
    has_disagreement: bool
    cohort: CalibrationCohort
    schema_version: Literal["1"] = "1"

    @field_validator("strategy_id", "symbol", "verdict_id")
    @classmethod
    def reject_blank_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity fields must not be blank")
        return value

    @model_validator(mode="after")
    def validate_record_consistency(self) -> "CalibrationRecordModel":
        if self.entry_verdict in {"NO_ENTRY", "UNKNOWN", "SUPPRESS"}:
            if any(
                value is not None
                for value in (
                    self.raw_return,
                    self.fee_cost,
                    self.slippage_cost,
                    self.net_return,
                )
            ):
                raise ValueError(
                    "non-actionable verdicts must not carry trade economics"
                )

        expected_has_disagreement = False
        if self.entry_verdict in {"OPEN_LONG", "OPEN_SHORT", "NO_ENTRY"}:
            expected_has_disagreement = self.entry_verdict != self.optimal_action
        if self.has_disagreement is not expected_has_disagreement:
            raise ValueError(
                "has_disagreement must match verdict-vs-optimal comparison")

        expected_cohort = _classify_cohort(
            entry_verdict=self.entry_verdict,
            optimal_action=self.optimal_action,
        )
        if self.cohort != expected_cohort:
            raise ValueError("cohort does not match deterministic cohort rule")

        return self


@lru_cache(maxsize=1)
def _load_calibration_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft7Validator.check_schema(schema)
    return schema


def _format_jsonschema_error(error: Any) -> str:
    if error.path:
        segments = []
        for segment in error.path:
            if isinstance(segment, int):
                segments.append(f"[{segment}]")
            else:
                segments.append(f".{segment}")
        location = "$" + "".join(segments)
    else:
        location = "$"
    return f"{location}: {error.message}"


def _validate_and_serialize_record(
    record: Mapping[str, object],
    index: int,
) -> dict[str, object]:
    parsed = CalibrationRecordModel.model_validate(record)
    serialized = parsed.model_dump(mode="json")

    validator = Draft7Validator(_load_calibration_schema())
    errors = sorted(
        validator.iter_errors(serialized),
        key=lambda error: list(error.path),
    )
    if errors:
        formatted_errors = "; ".join(
            _format_jsonschema_error(error) for error in errors[:5]
        )
        raise ValueError(
            f"Calibration record at index {index} failed schema validation: {formatted_errors}"
        )

    return serialized


def _build_disagreement_index(
    disagreements: Sequence[Mapping[str, object]],
) -> set[str]:
    verdict_ids: set[str] = set()
    for disagreement in disagreements:
        verdict_id = disagreement.get("verdict_id")
        if not isinstance(verdict_id, str) or not verdict_id.strip():
            raise ValueError(
                "disagreement records must carry a non-empty verdict_id")
        verdict_ids.add(verdict_id)
    return verdict_ids


def build_calibration_records(
    *,
    correlations: Sequence[CorrelatedVerdictOutcome],
    disagreements: Sequence[Mapping[str, object]],
    config: SimulatorConfig,
) -> list[dict[str, object]]:
    """Build deterministic calibration records from existing simulator outputs."""

    disagreement_verdict_ids = _build_disagreement_index(disagreements)
    records: list[dict[str, object]] = []

    for correlation in correlations:
        outcome = correlation.outcome
        if outcome is None:
            continue

        optimal_action = determine_optimal_action(
            matched_trade=outcome.matched_trade,
            entry_price=outcome.entry_price,
            exit_price=outcome.exit_price,
            fee_per_cycle_bps=config.fee_per_cycle_bps,
            slippage_pct=config.slippage_pct,
        )
        record = CalibrationRecordModel(
            strategy_id=correlation.verdict.correlation_key.strategy_id,
            symbol=correlation.verdict.correlation_key.symbol,
            tf_sec=correlation.verdict.correlation_key.tf_sec,
            bar_close_ts=correlation.verdict.correlation_key.bar_close_ts,
            verdict_id=correlation.verdict.verdict_id,
            entry_verdict=correlation.verdict.entry_verdict,
            confidence=correlation.verdict.confidence,
            dissent_noted=correlation.verdict.dissent_noted,
            matched_trade=outcome.matched_trade,
            raw_return=correlation.raw_return,
            fee_cost=correlation.fee_cost,
            slippage_cost=correlation.slippage_cost,
            net_return=correlation.net_return,
            optimal_action=optimal_action,
            has_disagreement=correlation.verdict.verdict_id in disagreement_verdict_ids,
            cohort=_classify_cohort(
                entry_verdict=correlation.verdict.entry_verdict,
                optimal_action=optimal_action,
            ),
        )
        records.append(record.model_dump(mode="json"))

    return records


def write_calibration_dataset(
    *,
    records: Sequence[Mapping[str, object]],
    output_path: str | Path,
) -> Path:
    """Write validated calibration records to deterministic JSONL.

    Policy: the writer creates missing parent directories, preserves caller
    order, and fails closed if the target file already exists.
    """

    if isinstance(records, (str, bytes)):
        raise TypeError(
            "records must be a sequence of mappings, not a string-like value")

    path = Path(output_path)
    if path.exists():
        if path.is_dir():
            raise IsADirectoryError(
                f"calibration dataset path is a directory: {path}")
        raise FileExistsError(
            f"calibration dataset path already exists: {path}")
    if path.suffix.lower() != ".jsonl":
        raise ValueError(
            "calibration dataset path must use a .jsonl extension")

    validated_records = [
        _validate_and_serialize_record(record, index)
        for index, record in enumerate(records)
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for record in validated_records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

    return path
