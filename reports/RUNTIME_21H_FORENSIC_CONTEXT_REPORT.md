# RUNTIME_21H_FORENSIC_CONTEXT_REPORT

## Run Environment
FACT:
- Analysis date: 2026-04-11.
- Workspace: c:/Users/user/Music/Phenix.
- Target run window used in this report: 1775850999747..1775925057020 (~20.57h).
- Runtime mode configured: hybrid_live_data_testnet_exec (from config/aurora/trading.yaml and config/aurora/system.yaml).

INFERENCE:
- This window is the intended "~21h run" based on observed startup/restore timestamps and latest observed portfolio tail.

ASSUMPTION:
- None.

UNKNOWN:
- Exact process PID/session identity for this run from startup banner is not fully reconstructed from collected excerpts.

## Artifact Inventory
FACT:
- Core artifacts inspected:
  - logs/order_log_v1.jsonl
  - logs/trade_lifecycle.jsonl
  - logs/shadow_critical_event_journal_v1.jsonl
  - logs/aurora_events.jsonl
  - logs/domain_feature_engineering.log (+ rotations)
  - logs/domain_decision_making.log (+ rotations)
  - logs/domain_execution_position.log (+ rotations)
  - logs/event_chain.log
- Runtime config truth inspected:
  - config/aurora/strategies.yaml
  - config/aurora/strategies/md_amr.yaml
  - config/aurora/domains.yaml
  - config/aurora/trading.yaml
  - config/aurora/system.yaml
  - config/aurora/instruments.yaml

Extraction method used (exact commands/patterns):
1) PowerShell inventory by LastWriteTime >= now-21h over logs/.
2) JSONL schema sanity by reading first/last lines for aurora_events, trade_lifecycle, order_log, shadow journal.
3) Pattern extraction in text logs with Select-String, patterns including:
   - CMD:PROCESS_STRATEGY
   - FE_WARMUP
   - STRATEGY_SIGNAL_GATEWAY
   - md_amr_handler
   - TRADE_INTENT_PROPOSED
   - REGIME_AUDIT decision
4) Grouped counting method from extracted evidence for reject classes and event classes; uncapped full-file counting is partially limited by extraction tooling on large files.

UNKNOWN:
- Full uncapped event cardinalities for every event_type in trade_lifecycle and aurora_events due capped extraction outputs in this session.

## Startup Truth
FACT:
- shadow journal startup markers:
  - 1775850999747 RESTORE:EXECUTION_TRUTH_HARDENING_RESET
  - 1775850999749 CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_EMPTY
- trade_lifecycle startup marker:
  - 1775850999991 POSITION_POLICY_SIDECAR_MODE_ACTIVE (mode=shadow, evaluation_mode=phase1_recommendation_only)
- order_log boot marker:
  - 1775851801349 BOOT event (OrderLoggerV1).
- FeatureEngineering warmup initialization includes explicit warmup completion lines for all symbols around 22:56:50..22:56:57 and immediate fail_fast warmup gating around 22:57:00.

INFERENCE:
- Startup completed functionally with runtime progression into live event flow, because later decision/execution events and portfolio updates are present.

UNKNOWN:
- Any startup warning/error outside the collected excerpt slices that could have had secondary effects.

## Active Symbol / Strategy Matrix
FACT from config/aurora/strategies.yaml:
- ETHUSDT -> aurora
- SOLUSDT -> aurora
- XRPUSDT -> md_amr
- BTCUSDT -> aurora
- BNBUSDT -> md_amr
- DOGEUSDT -> mean_reversion
- 1000PEPEUSDT -> llm_microstructure

FACT from runtime evidence:
- XRPUSDT and BNBUSDT md_amr runtime paths are observed (handler and/or execution evidence present).
- Multi-symbol execution flow exists for aurora and mean_reversion symbols.

See structured CSV: reports/runtime_21h_symbol_strategy_matrix.csv

## MD_AMR Runtime Path
### XRPUSDT
FACT:
- FE degraded bypass evidence exists for assigned strategy path when warmup not full_ready:
  - "CMD:PROCESS_STRATEGY warmup not full_ready ... -> allowed (exclusive degraded-eligible bypass for assigned strategies)".
- Handler-owned path observed in decision logs:
  - MDAMRHandler MARGIN_FIRST_SIZING
  - MDAMRHandler QTY_CALC
  - MD-AMR-TPSL
- Decision gateway progression observed:
  - "STRATEGY_SIGNAL_GATEWAY: Processing BUY signal ... strategy_id=md_amr"
  - "STRATEGY_SIGNAL_GATEWAY: All gates passed, emitting TRADE_INTENT_PROPOSED"
- Execution observed:
  - ORDER_FILLED BUY entry (XRPUSDT)
  - ORDER_FILLED SELL close_reason=SL at 1775900554008 with realized_pnl=-55.97484.

### BNBUSDT
FACT:
- FE degraded bypass evidence for BNBUSDT present in warmup-not-full-ready period.
- Execution truth observed:
  - ORDER_FILLED cumulative entry to 10.08 at price 607.06.
  - Final portfolio snapshots still include BNBUSDT position in tail evidence.

UNKNOWN:
- In collected excerpt slices, a full explicit BNB md_amr handler logging chain equivalent to XRP handler chain is not fully captured line-by-line.

