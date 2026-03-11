# Neocortex Production Shadow Roadmap

Date: 2026-03-10
Scope: `apps/reference/domains/neocortex`

## Rollout Order

External unblocker:

- `NEO-UNBLOCK-PYTEST-COLLECT-TUPLE-IMPORT`

Phases:

- P0 Context Freeze / Baseline Verification
- P1 Canonical Time Contract
- P2 Canonical Episode Identity + Fill-Aware Lifecycle
- P3 Reward Contract / Structured Close Feed
- P4 Objective Split
- P5 Sequence Semantics Repair
- P6 Dataset Hygiene Layer
- P7 Performance / Replay Engineering
- P8 Production Shadow Gates
- P9 Path from Production Shadow to 9.5/10 Advisory Architecture

## External Unblocker: `NEO-UNBLOCK-PYTEST-COLLECT-TUPLE-IMPORT`

- Objective: restore repo-level pytest collection so neocortex TDD packages can run.
- Files likely impacted: `apps/reference/config_models.py`
- Tests to write first: none in neocortex; prove `pytest apps/reference/domains/neocortex/tests -q` reaches collection.
- Acceptance criteria: collection no longer fails on missing `Tuple` import.
- Risks: none to neocortex semantics; keep package minimal.
- Rollout notes: do this immediately before or alongside P1.

## P0 Context Freeze / Baseline Verification

- Objective: freeze current behavior, create golden fixtures, and lock source-of-truth expectations.
- Contracts to add / change:
  - declare baseline fixture manifest for replay sources
  - declare contract-manifest consistency check against `domain.yaml`
  - document missing inputs and known external blocker
- Files likely impacted:
  - `apps/reference/domains/neocortex/domain.yaml`
  - `apps/reference/domains/neocortex/tests/fixtures/*`
  - `apps/reference/domains/neocortex/tests/test_config.py`
  - new `apps/reference/domains/neocortex/tests/test_domain_manifest_consistency.py`
- Tests to add first:
  - manifest consistency test
  - baseline fixture loading smoke test
  - replay determinism smoke test with current semantics frozen
- Acceptance criteria:
  - baseline fixtures exist for features, orders, core close logs
  - contract-manifest drift is surfaced by test
  - path resolution behavior is documented and tested
- Risks:
  - baking current broken semantics into fixtures if not tagged clearly
- Rollout notes:
  - mark current fixtures as `legacy_baseline`
  - do not normalize semantics yet

## P1 Canonical Time Contract

- Objective: normalize all ingestion paths to a single causal time field `event_ts_ms`.
- Contracts to add / change:
  - new canonical internal event field `event_ts_ms`
  - forbid replay wallclock as causal time
  - define per-source timestamp extraction rules and missing-time failure behavior
  - define deterministic replay ordering key: `(source_stream, source_offset, event_ts_ms, symbol, event_id)`
- Files likely impacted:
  - `apps/reference/domains/neocortex/config_models.py`
  - `apps/reference/domains/neocortex/config/replay.yaml`
  - `apps/reference/domains/neocortex/domain.yaml`
  - `apps/reference/domains/neocortex/logic/ingest/parsers/feature_parser.py`
  - `apps/reference/domains/neocortex/logic/ingest/parsers/order_parser.py`
  - `apps/reference/domains/neocortex/logic/ingest/parsers/core_parser.py`
  - `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py`
  - `apps/reference/domains/neocortex/transport/adapter.py`
- Tests to add first:
  - `apps/reference/domains/neocortex/tests/test_time_contract.py`
  - extend `test_ingest.py`, `test_multi_ingest.py`, `test_replay.py`
- Acceptance criteria:
  - 100% valid fixture rows normalize to `event_ts_ms`
  - 0 mixed-unit time defects on fixtures
  - stale cleanup uses canonical ms only
  - deterministic replay equality holds with fixed seed
  - missing event time fails closed unless fixture explicitly uses approved fallback field
- Risks:
  - replay ordering changes may alter previous shadow outputs
- Rollout notes:
  - keep legacy timestamp fields read-only during migration
  - emit migration warnings for any source still missing canonical time

## P2 Canonical Episode Identity + Fill-Aware Lifecycle

- Objective: replace symbol-keyed pending episodes with lifecycle-safe assembly.
- Contracts to add / change:
  - lifecycle identity contract: `lifecycle_id`, `trade_id`, `order_id`, `client_order_id`
  - explicit event semantics for `ORDER_PLACED`, `ORDER_FILLED`, `POSITION_OPENED`, `POSITION_CLOSED`, `ORDER_CANCELLED`, `ORDER_REJECTED`
  - fail-closed rule on ambiguous mapping
