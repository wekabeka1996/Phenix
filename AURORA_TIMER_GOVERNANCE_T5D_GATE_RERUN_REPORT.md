AGENT_REPORT_V1

task: AURORA_TIMER_GOVERNANCE_T5D_GATE_RERUN
verdict: READY_FOR_T5D_CALIBRATION
report_path: AURORA_TIMER_GOVERNANCE_T5D_GATE_RERUN_REPORT.md

problem:
- Re-run the T5D gate on fresh retained runtime evidence, segmented by restart windows, without changing runtime behavior or configuration.

facts:
- logs inspected: 965 files across current logs, logs/frozen bundles, root frozen bundles, and reports inventory.
- file time bounds detected:
- frozen/sidecar_feature_freshness_capture_20260513T190837Z/logs/aurora_core.log*: 2026-05-11T18:27:19.748000Z -> 2026-05-13T22:10:16.131000Z
- frozen/sidecar_feature_freshness_capture_20260513T190837Z/logs/domain_execution_position.log*: 2026-05-11T17:54:07.506000Z -> 2026-05-13T22:10:35.155000Z
- frozen/sidecar_feature_freshness_capture_20260513T190837Z/logs/order_log_v1.jsonl: 2026-05-11T15:10:03.413000Z -> 2026-05-13T17:55:01.595000Z
- frozen/sidecar_feature_freshness_capture_20260513T190837Z/logs/trade_lifecycle.jsonl: 2026-05-11T14:54:11.586000Z -> 2026-05-13T19:08:36.890000Z
- frozen/sidecar_manageflow_capture_20260510T200052Z/logs/aurora_core.log*: 2026-05-09T21:58:30.525000Z -> 2026-05-10T23:00:52.362000Z
- frozen/sidecar_manageflow_capture_20260510T200052Z/logs/domain_execution_position.log*: 2026-05-10T00:58:21.790000Z -> 2026-05-10T23:01:01.535000Z
- frozen/sidecar_manageflow_capture_20260510T200052Z/logs/order_log_v1.jsonl: 2026-05-09T22:15:03.691000Z -> 2026-05-10T20:00:05.130000Z
- frozen/sidecar_manageflow_capture_20260510T200052Z/logs/trade_lifecycle.jsonl: 2026-05-09T21:58:22.983000Z -> 2026-05-10T20:01:01.591000Z
- frozen/sidecar_manageflow_capture_20260510T200250Z/logs/aurora_core.log*: 2026-05-09T21:58:30.525000Z -> 2026-05-10T23:02:49.967000Z
- frozen/sidecar_manageflow_capture_20260510T200250Z/logs/domain_execution_position.log*: 2026-05-10T00:58:21.790000Z -> 2026-05-10T23:02:51.294000Z
- frozen/sidecar_manageflow_capture_20260510T200250Z/logs/order_log_v1.jsonl: 2026-05-09T22:15:03.691000Z -> 2026-05-10T20:00:05.130000Z
- frozen/sidecar_manageflow_capture_20260510T200250Z/logs/trade_lifecycle.jsonl: 2026-05-09T21:58:22.983000Z -> 2026-05-10T20:02:57.771000Z
- logs/aurora_core.log*: 2026-05-11T18:27:19.748000Z -> 2026-05-13T22:17:27.558000Z
- logs/domain_execution_position.log*: 2026-05-11T17:54:07.506000Z -> 2026-05-13T22:17:57.728000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190016Z/logs/order_log_v1.jsonl: 2026-05-11T15:10:03.413000Z -> 2026-05-13T17:55:01.595000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190016Z/logs/trade_lifecycle.jsonl: 2026-05-11T14:54:11.586000Z -> 2026-05-13T19:00:15.561000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/order_log_v1.jsonl: 2026-05-09T22:15:03.691000Z -> 2026-05-10T16:40:06.128000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/artifacts/calibration_datasets/_post_03k_realized_outcome/source_snapshot/trade_lifecycle.jsonl: 2026-05-09T21:58:22.983000Z -> 2026-05-10T18:40:47.938000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/artifacts/calibration_datasets/_post_03k_realized_outcome_03q/source_snapshot/order_log_v1.jsonl: 2026-05-09T22:15:03.691000Z -> 2026-05-10T16:40:06.128000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/artifacts/calibration_datasets/_post_03k_realized_outcome_03q/source_snapshot/trade_lifecycle.jsonl: 2026-05-09T21:58:22.983000Z -> 2026-05-10T18:40:47.938000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/logs/aurora_core.log*: 2026-05-11T18:27:19.748000Z -> 2026-05-13T22:07:36.031000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/logs/domain_execution_position.log*: 2026-05-11T17:54:07.506000Z -> 2026-05-13T22:07:32.833000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/logs/order_log_v1.jsonl: 2026-05-11T15:10:03.413000Z -> 2026-05-13T17:55:01.595000Z
- logs/frozen/calibrators_03u_multiday_post_03t_20260513T190409Z/logs/trade_lifecycle.jsonl: 2026-05-11T14:54:11.586000Z -> 2026-05-13T19:04:06.723000Z
- logs/frozen/prompt16_nrr062_post_prompt15_20260510_194306/logs/aurora_core.log*: 2026-05-10T16:49:13.410000Z -> 2026-05-10T22:43:06.230000Z
- logs/frozen/prompt16_nrr062_post_prompt15_20260510_194306/logs/order_log_v1.jsonl: 2026-05-09T22:15:03.691000Z -> 2026-05-10T19:40:03.490000Z
- logs/order_log_v1.jsonl: 2026-05-11T15:10:03.413000Z -> 2026-05-13T17:55:01.595000Z
- logs/trade_lifecycle.jsonl: 2026-05-11T14:54:11.586000Z -> 2026-05-13T19:23:56.484000Z
- runtime windows detected: 6
- first metadata ORDER_PLACED: 2026-05-09T22:15:05.503000Z in frozen/sidecar_manageflow_capture_20260510T200052Z/logs/order_log_v1.jsonl
- total post-T5C ORDER_PLACED: 90
- metadata-bearing ORDER_PLACED: 60
- calibration-relevant Aurora LIMIT/GTX entries: 60
- terminal joins: filled=80 timeout=9 canceled=0 unknown=1
- symbols: BNBUSDT, BTCUSDT, ETHUSDT, XRPUSDT
- strategies: aurora, close_executor
- source FSMs: CloseExecutor, ExecPosFSM

