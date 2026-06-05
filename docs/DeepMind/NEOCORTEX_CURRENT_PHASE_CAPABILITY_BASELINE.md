# Neocortex Current Phase Capability Baseline

This document records the current accepted Neocortex phase baseline after Phase 7 closure acceptance. It is a current-state artifact, not an implementation expansion plan.

Placement note:

- This baseline lives in `docs/DeepMind` because that folder already holds current-state Neocortex roadmap and audit-facing documents.
- The active implementation SSOT used by the recent acceptance audits remains `docs/plans/DeepMind/NEOCORTEX_IMPLEMENTATION_SSOT_v2.md`.

## 1. Executive Status

- Current phase: Phase 7 closed in scope.
- Verdict: ACCEPTED_WITH_RESIDUALS.
- Neocortex is currently a hardened memory/trust-control substrate, not a learning or rollout system.
- Next allowed direction: Phase 8 planning, Evidence Collection Mode, and real runtime data accumulation.
- Not allowed yet: model training, OPE, reward_valid enablement, live gating, production rollout.

Operational reading of the current state:

- Neocortex is a bounded adaptive trust controller.
- It is not an AI trader.
- It is not a strategy.
- It is not an execution owner.
- It is not approved for live authority rollout.

## 2. Current Phase Lock

```yaml
neocortex_current_phase:
  phase: "Phase 7 - Observability, Bounded Queues, Async Lifecycle / Dataset Admission Hardening"
  status: "closed_in_scope"
  verdict: "ACCEPTED_WITH_RESIDUALS"
  accepted_capability_level: "hardened memory/trust-control substrate"
  not_yet:
    - model_training
    - OPE
    - reward_valid_enablement
    - live_authority_rollout
    - production_gating
    - execution_ownership
```

## 3. Document Authority And SSOT Substitution

Requested conceptual SSOT handling:

- The exact file `neocortex_conceptual_implementation_plan_100_percent.md` was not found in the workspace at the time this baseline was written.
- This document therefore uses `docs/plans/DeepMind/NEOCORTEX_IMPLEMENTATION_SSOT_v2.md` as the active implementation SSOT substitution, consistent with the recent accepted audits.

Current authority stack for this baseline:

- Implementation SSOT: `docs/plans/DeepMind/NEOCORTEX_IMPLEMENTATION_SSOT_v2.md`
- Current roadmap anchor: `docs/DeepMind/07_NEOCORTEX_EXECUTION_ROADMAP.md`
- Closure verdict anchor: `reports/neocortex/NEOCORTEX_PHASE7_CLOSURE_ACCEPTANCE_REAUDIT.md`

## 4. Accepted Phase Ledger

- P0 causal/trainable truth hardening: RESOLVED in scope.
- Phase 7A canonical observability wiring: RESOLVED in scope.
- Phase 7B bounded active DecisionOutcomeLedger queue: RESOLVED in scope.
- Phase 7C async lifecycle / shutdown drain / no-orphan proof: RESOLVED in scope.
- Phase 7D dataset cutover guards: RESOLVED in scope.
- Phase 7 closure acceptance reaudit: ACCEPTED_WITH_RESIDUALS.
- Net accepted state: Phase 7 is closed in scope for the audited Neocortex hardening track.

## 5. Core Law

Neocortex must be understood as a bounded adaptive trust controller layered around the existing Aurora decision pipeline.

The governing law at the current baseline is:

- Neocortex does not emit direct `CMD:*`.
- Neocortex does not own order or position lifecycle.
- Neocortex does not replace Aurora strategy production.
- Neocortex does not patch YAML at runtime.
- Neocortex does not bypass panic, reduce-only, protective exits, or exchange recovery.
- Neocortex does not treat synthetic FLAT, `0.0`, `unknown`, zero latent, or wallclock fallback as safe trainable truth.

## 6. What Neocortex Can Do Right Now

At the current accepted baseline, Neocortex can:

- operate as a shadow-first, hardened memory/truth-control substrate around the pre-intent authority seam;
- preserve causal and trainable truth boundaries so missing or non-causal evidence is demoted to diagnostics-only or invalid status instead of being silently upgraded;
- record canonical authority, failure, journal, ledger, queue, and lifecycle observability on the shared telemetry surface;
- persist decision outcome truth through the active bounded, fail-closed DecisionOutcomeLedger queue with explicit overflow accounting;
- shut down audited active async and threaded surfaces with bounded stop timeouts, explicit forced-stop accounting, and undrained-row accounting rather than silent abandonment;
- evaluate trainable dataset cutover admission from canonical `DecisionOutcomeLedgerRow` truth plus explicit metadata and fail closed when real execution, terminal completeness, causal validity, or reward methodology proof is missing;
- accumulate real runtime evidence for future phases without changing execution ownership or enabling live model behavior.

Operationally, that means Neocortex is approved to be a hardened substrate for:

- truth preservation,
- authority-side observability,
- bounded persistence,
- bounded shutdown behavior,
- offline dataset admission truth.

It is not approved to become an active learning or rollout engine.

## 7. What Neocortex Cannot Do Right Now

At the current accepted baseline, Neocortex cannot:

