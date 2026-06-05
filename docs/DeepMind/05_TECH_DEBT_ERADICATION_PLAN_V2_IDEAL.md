# Blueprint: Neocortex Tech Debt Eradication V2 - Ideal Pragmatic Plan

## Purpose

This is the pragmatic replacement for `04_TECH_DEBT_ERADICATION_PLAN_V1.md`.

It targets the same Definition of Done:

- 0 static/type errors for the active Neocortex surface.
- 100% hot-path coverage for the production-shadow path.
- Strict causal time for trainable and authority-adjacent data.
- No silent fallbacks in ML, replay, telemetry, or dataset truth paths.

The key change from V1: do not start by splitting `transport/adapter.py`. First freeze the current hot path, classify legacy behavior, and build executable gates that make any later split measurable. The monolith is a risk, but splitting it before the contracts are nailed down mostly moves ambiguity into smaller files.

## Evidence Baseline

### Proven facts

- The active Stage 0.3 path is centered on `main.py`, `NeocortexStateAggregator`, `BaselineController`, `NeocortexAuthorityBridge`, and `ShadowGateEvaluator`.
- `transport/adapter.py`, `MultiTailer`, `WalTailer`, `WALReplayer`, `BrainCore`, `BrainBridge`, `Dreamer`, and PPO are legacy/offline/RL-shaped surfaces, not the current Stage 0.3 production-shadow authority path.
- The fail-closed refactor already removed several high-risk synthetic outputs: zero latents, synthetic FLAT actions, missing baseline thresholds, raw-feature Dreamer latents, missing reward matrix truth, and incomplete oracle labels.
- Current replay compatibility still exists through `ReplayConfig.wal_glob`, `ReplayConfig.wal_dir`, `feature_missing_timestamp_policy`, and `legacy_non_causal_file_offset`.
- `TelemetryLogger` writes CSV, not SQLite. SQLite risk exists in `logic/memory/graph.py`, which belongs to Dreamer/causal graph, not the current Stage 0.3 hot path.

### Inferences

- The highest-value work is not a broad rewrite. It is turning the remaining boundaries into executable contracts: time provenance, dataset trainability, config ownership, failure surfaces, and hot-path coverage.
- `adapter.py` should be quarantined before it is split. If split too early, tests will preserve accidental behavior just because it existed.
- Backward compatibility with old WALs must be explicit, labeled, and non-trainable by default. Compatibility is acceptable for diagnostics; it is not acceptable as causal truth.

### Unknowns

- Full mypy status is not proven in the current venv unless `mypy` is installed.
- Torch-dependent policy training tests may be skipped in this environment.
- Runtime behavior under sustained real event-tap load is not proven by unit tests alone.

## Execution Update - 2026-04-28

### What is now proven in code

- Phase 0 import quarantine is executable through `tests/domains/neocortex/architecture/test_import_boundaries.py`. It imports the active Stage 0.3 modules in isolation and asserts that they do not transitively load `transport.adapter`, `logic.ingest.multi_tailer`, `logic.brain.core`, `logic.brain.bridge`, `logic.dreamer`, or any `neocortex.PPO` modules.
- Legacy quarantine markers now exist in `transport/adapter.py`, `logic/ingest/multi_tailer.py`, `logic/ingest/wal_replayer.py`, `logic/brain/core.py`, `logic/dreamer.py`, and the canonical PPO entrypoints.
- Phase 1 causal-time contract now exists in `logic/datasets/time_provenance.py` as `CausalTimeProvenance` with the production-allowed set `{exchange_event, aurora_event, bar_end}`.
- `main.py` now tags `captured_ts_ms` or frame-time fallback as `captured_wallclock` instead of silently treating it as causal event time.
- `FeatureParser`, `core_parser.py`, and `order_parser.py` now emit explicit provenance (`time_provenance`) in addition to legacy compatibility fields such as `time_source` and `time_is_causal`.
- `NeocortexStateAggregator` now drops non-causal rows in `shadow` and `enforce` modes unless `allow_legacy_non_causal_time=True` is explicitly set.
- `MultiTailer` now forwards explicit provenance to downstream consumers through `event_time_provenance`.

### Validation already executed

- `pytest tests/domains/neocortex/architecture/test_import_boundaries.py -q` -> `5 passed`
- `pytest tests/domains/neocortex/unit/test_causal_time_provenance.py tests/domains/neocortex/unit/test_parser.py tests/domains/neocortex/unit/test_state_aggregator_v2.py tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q` -> `21 passed`
- VS Code diagnostics for the touched Phase 0 and Phase 1 files reported no errors.

