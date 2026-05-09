# Dataset Surface Audit

Audit-only surface map for the canonical calibrators layer.

- Package: CALIBRATORS_FOUNDATION_PACKAGE_02_DATASET_SURFACE_AUDIT
- Baseline commit: 46eda09769a5744a993f5d8b37bcc6429af66d70
- Generated at: 2026-05-07T11:04:34.5938758Z
- Runtime behavior changed: no
- Config values changed: no
- YAML changed: no
- Pydantic changed: no
- New events or commands added: no
- Registry changed: no

The canonical calibrators layer now contains 10 definite calibrators. This package maps which runtime and offline data surfaces each one already uses, where the trust boundaries are weak, and which canonical dataset schemas are needed before future calibration work should be treated as promotion-grade evidence.

The machine-readable companion to this document is calibrators/datasets/dataset_surface_inventory.json.

## Readiness Summary

| Readiness | Count | Calibrators |
| --- | ---: | --- |
| READY_WITH_EXISTING_DATA | 2 | aurora_regime_params, system_stress_weights |
| NEEDS_JOINED_DATASET | 3 | aurora_thresholds, objective_stack, low_vol_cost_floor |
| NEEDS_LABELLED_OUTCOMES | 1 | aurora_signal_weights |
| NEEDS_REPLAY_HARNESS | 3 | md_amr_weights, mean_reversion_params, md_amr_phase2b |
| BLOCKED_BY_MISSING_RUNTIME_TRACE | 1 | nrr062_historical |

## Data Quality Levels

| Level | Meaning | Safe use |
| --- | --- | --- |
| RAW_RUNTIME | Direct recorder, log, WAL, or journal capture preserved at source granularity. | Join source, audit source, immutable archive. |
| JOINED_RUNTIME | Deterministic row-level join across raw runtime surfaces with stable keys and lineage. | Attempt or trade datasets, fee-aware analysis, causal decision datasets. |
| DERIVED_LABELLED | Joined runtime with future labels or realized outcomes added. | Threshold search, model fitting, walk-forward validation, candidate ranking. |
| REPLAY_GENERATED | Replay or simulation output produced from frozen raw or joined inputs. | Counterfactual search and acceptance research only when replay version and config are pinned. |
| OUTSIDE_LADDER | External raw caches or ad hoc calibration artifacts not yet canonical training truth. | Bootstrap inputs and diagnostics only. |

External raw exchange caches such as data/raw/binance_um_klines are intentionally outside the main ladder until they are normalized and replay rules are frozen.

## Shared Surface Inventory

| Surface | Kind | Quality | Primary consumers | Key note |
| --- | --- | --- | --- | --- |
| data/recorder/YYYY-MM-DD/SYMBOL_TF.csv | B.derived_features | RAW_RUNTIME | thresholds, regime, signal, md_amr, mean_reversion, objective, system_stress, phase2b | Mixed row with OHLCV, feature columns, readiness, and inline regime state. |
| logs/aurora_core.log* | M.unknown_or_mixed | RAW_RUNTIME | aurora_thresholds | Text log only; not a stable row contract. |
| logs/features/SYMBOL.log | B.derived_features | RAW_RUNTIME | aurora_thresholds | Structured JSON lines with decimal-string payloads. |
| logs/ta_features/SYMBOL.jsonl | B.derived_features | RAW_RUNTIME | aurora_thresholds | Dataset-friendly TA rows, but still lacks split and lineage metadata. |
| data/raw/binance_um_klines/SYMBOL/1m/YYYY-MM.json | A.raw_market_data | OUTSIDE_LADDER | nrr062_historical | Real exchange market data, but not Phenix runtime truth. |
| data/processed/nrr062_historical_calibration/SYMBOL_TF.csv | K.replay_simulation_output | REPLAY_GENERATED | nrr062_historical | Generated intermediate, not authoritative raw input. |
| ops/wal/YYYY-MM-DD.jsonl | M.unknown_or_mixed | RAW_RUNTIME | objective_stack | Objective stack defaults here; top-level wal/ is absent. |
| data/authority_request_journal_v1.jsonl | E.trade_intent_trace | RAW_RUNTIME | future objective and low-vol builders | Strong present-day intent trace, not consumed directly yet. |
| data/authority_response_journal_v1.jsonl | E.trade_intent_trace | RAW_RUNTIME | future objective and low-vol builders | Natural pair to the request journal. |
| data/order_ledger.db | F.order_execution_trace | RAW_RUNTIME | objective_stack | Current builder reads the full orders table contractually via SELECT *. |
| logs/order_log_v1.jsonl | F.order_execution_trace | RAW_RUNTIME | low_vol_cost_floor | Direct order trace surface. |
| logs/trade_lifecycle.jsonl | G.position_lifecycle_trace | RAW_RUNTIME | low_vol_cost_floor | Sampled rows are mixed sidecar traces, not a closure-only feed. |
| logs/regime_confidence_audit_v1.jsonl | C.labelled_regime_data | RAW_RUNTIME | low_vol_cost_floor | Best present regime confidence audit surface. |
| logs/shadow_telemetry/decision_ledger_v1.jsonl | H.realized_outcome_trace | JOINED_RUNTIME | future objective and low-vol builders | Strongest joined runtime outcome surface currently present. |
| reports/executed_trades_master.csv and siblings | H.realized_outcome_trace | JOINED_RUNTIME | low_vol_cost_floor | Same wide CSV schema reused across three files; semantics depend on filename. |
| artifacts/strategy_calibration/**/* | L.calibration_output | DERIVED_LABELLED | md_amr_phase2b | Phase 2B reuses base calibration artifacts rather than a canonical dataset. |

