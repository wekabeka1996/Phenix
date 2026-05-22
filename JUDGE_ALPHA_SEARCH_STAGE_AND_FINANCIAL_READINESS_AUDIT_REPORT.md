BLOCKED: missing artifacts/judge_review, artifacts/phase5_calibration.jsonl, data/simulator, data/simulator/outcomes.json, logs/alpha_input/alpha_input_v1.jsonl, logs/alpha_search

# JUDGE_ALPHA_SEARCH_STAGE_AND_FINANCIAL_READINESS_AUDIT_REPORT

## 1. Readiness Verdict

PARTIAL_READY_NEEDS_JOIN_REPAIR

- FACT: alpha_search is wired into the main runtime and is actively emitting Judge shadow telemetry.
- FACT: Judge plan, verdict, and envelope rows already carry replay-relevant keys such as symbol, tf_sec, ts_ms, cycle_key, and strategy_id.
- FACT: the supported offline pipeline inputs and outputs are not materialized on disk right now: data/simulator/outcomes.json, artifacts/phase5_calibration.jsonl, and artifacts/judge_review are all absent.
- FACT: current runtime decision ledger rows are diagnostics-only, journal-only, and unsupported for counterfactual joins.
- INFERENCE: Judge is beyond telemetry-missing and beyond runtime-not-wired, but it is not yet end-to-end ready for authoritative financial replay or fee-adjusted head-to-head comparison.

## 2. Audit Scope And Constraints

- FACT: this was a read-only audit. No code, YAML, logs, or runtime state were modified.
- FACT: evidence was taken from config, runtime code, on-disk logs, artifacts, and safe help commands only.
- FACT: live JSONL files were still moving during the scan window. trade_lifecycle.jsonl changed slightly between line-count and parsed-event passes, so counts should be treated as point-in-time runtime counts rather than immutable archival numbers.
- FACT: verdicts below separate FACTS from INFERENCES and call out missing artifacts explicitly.

## 3. Evidence Sources

- FACT: configuration surfaces inspected: config/alpha_search.yaml, config/judge_simulator.yaml, config/judge_review.yaml, config/alpha_search_system.yaml, config/alpha_search/scenario_matrix.yaml.
- FACT: controlling runtime code inspected: apps/reference/main.py, apps/reference/domains/alpha_search/backtest_plugin.py, apps/reference/domains/alpha_search/runtime/launcher.py, apps/reference/domains/alpha_search/runtime/feature_mirror_writer.py, apps/reference/domains/alpha_search/runtime/ingest.py.
- FACT: offline surfaces inspected: apps/reference/domains/alpha_search/judge/simulator/cli.py, apps/reference/domains/alpha_search/judge/review/cli.py, corresponding config models, and simulator/review engines.
- FACT: runtime evidence inspected: logs/judge_experts/*.jsonl, logs/shadow_telemetry/decision_ledger_v1.jsonl, logs/order_log_v1.jsonl, logs/trade_lifecycle.jsonl, logs/shadow_critical_event_journal_v1.jsonl, logs/aurora_events.jsonl, data/recorder/**/*, data/raw_binance_klines_1m/**/*.
- FACT: safe entrypoint verification was executed with help-only commands for standalone runner, judge-simulator, and judge-review.

## 4. Runtime Wiring Status

- FACT: apps/reference/main.py registers AlphaSearchBacktestPlugin using config/alpha_search.yaml.
- FACT: embedded alpha_search therefore runs inside the main runtime path rather than existing only as dormant code.
- FACT: a separate standalone runner exists at scripts/runners/run_alpha_search_domain.py.
- FACT: no wrapper exists at scripts/run_alpha_search_domain.py.
- INFERENCE: embedded Judge is wired and live; standalone alpha_search is a separate operational shape, not the only path.

## 5. Current Operating Stage

- FACT: the environment is currently in an embedded Judge shadow-telemetry stage, not in a materialized standalone replay session stage.
- FACT: logs/judge_experts and logs/shadow_telemetry exist and are populated.
- FACT: logs/alpha_search, logs/alpha_input, standalone scores.jsonl, and standalone trades.jsonl are all absent.
- FACT: config/alpha_search/scenario_matrix.yaml expects standalone input.source_mode live_tail with stream_path logs/alpha_input/alpha_input_v1.jsonl.
- INFERENCE: the repo contains both embedded and standalone paths, but only the embedded Judge shadow path is currently materialized on disk.

