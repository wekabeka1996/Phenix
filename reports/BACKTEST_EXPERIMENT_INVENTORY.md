# BACKTEST EXPERIMENT INVENTORY

## 0. Purpose

This inventory separates existing research artifacts into:

- primary evidence: directly usable experimental or runtime evidence
- secondary evidence: summaries, runbooks, or interpretations built on top of other artifacts

The goal is to preserve what is already proven and stop re-discovering findings from scratch.

## 1. Primary Evidence Clusters

### 1.1 Current backtest bundles: `reports/backtests/`

Current active backtest evidence is the strongest evidence class in the repo.

Observed on disk:

- 25 timestamped bundle directories from `20260305_045933` through `20260313_031152`
- matching `backtest_<run_id>.json` summary files
- sidecar stdout captures such as `Q1_patched5_stdout.txt`, `Q1_patched6_stdout.txt`, `March2024_patched7_stdout.txt`, `March2024_2_patched7_stdout.txt`

Why this matters:

- each bundle preserves metrics, resolved config, manifest, and result payloads
- these files are the closest thing to current executable truth without re-running anything

Recommended baseline evidence subset:

- `reports/backtests/backtest_20260312_132130.json`
- `reports/backtests/20260312_132130/manifest.json`
- `reports/backtests/20260312_132130/resolved_config.json`
- `reports/backtests/20260312_132130/result.json`
- `logs/backtests/order_log_20260312_132130.jsonl`

These files together form the best current March side B reference set.

### 1.2 Historical backtest archive: `reports/arhive/backtests/`

The archive contains the earlier research wave before the current March/Q1/Q2 forensic cycle.

Observed on disk in `reports/arhive/`:

- 12 backtest summary JSON files at the top level
- a `backtests/` archive directory
- `backtest_ladder_manifest.json`
- `backtest_ladder_report.md`

Why this matters:

- this is primary historical evidence for the progression from earlier patched baselines into later forensic iterations
- it remains useful for cross-period comparison, but it is not current runtime truth by itself

### 1.3 Regime/statistical parquet studies: `reports/arhive/*.parquet` and manifests

Observed on disk:

- `regime_grid_*.parquet`
- `regime_grid_results.parquet`
- `r3_forward_separability_*.parquet`
- `r3_forward_separability_results.parquet`
- `r3a_edge_*.parquet`
- `r3a_aurora_policy_*.parquet`
- `r3a_mr_policy_*.parquet`
- manifests such as `regime_grid_manifest.json`, `r3_forward_separability_manifest.json`, `r3a_manifest.json`

Why this matters:

- these are direct data products, not prose summaries
- they preserve the regime-label and forward-return studies that drove the current 48/192 trend basis and policy-table logic

These files are primary evidence for regime research even if they are not execution artifacts.

### 1.4 Optuna outputs: `runs/optuna/`

Observed on disk:

- `best_regime_patch.yaml`
- `best_strategy_patch.yaml`
- `pipeline_report.yaml`
- `production_patch.yaml`
- `stage2_report.yaml`

Why this matters:

- these files preserve what automated sweeps selected as winning patches or candidate overlays
- they are primary optimization outputs, though they still require verification against the current runtime path

## 2. High-Value Secondary Evidence

### 2.1 Calibration synthesis

The strongest synthesis artifact from the earlier regime research wave is:

- `reports/arhive/aurora_weight_calibration_decision.md`

Why it matters:

- it compiles R2, R3-B, and R3-A-lite into actionable recommendations
- it is not primary runtime evidence, but it is a high-value interpretation layer over primary statistical outputs

### 2.2 Recent forensic postmortems

Strong recent secondary evidence in `reports/` includes:

- `reports/aurora_forensic_regime_entry_exit_flip_analysis.md`
- `reports/eth_trend_down_march_2024_postmortem.md`
- `reports/eth_trend_down_semantics_janfeb_vs_march.md`
- `reports/eth_trend_down_counterfactual.md`
- `reports/patched5_q4_research.md`
- `reports/patched5_q1_regime_research.md`
- `reports/patched5_q1_research_addendum.md`