window_summary:
- W01 2026-05-09T22:15:03.691000Z -> 2026-05-10T19:07:24.351000Z orders=32 metadata=19 aurora_limit_gtx=19 join_rate=1.000
- W02 2026-05-10T19:07:24.352000Z -> 2026-05-10T19:24:45.505000Z orders=1 metadata=1 aurora_limit_gtx=1 join_rate=1.000
- W03 2026-05-10T19:24:45.506000Z -> 2026-05-11T15:10:03.412000Z orders=2 metadata=2 aurora_limit_gtx=2 join_rate=1.000
- W04 2026-05-11T15:10:03.413000Z -> 2026-05-11T23:30:03.822000Z orders=11 metadata=7 aurora_limit_gtx=7 join_rate=1.000
- W05 2026-05-11T23:30:03.823000Z -> 2026-05-13T09:00:04.403000Z orders=32 metadata=24 aurora_limit_gtx=24 join_rate=0.969
- W06 2026-05-13T09:00:04.404000Z -> 2026-05-13T15:18:55.914000Z orders=12 metadata=7 aurora_limit_gtx=7 join_rate=1.000

metadata_coverage:
- fill_ttl_source present: 60/90
- fill_ttl_override_ms present/null: present=60 null=0
- per_order_override: 60
- global_watchdog: 0
- missing metadata: 30

