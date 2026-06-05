# REALIZED_OUTCOME_AUTHORITY_DECISION

- executed_trades_master authority status: DERIVED_CONVENIENCE_REPORT_ONLY
- recommended calibration source: BUILD_BRIDGE_DATASET_DECISION_LEDGER_TO_ORDER_LOG
- confidence: MEDIUM

## Why
- The only active producer found is scripts/forensics/build_order_flow_master.py, a manual CLI forensics script with no repo-wired invocation surface.
- Current master CSV outputs are stale relative to current runtime logs and contain only four timeout rows plus a header-only executed subset.
- decision_ledger and order_log provide current realized-outcome evidence, while executed_trades_master does not.
- The best exact identity surface for calibration is the decision_ledger -> order_log bridge, not executed_trades_master directly.

## Risks
- order_log remains a mixed event stream and needs explicit canonicalization rules
- decision_ledger realized fields are partial
- executed_trades_master may still be useful as a convenience export but is not proven authoritative