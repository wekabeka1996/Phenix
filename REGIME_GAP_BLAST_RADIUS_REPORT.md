# Blast Radius Audit

## Regime Gap Across Aurora, Mean Reversion, and MD-AMR

## Verdict

The suspected regime-gap issue is not a single defect class.

- The PENDING and missing-regime findings in recorder and order-flow artifacts are primarily an observability artifact, not proof that live strategy paths ran without regime.
- The real live-path defect is a bounded runtime and economic suppression effect caused by detector hysteresis and carry semantics: fresh raw regime can exist on a bar while the emitted regime remains UNCERTAIN or a prior cached stable regime.
- A true stale-context trading defect caused by a dead or missing detector heartbeat is not proven in the bounded evidence window. The code fail-closes that path, and no live heartbeat-dead markers were found in current logs.

Overall severity: P1.

Why not P0:

- No evidence of detector-dead / no-heartbeat live episodes.
- No evidence of 4h stale regime TTL breach in recorder rows.
- Rejected counterfactuals are mostly flat or capital-preserving, not a dominant missed-profit cluster.

Why not observability-only:

- Aurora shows real threshold, allowlist, and sizing-multiplier deltas under fresh-per-bar counterfactual.
- DOGE MR shows real gate-open deltas under fresh regime.
- XRP MD-AMR shows smaller but real gate-open deltas under fresh regime.

## Scope And Evidence Windows

Primary evidence windows used in this audit:

1. Live detector and recorder slice on 2026-04-15..2026-04-16 from [logs/domain_regime_detector.log](logs/domain_regime_detector.log) and data/recorder 300s CSVs.
2. Live decision-attempt forensic set from [reports/order_attempts_master.csv](reports/order_attempts_master.csv) and [reports/rejected_counterfactuals.csv](reports/rejected_counterfactuals.csv).
3. Runtime blocker and path artifacts from [reports/runtime_21h_blockers.csv](reports/runtime_21h_blockers.csv) and [reports/runtime_21h_md_amr_path.csv](reports/runtime_21h_md_amr_path.csv).
4. MD-AMR bounded recorder replay from [reports/md_amr_integrated_validation_summary.csv](reports/md_amr_integrated_validation_summary.csv).

Evidence limits:

- Aurora and MD-AMR economic evidence comes from forensic attempt datasets on 2026-04-12, while detector carry metrics come from the current 2026-04-15..16 live slice.
- MR DOGE was quantified at bar/gate level from [logs/mean_reversion/bars_300s.jsonl](logs/mean_reversion/bars_300s.jsonl), not by full downstream trade replay.

## Reasoning Protocol Outcome

### Symptom

- Recorder rows with regime=PENDING or join_status=MISSING.
- Order-flow report rows with missing regime tag.
- Live rejected intents from regime_confidence and regime-direction safety gates.

### Root Cause

