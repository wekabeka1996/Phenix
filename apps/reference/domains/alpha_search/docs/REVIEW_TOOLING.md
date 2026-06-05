# Alpha Search Review Tooling

## 1. Scope

The review tooling under apps/reference/domains/alpha_search/judge/review/ is the minimum offline surface that makes the Phase 6 review SSOT operational.

It consumes real repo-supported evidence inputs, writes bounded review artifacts, and makes missing or partial evidence explicit.

It must not emit a promotion verdict automatically.

## 2. Config Authority

The entry config is config/judge_review.yaml.

That config is intentionally narrow:

- it points to config/judge_simulator.yaml for verdict, chamber, envelope, and outcome input authority
- it sets only review-specific output_dir, segment_dimensions, and confidence_bucket_edges
- it does not widen JudgeCortexConfig or alpha_search live runtime config authority

## 3. Inputs

Resolved through config/judge_simulator.yaml:

- verdict_*.jsonl under the configured judge_logs_path
- optional chamber_*.jsonl under the configured judge_logs_path
- optional envelope_*.jsonl under the configured judge_logs_path
- outcome_data_path JSON input for the existing exact-key simulator correlation path
- optional existing Phase 5 calibration_dataset_path artifact
- optional existing Phase 5 summary_report_path artifact

Required evidence is fail-closed at config or path validation time. Optional artifacts stay optional, but missing or inconsistent files are carried into the review bundle as explicit insufficiency markers.

## 4. Outputs

The tooling writes:

- review_bundle.json
- review_summary.md
- comparison_by_segment.csv
- suppression_unknown_by_segment.csv
- disagreement_buckets.csv
- calibration_slices.csv
- surface_support.csv

These outputs are operator-readable and machine-readable only. They are not promotion commands.

## 5. What the Bundle Summarizes

The review bundle summarizes:

- baseline availability for incumbent-only, chamber-only, final-judge, and no-judge abstain baselines
- segmented chamber-only vs final-judge comparisons where chamber artifacts exist
- verdict-class and chamber-class counts
- UNKNOWN and SUPPRESS distribution plus abstain opportunity cost accounting
- disagreement buckets and calibration slices derived from the existing simulator cost model
- evidence-class support for structural, behavioral, replay, economic, comparative, and operator-observability review questions
- explicit insufficiency flags when current repo surfaces do not support a stronger conclusion

## 6. Boundaries

The review tooling is deliberately bounded.

- It is offline-only.
- It does not import from live decision or execution ownership lines.
- It does not widen judge runtime mode admission beyond off and shadow.
- It does not infer an incumbent baseline if the repo does not already produce one.
- It may summarize evidence, but final promotion-ladder choice remains a human review decision.

## 7. Typical Run

Use the CLI entrypoint:

python -m apps.reference.domains.alpha_search.judge.review.cli --config config/judge_review.yaml

Run this after the relevant verdict and outcome artifacts exist. If you want the bundle to compare against already materialized Phase 5 calibration or summary artifacts, generate those first through the simulator path.
