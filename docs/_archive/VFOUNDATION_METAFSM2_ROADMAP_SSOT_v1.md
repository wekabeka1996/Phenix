# VFOUNDATION / METAFSM2 ROADMAP SSOT
## Canonical Replayable Decision/Execution Truth System
**Status:** ACTIVE SSOT  
**Date:** 2026-04-08 (last reconciliation: 2026-04-20)  
**Scope:** vfoundation core roadmap only  
**Purpose:** single roadmap SSOT for implementation sequencing, closure criteria, and next exact packages

---

> **CONTRADICTION RESOLUTION NOTE (2026-04-20)**  
> Earlier wording of this SSOT (as of 2026-04-08) stated that Phase 5 was the main active
> implementation track and that Phase 6+ had not yet started as runtime implementation phases.
> In parallel, accepted execution-side package work conducted independent audits and closed the
> full guardian/cancel seam package line (Packages 4–12) under the label "Execution Phase 6"
> (guardian-seam-closure campaign).  An independent code-evidence re-audit (2026-04-20) verified
> this closure as VERIFIED_COMPLETE and explicitly stated that Execution Phase 6 can now be closed.
> This SSOT is updated below to match that accepted evidence without rewriting the historical
> wording of the pre-existing phases.  The two tracks (Phase 5 restart-truth hardening and
> Execution Phase 6 guardian/cancel seam closure) ran in parallel; neither invalidates the other.

---

## 1. Final Goal

The final goal is **not** “move everything to MetaFSM2/FSMv2 at any cost”.

The final goal is:

> Build a **canonical replayable decision/execution truth system** where lifecycle-critical behavior is:
> - contract-stable,
> - schema-backed,
> - causally readable,
> - restart-safe,
> - shadow-observable,
> - replayable,
> - and only then selectively formalized and cut over into FSM-first control.

### Frozen principles
These are **non-negotiable**:

- no big-bang migration
- no silent fallbacks
- contract-first
- additive-only evolution
- runtime truth first, migration second
- package is DONE only with `REPORT + validation evidence`
- truth plane before migration
- shadow / hardening before formal cutover
- restore is not replay
- YAML + Pydantic remain SSOT for config and typed contracts

### Not frozen in advance
These are **not** predetermined:

- first cutover target
- whether MetaFSM2/FSMv2 becomes substrate for every critical contour
- final orchestration shape of the replay / WAL plane
- exact contour order after the first cutover

---

## 2. Current Truth Snapshot

We are **not** at “start migration now”.
We are at:

> **Phase 4 is closed at truth/contract level.**  
> **Execution Phase 6 (guardian/cancel seam-closure campaign, Packages 4–12) is now CLOSED.**  
> **Phase 5 — Restart Truth Hardening — remains the main active framework track and is partially complete through 5A, 5B.1, 5B.1A, and 5B.2.**

Important current reality:

- Shadow truth layer exists and is operational.
- Lifecycle-critical seams are materially more visible than before.
- Guardian/cancel seam contours (all major raw adapter-cancel paths) are now runtime-governed by typed bridges and Package 4 typed cancel intake.
- `execution_position` is still the main runtime monolith and the main source of restart-truth risk.
- Restart truth is still not canonical because lifecycle restore is not yet authoritative.
- Writer-side restore artifact work already exists.
- Dark-read / authoritative reader / warm-state reclassification are still ahead.
- Residual out-of-scope debt from Execution Phase 6 is documented separately (see residual items below).

---

## 3. Status Ledger

## Phase 0 — Governance Freeze
**Status:** DONE

### Goal
Freeze engineering discipline so migration does not become chaos.

### Proven complete
- no big-bang migration
- no silent fallbacks
- no contract changes without registry/schema/YAML
- contract-first
- additive-only evolution
- runtime truth first
- package complete only with report + validation evidence

### Exit gate
- all new packages follow this discipline
- no “done” without report/evidence
- no direct rewrite without bounded contract surface

### Fail conditions
- hidden fallback
- contract drift without registry/schema
- “done” claimed without evidence

---

## Phase 1 — Architecture Truth Freeze
**Status:** DONE ENOUGH

### Goal
Freeze what is true about the current system and what is not.

### Proven
- direct FSMv2 / MetaFSM2 cutover into execution domain is forbidden right now
- current restart/hydrate truth for `execution_position` is lossy
- live fill surface to preserve is `TRADE_EXECUTED`
- first cutover target is not frozen yet
- restore/hydrate is not replay

### Practical meaning
- do not migrate from docs or aesthetics
- do not mistake portfolio truth for lifecycle truth
- future cutover must stand on runtime proof

