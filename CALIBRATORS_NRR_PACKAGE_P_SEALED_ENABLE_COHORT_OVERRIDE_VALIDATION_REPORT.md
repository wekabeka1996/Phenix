# CALIBRATORS_NRR_PACKAGE_P_SEALED_ENABLE_COHORT_OVERRIDE_VALIDATION_REPORT

Bundle root: logs/frozen/package_o_smoke/nrr062_fresh_capture_20260605_133915
Analysis scope: sealed_bundle_only
Bundle complete: True
Override rows: 79
Accepted low-vol rows: 79
Boundary verdict: BOUNDARY_REVIEW_REQUIRED
Economics verdict: ENABLE_RUNTIME_NOT_YET_POSITIVE_CONTINUE_TESTNET_COLLECTION_ONLY
Comparison verdict: P_REMAINS_ENABLE_COHORT_ALIGNED_WITH_H_L_N_HISTORY
Replay vs runtime verdict: ENABLE_RUNTIME_NOT_YET_DIRECTIONALLY_ALIGNED_WITH_POSITIVE_REPLAY

## Key Findings
The sealed bundle contains 79 DecisionMaking override rows with 79 accepted low-vol rows and 4884 linked shadow rows.
The decision ledger inside the bundle is complete for the analysis surface, with terminal statuses {"EXECUTED_AND_CLOSED": 11, "INVALID_FOR_DATASET": 45, "REJECTED_UPSTREAM": 22}.
The bundle config snapshot keeps the sidecar block aligned with the accepted enable baseline: True.
The sealed runtime remains net negative at -131.90550552 quote units across resolved closes when compared against the replay candidate baseline of 391.0476869715.

## Artifacts
- [Inventory](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_SEALED_BUNDLE_INVENTORY.md)
- [Override Ledger](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_OVERRIDE_LEDGER.md)
- [Lifecycle Classification](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_LIFECYCLE_CLASSIFICATION.md)
- [Boundary Audit](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_BOUNDARY_AUDIT.md)
- [Enable Cohort Economics](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_ENABLE_COHORT_ECONOMICS.md)
- [H/L/N/P Comparison](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_H_L_N_P_COMPARISON.md)
- [Shadow Appendix](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_SHADOW_APPENDIX.md)
- [Replay vs Runtime](calibrators/datasets/nrr062_sealed_enable_cohort_package_p/NRR062_PACKAGE_P_REPLAY_VS_RUNTIME.md)

## Residual Risk
One malformed trade_lifecycle JSONL line was skipped during analysis; it did not prevent the sealed bundle from supporting a complete package P report.