### Honest status against this plan

- Phase 0 is partially executed, not complete. Action 2 and Action 3 are done. Action 1 (surface inventory report) and Action 4 (one explicit public compatibility contract for old tests) remain open.
- Phase 1 is partially executed but the highest-risk Stage 0.3 runtime seam is now enforced. Action 1, Action 2, and Action 4 are done on the active shadow path. Action 3 is only partially complete because diagnostics-only or `trainable=false` enforcement is not yet proven end-to-end across all offline dataset builders. Action 5 is only partially complete because contract tests for `WalTailer` and `WALReplayer` are still missing.

### Later update - 2026-04-28

- The earlier Phase 0 note is stale on Action 1: the machine-checked surface inventory now exists at `docs/DeepMind/inventory/neocortex_surface_inventory.md`, and `tests/domains/neocortex/architecture/test_import_boundaries.py` enforces completeness for the current hot-path surface, including `contracts/causal_time.py` and `contracts/failure_taxonomy.py`.
- Phase 2 is now executed on the active Neocortex test surface. The config contract is explicit-on-enable, replay-enabled fixtures are explicit, and the Neocortex suite no longer depends on removed implicit business defaults.
- Phase 3 is now executed on the active Stage 0.3 path. `contracts/failure_taxonomy.py` exists, the named hot-path modules no longer use `except Exception`, `FailureOutcomeTaxonomy` is emitted through in-process counters for `SKIP_ROW`, `FALLBACK`, `DEGRADED_OBSERVABILITY`, and `FATAL_STARTUP`, and the authority bridge plus startup/bootstrap path now classify failures with explicit reason codes.
- Validation for the Phase 2 plus Phase 3 closure is now stronger than the earlier partial note: `pytest tests/domains/neocortex tests/apps/reference/domains/neocortex tests/domains/decision_making/test_authority_bridge.py -q` -> `520 passed, 27 skipped`.

## Non-Negotiable Invariants

1. Production-shadow mode must never treat wallclock, captured time, file offset time, or log write time as causal event time.
2. Legacy rows may be parsed only with explicit provenance and must default to diagnostics-only unless a test explicitly permits training.
3. ML failures must produce explicit failure semantics, not synthetic neutral actions or synthetic clean data.
4. Config owns all behavior-affecting parameters. Code may have structural defaults only when the default is provably not a trading/model behavior decision.
5. A module is not considered safe because it is split. It is safe only when its contract, failure mode, and caller expectations are tested.
6. Hot-path coverage means the Stage 0.3 path, not every legacy research script.

## Phase 0 - Freeze The Baseline And Draw The Boundary

### Goal

Make it impossible to confuse active runtime, legacy replay, offline research, and tests.

### Current status (2026-04-28)

Partial execution.

- Done: executable import-boundary proof
- Done: quarantine markers on the main legacy/RL entrypoints
- Still open: surface inventory artifact
- Still open: explicit compatibility contract for old tests

### Actions

1. Create a Neocortex surface inventory with four labels: `hot_path`, `legacy_runtime`, `offline_research`, `tests_only`.
2. Add a small import-boundary test that proves Stage 0.3 startup does not import `transport.adapter`, `logic.ingest.multi_tailer`, `logic.brain.core`, `logic.brain.bridge`, `logic.dreamer`, or PPO.
3. Add a legacy quarantine marker for `adapter.py`, `multi_tailer.py`, `tailer.py`, `wal_replayer.py`, `dreamer.py`, `brain/core.py`, and PPO entrypoints.
4. Define one public compatibility contract for old tests: either keep the old class names as thin wrappers, or move tests to the new service interfaces. Do not do both indefinitely.

### Validation

- `pytest tests/domains/neocortex -q` for Stage 0.3 tests.
- Import-boundary test fails if hot path imports quarantined legacy modules.
- A generated inventory report lists every Neocortex module and its label.
- Executed proof so far: `pytest tests/domains/neocortex/architecture/test_import_boundaries.py -q` -> `5 passed`.

### Exit gate

No refactor begins until the team can answer: what is hot, what is legacy, what is intentionally kept only for replay diagnostics, and what is deleteable.

## Phase 1 - Causal Time Contract First

### Goal

Close the highest silent-corruption channel before rearranging code.

### Current status (2026-04-28)

Partial execution, with the active Stage 0.3 shadow path now fail-closed on non-causal time.

