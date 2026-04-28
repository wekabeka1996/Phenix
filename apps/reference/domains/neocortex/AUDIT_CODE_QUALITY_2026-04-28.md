# Neocortex Code Quality Audit - 2026-04-28

## Scope

Audit target: `apps/reference/domains/neocortex`.

This document scores domain logic files that were inspected during the audit. Tests, `__init__.py` files, and PPO example scripts are not scored as domain runtime logic. Some experiment and PPO files were reviewed through static metrics rather than full line-by-line reading; those rows are marked as `metric-only` and should be treated as lower-confidence findings.

No runtime behavior was changed by this audit.

## Scoring Rubric

Score is out of 10. Deductions prioritize operational risk over style.

- 10: Clear contract, typed boundaries, no silent fallback, config-driven business behavior, testable and covered.
- 8-9: Generally healthy, with small contract or coverage gaps.
- 6-7: Usable but has meaningful hardcodes, fallback, async, typing, or formula risks.
- 4-5: High maintenance or runtime risk, especially broad exception handling and implicit defaults.
- 1-3: Not production-ready without isolation or rewrite; likely legacy, placeholder, or unsafe if reconnected.

Deduction categories used below:

- `fallback`: silent fallback, synthetic default, broad catch that hides failure.
- `hardcode`: behavior constant outside YAML/Pydantic SSOT.
- `async`: async or multiprocessing path with weak lifecycle or test coverage.
- `typing`: unclear or overly dynamic contracts.
- `math`: formula, scaling, normalization, or semantic mismatch risk.
- `dead`: legacy, placeholder, unused, or disconnected code that can be dangerous if revived.
- `tests`: missing focused tests for the risky path.

## Executive Verdict

The active Stage 0.3 shadow-baseline path is materially safer than the old Neocortex RL path. The strongest code quality center is: `main.py` + `state_aggregator_v2.py` + `baseline_inference.py` + `gates/shadow.py`.

The largest operational risk is not the current shadow baseline. It is the legacy/RL stack that still exists in the domain: `transport/adapter.py`, `logic/ingest/multi_tailer.py`, `logic/brain/core.py`, `logic/brain/bridge.py`, `logic/dreamer.py`, and legacy tail/replay parsers. These files have many hidden defaults, broad exception handling, async side effects, and business constants that are not fully owned by config.

## Priority Findings

1. `transport/adapter.py` and `logic/ingest/multi_tailer.py` should stay out of production authority until split, fail-closed, and covered by async lifecycle tests. They are too large and carry too many silent behavior paths.
2. `config_models.py` contradicts the local contract comment that business parameters have no defaults. It contains many defaults that must be either moved to YAML or explicitly classified as safe contract defaults.
3. `main.py` is a good Stage 0.3 boundary, but it still has hardcoded authority deadlines and may weaken causal time by accepting captured or frame timestamps as `event_ts_ms`.
4. `logic/brain/core.py` has the highest ML/runtime semantic risk: CPU/import fallbacks, PPO fallback action behavior, config defaults through `getattr`, and warning-only checkpoint metadata mismatch.
5. Legacy parsing and replay files can silently degrade timestamp truth. This is dangerous for ML/RL because causal time is the core Neocortex contract.

## Summary Table

