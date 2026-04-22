# VFOUNDATION / METAFSM2 ROADMAP SSOT
## Canonical Replayable Decision/Execution Truth System
**Status:** ACTIVE SSOT  
**Date:** 2026-04-08 (last reconciliation: 2026-04-21)  
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

> **CONTRADICTION RESOLUTION NOTE (2026-04-21)**  
> A later forensic code-evidence audit confirmed that the late Restart Truth Hardening surfaces
> previously left open in SSOT as 5B.3 / 5B.4 / 5B.5 are already implemented in runtime code:
> dark-read diff validation exists in startup, authoritative restore is wired and no-guessing,
> and warm-state has been explicitly demoted to cache-only, non-authoritative status.  
> Therefore Phase 5 is now closed at code-evidence level.  
> This SSOT is updated below so that:
> - **Phase 5 = CLOSED**
> - **Execution Phase 6 = CLOSED**
> - **Phase 7 becomes the next main implementation track**
> - **Phase 6B remains a separate deferred broader architectural track, not the immediate blocker**

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

We are **not** at “re-open Phase 5/6 now”.
We are at:

> **Phase 4 is closed at truth/contract level.**  
> **Phase 5 — Restart Truth Hardening — is now CLOSED at code-evidence level.**  
> **Execution Phase 6 (guardian/cancel seam-closure campaign, Packages 4–12) is CLOSED.**  
> **Phase 7 — First Cutover Target Selection — is now the next main implementation track.**

Important current reality:

- Shadow truth layer exists and is operational.
- Lifecycle-critical seams are materially more visible than before.
- Restart truth is no longer limited to writer-side artifact persistence only.
- Dark-read / diff-only validation exists in startup and remains non-authoritative.
- Authoritative restore exists in runtime and preserves exact vs unknown separation.
- Warm-state is explicitly cache-only and non-authoritative.
- `execution_position` remains the main runtime monolith and still matters for future cutover selection.
- Residual out-of-scope debt from Execution Phase 6 remains separate and non-blocking.
- Phase 6B remains a broader deferred architectural track, but it is no longer the immediate work queue blocker before Phase 7.

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
**Status:** CLOSED *(closed 2026-04-21 via forensic code-evidence audit and targeted restart-truth test bundle)*

### Why this phase mattered
Restart truth was the biggest remaining architectural blocker before any serious formal cutover.
The real problem was heuristic reconstruction of lifecycle truth from reduced artifacts and implied state.

### Goal
Separate restore from replay and stop guessing lifecycle phase from truncated snapshots.

### Phase 5 internal breakdown

#### 5A — Restart Truth Audit
**Status:** DONE

Proven:
- current restart truth was lossy
- lifecycle state was not yet canonically persisted
- portfolio truth and execution lifecycle truth were too entangled

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
- writer-only mode did not take startup authority
- artifact writes exact fields plus explicit unknown where required
- shadow journal remained evidence-only
- warm-state, pending-brackets WAL, and PositionTracking authority were not taken over by the writer

#### 5B.3 — Dark Reader / Diff-Only Validation
**Status:** DONE

### Proven outcome
- restore artifact is parsed at startup in non-authoritative mode
- startup can compare restore artifact truth against heuristic/runtime state
- corrupt / stale / mixed-certainty artifacts are handled explicitly
- mismatch reporting is recorded without authority transfer
- parse success is not treated as semantic proof by itself

#### 5B.4 — Authoritative Reader with Explicit Unknown Restore
**Status:** DONE

### Proven outcome
- runtime can consume authoritative restore envelope state during startup
- heuristic lifecycle guessing is bypassed when authoritative restore is active
- exact / unknown separation is preserved at runtime
- missing bracket lineage remains unknown rather than fabricated
- portfolio presence no longer implies lifecycle phase

#### 5B.5 — Warm-State Deprecation Boundary
**Status:** DONE

### Proven outcome
- `execution_truth_warm_state_v1.json` is legacy-compatible only
- warm-state is explicitly cache-only and non-authoritative
- naming and semantics no longer imply lifecycle restore truth
- warm-state is kept out of authoritative lifecycle restore/apply paths

### Closure evidence
- startup path wires: authoritative restore → reconstruction / guardian path → dark-read comparison → startup truth snapshot
- startup truth output separates:
  - what was restored exactly
  - what was reconstructed
  - what remains unknown
  - what is cache-only
- targeted restart-truth test bundle passed:
  - `test_execution_restore_dark_read.py`
  - `test_execution_restore_authoritative_read.py`
  - `test_authoritative_restore_apply.py`
  - `test_restart_runtime_truth_reconstruction.py`
  - `test_restart_seeded_execution_truth_warm_state.py`

### Exit gate for the whole Phase 5
**PASSED**

Operator can now explain:
- what was restored exactly
- what was reconstructed
- what remains unknown

### Fail conditions now considered resolved
- restore pretending to be replay
- lifecycle phase guessed from indirect evidence
- persisted truth mixing exact / degraded / unknown without explicit boundary