- act as an AI trader or generate an independent trading strategy;
- own execution or alter the `execution_position` ownership boundary;
- emit new direct runtime command authority below the accepted pre-intent seam;
- perform model training;
- perform OPE;
- enable `reward_valid` as a production-usable learning signal;
- run live authority rollout or production gating;
- promote legacy experiment scripts into canonical runtime truth;
- mutate live YAML or configuration state at runtime;
- treat synthetic or fallback values as equivalent to causal trainable truth.

This Phase 7 closure does not authorize:

- rollout,
- promotion,
- training,
- live advisory-to-gated enablement,
- new execution ownership changes,
- new Neocortex command emission.

## 8. Boundary Laws That Remain In Force

- `alpha_search` and the existing strategy stack remain the data plane.
- `decision_making` remains the authoritative pre-execution orchestrator.
- `execution_position` remains the only owner of order and position lifecycle.
- Neocortex may influence future bounded authority only through the accepted decision-making seam and only under future explicit rollout gates.
- Reduce-only closes, protective exits, panic paths, and exchange recovery remain outside Neocortex authority.
- Legacy experiment and offline research surfaces remain non-authoritative unless a future phase explicitly migrates them onto canonical contracts.

## 9. Current Trainable Truth And Dataset Admission Baseline

The accepted trainable-truth baseline after P0 and Phase 7D is:

- missing provenance is not safe trainable truth;
- non-causal provenance is not safe trainable truth;
- wallclock fallback is not safe trainable truth;
- diagnostics-only rows are not safe trainable truth;
- terminally incomplete outcomes are not safe trainable truth;
- synthetic fallback contamination is not safe trainable dataset admission;
- reward-bearing datasets without explicit methodology proof are not safe trainable dataset admission.

Current accepted dataset-admission posture:

- Neocortex now has a canonical aggregate cutover evaluator.
- That evaluator is fail-closed.
- It is authoritative for trainable dataset promotion or export decisions only when fed canonical ledger truth.
- Legacy baseline-prep experiment scripts are not accepted substitutes for canonical cutover truth.

## 10. Residuals Behind The ACCEPTED_WITH_RESIDUALS Verdict

Phase 7 is accepted, but not with a claim of zero remaining caveats.

Current residuals explicitly carried by the closure verdict:

- `apps/reference/main.py` still contains a broad startup wrapper around shadow telemetry bridge initialization outside the audited hot path;
- legacy offline dataset-prep experiment scripts remain non-authoritative and do not yet carry full canonical cutover truth;
- no live production export pipeline proof was part of Phase 7 closure;
- no model training, OPE, or rollout proof was attempted, by scope.

These residuals are not interpreted as permission to widen scope. They are reasons the verdict is `ACCEPTED_WITH_RESIDUALS` instead of `ACCEPTED_COMPLETE_IN_SCOPE` at the whole-track level.

## 11. Allowed Next Work

The next allowed direction from this baseline is narrow and explicit:

- Phase 8 planning;
- Evidence Collection Mode;
- real runtime data accumulation;
- continued preservation of fail-closed truth, queue, lifecycle, and ownership boundaries.

Any future work must preserve the current laws:

- no hidden authority expansion,
- no silent promotion of non-causal truth,
- no execution ownership transfer,
- no legacy experiment promotion into canonical runtime authority.

## 12. Evidence Anchors

The following requested reports were found locally and are the accepted evidence anchors imported by this baseline:

- `reports/neocortex/NEOCORTEX_P0_CAUSAL_TRAINABLE_TRUTH_HARDENING_REPORT.md`
- `reports/neocortex/NEOCORTEX_PHASE7A_CANONICAL_OBSERVABILITY_WIRING_REPORT.md`
- `reports/neocortex/NEOCORTEX_PHASE7B_BOUNDED_LEDGER_QUEUE_REPORT.md`
- `reports/neocortex/NEOCORTEX_PHASE7C_ASYNC_LIFECYCLE_NO_ORPHAN_REPORT.md`
- `reports/neocortex/NEOCORTEX_PHASE7D_DATASET_CUTOVER_GUARDS_REPORT.md`
- `reports/neocortex/NEOCORTEX_PHASE7_CLOSURE_ACCEPTANCE_REAUDIT.md`

Imported meaning from those artifacts:

- P0 established fail-closed causal/trainable truth at the authority and ledger seams.
- Phase 7A established canonical observability wiring.
- Phase 7B established the bounded fail-closed active ledger queue.
- Phase 7C established bounded lifecycle and no-orphan shutdown accounting.
- Phase 7D established fail-closed dataset cutover admission.
- The closure reaudit accepted the combined Phase 7 track in scope, with residuals carried explicitly.

## 13. Minimal Safe Reading For Future Work

If a future task asks what Neocortex is allowed to do right now, the safe answer is:

- it may observe, preserve truth, journal, meter, bound, and evaluate;
- it may not train, roll out, own execution, or emit direct trade commands.

If a future task would require any of the following, this baseline is not enough and a later phase gate is required:

- training,
- OPE,
- reward-valid promotion,
- advisory or gated live authority,
- production rollout,
- execution ownership changes.