## 6. Shadow And Authority Status

- FACT: config/alpha_search.yaml has enabled: true and shadow_mode: true.
- FACT: Judge sample rows show authority_mode: shadow and applied: false in both verdict and shadow_entry_plan outputs.
- FACT: the verb registry marks the Judge surfaces as shadow-only and not consumed by decision_making authority.
- INFERENCE: alpha_search and Judge are not promoted to live execution authority in the current audited state.

## 7. Provider And Expert Enablement

- FACT: config/alpha_search.yaml enables providers aurora, ta_ensemble, judge_sw, and judge_fn.
- FACT: logs/judge_experts contains live rows for judge.signal_weights_v1 and judge.feature_neutrals_v1, proving expert invocation rather than config-only presence.
- FACT: sample envelopes show expert_count: 2 and responding_count: 2.
- INFERENCE: judge_sw and judge_fn are enabled and callable in the embedded path.

## 8. Callable Surfaces And Operator Commands

- FACT: verified standalone runner help command: py -3 scripts/runners/run_alpha_search_domain.py --help
- FACT: verified simulator help command: py -3 -m apps.reference.domains.alpha_search.judge.simulator.cli --help
- FACT: verified review help command: py -3 -m apps.reference.domains.alpha_search.judge.review.cli --help
- FACT: build helper exists at tools/alpha_search/build_alpha_input.py and writes logs/alpha_input/alpha_input_v1.jsonl when executed.
- FACT: standalone runner help text still shows stale examples pointing to python scripts/run_alpha_search_domain.py even though the real file is under scripts/runners.
- INFERENCE: chamber, envelope, verdict, simulator, and review are callable surfaces, but some operator guidance in help/docs is path-stale.

## 9. Standalone Launcher And Alpha Input Ownership

- FACT: config/alpha_search/scenario_matrix.yaml defines standalone input.source_mode: live_tail and stream_path: logs/alpha_input/alpha_input_v1.jsonl.
- FACT: FeatureMirrorWriter can create the parent directory for logs/alpha_input/alpha_input_v1.jsonl when invoked.
- FACT: no FeatureMirrorWriter wiring was found in apps/reference/main.py.
- FACT: tools/alpha_search/build_alpha_input.py can synthesize alpha_input_v1.jsonl from data/recorder CSV files.
- FACT: logs/alpha_input and logs/alpha_input/alpha_input_v1.jsonl are absent on disk right now.
- INFERENCE: the main runtime is not currently auto-feeding standalone live_tail input; alpha_input ownership is either the unwired FeatureMirrorWriter or the offline build helper.

## 10. Directory Auto-Creation And Missing Paths

- FACT: launcher/runtime code can create some output directories for standalone sessions and aggregate reports.
- FACT: FeatureMirrorWriter creates the alpha_input parent directory if it is used.
- FACT: these paths are currently missing on disk: logs/alpha_search, logs/alpha_input, data/simulator, artifacts/judge_review, artifacts/phase5_calibration.jsonl, data/simulator/outcomes.json.
- FACT: standalone outputs search returned no scores.jsonl, no trades.jsonl, no alpha_input_v1.jsonl, no phase5_calibration.jsonl, and no outcomes.json anywhere in the repo tree.
- INFERENCE: auto-creation capability exists in code, but those paths have not been materialized in this environment.

## 11. Judge Artifact Inventory

