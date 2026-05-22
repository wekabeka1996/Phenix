# AGENT_REPORT_V1

## verdict
RESTORED_ACCEPTED_BASELINE_AND_VALIDATED

## problem_framing
Package L established that the NRR-062 collection line crossed a sidecar authority seam: `execution_position.position_policy_sidecar.mode` was `shadow` in the J snapshot and `enable` in the L snapshot. That drift must be resolved before more override economics are collected because `shadow` suppresses live sidecar close-command authority while `enable` allows the already-bounded soft-close path to emit live close requests. Continuing collection without classifying and reconciling that seam would mix different authority cohorts and would make downstream apples-to-apples economics claims invalid.

## facts
- Pre-action workspace capture was `branch=main`, `commit_sha=34a3b0cce8db834a6550e8087478cf6327d2df9d`.
- Pre-action `git status --short` included `config/aurora/domains.yaml`, `config/aurora/strategies/aurora.yaml`, and many unrelated modified files.
- Pre-action `config/aurora/domains.yaml` sha256 was `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477`.
- Pre-action `config/aurora/strategies/aurora.yaml` sha256 was `67cbe3b6f4263aa6a335813bd6940b8b97294f6a2657c185f5a14e70fa791882`.
- Pre-action current sidecar block had `execution_position.position_policy_sidecar.mode = shadow`, `peak_giveback_close.enabled = false`, `shadow_percent_notional_arm.enabled = true`, and `shadow_fee_aware_arm.enabled = true`.
- Package H bundle root is `logs/frozen/nrr062_fresh_capture_20260515_180927`; its `domains.yaml` snapshot hash is `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5`, `dirty_config_paths=[]`, and the sidecar mode in the snapshot is `enable`.
- Package I bundle root is `logs/frozen/nrr062_fresh_capture_20260516_101448`; its `domains.yaml` snapshot hash is `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477`, `dirty_config_paths` includes `config/aurora/domains.yaml`, and the sidecar mode in the snapshot is `shadow`.
- Package J bundle root is `logs/frozen/nrr062_fresh_capture_20260517_080431`; its `domains.yaml` snapshot hash is `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477`, `dirty_config_paths` includes `config/aurora/domains.yaml`, and the sidecar mode in the snapshot is `shadow`.
- Package L bundle root is `logs/frozen/nrr062_fresh_capture_20260517_210245`; its `domains.yaml` snapshot hash is `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5`, `dirty_config_paths` does not include `config/aurora/domains.yaml`, and the sidecar mode in the snapshot is `enable`.
- Packages H, I, J, and L all point at the same tracked commit `34a3b0cce8db834a6550e8087478cf6327d2df9d` in their snapshot manifests.
- Package J and Package L `config/aurora/strategies/aurora.yaml` snapshot hashes are identical: `e0c451d6cc21c577a8d2d868b378f3d7589ec6ad2d3015d8fb2b0a84a2df3b85`.
- `apps/reference/config/domains/execution_position.py` declares `PositionPolicySidecarMode` as `disable|shadow|enable`; the field is explicit and required.
- `git log -L /position_policy_sidecar:/,+70:config/aurora/domains.yaml` shows committed history switched `mode: shadow -> enable` in commit `a6dc8404f851e9a6d5f29da32cc47019f6ec8109` on 2026-04-13, and no later committed reversion to `shadow` appears in the line history.
- `SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT.md` verdict is `MAINTAIN_ENABLE_WITH_REQUIRED_PATCHES`.
- `reports/PEAK_GIVEBACK_CONTAINMENT_IDENTITY_REPAIR_REPORT.md` states the required target state was `position_policy_sidecar.mode = enable` while preserving `peak_giveback_close.enabled = false` and both shadow arms enabled.
- `reports/PEAK_GIVEBACK_CONFIG_ONLY_CONTAINMENT_REPORT.md` states `execution_position.position_policy_sidecar.mode remains enable`.
- `docs/plans/NEXT_TESTNET_CONFIG_BLUEPRINT_2026-05-16.md` proposes `enable -> shadow`, but the file appears as `??` untracked in the I/J/L snapshot manifests rather than as an applied tracked config change.
- Package L reported that the 24 Package J diagnostics-only rows are downstream no-effect confirmed and that the J-to-L sidecar mode drift contaminates authority-sensitive comparability.
- Action taken in this package changed only `config/aurora/domains.yaml` `execution_position.position_policy_sidecar.mode` from `shadow` to `enable`.
- Post-action `config/aurora/domains.yaml` sha256 is `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5`.
- Post-action `git status --short -- config/aurora/domains.yaml` is empty.
- Generated JSON validation returned `JSON_OK 3`.
- YAML validation returned `YAML_OK config/aurora/domains.yaml`.
- Focused pytest validation returned `80 passed in 20.79s` for the requested package-M slice.

