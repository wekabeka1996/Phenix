# Neocortex Fail-Closed Refactor Report

## Scope

Requested surface:

- apps/reference/domains/neocortex/logic/
- apps/reference/domains/neocortex/transport/
- apps/reference/domains/neocortex/config_models.py
- apps/reference/domains/neocortex/main.py

This pass focused on runtime truth boundaries: reward/oracle labeling, policy inference, policy training labels, baseline shadow inference, Dreamer consolidation, async file I/O, and bridge concurrency. Existing unrelated dirty worktree files were not reverted or normalized.

main.py was inspected for silent exception swallowing and blocking async hazards. Its broad startup exception handler logs and exits, and WAL append failure logs with exception context; no main.py code change was required in this package. main.py still uses dict[str, Any] for dynamic event payloads; see Residuals.

## Summary Verdict

Status: ACCEPTED_WITH_RESIDUALS

The major runtime silent fallbacks found in the Neocortex domain were removed or converted into fail-closed skip/error paths with logs and alerts. The old behavior that fabricated regime labels, reward matrix truth, PPO FLAT actions, zero latents, zero rewards, raw-feature latents, missing baseline thresholds, and missing toxic class provenance is now covered by focused tests.

Residuals remain around existing public payload APIs typed as Any, parser/normalizer vector sanitization defaults, and legacy experiment/PPO-library files outside the active runtime flow.

## Silent Fallbacks Fixed

### config_models.py

- Added strict reward matrix contract validation for OracleConfig.
- reward_matrix_enabled=True now requires reward_matrix.
- reward_matrix must be 5x5 and contain only finite numeric values.
- This prevents Formula B from silently depending on an implicit hardcoded matrix.

### logic/reward/reward_calculator.py

- Formula B no longer falls back to REWARD_MATRIX when runtime config omits reward_matrix.
- _validated_reward_matrix() now rejects missing, malformed, non-5x5, and non-finite matrix values.
- REWARD_MATRIX remains only as a documented legacy/reference constant for tests and audit comparisons.

### logic/reward/regime_labeler.py

- Realized regime computation no longer treats missing fields as 0.0 or default confidence as 0.5.
- Missing, None, bool, non-numeric, and non-finite inputs now raise ValueError.
- price must be finite and non-zero.
- Adapter oracle settlement catches these ValueErrors and emits ORACLE_LABEL_FEATURES_INCOMPLETE instead of producing synthetic label truth.

### logic/brain/baseline_inference.py

- Removed effective runtime fallback to DEFAULT_TOXIC_THRESHOLD.
- BaselineController now requires threshold either from explicit constructor argument or artifact metadata.
- predict_toxic_probability() now requires classes_ provenance.
- Missing toxic class 1 raises ValueError instead of assuming probability column position.

### logic/brain/bridge.py

- encode_async() no longer returns a synthetic zero latent on timeout/error.
- act_async() no longer returns a synthetic FLAT action on timeout/error.
- Both now raise RuntimeError with explicit no-synthetic wording.
- Worker result errors now set future exceptions rather than disappearing.
- Queue polling handles queue.Empty specifically.
- save_async()/load_async() and shutdown signal failure now log exceptions instead of silent pass behavior.

### logic/brain/core.py

- encode() now raises when PyTorch is unavailable instead of returning a zero latent.
- get_action() no longer emits synthetic FLAT when PPO is missing, corrupted, invalid, or produces non-finite output.
- Hidden-state reset failure now logs a warning instead of pass.
- Policy training now skips malformed policy samples instead of converting missing action to FLAT or missing reward to 0.0.
- Boolean action/reward labels are rejected as invalid training truth.
- Invalid policy action names and out-of-range action indexes are skipped with warnings.

### logic/dreamer.py

- Dreamer no longer treats raw features as latent state when no encoder is configured.
- Missing or invalid side no longer defaults to FLAT.
- Missing, bool, or non-finite reward no longer defaults to 0.0.
- Malformed episodes are skipped by consolidate() with warning logs, so they do not enter graph truth.

### transport/adapter.py

- _extract_raw_feature_map() no longer invents 0.0 for labeler-facing raw features.
- Oracle settlement skips and alerts when labeler features are incomplete.
- Missing reward is preserved as None and marked reward_missing/reward_complete=false.
- Missing reward keys are treated as missing, not 0.0.
- Oracle model feature vector construction no longer backfills missing features with 0.0; it skips and emits ORACLE_MODEL_FEATURES_INCOMPLETE.
- stats now logs telemetry stats read failures instead of swallowing them silently.