| Surface | Files | Rows | Symbols | Date Range UTC |
| --- | ---: | ---: | --- | --- |
| chamber_aggregate | 28 | 15,405 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | 2026-05-17T21:44:59.999Z to 2026-05-20T15:59:59.999Z |
| evidence_envelope | 28 | 15,405 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | 2026-05-17T21:44:59.999Z to 2026-05-20T15:59:59.999Z |
| expert_output.signal_weights | 28 | 15,405 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | 2026-05-17T21:44:59.999Z to 2026-05-20T15:59:59.999Z |
| expert_output.feature_neutrals | 28 | 15,405 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | 2026-05-17T21:44:59.999Z to 2026-05-20T15:59:59.999Z |
| policy_cortex | 28 | 15,405 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | timestamp not exposed in top-level scan |
| judge_verdict | 28 | 15,405 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | 2026-05-17T21:44:59.999Z to 2026-05-20T15:59:59.999Z |
| shadow_entry_plan | 28 | 46,215 | 1000PEPEUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, ETHUSDT, SOLUSDT, XRPUSDT | 2026-05-17T21:44:59.999Z to 2026-05-20T15:59:59.999Z |

- FACT: sample shadow_entry_plan rows include tf_sec, ts_ms, cycle_key, strategy_id, entry price reference, TP, SL, confidence tier, and source envelope/verdict IDs.
- FACT: sample verdict rows include tf_sec, ts_ms, cycle_key, confidence, strategy_id, and applied: false.
- FACT: sample envelope rows include regime, regime_confidence, regime_source, freshness_deadline_ms, expert_outputs, and provenance.
- INFERENCE: Judge telemetry is materially populated and rich enough for segmented replay preparation.

## 12. Runtime Outcome Inventory

- FACT: logs/order_log_v1.jsonl had 158 rows at scan time.
- FACT: top order_log event counts were DECISION_INTENT_REJECTED 44, ORDER_INTENT 44, ORDER_FILLED 39, ORDER_PLACED 13, POSITION_CLOSED 9.
- FACT: accepted trade intents found at top-level order_log event typing: 0. Rejected trade intents: 44.
- FACT: logs/trade_lifecycle.jsonl was active during the scan and sat at roughly 176k rows, dominated by POSITION_POLICY_SIDECAR_SUPPRESSED events, with EXECUTION_FILL_INGRESS 39 and TRADE_LIFECYCLE_FILLED 37 visible in the top distribution.
- FACT: logs/shadow_critical_event_journal_v1.jsonl had 54,516 rows with EVT:REGIME_DETECTED 5,473, EVT:QUADRATIC_DECISION_TRACE 1,756, EVT:GATE_CHAIN_TRACE 196, EVT:DECISION_TRACE_EMITTED 62, EVT:TRADE_EXECUTED 117, and EVT:TRADE_INTENT_REJECTED 281.
- FACT: logs/aurora_events.jsonl had 47 rows but zero counted EVT:ALPHA_SCORE_CALCULATED, zero EVT:ALPHA_SCORES_AGGREGATED, zero EVT:REGIME_DETECTED, and zero EVT:DECISION_TRACE_EMITTED in the scanned window.
- FACT: logs/shadow_telemetry/decision_ledger_v1.jsonl had 67 rows: EXECUTED_AND_CLOSED 5, REJECTED_UPSTREAM 45, INVALID_FOR_DATASET 17. REALIZED outcomes were present on 5 rows only.

## 13. Field Coverage For Financial Analysis

| Requirement | Judge telemetry | Recorder candles | Current runtime decision_ledger | Audit status |
| --- | --- | --- | --- | --- |
| symbol, tf_sec, event time | present in plan, verdict, envelope | present | top-level missing in sampled rows | good for Judge replay, bad for supported runtime ledger join |
| cycle_key | present in plan, verdict, envelope | not native, but bar timestamp plus tf_sec are present | top-level missing in sampled rows | good for Judge surface joins |
| strategy_id | present in plan, verdict, envelope | not needed | top-level missing in sampled rows | good for Judge replay, missing for supported runtime comparison |
| regime and regime_confidence | present in envelope | present in recorder | top-level missing in sampled rows | good for Judge per-regime segmentation |
| entry reference and TP/SL levels | present in shadow_entry_plan | high/low/close available | absent | good for candle replay of Judge proposals |
| realized PnL and fees | absent from raw Judge plans | not applicable | present on 5 realized rows only | only partial incumbent outcome evidence |
| accepted/rejected outcome labeling | can be derived later from replay | not native | top-level missing in sampled rows | unsupported in current runtime ledger contract |
| counterfactual join support | not needed if custom replay is built | not needed | supports_counterfactual_join true on 0 of 67 rows | official runtime comparison blocked |