Why they matter:

- they already localize the most important failure mode clusters
- they should be used as guided evidence maps, not as SSOT without checking the underlying run bundles

### 2.3 Data integrity and operations evidence from the current conversation

Fresh secondary evidence now present in the repo:

- `reports/run_integrity_audit_20260312_132130_vs_20260313_031152.md`
- `reports/processed_data_coverage_audit_q2_2024.md`
- `reports/q2_processed_backfill_runbook_uk.md`

Why they matter:

- they establish the operational truth that Mar-Jun reporting can be invalid when data coverage stops in March
- they document the exact blocker for future Q2 / Apr-Jun research

## 3. What Each Evidence Cluster Proves

### 3.1 Current backtest bundles prove

- what config the run actually resolved
- what metrics the run actually produced
- what order-log and trade timelines really occurred

They do **not** by themselves prove that the run covered the intended full data window unless data coverage is independently validated.

### 3.2 Statistical parquet studies prove

- the historical behavior of regime labels and forward-return distributions
- cross-symbol policy suggestions for sizing and regime treatment

They do **not** prove end-to-end execution profitability under the current backtest engine.

### 3.3 Forensic markdown studies prove

- where past analysis attention has already converged
- which slices are most likely to matter economically

They do **not** replace the underlying run bundle or trade data.

### 3.4 Optuna outputs prove

- what the optimization framework selected at the time of those runs

They do **not** prove those patches remain valid against the current runtime, current universe, or current processed coverage.

## 4. Most Important Findings Already Recoverable From Existing Artifacts

### 4.1 Canonical side B changed materially over time

Older reports frequently discuss DOGE or other regimes as live contributors.

Current side B registry no longer includes DOGE in assignments, so any DOGE-heavy Q4 or early-Q1 finding must be treated as historical, not current-baseline truth.

### 4.2 ETH TREND_DOWN remains the main residual forensic target

This is supported across multiple existing artifacts:

- `reports/eth_trend_down_march_2024_postmortem.md`
- `reports/eth_trend_down_semantics_janfeb_vs_march.md`
- `reports/eth_trend_down_counterfactual.md`
- `reports/patched5_q1_research_addendum.md`

This cluster is large enough that new work should start from these findings rather than rediscovering the same March failure mode.

### 4.3 Regime research is already deep enough to support calibration hypotheses

The regime/statistical chain preserved under `reports/arhive/` already supports:

- the 48/192 trend basis
- volatility/state structure claims
- sizing-policy hypotheses

This means future experiments should focus on execution confirmation, not rebuilding R1/R2/R3 theory from zero.

### 4.4 Data coverage is now a first-class research constraint

The latest run-integrity and processed-coverage audits proved that missing parquet can silently corrupt benchmark validity.

Any future experiment inventory or comparison must record whether the run was:

- full-universe clean
- partial-universe degraded
- outright invalid for the claimed date window

## 5. Practical Evidence Ranking for Future Work

When making a claim about current backtest behavior, use this priority order:

1. current backtest bundle + order log + resolved config
2. processed data coverage audit
3. statistical parquet outputs and manifests
4. forensic markdown tied to a concrete run id
5. runbooks and concept docs

## 6. Recommended Baseline Evidence Package

If one compact package must anchor future strategy work, use:

- current March reference bundle: `20260312_132130`
- data-integrity blockers: the three audit reports from this conversation
- statistical foundation: `regime_grid_report.md`, `r3_forward_separability_report.md`, `r3a_market_policy_tables.md`
- key forensic cluster: the ETH TREND_DOWN March reports
- optimization outputs in `runs/optuna/` as tertiary comparison only

## 7. Final Inventory Verdict

The repo already contains enough evidence to define a research baseline.

What is missing is not evidence volume. What is missing is disciplined ranking of evidence quality and explicit labeling of degraded versus canonical runs.