## Per-Calibrator Dataset Map

### aurora_thresholds

- Path: calibrators/strategies/calibrate_aurora_thresholds.py
- Primary inputs: recorder bars, aurora_core log lines, feature logs, TA feature logs.
- Labels or outcomes: internal forward-return proxy over train, validation, and forward windows.
- Artifacts: candidate_aurora_threshold_overlay.yaml, candidate_threshold_overlay.yaml, run_manifest.json, baseline_metrics.json, candidate_metrics.json, validation_metrics.json, forward_metrics.json, report.md.
- Tests: tests/tools/test_aurora_threshold_calibrator.py uses synthetic tmp_path fixtures and verifies canonical YAML immutability.
- Readiness: NEEDS_JOINED_DATASET.
- Smallest next dataset: calibration_feature_snapshot_dataset_v1.
- Main gap: the input contract is fragmented across text logs, feature logs, and recorder rows.

### aurora_regime_params

- Path: calibrators/regimes/calibrate_aurora_regime_params.py
- Primary inputs: recorder bars only.
- Labels or outcomes: internal oracle regime labels from future bars.
- Artifacts: report.md, candidate_regime_overlay.yaml, best_trial.json.
- Tests: no dedicated test file was found during this audit.
- Readiness: READY_WITH_EXISTING_DATA.
- Smallest next dataset: calibration_oracle_regime_labels_v1.
- Main gap: schema hardening and missing tests, not missing runtime truth.

### aurora_signal_weights

- Path: calibrators/strategies/calibrate_aurora_signal_weights.py
- Primary inputs: recorder bars and SSOT Aurora YAML.
- Labels or outcomes: internal forward-return proxy with explicit cost_bps assumption.
- Artifacts: none on disk; the script prints advisory research-only candidate YAML to stdout.
- Tests: no dedicated test file was found during this audit.
- Readiness: NEEDS_LABELLED_OUTCOMES.
- Smallest next dataset: calibration_feature_snapshot_dataset_v1.
- Main gap: there is no frozen labelled dataset contract or file artifact set, so outputs remain advisory only.

### md_amr_weights

- Path: calibrators/strategies/calibrate_md_amr_weights.py
- Primary inputs: recorder 900-second bars plus computed MD-AMR features; optional hydration path exists but is not required.
- Labels or outcomes: replay-generated baseline, candidate, validation, and forward metrics.
- Artifacts: run_manifest.json, baseline_metrics.json, candidate_metrics.json, validation_metrics.json, forward_metrics.json, candidate_md_amr_strategy_overlay.yaml, per_regime_analysis.json, report.md.
- Tests: tests/tools/test_md_amr_weight_calibrator.py uses synthetic recorder fixtures and real config anchors for immutability checks.
- Readiness: NEEDS_REPLAY_HARNESS.
- Smallest next dataset: calibration_feature_snapshot_dataset_v1.
- Main gap: replay inputs are still implicit and optional hydration can change the effective dataset unless frozen.