---
## Phase 6 — Guardian / Cancel Seam Closure (Execution-Side)
**Status: CLOSED** *(closed 2026-04-20 via accepted execution-side package ledger and independent audit)*

> **Note on naming:** The earlier SSOT phrasing for Phase 6 described it as
> "Foundation-to-Runtime Closure" (NOT STARTED, MANDATORY) — a broader future goal.
> In practice, accepted execution-side work used "Execution Phase 6" to label the
> guardian/cancel seam-closure campaign (Packages 4–12).  These are distinct efforts.
> This section now records the accepted execution-side closure.  The broader
> Foundation-to-Runtime goal remains open as a separate deferred broader track and is not the immediate Phase 7 blocker.

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
**Status: DEFERRED / SEPARATE TRACK** *(not the immediate blocker to Phase 7 unless explicitly reactivated by new evidence)*

### Why this track exists
vfoundation already exists as a strengthened library/tooling layer, but part of it still lives beside runtime instead of governing runtime.

### Goal
Close the gap between:
- “this exists as a library / blueprint artifact”
and
- “this actually determines hot-path runtime behavior”

### Current disposition
- this remains a legitimate broader architectural goal
- this is **not** the already closed execution-side Phase 6 guardian/cancel campaign
- this is **not** the next exact work package
- this may be reactivated later if Phase 7 target selection proves it is the real bottleneck

### What must be done when reactivated
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
- Phase 5B.3 — Dark Reader / Diff-Only Validation
- Phase 5B.4 — Authoritative Reader with Explicit Unknown Restore
- Phase 5B.5 — Warm-State Deprecation Boundary
- **Phase 5 overall — Restart Truth Hardening** *(closed 2026-04-21)*
- **Execution Phase 6 — Guardian/Cancel Seam Closure (Packages 4–12)** *(closed 2026-04-20)*

### Proven not 100% closed
- Phase 1 — DONE ENOUGH, not mathematically “final”
- Phase 3 — MOSTLY DONE, tails remain
- Phase 6B — deferred separate broader architectural track
- Phase 7+ — not started

### Residual open items from Execution Phase 6 (not blockers)
- `positionAmt` / exchange-position parsing duplication
- `EVT:EXECUTION_CLOSE_RECONCILED` payload ownership / validation
- DEF-005 restart tail — requires independent scoping

---

## 5. Next Exact Work Order

This is the authoritative immediate sequence from the current point:

> **Already closed (no longer in the work queue):**  
> Phase 5 — Restart Truth Hardening — CLOSED 2026-04-21  
> Execution Phase 6 — Guardian/Cancel Seam Closure — CLOSED 2026-04-20

1. **Phase 7 — First Cutover Target Selection** ← **NEXT EXACT PACKAGE**
2. **Phase 8 — Shadow Migration for first target**
3. **Phase 9 — Formal Transition Model**
4. **Phase 10 — First Cutover After Proof**
5. **Phase 11–12 — replay / DR consolidation and contour-by-contour expansion**
6. **Scope the three residual Execution Phase 6 debt items** (positionAmt parsing, EVT:EXECUTION_CLOSE_RECONCILED, DEF-005) as separate bounded packages or defer
7. **Phase 6B — Foundation-to-Runtime Closure** *(deferred broader track; reactivate only if future evidence makes it the true bottleneck)*

---

## 6. What We Explicitly Do Not Do Next

To protect the roadmap from drift:

- do not reopen Phase 5 without new contradictory runtime evidence
- do not reopen Execution Phase 6 guardian/cancel seam packages without new contradictory runtime evidence
- do not turn sidecar or calibration tails into the main project
- do not choose a cutover target by frustration
- do not let shadow journal impersonate restore authority
- do not let portfolio truth impersonate lifecycle truth
- do not reactivate Phase 6B as the main track unless Phase 7 evidence proves it is the real bottleneck

---

## 7. Official Current Position

> **Official current position (updated 2026-04-21):**  
> Phase 0–2 are complete at their intended scope.  
> Phase 3 is mostly complete but not replay-final.  
> Phase 4 is closed at truth/contract level.  
> **Phase 5 — Restart Truth Hardening — is CLOSED** — verified by forensic code-evidence audit 2026-04-21.  
> **Execution Phase 6 (guardian/cancel seam-closure campaign, Packages 4–12) is CLOSED** — verified by independent code-evidence audit 2026-04-20.  
> **Phase 7 — First Cutover Target Selection — is now the next main implementation track.**  
> Three residual out-of-scope debt items from Execution Phase 6 remain open and are not blockers: positionAmt parsing duplication, EVT:EXECUTION_CLOSE_RECONCILED validation, DEF-005 restart tail.  
> Phase 6B remains a deferred separate broader track and is not the immediate blocker to Phase 7.

---
## 8. SSOT Decision Rule

If a future package report contradicts this roadmap, the contradiction must be resolved explicitly.
This file may be updated only when one of the following is proven with evidence:

- phase status changes
- exit gate is passed
- fail condition is triggered
- sequencing must change because evidence disproves the current order

Until then, this document is the **single working roadmap SSOT** for vfoundation / MetaFSM2 migration planning.
