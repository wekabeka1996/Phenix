# SEMA_ATOM_POC_03_JSON_SIDECAR_CONTRACT_CLEANUP_REPORT

## Verdict
JSON_SIDECAR_CONTRACT_ACCEPTED_WITH_RESIDUALS

## Scope
- Narrow contract-hardening package for the offline SemaAtom POC_03 -> POC_03B evidence path only.
- No live trading logic changes.
- No YAML policy changes.
- No gate threshold changes.
- No runtime authority, advisory, shadow listener, drift/decay, or economics V2 implementation.

## Files Changed
- Sema_Atom/SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json (created 2026-05-18)
- tests/test_sema_atom_poc_03b_stability_filter_full.py (added test_run_fails_closed_on_schema_id_mismatch)

## Discovery / Duplication Check
- Existing writer located in Sema_Atom/SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION.py.
- Existing stability consumer located in Sema_Atom/SEMA_ATOM_POC_03B_STABILITY_FILTER_FULL.py.
- Existing downstream manifest consumer located in Sema_Atom/SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION.py.
- Existing focused tests located in tests/test_sema_atom_poc_03_memory_verdict_validation.py, tests/test_sema_atom_poc_03b_stability_filter_full.py, and tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py.
- No duplicate scripts were created; this package adds only the missing schema file and one missing test.

## Schema Contract
- Machine-readable JSON Schema file Sema_Atom/SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json created as Draft-7 schema.
- Root contract requires: schema_id, schema_version, generated_at_utc, saf_path, total_atoms, contexts_total, split_config, final_verdict, residual_status, summary, contexts.
- split_config.split_method constrained to enum: chronological_50_50, chronological_60_40, chronological_70_30, chronological_ratio.
- split_config separates primary readiness minimums (min_train_atoms, min_validation_atoms) from lower display/scoring thresholds (display_min_train_atoms, display_min_validation_atoms).
- Canonical context key format enforced as SYMBOL|SIDE|STRATEGY_ID|REGIME|CONFIDENCE_BUCKET.
- strategy_id is required (minLength: 1) and is never silently merged away.
- support_quality constrained to enum: INSUFFICIENT, BORDERLINE, SUFFICIENT, STRONG.
- support_counts block required: raw_total_count, train_count, validation_count, effective_total_count (int|null), decay_applied (bool). No decay implementation — fields reserved for future auditability.
- timestamp_range block required: earliest_atom_ts_ms, latest_atom_ts_ms, train_window_end_ts_ms, validation_window_start_ts_ms (all int|null).
- final_verdict constrained to enum: VALIDATION_PASSED, VALIDATION_FAILED, VALIDATION_INCONCLUSIVE, VALIDATION_PARTIAL.
- residual_status constrained to enum: NONE, LOW_POWER_RESIDUALS, DATA_COVERAGE_RESIDUALS, MIXED_SIGNAL_RESIDUALS.
- low_power_reason constrained to explicit enum of 7 values.
- train_outcomes/validation_outcomes keys are not schema-constrained to canonical codes (additionalProperties allows any integer count), but POC_03B runtime contract validation enforces canonical-only labels separately.

## POC_03 Sidecar Writer
- POC_03 writes SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json beside the Markdown report.
- The sidecar includes all evaluated contexts, including confirmed, contradicted, inconclusive, and skipped-low-support rows.
- The writer validates the emitted sidecar against the JSON schema before writing it to disk (validate_sidecar_payload call in run_validation).
- No context exists only in Markdown.

## POC_03B JSON Consumer
- POC_03B requires the JSON sidecar as input; no Markdown parsing code exists in POC_03B.
- The consumer validates: schema_id == SemaAtomPoc03EvaluationSidecarV01, schema_version == 1.0.0, contexts_total == len(contexts), context_key uniqueness, strategy_id non-empty, context_key format match, canonical outcome labels only.
- Fails closed on: missing sidecar (FileNotFoundError), malformed JSON (JSONDecodeError), schema_id mismatch, schema_version mismatch, duplicate context_keys, missing strategy_id, context_key format mismatch, non-canonical outcome codes.
- BORDERLINE support_quality never routes to READY_FOR_COUNTERFACTUAL_SIM; always routes to PROMISING_LOW_SUPPORT.
- Manifest preserves context_id as alias of context_key for downstream compatibility.

## Regenerated Artifacts
- Sema_Atom/SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json: created from scratch.
- Other POC_03/POC_03B artifacts (REPORT.md, SIDECAR_V01.json, CANDIDATE_MANIFEST.json, STABILITY_FILTER_REPORT.md) were not regenerated.
- Residual blocker: the canonical input aurora_real_logs_v02.saf.jsonl is not present anywhere in the current workspace as of 2026-05-18, so evidence-faithful regeneration from the real baseline corpus cannot be completed.
- Existing artifact files were not overwritten with synthetic or fail-closed placeholder content.

## Validation
- Focused pytest: tests/test_sema_atom_poc_03_memory_verdict_validation.py — 5/5 passed.
- Focused pytest: tests/test_sema_atom_poc_03b_stability_filter_full.py — 6/6 passed (includes new schema_id mismatch test).
- Downstream regression: tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py — 2/2 passed.
- Total: 13 tests passing, 0 failures.

## Tests
Coverage against the 8 required acceptance tests:

| # | Test Requirement | File | Status |
|---|---|---|---|
| 1 | POC_03 sidecar schema validates | test_run_validation_generates_report_and_inconclusive_status | PASS |
| 2 | POC_03 sidecar contains all contexts | test_run_validation_generates_report_and_inconclusive_status | PASS |
| 3 | POC_03B consumes JSON and produces correct bucket counts | test_run_consumes_json_and_preserves_bucket_counts | PASS |
| 4 | POC_03B fails closed when sidecar missing | test_run_fails_closed_when_sidecar_missing | PASS |
| 5 | POC_03B fails closed on schema_id/schema_version mismatch | test_run_fails_closed_on_schema_id_mismatch + test_run_fails_closed_on_schema_version_mismatch | PASS |
| 6 | Original adapter labels normalized to canonical outcome codes | test_normalize_outcome_code_maps_required_labels + test_run_validation_generates_report_and_inconclusive_status | PASS |
| 7 | context_key includes strategy_id | test_run_validation_partitions_by_strategy_id_in_context_key | PASS |
| 8 | BORDERLINE is not primary READY_FOR_COUNTERFACTUAL_SIM | test_apply_stability_filter_never_promotes_borderline_to_ready | PASS |

## Residual Risks
- Fresh artifact regeneration from the real SAF corpus is still unproven because aurora_real_logs_v02.saf.jsonl is absent from the current workspace. Existing SIDECAR_V01.json and CANDIDATE_MANIFEST.json remain stale until a real SAF is restored and POC_03/POC_03B are rerun.
- The JSON schema does not constrain train_outcomes/validation_outcomes to canonical codes (additionalProperties allows any integer counts). Canonical-code enforcement is applied at POC_03B runtime contract validation. This is intentional to allow the schema to remain valid for schema-level tools while the application layer enforces semantic correctness.
- train_ratio and validation_ratio are optional in split_config. They are reserved for chronological_ratio split method and are not validated to sum to 1.0 at the schema level.

## Next Recommended Step
- Restore or provide the canonical baseline input aurora_real_logs_v02.saf.jsonl.
- Rerun POC_03 to emit the JSON sidecar from the real baseline corpus.
- Rerun POC_03B to regenerate the manifest and stability report from that sidecar.
- After that regeneration closes, proceed to SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01.