| File | Role | Review depth | Score | Main deductions |
| --- | --- | --- | ---: | --- |
| `main.py` | active Stage 0.3 runtime | direct | 7.0 | hardcode, fallback, causal timestamp ambiguity, broad startup catch |
| `config_models.py` | config schema | direct+metrics | 5.5 | many business defaults, contract drift, permissive legacy compatibility |
| `transport/adapter.py` | legacy/RL orchestrator | direct+metrics | 3.0 | monolith, async, broad exceptions, hidden defaults, weak backpressure |
| `logic/brain/baseline_inference.py` | active baseline scorer | direct | 8.0 | feature sentinel semantics, artifact coupling |
| `logic/ingest/state_aggregator_v2.py` | active state aggregation | direct | 8.0 | timestamp alias ambiguity, context vector contract needs docs/tests |
| `logic/gates/shadow.py` | production-shadow gates | direct | 8.0 | mostly clean, depends on config contract completeness |
| `logic/datasets/contracts.py` | dataset contracts | direct | 8.0 | good separation, limited runtime proof |
| `logic/datasets/hygiene.py` | dataset eligibility | direct | 8.0 | unknown family coercion after exclusion should stay explicit |
| `logic/ingest/normalizer.py` | Welford normalizers | direct | 8.0 | registry concurrency risk |
| `logic/ingest/observation.py` | observation model | direct | 9.0 | minimal; simple and typed |
| `logic/ingest/parser.py` | feature parser | direct | 6.5 | hardcoded clip defaults, missing features to zero, formula contract gaps |
| `logic/ingest/multi_tailer.py` | legacy multi-source tailer | direct+metrics | 3.0 | hardcoded paths/rewards, async complexity, config mutation, stale cleanup TTL |
| `logic/ingest/tailer.py` | legacy WAL tailer | direct+metrics | 4.5 | broad catches, hardcoded polling, legacy verb default |
| `logic/ingest/wal_replayer.py` | legacy replay | direct+metrics | 4.5 | deprecated `wal_glob`, handler errors swallowed, async gaps |
| `logic/ingest/parsers/feature_parser.py` | feature log parser | direct | 6.5 | full-log timestamp may be wallclock, legacy policy risk |
| `logic/ingest/parsers/order_parser.py` | order log parser | direct | 6.0 | UNKNOWN symbol/side fallback, unknown event mapping |
| `logic/ingest/parsers/core_parser.py` | core log parser | direct | 5.5 | regex fragility, legacy close lacks `trade_id` |
| `logic/brain/bridge.py` | async BrainCore bridge | direct+metrics | 5.0 | daemon lifecycle, broad catches, no task timeout, error dict returns |
| `logic/brain/core.py` | VAE/WorldModel/PPO orchestrator | direct+metrics | 4.0 | CPU/import fallback, FLAT fallback, many defaults, metadata warn-only |
| `logic/brain/worker.py` | worker process | direct | 5.0 | broad catches, futures can hang after worker death |
| `logic/brain/vae.py` | VAE model/loss | direct | 7.0 | formula clear, but some `getattr` defaults |
| `logic/brain/world_model.py` | GRU dynamics model | direct | 6.0 | zero action fallback, action_dim currently inert |
| `logic/dreamer.py` | legacy/offline dreamer | direct | 3.0 | placeholder self-transition, raw feature latent fallback, broad catches |
| `logic/telemetry.py` | CSV telemetry | direct+metrics | 6.5 | hardcoded rotation/pending limits, singleton state |
| `logic/amygdala/valuation.py` | importance scoring | direct | 4.0 | placeholder scoring, hardcoded trace constants |
| `logic/memory/buffer.py` | rolling memory buffer | direct | 8.0 | reproducibility issue from unseeded random sampling |
| `logic/memory/graph.py` | SQLite causal graph | direct | 5.0 | hardcoded radius/timeout, `reward_var` likely M2, O(N) nearest neighbor |
| `logic/reward/regime_labeler.py` | regime oracle labels | direct | 6.5 | final MEAN_REVERSION fallback, formula proof gaps |
| `logic/reward/reward_calculator.py` | regime reward | direct | 7.5 | explicit formulas, invalid action soft fallback |
| `logic/reward/feature_buffer.py` | lookahead buffer | direct | 8.5 | float timestamp contract could be stricter |
| `logic/evaluation/contracts.py` | evaluation contracts | direct | 8.0 | good type contracts, limited runtime proof |
| `logic/evaluation/evaluator.py` | offline reports | partial direct | 6.5 | confidence semantics mismatch risk, calibration assumptions |
| `PPO/ppo_library_v2/ppo_system/agent.py` | PPO facade | direct | 7.0 | hidden state lifecycle depends on caller |
| `PPO/ppo_library_v2/ppo_system/learning/updater.py` | PPO update | direct | 7.5 | good numerical checks, many local constants |
| `PPO/ppo_library_v2/ppo_system/utils/safety.py` | numerical safety | direct | 6.5 | many numeric defaults and fallback ratios need config/rationale |
| `PPO/ppo_library_v2/ppo_system/learning/buffer.py` | trajectory buffer | direct | 8.0 | clear finalize contract, limited integration proof |
| `PPO/ppo_library_v2/ppo_system/models/actor_critic_lstm.py` | PPO model | direct | 7.0 | hardcoded clamp/temp floor, hidden state complexity |
| `PPO/ppo_library_v2/ppo_system/core/dataclasses.py` | PPO data classes | metric-only | 7.0 | needs semantic review before production use |
| `PPO/ppo_library_v2/ppo_system/learning/controllers.py` | PPO controllers | metric-only | 6.0 | numeric hint density, config/rationale unknown |
| `PPO/ppo_library_v2/ppo_system/training_loop.py` | PPO training loop | metric-only | 6.0 | lifecycle and runtime proof unknown |
| `PPO/ppo_library_v2/ppo_system/utils/logging.py` | PPO logging | metric-only | 7.0 | low apparent risk, not fully reviewed |
| `PPO/ppo_library_v2/ppo_system/utils/seed.py` | PPO seeding | metric-only | 8.0 | likely narrow, not fully reviewed |
| `experiments/00_oracle_pnl_analysis.py` | oracle experiment | metrics | 6.0 | large script, reproducibility contract needs tightening |
| `experiments/01_state_reconstruction.py` | state reconstruction experiment | metrics | 5.5 | experiment-only, assumptions not audited |
| `experiments/02_action_decoder_simulation.py` | action decoder sim | metrics | 5.5 | experiment-only, hardcode risk unknown |
| `experiments/03_reward_decomposition_sim.py` | reward sim | metrics | 6.0 | experiment-only, formula proof unknown |
| `experiments/04_async_checkpoint_reload.py` | async checkpoint sim | metrics | 5.5 | async behavior not proven in runtime |
| `experiments/05_lstm_memory_isolation_sim.py` | LSTM sim | metrics | 5.5 | hidden-state assumptions need proof |
| `experiments/06_aurora_sim_env.py` | Aurora sim env | metrics | 5.0 | simulator fidelity and constants need contract |
| `experiments/07_vae_latent_space_sim.py` | VAE latent sim | metrics | 5.5 | experiment-only, statistical assumptions not audited |
| `experiments/08_decision_ledger_dataset_prep.py` | ledger prep | metrics | 6.0 | data provenance and filtering need stronger gates |
| `experiments/09_dumb_baseline_eval.py` | baseline eval | metrics | 5.0 | high default hint count, threshold/eval provenance risk |
| `experiments/_decision_ledger_baseline.py` | ledger baseline | metrics | 5.0 | large script, many defaults, broad exception present |