- Recorder joins features and regime asynchronously and writes PENDING on timeout by design. See [apps/reference/domains/data_recorder/recorder.py](apps/reference/domains/data_recorder/recorder.py#L314) and [apps/reference/domains/data_recorder/docs/ARCHITECTURE.md](apps/reference/domains/data_recorder/docs/ARCHITECTURE.md#L9).
- Detector hysteresis emits a carried regime per bar. Fresh raw regime can disagree with emitted regime on the same bar. See [logs/domain_regime_detector.log](logs/domain_regime_detector.log#L4) and [logs/domain_regime_detector.log](logs/domain_regime_detector.log#L98).

### Contributing Factors

- Sparse regime propagation into text-log and order-flow artifacts. [reports/ORDER_FLOW_FINAL.md](reports/ORDER_FLOW_FINAL.md#L146-L157)
- Shared min_regime_confidence safety gate at 0.42. [config/aurora/domains.yaml](config/aurora/domains.yaml#L90-L93) and [apps/reference/domains/decision_making/safety_gates.py](apps/reference/domains/decision_making/safety_gates.py#L556-L590)
- MR fail-closed UNCERTAIN mapping. [apps/reference/domains/feature_engineering/regime_mapping.py](apps/reference/domains/feature_engineering/regime_mapping.py#L102-L119)

### Masking Layer

- Missing regime tags in order-flow tables are structural, not runtime truth. [reports/ORDER_FLOW_FINAL.md](reports/ORDER_FLOW_FINAL.md#L150-L157)
- PENDING in recorder is a join timeout marker, not proof that the strategy consumed no regime. [apps/reference/domains/data_recorder/recorder.py](apps/reference/domains/data_recorder/recorder.py#L314)

## Counterfactual Methodology

Actual runtime cohort:

- Use emitted detector regime and emitted_conf from REGIME_AUDIT rows.
- Use current strategy allowlists.
- Use current Aurora context_shield multipliers.
- Use shared min_regime_confidence threshold 0.42.

Counterfactual cohort:

- Replace emitted regime with fresh raw or pre_cutoff regime from the same detector bar.
- Replace emitted_conf with pre_cutoff_conf from the same detector bar.
- Leave all other bar inputs unchanged.

Interpretation rules:

- Bar blocked due to no regime: only counted when live evidence proves missing regime or missing heartbeat. Not inferred from recorder PENDING.
- Bar processed with stale regime: counted only if regime_age_ms exceeds Aurora stale TTL or detector heartbeat is missing. No such live case was observed in the bounded slice.
- Bar processed with uncertain regime: emitted regime is UNCERTAIN.
- Bar processed with cached prior regime: detector kind is hysteresis_carried and emitted regime differs from raw regime, especially raw=UNCERTAIN while emitted remains a prior stable regime.

MR join rule:

- DOGE MR bars were matched to detector rows by nearest timestamp within 15s.
- All joined DOGE bars matched within 15s, with observed nearest difference effectively 1 ms.

## Code Trace

Aurora regime dependencies:

- Cache update: [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L539-L575)
- Detector liveness fail-close: [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L447-L499)
- Strict allowlist gate: [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L718-L780)
- Context shield with no-regime and stale-regime attenuation: [apps/reference/domains/decision_making/shields/context_shield.py](apps/reference/domains/decision_making/shields/context_shield.py#L1-L117)

Mean Reversion regime dependencies:

- Cache update: [apps/reference/domains/decision_making/mean_reversion_handler.py](apps/reference/domains/decision_making/mean_reversion_handler.py#L1300-L1339)
- Bar-driven regime gate: [apps/reference/domains/feature_engineering/mean_reversion_strategy.py](apps/reference/domains/feature_engineering/mean_reversion_strategy.py#L385-L402)
- Regime mapping and UNCERTAIN fail-close: [apps/reference/domains/feature_engineering/regime_mapping.py](apps/reference/domains/feature_engineering/regime_mapping.py#L77-L119)

MD-AMR regime dependencies:

- Entry allowlist fail-close: [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py#L858-L900)
- Cache update: [apps/reference/domains/decision_making/md_amr_handler.py](apps/reference/domains/decision_making/md_amr_handler.py#L999-L1014)
- Context validity regime component: [apps/reference/domains/feature_engineering/md_amr_strategy.py](apps/reference/domains/feature_engineering/md_amr_strategy.py#L574-L585)

Objective-engine seam:

- Missing regime and missing regime_ts are hard precondition failures. [apps/reference/domains/decision_making/objective_gate_evaluator.py](apps/reference/domains/decision_making/objective_gate_evaluator.py#L120-L156)
- Staleness is penalized only through regime_age_sec. [apps/reference/domains/objective_engine/components/information.py](apps/reference/domains/objective_engine/components/information.py#L8-L31)

## Observability Findings

Recorder and order-flow artifacts do contain missing regime symptoms, but they do not prove live regime absence.

- Recorder active-symbol 300s rows on 2026-04-15..16: 799 / 7,835 rows were PENDING or join_status=MISSING, about 10.2%.
- Order-flow forensic report: missing regime tag is structural because text-log intent lines do not propagate regime. [reports/ORDER_FLOW_FINAL.md](reports/ORDER_FLOW_FINAL.md#L150-L157)
- No live detector-heartbeat-dead or no-heartbeat markers were found in the current logs, even though Aurora has a dedicated fail-closed liveness path. [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L447-L499)
- No 4h stale regime TTL breach was observed in recorder rows for active Aurora and MD-AMR symbols.

Conclusion for the forensic symptom layer:

- PENDING or missing regime in these artifacts is observability-only.

## Per-Strategy Impact Matrix

| Strategy | Active symbols used | Proven runtime effect | Quantified delta under fresh-per-bar regime | Economic evidence | Impact class | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| Aurora | ETH, SOL, XRP, BTC, BNB, DOGE | Yes | 34 / 1,776 bars would reopen confidence gate; 100 / 1,776 bars change allowlist outcome; 153 / 1,776 bars change context multiplier | 157 forensic attempts, 137 rejected; 76 confidence-gate rejects and 29 directional rejects | Runtime + economic, but conservative not toxic | P1 |
| Mean Reversion | DOGE | Yes | 14 / 245 bars become gate-open upper bound under fresh raw regime | No full downstream replay; only bar/gate evidence | Runtime proven, economic unproven | P2 |
| MD-AMR | XRP current live assignment | Yes, small | 8 / 296 bars would reopen confidence gate; 4 / 296 bars change allowlist outcome | 35 forensic attempts, 32 rejected; integrated replay shows zero trade delta and zero net-return delta for bounded MD-AMR context overlay | Runtime proven, strategy-local economics largely unproven or neutral | P2 |

## Per-Symbol Impact Matrix

Aurora current-assignment symbol results from live detector slice:

| Symbol | Bars | Actual UNCERTAIN bars | Carry bars | Fresh would reopen confidence gate | Allowlist delta bars | Context multiplier delta bars | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BNBUSDT | 296 | 30 | 51 | 2 | 30 | 41 | Highest allowlist and multiplier drift; low direct confidence-gate delta |
| BTCUSDT | 296 | 40 | 14 | 3 | 7 | 13 | Smaller drift footprint |
| DOGEUSDT | 296 | 89 | 26 | 6 | 12 | 24 | Most UNCERTAIN-heavy Aurora symbol in current slice |
| ETHUSDT | 296 | 51 | 23 | 7 | 11 | 21 | Medium carry and confidence delta |
| SOLUSDT | 296 | 40 | 31 | 8 | 17 | 28 | Stronger fresh-vs-emitted gap |
| XRPUSDT | 296 | 36 | 26 | 8 | 23 | 26 | Largest fresh confidence delta together with SOL |

MD-AMR live-assignment symbol result:

| Symbol | Bars | Actual UNCERTAIN bars | Carry bars | Fresh would reopen confidence gate | Allowlist delta bars | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| XRPUSDT | 296 | 36 | 26 | 8 | 4 | Small but real runtime sensitivity |

Mean Reversion DOGE result:

| Symbol | Bars | Actual gate-allowed bars | Actual non-neutral signals | Actual regime_not_flat bars | Actual regime_not_allowed bars | Fresh gate-open upper bound | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DOGEUSDT | 245 | 70 | 9 | 156 | 10 | 14 | Strong fail-closed regime dependence; 4 bars were UNCERTAIN-blocked but fresh-allowed |

## Matched-Case Examples

### Case 1: Observability-only PENDING

- Recorder writes regime=PENDING when the regime event does not arrive inside the retention window. [apps/reference/domains/data_recorder/recorder.py](apps/reference/domains/data_recorder/recorder.py#L314)
- The order-flow audit independently states that missing regime is structural because only ORDER_LOG v1 JSON carries regime. [reports/ORDER_FLOW_FINAL.md](reports/ORDER_FLOW_FINAL.md#L150-L157)

Interpretation:

- This is a masking layer, not live proof of no-regime consumption.

### Case 2: Fresh regime exists, emitted regime is UNCERTAIN

- SOLUSDT at 2026-04-15 12:20: detector raw regime is LOW_VOLATILITY with pre_cutoff_conf=0.85, but emitted regime is UNCERTAIN with emitted_conf=0.15 under hysteresis carry. [logs/domain_regime_detector.log](logs/domain_regime_detector.log#L4)

Interpretation:

- This is not a missing regime.
- It is a runtime conservative suppression case.
- Under the shared 0.42 confidence gate, actual fails and fresh-per-bar counterfactual would pass.

### Case 3: Raw regime is already UNCERTAIN, emitted regime still uses prior stable cache

- BNBUSDT at 2026-04-15 13:10: raw regime is UNCERTAIN at 0.15, but emitted regime remains LOW_VOLATILITY with emitted_conf=0.309154 under hysteresis carry. [logs/domain_regime_detector.log](logs/domain_regime_detector.log#L98)

Interpretation:

- This is processed with cached prior regime, not missing regime.
- This can alter allowlist outcome and context multiplier even when no trade is emitted.

### Case 4: Real trade suppression in Aurora

- A real Aurora SOLUSDT attempt was rejected because regime_confidence=0.27248 was below 0.42. [reports/order_attempts_master.csv](reports/order_attempts_master.csv#L2)
- Its rejected-counterfactual row shows only 0.22% MFE and -0.18% MAE, classified as Indeterminate / Flat. [reports/rejected_counterfactuals.csv](reports/rejected_counterfactuals.csv#L2)

Interpretation:

- This is a real trade-count suppression event.
- The bounded economic evidence does not support classifying it as economically dangerous.

### Case 5: Real trade suppression in MD-AMR

- A real XRPUSDT MD-AMR attempt was rejected because regime_confidence=0.16646 was below 0.42. [reports/order_attempts_master.csv](reports/order_attempts_master.csv#L4)
- Its rejected-counterfactual row is also Indeterminate / Flat with small excursion. [reports/rejected_counterfactuals.csv](reports/rejected_counterfactuals.csv#L4)
- The 21h runtime path also shows both a directional regime reject and a later successful intent path for XRPUSDT MD-AMR. [reports/runtime_21h_md_amr_path.csv](reports/runtime_21h_md_amr_path.csv#L2-L7)

Interpretation:

- The MD-AMR live path is regime-sensitive.
- In bounded evidence, the economic effect is small and mixed.

## Trade Count And Economic Impact

### Aurora

Forensic attempt counts:

- 157 total attempts.
- 137 decision_rejected.
- 76 confidence-gate rejects.
- 29 directional regime rejects.

Rejected-counterfactual outcomes:

- Confidence-gate rejects: 76 cases total.
- Saved Capital: 19.
- Missed Profit: 4.
- Stopped Out Early / Whipsaw: 3.
- Indeterminate / Flat: 40.
- Missing window: 10.

Directional rejects:

- 29 cases total.
- Saved Capital: 15.
- Missed Profit: 3.
- Indeterminate / Flat: 7.
- Missing window: 3.
- Whipsaw: 1.

Interpretation:

- Aurora does have real trade-count suppression from regime-dependent gates.
- The suppressed cohort is economically mixed and mostly conservative, not a silent toxic stale-context cluster.
- Only 34 of 784 actual confidence-fail bars in the current detector slice would reopen under fresh raw regime, about 4.3% of actual confidence fails. Most confidence fails remain fails even under fresh-per-bar alignment.

### Mean Reversion

- DOGE MR joined 245 live bars.
- 156 bars were blocked as regime_not_flat.
- 10 bars were blocked as regime_not_allowed.
- 9 bars produced non-neutral signals.
- Fresh-per-bar regime would open the gate on at most 14 bars.

Interpretation:

- Runtime blast radius is real.
- Economic blast radius is not yet proven because the downstream MR signal and trade path were not fully replayed on those 14 bars.

### MD-AMR

Forensic attempt counts:

- 35 total attempts.
- 32 decision_rejected.
- 27 confidence-gate rejects.
- 4 directional rejects.

Rejected-counterfactual outcomes:

- Confidence-gate rejects: 27 cases total, with 18 Indeterminate / Flat and 3 Missed Profit.
- Directional rejects: 4 cases total, with 2 Missed Profit.

Bounded recorder replay:

- Combined baseline vs integrated MD-AMR replay shows trade_count_delta=0 and net_return_ratio_delta=0. [reports/md_amr_integrated_validation_summary.csv](reports/md_amr_integrated_validation_summary.csv#L2-L4)

Interpretation:

- The current MD-AMR strategy-local context overlay is not proven to be economically harmful on bounded replay.
- The live-path regime issue manifests mainly as shared safety-gate suppression, not as a proven MD-AMR-specific economic defect.

## Objective-Engine Impact

What is proven in code:

- Missing regime_name or regime_ts_ms hard-fails objective preconditions. [apps/reference/domains/decision_making/objective_gate_evaluator.py](apps/reference/domains/decision_making/objective_gate_evaluator.py#L132-L156)
- Information score penalizes only regime_age_sec and rewards regime_confidence plus readiness. [apps/reference/domains/objective_engine/components/information.py](apps/reference/domains/objective_engine/components/information.py#L23-L31)

What is proven in runtime:

- No live detector-heartbeat-dead markers were found.
- No 4h stale regime TTL breach was observed in recorder rows.

Conclusion:

- A true stale-regime objective penalty spike is unproven in the bounded live slice.
- Hysteresis carry changes confidence reward, but not necessarily staleness age, because the detector still emits every bar.
- I do not have aligned objective traces for the fresh-vs-emitted cohort, so objective-engine economic delta remains unproven.

## Severity Assessment

Overall class:

- Symptom layer: observability only.
- Live decision layer: runtime and economic, but conservative and bounded.
- Dead-detector stale-context layer: unproven.

Severity:

- Overall: P1.
- Aurora: P1.
- Mean Reversion DOGE: P2.
- MD-AMR XRP: P2.

## Operator Risk Assessment

Operator risk is moderate.

- The main operator risk is misclassification: treating PENDING or missing regime tags as live no-regime readiness failure.
- The main real runtime cost is suppressed entries and distorted trade-count attribution.
- The main unproven risk is stale toxic trading on a dead detector; current evidence does not support that class.

Operationally, the issue is more likely to under-trade than to silently over-trade.

## What Remains Unproven

1. Full end-to-end fresh-per-bar trade replay for Aurora on the same live slice as the detector carry metrics.
2. Full downstream MR DOGE replay on the 14 gate-open upper-bound bars.
3. Objective-engine trace deltas aligned to the fresh-vs-emitted cohort.
4. Any live detector-heartbeat-dead episode that would convert this from bounded suppression into a readiness outage.

## Recommended Priority Relative To Other Open Defects

Priority recommendation:

1. Below execution_position lifecycle defects that hard-disable symbols or invalidate economic attribution across the entire stack.
2. Below or alongside high-recurring warmup_not_full_ready defects, which remain the dominant runtime suppressor in the blocker matrix. [reports/runtime_21h_blockers.csv](reports/runtime_21h_blockers.csv#L2)
3. Above pure observability cleanup, because Aurora and MD-AMR show real gate deltas and real rejected attempts. [reports/runtime_21h_blockers.csv](reports/runtime_21h_blockers.csv#L3-L4)

Practical ranking:

- P0: no.
- P1: yes, if the current goal is improving live entry throughput and restoring economically valid trade-count attribution.
- P2: only if the immediate roadmap is dominated by harder symbol-disabling defects.

## Final Classification

The defect is best classified as:

- Observability only at the forensic symptom layer.
- Both runtime and economic at the live strategy layer, strongest in Aurora, but conservative and bounded rather than economically dangerous.
- Not proven as a dead-detector readiness outage or toxic stale-context trading defect.

That is why the correct repository-level priority is P1, not P0.