- Files likely impacted:
  - `apps/reference/domains/neocortex/config_models.py`
  - `apps/reference/domains/neocortex/domain.yaml`
  - `apps/reference/domains/neocortex/logic/ingest/parsers/order_parser.py`
  - `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py`
  - `apps/reference/domains/neocortex/transport/adapter.py`
- Tests to add first:
  - `apps/reference/domains/neocortex/tests/test_lifecycle_contract.py`
  - extend `test_tailer.py`, `test_multi_ingest.py`, `test_integration.py`
- Acceptance criteria:
  - entry anchor is `ORDER_FILLED` or canonical open event
  - partial fills are represented explicitly
  - overlapping same-symbol intents are isolated by lifecycle identity
  - ambiguous close mapping fails closed
- Risks:
  - existing historical logs may lack enough identity fields; migration needs explicit completeness status
- Rollout notes:
  - keep symbol-only path only as rejected legacy behavior, not as fallback training path

## P3 Reward Contract / Structured Close Feed

- Objective: produce a production-grade reward path with completeness semantics.
- Contracts to add / change:
  - dedicated structured close / reward feed preferred
  - canonical reward payload fields:
    - `realized_pnl_gross`
    - `fees`
    - `slippage`
    - `realized_pnl_net`
    - `holding_time_ms`
    - `mae`
    - `mfe`
    - `reward_completeness_status`
  - transitional text parser only as shim
- Files likely impacted:
  - `apps/reference/domains/neocortex/domain.yaml`
  - `apps/reference/domains/neocortex/config_models.py`
  - `apps/reference/domains/neocortex/config/replay.yaml`
  - `apps/reference/domains/neocortex/logic/ingest/parsers/core_parser.py`
  - `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py`
  - `apps/reference/domains/neocortex/tests/test_reward_parsing.py`
- Tests to add first:
  - reward contract fixture suite
  - structured close feed parser tests
  - completeness-status tests
- Acceptance criteria:
  - reward extraction coverage exceeds target threshold on valid close fixtures
  - no reward-bearing episode is created without explicit completeness status
  - parser and structured feed agree on overlapping golden fixtures
- Risks:
  - cross-domain dependency if structured close feed is introduced outside neocortex
- Rollout notes:
  - use parser only until structured feed is available; do not claim parity

## P4 Objective Split

- Objective: separate representation, regime, execution-quality, and policy tasks.
- Contracts to add / change:
  - separate buffers and metrics for:
    - self-supervised representation learning
    - supervised regime head
    - execution-quality / adverse-selection head
    - contextual bandit or offline-RL head on clean executed trajectories only
  - explicit state-vector contract if `ppo.state_dim` is kept
- Files likely impacted:
  - `apps/reference/domains/neocortex/config_models.py`
  - `apps/reference/domains/neocortex/logic/brain/core.py`
  - `apps/reference/domains/neocortex/transport/adapter.py`
  - `apps/reference/domains/neocortex/logic/dreamer.py`
- Tests to add first:
  - `test_objective_split.py`
  - `test_state_vector_contract.py`
  - extend `test_ppo_loop.py`, `test_oracle_wiring.py`
- Acceptance criteria:
  - oracle regime labels can no longer enter execution-policy buffers
  - each task has its own metrics and acceptance thresholds
  - `state_dim` is either wired to explicit features or removed from config
- Risks:
  - temporary metric resets during migration
- Rollout notes:
  - preserve old checkpoints as legacy-only artifacts; do not migrate semantically corrupted models

## P5 Sequence Semantics Repair

- Objective: make recurrent and world-model sequence behavior causally valid.
- Contracts to add / change:
  - explicit `sequence_key`
  - explicit reset rules on lifecycle / symbol boundaries
  - train / inference parity contract
  - no hidden-state leakage across symbols
- Files likely impacted:
  - `apps/reference/domains/neocortex/logic/brain/core.py`
  - `apps/reference/domains/neocortex/PPO/ppo_library_v2/ppo_system/agent.py`
  - `apps/reference/domains/neocortex/PPO/ppo_library_v2/ppo_system/learning/updater.py`
  - `apps/reference/domains/neocortex/PPO/ppo_library_v2/ppo_system/models/actor_critic_lstm.py`
  - `apps/reference/domains/neocortex/logic/dreamer.py`