### logic/ingest/wal_replayer.py

- Async fallback read path now uses asyncio.to_thread(file_path.read_text, ...), avoiding synchronous file iteration inside an async generator.
- Malformed JSON lines increment events_malformed and log warnings for early/periodic occurrences instead of being invisible.

## Dead Code Removed

- logic/dreamer.py: removed standalone dream_consolidation(...), including the inner EpisodeLike defaults that converted side to FLAT and reward to 0.0.
- logic/ingest/multi_tailer.py: removed unreachable legacy cancellation block after an unconditional return.
- logic/brain/bridge.py: removed stale pass/comment block around future completion and replaced error completion with explicit exception propagation.
- logic/brain/core.py: removed synthetic inference fallback behavior for PPO/latent paths rather than keeping compatibility masks.

## Async/Await Correctness

- logic/ingest/wal_replayer.py: replaced blocking fallback file iteration with asyncio.to_thread for whole-file read before line replay.
- transport/adapter.py: added _run_non_critical_io() and moved non-critical JSONL/telemetry writes in async paths through asyncio.to_thread.
- transport/adapter.py: protected shadow intent buffer enqueue/flush with an RLock.
- logic/brain/bridge.py: queue.Empty is handled explicitly, timeouts are logged, and future completion now propagates worker errors.
- logic/brain/bridge.py: _submit() safely acquires or refreshes the event loop before creating futures.

## Data Provenance

- Reward matrix truth now must come from config when Formula B is enabled.
- Realized regime labels require finite source features at t and t+h; incomplete source data is skipped with alert telemetry.
- Baseline shadow inference requires threshold and classes_ artifact provenance.
- Adapter episode serialization preserves reward_missing/reward_complete instead of flattening absent reward to zero.
- Dreamer graph consolidation requires a real encoder and real reward before adding graph transition truth.
- PPO training samples require explicit valid action and reward before entering the PPO buffer.

## Tests Updated Or Added

- tests/apps/reference/domains/neocortex/tests/test_confusion_matrix.py
- tests/apps/reference/domains/neocortex/tests/test_oracle_infrastructure.py
- tests/apps/reference/domains/neocortex/tests/test_oracle_wiring.py
- tests/apps/reference/domains/neocortex/tests/test_reward_contract.py
- tests/apps/reference/domains/neocortex/tests/test_brain.py
- tests/apps/reference/domains/neocortex/tests/test_dreamer.py
- tests/domains/neocortex/unit/test_baseline_inference.py
- tests/domains/neocortex/integration/test_bridge_timeouts.py

Regression coverage now asserts:

- missing reward_matrix is rejected when reward_matrix_enabled=True
- missing/None labeler features are rejected
- adapter preserves missing reward as None
- absent reward key is treated as missing
- baseline missing threshold is rejected
- baseline missing toxic class 1 is rejected
- bridge encode/action timeout paths raise RuntimeError instead of synthetic output
- BrainCore PPO action fallback paths fail closed
- Dreamer does not create raw-feature latent state or zero-reward transitions
- PPO policy-training malformed samples are skipped instead of becoming FLAT/zero reward labels

## Static Analysis And Validation Evidence

Python executable used:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe
```

Expanded targeted regression command:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/apps/reference/domains/neocortex/tests/test_confusion_matrix.py tests/apps/reference/domains/neocortex/tests/test_oracle_infrastructure.py tests/apps/reference/domains/neocortex/tests/test_oracle_wiring.py tests/apps/reference/domains/neocortex/tests/test_reward_contract.py tests/apps/reference/domains/neocortex/tests/test_brain.py tests/apps/reference/domains/neocortex/tests/test_dreamer.py tests/domains/neocortex/unit/test_baseline_inference.py tests/domains/neocortex/test_shadow_inference_flow.py tests/apps/reference/domains/neocortex/tests/test_ppo_loop.py tests/domains/neocortex/integration/test_bridge_timeouts.py -q
```

Result:

```text
122 passed, 9 skipped in 3.76s
```

Dreamer focused validation after removing legacy fallback:

```text
tests/apps/reference/domains/neocortex/tests/test_dreamer.py: 18 passed in 3.49s
```

Reward/oracle focused validation after reward/model feature provenance tightening:

