#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.reference.domains.alpha_search.judge.central_brain.calibration import (  # noqa: E402
    build_calibration_proposal,
)
from apps.reference.domains.alpha_search.judge.central_brain.shadow_calibration import (  # noqa: E402
    JudgeShadowCalibrationRowV1,
    to_phase8_calibration_row,
)


def load_shadow_rows(path: Path) -> list[JudgeShadowCalibrationRowV1]:
    rows: list[JudgeShadowCalibrationRowV1] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            rows.append(JudgeShadowCalibrationRowV1.model_validate(payload))
    return rows


def render_summary(proposal: dict, shadow_rows: list[JudgeShadowCalibrationRowV1]) -> str:
    statuses = Counter(band["status"] for band in proposal["confidence_bands"]["candidates"])
    dataset = proposal["dataset_summary"]
    policy = proposal["recommended_policy"]
    lines = [
        "# Testnet Shadow Judge Calibration Experiment",
        "",
        f"- shadow_rows: `{len(shadow_rows)}`",
        f"- total_rows: `{dataset['total_rows']}`",
        f"- usable_rows: `{dataset['usable_rows']}`",
        f"- unresolved_rows: `{dataset['unresolved_rows']}`",
        f"- symbols: `{', '.join(dataset['symbols'])}`",
        f"- regimes: `{', '.join(dataset['regimes'])}`",
        f"- sides: `{', '.join(dataset['sides'])}`",
        f"- candidate_bands: `{statuses.get('CANDIDATE', 0)}`",
        f"- toxic_bands: `{statuses.get('TOXIC', 0)}`",
        f"- low_power_bands: `{statuses.get('LOW_POWER', 0)}`",
        f"- promotion_allowed: `{proposal['gates']['promotion_allowed']}`",
        f"- auto_apply: `{policy['auto_apply']}`",
        f"- human_review_required: `{policy['human_review_required']}`",
        "",
        "| band | action | rows | status | expectancy |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for band in proposal["confidence_bands"]["candidates"]:
        lines.append(
            f"| {band['band_id']} | {band['action']} | {band['rows']} | "
            f"{band['status']} | {band['expectancy_net_usd']} |"
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 9 testnet shadow calibration experiment.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-dir", required=True)
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
        input_path = Path(args.input_jsonl)
        output_dir = Path(args.output_dir)
        shadow_rows = load_shadow_rows(input_path)
        calibration_rows = [to_phase8_calibration_row(row) for row in shadow_rows]
        created_ts_ms = max((row.decision_ts_ms for row in shadow_rows), default=0)
        proposal = build_calibration_proposal(
            calibration_rows,
            created_ts_ms=created_ts_ms,
            band_step=args.band_step,
            cadence_days=args.cadence_days,
            min_rows=args.min_rows,
            min_symbols=args.min_symbols,
            holdout_ratio=args.holdout_ratio,
            gross_pnl_fallback=args.gross_pnl_fallback,
            input_paths=[input_path.as_posix()],
            report_path=(output_dir / "summary.md").as_posix(),
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = proposal.model_dump(mode="json", by_alias=True)
        (output_dir / "proposal.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / "summary.md").write_text(
            render_summary(payload, shadow_rows),
            encoding="utf-8",
        )
        diagnostics = {
            "rows": len(shadow_rows),
            "join_quality": Counter(row.diagnostics.join_quality for row in shadow_rows),
            "outcome_status": Counter(row.outcome.outcome_status for row in shadow_rows),
        }
        (output_dir / "diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        print(f"shadow calibration experiment failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
