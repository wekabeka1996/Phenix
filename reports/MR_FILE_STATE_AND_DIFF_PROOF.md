# MR File State and Diff Proof

## Scope and method

This document records repository truth using:

1. direct file-system inspection of current source files
2. earlier local branch-status evidence already gathered before the user disallowed further git interaction
3. direct source-code and test inspection

No new git commands were executed after the user restriction.

## Exact files audited

- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/normalized_reject_reasons.py`
- `apps/reference/domains/feature_engineering/feature_engineering.py`
- `apps/reference/domains/feature_engineering/types.py`
- `apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json`
- `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/strategies.yaml`
- `config/aurora/domains.yaml`
- `config/docs/mean_reversion_state_machine_passport.md`
- `tests/config/test_mr_microstructure_veto_config.py`
- `tests/domains/decision_making/test_mr_microstructure_veto.py`
- `tests/config/test_mr_directional_bias_config.py`
- `tests/domains/decision_making/test_mr_directional_bias.py`
- `reports/REPORT_PACK_1_MR_V1_CONTRACTS_CONFIG.md`
- `reports/REPORT_PACK_2_MR_V1_HANDLER_OVERLAY.md`
- `reports/REPORT_PACK_3_MR_V1_TESTS_VALIDATION.md`
- `reports/REPORT_PACK_4_MR_V2_CONTRACTS_CONFIG.md`
- `reports/REPORT_PACK_5_MR_V2_RUNTIME_INTEGRATION.md`
- `reports/REPORT_PACK_6_MR_V2_TESTS_VALIDATION.md`
- `reports/REPORT_PACK_7_DOCS_PASSPORT_FORENSIC_SYNC.md`
- `reports/REPORT_PACK_R1.md`
- `reports/REPORT_PACK_R2.md`
- `reports/REPORT_PACK_R3.md`
- `reports/REPORT_PACK_R4.md`
- `reports/REPORT_IMPLEMENTED_MR_VECTORS_V1_V2.md`

## Earlier repository snapshot already available to this audit

### Working-tree snapshot

Earlier local status evidence showed the following relevant MR surfaces as modified or untracked at audit time:

#### Modified tracked files

- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/docs/mean_reversion_state_machine_passport.md`
- `tests/config/test_mr_microstructure_veto_config.py`
- `tests/domains/decision_making/test_mr_microstructure_veto.py`

#### Untracked working-tree files

- `reports/REPORT_IMPLEMENTED_MR_VECTORS_V1_V2.md`
- `reports/REPORT_PACK_5_MR_V2_RUNTIME_INTEGRATION.md`
- `reports/REPORT_PACK_6_MR_V2_TESTS_VALIDATION.md`
- `reports/REPORT_PACK_7_DOCS_PASSPORT_FORENSIC_SYNC.md`
- `reports/REPORT_PACK_R1.md`
- `reports/REPORT_PACK_R2.md`
- `reports/REPORT_PACK_R3.md`
- `reports/REPORT_PACK_R4.md`
- `tests/domains/decision_making/test_mr_directional_bias.py`

### Earlier branch-vs-main snapshot

An earlier branch-vs-main snapshot already showed committed proof for these MR-related surfaces:

#### Modified relative to merge-base

- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `config/aurora/strategies/mean_reversion.yaml`
- `config/docs/mean_reversion_state_machine_passport.md`

#### Added relative to merge-base

- `reports/REPORT_PACK_1_MR_V1_CONTRACTS_CONFIG.md`
- `reports/REPORT_PACK_2_MR_V1_HANDLER_OVERLAY.md`
- `reports/REPORT_PACK_3_MR_V1_TESTS_VALIDATION.md`
- `reports/REPORT_PACK_4_MR_V2_CONTRACTS_CONFIG.md`
- `tests/config/test_mr_directional_bias_config.py`
- `tests/config/test_mr_microstructure_veto_config.py`
- `tests/domains/decision_making/test_mr_microstructure_veto.py`

