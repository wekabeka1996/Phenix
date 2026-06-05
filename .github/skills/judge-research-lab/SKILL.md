---
name: judge-research-lab
description: Use when analyzing Judge decisions, comparing confidence buckets, inspecting all available shadow plans, classifying winners and losers, running sidecar counterfactual calibration, auditing freshness and lineage, analyzing features like obi/tfi/macro_resid, and building research-only Judge or alpha_search canary candidate reports without changing trading behavior.
---

# Judge Research Lab Skill

## Purpose

Standardize repository-local Judge and alpha_search research workflows so future agents can answer short research requests without rediscovering:

- source files
- corpus-building commands
- grouping logic
- evidence-class boundaries
- output contracts
- safety warnings

This skill is research-only.

## Scope

- all-available Judge corpus building
- confidence bucket analysis
- cross-asset feature and outcome analysis
- sidecar counterfactual calibration
- loss cluster atomization
- winner path forensics
- stale and freshness lineage audit
- candidate canary selection
- report generation under reports/judge/

## When to use this skill

Use when the user asks to:

- analyze Judge decisions
- compare confidence buckets
- inspect all available shadow plans
- classify winners or losers
- find best symbol, confidence, tf, or scenario candidates
- analyze features such as obi, tfi, macro_resid, depth_imbalance, delta_price, or pillar_sum
- run sidecar counterfactual analysis
- build a canary candidate report
- understand why Judge won or lost
- check data freshness, regime joins, or Policy Cortex status

## When NOT to use this skill

- enabling Judge authority
- changing live or testnet trading behavior
- changing production YAML
- starting any runtime service
- promoting a candidate to live or testnet
- making claims of production readiness or proven alpha

## Required inputs

- analysis intent
- optional slice filters such as symbol, date, tf_sec, side, regime, confidence range, or scenario name

If the user does not specify filters, default to:

- all available Judge shadow-plan files in logs/judge_experts/
- current recorder-backed replay scope only
- existing reports/judge/ artifacts when they already match the requested scope

If required artifacts are missing, output MUST start with:

BLOCKED: missing <exact paths>

## Repository anchors

Primary discovery and analysis surfaces:

- logs/judge_experts/shadow_entry_plan_*.jsonl
- logs/judge_experts/verdict_*.jsonl
- logs/judge_experts/envelope_*.jsonl
- logs/judge_experts/chamber_*.jsonl
- logs/judge_experts/policy_cortex_*.jsonl
- logs/judge_experts/judge.signal_weights_v1_*.jsonl
- logs/judge_experts/judge.feature_neutrals_v1_*.jsonl
- data/recorder/YYYY-MM-DD/SYMBOL_TFSEC.csv
- logs/regime_confidence_audit_v1.jsonl
- reports/judge/

Preferred tool anchors already present in this repo:

- tools/judge/build_judge_aurora_joint_calibration_current_window.py
- tools/judge/analyze_shadow_plan_file.py
- tools/judge/sidecar_shadow_counterfactual.py
- tools/judge/sidecar_shadow_counterfactual_batch.py
- tools/judge/build_path_diagnostics.py
- tools/judge/build_review_baselines_current_window.py

Repository-specific discovery rule:

- prefer directory listing on logs/judge_experts/ for shadow_entry_plan discovery in this repo
- do not rely on broad file_search alone for shadow_entry_plan_*.jsonl discovery

## Evidence classes

Every dataset row, grouped table, and report MUST preserve exactly one evidence_class:

- shadow_plan_only
- coarse_replay_outcome
- sidecar_counterfactual
- real_order_outcome
- diagnostic_only

Default evidence-class mapping in this repo:

- raw shadow_entry_plan, verdict, envelope, chamber, Policy Cortex, and expert outputs without replayed outcome: shadow_plan_only
- analyze_shadow_plan_file and current-window Judge vs Aurora joint corpus: coarse_replay_outcome
- sidecar_shadow_counterfactual and sidecar_shadow_counterfactual_batch outputs: sidecar_counterfactual
- order_log_v1.jsonl or trade_lifecycle.jsonl based realized trade analysis: real_order_outcome
- build_path_diagnostics and similar geometry-only artifacts: diagnostic_only

Never merge evidence classes in one conclusion without labeling the weaker class explicitly.

## Default workflow

### A. Discover available sources

Always inventory these surfaces first:

