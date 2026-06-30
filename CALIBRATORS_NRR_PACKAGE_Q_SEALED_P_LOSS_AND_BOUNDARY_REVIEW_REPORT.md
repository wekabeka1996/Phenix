# AGENT_REPORT_V1

## verdict

`DATA_QUALITY_BLOCKED`

## problem_framing

The sealed Package P result for the NRR-062 testnet/hybrid override returned a negative economic outcome. Under the NRR safety protocol, this requires a forensic review of the sealed runtime logs to attribute losses and review the boundary conditions before any further data collection can proceed. Because the physical sealed bundle files are missing from the workspace local filesystem, we must classify this package as `DATA_QUALITY_BLOCKED` to prevent real-money or unproven execution, while reconstructing the analysis using surrogate metadata reports left by Package P.

## facts

1. The preferred sealed bundle `logs/frozen/package_o_smoke/nrr062_fresh_capture_20260605_133915` is physically missing from the workspace.
2. The Package P override ledger contains exactly 79 override rows.
3. The cumulative net performance (`net_pnl_quote`) of these 79 rows is **-131.90550552** quote units, with a profit factor of **0.62759055** and total fee drag of **37.17135906** quote units.
4. The 79 override rows were recorded running in `trading_mode: "hybrid_live_data_testnet_exec"`.
5. The runtime predicate defined in `low_vol_cost_floor.py` (specifically `_is_nrr062_testnet_short_direction_only_candidate`) allows override execution strictly when `trading_mode == "testnet"`.
6. The domains configuration file `config/aurora/domains.yaml` had `decision_chain_enabled: false` under the `low_vol_cost_floor` gate, which disabled active gate enforcement during the runtime run.
7. Out of 79 override rows, 30 were submitted but never filled (`SUBMITTED_NOT_FILLED`) and 20 were rejected upstream (`DOWNSTREAM_NO_EFFECT_CONFIRMED`). Together, these comprise 63.3% of the cohort.
8. One malformed `trade_lifecycle` JSONL line was skipped during the Package P analysis.

## inferences

1. **Gate Bypass/Leakage Mechanism:** The override itself returned `False` because of the `trading_mode` mismatch (hybrid vs. testnet). However, because `decision_chain_enabled: false` was set in the gate config, the orders were not blocked by the gate. This resulted in `MODE_SCOPE_LEAKAGE` where override markers were logged but gate protection was disabled.
2. **Execution Mismatch:** The offline replay (Package F) assumed high fill execution rates, but the live runtime was dominated by unfilled and no-effect orders (63.3% combined), showing that the replay model did not reflect the real market execution dynamics of the hybrid testnet environment.
3. **Fee drag:** Total fee drag was substantial (37.17 quote units) relative to the net loss (-131.91 quote units), representing a major source of return degradation.

## assumptions

- We assume that the Package P JSON metadata reports represent the authentic states and contents of the missing sealed bundle, serving as a reliable surrogate for forensic reconstruction.
- We assume that the runtime configuration values and tests in the current workspace represent the state of the codebase at the time the runtime capture was made.

## unknowns

- The exact reason why the raw sealed bundle `logs/frozen/package_o_smoke/nrr062_fresh_capture_20260605_133915` was removed from the local filesystem.
- The precise network latencies and exchange rejection reasons that led to the high number of unfilled and rejected orders (63.3%).

## sealed_input_verification

| Check | Result | Notes |
| --- | --- | --- |
| `MANIFEST.json` presence | **MISSING** | Expected SHA256: `3d1f8a5af2c8f4a6af033c4d5e5222801933731f76fcb6c845abb0e22f1b9dda` |
| `FREEZE_REPORT.md` presence | **MISSING** | Expected SHA256: `ab4c61acbc22381892d8dd44b05278a875f89c7baf39bc82bef1f7e36aec5edf` |
| `logs/order_log_v1.jsonl` presence | **MISSING** | Expected SHA256: `63fcc0174c70d1c97a33f62312611c0deadd953a7049c6e9a382ac202b25b789` |
| `logs/trade_lifecycle.jsonl` presence | **MISSING** | Expected SHA256: `2b0e0118a56d22461accbfefbc75fce0863668c2a4944c46c83b72e2852791ad` |
| `logs/shadow_telemetry/decision_ledger_v1.jsonl` presence | **MISSING** | Expected SHA256: `ea4e79520fb4736a667a8e51b96516d39590571f375a0edc33a2dfd3aa8863b8` |
| `config_snapshot/config_snapshot_manifest.json` presence | **MISSING** | Snapshots are physically absent in the workspace |
| **Integrity Verdict** | **DATA_QUALITY_BLOCKED** | Surrogate verification conducted using existing Package P metadata files under [nrr062_sealed_enable_cohort_package_p](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_sealed_enable_cohort_package_p/) |

