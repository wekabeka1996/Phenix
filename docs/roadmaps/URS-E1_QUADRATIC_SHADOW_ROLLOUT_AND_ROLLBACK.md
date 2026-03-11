## URS-E1 Quadratic Shadow Rollout and Rollback

Status: implemented on 2026-03-11 as additive rollout/rollback contract for Aurora

### Problem

Quadratic scoring code exists, but the runtime still lacks one explicit rollout contract for:

- keeping Aurora v2 as live truth by default
- evaluating Quadratic in shadow without a config flip
- arming rollback explicitly
- disabling Quadratic new-entry permission without breaking protect-existing-risk behavior
- exposing rollout state to operators

Without this package, `scoring_version`, pillar readiness, restart semantics, and operator rollback intent remain loosely coupled.

### Scope

This package standardizes:

- Quadratic rollout mode semantics
- explicit rollback-armed semantics
- one-step effective rollback from Quadratic to v2 without manual state surgery
- signal-level rollout telemetry
- startup rollout telemetry
- explicit Quadratic new-risk gate separate from generic FE readiness

### Owner Domains

- `decision_making`: live/shadow scoring truth and signal surfaces
- `policy_arbiter`: final permission consequences when Quadratic is live
- `bootstrap/main`: startup rollout telemetry

### In-Scope Files

- `apps/reference/contracts/quadratic_rollout.py`
- `apps/reference/config_models.py`
- `apps/reference/domains/decision_making/aurora_config_loader.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `apps/reference/domains/decision_making/aurora_scoring_helpers.py`
- `apps/reference/domains/decision_making/aurora_handler.py`
- `apps/reference/main.py`
- `schemas/strategy_signal_produced_v1.json`
- rollout tests and updated Aurora payload/schema tests

### Out Of Scope

- no active config flip in `config/aurora/strategies/aurora.yaml`
- no broad startup hydration redesign outside the canonical planner already added in `URS-B3`
- no change to MR or md_amr live scoring/execution semantics
- no replacement of v2 as default live strategy truth

### Invariants

- Aurora v2 remains the active live truth unless config explicitly activates Quadratic
- rollback must preserve `can_manage_existing_risk`
- `can_manage_existing_risk` and `can_open_new_risk` remain separate
- MR and md_amr must remain unaffected by Quadratic shadow enablement by default
- `quadratic_htf_ready` remains separate from generic FE readiness
- rollout truth must stay additive and must not replace URS-A1/A2/B1/B2/B3/C1/D1 surfaces

### Deliverables

- rollout contract with explicit mode and rollback state
- optional config surface for `quadratic_rollout`
- Aurora shadow-evaluation path when live engine stays v2
- explicit live Quadratic open-new-risk gate
- operator-visible startup and signal telemetry
- tested rollback path back to v2 semantics

### Tests

- contract tests for rollout mode resolution and rollback gating
- Aurora signal payload tests for rollout fields
- schema additive tests for rollout payload
- compatibility regression tests for Aurora/MR/md_amr

### Rollback And Safety Constraints

- `rollback_armed=true` must fail closed for Quadratic new entries
- rollback must not require manual cache mutation or hand edits outside config/runtime surface
- when live Quadratic is rolled back, runtime must still allow protect-only management if other contracts allow it

### Done When

- runtime exposes one explicit rollout state
- shadow Quadratic can be evaluated without forcing global live flip
- live Quadratic open-new-risk is separately gated by explicit Quadratic readiness and rollback state
- rollback back to v2 semantics is explicit and tested
- MR and md_amr stay backward-compatible