### mean_reversion_params

- Path: calibrators/strategies/calibrate_mean_reversion_params.py
- Primary inputs: recorder 300-second bars plus replay logic; optional hydration path exists but is not required.
- Labels or outcomes: replay-generated baseline, candidate, validation, and forward metrics with optional TPSL and MFE/MAE analyses.
- Artifacts: run_manifest.json, baseline_metrics.json, candidate_metrics.json, validation_metrics.json, forward_metrics.json, candidate_mean_reversion_strategy_overlay.yaml, candidate_mean_reversion_overlay.yaml, report.md, best_trial.json, candidate_bundle.json, tpsl_surface.json, mfe_mae_analysis.json, per_regime_analysis.json.
- Tests: tests/tools/test_mean_reversion_param_calibrator.py uses synthetic recorder fixtures and real config anchors for immutability checks.
- Readiness: NEEDS_REPLAY_HARNESS.
- Smallest next dataset: calibration_feature_snapshot_dataset_v1.
- Main gap: trustworthy promotion still needs frozen replay inputs and explicit cost-assumption manifests.

### nrr062_historical

- Path: calibrators/policy_gates/calibrate_nrr062_historical.py
- Primary inputs: data/raw/binance_um_klines plus processed normalized bars emitted under data/processed/nrr062_historical_calibration.
- Labels or outcomes: candle-only low-vol gate evaluation with candidate_rows frontier output and holdout report.
- Artifacts: normalized per-symbol bar CSVs, candidate_rows.csv, reports/NRR062_HISTORICAL_CALIBRATION_REPORT.md, reports/NRR062_CONFIG_PATCH_CANDIDATE.yaml, artifacts/nrr062_historical_calibration/results.json.
- Tests: tests/tools/test_calibrate_nrr062_historical.py uses synthetic bars and patched runtime helpers rather than real raw files.
- Readiness: BLOCKED_BY_MISSING_RUNTIME_TRACE.
- Smallest next dataset: calibration_low_vol_gate_dataset_v1.
- Main gap: the script explicitly cannot reconstruct live OBI, TFI, depth imbalance, or macro residual inputs, so it cannot yet be treated as a trustworthy promotion surface.

### objective_stack

- Path: calibrators/strategies/calibrate_objective_stack.py
- Primary inputs: recorder bars, ops/wal, and data/order_ledger.db.
- Labels or outcomes: joined attempted_entries and realized_trades datasets built from runtime truth surfaces.
- Artifacts: dataset/attempted_entries.csv, dataset/realized_trades.csv, dataset/manifest.json, candidate_bundle.json, overlay YAML files, report.md.
- Tests: tests/tools/test_objective_calibration.py uses synthetic recorder, WAL, and SQLite fixtures plus real config anchors for immutability.
- Readiness: NEEDS_JOINED_DATASET.
- Smallest next dataset: calibration_realized_trade_dataset_v1.
- Main gap: the dataset contract exists only in builder code, while WAL and ledger source schemas remain implicit.

### system_stress_weights

- Path: calibrators/policy_gates/calibrate_system_stress_weights.py
- Primary inputs: recorder bars and optional frozen dataset-manifest.
- Labels or outcomes: oracle-labelled walk-forward metrics across research or acceptance mode.
- Artifacts: walkforward_metrics.csv, yaml_patch_snippet.yaml, candidate_summary.json, candidate_metrics.json, report.md.
- Tests: tests/test_system_stress_calibration.py uses synthetic recorder fixtures and temporary manifests.
- Readiness: READY_WITH_EXISTING_DATA.
- Smallest next dataset: calibration_walkforward_manifest_v1.
- Main gap: the dataset-manifest contract is enforced in code but not documented as a canonical dataset schema.

### md_amr_phase2b