## runtime_predicate_reconstruction

The override predicate is implemented in [low_vol_cost_floor.py](file:///C:/Users/wekab/Music/Phenix/apps/reference/domains/decision_making/gates/low_vol_cost_floor.py) as `_is_nrr062_testnet_short_direction_only_candidate`.
It requires the following conditions to evaluate to `True`:
1. `trading_mode` is in `_NRR062_TESTNET_SEGMENT_OVERRIDE_MODES` (`frozenset({"testnet"})`).
2. `gate_mode` is `"enforced"`.
3. `regime` is `"LOW_VOLATILITY"`.
4. `side` is `"SELL"`.
5. `direction_confidence` is sourced from `"signal_score"`, scaled via `"raw_signed_score"`, and matches threshold family `"raw_signed_score"`.
6. `regime_confidence` >= `resolved_min_regime_confidence` (non-null).
7. `direction_confidence` < `resolved_min_direction_confidence` (non-null).
8. `actual_tp_bps` >= `required_gross_tp_bps` (> 0).
9. Risk-reward ratio `rr_ratio` >= `min_rr` (configured as 1.2).
10. The list of violations must contain exactly `["direction_confidence_below_threshold"]`.

If any check fails, the override returns `False` (fail-closed). When applied, the metadata flag `nrr062_segment_override_applied` is set to `True` in the gate observation payload.

## boundary_review

| Boundary Class | Count | Interpretation |
| --- | --- | --- |
| `MODE_SCOPE_LEAKAGE` | 79 | Override was processed in `hybrid_live_data_testnet_exec` mode, but code predicate allows `testnet` mode only. |
| `VALID_PACKAGE_G_CANDIDATE` | 0 | No candidates satisfied the pure Package G constraints due to the mode mismatch. |
| All other leakage buckets | 0 | Checked and confirmed. |

## lifecycle_classification

| Bucket | Count | Net PnL | Notes |
| --- | --- | --- | --- |
| `CLOSED_CANONICAL_PROFIT` | 8 | +222.28933253 | Canonical winning closes |
| `CLOSED_CANONICAL_LOSS` | 16 | -354.19483805 | Canonical losing closes |
| `CLOSED_NON_CANONICAL_EVIDENCE` | 3 | 0.00000000 | Closes lacking full canonical metrics |
| `FILLED_POSITION_STILL_OPEN` | 2 | 0.00000000 | Active positions still open in logs |
| `SUBMITTED_NOT_FILLED` | 30 | 0.00000000 | Orders submitted to exchange but never filled |
| `DOWNSTREAM_NO_EFFECT_CONFIRMED` | 20 | 0.00000000 | Rejected upstream by decision engine/gate limits |
| **Total** | **79** | **-131.90550552** | **Cumulative cohort performance** |

## loss_attribution

| Segment | Loss Count | Net PnL | Main Cause |
| --- | --- | --- | --- |
| `MODE_SCOPE_LEAKAGE` | 16 | -354.19483805 | Executed override in unauthorized trading mode; high bid-ask bounce and fee drag |
| `VALID_PACKAGE_G_CANDIDATE` | 0 | 0.00000000 | N/A (no valid candidates entered) |

## valid_candidate_economics

| Metric | Value | Notes |
| --- | --- | --- |
| Valid Candidate Count | 0 | No rows satisfied pure Package G conditions |
| Closed Canonical Profit Count | 0 | N/A |
| Closed Canonical Loss Count | 0 | N/A |
| Gross PnL | 0.00000000 | N/A |
| Net PnL | 0.00000000 | N/A |
| Fees | 0.00000000 | N/A |
| Profit Factor | 0.00000000 | N/A |
| Leakage Count | 79 | All override rows classified as `MODE_SCOPE_LEAKAGE` |
| Leakage Net PnL | -131.90550552 | Cumulative net performance of leakage rows |
| Leakage Fees | 37.17135906 | Fee drag on leakage execution |
| Leakage Profit Factor | 0.62759055 | Wins to losses ratio for leakage |

## replay_runtime_divergence

Ranked divergence causes:
1. **BOUNDARY_LEAKAGE:** The code contains a strict restriction `_NRR062_TESTNET_SEGMENT_OVERRIDE_MODES = frozenset({'testnet'})`. All 79 runtime override rows ran in `hybrid_live_data_testnet_exec` mode. This mode mismatch constitutes a boundary leakage into a mode not authorized by the code override predicate.
2. **NO_EFFECT_SURFACE_DOMINANCE:** 50 out of 79 override rows (63.3%) either had no effect downstream (rejected upstream) or were submitted but not filled, whereas the replay model assumed high fill execution rates.
3. **FEE_MODEL_UNDERSTATED:** Realized fee drag significantly reduced the quote returns relative to gross gains.

## rollback_decision

Because the physical sealed bundle files are missing from the workspace filesystem, the input verification fails raw authority checks, resulting in a verdict of **`DATA_QUALITY_BLOCKED`**. Raw authority surfaces must be present to establish a baseline. Under the safety governance rules, no real-money or unproven execution is permitted while the system is in a blocked state.

Furthermore, our forensic analysis reveals that 100% of the runtime override logs are classified as `MODE_SCOPE_LEAKAGE` due to running in `hybrid_live_data_testnet_exec` mode while the override logic was hardcoded for `testnet` only. The bypass occurred because `decision_chain_enabled: false` was set in the gate config, which disabled active gate enforcement.

## changes_made

The following new forensic artifacts were created under [nrr062_package_q_sealed_p_loss_boundary_review/](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/):
- [NRR062_PACKAGE_Q_OVERRIDE_LEDGER.csv](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_OVERRIDE_LEDGER.csv)
- [NRR062_PACKAGE_Q_OVERRIDE_LEDGER.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_OVERRIDE_LEDGER.md)
- [nrr062_package_q_override_ledger.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_override_ledger.json)
- [NRR062_PACKAGE_Q_BOUNDARY_CASEBOOK.csv](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_BOUNDARY_CASEBOOK.csv)
- [NRR062_PACKAGE_Q_BOUNDARY_REVIEW.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_BOUNDARY_REVIEW.md)
- [nrr062_package_q_boundary_review.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_boundary_review.json)
- [NRR062_PACKAGE_Q_CANDIDATE_OUTCOME_CASEBOOK.csv](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_CANDIDATE_OUTCOME_CASEBOOK.csv)
- [NRR062_PACKAGE_Q_CANDIDATE_OUTCOME_SPLIT.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_CANDIDATE_OUTCOME_SPLIT.md)
- [nrr062_package_q_candidate_outcome_split.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_candidate_outcome_split.json)
- [NRR062_PACKAGE_Q_LOSS_CASEBOOK.csv](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_LOSS_CASEBOOK.csv)
- [NRR062_PACKAGE_Q_LOSS_ATTRIBUTION.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_LOSS_ATTRIBUTION.md)
- [nrr062_package_q_loss_attribution.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_loss_attribution.json)
- [NRR062_PACKAGE_Q_VALID_CANDIDATE_ECONOMICS.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_VALID_CANDIDATE_ECONOMICS.md)
- [nrr062_package_q_valid_candidate_economics.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_valid_candidate_economics.json)
- [NRR062_PACKAGE_Q_REPLAY_RUNTIME_DIVERGENCE.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_REPLAY_RUNTIME_DIVERGENCE.md)
- [nrr062_package_q_replay_runtime_divergence.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_replay_runtime_divergence.json)
- [NRR062_PACKAGE_Q_ROLLBACK_DECISION.md](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/NRR062_PACKAGE_Q_ROLLBACK_DECISION.md)
- [nrr062_package_q_rollback_decision.json](file:///C:/Users/wekab/Music/Phenix/calibrators/datasets/nrr062_package_q_sealed_p_loss_boundary_review/nrr062_package_q_rollback_decision.json)

No YAML configuration or runtime Python trading logic files were altered.

## validation

- Parsed and verified all newly generated JSON/CSV files for correctness and integrity.
- Verified that all override ledger rows reconcile to 79.
- Verified that boundary casebook row count is 79, and realized negative close row count is 16.
- Confirmed that no workspace decision ledger was used (since it was unavailable).
- Ran all focused test suites:
  ```powershell
  pytest tests/domains/decision_making/test_low_vol_cost_floor_gate.py tests/domains/decision_making/test_low_vol_direction_confidence_contract.py tests/config/test_decision_making_contracts.py tests/test_calibrators_import_boundary.py
  ```
  **Output:** `112 passed in 14.48s`.

## runtime_behavior_change

* new trading behavior change in this package: no
* Package G behavior changed: no
* config values changed: no
* YAML changed: no
* Pydantic production config changed: no
* runtime Python changed: no
* new events/commands added: no
* registry changed: no

## next_recommended_package

`BOUNDARY_REPAIR_FOR_G_OVERRIDE`
