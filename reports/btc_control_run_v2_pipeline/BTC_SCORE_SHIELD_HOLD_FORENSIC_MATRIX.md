# BTC Score Shield Hold Forensic Matrix

## Hard Verdict

GO_ROOT_CAUSES_ISOLATED_WITH_REPAIR_PLAN

## Scope

- Package: AURORA_BTC_SCORE_SHIELD_HOLD_FIDELITY_FORENSIC.
- Target slices: 2026-03-31 07:30, 07:35, 19:05, 19:15 live vs repaired replay anchors.
- Objective: isolate why repaired BTC replay still diverges on score scale, shield attenuation, hold continuity, and downstream action semantics.

## Matrix

| Surface | Proven symptom | Dominant root cause | Evidence status | Repairability | Current classification |
| --- | --- | --- | --- | --- | --- |
| score_scale | Replay scores are materially smaller in magnitude than live on matched BTC bars. | Replay compute path omits live decision geometry kwargs and therefore falls back to quadratic admission semantics. | Proven by exact arithmetic on anchored slices. | Local repair. | Isolated. |
| shield_attenuation | Replay shield multipliers are 0.80, 1.00, 0.75 where live shows 0.60 and 0.45. | MemoryShield familiarity tier divergence, not regime-context mismatch and not missing pillar features. | Proven to root-cause family; exact horizon vs write-path split remains unproven. | Partial repair. | Isolated enough for repair plan. |
| hold_state_continuity | Live 07:35 remains hold:sell; replay 07:34:59.999 turns neutral. | Secondary effect of score-scale drift across thr_neutral, not a proven independent hold-state bug. | Proven on 07:35 anchor. | Verify after score fix. | Isolated. |
| replay_to_gateway_semantics | Live continues into STRATEGY_SIGNAL_GATEWAY and TRADE_INTENT_PROPOSED; replay stops at ReplayObservation. | Harness boundary stops below EVT:STRATEGY_SIGNAL_PRODUCED and StrategyGateway. | Proven from code and logs. | Architectural extension or explicit scope bound. | Isolated. |
| feature_provenance_time_axis | Feature log audit still has no explicit timestamp field. | Observability gap blocks audit-grade bar-alignment proof, but it does not explain the anchored score formula mismatch. | Proven as contributing blocker. | Instrumentation repair. | Contributing blocker, not primary root cause for anchored score drift. |

## FACTS

- Live Aurora passes admission_mode, sizing_mode, and admission_shield_floor into QuadraticScoringKernel.compute.
- Repaired replay still calls QuadraticScoringKernel.compute without those kwargs.
- Live BTC anchor feature logs at 07:30, 07:35, 19:05, and 19:15 contain pillar_sum, pillar_operator, pillar_strategist, and pillar_contribs.
- Live KERNEL_DIAG lines show admission=linear, sizing=quadratic, admission_shield_mult=0.750 on all four anchors.
- Replay slice artifact shows:
  - 07:29:59.999 score=-0.0259507 shield=0.8 side=sell.
  - 07:34:59.999 score=-0.03472356 shield=1.0 side="".
  - 19:04:59.999 score=-0.02899209 shield=0.75 side=sell.
  - 19:14:59.999 score=-0.02899209 shield=0.75 side=sell.
- Live shadow journal sequence 15609 records why-chain hold:sell:score=-0.1398<=-thr_neutral=-0.0500 and the same rid emits EVT:TRADE_INTENT_PROPOSED.
- ContextShield regime multipliers are TREND_UP=1.0 and MEAN_REVERSION=0.75.
- MemoryShield tier multipliers are UNKNOWN=0.60, EXPLORING=0.80, KNOWN=1.00.
- Live MemoryShield records visits only after signal emission and prefers the memory_state_hash returned by evaluation.
- Replay records MemoryShield visits directly on buy/sell and recomputes the hash instead of threading the evaluated state hash through.
- MemoryShield storage_path is null, so live familiarity state is in-memory only.

## INFERENCES

- Score-scale drift is no longer a generic "feature mismatch" hypothesis. The anchored arithmetic proves the replay compute path is using the wrong admission geometry.
- Shield drift is not caused by missing pillar keys on the inspected BTC anchors. The live feature logs already contain the keys required by MemoryShield._get_state_hash().
- Hold-state drift at 07:35 is explained by replay score remaining above the neutral hold threshold after the geometry mismatch compresses score magnitude.
- Exact live-replay MemoryShield parity cannot be fully proven offline while familiarity state remains in-memory only and replay does not mirror the live write path.
- Current replay can prove at most pre-gateway signal-layer parity. It cannot prove downstream trade-intent parity.

## Repair Priority

1. Repair replay geometry wiring so compute kwargs match live decision geometry.
2. Repair replay MemoryShield write semantics so record_visit uses the evaluated state hash and matches live emission timing.
3. Decide whether replay scope should stop at signal parity or be raised through StrategyGateway.
4. Add timestamped feature provenance and, if exact shield parity matters, persist or checkpoint MemoryShield state.

## Final Classification

- Root causes are isolated well enough to act.
- The score bug is local and repairable.
- The shield mismatch is isolated to state-history reconstruction semantics, but exact parity remains blocked without better state provenance.
- The hold mismatch is presently a symptom, not a separately proven defect.
- The gateway mismatch is a harness boundary, not a hidden scoring bug.