- FACT: the strongest contract gap is not inside Judge plan/verdict/envelope telemetry; it is between those Judge rows and the currently missing official outcomes dataset plus the non-causal current runtime ledger.

## 14. Historical Analysis Capability

- FACT: historical Judge decision analysis is possible now for descriptive analysis: verdict mix, consensus direction, confidence distribution, symbol splits, tf splits, regime splits, and expert reasoning traces.
- FACT: per-symbol and per-regime segmentation is possible because envelope rows carry regime data and recorder rows also carry regime fields.
- FACT: confidence-threshold slicing is possible because plan and verdict rows carry confidence and tier information.
- INFERENCE: telemetry-level historical analysis is already available now.
- INFERENCE: authoritative financial analysis is not yet turnkey because the official replay outcome layer is not materialized.

## 15. Candle Replay, Simulator, And Review Readiness

- FACT: shadow_entry_plan rows contain entry_price_ref, limit_price, tp_price, sl_price, tf_sec, ts_ms, cycle_key, and strategy_id.
- FACT: recorder data covers 102 day directories, 1,986 CSV files, 7 symbols, and the three active timeframes 180, 300, and 900 seconds.
- FACT: raw 1m candle data exists for 6 symbols, but not for the full 7-symbol Judge set; 1000PEPEUSDT is covered in recorder but not in the raw 1m inventory scanned.
- FACT: judge-simulator and judge-review CLIs are callable, but their configured inputs are missing on disk right now.
- FACT: no data/simulator/outcomes.json exists; no artifacts/phase5_calibration.jsonl exists; no artifacts/judge_review exists.
- INFERENCE: custom candle replay of Judge proposals is feasible now from existing telemetry plus recorder candles.
- INFERENCE: the supported simulator/review pipeline is not runnable end-to-end until outcomes.json is materialized.

## 16. Comparison Against Current Runtime

- FACT: incumbent runtime outcome evidence exists: 44 rejected intents, 39 fills, 9 position closes, and 5 realized decision-ledger rows with gross/net PnL and fees.
- FACT: every scanned decision_ledger row had supports_counterfactual_join: false and counterfactual_support: unsupported.
- FACT: sampled decision_ledger rows had null top-level cycle_key, tf_sec, bar_close_ts_ms, strategy_id, side, accepted_or_rejected, regime, regime_confidence, decision_surface, scores, threshold, and gate_chain_result.
- FACT: gate trace data exists, but only inside nested causal_state_snapshot.gate_trace_summary and a diagnostics-only journal capture mode.
- INFERENCE: qualitative side-by-side inspection against incumbent runtime is possible.
- INFERENCE: audit-grade, fee-adjusted, causal Judge-vs-runtime comparison is not currently supported by the emitted runtime ledger contract.

## 17. Explicit Answers And Single Smallest Next Action

1. Is Judge already ready for financial replay or calibration?

   No. The correct classification is PARTIAL_READY_NEEDS_JOIN_REPAIR.

2. Can historical Judge decisions be analyzed now?

   Yes, at telemetry level. Symbol, timeframe, regime, confidence, consensus, and reasoning analysis are available now from existing judge_experts outputs.

3. Can Win Rate, PnL, DD, PF, expectancy, per-symbol, and per-regime financial metrics be computed now?

   Not through the supported built-in pipeline as audited today. Those require materialized replay outcomes. Per-symbol and per-regime slicing inputs already exist, but the outcome layer does not.

4. Can confidence thresholds be swept now?

   Yes for decision-distribution analysis. No for authoritative financial metrics until replay outcomes are materialized.

5. Can Judge proposed trades be compared against the current runtime now?

   Only partially and mostly qualitatively. The current runtime decision ledger is diagnostics-only and explicitly unsupported for counterfactual joins, so audit-grade head-to-head comparison is not ready.

6. What is the single smallest next action?

   Materialize data/simulator/outcomes.json from the already-existing Judge shadow_entry_plan plus envelope telemetry joined to data/recorder by cycle_key, symbol, tf_sec, ts_ms, and strategy_id, then run judge-simulator and judge-review on that dataset. This unlocks official financial replay without first changing Judge emission contracts.
