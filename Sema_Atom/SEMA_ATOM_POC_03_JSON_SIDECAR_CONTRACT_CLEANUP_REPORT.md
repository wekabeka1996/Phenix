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
- Sema_Atom/SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION.py
- Sema_Atom/SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json
- Sema_Atom/SEMA_ATOM_POC_03B_STABILITY_FILTER_FULL.py
- tests/test_sema_atom_poc_03_memory_verdict_validation.py
- tests/test_sema_atom_poc_03b_stability_filter_full.py

## Discovery / Duplication Check
- Existing writer located in Sema_Atom/SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION.py.
- Existing stability consumer located in Sema_Atom/SEMA_ATOM_POC_03B_STABILITY_FILTER_FULL.py.
- Existing downstream manifest consumer located in Sema_Atom/SEMA_ATOM_POC_04_COUNTERFACTUAL_POLICY_IMPACT_SIMULATION.py.
- Existing focused tests located in tests/test_sema_atom_poc_03_memory_verdict_validation.py, tests/test_sema_atom_poc_03b_stability_filter_full.py, and tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py.
- No duplicate scripts were created; the package extends the existing POC_03 and POC_03B scripts in place.

## Schema Contract
- Added machine-readable schema file Sema_Atom/SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json.
- Root contract now requires schema_id, schema_version, generated_at_utc, saf_path, total_atoms, contexts_total, split_config, summary, contexts, final_verdict, and residual_status.
- Canonical context key is enforced as SYMBOL|SIDE|STRATEGY_ID|REGIME|CONFIDENCE_BUCKET.
- strategy_id is required and is never silently merged away.
- split_config now separates primary readiness minimums (5/5) from lower display/scoring thresholds when used.
- support_quality is constrained to INSUFFICIENT, BORDERLINE, SUFFICIENT, STRONG.
- support_counts and timestamp_range are explicit required blocks.
- Outcome counts are constrained to canonical outcome codes only: GOOD_DECISION, CLEAN_LOSS, BAD_EXIT, POLICY_PROTECTED, POLICY_TOO_STRICT, NEUTRAL_SIGNAL.

## POC_03 Sidecar Writer
- POC_03 now writes SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json beside the Markdown report.
- The sidecar includes all evaluated contexts, including confirmed, contradicted, inconclusive, and skipped-low-support rows.
- Context payloads now include context_key, symbol, side, strategy_id, regime, confidence_bucket, verdict, recommendation, validation_result, validation_reason, train/validation counts, train/validation outcome counts, train/validation net scores, train/validation rates, support_quality, support_counts, low_power_reason, and timestamp_range.
- The writer validates the emitted sidecar against the JSON schema before writing it to disk.

## POC_03B JSON Consumer
- POC_03B now requires the JSON sidecar as input and no longer parses Markdown as transport.
- The consumer validates schema_id == SemaAtomPoc03EvaluationSidecarV01 and schema_version == 1.0.0.
- The consumer fails closed on missing sidecar, malformed JSON, schema mismatch, duplicate context keys, missing strategy_id, context_key mismatch, or non-canonical outcome labels.
- READY_FOR_COUNTERFACTUAL_SIM admission now depends on support_quality in {SUFFICIENT, STRONG}; BORDERLINE is routed to PROMISING_LOW_SUPPORT and is never primary-ready.
- Manifest payloads preserve downstream compatibility by retaining context_id as an alias of context_key.

## Regenerated Artifacts
- Created: Sema_Atom/SEMA_ATOM_POC_03_EVALUATION_SIDECAR_SCHEMA_V01.json.
- Code path now supports regenerating:
  - SEMA_ATOM_POC_03_MEMORY_VERDICT_VALIDATION_REPORT.md
  - SEMA_ATOM_POC_03_EVALUATION_SIDECAR_V01.json
  - SEMA_ATOM_POC_03B_CANDIDATE_MANIFEST.json
  - SEMA_ATOM_POC_03B_STABILITY_FILTER_REPORT.md
- Residual blocker: the canonical input aurora_real_logs_v02.saf.jsonl is not present anywhere in the current workspace as of 2026-05-15, so evidence-faithful regeneration against the existing SAF input could not be completed.
- Existing artifact files were not overwritten with synthetic or fail-closed placeholder content.

## Validation
- Focused pytest validation after the first writer change:
  - tests/test_sema_atom_poc_03_memory_verdict_validation.py
- Focused pytest validation after the consumer rewrite:
  - tests/test_sema_atom_poc_03b_stability_filter_full.py
- Narrow downstream regression validation:
  - tests/test_sema_atom_poc_03_memory_verdict_validation.py
  - tests/test_sema_atom_poc_03b_stability_filter_full.py
  - tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py
- Filesystem check for aurora_real_logs_v02.saf.jsonl returned NO_SAF_FOUND in the current workspace.

## Tests
- 5/5 passed: tests/test_sema_atom_poc_03_memory_verdict_validation.py
- 5/5 passed: tests/test_sema_atom_poc_03b_stability_filter_full.py
- 12/12 passed: tests/test_sema_atom_poc_03_memory_verdict_validation.py tests/test_sema_atom_poc_03b_stability_filter_full.py tests/test_sema_atom_poc_04_counterfactual_policy_impact_simulation.py

## Residual Risks
- Fresh artifact regeneration is still unproven because the canonical SAF corpus is absent from the workspace.
- Existing POC_03 / POC_03B artifact files remain stale until rerun on the restored SAF input.
- POC_04 compatibility is test-proven, but no new end-to-end artifact batch was emitted from the real baseline corpus in this workspace state.

## Next Recommended Step
- Restore or provide the canonical baseline input aurora_real_logs_v02.saf.jsonl.
- Rerun POC_03 to emit the JSON sidecar from the real baseline corpus.
- Rerun POC_03B to regenerate the manifest and stability report from that sidecar.
- After that regeneration closes, proceed to SEMA_ATOM_REFERENCE_PRICE_RECOVERY_POLICY_V01.
