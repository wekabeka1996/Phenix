# Merge Sequence

We integrated the P40 candidate branches in the following order using `--no-ff` merge commits:

1.  **Merge 1: P40A Gate Config**
    - Source: `origin/p40-testnet-order-proof-integrated-primary-20260709`
    - Commit SHA: `cae21e6443c7b3dd62bb22a420b925b34bc293d0`
    - Merge Commit: `cd223b8a`
2.  **Merge 2: P40B Hardened Capability Descriptor**
    - Source: `p40b-testnet-adapter-capability-primary-20260709`
    - Commit SHA: `02b63aa666ef11dcf8786016abefc787a718d7ef`
    - Merge Commit: `312427fb`
3.  **Merge 3: P40C Order Lifecycle Harness**
    - Source: `origin/p40c-order-lifecycle-proof-harness-primary-20260709`
    - Commit SHA: `e28bda99e69e06180373df829fa5113d0774a36f`
    - Merge Commit: `b8157f1b`
