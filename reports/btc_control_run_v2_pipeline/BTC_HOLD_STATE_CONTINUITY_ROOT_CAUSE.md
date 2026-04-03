# BTC Hold State Continuity Root Cause

## Hard Verdict

HOLD_MISMATCH_IS_SECONDARY_TO_SCORE_DRIFT

## Claim

The 07:35 BTC hold-state mismatch is currently explained by replay score compression across the neutral hold threshold. There is not yet evidence of an independent current_side or hysteresis bug.

## FACTS

- Live 07:35 KERNEL_DIAG shows score=-0.139757, side=sell, thr_buy=0.01620, thr_sell=0.01620.
- Live shadow journal sequence 15609 records why-chain hold:sell:score=-0.1398<=-thr_neutral=-0.0500.
- The same live rid emits EVT:TRADE_INTENT_PROPOSED with side=SELL and qty=0.148.
- Replay 07:34:59.999 shows score=-0.03472356, side="", deferred=false.
- Replay neutral_threshold for this run is 0.05.

## Threshold Test

- Live hold condition from the shadow journal is explicit:
  - score <= -thr_neutral
  - -0.1398 <= -0.0500 is true.
- Replay 07:34:59.999 score check:
  - -0.03472356 <= -0.0500 is false.
- Therefore replay does not satisfy the live hold predicate on that bar.

## What This Proves

- The 07:35 live-vs-replay hold divergence is already explained by score-scale drift.
- Replay does not need a separate hold-state defect to become neutral on that anchor.
- The most defensible ordering is:
  - first fix score geometry parity,
  - then retest hold continuity,
  - only then investigate residual current_side drift if the mismatch survives.

## What Is Not Proven

- It is not yet proven that hold continuity is perfect after a score fix.
- It is not yet proven that replay current_side evolution always matches live signal sequencing.
- It is not yet proven that no residual drift exists on other bars.

## Root Cause Classification

- Cause: upstream score compression.
- Mechanism: replay uses quadratic admission semantics and lands above the neutral hold boundary.
- Effect: replay drops to neutral where live remains in sell hold mode.
- Repairability: dependent on score-geometry repair first.

## Minimal Repair Order

1. Repair replay geometry kwargs.
2. Rerun the 07:35 anchor.
3. If replay still turns neutral, inspect current_side and event sequencing as a second-stage issue.

## Final Classification

Treat hold-state continuity as a downstream symptom until score parity is restored and re-tested.
