# AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5D_GATE
verdict: NOT_READY_INSUFFICIENT_POST_T5C_ORDERS
report_path: AURORA_TIMER_GOVERNANCE_T5D_GATE_REPORT.md

facts:
- Canonical placement and terminal evidence for this gate is present in logs/order_log_v1.jsonl.
- Post-T5C runtime window was inferred from the first ORDER_PLACED record that already carries fill_ttl_source and fill_ttl_override_ms: 2026-05-09T22:15:05.503Z through 2026-05-10T18:45:08.454Z, spanning 20.5 hours.
- Total ORDER_PLACED after the post-T5C marker: 30.
- Calibration-relevant ORDER_PLACED records with T5C metadata: 18.
- ORDER_PLACED with fill_ttl_source: 18.
- ORDER_PLACED with fill_ttl_source="per_order_override": 18.
- ORDER_PLACED with fill_ttl_source="global_watchdog": 0.
- ORDER_PLACED with fill_ttl_override_ms present: 18.
- ORDER_PLACED with fill_ttl_override_ms explicit null: 0.
- LIMIT or GTX orders with fill_ttl_source="per_order_override": 18.
- Joined terminal outcomes for metadata-bearing ORDER_PLACED records: filled=16, timeout=2, canceled=0, unknown=0.
- Joined terminal outcomes for all 30 post-T5C ORDER_PLACED records: filled=28, timeout=2, canceled=0, unknown=0.
- Symbols observed: BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT.
- Inferred strategy cohort for metadata-bearing entry placements: aurora.
- Source FSMs observed in the post-T5C placement window: ExecPosFSM and CloseExecutor.

data_quality:
- The available order_log_v1.jsonl window already starts with T5C metadata present on the first observed ORDER_PLACED, so the gate uses first-observed metadata as the post-T5C boundary for the current retained logs.
- order_log_v1.jsonl was sufficient to complete placement-to-terminal joins through client_order_id and order_id without unknown residuals.
- The full log surface requested in the task was inspected via VS Code search and terminal commands, but TTL metadata coverage and terminal joinability were only materially populated in logs/order_log_v1.jsonl for this runtime window.
- Current post-T5C volume mixes calibration-relevant Aurora entry placements with close MARKET placements. The gate verdict uses the full 30-record count for the hard threshold and the 18 metadata-bearing Aurora entry subset for calibration readiness quality.
- rg is not available in this PowerShell session, so equivalent search and counting were performed with VS Code search plus PowerShell parsing.

metadata_coverage:
- fill_ttl_source is observed on 18 of 18 calibration-relevant ORDER_PLACED records.
- fill_ttl_source values observed in the calibration-relevant subset: per_order_override only; global_watchdog was not observed.
- fill_ttl_override_ms is observed on 18 of 18 calibration-relevant ORDER_PLACED records.
- Explicit null fill_ttl_override_ms was not observed in the current window.
- At least one LIMIT order with fill_ttl_source="per_order_override" exists; observed count is 18.
- Terminal joins are possible and complete for all 18 metadata-bearing ORDER_PLACED records.

readiness_decision:
- Verdict is NOT_READY_INSUFFICIENT_POST_T5C_ORDERS.
- The gate requires at least 50 post-T5C ORDER_PLACED records. The current retained post-T5C window contains 30, which is below threshold.
- Metadata observability itself is present and adequate on observed Aurora entry placements.
- Terminal joinability is present and adequate on observed Aurora entry placements.
- The blocking condition is sample size, not metadata absence and not join failure.

if_not_ready_collection_plan:
- minimum runtime duration: approximately 13.7 more hours at the current observed overall pace of 1.46 ORDER_PLACED per hour to reach 50 total post-T5C placements; approximately 36.36 more hours at the current observed metadata-bearing pace of 0.88 orders per hour to reach 50 calibration-relevant Aurora entry placements. Use the longer target for real T5D calibration readiness.
- minimum order count: 50 post-T5C ORDER_PLACED at minimum, and preferably 50 metadata-bearing Aurora entry LIMIT or GTX placements before calibrating trading.execution.watchdog.fill_ttl_ms.
- required log fields: ORDER_PLACED.fill_ttl_source, ORDER_PLACED.fill_ttl_override_ms or explicit null, join keys through order_id and or client_order_id, and terminal records through ORDER_FILLED or ORDER_TIMEOUT or ORDER_CANCELLED.
- next command to rerun: Get-ChildItem logs -Recurse -File | Select-String -Pattern "ORDER_PLACED|fill_ttl_source|fill_ttl_override_ms|ORDER_FILLED|ORDER_TIMEOUT|ORDER_CANCELLED|TRADE_EXECUTED"

runtime_behavior_change:
- NONE

config_changes:
- NONE

next_recommended_package:
- otherwise continue runtime collection