- Done: `CausalTimeProvenance` contract exists and is used by the active parser or aggregator path
- Done: Stage 0.3 ingress now distinguishes `captured_wallclock` from causal event time
- Done: aggregator rejects non-causal rows in `shadow` or `enforce` unless explicitly overridden for tests or legacy replay
- Still open: explicit diagnostics-only or `trainable=false` propagation through all offline dataset builders
- Still open: contract tests for `WalTailer` and `WALReplayer`

### Actions

1. Define a `CausalTimeProvenance` contract with allowed values such as `exchange_event`, `aurora_event`, `bar_end`, `captured_wallclock`, `file_offset_legacy`, and `unknown`.
2. In production-shadow and training modes, allow only causal sources: `exchange_event`, `aurora_event`, or a documented `bar_end` source when the strategy contract explicitly uses bar close time.
3. In legacy replay mode, allow `file_offset_legacy` only when the row is marked `trainable=false` and carries a visible reason such as `NON_CAUSAL_TIMESTAMP`.
4. Tighten `main.py` normalization so `captured_ts_ms` and frame `ts` cannot silently become causal `event_ts_ms` in Stage 0.3.
5. Add contract tests for `StateAggregator_v2`, `feature_parser.py`, `MultiTailer`, `WalTailer`, and `WALReplayer` using rows with real event time, wallclock time, file offset time, missing time, and mixed aliases.

### Validation

- Production-shadow test: non-causal row is rejected or ignored before state aggregation.
- Offline compatibility test: legacy row is accepted only as diagnostics-only.
- Dataset admission test: non-causal rows cannot enter policy, execution-quality, regime-supervision, or representation training unless a mode-specific exception is explicitly tested.
- Executed proof so far: `pytest tests/domains/neocortex/unit/test_causal_time_provenance.py tests/domains/neocortex/unit/test_parser.py tests/domains/neocortex/unit/test_state_aggregator_v2.py tests/apps/reference/domains/neocortex/tests/test_time_contract.py -q` -> `21 passed`.

### Exit gate

It is physically hard for a non-causal timestamp to become trainable truth or authority-adjacent state.

## Phase 2 - Config Sterilization With Classification, Not Blind Deletion

### Goal

Remove behavior defaults without breaking harmless structure or test ergonomics.

### Actions

1. Classify every Pydantic default as one of:
   - `structural_safe`: path shape, empty list/dict containers, optional disabled subsystem.
   - `runtime_behavior`: any threshold, mode, seed, timeout, quota, reward scale, model dimension, clipping rule, action policy, or emit policy.
   - `legacy_compat`: values retained only for old WALs/tests and forbidden in production-shadow.
2. Move all `runtime_behavior` defaults into YAML and require explicit values in Pydantic.
3. Keep `legacy_compat` defaults only behind explicit legacy mode and make startup gates warn or fail depending on mode.
4. Add a reflection test that fails when a new behavior-affecting field gets a Pydantic default without a classification entry.
5. Add a real-config startup test that loads `system.yaml`, `ingest.yaml`, `neuro.yaml`, `replay.yaml`, and `regime_oracle_reward.yaml` and evaluates `ShadowGateEvaluator`.

### Validation

- Config reflection test has 0 unclassified defaults.
- Real config load has 0 schema errors.
- Production-shadow config fails if `feature_missing_timestamp_policy=legacy_non_causal_file_offset`.
- Offline replay config may warn, but its output rows remain non-trainable unless proven causal.

### Exit gate

No behavior-affecting value lives only in code.

## Phase 3 - Failure Semantics And Fallback Ledger

### Goal

Finish the silent fallback purge as a domain-wide executable policy.

### Actions

1. Create a failure taxonomy: `BLOCK`, `FALLBACK`, `SKIP_ROW`, `DEGRADED_OBSERVABILITY`, `FATAL_STARTUP`, `LEGACY_DIAGNOSTIC_ONLY`.
2. Replace remaining broad catch-and-continue paths in active or trainable surfaces with typed outcomes and alert/event counters.
3. Require every skipped row to carry machine-readable reason codes.
4. Make `WALReplayer` strict by default for training: malformed JSON, handler failure, and missing causal time fail the replay unless `diagnostic_legacy` mode is set.
5. Add tests that deliberately trigger I/O failure, malformed JSON, handler exception, bridge timeout, baseline artifact mismatch, and telemetry flush failure.

### Validation