## Per-File Findings And Proposals

### `main.py` - 7.0/10

Role: active Stage 0.3 shadow-baseline service.

Deductions:
- `hardcode`: log rotation is fixed at `20 * 1024 * 1024` and `backupCount=100`; authority timeout is hardcoded at `50` ms; missing deadline falls back to `now_ms + 50`.
- `fallback`: WAL append catches broad `Exception` and logs instead of making persistence failure an explicit startup/runtime gate.
- `math/contract`: event normalization can synthesize `event_ts_ms` from captured/frame timestamps, which may weaken the causal-time contract.
- `tests`: current tests cover bootstrap and mock event flow, not long-running TCP tap, real WAL append, or restart behavior.

Proposals:
- Move authority timeout, fallback deadline, and log rotation into explicit config.
- For live/shadow production, reject frames that lack causal `event_ts_ms` unless an explicit legacy replay policy is enabled.
- Convert WAL append failure into an observable bounded decision: fail startup if WAL sink is required, or emit a first-class degraded telemetry event if shadow-only logging is allowed to continue.

### `config_models.py` - 5.5/10

Role: Pydantic config schema and loader.

Deductions:
- `fallback/hardcode`: metric scan found 82 field defaults. Some are harmless structural defaults, but several look like business behavior: default run mode, RNG seed, normalization scope, feature price modes, PPO reward/training modes, performance and replay quotas.
- `typing`: some compatibility surfaces remain broad/dynamic for legacy use.
- `contract`: header says no defaults for business parameters, but implementation does not strictly enforce that.

