# BTC Shield Drift Root Cause

## Hard Verdict

ISOLATED_TO_MEMORYSHIELD_STATE_HISTORY_MISMATCH

## Claim

The remaining BTC shield drift is not caused by threshold extraction and not caused by missing pillar features on the inspected anchors. It is caused by MemoryShield familiarity tier divergence, most likely from replay using different visit-history semantics than live.

## FACTS

- ContextShield config sets TREND_UP=1.0 and MEAN_REVERSION=0.75.
- MemoryShield config sets UNKNOWN=0.60, EXPLORING=0.80, KNOWN=1.00.
- Live BTC anchors show:
  - 07:30 shield_mult=0.600 in TREND_UP.
  - 07:35 shield_mult=0.600 in TREND_UP.
  - 19:05 shield_mult=0.450 in MEAN_REVERSION.
  - 19:15 shield_mult=0.450 in MEAN_REVERSION.
- Replay BTC anchors show:
  - 07:29:59.999 shield_multiplier=0.8 in TREND_UP.
  - 07:34:59.999 shield_multiplier=1.0 in TREND_UP.
  - 19:04:59.999 shield_multiplier=0.75 in MEAN_REVERSION.
  - 19:14:59.999 shield_multiplier=0.75 in MEAN_REVERSION.
- Live BTC feature logs on all four anchors contain pillar_operator and pillar_strategist, which are required by MemoryShield._get_state_hash().
- MemoryShield.evaluate() fail-closes to UNKNOWN only when required state-hash inputs are missing or when effective visits remain below the unknown threshold.
- Live aurora_decision.py records visits only after signal emission and prefers result.details["memory_state_hash"].
- Replay records visits directly on buy/sell and recomputes the hash instead of threading the evaluated hash through.
- MemoryShield storage_path is null, so live familiarity state is not persisted across restarts.

## Multiplier Decomposition

### Live

- TREND_UP 0.600 = context 1.0 * memory 0.60.
- MEAN_REVERSION 0.450 = context 0.75 * memory 0.60.

### Replay

- TREND_UP 0.800 = context 1.0 * memory 0.80.
- TREND_UP 1.000 = context 1.0 * memory 1.00.
- MEAN_REVERSION 0.750 = context 0.75 * memory 1.00.

## What This Rules Out

- Not a context-regime mismatch: the observed multipliers decompose exactly with the expected regime multipliers.
- Not a missing-pillar-key explanation on these anchors: live feature logs already contain pillar_operator and pillar_strategist.
- Not a threshold-surface issue: thresholds do not control shield tier selection.

## Root Cause Family

- Cause family: MemoryShield familiarity state reconstruction mismatch.
- Dominant mechanism 1: write-path mismatch.
  - Live records visits after _emit_signal and uses the evaluated memory_state_hash when available.
  - Replay records immediately on buy/sell and recomputes the bucket hash.
- Dominant mechanism 2: history-horizon mismatch.
  - Live familiarity is in-memory only.
  - Offline replay synthesizes a month-long visit ledger that may not match the live process horizon around the anchor windows.

## Confidence Boundaries

- Proven: shield drift is a MemoryShield tier problem.
- Proven: missing pillar keys are not the explanation on the inspected BTC anchors.
- Proven: replay and live use different write semantics.
- Not fully proven: the exact percentage split between write-path drift and horizon/reset drift.

## Repairability

- Partial local repair is available:
  - only record replay visits after a signal-emission-equivalent boundary.
  - thread result.details["memory_state_hash"] through replay and use that exact bucket for record_visit.
- A remaining hard blocker persists for exact fidelity:
  - without persisted MemoryShield state or explicit reset markers, replay cannot prove exact live familiarity parity across process restarts.

## Operational Risk

- Shield drift changes both admission attenuation and resulting score magnitude.
- Until shield history semantics are aligned or explicitly bounded, replay can overstate or understate live confidence on the same BTC state.

## Final Classification

Shield drift is isolated to MemoryShield state-history semantics. It is partially repairable, but exact parity remains blocked by missing persisted familiarity state.