terminal_join_quality:
- filled: 80
- timeout: 9
- canceled: 0
- unknown: 1
- join rate: 0.989
- join methods: client_order_id, lifecycle_id+client_order_id, order_id

timing_distributions:
- age_to_first_fill_ms: count=80 min=2 p50=13564 p75=163316 p90=317352 p95=495737 p99=809179 max=965236
- age_to_timeout_ms: count=9 min=1200220 p50=1200457 p75=1200540 p90=1200686 p95=1200854 p99=1200988 max=1201022
- age_to_cancel_ms: count=9 min=1200816 p50=1201065 p75=1201252 p90=1201687 p95=1201887 p99=1202047 max=1202087

fill_ttl_override_ms_distribution:
- count: 60
- unique_values: 1200000
- min/p50/p95/max: 1200000 / 1200000 / 1200000 / 1200000
- by_symbol: BNBUSDT=[1200000]; BTCUSDT=[1200000]; ETHUSDT=[1200000]; XRPUSDT=[1200000]
- by_strategy: aurora=[1200000]
- by_timeframe_if_available: 300s=[1200000]

stale_watchdog_regression_check:
- verdict: STALE_WATCHDOG_SUSPECTED
- evidence: timeout_rows=9 suspicious_cases=1 text_watchdog_markers=3920
- suspicious timelines:
- 1362767783 BNBUSDT placed=2026-05-12T04:25:05.322000Z timeout=2026-05-12T04:45:05.809000Z terminal=2026-05-12T04:45:05.809000Z position_closed=2026-05-12T04:40:20.798000Z position_closed_method=position_closed.symbol reasons=timeout_after_position_closed_symbol_only

candidate_simulation:
- ttl=60000 orders=60 before_fill=30 before_cancel=0 before_known_terminal=39 risk=HIGH
- ttl=120000 orders=60 before_fill=24 before_cancel=0 before_known_terminal=33 risk=HIGH
- ttl=300000 orders=60 before_fill=9 before_cancel=0 before_known_terminal=18 risk=HIGH
- ttl=600000 orders=60 before_fill=3 before_cancel=0 before_known_terminal=12 risk=HIGH
- ttl=1200000 orders=60 before_fill=0 before_cancel=0 before_known_terminal=9 risk=MEDIUM
- ttl=1800000 orders=60 before_fill=0 before_cancel=0 before_known_terminal=0 risk=BACKSTOP_ONLY
- ttl=3600000 orders=60 before_fill=0 before_cancel=0 before_known_terminal=0 risk=BACKSTOP_ONLY

readiness_decision:
- verdict: READY_FOR_T5D_CALIBRATION
- Minimum gate passed and preferred calibration subset threshold was reached.
- threshold passed/failed: minimum_total_50=PASS preferred_aurora_limit_gtx_50=PASS metadata_present=PASS joins_possible=PASS

if_ready_next_package:
- T5D calibration study / patch proposal prompt

if_not_ready_collection_plan:
- minimum runtime duration: about 0.00 additional hours at current observed rates.
- minimum additional ORDER_PLACED: total=0 calibration_relevant_preferred=0
- required fields: ORDER_PLACED.fill_ttl_source and ORDER_PLACED.fill_ttl_override_ms present or explicit null, plus joinable terminal events.
- rerun command: c:/Users/user/Music/Phenix/.venv/Scripts/python.exe tools/audits/t5d_gate_rerun_analysis.py

runtime_behavior_change:
- NONE

config_changes:
- NONE

unproven:
- global_watchdog fill_ttl_source observations remain sparse: 0
- explicit null fill_ttl_override_ms observations: 0
- root frozen sidecar captures overlap and were deduplicated by event fingerprint rather than file identity.

next_recommended_package:
- T5D calibration study if verdict is READY_FOR_T5D_CALIBRATION; otherwise continue runtime collection and rerun this package.