Proposals:
- Split defaults into two explicit groups: contract-safe defaults and business defaults that must come from YAML.
- Add a config-contract test that fails when new business fields use implicit defaults.
- For production shadow, require all behavior-affecting model fields to be present in YAML.

### `transport/adapter.py` - 3.0/10

Role: legacy/RL event-bus adapter and orchestrator.

Deductions:
- `async`: 17 async functions and complex task tracking in one 1862-line file.
- `fallback`: 21 broad exception catches and many `getattr(..., default)` patterns hide runtime contract failures.
- `hardcode`: shadow log rotation, dream thresholds, checkpoint metadata behavior, and runtime mutation are not cleanly config-owned.
- `dead`: this is not the current Stage 0.3 authority path, but it still contains high-impact logic if reconnected.
- `tests`: full-loop async coverage and failure-mode coverage are insufficient for the blast radius.

Proposals:
- Keep this path disconnected from production authority until split into ingestion, dataset admission, training, telemetry, and checkpoint services.
- Replace broad exception paths with typed failure outcomes and explicit telemetry.
- Make backpressure actually enforce a bounded queue policy or rename it to observational telemetry.

### `logic/ingest/multi_tailer.py` - 3.0/10

Role: legacy multi-source async log tailer and RL episode builder.

Deductions:
- `hardcode`: paths, symbol list, batch size defaults, `REWARD_SCALE = 10.0`, rejected/cancelled reward `-0.001`, and stale TTL are hardcoded.
- `fallback`: auto-picks latest backtest order log and mutates config during path resolution.
- `async`: 16 async functions, multiple sources, and state persistence make ordering hard to prove.
- `math`: `tanh(net_pnl / REWARD_SCALE)` needs account/symbol normalization and SSOT ownership.

Proposals:
- Treat as legacy/offline only until reward scale, TTL, symbol universe, and path resolution are config-contract enforced.
- Add deterministic replay tests for ordering, duplicate fills, partial fills, and stale episode cleanup.
- Store replay source decisions in provenance, not as hidden resolver mutation.

### `logic/brain/baseline_inference.py` - 8.0/10

Role: active dumb-baseline artifact loader and scorer.

Deductions:
- `typing/contract`: model feature names and artifact schema are runtime validated but not yet formalized as a versioned schema.
- `math`: categorical sentinel values such as `MISSING` are explicit, but they still affect model semantics and should be part of training metadata.

Proposals:
- Add a formal baseline artifact schema/version contract.
- Require training metadata to record sentinel handling and threshold provenance.

### `logic/ingest/state_aggregator_v2.py` - 8.0/10

Role: active causal state snapshot builder.

Deductions:
- `contract`: timestamp extraction accepts aliases such as `timestamp` and `ts`; safe only if upstream has already normalized them to causal time.
- `hardcode`: context vector dimension and ordering are implicit contract (`CONTEXT_DIM = 11`).
- `tests`: current tests cover core behavior, but vector schema/ordering deserves a contract test.

Proposals:
- Declare state vector layout in a schema/passport and test it against expected feature/context slots.
- Add strict mode that only accepts `event_ts_ms` for production shadow.

### `logic/ingest/parser.py` - 6.5/10

Role: feature payload to `MarketObservation` parser.

Deductions:
- `hardcode`: `_DEFAULT_CLIP_ABS` and dynamic clip defaults encode behavior outside YAML.
- `fallback`: missing/nonfinite values become `0.0`, which can silently hide upstream data quality problems.
- `math`: log price transform and percentage delta formulas need explicit contract and tests against edge cases.

Proposals:
- Move clipping and transform policies to config with fail-closed validation.
- Add a data quality output that distinguishes true zero from imputed zero.
- Add formula tests for zero/negative price, huge spread, and nonfinite inputs.

### `logic/ingest/normalizer.py` - 8.0/10

