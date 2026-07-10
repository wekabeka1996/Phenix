# Canonical Baseline

- Runtime baseline branch: `origin/p40-runtime-order-proof-integrated-primary-20260710`
- Exact baseline SHA before P41X editing: `9af369b7657e631b22519785ae09e54b8e9c28b8`
- Merge-base with the working branch: the same SHA.
- P39 report verdict read: `P39A_RUN_READY_GATE_NO_ORDER_ONLY`.
- P40 primary report verdict read: `P40_FINAL_TESTNET_ORDER_PROOF_BLOCKED`.
- P40R final report verdict read: `P40R_FINAL_EXTERNAL_PROOF_BLOCKED`.

P40R's secondary report called a shadow `ExchangeACL(shadow_mode=True)` response a real ACK. Source and final coordination evidence contradict that claim; P41X treats it as simulated/shadow evidence only.

During P41X work, another local P42 agent committed and pushed `95604243` and `5d421450` on the same branch, including the initial P41X config/model files plus P42-only reports/tests. Those commits were preserved; no destructive Git operation was used.