- Tests to add first:
  - `test_sequence_contract.py`
  - extend `test_brain.py`, `test_ppo_loop.py`, `test_dreamer.py`
- Acceptance criteria:
  - 0 hidden-state leakage across symbols
  - sequence batches preserve episode boundaries
  - training uses real sequence lengths greater than 1 when expected
  - inference and training reset semantics match
- Risks:
  - recurrent performance may regress until datasets are cleaned
- Rollout notes:
  - keep world model offline-only until sequence contract is green

## P6 Dataset Hygiene Layer

- Objective: build canonical, reproducible, contamination-aware datasets.
- Contracts to add / change:
  - contamination quarantine rules
  - dataset manifest with provenance and hash
  - explicit exclusion reasons
  - time-based train / validation / test splits
- Files likely impacted:
  - new dataset builder package under `apps/reference/domains/neocortex/`
  - `apps/reference/domains/neocortex/config/replay.yaml`
  - `apps/reference/domains/neocortex/config/system.yaml`
  - replay ingestion tests
- Tests to add first:
  - `test_dataset_hygiene.py`
  - extend `test_replay.py`
- Acceptance criteria:
  - 0 contaminated rows in canonical train dataset
  - manifests record source files, hashes, exclusion counts, and split windows
  - quarantine catches `MagicMock` and malformed identity rows
- Risks:
  - usable sample count may drop sharply after cleanup
- Rollout notes:
  - sample count reduction is acceptable; silent contamination is not

## P7 Performance / Replay Engineering

- Objective: make shadow mode operationally affordable at real replay volume.
- Contracts to add / change:
  - explicit live-shadow vs offline-replay mode split
  - decimation / downsampling policy for shadow-intent logging
  - batching and async write policy
  - CPU, RAM, and disk budgets in config
- Files likely impacted:
  - `apps/reference/domains/neocortex/config/system.yaml`
  - `apps/reference/domains/neocortex/config/replay.yaml`
  - `apps/reference/domains/neocortex/transport/adapter.py`
  - `apps/reference/domains/neocortex/tests/test_backpressure.py`
- Tests to add first:
  - `test_shadow_hot_path_budget.py`
  - replay throughput harness
  - extend `test_backpressure.py`
- Acceptance criteria:
  - live-shadow path avoids per-row synchronous flush
  - replay path meets configured throughput target
  - RSS and CPU stay inside declared budgets
- Risks:
  - batching can hide ordering bugs if P1 is not already complete
- Rollout notes:
  - do not optimize before data contracts are green

## P8 Production Shadow Gates

- Objective: convert fixed contracts into hard go / no-go gates.
- Contracts to add / change:
  - acceptance-gate registry
  - contract-manifest consistency gate
  - deterministic replay gate
  - red-line list for forbidden capabilities
- Files likely impacted:
  - `apps/reference/domains/neocortex/domain.yaml`
  - `apps/reference/domains/neocortex/tests/*`
  - CI or local gate runner definitions
- Tests to add first:
  - gate runner test suite
  - deterministic replay equality tests
  - manifest consistency tests
- Acceptance criteria:
  - all production shadow gates in `docs/architecture/neocortex_acceptance_gates.md` are green
- Risks:
  - none; this phase is the formal stop/go boundary
- Rollout notes:
  - until P8 is green, domain remains research-only

## P9 Path From Production Shadow To 9.5/10 Advisory Architecture

- Objective: add the missing capabilities required for a true high-grade advisory architecture.
- Contracts to add / change:
  - uncertainty and calibration outputs
  - OOD / drift contracts
  - agent-state-aware input contract
  - offline evaluator contract
  - planner / world-model responsibility split
- Files likely impacted:
  - new evaluation and calibration modules under `apps/reference/domains/neocortex/`
  - `apps/reference/domains/neocortex/config_models.py`
  - `apps/reference/domains/neocortex/logic/brain/core.py`
  - `apps/reference/domains/neocortex/logic/dreamer.py`
- Tests to add first:
  - `test_uncertainty_calibration.py`
  - `test_ood_drift_contract.py`
  - `test_offline_evaluator.py`
- Acceptance criteria:
  - advisory-precondition gates are green
  - no live influence is enabled without passing future advisory gates
- Risks:
  - offline-RL temptation before data volume and behavior-policy logging are sufficient
- Rollout notes:
  - this phase starts only after production shadow is stable, measured, and useful