Role: Welford online normalization.

Deductions:
- `async/threading`: individual normalizer uses locks, but multi-symbol registry access is not obviously locked.
- `tests`: concurrency and persistence-corruption tests should be explicit if shared across threads.

Proposals:
- Lock the symbol registry or document single-thread ownership.
- Add concurrent update/save/load tests for multi-symbol normalizers.

### `logic/brain/bridge.py` - 5.0/10

Role: async client for BrainCore worker process.

Deductions:
- `async`: worker and listener are daemonized; shutdown uses short fixed joins.
- `fallback`: many broad catches. `train_*` methods return error dicts instead of failing closed. Current `encode_async` and `act_async` correctly raise RuntimeError instead of returning synthetic zero/FLAT, which is an improvement.
- `tests`: no proven per-request timeout if worker dies after init; futures can hang.

Proposals:
- Add request-level timeout and worker-death propagation in `_submit`.
- Replace training error dicts with typed failure results or exceptions.
- Add tests for worker crash after initialization and queue backpressure.

### `logic/brain/core.py` - 4.0/10

Role: VAE, WorldModel, PPO orchestration.

Deductions:
- `fallback`: CPU fallback, dynamic PPO import fallback, and `get_action` FLAT fallback can mask degraded ML runtime.
- `hardcode`: many behavior defaults are pulled with `getattr(..., default)` instead of strict config.
- `contract`: checkpoint metadata mismatch warns rather than fail-closes.
- `math`: model corruption thresholds and PPO sanitization policy require runtime contract.

Proposals:
- Make device, PPO availability, and checkpoint compatibility explicit startup gates.
- Remove synthetic FLAT action fallback from any enforcement-capable path.
- Turn checkpoint metadata mismatch into fail-closed for production and explicit degraded mode for offline experiments.

### `logic/brain/worker.py` - 5.0/10

Role: worker process wrapper around BrainCore.

Deductions:
- `fallback`: broad catches around init and task loop.
- `async`: bridge futures can wait indefinitely if worker dies after init.
- `dead`: belongs to legacy/RL path, not active Stage 0.3.

Proposals:
- Send structured fatal messages on worker failure.
- Add heartbeat or process-exit detection in bridge.

### `logic/brain/vae.py` - 7.0/10

Role: VAE model and loss.

Deductions:
- `math`: main VAE formula is clear, but free-bits/auxiliary config defaults require explicit provenance.
- `fallback`: some regime auxiliary values are read through `getattr` defaults despite Pydantic config.

Proposals:
- Require VAE auxiliary settings from config when enabled.
- Add numerical tests for KL/free-bits boundaries and regime aux loss off/on.

### `logic/brain/world_model.py` - 6.0/10

Role: GRU dynamics model.

Deductions:
- `fallback`: action defaults to zero if missing.
- `dead/math`: BrainCore currently initializes with `action_dim=0`, so action-conditioned dynamics are effectively not active.

Proposals:
- Make action conditioning an explicit mode.
- Fail if action-conditioned mode is enabled but action is missing.

### `logic/dreamer.py` - 3.0/10

Role: legacy/offline graph consolidation.

Deductions:
- `dead`: placeholder-like implementation.
- `math`: self-transition `z_next = z` is not a real world model transition.
- `fallback`: raw features are used as latent if no encoder; timestamp can fall back to wallclock time.
- `fallback`: broad per-episode catch hides data problems.

Proposals:
- Keep offline-only and mark experimental.
- Remove or gate raw-feature latent fallback.
- Require causal timestamps and encoder availability for any training artifact.

### `logic/gates/shadow.py` - 8.0/10

Role: production-shadow readiness gates.

Deductions:
- `tests`: gate set is strong, but must stay synchronized with config and domain YAML contracts.
- `contract`: any future config defaults can weaken these gates if not tested.

Proposals:
- Add a single end-to-end startup gate test that loads real YAML and asserts all shadow invariants.
- Keep this as the main guard before any Neocortex runtime starts.

### `logic/datasets/contracts.py` and `logic/datasets/hygiene.py` - 8.0/10

