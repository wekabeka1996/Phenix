# SIDECAR_MODE_BASELINE_RECONCILIATION

## Classification

- Accepted baseline: `enable`
- Current pre-action classification: `ACCIDENTAL_DRIFT_TO_SHADOW`
- Current post-action state: `ACCEPTED_BASELINE_ENABLE`

## Evidence

| Source | Observation | Implication |
| --- | --- | --- |
| `git log -L /position_policy_sidecar:/,+70:config/aurora/domains.yaml` | Commit `a6dc8404f851e9a6d5f29da32cc47019f6ec8109` changed `mode: shadow -> enable` on 2026-04-13; later tracked commits through `f0cf6363f36a04d679fe75c31987c6dbe0361cac` kept `mode: enable`. | The tracked project baseline has been `enable` since 2026-04-13. |
| `SIDECAR_ENABLE_GOVERNANCE_AUDIT_REPORT.md` | Verdict: `MAINTAIN_ENABLE_WITH_REQUIRED_PATCHES`. | Governance evidence explicitly keeps `enable`, not `shadow`, as the accepted mode. |
| `reports/PEAK_GIVEBACK_CONTAINMENT_IDENTITY_REPAIR_REPORT.md` | Required target state: `position_policy_sidecar.mode = enable` while keeping `peak_giveback_close.enabled = false` and both shadow arms enabled. | Later config-governance repair explicitly restored the accepted seam to `enable`. |
| `reports/PEAK_GIVEBACK_CONFIG_ONLY_CONTAINMENT_REPORT.md` | States `execution_position.position_policy_sidecar.mode remains enable`. | The accepted post-containment seam remained `enable` after peak-giveback disablement. |
| `logs/frozen/nrr062_fresh_capture_20260515_180927/config_snapshot_manifest.json` | Clean `domains.yaml` snapshot hash `3ece...`, `dirty_config_paths=[]`, sidecar mode `enable`. | Package H ran on the accepted clean baseline. |
| `logs/frozen/nrr062_fresh_capture_20260517_210245/config_snapshot_manifest.json` | Clean `domains.yaml` snapshot hash `3ece...`, `dirty_config_paths` does not include `config/aurora/domains.yaml`, sidecar mode `enable`. | Package L also ran on the accepted clean baseline. |
| `logs/frozen/nrr062_fresh_capture_20260516_101448/config_snapshot_manifest.json` and `logs/frozen/nrr062_fresh_capture_20260517_080431/config_snapshot_manifest.json` | Both show `domains.yaml` hash `e33...`, sidecar mode `shadow`, and `dirty_config_paths` includes `config/aurora/domains.yaml` on the same tracked commit `34a3...`. | Packages I and J captured a dirty local drift, not a new accepted tracked baseline. |
| `docs/plans/NEXT_TESTNET_CONFIG_BLUEPRINT_2026-05-16.md` | Proposes `enable -> shadow` for a future testnet preset, but the same file appears as `??` untracked in I/J/L snapshot manifests. | This is a proposal, not accepted or applied baseline evidence. |
| Current workspace before restore | `config/aurora/domains.yaml` hash `e33...`, sidecar mode `shadow`, file showed as modified. | The workspace had drifted back to the same dirty shadow state seen in I/J. |
| Current workspace after restore | `config/aurora/domains.yaml` hash `3ece...`, `git status --short -- config/aurora/domains.yaml` is empty. | Restoring `enable` returned the workspace exactly to the accepted tracked baseline. |

## Minimal Verdict

The accepted project baseline for `execution_position.position_policy_sidecar.mode` is `enable`. The observed `shadow` state in packages I/J and in the pre-action workspace is best classified as accidental dirty-worktree drift to shadow, not as an accepted baseline migration.
