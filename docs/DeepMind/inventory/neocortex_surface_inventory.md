# Neocortex Surface Inventory (Machine-Checkable)

> Generated: 2026-04-28
> Contract: Every `.py` file under `apps/reference/domains/neocortex/` appears exactly once.
> Every file has exactly one classification: `hot_path`, `legacy_runtime`, `offline_research`, `tests_only`.

## Classification Table

| Relative Path | Classification |
|---|---|
| `__init__.py` | `hot_path` |
| `config_models.py` | `hot_path` |
| `contracts/__init__.py` | `hot_path` |
| `contracts/causal_time.py` | `hot_path` |
| `contracts/control_decision.py` | `hot_path` |
| `contracts/decision_outcome_ledger.py` | `hot_path` |
| `contracts/failure_taxonomy.py` | `hot_path` |
| `contracts/observation_envelope.py` | `hot_path` |
| `main.py` | `hot_path` |
| `logic/__init__.py` | `hot_path` |
| `logic/telemetry.py` | `offline_research` |
| `logic/datasets/__init__.py` | `hot_path` |
| `logic/datasets/contracts.py` | `hot_path` |
| `logic/datasets/hygiene.py` | `offline_research` |
| `logic/datasets/time_provenance.py` | `hot_path` |
| `logic/gates/__init__.py` | `hot_path` |
| `logic/gates/shadow.py` | `hot_path` |
| `logic/ledger/__init__.py` | `hot_path` |
| `logic/ledger/decision_outcome_ledger.py` | `hot_path` |
| `logic/failure_ledger.py` | `hot_path` |
| `logic/ingest/__init__.py` | `hot_path` |
| `logic/ingest/normalizer.py` | `hot_path` |
| `logic/ingest/observation.py` | `hot_path` |
| `logic/ingest/parser.py` | `hot_path` |
| `logic/ingest/state_aggregator_v2.py` | `hot_path` |
| `logic/brain/__init__.py` | `hot_path` |
| `logic/brain/baseline_inference.py` | `hot_path` |
| `logic/evidence_collection/__init__.py` | `offline_research` |
| `logic/evidence_collection/collector.py` | `offline_research` |
| `logic/evidence_collection/contracts.py` | `offline_research` |
| `logic/evidence_collection/summary.py` | `offline_research` |
| `logic/evidence_collection/writer.py` | `offline_research` |
| `logic/evaluation/__init__.py` | `offline_research` |
| `logic/evaluation/contracts.py` | `offline_research` |
| `logic/evaluation/evaluator.py` | `offline_research` |
| `logic/amygdala/__init__.py` | `legacy_runtime` |
| `logic/amygdala/valuation.py` | `legacy_runtime` |
| `logic/memory/__init__.py` | `legacy_runtime` |
| `logic/memory/buffer.py` | `legacy_runtime` |
| `logic/memory/graph.py` | `legacy_runtime` |
| `logic/reward/__init__.py` | `legacy_runtime` |
| `logic/reward/feature_buffer.py` | `legacy_runtime` |
| `logic/reward/regime_labeler.py` | `legacy_runtime` |
| `logic/reward/reward_calculator.py` | `legacy_runtime` |
| `logic/ingest/parsers/__init__.py` | `hot_path` |
| `logic/ingest/parsers/core_parser.py` | `hot_path` |
| `logic/ingest/parsers/feature_parser.py` | `hot_path` |
| `logic/ingest/parsers/order_parser.py` | `hot_path` |
| `transport/__init__.py` | `hot_path` |
| `transport/authority_bridge.py` | `hot_path` |
| `logic/dreamer.py` | `legacy_runtime` |
| `logic/brain/core.py` | `legacy_runtime` |
| `logic/brain/bridge.py` | `legacy_runtime` |
| `logic/brain/worker.py` | `legacy_runtime` |
| `logic/brain/vae.py` | `legacy_runtime` |
| `logic/brain/world_model.py` | `legacy_runtime` |
| `logic/ingest/tailer.py` | `legacy_runtime` |
| `logic/ingest/multi_tailer.py` | `legacy_runtime` |
| `logic/ingest/wal_replayer.py` | `legacy_runtime` |
| `transport/adapter.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/__init__.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/agent.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/core/dataclasses.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/learning/__init__.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/learning/buffer.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/learning/controllers.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/learning/updater.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/models/__init__.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/models/actor_critic_lstm.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/models/base_model.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/training_loop.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/utils/__init__.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/utils/logging.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/utils/safety.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/ppo_system/utils/seed.py` | `legacy_runtime` |
| `PPO/ppo_library_v2/examples/01_train_cartpole_single.py` | `offline_research` |
| `PPO/ppo_library_v2/examples/02_train_cartpole_vectorized.py` | `offline_research` |
| `experiments/_decision_ledger_baseline.py` | `offline_research` |
| `experiments/00_oracle_pnl_analysis.py` | `offline_research` |
| `experiments/01_state_reconstruction.py` | `offline_research` |
| `experiments/02_action_decoder_simulation.py` | `offline_research` |
| `experiments/03_reward_decomposition_sim.py` | `offline_research` |
| `experiments/04_async_checkpoint_reload.py` | `offline_research` |
| `experiments/05_lstm_memory_isolation_sim.py` | `offline_research` |
| `experiments/06_aurora_sim_env.py` | `offline_research` |
| `experiments/07_vae_latent_space_sim.py` | `offline_research` |
| `experiments/08_decision_ledger_dataset_prep.py` | `offline_research` |
| `experiments/09_dumb_baseline_eval.py` | `offline_research` |
| `tests/test_calibration.py` | `tests_only` |
| `tests/test_dataset_hygiene.py` | `tests_only` |
| `tests/test_disagreement.py` | `tests_only` |
| `tests/test_evaluator_reports.py` | `tests_only` |
| `tests/test_objective_split.py` | `tests_only` |
| `tests/test_performance_contract.py` | `tests_only` |
| `tests/test_provenance.py` | `tests_only` |
| `tests/test_replay_engineering.py` | `tests_only` |
| `tests/test_sequence_semantics.py` | `tests_only` |
| `tests/test_shadow_gates.py` | `tests_only` |

## Counts

| Classification | Count |
|---|---|
| `hot_path` | 31 |
| `legacy_runtime` | 34 |
| `offline_research` | 23 |
| `tests_only` | 10 |
| **Total** | **98** |