Role: dataset manifest, eligibility, and provenance checks.

Deductions:
- `fallback`: unknown objective family is excluded then coerced toward representation; acceptable only while explicitly recorded.
- `tests`: runtime data corpus proof is separate from unit contract proof.

Proposals:
- Keep unknown-family rows diagnostics-only.
- Add manifest checks for pre-cutover WAL provenance and causal timestamp trust labels.

### `logic/telemetry.py` - 6.5/10

Role: CSV telemetry logger.

Deductions:
- `hardcode`: rotation and pending limits are fixed in code.
- `fallback`: singleton global can hide test/process state.
- `async`: I/O is synchronous; adapter uses `to_thread`, but backpressure behavior is not a strong contract.

Proposals:
- Move rotation and queue/pending limits into config.
- Avoid global singleton in tests or add explicit reset fixture.

### `logic/ingest/tailer.py` - 4.5/10

Role: legacy WAL tailer.

Deductions:
- `fallback`: broad catches in load/save/process/tail paths.
- `hardcode`: poll interval `0.1` and legacy filter default are fixed.
- `dead`: legacy path not active Stage 0.3.

Proposals:
- Keep legacy-only or replace with the newer tap/aggregator path.
- Make poll interval and filter verb explicit config.

### `logic/ingest/wal_replayer.py` - 4.5/10

Role: historical WAL replay.

Deductions:
- `contract`: requires `wal_glob` despite config direction toward `wal_dir`.
- `fallback`: replay file errors and handler errors are logged/debugged without fail-closed propagation.
- `async`: replay ordering and handler failure semantics need tests.

Proposals:
- Align replay input with current config contract.
- Add strict mode where any malformed row or handler error fails the replay.

### `logic/ingest/observation.py` - 9.0/10

Role: immutable market observation model.

Deductions:
- Minimal. It validates `float32` feature vectors and is small.

Proposals:
- Keep as-is. Add shape contract only if multiple feature schemas become active.

### `logic/amygdala/valuation.py` - 4.0/10

Role: importance scoring.

Deductions:
- `dead`: placeholder/TODO quality.
- `hardcode`: trace decay, max trace length, epsilon constants are fixed.
- `math`: importance currently reduces mostly to absolute reward plus epsilon.

Proposals:
- Mark experimental or remove from production wiring.
- Move constants into config and define the intended valuation formula.

### `logic/memory/buffer.py` - 8.0/10

Role: rolling memory buffer.

Deductions:
- `math/reproducibility`: random sampling is not explicitly seeded.

Proposals:
- Inject RNG or seed for deterministic offline experiments.

### `logic/memory/graph.py` - 5.0/10

Role: SQLite causal graph.

Deductions:
- `hardcode`: cluster radius, SQLite timeout, and prune defaults are fixed.
- `math`: `reward_var` appears to store accumulated M2 rather than normalized variance, making the name misleading.
- `performance`: O(N) nearest neighbor is acceptable only for small offline data.

Proposals:
- Rename or normalize `reward_var` semantics.
- Move radius and timeouts to config.
- Add tests for incremental variance math.

### `logic/reward/regime_labeler.py` - 6.5/10

Role: realized regime labeling.

Deductions:
- `fallback`: final default returns MEAN_REVERSION for remaining bars.
- `math`: formula cascade is readable, but regime thresholds need SSOT and boundary tests.

Proposals:
- Replace fallback label with `UNKNOWN` or require explicit catch-all policy.
- Add threshold edge-case tests per regime.

### `logic/reward/reward_calculator.py` - 7.5/10

Role: regime prediction reward.

Deductions:
- `fallback`: invalid action/regime returns `reward_wrong` with warning rather than hard failure.
- `math`: Formula B depends on config matrix quality.

Proposals:
- Fail closed for invalid labels in training-grade mode.
- Keep the legacy matrix as documentation only; require runtime matrix from config.

### `logic/reward/feature_buffer.py` - 8.5/10

Role: per-symbol lookahead buffer.

Deductions:
- `typing`: timestamp is float rather than explicit `event_ts_ms` integer.