- No hot-path test relies on `except Exception` swallowing behavior.
- Failure reason counters are asserted in tests.
- `py_compile` passes for all touched runtime modules.
- VS Code diagnostics show no errors for touched files.

### Exit gate

The system may continue operating in shadow mode after non-critical observability failure, but it must say exactly what degraded and what data was dropped.

## Phase 4 - Hot-Path Coverage And Static Type Closure

### Goal

Achieve the stated Definition of Done where it matters: the active Stage 0.3 path.

### Hot path scope

- `main.py`
- `logic/ingest/state_aggregator_v2.py`
- `logic/brain/baseline_inference.py`
- `logic/gates/shadow.py`
- `decision_making.authority_bridge` Neocortex integration
- Shadow decision WAL append path

### Actions

1. Add branch coverage for startup gate pass/fail, event tap normalization, state snapshot production, baseline threshold/class validation, authority timeout, shadow FALLBACK, and WAL append failure.
2. Install or vendor the static-check dependency needed for the agreed mypy command, or change the DoD to a tool that exists in the project environment. Do not claim mypy closure when mypy is absent.
3. Keep `dict[str, Any]` only at JSON ingress/egress boundaries. Convert internal contracts to typed dataclasses or Pydantic models.
4. Add a coverage gate scoped to hot-path modules, not legacy/PPO/experiments.

### Validation

- `python -m pytest <hot-path-test-set> --cov=<hot-path-modules> --cov-fail-under=100`.
- `python -m mypy apps/reference/domains/neocortex/main.py <hot-path-modules>` with 0 errors, after mypy availability is proven.
- A report explicitly lists excluded legacy/offline modules.

### Exit gate

The active shadow runtime is fully covered and statically clean within declared boundaries.

## Phase 5 - Adapter Quarantine, Then Surgical Extraction

### Goal

Reduce `adapter.py` risk without preserving accidental legacy behavior as a requirement.

### What breaks if we split `adapter.py`

The likely breakage is acceptable if planned:

- Legacy tests that instantiate `NeocortexAdapter` directly will fail until moved to service-level tests or a thin compatibility facade.
- `WalTailer`, `WALReplayer`, and `MultiTailer` examples/documentation assume a single `adapter.handle_features` handler. They need a new handler interface such as `FeatureIngestionService.handle_feature_event`.
- Oracle wiring tests depend on adapter-owned reward settlement and feature extraction. Those should move to an `OracleSettlementService` with fixture-level tests.
- Backpressure and telemetry tests depend on adapter private fields. They should test a bounded queue/sink contract, not private monolith state.
- Persistence/checkpoint tests assume adapter owns normalizer and checkpoint metadata. That should become `PreprocessingStateService` plus `CheckpointMetadataService`.

What does not materially break:

- Stage 0.3 hot path should not break if Phase 0 import-boundary test is true.
- Current shadow baseline authority should not depend on `NeocortexAdapter`.
- Old WAL diagnostics can continue through a compatibility facade if needed.

### Extraction order

1. Extract pure functions first: event timestamp normalization, feature-map extraction, shadow-intent serialization, objective-family classification.
2. Extract sinks second: telemetry CSV sink, shadow JSONL sink, alert emitter. Each sink gets bounded queue semantics and explicit drop counters.
3. Extract stateful training/replay pieces third: normalizer state, dataset admission, oracle settlement, policy sample buffering.
4. Leave a thin `NeocortexAdapter` facade only for legacy tests and offline replay commands.
5. Delete or archive the facade only after all direct adapter tests are migrated or intentionally marked legacy.

### Validation

- Every extraction has before/after golden tests.
- Compatibility facade is covered only by smoke tests, not treated as the new authority.
- No private-field assertions remain for the new services.

### Exit gate

The monolith is gone because behavior moved behind tested contracts, not because code was mechanically split into more files.

## Phase 6 - Replay/WAL Compatibility Matrix

### Goal

Keep old data readable while preventing old data from poisoning training.

### Actions

1. Define WAL format versions and accepted aliases: `event_ts_ms`, `timestamp_ms`, `timestamp`, `ts_ms`, `ts`, `rid`, `lifecycle_id`, `idempotent_key`, `reservation_id`, `corr_id`, `trade_id`.
2. Build a compatibility matrix:
   - old WAL with causal timestamp: trainable if other gates pass.
   - old WAL without causal timestamp: diagnostics-only.
   - old order lifecycle with alias drift: resolvable only if alias reconciliation is deterministic and recorded.
   - malformed/incomplete rows: skipped or fail replay according to strictness mode.