See structured CSV: reports/runtime_21h_md_amr_path.csv

## System-Wide Decision / Execution Summary
FACT:
- DECISION_INTENT_REJECTED total in window: 42.
- ORDER_REJECTED observed: 0.
- Dominant reject classes by NRR code:
  - NRR-026: 25
  - NRR-027: 10
  - NRR-029: 4
  - NRR-030: 2
  - NRR-028: 1
- Sidecar event totals in window include:
  - POSITION_POLICY_SIDECAR_SUPPRESSED: 93964
  - POSITION_POLICY_SIDECAR_SCORES: 3036
  - POSITION_POLICY_SIDECAR_EVALUATED: 3036
  - POSITION_POLICY_SIDECAR_RECOMMENDED: 5
- Executions and fills are present for multiple symbols (entry and close cycles observed).

INFERENCE:
- The system traded actively (not purely suppressed) because ORDER_FILLED events span multiple symbols and include completed close outcomes.

UNKNOWN:
- Full uncapped attribution of every sidecar suppression reason to startup-only vs later-runtime policy classes without additional temporal slicing by segment.

## Dominant Blockers
FACT:
1) warmup_not_full_ready (feature_engineering): recurrent FE_WARMUP false and CMD:PROCESS_STRATEGY fail_fast rejects.
2) regime_confidence gate (decision_making, NRR-026): low confidence gate denials.
3) directional safety gate (decision_making, NRR-027): downtrend/against-trend denials.
4) price-motion/transition gates (decision_making, NRR-028/029/030).

Operational mapping is provided in reports/RUNTIME_21H_BLOCKER_MATRIX.md and reports/runtime_21h_blockers.csv.

## 21-Hour Timeline
See detailed segmentation file: reports/RUNTIME_21H_TIMELINE.md

Summary FACT:
- Startup/restore at ~1775850999xxx.
- Early warmup with fail_fast and degraded bypass windows.
- Stable runtime with observed md_amr and non-md_amr execution flows.
- Late runtime with recurring reject gates (notably NRR-026/027).
- Tail state includes active exposure/portfolio update cycle.

## What Is Proven
FACT:
- Runtime mode configured as hybrid_live_data_testnet_exec.
- md_amr assignment exists for XRPUSDT and BNBUSDT.
- md_amr runtime handler path is explicitly proven for XRPUSDT.
- TRADE_INTENT_PROPOSED emission is explicitly proven for XRPUSDT.
- Execution (fills) is proven for XRPUSDT and BNBUSDT.
- Exchange-level ORDER_REJECTED is not observed in this window.
- Warmup fail_fast gating and degraded bypass behavior are both present in FeatureEngineering logs.

## What Remains Unknown
UNKNOWN:
- Fully uncapped system-wide totals for all event families across largest JSONL files in this session.
- Full explicit BNB handler-line progression (handler log chain) in the collected excerpt set.
- Any hidden startup anomaly outside sampled startup lines.

Impact of unknowns:
- Does not invalidate proven XRP md_amr success path or proven multi-symbol execution activity.
- Limits precision of ranking by exact frequency for secondary blocker classes.

## Recommended Next Work Packages
1) Package: FE Warmup Stability Forensics
- owner_domain: feature_engineering
- objective: quantify why macro_sync and readiness oscillate (full_ready false->true flaps)
- why_next: highest recurrent suppressor with broad symbol blast radius
- evidence: repeated FE_WARMUP false and CMD:PROCESS_STRATEGY fail_fast rejects
- blast_radius_if_ignored: recurring no-trade windows and inconsistent strategy activation

2) Package: Decision Gate Threshold Evidence Audit
- owner_domain: decision_making
- objective: separate healthy protection vs over-suppression for NRR-026/027 in late runtime
- why_next: second highest blocker class after warmup
- evidence: 43 decision rejects with NRR-026/027 dominant share
- blast_radius_if_ignored: sustained suppression despite valid setups

3) Package: md_amr BNB Handler Trace Completion
- owner_domain: decision_making md_amr_handler
- objective: capture complete BNB handler-stage trace parity with XRP evidence chain
- why_next: XRP chain is complete, BNB chain is execution-proven but handler-stage evidence incomplete
- evidence: BNB fill/open state proven, handler log chain partially missing in collected excerpt
- blast_radius_if_ignored: reduced confidence in md_amr observability completeness for BNB

4) Package: Uncapped Event Cardinality Extractor
- owner_domain: observability/tooling
- objective: produce deterministic full-file counts for all major JSONL event families over arbitrary window
- why_next: current session hit extraction caps on large artifacts
- evidence: capped outputs in trade_lifecycle/aurora_events extraction
- blast_radius_if_ignored: future forensic ranking remains approximate for secondary classes

## Final Verdict
FACT:
- The 21h run is not a "mostly dead" system; runtime reached real decision and execution across multiple symbols.
- md_amr definitely progressed through handler-owned decision path and intent formation for XRPUSDT, and execution occurred.
- BNBUSDT md_amr execution occurred; handler-stage proof is partial in collected excerpts.
- Dominant suppression classes are warmup readiness enforcement and decision safety gates (NRR-026/027), not exchange reject failures.

INFERENCE:
- The next engineering decision should prioritize warmup/readiness stability and gate calibration evidence before any strategy retuning.
