# AGENT_REPORT_V1

## Executive Summary
Package N extends NRR062 override runtime collection under enable-mode sidecar authority, with current owner-surface equivalence to the accepted enable baseline and fresh override-applied runtime evidence in the new window. Git history for Packages H and M confirms that the accepted clean cohort remains enable-mode, while I/J remain a separate shadow cohort.

## Proven Facts
- Fresh bundle logs/frozen/nrr062_fresh_capture_20260529_065313 contains 22 distinct override-applied ORDER_INTENT rows derived from DecisionMaking ORDER_INTENT metadata.low_vol_cost_floor; this is a different measure from MANIFEST probe.order_log_nrr062_rows=13.
- Current frozen domains full hash is 5f7a330b12a7e52ae3c412b967960726c9926c156e3b97acf26aac94d7339a12 while accepted enable snapshot hash is 3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5.
- execution_position.position_policy_sidecar blocks are equal between current frozen domains and the accepted enable snapshot, and both use mode=enable.
- Fresh bundle recorder coverage is sufficient=True and config snapshot required files are 8 / 8.
- Fresh bundle still lacks a frozen decision_ledger surface, so decision_ledger terminal status used in derived reports comes from current workspace authority only.
- Package H and Package M reports re-read from git history confirm that H/L are the clean enable cohort at hash 3ece313409a6f0db2fd0ee5ce44a9ee0ff5e94a6fad98c1a878e8c6f3a5394d5, while I/J are the dirty shadow cohort at hash e33e95a9a44f7606169ad78ac6bf0bc68be4a1d47df0d61940ce05f117fd0477.

## Inferred Findings
- Full domains hash drift is outside the sidecar owner surface, so enable-vs-shadow cohort separation remains supportable on the override authority surface for this Package N window.
- Enable-cohort latest-known runtime net quote is 4.948720610000007, which remains positive across H/L/N occurrence rows.
- Package N should remain grouped with the enable cohort, not with the I/J shadow cohort, because the current sidecar owner block matches the accepted enable snapshot and git-history lineage keeps enable as the accepted baseline.
- Shadow I/J economics remain appendix-only evidence and are not blended into enable-cohort verdicts.

## Contradictions / Evidence Gaps
- Fresh capture script still does not freeze decision_ledger into the bundle, so decision terminal evidence is not capture-time sealed for Package N.
- Package N report does not replay new N rows against recorder bars; replay-vs-runtime remains anchored to the pre-existing Package F candidate surface.

## Root Cause Candidates
- The capture contract omits FREEZE_REPORT.md and decision_ledger freezing, so post-capture forensic reporting has to reconstruct part of the authority story outside the bundle.

## Operational Risk
- Observability Gap

## Files / Areas Touched
- tools/analysis/generate_nrr062_package_n_report.py
- logs/frozen/nrr062_fresh_capture_20260529_065313/FREEZE_REPORT.md
- calibrators/datasets/nrr062_testnet_override_runtime/NRR062_OVERRIDE_RUNTIME_LEDGER_N.md
- calibrators/datasets/nrr062_testnet_override_runtime/NRR062_ENABLE_COHORT_OVERRIDE_LEDGER.md
- calibrators/datasets/nrr062_testnet_override_runtime/NRR062_ENABLE_COHORT_BOUNDARY_AUDIT.md
- calibrators/datasets/nrr062_testnet_override_runtime/NRR062_ENABLE_COHORT_ECONOMICS_REVIEW.md
- calibrators/datasets/nrr062_testnet_override_runtime/NRR062_SHADOW_COHORT_APPENDIX.md
- calibrators/datasets/nrr062_testnet_override_runtime/NRR062_ENABLE_COHORT_REPLAY_VS_RUNTIME.md
- CALIBRATORS_NRR_PACKAGE_N_CONTINUE_COLLECTION_POST_BASELINE_RECONCILIATION_REPORT.md

## Validation Performed
- Executed the generator against the fresh bundle and emitted all requested Package N artifacts.
- Validated sidecar owner-surface equivalence by YAML-loading current frozen domains and the accepted enable snapshot and comparing execution_position.position_policy_sidecar blocks directly.
- Used runtime bundle order_log/trade_lifecycle plus current workspace decision_ledger authority to classify Package N latest-known lifecycle buckets.
- Re-read deleted Package H and Package M root reports from git history to verify that enable remains the accepted clean cohort and that I/J stay explicitly separated as the shadow cohort.

## Residual Risk
- Decision-ledger-dependent no-effect interpretations are weaker than they would be under a fully frozen decision_ledger capture.
- Replay-vs-runtime still relies on historical Package F candidate economics instead of a fresh N-only replay rerun.

## What Remains Unproven
- Whether every current full-config delta outside the sidecar block is operationally irrelevant to realized economics remains unproven.
- Whether a fresh N-only replay rerun over the current window would preserve the same positive directionality seen in the Package F candidate replay remains unproven.

## Minimal Safe Verdict
- Continue Package G override collection in hybrid_live_data_testnet_exec as enable-cohort testnet-only evidence. Do not promote, do not tune thresholds, and keep shadow I/J economics appendix-only while fresh bundle sealing still lacks a frozen decision_ledger surface.