Proposals:
- Use an explicit timestamp type or field name in any production replay path.

### `logic/evaluation/contracts.py` and `logic/evaluation/evaluator.py` - 6.5 to 8.0/10

Role: offline evaluation, calibration, disagreement, and advisory readiness reports.

Deductions:
- `math`: calibration is equal-width and confidence must be `[0, 1]`.
- `contract`: legacy PPO path may pass log-probability-like values as confidence, creating semantic mismatch.
- `tests`: report generation tests exist, but runtime consumer semantics need stronger proof.

Proposals:
- Make confidence type explicit per model family: probability, margin, logprob, or score.
- Reject non-probability confidence in calibration/disagreement reports.

### `logic/ingest/parsers/feature_parser.py` - 6.5/10

Role: feature log parser.

Deductions:
- `contract`: pure JSON path fail-closes on missing causal timestamp, but full-log format derives time from log timestamp and marks it causal.
- `fallback`: legacy non-causal policy is necessary but risky.

Proposals:
- In production/training mode, never mark wallclock log timestamps as causal.
- Require provenance field showing whether timestamp is event, bar, ingestion, or file-offset derived.

### `logic/ingest/parsers/order_parser.py` - 6.0/10

Role: order log event parser.

Deductions:
- `fallback`: unknown event type maps to UNKNOWN; missing symbol/side default to UNKNOWN.
- `tests`: needs tests that UNKNOWN rows are not used for training labels.

Proposals:
- Treat UNKNOWN values as diagnostics-only unless a caller explicitly allows them.

### `logic/ingest/parsers/core_parser.py` - 5.5/10

Role: core position/equity parser.

Deductions:
- `typing`: regex-based parsing is fragile.
- `contract`: legacy position-closed text has no trade_id, which conflicts with current resolution contract.

Proposals:
- Prefer structured JSONL sources over regex parsing.
- Mark legacy close rows without trade_id as unresolved diagnostics-only.

### PPO Library Files - 6.0 to 8.0/10

Files:
- `PPO/ppo_library_v2/ppo_system/agent.py` - 7.0
- `PPO/ppo_library_v2/ppo_system/learning/updater.py` - 7.5
- `PPO/ppo_library_v2/ppo_system/utils/safety.py` - 6.5
- `PPO/ppo_library_v2/ppo_system/learning/buffer.py` - 8.0
- `PPO/ppo_library_v2/ppo_system/models/actor_critic_lstm.py` - 7.0
- `PPO/ppo_library_v2/ppo_system/core/dataclasses.py` - 7.0 metric-only
- `PPO/ppo_library_v2/ppo_system/learning/controllers.py` - 6.0 metric-only
- `PPO/ppo_library_v2/ppo_system/training_loop.py` - 6.0 metric-only
- `PPO/ppo_library_v2/ppo_system/utils/logging.py` - 7.0 metric-only
- `PPO/ppo_library_v2/ppo_system/utils/seed.py` - 8.0 metric-only

Deductions:
- `hardcode`: safety constants, ratio clamps, KL limits, logit clamps, temp floors, and gradient thresholds are local defaults.
- `math`: update logic is much healthier than expected because single-sample advantage std uses `correction=0` and degenerate advantages are handled, but constants still need rationale/config if used for real training.
- `async/dead`: this is not active Stage 0.3 production authority.

Proposals:
- Treat PPO as research/offline until all safety constants are config-owned and documented.
- Add deterministic seed and hidden-state reset tests around every training/eval boundary.

### Experiment Scripts - 5.0 to 6.0/10

Files:
- `experiments/00_oracle_pnl_analysis.py` - 6.0
- `experiments/01_state_reconstruction.py` - 5.5
- `experiments/02_action_decoder_simulation.py` - 5.5
- `experiments/03_reward_decomposition_sim.py` - 6.0
- `experiments/04_async_checkpoint_reload.py` - 5.5
- `experiments/05_lstm_memory_isolation_sim.py` - 5.5
- `experiments/06_aurora_sim_env.py` - 5.0
- `experiments/07_vae_latent_space_sim.py` - 5.5
- `experiments/08_decision_ledger_dataset_prep.py` - 6.0
- `experiments/09_dumb_baseline_eval.py` - 5.0
- `experiments/_decision_ledger_baseline.py` - 5.0