- Path: calibrators/strategies/run_md_amr_phase2b_aggression_grid.py
- Primary inputs: recorder bars plus base MD-AMR calibration artifacts.
- Labels or outcomes: replay-generated candidate ranking, data-quality summaries, and per-family aggression-grid reports.
- Artifacts: phase2b_candidate_summary.json, candidate_ranking.json, candidate_ranking.csv, per-run report.md, reports/MD_AMR_PHASE2B_DATA_QUALITY_REPORT.md, reports/MD_AMR_PHASE2B_BASELINE_CONFIRMATION_REPORT.md, reports/MD_AMR_PHASE2B_AGGRESSION_GRID_REPORT.md, reports/MD_AMR_PHASE2B_CANDIDATE_OVERLAYS_REPORT.md.
- Tests: tests/tools/test_md_amr_phase2b_aggression_grid.py uses tmp_path recorder fixtures.
- Readiness: NEEDS_REPLAY_HARNESS.
- Smallest next dataset: calibration_feature_snapshot_dataset_v1.
- Main gap: it reuses base calibration artifacts instead of consuming a frozen canonical dataset directly.

### low_vol_cost_floor

- Path: calibrators/policy_gates/calibrate_low_vol_cost_floor.py
- Primary inputs: logs/order_log_v1.jsonl, logs/trade_lifecycle.jsonl, logs/regime_confidence_audit_v1.jsonl, reports/executed_trades_master.csv, reports/rejected_attempts_master.csv, reports/order_attempts_master.csv, and recorder bars.
- Labels or outcomes: joined realized and counterfactual outcome table with fee-aware candidate thresholds.
- Artifacts: low_vol_trade_dataset.csv, low_vol_threshold_candidates.json, low_vol_candidate_yaml_patch.yaml, LOW_VOL_DATA_INVENTORY_REPORT.md, LOW_VOL_COST_FLOOR_CALIBRATION.md.
- Tests: tests/test_calibrate_low_vol_cost_floor.py uses synthetic logs and reports fixtures plus real repo YAML immutability checks.
- Readiness: NEEDS_JOINED_DATASET.
- Smallest next dataset: calibration_low_vol_gate_dataset_v1.
- Main gap: trustworthy calibration currently depends on filename-based report joins, mixed lifecycle traces, and fee-sensitive assumptions rather than a single canonical joined runtime dataset.

## Proposed Canonical Dataset Schemas

### calibration_market_bar_dataset_v1

- Target quality: RAW_RUNTIME.
- Source surfaces: recorder_bars and raw_binance_um_klines.
- Key fields: source_surface, source_file, session_date, symbol, tf_sec, ts_ms, bar_close_ts_ms, open, high, low, close, volume, trade_count.
- Primary use: deterministic bar truth for regime, replay, and oracle-labelled calibrators.

### calibration_feature_snapshot_dataset_v1

- Target quality: JOINED_RUNTIME.
- Source surfaces: recorder_bars, feature_logs, ta_feature_logs.
- Key fields: symbol, tf_sec, ts_ms, close, feat_obi, feat_tfi, feat_delta_price, feat_absorption, feat_depth_imbalance, feat_spread_bps, feat_macro_sync, feat_macro_resid, ready, not_ready_reasons, regime, regime_conf.
- Primary use: freeze the feature vector surface for threshold and replay calibrators.

### calibration_oracle_regime_labels_v1

- Target quality: DERIVED_LABELLED.
- Source surfaces: calibration_market_bar_dataset_v1.
- Key fields: symbol, tf_sec, ts_ms, horizon_bars, future_return_bps, future_volatility_bps, flip_rate, oracle_regime, label_version, split_bucket.
- Primary use: explicit future-label dataset for regime, signal, and system-stress calibrators.

### calibration_trade_decision_dataset_v1

- Target quality: JOINED_RUNTIME.
- Source surfaces: authority journals, ops_wal, order_log_v1, decision_outcome_ledger.
- Key fields: decision_id, rid, symbol, strategy_id, side, proposed_action, decision_basis_ts_ms, request_ts_ms, response_ts_ms, authority_mode, action, apply_result, reason_code, dataset_visibility, observation_causal.
- Primary use: canonical intent-level dataset for objective and low-vol builders.

### calibration_realized_trade_dataset_v1

- Target quality: DERIVED_LABELLED.
- Source surfaces: calibration_trade_decision_dataset_v1, order_ledger_db, attempt_master_reports, trade_lifecycle, decision_outcome_ledger.
- Key fields: attempt_id, decision_id, rid, symbol, strategy_id, side, intent_ts_ms, entry_ts_ms, exit_ts_ms, outcome, exit_price, realized_pnl_net, fees, commission, exact_roundtrip, terminal_status, source_surface.
- Primary use: objective search and fee-aware trade calibration.