```text
54 passed in 2.32s
```

BrainCore focused validation after PPO hardening:

```text
2 passed, 10 skipped in 0.86s
```

The extra BrainCore policy-training regression is skipped in this venv because PyTorch is unavailable.

Syntax validation command:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m py_compile apps/reference/domains/neocortex/config_models.py apps/reference/domains/neocortex/logic/reward/reward_calculator.py apps/reference/domains/neocortex/logic/reward/regime_labeler.py apps/reference/domains/neocortex/logic/brain/bridge.py apps/reference/domains/neocortex/logic/brain/core.py apps/reference/domains/neocortex/logic/brain/baseline_inference.py apps/reference/domains/neocortex/logic/dreamer.py apps/reference/domains/neocortex/transport/adapter.py apps/reference/domains/neocortex/logic/ingest/wal_replayer.py apps/reference/domains/neocortex/logic/ingest/multi_tailer.py
```

Result: no output, exit success.

VS Code diagnostics via get_errors:

```text
No errors found for all edited runtime and focused test files.
```

Requested mypy command:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m mypy apps/reference/domains/neocortex/
```

Result:

```text
C:\Users\user\Music\Phenix\.venv\Scripts\python.exe: No module named mypy
```

mypy evidence is unavailable until mypy is installed in this virtualenv. The fallback static evidence for this pass is py_compile plus VS Code diagnostics.

## Residuals

- Strict Type Hinting / Kill Any is not fully complete. The Neocortex runtime still exposes dynamic event payload APIs using dict[str, Any] and helper functions that handle JSON-like values. Removing all Any would be a wider API-contract migration and was not forced into this fail-closed patch.
- logic/ingest/parser.py and logic/ingest/normalizer.py still sanitize model-vector representation with configured zero fill in places. This pass left that intact because it is vector representation hygiene, not realized label/reward truth. The adapter now preserves raw feature incompleteness before oracle labeling.
- apps/reference/domains/neocortex/PPO/ and apps/reference/domains/neocortex/experiments/ still contain legacy/demo zero initializers and metrics defaults. They were not part of the active runtime patch surface and were not rewritten.
- Full repository tests were not run. The validation here is the focused Neocortex regression set plus syntax and diagnostics.
- PyTorch is unavailable in this venv, so PyTorch-dependent tests remain skipped. The new policy-training regression is present and will run in a torch-enabled environment.

## Closure

This refactor removes the dangerous runtime fallbacks that could fabricate decision, reward, latent, action, and graph-training truth. The remaining residuals are explicit and bounded: typing cleanup, parser vector sanitization policy, legacy experiment/PPO-library surfaces, and environment-limited mypy/torch coverage.

## Phase 2 Evidence Addendum

This addendum hardens the Phase 2 audit trail before Phase 3. The runtime config surface now treats `system.yaml`, `ingest.yaml`, `neuro.yaml`, and `replay.yaml` as explicit required inputs, and the config-contract tests confirm fail-closed behavior on missing runtime keys.

