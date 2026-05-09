#!/usr/bin/env python3
from __future__ import annotations
from tools.alpha_search.j6_s17_c1_shadow_outcomes import (
    BASE_DATASET_CSV,
    REPORTS_DIR,
    augment_dataset_with_outcomes,
    build_contract_audit,
    build_markdown_report,
    load_jsonl,
    read_csv_rows,
    revalidate_inputs,
    verdict_from_join_summary,
    write_csv,
    write_json,
    write_jsonl,
)

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Augment J6-S17-B dataset with J6-S17-C1 simulator outcomes.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--base-csv",
        type=Path,
        default=BASE_DATASET_CSV,
    )
    parser.add_argument(
        "--simulation-results",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_shadow_simulation_results.jsonl",
    )
    parser.add_argument(
        "--run-summary",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_simulator_run_summary.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_augmented_policy_outcome_dataset.csv",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_augmented_policy_outcome_dataset.jsonl",
    )
    parser.add_argument(
        "--tests-run",
        action="append",
        default=[],
        help="Record a validation command or check that was run for this artifact set.",
    )
    args = parser.parse_args()

    base_rows = read_csv_rows(args.base_csv)
    outcome_rows = load_jsonl(args.simulation_results)
    run_summary = __import__("json").loads(
        args.run_summary.read_text(encoding="utf-8"))
    contract_audit = build_contract_audit(args.root)
    augmented_rows, join_summary, classifier_summary, label_summary, dimension_summary = augment_dataset_with_outcomes(
        base_rows, outcome_rows)
    verdict = verdict_from_join_summary(join_summary, run_summary)

    write_csv(args.output_csv, augmented_rows)
    write_jsonl(args.output_jsonl, augmented_rows)
    write_json(REPORTS_DIR / "j6_s17_c1_outcome_join_summary.json", join_summary)
    write_json(
        REPORTS_DIR / "j6_s17_c1_outcome_availability_by_classifier.json", classifier_summary)
    write_json(REPORTS_DIR /
               "j6_s17_c1_outcome_availability_by_label.json", label_summary)
    write_json(
        REPORTS_DIR / "j6_s17_c1_outcome_availability_by_dimension.json", dimension_summary)

    report = build_markdown_report(
        contract_audit=contract_audit,
        run_summary=run_summary,
        join_summary=join_summary,
        classifier_summary=classifier_summary,
        label_summary=label_summary,
        dimension_summary=dimension_summary,
        verdict=verdict,
        files_changed=[
            "tools/alpha_search/j6_s17_c1_shadow_outcomes.py",
            "tools/alpha_search/j6_s17_c1_run_shadow_simulator.py",
            "tools/alpha_search/j6_s17_c1_augment_outcomes.py",
            "tests/domains/alpha_search/judge/test_j6_s17_c1_shadow_outcomes.py",
        ],
        tests_run=args.tests_run,
    )
    (REPORTS_DIR / "J6_S17_C1_SHADOW_SIMULATOR_OUTCOME_COLLECTION_REPORT.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
