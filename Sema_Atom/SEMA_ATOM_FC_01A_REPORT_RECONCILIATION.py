from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import SEMA_ATOM_FORWARD_COLLECTOR as fc


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SLICE_PATH = REPO_ROOT / "aurora_forward_slice_2026-05-08_2026-05-09.saf.jsonl"
DEFAULT_REPORT_PATH = REPO_ROOT / "SEMA_ATOM_FORWARD_COLLECTION_2026-05-08_2026-05-09_REPORT.md"
DEFAULT_INDEX_PATH = REPO_ROOT / "SEMA_ATOM_FORWARD_COLLECTION_INDEX.json"
DEFAULT_ORDER_LOG_PATH = REPO_ROOT / "logs" / "order_log_v1.jsonl"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "SEMA_ATOM_FC_01A_REPORT_RECONCILIATION.md"


def _parse_metric(report_text: str, label: str) -> str | None:
    prefix = f"- {label}: "
    for line in report_text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def _load_atoms(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _iso(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Artifact-driven FC_01A reconciliation.")
    parser.add_argument("--from", dest="from_day", default="2026-05-08")
    parser.add_argument("--to", dest="to_day", default="2026-05-09")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from_day = fc._parse_day(args.from_day)
    to_day = fc._parse_day(args.to_day)
    start_ts_ms, _ = fc._date_to_range(from_day)
    _, end_ts_ms = fc._date_to_range(to_day)

    atoms = _load_atoms(DEFAULT_SLICE_PATH)
    report_text = DEFAULT_REPORT_PATH.read_text(encoding="utf-8")
    index_payload = json.loads(DEFAULT_INDEX_PATH.read_text(encoding="utf-8"))
    order_rows, _, _ = fc._parse_jsonl(DEFAULT_ORDER_LOG_PATH)
    window_rows, _ = fc._window_rows(order_rows, start_ts_ms, end_ts_ms)

    accepted_atoms = [atom for atom in atoms if atom.get("atom_kind") == "ACCEPTED"]
    rejected_atoms = [atom for atom in atoms if atom.get("atom_kind") == "REJECTED"]
    diagnostics_only_atoms = [
        atom
        for atom in atoms
        if atom.get("atom_kind") not in {"ACCEPTED", "REJECTED"}
        or atom.get("trainable") is False
    ]
    atoms_created = len(atoms)
    accepted_atoms_created = len(accepted_atoms)
    rejected_atoms_created = len(rejected_atoms)
    diagnostics_only_atoms_created = len(diagnostics_only_atoms)
    atoms_reconciled = atoms_created == (
        accepted_atoms_created + rejected_atoms_created + diagnostics_only_atoms_created
    )

    accepted_close_rows = [row for row in window_rows if row.get("event_type") == "POSITION_CLOSED"]
    accepted_unresolved_rows = [
        row
        for row in accepted_close_rows
        if fc._text(row.get("pnl_status")) == "unresolved" or fc._safe_float(row.get("realized_pnl_net")) is None
    ]
    accepted_trainable_defect = False
    accepted_defect_atom: dict[str, Any] | None = None
    inspected_row: dict[str, Any] | None = accepted_unresolved_rows[0] if accepted_unresolved_rows else None
    if inspected_row is not None:
        inspected_lifecycle = fc._text(inspected_row.get("lifecycle_id"))
        inspected_close_ts = fc._safe_int(inspected_row.get("timestamp"))
        for atom in accepted_atoms:
            raw_contract = atom.get("raw_contract", {})
            if (
                fc._text(raw_contract.get("lifecycle_id")) == inspected_lifecycle
                and fc._safe_int(raw_contract.get("close_ts_ms")) == inspected_close_ts
            ):
                accepted_trainable_defect = True
                accepted_defect_atom = atom
                break

    missing_t30 = 0
    missing_t60 = 0
    cross_day_t30 = 0
    cross_day_t60 = 0
    max_future_ts: int | None = None
    latest_rejected_event_ts: int | None = None
    for atom in rejected_atoms:
        raw_contract = atom.get("raw_contract", {})
        evt = fc._safe_int(raw_contract.get("event_ts_ms"))
        if evt is not None and (latest_rejected_event_ts is None or evt > latest_rejected_event_ts):
            latest_rejected_event_ts = evt
        horizons = atom.get("outcome_snapshot", {}).get("post_move_horizons", {})
        if not isinstance(horizons, dict):
            continue
        for label in ("T+30m", "T+60m"):
            entry = horizons.get(label, {})
            future_ts = fc._safe_int(entry.get("future_ts_ms")) if isinstance(entry, dict) else None
            if label == "T+30m" and future_ts is None:
                missing_t30 += 1
            if label == "T+60m" and future_ts is None:
                missing_t60 += 1
            if future_ts is not None:
                if max_future_ts is None or future_ts > max_future_ts:
                    max_future_ts = future_ts
                future_day = datetime.fromtimestamp(future_ts / 1000.0, tz=timezone.utc).date().isoformat()
                if label == "T+30m" and future_day == "2026-05-09":
                    cross_day_t30 += 1
                if label == "T+60m" and future_day == "2026-05-09":
                    cross_day_t60 += 1

    accepted_close_events_found = _parse_metric(report_text, "accepted close events found") or "0"
    accepted_contracts_completed = _parse_metric(report_text, "accepted contracts completed") or "0"
    mfe_mae_computed = _parse_metric(report_text, "MFE/MAE computed") or "0"
    recorder_dates_missing = _parse_metric(report_text, "recorder_dates_missing") or "[]"
    window_end_metric = _parse_metric(report_text, "window_end_ts_ms_exclusive") or str(end_ts_ms)
    expected_window_end_ts_ms = end_ts_ms
    time_window_ambiguous = window_end_metric != str(expected_window_end_ts_ms)

    if accepted_trainable_defect:
        verdict = "FC_01A_BLOCKED_ACCEPTED_INCOMPLETE_TRAINABLE_ATOM"
    elif time_window_ambiguous:
        verdict = "FC_01A_BLOCKED_TIME_WINDOW_AMBIGUITY"
    elif recorder_dates_missing != "[]":
        verdict = "FC_01A_RECONCILED_WITH_RESIDUALS"
    else:
        verdict = "FC_01A_RECONCILED_NO_BLOCKER"

    lines = [
        "# SEMA_ATOM_FC_01A_REPORT_RECONCILIATION",
        "",
        "## Verdict",
        verdict,
        "",
        "## Scope",
        "- Artifact-only reconciliation of the existing FC_01 outputs after the accepted incomplete guard patch.",
        "- No new data collection, no runtime modification, and no baseline SAF mutation.",
        "",
        "## Inputs Read",
        f"- {DEFAULT_SLICE_PATH.name}",
        f"- {DEFAULT_REPORT_PATH.name}",
        f"- {DEFAULT_INDEX_PATH.name}",
        f"- {DEFAULT_ORDER_LOG_PATH}",
        "",
        "## Atom Reconciliation",
        f"- atoms_created: {atoms_created}",
        f"- accepted_atoms_created: {accepted_atoms_created}",
        f"- rejected_atoms_created: {rejected_atoms_created}",
        f"- diagnostics_only_atoms_created: {diagnostics_only_atoms_created}",
        f"- atoms_created_reconciliation_ok: {atoms_reconciled}",
        "",
        "## Accepted Incomplete Inspection",
        f"- accepted close events found: {accepted_close_events_found}",
        f"- accepted contracts completed: {accepted_contracts_completed}",
        f"- MFE/MAE computed: {mfe_mae_computed}",
    ]
    if inspected_row is not None:
        lines.extend(
            [
                f"- inspected_lifecycle_id: {fc._text(inspected_row.get('lifecycle_id'))}",
                f"- inspected_pnl_status: {fc._text(inspected_row.get('pnl_status'))}",
                f"- inspected_realized_pnl_net: {json.dumps(fc._safe_float(inspected_row.get('realized_pnl_net')))}",
                f"- inspected_fees: {json.dumps(fc._safe_float(inspected_row.get('fees')))}",
                f"- inspected_close_price: {json.dumps(fc._extract_first_float(inspected_row, (('metadata', 'close_price'), ('close_price',))))}",
            ]
        )
    if accepted_trainable_defect:
        lines.append("- ACCEPTED_INCOMPLETE_TRAINABLE_ATOM_DEFECT: TRUE")
        lines.append(f"- leaked_atom_id: {accepted_defect_atom.get('atom_id') if accepted_defect_atom else 'unknown'}")
    else:
        lines.append("- ACCEPTED_INCOMPLETE_TRAINABLE_ATOM_DEFECT: FALSE")
        lines.append("- unresolved accepted close did not produce a trainable ACCEPTED atom.")
        lines.append("- handling mode: incomplete bucket / excluded from trainable SAF corpus.")

    lines.extend(
        [
            "",
            "## Metric Semantics Clarification",
            "- `accepted close events found = 1` counts the raw `POSITION_CLOSED` row in the window.",
            "- `accepted contracts completed = 0` because the row was incomplete on terminal economics and therefore not trainable.",
            "- `MFE/MAE computed = 1` is still possible because replay only requires symbol, side, entry_price, entry_ts_ms, and close_ts_ms.",
            "- After the patch, replay evidence can still exist for forensic reporting while the unresolved accepted close stays outside the trainable SAF corpus.",
            "",
            "## Time Window Semantics",
            f"- `--from` is inclusive at {from_day.isoformat()}T00:00:00Z.",
            f"- `--to` is inclusive by day, implemented as exclusive next-midnight bound.",
            f"- window_start_ts_ms: {start_ts_ms} ({_iso(start_ts_ms)})",
            f"- window_end_ts_ms_exclusive: {expected_window_end_ts_ms} ({_iso(expected_window_end_ts_ms)})",
            f"- time_window_ambiguity_detected: {time_window_ambiguous}",
            "- The end timestamp corresponds to 2026-05-10T00:00:00Z because the collector includes the full UTC day 2026-05-09 and then uses the next midnight as the exclusive boundary.",
            "",
            "## Recorder Coverage Impact",
            f"- recorder_dates_missing: {recorder_dates_missing}",
            f"- latest_rejected_event_ts: {latest_rejected_event_ts} ({_iso(latest_rejected_event_ts)})",
            f"- latest_replay_future_ts: {max_future_ts} ({_iso(max_future_ts)})",
            f"- missing_t30_horizons: {missing_t30}",
            f"- missing_t60_horizons: {missing_t60}",
            f"- cross_day_t30_horizons_into_2026_05_09: {cross_day_t30}",
            f"- cross_day_t60_horizons_into_2026_05_09: {cross_day_t60}",
        ]
    )
    if missing_t30 == 0 and missing_t60 == 0 and cross_day_t30 == 0 and cross_day_t60 == 0:
        lines.append("- The missing `2026-05-09` recorder directory did not affect any actual rejected T+30/T+60 evaluation in this slice.")
        lines.append("- No late 2026-05-08 replay horizon was truncated by the missing next-day recorder folder.")
    else:
        lines.append("- Recorder coverage did affect at least one rejected replay horizon.")
    lines.extend(
        [
            "",
            "## Index Reconciliation",
            f"- index_atoms_created: {index_payload['slices'][0].get('atoms_created') if index_payload.get('slices') else None}",
            f"- index_accepted_atoms_created: {index_payload['slices'][0].get('accepted_atoms_created') if index_payload.get('slices') else None}",
            f"- index_rejected_atoms_created: {index_payload['slices'][0].get('rejected_atoms_created') if index_payload.get('slices') else None}",
            f"- index_diagnostics_only_atoms_created: {index_payload['slices'][0].get('diagnostics_only_atoms_created') if index_payload.get('slices') else None}",
            f"- index_incomplete_accepted_missing_realized_pnl_net: {index_payload['slices'][0].get('incomplete_accepted_missing_realized_pnl_net') if index_payload.get('slices') else None}",
            "",
            "## Final Assessment",
        ]
    )
    if verdict == "FC_01A_BLOCKED_ACCEPTED_INCOMPLETE_TRAINABLE_ATOM":
        lines.append("- The unresolved accepted close still leaked into trainable SAF, so the blocker remains open.")
    elif verdict == "FC_01A_BLOCKED_TIME_WINDOW_AMBIGUITY":
        lines.append("- The collector report time-window contract was inconsistent with the implemented exclusive bound.")
    else:
        lines.append("- The accepted incomplete guard is now effective: unresolved accepted economics no longer enter the trainable SAF corpus.")
        if verdict == "FC_01A_RECONCILED_WITH_RESIDUALS":
            lines.append("- Residuals remain from the requested window extending beyond recorder day coverage, but they did not create the original accepted-atom blocker.")
        else:
            lines.append("- No blocker remains on the reconciled artifact set.")

    DEFAULT_OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
