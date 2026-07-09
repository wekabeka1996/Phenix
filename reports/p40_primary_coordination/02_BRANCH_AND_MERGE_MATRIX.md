# P40 Branch And Merge Matrix

## FACTS

| Component | Branch/Ref | Commit Observed | Report Status |
|---|---|---:|---|
| Baseline | `origin/p39-runtime-mvp-integrated-primary-20260709` | `985b4800` | Present |
| P40 primary coordination | `p40-primary-coordination-20260709` | local branch | This package |
| P40A gate | `origin/p40-testnet-order-proof-integrated-primary-20260709` | `cae21e64` | Report found |
| P40B adapter | `p40b-testnet-adapter-capability-primary-20260709` | `02b63aa6` | Report found on local branch |
| P40C lifecycle harness | `origin/p40c-order-lifecycle-proof-harness-primary-20260709` | `e28bda99` | Report found |
| P40E external runner | `origin/p40e-external-testnet-order-proof-secondary-20260709` | `c4e88d59` | Supplemental blocked evidence found |
| P40 secondary quality | `origin/p40f-testnet-proof-quality-secondary-20260709` | `c7716a1b` | Report found |

## INFERENCES

- The branches were not fully integrated into the coordinator branch when this report was produced.
- P40E appears to have run before the P40A branch was visible on origin, causing a fail-closed block.

## ASSUMPTIONS

- The local P40B branch is acceptable evidence because it exists in the shared workspace and contains the required report.

## UNKNOWNS

- Whether P40B will be pushed or merged into the same integration branch as P40A/P40C.
- Whether the prompt commit typo reflects an unpublished baseline rewrite or simple transcription error.