3. Require replay reports to count accepted, skipped, diagnostics-only, malformed, non-causal, unresolved-lifecycle, and trainable rows.
4. Add fixture WALs for each case.

### Validation

- Replay strict mode fails on malformed or non-causal trainable rows.
- Diagnostic mode completes but reports the exact exclusions.
- Alias reconciliation tests cover `rid`, `lifecycle_id`, `metadata.idempotent_key`, `reservation_id`, `corr_id`, downstream order IDs, and trade IDs.

### Exit gate

Backward compatibility exists as a transparent import path, not as silent causal trust.

## Phase 7 - Storage, Backpressure, And Lifecycle Hardening

### Goal

Close bottlenecks V1 under-specifies.

### Actions

1. Telemetry CSV sink:
   - prove bounded memory under sustained writes;
   - assert drop counters and flush counters;
   - decide whether observability loss is `DEGRADED_OBSERVABILITY` or `FATAL_STARTUP` per mode.
2. SQLite causal graph:
   - keep out of hot path;
   - enforce single-writer policy;
   - configure timeout and cluster radius explicitly;
   - test lock contention and graph growth limits before reconnecting Dreamer.
3. Async services:
   - every task has a name, owner, shutdown path, timeout, and exception propagation test;
   - no unbounded queue without an explicit overflow policy;
   - no daemon process/thread as a silent lifecycle dependency.
4. Memory growth:
   - assert max sizes for event tasks, pending rows, buffers, normalizer registries, replay state, and graph caches;
   - add soak-style unit/integration tests with synthetic bursts.

### Validation

- Bounded queue tests for CSV telemetry, shadow JSONL, replay handlers, and any future service queue.
- SQLite lock-contention test for `CausalGraph` if Dreamer is re-enabled.
- Async shutdown test proves no pending tasks remain after cancellation.

### Exit gate

The new service architecture cannot leak memory or hide blocked I/O under normal tested failure modes.

## Phase 8 - Delete, Archive, Or Reconnect Legacy RL

### Goal

Stop paying maintenance cost for ambiguous code.

### Actions

1. For every legacy module, choose one final state:
   - `delete`: no supported use remains;
   - `archive`: kept as reference docs/experiments only;
   - `offline_only`: executable but barred from production-shadow import;
   - `reconnect`: must satisfy all contracts above.
2. Reconnect PPO/Dreamer only after:
   - torch-enabled tests pass;
   - checkpoint metadata mismatch is fail-closed;
   - action/confidence semantics are typed;
   - reward formulas and safety constants are config-owned;
   - deterministic seed behavior is proven.
3. Do not let examples or old tests force production API shape.

### Validation

- Import-boundary tests enforce final states.
- Torch-enabled CI lane or local report is required before RL code is called production-ready.
- Deleted/archived modules are removed from hot-path coverage scope.

### Exit gate

There is no zombie code that looks production-shaped but is neither tested nor intentionally offline.

## Final Definition Of Done

The project can call the debt eradicated only when all of these are true:

1. Active Stage 0.3 path has 100% branch coverage for declared hot-path modules.
2. Hot-path mypy command passes with 0 errors in an environment where mypy is installed and version-recorded.
3. Production-shadow startup fails if causal time policy, enforcement mode, config completeness, or shadow telemetry contract is invalid.
4. Non-causal legacy data can be parsed only as diagnostics-only unless a specific causal provenance gate passes.
5. No ML or replay path returns synthetic neutral actions, zero latents, zero rewards, or imputed labels after systemic failure.
6. Every intentional fallback has a typed outcome, reason code, counter, and test.
7. Adapter monolith is either quarantined behind a compatibility facade or replaced by tested services; no hot-path code imports it.
8. Legacy/RL modules are deleted, archived, offline-only, or reconnected with explicit proof.

## Brutally Honest Verdict

V1 is directionally correct but too refactor-first. It risks creating three polished micro-services that still carry the old ambiguity: hidden defaults, unclear data provenance, compatibility with untrusted WAL rows, and async lifecycle gaps.

V2 treats tech debt as failed contracts, not ugly file shape. The adapter split is still needed, but only after the boundary and invariant tests exist. Otherwise the plan does not eradicate debt; it distributes it into smaller boxes with nicer names.

The realistic solo-developer path is: freeze boundary, enforce time/config/fallback gates, cover the active hot path, then extract the adapter in small reversible steps. That is less dramatic than decapitation, but it is much more likely to end with 0 errors, strict causal time, and no silent fallbacks.