```yaml
phase_2_evidence_addendum:
  completed: true
  location: "docs/DeepMind/NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md"
  validation_commands:
    - command: "python -m pytest tests/domains/neocortex/contract/test_failure_taxonomy.py -v"
      result: pass
      output_summary: "18 passed, 1 skipped"
    - command: "python -m pytest tests/domains/neocortex/architecture/test_failure_boundary.py -v"
      result: pass
      output_summary: "1 passed"
    - command: "python -m pytest tests/domains/neocortex/contract/test_config_default_classification.py -v"
      result: pass
      output_summary: "88 passed"
    - command: "python -m pytest tests/domains/neocortex/architecture/test_neocortex_real_config_startup.py -v"
      result: pass
      output_summary: "6 passed"
    - command: "python -m pytest tests/domains/neocortex/contract/test_causal_time_provenance.py -v"
      result: pass
      output_summary: "46 passed"
    - command: "python -m pytest tests/domains/neocortex/contract/test_state_aggregator_causal_time.py -v"
      result: pass
      output_summary: "23 passed"
    - command: "python -m pytest tests/domains/neocortex/architecture/test_import_boundaries.py -v"
      result: pass
      output_summary: "130 passed"
    - command: "python -m pytest tests/domains/neocortex/test_neocortex_main_bootstrap.py -v"
      result: pass
      output_summary: "5 passed"
    - command: "python -m pytest tests/domains/neocortex/ -v"
      result: pass
      output_summary: "369 passed, 1 skipped"
  config_field_inventory:
    total_fields: 140
    structural_safe: 27
    runtime_behavior: 109
    legacy_compat: 4
    unclassified: 0
  yaml_files_changed:
    - "apps/reference/domains/neocortex/config/system.yaml"
    - "apps/reference/domains/neocortex/config/ingest.yaml"
    - "apps/reference/domains/neocortex/config/neuro.yaml"
    - "apps/reference/domains/neocortex/config/replay.yaml"
  runtime_behavior_defaults_removed_list:
    - field: "neocortex.trust_enabled"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.mode"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.deadline_ms"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.fallback_policy"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.max_inflight_per_symbol"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.modulation_allowlist"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.signal_threshold_bias_bounds"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
    - field: "neocortex.authority.cooldown_mult_bounds"
      old_python_default: "removed in Phase 2"
      new_yaml_path: "apps/reference/domains/neocortex/config/system.yaml"
  required_62_keys_presence_table:
    - key: "neocortex.trust_enabled"
      status: present
    - key: "neocortex.authority.mode"
      status: present
    - key: "neocortex.authority.deadline_ms"
      status: present
    - key: "neocortex.authority.fallback_policy"
      status: present
    - key: "neocortex.authority.max_inflight_per_symbol"
      status: present
    - key: "neocortex.authority.modulation_allowlist"
      status: present
    - key: "neocortex.authority.signal_threshold_bias_bounds"
      status: present
    - key: "neocortex.authority.cooldown_mult_bounds"
      status: present
```

## Phase 3 Closure Addendum