## File-level proof of claimed changes

| Surface | Claimed change | Actual proof on disk | Proof class |
|---|---|---|---|
| `config_models.py` | add V1/V2 config models | Present | Strong |
| `mean_reversion_handler.py` | add V1/V2 handler logic | Present | Strong |
| `mean_reversion_strategy.py` | consume split thresholds | Present | Strong |
| `mean_reversion.yaml` | add V1/V2 YAML blocks | Present | Strong |
| passport | add V1/V2 sections | Present | Strong |
| V1 config tests | add strict-contract tests | Present | Strong |
| V1 behavior tests | add helper-level veto tests | Present | Strong |
| V2 config tests | add strict-contract tests | Present | Strong |
| V2 behavior tests | add helper-level modulation tests | Present | Medium: working-tree proof only at audit time |
| PACK-1..4 reports | describe early package set | Present | Mixed: some content now stale |
| PACK-5..7 and R1..R4 reports | describe later integration/remediation | Present | Medium: working-tree proof only at audit time |

## What is proven without relying on narrative reports

1. V1 exists in code.
2. V2 exists in code.
3. Both YAML blocks exist.
4. Both config models exist and are strict.
5. `missing_policy="skip"` is not allowed in the active config model.
6. The strategy now supports split long/short thresholds.
7. `NRR-060` exists.
8. The current passport contains dedicated V1 and V2 sections.

## What has only partial proof

1. R1-R4 package narratives have source-file proof on disk, but several were only working-tree artifacts at audit time.
2. V2 behavioral test file existed on disk, but it was not part of the earlier committed branch snapshot.
3. Several report conclusions are contradicted by current code or current test inventory.

## Trusted vs untrusted report claims

| Report claim | Status | Reason |
|---|---|---|
| V1 and V2 code changes exist | Trusted | Directly confirmed in source files |
| `MRMicrostructureVetoConfig` and `MRDirectionalBiasConfig` exist | Trusted | Directly confirmed |
| `missing_policy="skip"` removed from active contract | Trusted | Directly confirmed in code and tests |
| `NRR-060` exists | Trusted | Directly confirmed |
| V2 uses simplified symmetric contract | Trusted | Directly confirmed |
| `REPORT_PACK_1`: `missing_policy` still accepts `skip` | Untrusted | Contradicted by current code |
| `REPORT_PACK_1`: price reaction is available in CMD payload | Untrusted | Contradicted by current FE -> CMD shape |
| `REPORT_PACK_3`: skip test still exists and 15 tests prove package | Untrusted | Current file has different tests and count |
| `REPORT_PACK_4`: positive funding makes LONG easier, SHORT stricter | Untrusted | Contradicted by strategy trigger inequalities |
| `REPORT_PACK_5`: FE likely does not populate funding rate | Downgraded | Code can populate it; current defaults disable futures config instead |
| `REPORT_PACK_6`: 13 tests prove V2 behavior | Untrusted | Current file has 19 tests and some claims are overstated |
| `REPORT_PACK_R3`: cleanup proven by test | Downgraded | Current cleanup test simulates manual clearing, not actual finally execution |
| `REPORT_PACK_R4`: parity is complete | Untrusted | Current code/docs/reports still drift |

## If git proof were unavailable, which claims would become less trustworthy?

If the earlier branch snapshot had not existed, these claims would need downgrading:

1. whether the surfaces were actually changed relative to prior branch history rather than only edited locally
2. whether the early package reports corresponded to committed branch work
3. whether the remediation packs reflected committed changes or only working-tree drafts

Even without git, the implementation itself would still be proven by current file-state inspection. What would weaken is change-history confidence, not source existence.

## Final repository-truth conclusion

The code changes are real and present in the repository workspace. The main uncertainty is not whether the implementation exists, but how much of the later report narrative is trustworthy. The answer is: only partially. Current source files must be treated as the primary truth source.
