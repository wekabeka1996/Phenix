#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.alpha_search.judge.central_brain.calibration import (  # noqa: E402
    JudgeCalibrationOutcomeRow,
    build_calibration_proposal,
)


def _coerce_scalar(value: str) -> object:
    if value in {"", "null", "None"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        if "." not in value:
            return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _expand_dotted(row: dict[str, object]) -> dict[str, object]:
    expanded: dict[str, object] = {}
    for key, value in row.items():
        parts = key.split(".")
        cursor = expanded
        for part in parts[:-1]:
            nested = cursor.setdefault(part, {})
            if not isinstance(nested, dict):
                raise ValueError(f"conflicting dotted key: {key}")
            cursor = nested
        cursor[parts[-1]] = value
    return expanded


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: row must be a JSON object")
            rows.append(payload)
    return rows


def _load_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            _expand_dotted({key: _coerce_scalar(value or "") for key, value in row.items()})
            for row in reader
        ]


def load_rows(paths: Iterable[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"input path does not exist: {path}")
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            rows.extend(_load_jsonl(path))
        elif suffix == ".csv":
            rows.extend(_load_csv(path))
        else:
            raise ValueError(f"unsupported input extension for {path}; expected .jsonl or .csv")
    return rows


def render_markdown_summary(proposal: dict[str, object]) -> str:
    summary = proposal["dataset_summary"]
    gates = proposal["gates"]
    bands = proposal["confidence_bands"]["candidates"]
    lines = [
        "# Judge Confidence Calibration Proposal",
        "",
        f"- proposal_id: `{proposal['proposal_id']}`",
        f"- total_rows: `{summary['total_rows']}`",
        f"- usable_rows: `{summary['usable_rows']}`",
        f"- promotion_allowed: `{gates['promotion_allowed']}`",
        f"- auto_apply: `{proposal['recommended_policy']['auto_apply']}`",
        "",
        "| band | action | rows | status | expectancy |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for band in bands:
        lines.append(
            "| {band_id} | {action} | {rows} | {status} | {expectancy} |".format(
                band_id=band["band_id"],
                action=band["action"],
                rows=band["rows"],
                status=band["status"],
                expectancy=band["expectancy_net_usd"],
            )
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build proposal-only Judge confidence calibration artifact.")
    parser.add_argument("--input", action="append", required=True, help="Input JSONL/CSV path; repeatable.")
    parser.add_argument("--output-json", required=True, help="Output proposal JSON path.")
    parser.add_argument("--output-md", help="Optional output Markdown summary path.")
    parser.add_argument("--band-step", type=float, required=True)
    parser.add_argument("--cadence-days", type=int, required=True)
    parser.add_argument("--min-rows", type=int, required=True)
    parser.add_argument("--min-symbols", type=int, required=True)
    parser.add_argument("--holdout-ratio", type=float, default=0.0)
    parser.add_argument("--gross-pnl-fallback", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        input_paths = [Path(raw) for raw in args.input]
        rows = load_rows(input_paths)
        parsed_rows = [
            JudgeCalibrationOutcomeRow.model_validate(row)
            for row in rows
        ]
        created_ts_ms = max((row.decision_ts_ms for row in parsed_rows), default=0)
        proposal = build_calibration_proposal(
            parsed_rows,
            created_ts_ms=created_ts_ms,
            band_step=args.band_step,
            cadence_days=args.cadence_days,
            min_rows=args.min_rows,
            min_symbols=args.min_symbols,
            holdout_ratio=args.holdout_ratio,
            gross_pnl_fallback=args.gross_pnl_fallback,
            input_paths=[str(path) for path in input_paths],
            report_path=args.output_md,
        )
        payload = proposal.model_dump(mode="json", by_alias=True)
        output_json = Path(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.output_md:
            output_md = Path(args.output_md)
            output_md.parent.mkdir(parents=True, exist_ok=True)
            output_md.write_text(render_markdown_summary(payload), encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"rolling confidence calibration failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