Deductions:
- `hardcode`: experiments likely contain thresholds, paths, and assumptions that are acceptable for R&D but not for runtime.
- `fallback`: static metrics showed high default-hint density in baseline/eval scripts.
- `tests`: experiments are not production-tested and should not be cited as runtime proof.

Proposals:
- Promote only the stable outputs into versioned artifacts: dataset manifest, model artifact schema, threshold provenance, and evaluation report.
- Add command-line args or config for all thresholds/paths before repeating experiments as evidence.
- Mark all generated rows with artifact version, source WAL cutover trust, and causal timestamp policy.

## Files Not Scored

The following categories were intentionally not scored:

- `__init__.py` files: no domain logic.
- `apps/reference/domains/neocortex/tests/*` and `tests/**/neocortex/*`: tests are coverage evidence, not domain runtime logic.
- `PPO/ppo_library_v2/examples/*`: examples, not domain runtime logic.
- Documentation files: useful context, but not executable domain logic.

## Cross-Cutting Recommendations

### P0 - before any legacy/RL reconnection

1. Keep `transport/adapter.py`, `multi_tailer.py`, `BrainCore`, `BrainBridge`, and `dreamer.py` outside live authority.
2. Enforce causal time strictly: no captured/wallclock/file-offset timestamp may become `event_ts_ms` without explicit legacy provenance.
3. Remove silent action fallbacks from enforcement-capable ML paths. A model failure should be an explicit BLOCK/FALLBACK/degraded result, not a synthetic safe-looking action.
4. Classify every config default in `config_models.py` as either safe structural default or forbidden business default.

### P1 - focused hardening

1. Split `transport/adapter.py` into smaller components with typed boundaries.
2. Add async lifecycle tests for bridge startup, worker death, shutdown, queue timeout, and handler failure.
3. Move hardcoded rotations, TTLs, reward scales, clip limits, timeouts, and PPO safety constants into YAML/Pydantic contracts.
4. Add provenance labels to every dataset row: causal timestamp source, WAL trust cutover, objective family, trainability, and diagnostics-only status.

### P2 - research hygiene

1. Keep experiment scripts reproducible with CLI/config inputs and output manifests.
2. Separate research defaults from runtime defaults.
3. Add formula passports for parser transforms, reward scales, regime labels, graph variance, and PPO safety constants.

## FACTS

- Active Stage 0.3 startup currently uses `main.py`, `NeocortexStateAggregator`, `BaselineController`, `NeocortexAuthorityBridge`, and `ShadowGateEvaluator`.
- Legacy/RL code remains present in the domain and contains many async and multiprocessing surfaces.
- Static metrics found major hotspots: `transport/adapter.py` has 1862 lines and 21 broad exception catches; `multi_tailer.py` has 1427 lines and 16 async functions; `config_models.py` has many field defaults; `brain/core.py` has many `getattr(..., default)` hints.
- Current `BrainBridge.encode_async` and `BrainBridge.act_async` raise RuntimeError on failure instead of returning synthetic zero/FLAT values.

## INFERENCES

- The active Stage 0.3 shadow-baseline slice is acceptable for continued shadow use with known hardening gaps.
- The legacy/RL slice is not acceptable for live enforcement without a dedicated fail-closed hardening package.
- The biggest root pattern is not one bug; it is old research code crossing into runtime-shaped code without strict config, provenance, and async lifecycle contracts.

## UNKNOWNS

- This audit did not run full tests or live runtime replay.
- Some PPO and experiment files were scored from metrics plus architectural context rather than complete manual line review.
- No claim is made that all domain behavior is safe in production; this document is a code-quality and risk audit, not runtime certification.

## Minimal Safe Verdict

Proceed with Stage 0.3 shadow-baseline only. Do not reconnect legacy/RL Neocortex authority or training loops to live decision control until the P0 items above are closed with tests and runtime-facing observability.