### Fail conditions
- treating restore as replay
- selecting cutover by intuition
- attempting whole-domain migration

---

## Phase 2 — Shadow Truth Layer
**Status:** DONE (baseline layer)

### Goal
Create append-only visibility over runtime truth.

### Proven complete
- shadow-only critical event journal exists
- append-only observability exists
- before/after visibility exists
- duplicate/restart/close truth markers exist

### What this phase means
This is **not** replay and **not** restore authority.
This is the evidence plane.

### Exit gate
- lifecycle-critical events are no longer invisible
- operator can reconstruct local causal fragments
- hardening packages have a truth artifact sink

### Fail conditions
- critical events remain invisible
- observability exists only in memory
- journal cannot support local causality reconstruction

---

## Phase 3 — Pre-Stabilization Execution-Truth Hardening
**Status:** MOSTLY DONE, TAILS REMAIN

### Goal
Remove the most dangerous execution-truth defects before formal migration work.

### Proven complete enough
- duplicate fill hardening around `TRADE_EXECUTED`
- repeated close hardening
- stronger execution-truth continuation on selected paths

### Not fully done
- not every close-producing path is equally proven
- degraded identity is still not ideal
- execution truth is not replayable yet
- `execution_position/fsm.py` remains a maintenance and comprehension risk

### Exit gate
- duplicate / repeated-close defect class no longer reproduces in control scenarios
- known close-producing critical paths have bounded guard logic
- live fill surface remains stable

### Fail conditions
- hardening breaks `TRADE_EXECUTED`
- new close path bypasses truth markers
- coverage on active paths is only speculative

---

## Phase 4 — Lifecycle Contract Hardening
**Status:** CLOSED

### Goal
Make lifecycle-critical surfaces contract-stable, schema-backed, causally readable, and operationally visible.

### Included work
- schema stabilization for lifecycle-critical verbs
- canonical ownership for fill / reject / cancel / expire surfaces
- causality / idempotency policy on active seams
- cleanup of legacy fill surface from active truth model
- explicit semantics for reject / cancel / expire without semantic collapse

### Proven completed blockers
1. `EVT:EXECUTION_GUARD_BLOCKED` schema/runtime drift fixed end-to-end  
2. `BRACKETS_PENDING` deferred bracket silent-drop seam removed  
3. Package 4 recommendation / overlap ambiguity resolved as **truthful zero**, not hidden defect

### Important closure note
Phase 4 is closed **because truth gaps were closed**, not because every optional experimental surface became active or because recommendation paths started firing more often.

### What “closed” means here
- active critical producers are no longer silently dying on schema drift
- critical deferred lifecycle seam is no longer hidden
- package-level validation no longer confuses “zero observed recommendations” with “unknown truth”

### What it does **not** mean
- not every branch has perfect live capture density
- not every experimental surface is “production mature”
- restart truth is still not solved here

### Fail conditions that are now considered resolved for Phase 4
- schema exists but runtime uses incompatible payload on critical producer
- active lifecycle seam can silently drop without forensic evidence
- validator ambiguity masks the real runtime truth of critical package-level behavior

---

## Phase 5 — Restart Truth Hardening
**Status:** IN PROGRESS

### Why this is the main active phase now
Restart truth is still the biggest remaining architectural blocker before any serious formal cutover.
Right now the system still risks reconstructing lifecycle truth heuristically from reduced artifacts.

### Goal
Separate restore from replay and stop guessing lifecycle phase from truncated snapshots.

### Phase 5 internal breakdown

#### 5A — Restart Truth Audit
**Status:** DONE

Proven:
- current restart truth is lossy
- lifecycle state is not yet canonically persisted
- portfolio truth and execution lifecycle truth are still too entangled

#### 5B.1 — Canonical Restore Model Spec
**Status:** DONE

Proven:
- canonical restore model defined
- execution-owned truth separated conceptually from portfolio truth
- explicit unknown semantics established as required direction

#### 5B.1A — Addendum / Minimum Artifact Correction
**Status:** DONE

Proven:
- `contour_id` removed from minimum rollout
- minimum identity surface narrowed to real runtime anchors
- writer rollout no longer blocked by synthetic identity issuance

#### 5B.2 — Writer-Side Introduction
**Status:** DONE

Proven:
- `execution_position_restore_envelope_v1.json` writer introduced
- writer-only mode does not change startup behavior
- artifact writes exact fields plus explicit unknown where required
- shadow journal remains evidence-only
- warm-state, pending-brackets WAL, and PositionTracking authority were not taken over by the writer