### calibration_low_vol_gate_dataset_v1

- Target quality: DERIVED_LABELLED.
- Source surfaces: calibration_realized_trade_dataset_v1, regime_confidence_audit, recorder_bars.
- Key fields: attempt_id, symbol, strategy_id, regime, regime_confidence, direction_confidence, target_net_fee_multiple, required_gross_tp_bps_floor, min_rr, gross_tp_bps, realized_pnl_net, commission, outcome, counterfactual_source, exact_roundtrip.
- Primary use: trustworthy low-vol fee-floor calibration and any future NRR062 runtime-backed recalibration.

### calibration_walkforward_manifest_v1

- Target quality: DERIVED_LABELLED.
- Source surfaces: any canonical dataset above.
- Key fields: dataset_id, source_dataset, train_start, train_end, validation_start, validation_end, forward_start, forward_end, excluded_sessions, label_horizon_bars, config_snapshot.
- Primary use: freeze split policy across all replay and threshold calibrators.

## Gap Analysis

- Canonical joined runtime datasets are missing exactly where trust is weakest: objective_stack and low_vol_cost_floor both rely on multi-source joins that currently exist only in code or report filenames.
- Replay-driven calibrators are already structurally close to a dataset layer, but md_amr_weights, mean_reversion_params, and md_amr_phase2b still need frozen replay manifests to remove hidden hydration and split drift.
- aurora_thresholds is the main mixed-surface strategy calibrator. Its decision input surface is split across aurora_core text logs, feature logs, and recorder rows.
- aurora_signal_weights is still a legacy research CLI. It needs an explicit labelled dataset contract before its outputs should be treated as anything beyond advisory experiments.
- nrr062_historical is the single hard blocker. It is useful as a diagnostic frontier builder, but not as a trustworthy policy-promotion surface until live low-vol gate inputs are captured in a canonical runtime dataset.
- Dedicated test coverage is missing for aurora_regime_params and aurora_signal_weights.
- A residual non-package finding remains outside scope: scripts/calibration/calibrate_low_vol_cost_floor.py showed external bootstrap-order drift during this audit. That was not changed here because this package is audit-only.

## Synthetic Data Boundaries

- Synthetic data is appropriate for parser validation, schema validation, join-key edge cases, malformed-row handling, YAML immutability checks, and deterministic split logic.
- Synthetic data is not sufficient for fee-aware low-vol calibration, objective candidate ranking intended for promotion, NRR062 acceptance, or claims about live microstructure equivalence.
- Any synthetic dataset used for calibrator testing should carry explicit synthetic provenance, data_origin, supports_counterfactual_join, dataset_visibility, and observation_causal markers.
- Policy-gate scenario coverage should include allow, reject, timeout_non_fill, take_profit, stop_loss, and manual or timeout close.
- Regime coverage should include LOW_VOLATILITY, HIGH_VOLATILITY, TREND_UP, TREND_DOWN, MEAN_REVERSION, and UNCERTAIN.
- Strategy coverage should include aurora, md_amr, and mean_reversion.
- Lifecycle coverage should include decision_only, ordered_not_filled, partial_fill, full_fill, and reduce_only_close.

## Next Package Recommendations

1. CALIBRATORS_FOUNDATION_PACKAGE_03_CANONICAL_DATASET_SCHEMAS
Create the documented schema specs and builders under calibrators/datasets for the seven proposed dataset contracts.

2. CALIBRATORS_FOUNDATION_PACKAGE_04_OBJECTIVE_LOWVOL_JOIN_BUILDERS
Implement canonical joined runtime datasets for objective_stack and low_vol_cost_floor from authority journals, WAL, ledger, master CSVs, and decision ledger surfaces.

3. CALIBRATORS_FOUNDATION_PACKAGE_05_REPLAY_FREEZE_MANIFESTS
Freeze replay inputs and walk-forward manifests for md_amr, mean_reversion, aurora_thresholds, and phase2b so that no hidden hydration or split drift remains.

4. CALIBRATORS_FOUNDATION_PACKAGE_06_NRR062_RUNTIME_TRACE_RECOVERY
Bridge low-vol runtime decision traces to real gate inputs so NRR062 can move from candle-only diagnostics toward a trustworthy policy-gate calibration surface.
