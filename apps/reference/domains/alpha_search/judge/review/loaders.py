"""Loaders for offline judge review surfaces."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from apps.reference.domains.alpha_search.judge.chamber.chamber_aggregator import (
    ChamberAggregate,
)
from apps.reference.domains.alpha_search.judge.contracts import (
    JudgeEvidenceEnvelope,
    JudgeVerdict,
)
from apps.reference.domains.alpha_search.judge.simulator.calibration_dataset_writer import (
    CalibrationRecordModel,
)

LOG = logging.getLogger(__name__)

_SIMULATOR_SCHEMAS_DIR = (
    Path(__file__).resolve().parents[1] / "simulator" / "schemas"
)
_SUMMARY_SCHEMA_PATH = _SIMULATOR_SCHEMAS_DIR / "summary_report_v1.json"


@dataclass(frozen=True)
class LoadedVerdict:
    verdict: JudgeVerdict
    source_file: str


@dataclass(frozen=True)
class LoadedChamber:
    chamber: ChamberAggregate
    source_file: str


@dataclass(frozen=True)
class LoadedEnvelope:
    envelope: JudgeEvidenceEnvelope
    source_file: str


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


def _iter_jsonl_files(
    judge_logs_path: str | Path,
    prefix: str,
    *,
    required: bool,
) -> list[Path]:
    path = Path(judge_logs_path)
    if not path.exists():
        raise FileNotFoundError(f"judge logs path does not exist: {path}")

    if path.is_file():
        if path.name.startswith(f"{prefix}_"):
            return [path]
        if required:
            raise FileNotFoundError(
                f"judge logs file does not match required prefix '{prefix}_': {path}"
            )
        return []

    files = sorted(
        candidate
        for candidate in path.glob(f"{prefix}_*.jsonl")
        if candidate.is_file()
    )
    if required and not files:
        raise FileNotFoundError(
            f"No {prefix}_*.jsonl files found under {path}"
        )
    return files


def _load_jsonl_payloads(files: list[Path]) -> list[tuple[Path, int, dict[str, object]]]:
    payloads: list[tuple[Path, int, dict[str, object]]] = []
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    LOG.warning(
                        "Skipping malformed JSONL line %s:%s: %s",
                        file_path,
                        line_number,
                        exc,
                    )
                    continue
                if not isinstance(payload, dict):
                    LOG.warning(
                        "Skipping non-object JSONL payload %s:%s",
                        file_path,
                        line_number,
                    )
                    continue
                payloads.append((file_path, line_number, payload))
    return payloads


def load_all_verdicts(judge_logs_path: str | Path) -> list[LoadedVerdict]:
    loaded: list[LoadedVerdict] = []
    for file_path, line_number, payload in _load_jsonl_payloads(
        _iter_jsonl_files(judge_logs_path, "verdict", required=True)
    ):
        try:
            verdict = JudgeVerdict.model_validate(payload)
        except Exception as exc:
            LOG.warning(
                "Skipping invalid verdict payload %s:%s: %s",
                file_path,
                line_number,
                exc,
            )
            continue
        loaded.append(LoadedVerdict(
            verdict=verdict, source_file=file_path.name))

    if not loaded:
        raise ValueError("No valid judge verdict records were loaded")
    return loaded


def load_chambers(judge_logs_path: str | Path) -> list[LoadedChamber]:
    loaded: list[LoadedChamber] = []
    for file_path, line_number, payload in _load_jsonl_payloads(
        _iter_jsonl_files(judge_logs_path, "chamber", required=False)
    ):
        try:
            chamber = ChamberAggregate.model_validate(payload)
        except Exception as exc:
            LOG.warning(
                "Skipping invalid chamber payload %s:%s: %s",
                file_path,
                line_number,
                exc,
            )
            continue
        loaded.append(LoadedChamber(
            chamber=chamber, source_file=file_path.name))
    return loaded


def load_envelopes(judge_logs_path: str | Path) -> list[LoadedEnvelope]:
    loaded: list[LoadedEnvelope] = []
    for file_path, line_number, payload in _load_jsonl_payloads(
        _iter_jsonl_files(judge_logs_path, "envelope", required=False)
    ):
        try:
            envelope = JudgeEvidenceEnvelope.model_validate(payload)
        except Exception as exc:
            LOG.warning(
                "Skipping invalid envelope payload %s:%s: %s",
                file_path,
                line_number,
                exc,
            )
            continue
        loaded.append(LoadedEnvelope(
            envelope=envelope, source_file=file_path.name))
    return loaded


def load_existing_calibration_dataset(
    dataset_path: str | Path,
) -> list[dict[str, object]]:
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Calibration dataset not found: {path}")

    records: list[dict[str, object]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Calibration dataset line {line_number} is not valid JSON: {exc}"
                ) from exc
            record = CalibrationRecordModel.model_validate(payload)
            records.append(record.model_dump(mode="json"))
    return records


def _load_summary_schema() -> dict[str, object]:
    with open(_SUMMARY_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft7Validator.check_schema(schema)
    return schema


def load_existing_summary_report(summary_path: str | Path) -> dict[str, object]:
    path = Path(summary_path)
    if not path.is_file():
        raise FileNotFoundError(f"Summary report not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        try:
            payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Summary report is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Summary report must be a JSON object")

    validator = Draft7Validator(_load_summary_schema())
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        formatted = "; ".join(
            _format_jsonschema_error(error) for error in errors[:5]
        )
        raise ValueError(
            f"Summary report failed schema validation: {formatted}"
        )

    return dict(payload)