```yaml
verdict: PHASE_3_GREEN
phase: "Phase 3 - Failure Taxonomy & Fallback Ledger Closure Addendum"

phase_2_addendum:
  accepted: true
  location: "docs/DeepMind/NEOCORTEX_FAIL_CLOSED_REFACTOR_REPORT.md"

contracts:
  failure_taxonomy_exists: true
  failure_reason_codes_exist: true
  contract_files:
    - "apps/reference/domains/neocortex/contracts/failure_taxonomy.py"

failure_reason_coverage:
  NON_CAUSAL_TIME: present
  MISSING_REQUIRED_STATE: present
  UNJOINABLE_LIFECYCLE: present
  LOW_SUPPORT: present
  BASELINE_UNAVAILABLE: present
  MALFORMED_JSON: present
  HANDLER_FAILURE: present
  BRIDGE_UNAVAILABLE: present
  MODEL_ARTIFACT_MISMATCH: present
  TELEMETRY_FLUSH_FAILED: present

failure_ledger:
  exists: true
  files:
    - "apps/reference/domains/neocortex/logic/failure_ledger.py"
  api:
    record: "record_failure_outcome(...), FailureLedger.record_failure(outcome)"
    read_counts: "get_failure_outcome_total(...), get_failure_outcome_counts()"
    reset_for_tests: "reset_failure_outcomes(), FailureLedger.reset_failure_counts()"
  counter_name: "failure_outcomes_total"
  canonical_metrics_emission: false
  temporary_local_counter: true
  phase7_followup_required: true

hot_path_exception_audit:
  audit_test: "tests/domains/neocortex/architecture/test_failure_boundary.py::test_hot_path_broad_exception_handlers_are_typed_or_absent"
  total_broad_exceptions_found: 0
  hot_path_broad_exceptions_found: 0
  hot_path_resolved: 0
  remaining_hot_path_broad_exceptions: []

synthetic_fallback_checks:
  model_failure_returns_flat: impossible
  model_failure_returns_zero_latent: impossible
  failure_returns_zero_reward: impossible
  missing_state_becomes_unknown_safe: impossible
  malformed_json_becomes_valid_row: impossible
  telemetry_failure_silent: impossible
  startup_failure_silent_downgrade: impossible

provocation_tests:
  malformed_json:
    test: "tests/domains/neocortex/contract/test_failure_taxonomy.py::test_malformed_json_records_skip_row_reason"
    result: pass
  io_fail:
    test: "tests/domains/neocortex/contract/test_failure_taxonomy.py::test_model_artifact_mismatch_fails_startup_without_zero_latent[missing]"
    result: pass
  bridge_timeout:
    test: "tests/domains/neocortex/contract/test_failure_taxonomy.py::test_bridge_timeout_records_fallback_reason"
    result: pass
  baseline_artifact_mismatch:
    test: "tests/domains/neocortex/contract/test_failure_taxonomy.py::test_model_artifact_mismatch_fails_startup_without_zero_latent[corrupt]"
    result: pass
  telemetry_flush_fail:
    test: "tests/domains/neocortex/contract/test_failure_taxonomy.py::test_telemetry_flush_failure_becomes_degraded_observability"
    result: pass

wal_replayer_training_strict_mode:
  addressed: false
  evidence: "apps/reference/domains/neocortex/logic/ingest/wal_replayer.py remains # QUARANTINED: legacy_runtime with __quarantined__ = True."
  if_not_addressed_reason: "Legacy WAL replayer is quarantined and outside the active hot-path runtime; keep the strict-mode default as a Phase 6/7 follow-up."

validation:
  - command: "python -m pytest tests/domains/neocortex/contract/test_failure_taxonomy.py -v"
    result: pass
    output_summary: "19 passed, 1 skipped"
  - command: "python -m pytest tests/domains/neocortex/architecture/test_failure_boundary.py -v"
    result: pass
    output_summary: "1 passed"
  - command: "python -m pytest tests/domains/neocortex/contract/test_config_default_classification.py -v"
    result: pass
    output_summary: "88 passed"
  - command: "python -m pytest tests/domains/neocortex/architecture/test_neocortex_real_config_startup.py -v"
    result: pass
    output_summary: "6 passed"
  - command: "python -m pytest tests/domains/neocortex/contract/test_causal_time_provenance.py -v"
    result: pass
    output_summary: "46 passed"
  - command: "python -m pytest tests/domains/neocortex/contract/test_state_aggregator_causal_time.py -v"
    result: pass
    output_summary: "23 passed"
  - command: "python -m pytest tests/domains/neocortex/architecture/test_import_boundaries.py -v"
    result: pass
    output_summary: "130 passed"
  - command: "python -m pytest tests/domains/neocortex/ -v"
    result: pass
    output_summary: "370 passed, 1 skipped"

residuals_accepted_as_non_blocking:
  - residual: "dict[str, Any] dynamic payload APIs remain at the JSON boundary."
    reason_not_blocking_phase3: "They do not fabricate business truth; they only carry untyped transport payloads."
    phase_to_close: "Phase 4+"
  - residual: "logic/ingest/parser.py and logic/ingest/normalizer.py still zero-fill model-vector representation in local hygiene paths."
    reason_not_blocking_phase3: "The zero-fill is representation hygiene, not realized label/reward truth."
    phase_to_close: "Phase 4+"
  - residual: "apps/reference/domains/neocortex/PPO/ and apps/reference/domains/neocortex/experiments/ still contain legacy/demo zero initializers."
    reason_not_blocking_phase3: "They are legacy/demo surfaces, not active runtime truth."
    phase_to_close: "Phase 6+"
  - residual: "apps/reference/domains/neocortex/logic/ingest/wal_replayer.py strict-mode default for training modes remains pending."
    reason_not_blocking_phase3: "The module is quarantined legacy_runtime and is not part of the current hot-path runtime."
    phase_to_close: "Phase 6/7"
  - residual: "BRIDGE_UNAVAILABLE runtime mapping remains declared Phase 5 pending."
    reason_not_blocking_phase3: "The active bridge path is typed and fail-closed; the placeholder runtime mapping is explicitly skipped."
    phase_to_close: "Phase 5"

hard_fail_conditions:
  model_baseline_failure_can_return_synthetic_flat: resolved
  model_baseline_failure_can_return_zero_latent_or_reward: resolved
  unknown_missing_state_can_be_safe_valid_business_value: resolved
  hot_path_broad_exception_swallows_failure: resolved
  malformed_json_becomes_valid_trainable_row: resolved
  telemetry_flush_failure_silent: resolved
  startup_failure_silent_downgrade: resolved
  failure_counter_not_testable: resolved
  phase_0_boundary_regressed: resolved
  phase_1_causal_tests_regressed: resolved
  phase_2_config_tests_regressed: resolved

self_attack:
  - "The only remaining ambiguity is whether Phase 7 will adopt the local failure ledger as canonical metrics or replace it with a metrics sink-backed emitter."
  - "Quarantined legacy_runtime surfaces stay excluded from the hot-path audit; keep that boundary explicit when Phase 5/6 work starts."

phase_4_allowed: true
```