#### 5B.3 — Dark Reader / Diff-Only Validation
**Status:** NEXT EXACT PACKAGE

### Goal
Parse the restore artifact at startup and compare it to the current heuristic path without giving it authority.

### Required outcome
- reader can parse the artifact
- comparison markers show differences versus current heuristic startup path
- corrupt/stale/mixed-certainty artifacts are handled explicitly
- parse success alone is not mistaken for semantic correctness

### Exit gate
- dark-read comparison exists
- mismatch reporting is explicit
- no startup authority transfer happens yet

### Fail conditions
- dark-read is treated as proof by itself
- parse success hides semantic mismatch
- current runtime behavior is accidentally mutated

#### 5B.4 — Authoritative Reader with Explicit Unknown Restore
**Status:** PLANNED AFTER 5B.3

### Goal
Replace heuristic execution hydrate with authoritative envelope restore for exact fields and explicit unknown for the rest.

### Required outcome
- no lifecycle guessing from portfolio presence
- missing bracket lineage remains unknown, not inferred
- live portfolio truth can reconcile with restored lifecycle only through explicit rules
- no split-brain between restored lifecycle truth and live portfolio truth

### Exit gate
- authoritative reader works without semantic guessing
- exact / unknown separation is preserved at runtime
- startup behavior is truth-safe, not convenience-safe

### Fail conditions
- restored lifecycle certainty is fabricated
- portfolio presence implies lifecycle phase
- live-overwrite rules are ambiguous

#### 5B.5 — Warm-State Deprecation Boundary
**Status:** PLANNED AFTER 5B.4

### Goal
Reclassify `execution_truth_warm_state_v1.json` as cache-only and remove any lifecycle-authority implication.

### Required outcome
- warm-state is explicitly non-authoritative
- naming and semantics no longer imply restore truth
- compatibility/migration markers exist

### Exit gate for the whole Phase 5
- restart can restore working execution state without semantic guessing
- execution lifecycle snapshot is separate from portfolio snapshot
- operator can explain:
  - what was restored exactly
  - what was reconstructed
  - what remains unknown

### Fail conditions
- restore keeps pretending to be replay
- lifecycle phase is still guessed from indirect evidence
- persisted truth still mixes exact / degraded / unknown

---

## Phase 6 — Guardian / Cancel Seam Closure (Execution-Side)
**Status: CLOSED** *(closed 2026-04-20 via accepted execution-side package ledger and independent audit)*

> **Note on naming:** The earlier SSOT phrasing for Phase 6 described it as
> "Foundation-to-Runtime Closure" (NOT STARTED, MANDATORY) — a broader future goal.
> In practice, accepted execution-side work used "Execution Phase 6" to label the
> guardian/cancel seam-closure campaign (Packages 4–12).  These are distinct efforts.
> This section now records the accepted execution-side closure.  The broader
> Foundation-to-Runtime goal remains open and will be addressed after Phase 5 completes.

### What this phase closed (guardian/cancel seam campaign)
- **Package 4** — Typed cancel intake seam (`CancelSubmissionPayload.from_dec_cancel`)
- **Package 5–8** — Intermediate guardian seam hardening packages (per accepted ledger)
- **Package 9** — `reconcile_symbol → cleanup_orphans(hard=True)` typed bridge
- **Package 10** — `cleanup_other_brackets_for_symbol()` typed bridge
- **Package 11** — `cleanup_before_close()` typed bridge + canonicalization fix
- **Package 12** — `cleanup_orphans(hard=False)` background orphan cancel typed bridge

### Closure evidence
- Independent code-evidence audit (2026-04-20): verdict VERIFIED_COMPLETE on Package 12
- 57 tests pass across Packages 4, 9, 10, 11, 12 (exit code 0)
- No raw direct adapter cancel remains governing owner for any named guardian path
- No hidden bypass found on any audited seam

### What was explicitly left out of scope (residual debt)
The following items were documented as out of scope for all packages and remain open:
- `positionAmt` / exchange-position parsing duplication inside `cleanup_orphans`
- `EVT:EXECUTION_CLOSE_RECONCILED` payload ownership / validation boundary
- DEF-005 restart tail remediation

These are not Phase 6 failures — they are separate work items requiring independent scoping.

### Fail conditions that are now resolved
- runtime bypasses typed payload on guardian cancel paths → **RESOLVED**: all major paths now typed
- critical hot-path depends on logic that exists only in tests → **RESOLVED**: bridges are runtime-wired
- completion was checklist-driven rather than runtime-proven → **RESOLVED**: audit evidence provided

---

## Phase 6B — Foundation-to-Runtime Closure (Broader Goal)
**Status: NOT STARTED** *(deferred; becomes relevant after Phase 5 completes)*