- logs/judge_experts/shadow_entry_plan_*.jsonl
- logs/judge_experts/verdict_*.jsonl
- logs/judge_experts/envelope_*.jsonl
- logs/judge_experts/chamber_*.jsonl
- logs/judge_experts/policy_cortex_*.jsonl
- logs/judge_experts/judge.signal_weights_v1_*.jsonl
- logs/judge_experts/judge.feature_neutrals_v1_*.jsonl
- data/recorder/**/*.csv
- logs/regime_confidence_audit_v1.jsonl
- reports/judge/** existing counterfactual and forensic outputs

Discovery principle:

- reuse existing official reports first when scope already matches
- rerun only the minimal missing layer

### B. Build or refresh corpus

Preferred corpus-build order:

1. Current-window all-available joint corpus

   Command:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.judge.build_judge_aurora_joint_calibration_current_window
   ```

   Primary outputs:

   - reports/judge/judge_aurora_joint_calibration_current_window/report.md
   - reports/judge/judge_aurora_joint_calibration_current_window/summary.json
   - reports/judge/judge_aurora_joint_calibration_current_window/per_plan_joint_rows.csv
   - reports/judge/judge_aurora_joint_calibration_current_window/per_plan_joint_rows.jsonl

2. Single-file detailed Judge-plan corpus

   Command:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.judge.analyze_shadow_plan_file --shadow-plan-file logs/judge_experts/shadow_entry_plan_XRPUSDT_2026-05-24.jsonl
   ```

   Primary outputs:

   - reports/judge/shadow_entry_plan_<SYMBOL>_<DATE>/report.md
   - reports/judge/shadow_entry_plan_<SYMBOL>_<DATE>/summary.json
   - reports/judge/shadow_entry_plan_<SYMBOL>_<DATE>/per_plan_rows.csv
   - reports/judge/shadow_entry_plan_<SYMBOL>_<DATE>/per_plan_rows.jsonl

3. Sidecar counterfactual single-file analysis

   Command:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.judge.sidecar_shadow_counterfactual --shadow-plan-file logs/judge_experts/shadow_entry_plan_XRPUSDT_2026-05-24.jsonl
   ```

4. Sidecar counterfactual all-available batch analysis

   Command:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.judge.sidecar_shadow_counterfactual_batch
   ```

   Primary outputs:

   - reports/judge/sidecar_shadow_counterfactual_batch_all_available/report.md
   - reports/judge/sidecar_shadow_counterfactual_batch_all_available/summary.json
   - reports/judge/sidecar_shadow_counterfactual_batch_all_available/aggregate_calibration_grid.csv
   - reports/judge/sidecar_shadow_counterfactual_batch_all_available/per_file_recommendations.csv

5. Strict 1m path geometry diagnostics when official candle outcomes are available

   Command pattern:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.judge.build_path_diagnostics --outcomes-path data/simulator/outcomes.json --manifest-path data/simulator/outcomes_manifest.json --outcomes-diagnostics-path data/simulator/outcomes_diagnostics.jsonl --judge-log-dir logs/judge_experts --raw-1m-dir data/raw_binance_klines_1m --recorder-1m-dir data/recorder_backfill_1m --simulator-config config/judge_simulator.yaml --diagnostics-out data/simulator/judge_path_diagnostics.jsonl --summary-out data/simulator/judge_path_diagnostics_summary.json --report-path reports/PKG_5_JUDGE_PATH_DIAGNOSTICS_REPORT.md
   ```

Corpus row requirements:

- one row per Judge plan or verdict source
- include symbol, date, tf_sec, side, confidence, tier, and bucket
- include regime, policy, freshness, and join status
- include feature values rounded to 3 or 4 decimals in report tables
- include enabled, disabled, shadow, diagnostic, or blocked classification when known
- include replayed outcomes and scenario results when available

### C. Filter requested slice

Always support filters by:

- confidence range such as 0.6-0.9
- symbol such as XRPUSDT
- tf_sec such as 300
- side such as SELL
- envelope_regime such as LOW_VOLATILITY
- recorder_regime_join_status such as MISSING
- top_support_feature such as obi
- scenario_name such as sidecar_pct_0.40_gb_80

If the user gives a broad request, start from all available and narrow only after the initial grouped summary.

### D. Run analysis modules

Standard module set:

- confidence bucket report
- cross-asset report
- feature contribution and outcome report
- sidecar counterfactual report
- winner forensic report
- loss forensic report
- freshness and lineage report
- candidate canary shortlist

Module selection rules:

- use the joint current-window corpus for broad Judge vs Aurora alignment questions
- use per-plan detailed rows for feature, dissent, freshness, and policy context questions
- use sidecar counterfactual outputs for exit-policy and managed-exit questions
- use path diagnostics only when strict 1m outcome geometry is required and artifacts exist

### E. Produce standard outputs

Every non-trivial run should materialize:

- markdown report
- summary.json
- grouped csv tables
- per-row jsonl or csv dataset
- AGENT_REPORT_V1 companion section or companion markdown report

Preferred output location:

- reports/judge/<report_name>/ for multi-artifact runs
- reports/judge/<REPORT_NAME>.md for report-only outputs

## Required grouping dimensions

Always support grouping by:

- symbol
- date
- tf_sec
- side
- confidence_bucket
- confidence_tier
- envelope_regime
- recorder_regime
- recorder_regime_join_status
- policy_cortex_label
- top_support_feature
- top_oppose_feature
- scenario_name
- terminal_reason
- data_quality_issue

If a dimension is unavailable in the current evidence class, record it as unavailable rather than silently dropping it.

## Standard confidence buckets

Use exactly these Judge confidence buckets:

- 0.3-0.4
- 0.4-0.5
- 0.5-0.6
- 0.6-0.7
- 0.7-0.8
- 0.8-0.9
- 0.9-1.0

Rules:

- do not assume higher confidence is better
- always compute total net pnl and expectancy by bucket
- always check for confidence misordering
- if ordering is non-monotonic, say so explicitly

Confidence misordering rule:

- if a higher-confidence bucket has lower expectancy or lower total-net quality than a lower bucket, report confidence_misordering_detected

## Feature interpretation rules

### Rounding

Round feature values in grouped tables as follows:

- normalized directional values: 4 decimals
- pct and bps values: 4 decimals
- prices: exchange precision or raw recorded precision if exchange precision is unknown

### Normalized feature buckets

Bucket normalized directional features as:

- strong_negative: <= -0.60
- negative: (-0.60, -0.20]
- neutral: (-0.20, 0.20)
- positive: [0.20, 0.60)
- strong_positive: >= 0.60

### Feature families

- order_flow: obi, tfi, depth_imbalance, large_trade_imbalance
- trend_price: delta_price, ema_bias, volatility_state
- macro_context: macro_sync, macro_resid
- tradeability: spread_bps, liquidity_kappa, volume_spike, volume_zscore
- policy_context: regime, regime_conf, policy_cortex_label, recorder_regime_join_status

### Per-feature audit fields

For every feature discussed in a report, record:

- produced yes or no
- retained yes or no
- consumed by Judge yes or no
- consumed by strategy or gate yes or no
- consumed by policy cortex yes or no
- can change decision yes or no
- status:
  - live_authoritative
  - live_veto_or_attenuation
  - shadow_only
  - diagnostic_only
  - retained_but_unjoined
  - unknown_requires_audit

### Deterministic status rules

- produced yes: feature exists in source feature-engineering payload or recorder feat_* column
- retained yes: feature survives into the current corpus row or retained report artifact
- consumed by Judge yes: feature is present in config/alpha_search.yaml Judge expert config and expert code path
- consumed by strategy or gate yes: feature is used by live strategy scoring, live gate logic, or live attenuation path
- consumed by policy cortex yes: feature contributes to surface-key or policy classification inputs
- can change decision yes: feature is live_authoritative, live_veto_or_attenuation, or changes the Judge shadow verdict path

Current repo anchor examples:

- pillar_sum: live_authoritative for Aurora, not currently consumed by Judge experts
- judge_confidence and strategy_confidence: shadow_only
- regime and regime_conf: usually live_veto_or_attenuation plus policy_context
- policy_cortex_label: shadow_only unless explicitly proven otherwise
- recorder_regime_join_status: diagnostic_only unless a runtime gate proves otherwise

If evidence is mixed or missing, use unknown_requires_audit.

## Mandatory warnings

Always warn if:

- a no-timeout scenario is being treated as live-safe
- Policy Cortex UNKNOWN is being treated as approval
- recorder_regime_join_status is MISSING
- tf_sec is 180 or 900 while regime context is effectively 300s-based only
- decision_ledger or authority artifacts show causal_state_missing flags
- subgroup sample size is below 30 rows
- a canary candidate has fewer than 100 rows
- a result comes from only one day or one symbol
- current-config result differs strongly from calibrated result

Strongly differs means at least one of:

- sign flip in total_net_pnl_pct
- sign flip in expectancy_net_pnl_pct
- absolute total_net_pnl_pct delta greater than 25 percent of the larger absolute baseline
- calibrated winner depends on scenario assumptions unavailable in live runtime

## Standard reports

### A. CROSS_ASSET_JUDGE_REPORT

Must answer:

- best buckets by total net
- best buckets by expectancy
- best symbols
- worst symbols
- best tf_sec
- bad confidence zones
- feature winners
- feature risk flags
- canary shortlist

Preferred evidence:

- coarse_replay_outcome for current-window Judge corpus
- sidecar_counterfactual when scenario comparisons are included

### B. FEATURE_OUTCOME_REPORT

Must answer:

- which features are useful
- which features are unstable
- which features are noisy
- which feature combinations imply WAIT, TRADE, or NO_ENTRY

### C. SIDECAR_COUNTERFACTUAL_REPORT

Must compare:

- baseline_timeout_12
- no_timeout_hold_to_data_end
- current config candidate
- calibrated sidecar candidates
- dynamic SL or TP candidates if available

### D. LOSS_CLUSTER_FORENSIC_REPORT

Must answer:

- largest repeated loss clusters
- whether fee-cover profit existed
- whether smaller-loss exit existed
- whether policy, recorder, or regime saw the state
- which feature or policy patterns dominate

### E. WINNER_PATH_FORENSIC_REPORT

Must answer:

- when winners first covered fees
- when peak occurred
- giveback after peak
- whether earlier TP would help
- whether dynamic SL would harm winners

### F. CANARY_SELECTION_REPORT

Must answer:

- best symbol, tf, confidence, and rule candidates
- blocked candidates
- research-only candidates
- required guardrails before testnet

Candidate selection rule:

- canary means research-only or testnet-canary candidate, never live approval

## Output contract

Every report must include:

- FACTS
- INFERENCES
- ASSUMPTIONS
- UNKNOWNS
- sample size
- source inventory
- evidence_class
- limitations
- next exact action

Every substantial output should also include an AGENT_REPORT_V1 section or companion file with:

- Executive Summary
- Proven Facts
- Inferred Findings
- Contradictions or Evidence Gaps
- Root Cause Candidates
- Operational Risk
- Files or Areas Touched
- Validation Performed
- Residual Risk
- What Remains Unproven
- Minimal Safe Verdict

Allowed verdict enum:

- CORPUS_READY
- SIGNAL_STABLE_ENOUGH_FOR_CANARY_REVIEW
- SIGNAL_NOT_STABLE
- FEATURE_SIGNAL_MIXED
- JOIN_GAPS_BLOCK_CONCLUSION
- INSUFFICIENT_DATA
- REPLAY_ONLY_NOT_RUNTIME_PROOF

## Safety rules

Never say:

- production-ready
- live alpha proven
- fixed
- profitable system proven

Allowed language:

- shadow evidence
- counterfactual candidate
- testnet canary candidate
- research-only candidate

Hard boundaries:

- do not change live trading logic
- do not change production YAML
- do not enable Judge authority
- do not start runtime
- do not promote any candidate to live or testnet

## Example user intents

If the user asks:

"проаналізуй всі Judge рішення"

- run corpus discovery plus a CROSS_ASSET_JUDGE_REPORT

"розбий по confidence"

- run a confidence bucket report

"чи 0.6-0.9 нормальний"

- run a confidence range stability report with monotonicity and misordering checks

"яка монета найкраща"

- build a symbol x confidence x scenario table

"чому збитки"

- run a LOSS_CLUSTER_FORENSIC_REPORT

"чому прибуткові"

- run a WINNER_PATH_FORENSIC_REPORT

"які фічі працюють"

- run a FEATURE_OUTCOME_REPORT

"що включати в testnet"

- run a CANARY_SELECTION_REPORT with research-only guardrails

## Failure handling

If source artifacts are missing or too weak for the requested conclusion:

- fail closed
- state the missing artifacts explicitly
- downgrade the verdict
- preserve the strongest evidence_class actually available
- do not silently substitute weaker evidence without saying so

If required artifacts are missing, output MUST start with:

BLOCKED: missing <exact paths>
