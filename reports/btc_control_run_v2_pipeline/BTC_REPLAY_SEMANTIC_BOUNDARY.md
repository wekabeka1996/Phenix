# BTC Replay Semantic Boundary

## Hard Verdict

CURRENT_REPLAY_STOPS_BELOW_GATEWAY_TRUTH

## Claim

The current repaired BTC replay harness does not reproduce live downstream action semantics because it stops before EVT:STRATEGY_SIGNAL_PRODUCED enters StrategyGateway and IntentBuilder.

## FACTS

- Live AuroraDecision emits EVT:STRATEGY_SIGNAL_PRODUCED after local checks pass.
- DecisionMaking listens for EVT:STRATEGY_SIGNAL_PRODUCED and routes it into _on_strategy_signal_gateway.
- StrategyGateway logs "All gates passed, emitting TRADE_INTENT_PROPOSED" when the full gate chain succeeds.
- Live BTC anchors at 07:30, 07:35, 19:05, and 19:15 all show STRATEGY_SIGNAL_GATEWAY processing and TRADE_INTENT_PROPOSED emission.
- Replay _replay_symbol() directly appends ReplayObservation(timestamp, symbol, regime, score, side, deferred, shield_multiplier, threshold_factor, thr_buy, thr_sell, forward_bps_1, forward_bps_3).
- Replay _replay_symbol() does not emit EVT:STRATEGY_SIGNAL_PRODUCED.
- Replay _replay_symbol() does not invoke DecisionMaking._on_strategy_signal_gateway, StrategyGateway, or IntentBuilder.

## Boundary Definition

- Live truth chain:
  - feature evaluation
  - QuadraticScoringKernel.compute
  - _emit_signal
  - EVT:STRATEGY_SIGNAL_PRODUCED
  - StrategyGateway gates
  - EVT:TRADE_INTENT_PROPOSED
- Current replay chain:
  - recorder bar
  - QuadraticScoringKernel.compute
  - ReplayObservation

## Consequence

- Current replay can only claim signal-layer parity.
- Current replay cannot claim gateway parity, sizing parity, or trade-intent parity.
- Comparing replay side directly to live trade-intent behavior crosses a known harness boundary.

## Repair Options

- Option A: keep replay bounded to pre-gateway truth and report that boundary explicitly.
- Option B: raise the replay harness through EVT:STRATEGY_SIGNAL_PRODUCED and StrategyGateway.
- Option C: create a second-stage gateway replay harness instead of overloading the current threshold calibrator.

## Classification

- This is an architectural boundary, not a hidden threshold bug.
- It is repairable only by extending the harness scope or by narrowing the claims made from replay outputs.

## Final Classification

Downstream action-semantic divergence is expected under the current replay boundary and should not be misclassified as a pure scoring defect.
