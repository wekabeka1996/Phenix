# AGENT_REPORT_V1

## Executive Summary
BTCUSDT has a proven Aurora path through signal emission, strategy gateway, trade intent, and downstream execution logs on 2026-03-20. ETHUSDT and SOLUSDT are proven to reach feature, regime, and risk ingestion, but there is no evidence in the inspected logs that Aurora emits EVT:STRATEGY_SIGNAL_PRODUCED for either symbol; the silent path begins before the strategy gateway, not at execution_position.

## Proven Facts
- Scope was limited to Aurora path evidence for BTCUSDT, ETHUSDT, and SOLUSDT on 2026-03-20.
- SSOT assignment is symmetric: BTCUSDT, ETHUSDT, and SOLUSDT are assigned to Aurora and enabled in Aurora configs.
- Decision-making contract is signal-first, then gateway, then trade intent:
  - apps/reference/domains/decision_making/aurora_decision.py: _emit_signal logs SIGNAL and emits EVT:STRATEGY_SIGNAL_PRODUCED.
  - apps/reference/domains/decision_making/decision_making.py: DecisionMaking listens for EVT:STRATEGY_SIGNAL_PRODUCED and routes into _on_strategy_signal_gateway.
  - apps/reference/domains/decision_making/strategy_gateway.py: gateway logs Processing ... signal and, on success, All gates passed, emitting TRADE_INTENT_PROPOSED.
- ETHUSDT and SOLUSDT clearly reach upstream Aurora prerequisites in the active-day logs:
  - logs/domain_feature_engineering.log: BTCUSDT=960, ETHUSDT=960, SOLUSDT=960 mentions.
  - logs/domain_regime_detector.log: BTCUSDT=13, ETHUSDT=27, SOLUSDT=25 mentions.
  - logs/domain_decision_making.log: BTCUSDT=172, ETHUSDT=162, SOLUSDT=162 mentions.
- ETHUSDT and SOLUSDT reach decision_making risk/features ingestion in the active log:
  - logs/domain_decision_making.log lines 1063-1068 show SOLUSDT RISK_RX and FEATURES_RX, and ETHUSDT RISK_RX and FEATURES_RX in the same window.
- BTCUSDT reaches the Aurora gateway in the same window:
  - logs/domain_decision_making.log lines 1071-1075 show BTCUSDT STRATEGY_SIGNAL_GATEWAY processing and successful TRADE_INTENT_PROPOSED emission.
- Rotated Aurora logs contain explicit Aurora signal emission evidence for BTCUSDT:
  - logs/aurora_core.log.1 lines 5192-5196 show BTCUSDT QUADRATIC_DECISION_TRACE, REGIME_TPSL, SIGNAL: SELL, and gateway processing.
  - logs/aurora_core.log.1 lines 15284-15288 show the same BTCUSDT sequence again.
- Across rotated Aurora logs, symbol-specific Aurora signal/gateway counts are:
  - BTCUSDT SIGNAL=15, GATEWAY=15.
  - ETHUSDT SIGNAL=0, GATEWAY=0.
  - SOLUSDT SIGNAL=0, GATEWAY=0.
- Downstream Aurora execution evidence is BTC-only in inspected logs:
  - logs/aurora_trades.log: BTCUSDT=724, ETHUSDT=0, SOLUSDT=0.
  - logs/order_log_v1.jsonl: BTCUSDT=100, ETHUSDT=2, SOLUSDT=0.
  - logs/trade_lifecycle.jsonl: BTCUSDT=5, ETHUSDT=0, SOLUSDT=0.
- The only ETHUSDT order-log hits are unrelated adapter cancel failures, not Aurora open-path evidence:
  - logs/order_log_v1.jsonl lines 14 and 146 are ORDER_REJECTED with NRR-015 and decision_verb=CANCEL_ORDER.
- ETHUSDT and SOLUSDT do receive regime updates, including actionable-looking non-idle regimes:
  - logs/domain_regime_detector.log lines 151-152 show ETHUSDT updated to TREND_DOWN.
  - logs/domain_regime_detector.log lines 181-182 show SOLUSDT updated to MEAN_REVERSION.

## Inferred Findings
- The first proven divergence between BTCUSDT and ETHUSDT/SOLUSDT is not market data, feature engineering, regime detection, or risk ingestion.
- The first proven divergence is the Aurora signal-emission stage: BTCUSDT produces Aurora SIGNAL logs and gateway events; ETHUSDT and SOLUSDT do not.
- Because DecisionMaking listens directly to EVT:STRATEGY_SIGNAL_PRODUCED, the absence of ETHUSDT/SOLUSDT gateway logs strongly implies one of two bounded outcomes:
  - Aurora never emits EVT:STRATEGY_SIGNAL_PRODUCED for ETHUSDT/SOLUSDT.
  - Aurora emits it, but observability for both SIGNAL and gateway is missing specifically for ETHUSDT/SOLUSDT.
- Given that BTCUSDT logs both SIGNAL and gateway in the same logger family and the counts for ETHUSDT/SOLUSDT are zero across rotated Aurora logs, the more likely interpretation is no Aurora signal emission for ETHUSDT/SOLUSDT, not an execution-only failure.

