# BTC Score Shield Hold Report

## Hard Verdict

GO_ROOT_CAUSES_ISOLATED_WITH_REPAIR_PLAN

## Executive Summary

The repaired BTC control harness fixed the threshold-entry contract but did not fix behavior fidelity. This forensic package isolates the remaining divergence stack with enough precision to act.

The highest-confidence finding is score scale. Replay still calls QuadraticScoringKernel.compute without the live decision geometry kwargs, so it falls back to quadratic admission. The four anchored BTC slices are not just directionally different; the replay scores are exact numeric matches for the wrong formula applied to the live s_linear values. This makes score drift a local replay defect, not a vague provenance problem.

Shield drift is a separate layer. Live anchors decompose to UNKNOWN MemoryShield tier, while replay anchors decompose to EXPLORING or KNOWN tiers. The live anchor feature logs contain the pillar fields required by MemoryShield hashing, so the inspected drift is not caused by missing pillar keys. The remaining cause family is MemoryShield state-history mismatch: replay records visits differently from live and live familiarity state is in-memory only.

Hold continuity at 07:35 is downstream of score compression. Live remains sell because score <= -thr_neutral. Replay becomes neutral because its compressed score is above that boundary. There is no need to posit an independent hold-state bug before geometry parity is restored.

Replay-to-gateway divergence is also now bounded. Live continues through EVT:STRATEGY_SIGNAL_PRODUCED, StrategyGateway, and TRADE_INTENT_PROPOSED; replay ends at ReplayObservation. That is an architectural boundary and should be treated as such.

## FACTS

- Live decision geometry is admission_mode=linear, sizing_mode=quadratic, admission_shield_floor=0.75.
- Repaired replay omits those kwargs at the kernel call site.
- Live 19:05 score=-0.147459 is exactly reproduced by linear admission arithmetic on the live s_linear value.
- Replay 19:04:59.999 score=-0.02899209 is exactly reproduced by quadratic admission arithmetic on that same live s_linear value.
- Live 07:35 why-chain records hold:sell:score=-0.1398<=-thr_neutral=-0.0500.
- Replay 07:34:59.999 score=-0.03472356 does not satisfy that hold predicate.
- Live BTC feature logs at all four anchors include pillar_operator and pillar_strategist.
- Live shield multipliers map to UNKNOWN familiarity tier, while replay shield multipliers map to EXPLORING or KNOWN tiers.
- Live records MemoryShield visits after signal emission using memory_state_hash when available.
- Replay records MemoryShield visits directly on buy/sell and recomputes the bucket hash.
- MemoryShield storage_path is null, so exact live familiarity history is not persisted.
- Live anchors all pass StrategyGateway and emit TRADE_INTENT_PROPOSED.
- Replay never enters StrategyGateway.

## Direct Answers

1. Why does repaired BTC replay still diverge on score scale?
   - Because replay still uses the wrong kernel geometry. This is proven and locally repairable.

2. Why does shield attenuation still diverge?
   - Because replay and live land in different MemoryShield familiarity tiers. The cause family is isolated to history/write semantics, not missing pillar keys on the inspected anchors.

3. Why does hold continuity diverge at 07:35?
   - Because replay score compression moves the bar above the neutral hold boundary. Hold drift is currently a symptom of score drift.

4. Why does replay-to-gateway behavior diverge?
   - Because current replay stops below EVT:STRATEGY_SIGNAL_PRODUCED -> StrategyGateway -> TRADE_INTENT_PROPOSED semantics.

5. Is feature provenance still a blocker?
   - Yes for audit-grade proof, because sampled feature logs still expose no explicit timestamp field. But that gap is not required to explain the anchored score formula mismatch.

## Repair Plan

### Stage 1: local replay fix

- Thread admission_mode, sizing_mode, and admission_shield_floor into replay compute calls.
- Re-run the four BTC anchors and canonical BTC control harness.
- Verify whether 07:35 hold continuity collapses automatically.

### Stage 2: shield-state alignment

- Change replay visit recording to use the evaluated memory_state_hash.
- Move replay visit recording to the same semantic point as live signal emission.
- Re-test the four anchors.

### Stage 3: decide boundary

- Either keep replay explicitly bounded to signal-layer parity.
- Or extend replay to emit EVT:STRATEGY_SIGNAL_PRODUCED and enter StrategyGateway.

### Stage 4: provenance hardening

- Add explicit timestamps to feature logs.
- If exact shield parity matters across restarts, persist or checkpoint MemoryShield state.

## Repairability Map

- Score-scale drift: repairable local replay bug.
- Shield drift: partially repairable, but exact parity is blocked without better familiarity-state provenance.
- Hold continuity drift: likely resolves after score fix; do not treat as independent until re-tested.
- Replay-to-gateway semantic gap: architectural and must be either extended or explicitly bounded.
- Feature provenance gap: instrumentation blocker for audit-grade proof.

## Final Verdict

GO_ROOT_CAUSES_ISOLATED_WITH_REPAIR_PLAN
