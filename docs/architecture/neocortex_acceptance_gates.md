# Neocortex Acceptance Gates

Date: 2026-03-10
Scope: `apps/reference/domains/neocortex`

## Production Shadow Gates

| Gate ID | Gate | Threshold / rule | Evidence / test package | Red line if failed |
| --- | --- | --- | --- | --- |
| G-SHADOW-01 | Canonical time normalization | 100% of valid fixtures normalize to `event_ts_ms` | `test_time_contract.py` | No production shadow claim |
| G-SHADOW-02 | Mixed-unit time defects | 0 on feature, order, and core fixtures | `test_time_contract.py`, `test_multi_ingest.py` | Replay invalid |
| G-SHADOW-03 | Replay wallclock usage | 0 causal uses of `time.time()` for event ordering / idempotency | code search + tests | Deterministic replay invalid |
| G-SHADOW-04 | Lifecycle ambiguity handling | 100% ambiguous mappings fail closed | `test_lifecycle_contract.py` | Training data invalid |
| G-SHADOW-05 | Partial fill support | All partial-fill fixtures assemble correctly | `test_lifecycle_contract.py` | Execution-quality claims blocked |
| G-SHADOW-06 | Same-symbol overlap isolation | 0 collisions across overlapping same-symbol fixtures | `test_lifecycle_contract.py` | Episode builder invalid |
| G-SHADOW-07 | Reward completeness coverage | >= 95% on valid close fixtures; 100% explicit completeness status | `test_close_feed_contract.py`, `test_reward_parsing.py` | Pnl-aware evaluation blocked |
| G-SHADOW-08 | Objective isolation | 0 regime-oracle samples enter execution-policy buffer | `test_objective_split.py` | PPO metrics invalid |
| G-SHADOW-09 | Hidden-state leakage | 0 leakage across symbol / lifecycle boundaries | `test_sequence_contract.py` | Recurrent claims blocked |
| G-SHADOW-10 | Train / inference parity | sequence reset and length semantics match on golden fixtures | `test_sequence_contract.py`, `test_brain.py` | Sequence models invalid |
| G-SHADOW-11 | Dataset contamination | 0 contaminated rows in canonical train manifest | `test_dataset_hygiene.py` | Dataset use blocked |
| G-SHADOW-12 | Provenance and splits | 100% datasets have manifest, source hashes, time split windows | `test_dataset_hygiene.py` | Offline evaluation blocked |
| G-SHADOW-13 | Deterministic replay | two fixed-seed replays produce equal outputs on golden fixtures | `test_replay.py` | Shadow diagnostics not trustworthy |
| G-SHADOW-14 | Contract-manifest consistency | 100% emitted events declared in `domain.yaml` | `test_domain_manifest_consistency.py` | Domain cannot be called production shadow |
| G-SHADOW-15 | Resource budget | live-shadow p95 observer overhead <= 2 ms per event on baseline hardware; replay throughput >= 50,000 feature rows/hour; RSS <= 1.5 GB; no per-row sync flush | `test_shadow_hot_path_budget.py`, perf harness | Operational rollout blocked |

## Advisory-Precondition Gates

| Gate ID | Gate | Threshold / rule | Evidence / test package | Red line if failed |
| --- | --- | --- | --- | --- |
| G-ADV-01 | Agent-state-aware inputs | explicit contract for inventory, exposure, margin, risk-gate state, action history | `test_agent_state_features.py` | No advisory decision context |
| G-ADV-02 | Calibration quality | regime / execution heads ECE <= 0.05 on holdout | `test_uncertainty_calibration.py` | No confidence-bearing advice |
| G-ADV-03 | Reliability reporting | reliability curves and calibration report generated each evaluation run | offline evaluator tests | Advisory confidence not publishable |
| G-ADV-04 | OOD detection | stable OOD score and alert threshold validated on held-out drift fixtures | `test_ood_drift_contract.py` | No advisory on unseen regimes |
| G-ADV-05 | Execution-quality labeling | clean labels for slippage / cancel / reject / adverse selection coverage >= 95% of valid executed trajectories | evaluator + dataset tests | No execution advisor |
| G-ADV-06 | Offline evaluator completeness | evaluator reports representation, calibration, disagreement, reward coverage, and drift metrics in one run | `test_offline_evaluator.py` | Advisory promotion blocked |

## Future Offline-RL Gates

| Gate ID | Gate | Threshold / rule | Evidence / test package | Red line if failed |
| --- | --- | --- | --- | --- |
| G-RL-01 | Clean executed trajectory volume | sufficient complete trajectories with canonical lifecycle and reward contracts; no ambiguous joins | dataset manifests | No offline RL research |
| G-RL-02 | Behavior-policy logging | action propensities or equivalent support metadata available for every RL sample | dataset / evaluator tests | Off-policy value estimates not credible |
| G-RL-03 | Reward completeness | 100% RL samples have explicit reward completeness and exclusion reason if dropped | reward + dataset tests | RL labels invalid |
| G-RL-04 | Support coverage | candidate actions remain within observed support or conservative algorithm proves otherwise | offline evaluator | No policy optimization |
| G-RL-05 | Conservative algorithm choice | use pessimistic offline RL or contextual bandit methods only after support checks | design review + tests | No aggressive RL rollout |
| G-RL-06 | Counterfactual safety | off-policy evaluation and uncertainty bounds documented per run | evaluator reports | No progression to modulation advisor |

## Explicit Red Lines

Until production shadow gates are green, the following are forbidden:

- live policy modulation,
- live sizing changes,
- live execution parameter changes,
- reward-driven online learning,
- labeling current PPO as a production RL brain.

Until advisory-precondition gates are green, the following are forbidden:

- any confidence-bearing advisory consumed by Aurora,
- any execution-quality recommendation that affects routing or sizing,
- any advisory surface that hides OOD / uncertainty state.

Until future offline-RL gates are green, the following are forbidden:

- offline RL training on symbol-keyed or ambiguous trajectories,
- RL on parser-inferred rewards without completeness semantics,
- any direct path from `neocortex` policy output to Aurora execution logic.

## Enforcement Posture

- Default posture: fail closed.
- Missing contract field: reject or quarantine.
- Ambiguous lifecycle: reject.
- Missing reward completeness: reject from training.
- OOD / uncertainty beyond threshold: advisory suppressed.