### Why this phase exists
vfoundation already exists as a strengthened library/tooling layer, but part of it still lives beside runtime instead of governing runtime.

### Goal
Close the gap between:
- “this exists as a library / blueprint artifact”
and
- “this actually determines hot-path runtime behavior”

### What must be done
- runtime wiring for typed payloads on active decision/execution seams
- selective activation of FSMv2 / MetaFSM2 validation hooks where they measure truth
- protocol migration hooks only on paths runtime actually uses
- decomposition of the first cutover candidate seam into manageable runtime boundaries
- no fake “blueprint completion” claims while hot path still bypasses those hooks

### Exit gate
- foundation artifacts that matter for the selected live seam are in runtime path
- no critical hot path depends on logic that exists only in tests/library
- first cutover candidate is no longer blocked by unreadable monolith boundaries

### Fail conditions
- runtime bypasses typed payload or validation hooks
- migration still depends on an unbounded monolith
- completion is checklist-driven rather than runtime-proven

---

## Phase 7 — First Cutover Target Selection
**Status:** NOT STARTED

### Goal
Choose the first real cutover target after evidence, not by intuition.

### Candidate classes
- ManageFlow
- CloseFlow
- seam-first / adapter-first candidate
- another local lifecycle contour if evidence shows it is better

### Selection rule
Never “execution_position as a whole”.
Choose the **smallest operationally valuable seam** that is already:

- truth-proven
- contract-stable
- restart-safe enough
- decomposition-ready

### Exit gate
- candidate selected with explicit comparison matrix
- candidate has bounded state space and known forbidden transitions
- candidate can run in shadow without risking live fill path

### Fail conditions
- selection by aesthetics or frustration
- choosing the biggest monolith because “eventually we must”
- selecting a candidate that depends on unresolved restart truth

---

## Phase 8 — Shadow Migration / Adapter Seam for First Target
**Status:** NOT STARTED

### Goal
Run the new model/controller in shadow while old runtime remains authoritative.

### Required outcomes
- transition diff report
- action diff report
- forbidden-state coverage
- why/diff observability
- measured latency/overhead

### Exit gate
- shadow model reproduces legacy truth within agreed tolerance
- forbidden transitions are explicitly testable
- rollback / disable path exists and is verified

### Fail conditions
- shadow path mutates live truth
- adapter seam hides semantic mismatch
- disagreements cannot be explained

---

## Phase 9 — Formal Transition Model
**Status:** NOT STARTED

### Goal
After shadow evidence, formalize the selected contour as a real FSM surface:

- states
- events
- guards
- actions
- forbidden transitions
- rollback semantics
- idempotency policy
- observability hooks

### Rule
Formal tables are written from live/shadow observed truth, not from imagination or stale docs.

### Exit gate
- transition table matches shadow-observed truth
- guards map to real runtime conditions
- rollback semantics are tested
- WAL transition records are deterministic and replay-usable for the selected contour

### Fail conditions
- formal FSM contradicts live truth
- actions can fail after state mutation without rollback
- model exists only as a diagram

---

## Phase 10 — First Cutover After Proof
**Status:** NOT STARTED

### Goal
Move the first contour from shadow/hybrid into authoritative formal control.

### Cutover allowed only if all exist
- shadow diff report
- transition coverage
- forbidden transition coverage
- replay tests on real traces
- live-like race stress
- rollback plan
- feature flag / kill switch

### Exit gate
- authoritative formal model survives real traffic without hiding truth
- rollback is exercised, not merely promised
- preserved live surfaces, especially `TRADE_EXECUTED`, remain safe

### Fail conditions
- cutover before replay on real traces
- no kill switch
- no race stress
- formal model needs hidden compatibility hacks

---

## Phase 11 — Replay / DR / Canonical Journal Consolidation
**Status:** FUTURE, BUT MANDATORY

### Goal
Complete the final canonical truth plane:

- real WAL semantics
- snapshots with explicit recovery semantics
- replay verified on real traces
- RID / span / hash-prev lineage
- DR smoke and audited restore boundaries

### Exit gate
- replay reconstructs selected target truth from real traces
- restore and replay semantics are clearly separate
- DR objectives are measurable and met for selected contours

### Fail conditions
- replay depends on hidden side effects or memory-only state
- snapshots still mix lifecycle and portfolio semantics
- operator cannot explain lineage from RID to recovered state

---

## Phase 12 — Expand Cutover Candidate-by-Candidate
**Status:** FUTURE

### Goal
Repeat phases 7–11 one contour at a time rather than migrate the whole domain.