## Contradictions / Evidence Gaps
- There is no direct log line in the inspected set stating why Aurora chose not to emit a signal for ETHUSDT or SOLUSDT.
- No ETHUSDT/SOLUSDT STRATEGY_DECISION_BLOCKED evidence was surfaced in the inspected logs.
- No ETHUSDT/SOLUSDT TRADE_INTENT_REJECTED evidence tied to Aurora was surfaced in the inspected logs.
- Because the decisive non-emission reason is not logged in the available evidence, the exact root cause inside Aurora decision scoring remains unproven.
- The inspected active file logs/domain_decision_making.log only covers a later time slice, so historical Aurora proof for BTC came from rotated files as well. That strengthens the need to treat absence claims as bounded to the inspected log set, not universal runtime truth.

## Root Cause Candidates
- Highest-likelihood candidate: Aurora scoring/threshold logic never produces actionable result.side for ETHUSDT and SOLUSDT on the inspected day, so _emit_signal is never reached.
  - Supporting evidence: ETHUSDT/SOLUSDT have features, regimes, and risk, but zero SIGNAL and zero gateway entries across rotated Aurora logs.
- Second candidate: a fail-closed pre-signal path inside Aurora returns early for ETHUSDT/SOLUSDT before SIGNAL logging.
  - Candidate locations from code: aurora_decision.py around volatility fail-closed, quantizer reject/error, or earlier strategy evaluation branches before _emit_signal.
  - Counterpoint: no ETHUSDT/SOLUSDT STRATEGY_DECISION_BLOCKED lines were found, so if this is happening it is under-instrumented.
- Lower-likelihood candidate: symbol-specific observability gap hides ETHUSDT/SOLUSDT SIGNAL and gateway events.
  - Counterpoint: this would require both Aurora SIGNAL logging and downstream gateway logging to fail specifically for two symbols while working for BTCUSDT in the same process family.

## Operational Risk
- Runtime
- Capital
- Observability Gap

## Files / Areas Touched
- reports/REPORT_AURORA_ETH_SOL_SILENT_PATH_FORENSIC.md

## Validation Performed
- Verified SSOT assignment and Aurora routing contracts in decision_making code.
- Searched active and rotated logs for:
  - upstream symbol presence,
  - Aurora SIGNAL entries,
  - STRATEGY_SIGNAL_GATEWAY entries,
  - downstream trade/order/lifecycle evidence.
- Collected symbol-count matrix from:
  - logs/domain_feature_engineering.log
  - logs/domain_regime_detector.log
  - logs/domain_decision_making.log
  - logs/aurora_trades.log
  - logs/order_log_v1.jsonl
  - logs/trade_lifecycle.jsonl
- Collected Aurora SIGNAL/GATEWAY counts across rotated files matching logs/aurora_core.log*.
- Validation was forensic-only; no runtime replay or test execution was performed.

## Residual Risk
- If ETHUSDT/SOLUSDT are silently suppressed before _emit_signal without an explicit blocked-event log, operators cannot distinguish healthy no-trade from broken no-trade in real time.
- The current evidence does not prove whether suppression is strategy-correct or a defect; only the stage boundary is localized.

## What Remains Unproven
- The exact branch or predicate inside Aurora that prevents ETHUSDT/SOLUSDT from reaching _emit_signal.
- Whether the non-emission is intended strategy behavior or a bug.
- Whether any missing STRATEGY_DECISION_BLOCKED or TRADE_INTENT_REJECTED events are due to absent instrumentation versus absent blocking.

## Minimal Safe Verdict
Minimal safe verdict: BTCUSDT is the valid control path for Aurora on 2026-03-20. ETHUSDT and SOLUSDT are not silent at data, feature, regime, or risk stages; they go silent before the first observable Aurora signal emission. Therefore the current root location is Aurora pre-gateway decision generation, with a secondary observability defect because ETHUSDT/SOLUSDT non-emission lacks an explicit blocked-event audit trail.

## Evidence Appendix

### Stage Matrix

| Stage | BTCUSDT | ETHUSDT | SOLUSDT | Evidence |
| --- | --- | --- | --- | --- |
| Assigned to Aurora SSOT | Yes | Yes | Yes | Config inspection performed |
| Feature calculations present | Yes | Yes | Yes | domain_feature_engineering counts: 960 / 960 / 960 |
| Regime updates present | Yes | Yes | Yes | domain_regime_detector counts: 13 / 27 / 25 |
| Risk + features ingested by decision_making | Yes | Yes | Yes | logs/domain_decision_making.log lines 1063-1068 and nearby |
| Aurora SIGNAL log present | Yes | No evidence | No evidence | aurora_core.log* counts: 15 / 0 / 0 |
| Strategy gateway processing present | Yes | No evidence | No evidence | aurora_core.log* counts: 15 / 0 / 0 |
| Aurora trade log present | Yes | No | No | aurora_trades counts: 724 / 0 / 0 |
| Order log open-path evidence present | Yes | No | No | order_log_v1 counts: 100 / 2 unrelated / 0 |
| Lifecycle present | Yes | No | No | trade_lifecycle counts: 5 / 0 / 0 |

### Representative Evidence Snippets
- BTC gateway success:
  - logs/domain_decision_making.log lines 261-264.
- ETH/SOL upstream presence without gateway in same time slice:
  - logs/domain_decision_making.log lines 1063-1068.
- BTC Aurora signal emission before gateway:
  - logs/aurora_core.log.1 lines 5192-5196.
  - logs/aurora_core.log.1 lines 15284-15288.
- ETH/SOL active feature calculations later in the session:
  - logs/aurora_core.log lines 101-102.