## inferences
- The accepted tracked project baseline for `execution_position.position_policy_sidecar.mode` is `enable`.
- The `shadow` state observed in packages I and J, and again in the pre-action workspace, is accidental dirty-worktree drift to `shadow`, not an accepted baseline migration.
- Package H and Package L form the clean `enable` cohort; packages I and J form the dirty `shadow` cohort.
- NRR-062 economics can still be used, but only with explicit cohort split. Cross-cohort apples-to-apples comparison between `enable` and `shadow` packages is not valid.
- Package L's no-effect classification for the 24 J diagnostics-only rows remains valid because those rows never reached submit, fill, or close evidence; the baseline issue affects authority-sensitive comparability, not the no-effect forensic classification itself.
- The minimal safe action is `RESTORE_PREVIOUS_ACCEPTED_BASELINE`, not `ACCEPT_ENABLE_AS_NEW_BASELINE_AND_SPLIT_COHORTS`, because `enable` was already the accepted baseline before this package started.

## assumptions
- Package-to-bundle mapping is H=`20260515_180927`, I=`20260516_101448`, J=`20260517_080431`, L=`20260517_210245` as referenced by the package reports and runtime artifacts.
- The untracked `NEXT_TESTNET_CONFIG_BLUEPRINT_2026-05-16.md` is a proposal surface only and does not represent a silently accepted runtime baseline.
- Future NRR-062 collection will use the restored current workspace as its config starting point unless an operator intentionally authors and records a different cohort.

## unknowns
- Which operator or local workflow reintroduced the dirty `shadow` copy of `config/aurora/domains.yaml` before packages I and J and in the pre-action workspace.
- Whether anyone intended an undocumented `shadow`-only sidecar experiment for I/J and failed to record the cohort split explicitly.
- Whether the historical I/J `shadow` cohort will require a dedicated rerun later for like-for-like comparison against the restored `enable` cohort.

## j_to_l_config_diff
| Field | J Snapshot | L Snapshot | Current | Meaning |
| --- | --- | --- | --- | --- |
| `config/aurora/domains.yaml.sha256` | `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477` | `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` | `e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477 -> 3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5` | Whole-file drift was real; restore returned the workspace to the clean accepted hash. |
| `config/aurora/strategies/aurora.yaml.sha256` | `e0c451d6cc21c577a8d2d868b378f3d7589ec6ad2d3015d8fb2b0a84a2df3b85` | `e0c451d6cc21c577a8d2d868b378f3d7589ec6ad2d3015d8fb2b0a84a2df3b85` | `67cbe3b6f4263aa6a335813bd6940b8b97294f6a2657c185f5a14e70fa791882` | J/L strategy config stayed constant; current local strategy drift is unrelated to the sidecar authority seam. |
| `execution_position.position_policy_sidecar.mode` | `shadow` | `enable` | `shadow -> enable` | The authority-relevant change. `shadow` suppresses live close command emission; `enable` permits the bounded soft-close path. |
| `execution_position.position_policy_sidecar.peak_giveback_close.enabled` | `false` | `false` | `false` | Peak-giveback close remained disabled. |
| `execution_position.position_policy_sidecar.shadow_percent_notional_arm.enabled` | `true` | `true` | `true` | Shadow percent-of-notional telemetry arm unchanged. |
| `execution_position.position_policy_sidecar.shadow_fee_aware_arm.enabled` | `true` | `true` | `true` | Shadow fee-aware telemetry arm unchanged. |
| `execution_position.position_policy_sidecar.allowed_actions.soft_close_symbol_current_net_only` | `true` | `true` | `true` | Bounded action scope unchanged. |
| `execution_position.position_policy_sidecar.allowed_actions.partial_reduce` | `false` | `false` | `false` | Forbidden authority unchanged. |
| `execution_position.position_policy_sidecar.allowed_actions.bracket_mutation` | `false` | `false` | `false` | Forbidden authority unchanged. |
| `execution_position.position_policy_sidecar.allowed_actions.exact_targeting` | `false` | `false` | `false` | Forbidden authority unchanged. |