### Rule
Each next contour must pass the same chain:

truth proof  
→ contract/restart readiness  
→ shadow migration  
→ formal model  
→ cutover after proof

### Exit gate
- each new contour has its own diff report
- replay proof exists
- rollback proof exists
- previous contours remain stable

### Fail conditions
- multi-candidate migration at once
- pressure to “finally finish MetaFSM2 everywhere”
- orchestration plane grows faster than truth plane

---

## 4. What Is Closed 100%

This section exists to prevent drift and false reopenings.

### Proven 100% closed
- Phase 0 — Governance Freeze
- Phase 2 — Shadow Truth Layer (baseline evidence layer)
- Phase 4 — Lifecycle Contract Hardening
- Phase 5A — Restart Truth Audit
- Phase 5B.1 — Canonical Restore Model Spec
- Phase 5B.1A — Minimum artifact correction / contour_id deferral
- Phase 5B.2 — Writer-side introduction
- **Execution Phase 6 — Guardian/Cancel Seam Closure (Packages 4–12)** *(closed 2026-04-20)*

### Proven not 100% closed
- Phase 1 — DONE ENOUGH, not mathematically “final”
- Phase 3 — MOSTLY DONE, tails remain
- Phase 5 overall — IN PROGRESS (next: 5B.3 Dark Reader)
- Phase 6B — Foundation-to-Runtime Closure (broader goal) — NOT STARTED
- Phase 7+ — not started

### Residual open items from Execution Phase 6 (not blockers)
- `positionAmt` / exchange-position parsing duplication
- `EVT:EXECUTION_CLOSE_RECONCILED` payload ownership / validation
- DEF-005 restart tail — requires independent scoping

---

## 5. Next Exact Work Order

This is the authoritative immediate sequence from the current point:

> **Already closed (no longer in the work queue):**  
> Execution Phase 6 — Guardian/Cancel Seam Closure — CLOSED 2026-04-20

1. **Phase 5B.3 — Dark Reader / Diff-Only Validation** ← **NEXT EXACT PACKAGE**
2. **Phase 5B.4 — Authoritative Reader with Explicit Unknown Restore**
3. **Phase 5B.5 — Warm-State Deprecation Boundary**
4. **Phase 5 closure audit**
5. **Scope the three residual Execution Phase 6 debt items** (positionAmt parsing, EVT:EXECUTION_CLOSE_RECONCILED, DEF-005) as separate bounded packages or defer
6. **Phase 6B — Foundation-to-Runtime Closure** (broader goal, post-Phase-5)
7. **Phase 7 — First Cutover Target Selection**
8. **Phase 8 — Shadow Migration for first target**
9. **Phase 9 — Formal Transition Model**
10. **Phase 10 — First Cutover After Proof**
11. **Phase 11–12 — replay / DR consolidation and contour-by-contour expansion**

---

## 6. What We Explicitly Do Not Do Next

To protect the roadmap from drift:

- do not reopen Phase 4 because of threshold/capture noise that no longer represents a truth gap
- do not turn sidecar or calibration tails into the main project
- do not start MetaFSM2/FSMv2 cutover before Phase 5 and Phase 6
- do not choose a cutover target by frustration
- do not let restore artifact become authoritative before dark-read and no-guessing proof
- do not treat shadow journal as restore authority
- do not let portfolio truth impersonate lifecycle truth

---

## 7. Official Current Position

> **Official current position (updated 2026-04-20):**  
> Phase 0–2 are complete at their intended scope.  
> Phase 3 is mostly complete but not replay-final.  
> Phase 4 is closed at truth/contract level.  
> **Execution Phase 6 (guardian/cancel seam-closure campaign, Packages 4–12) is CLOSED** — verified by independent code-evidence audit 2026-04-20.  
> Phase 5 remains the main active framework implementation track and is partially complete through 5A, 5B.1, 5B.1A, and 5B.2.  
> The next exact package is **5B.3 Dark Reader / Diff-Only Validation**.  
> Three residual out-of-scope debt items from Execution Phase 6 remain open and are not Phase 5 blockers: positionAmt parsing duplication, EVT:EXECUTION_CLOSE_RECONCILED validation, DEF-005 restart tail.

---

## 8. SSOT Decision Rule

If a future package report contradicts this roadmap, the contradiction must be resolved explicitly.
This file may be updated only when one of the following is proven with evidence:

- phase status changes
- exit gate is passed
- fail condition is triggered
- sequencing must change because evidence disproves the current order

Until then, this document is the **single working roadmap SSOT** for vfoundation / MetaFSM2 migration planning.