## accepted_baseline
Accepted sidecar baseline: `enable`.

Evidence:
- committed line history has kept `enable` since 2026-04-13;
- `SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT.md` explicitly maintains `enable`;
- `reports/PEAK_GIVEBACK_CONTAINMENT_IDENTITY_REPAIR_REPORT.md` explicitly restores `enable` as the accepted post-containment seam;
- `reports/PEAK_GIVEBACK_CONFIG_ONLY_CONTAINMENT_REPORT.md` confirms mode remains `enable`;
- the clean H and L runtime snapshots both carry the same `enable` hash `3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5`.

Rejected alternative:
- `shadow` appears in I, J, and the pre-action workspace only as a dirty local copy on the same tracked commit. The untracked next-testnet blueprint is not sufficient evidence to reclassify that drift as an accepted baseline.

## nrr062_comparability
| Package | Sidecar Mode | Comparable With | Notes |
| --- | --- | --- | --- |
| H | `enable` | H, L, restored current baseline, future enable-cohort packages | Clean snapshot hash `3ece...`; matches accepted baseline. |
| I | `shadow` | I, J | Dirty snapshot hash `e33...`; must be labeled as a separate shadow cohort. |
| J | `shadow` | I, J | Dirty snapshot hash `e33...`; package L already documented the resulting comparability caveat. |
| L | `enable` | H, L, restored current baseline, future enable-cohort packages | Clean snapshot hash `3ece...`; matches accepted baseline. |

Comparability verdict: `COMPARABILITY_COHORT_SPLIT_REQUIRED`.

## action_taken
- Decision chosen: `RESTORE_PREVIOUS_ACCEPTED_BASELINE`.
- Restored `config/aurora/domains.yaml` `execution_position.position_policy_sidecar.mode` from `shadow` to `enable`.
- Did not change any NRR-062 thresholds, override conditions, strategy YAML values, Pydantic models, or runtime Python.
- Updated one stale config-contract test expectation in `tests/config/test_decision_making_contracts.py` from `shadow` to `enable` so the focused validation slice matches the restored accepted baseline.
- Rollback instructions: if an operator intentionally needs the historical `shadow` cohort for a forensic-only rerun, change only `execution_position.position_policy_sidecar.mode` back to `shadow`, rerun the same focused validation slice used here, and label all resulting runtime evidence as a separate `shadow` cohort. Do not merge that evidence into the `enable` cohort economics.

## validation
- JSON parse:
  - `Get-Content nrr062_j_to_l_sidecar_config_diff.json -Raw | ConvertFrom-Json | Out-Null`
  - `Get-Content sidecar_mode_baseline_reconciliation.json -Raw | ConvertFrom-Json | Out-Null`
  - `Get-Content nrr062_sidecar_mode_comparability_matrix.json -Raw | ConvertFrom-Json | Out-Null`
  - output: `JSON_OK 3`
- YAML parse:
  - `./.venv/Scripts/python.exe -c "import pathlib, yaml; yaml.safe_load(pathlib.Path(r'config/aurora/domains.yaml').read_text(encoding='utf-8')); print('YAML_OK config/aurora/domains.yaml')"`
  - output: `YAML_OK config/aurora/domains.yaml`
- Focused pytest:
  - `./.venv/Scripts/python.exe -m pytest tests/config/test_decision_making_contracts.py tests/config/test_position_policy_sidecar_config_contract.py tests/domains/execution_position/test_sidecar_modes_disable_shadow_enable.py tests/config/test_execution_position_contracts.py::test_current_aurora_config_loads_execution_position_contract tests/test_calibrators_import_boundary.py`
  - output: `80 passed in 20.79s`
- No unintended `domains.yaml` diff remains:
  - `git status --short -- config/aurora/domains.yaml config/aurora/strategies/aurora.yaml tests/config/test_decision_making_contracts.py`
  - output shows `config/aurora/domains.yaml` absent; remaining modified tracked files in this check are the unrelated local `config/aurora/strategies/aurora.yaml` and the aligned test file `tests/config/test_decision_making_contracts.py`.

## runtime_behavior_change
- NRR-062 behavior changed: no
- sidecar config changed: yes
- YAML changed: yes
- Pydantic changed: no
- runtime Python changed: no
- new events/commands added: no

## next_recommended_package
CONTINUE_NRR062_COLLECTION_POST_BASELINE_RECONCILIATION
