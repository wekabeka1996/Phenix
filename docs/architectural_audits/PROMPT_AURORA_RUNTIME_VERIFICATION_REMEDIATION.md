# AGENT IMPLEMENTATION PROMPT: Aurora Runtime Verification and Remediation (Live-Code Rewrite)

This prompt supersedes the older "Aurora/Phenix Audit Verification & Fix Sprint" prompt when working against the current `Phenix_v2` codebase.

It is intentionally based on live code under `apps/reference/`, not on stale audit prose.

## Copy/Paste Prompt

```text
You are a Principal Engineer assigned to the Aurora/Phenix project.

Your task is to run a verify-first runtime remediation sprint against the live codebase, not against stale audit assumptions.

Codebase root: c:\Users\user\Music\Phenix\
Entrypoint: apps/reference/main.py
Primary stale-hypothesis source: docs/audits/audit_report.md

===========================================
MISSION
===========================================

You must:

1. Read code first.
2. Reclassify each claimed issue as REFUTED, PARTIAL, or CONFIRMED.
3. Only implement fixes for PARTIAL or CONFIRMED issues that still represent a real runtime gap.
4. Explicitly justify every disagreement with the older audit using file + line evidence.

Do not treat the old audit as ground truth. Treat it as a hypothesis set.

===========================================
KNOWN LIVE-CODE TRUTHS YOU MUST ACCOUNT FOR
===========================================

Before making any changes, verify these current-code claims:

- Old N-1 is likely stale: `main.py` already pushes analytics restore snapshots into strategy handlers.
- Old N-4 is likely stale as written: `md_amr_handler.py` already exposes `describe_runtime_analytics_restore()` and uses `md_amr_rest_hydration` as a real restore-state label.
- Old N-7 is likely misstated: the objective-engine `ValueError` path is caught locally and converted into a fail-closed strategy block; it does not obviously escape `_process_decision()`.
- Old N-6 is likely overstated for live runtime: `DecisionConfig.scoring_version` is already type-constrained in `config_models.py`, so invalid values should usually fail during config load.

If any of the above are false in live code, say so with evidence and continue.

===========================================
MANDATORY EXECUTION ORDER
===========================================

1. Run a Reclassification Pass on all issues below.
2. Refute stale claims explicitly before patching anything.
3. Fix only remaining runtime gaps.
4. Prefer wiring existing mechanisms over introducing new architecture.
5. Preserve runtime invariants:
   - no Quadratic config flip
   - no MR or md_amr regression
   - do not merge `can_manage_existing_risk` with `can_open_new_risk`
   - do not turn the planner into a god-object
   - no YAML churn unless a fix truly requires it
   - do not modify tests except to validate a surviving issue

===========================================
RECLASSIFICATION PASS
===========================================

Before applying any fix, do this for every issue:

1. Read the live code.
2. Classify the issue as:
   - REFUTED: the old audit claim is no longer true in live code
   - PARTIAL: part of the claim is stale, but a real runtime gap remains
   - CONFIRMED: the claim still describes a real runtime gap
3. Provide code evidence with file + line references.
4. Only then decide whether a fix is needed.

If an issue is REFUTED, do not patch around it just to satisfy the old audit.

===========================================
ISSUES TO VERIFY AND FIX (UPDATED)
===========================================

---------------------------------------------------
ISSUE N-2/N-3 [CRITICAL]: Startup hydration remains report-only
---------------------------------------------------
Hypothesis:
`build_startup_hydration_plan()` returns a planning/report artifact, but startup does not execute planner actions. FE/regime/pillar/basis-bar state may still start cold after restart, with warmup becoming the only practical barrier.

VERIFY:
1. Read `apps/reference/bootstrap/startup_hydration_planner.py`.
   - Confirm whether `build_startup_hydration_plan()` returns only a report/plan object.
   - Confirm whether it executes hydration, replay, or permission decisions itself.
2. Read `apps/reference/main.py`.
   - Confirm what happens after `build_startup_hydration_plan()` is called.
   - Confirm whether the result is used for anything beyond logging/telemetry.
3. Read `apps/reference/domains/feature_engineering/feature_engineering.py`.
   - Check for startup-capable hydration paths, especially `EVT:HTF_BARS_IMPORTED` handling.
4. Read `apps/reference/domains/feature_engineering/pillar_backfill.py`.
   - Check whether a real startup historical backfill service already exists and whether it is actually wired from boot.
5. Read active market-data startup paths.
   - Verify whether there is any real basis-bar replay / historical fetch / warmup import path for live startup.

IF CONFIRMED OR PARTIAL:
Implement the smallest correct fix in this priority order:

a) Reuse existing startup-capable mechanisms first.
   - If FE HTF/pillar backfill already exists but is not wired, wire it into startup.
   - Do not invent a new hydration subsystem if the existing one can be used.

b) If no real basis-bar hydration path exists, add an explicit per-strategy per-symbol `bars_required` gate.
   - Use `StrategyCompatibilityProfile.basis_required_bars` as the source of truth.
   - Gate must be per strategy and per symbol.
   - Gate must block new-risk signal flow until enough post-restart real bars have been observed.
   - Use `RuntimeReadinessScope.BARS` as the readiness scope identifier.
   - The gate may live in `decision_making.py` or `readiness_gates.py`, whichever is the existing policy seam.

c) Do not let the planner become the owner of readiness truth, final trading permission, or data fetching.

---------------------------------------------------
ISSUE N-1 [HIGH / PARTIAL]: Analytics restore is strategy-snapshot plumbing, not full owner-domain restore
---------------------------------------------------
Hypothesis:
Snapshot push wiring may already exist, but analytics restore may still be only a strategy-facing truth layer rather than a real owner-domain restore for FE/regime/pillar/bar state.

VERIFY:
1. Read `apps/reference/main.py`.
   - Confirm whether restore snapshots are pushed to handlers at boot.
2. Read `apps/reference/bootstrap/runtime_analytics_restore.py`.
   - Confirm how startup restore state is built and whether any owner-domain restore is actually executed there.
3. Read:
   - `apps/reference/domains/decision_making/aurora_decision.py`
   - `apps/reference/domains/decision_making/mean_reversion_handler.py`
   - `apps/reference/domains/decision_making/md_amr_handler.py`
   - Confirm how restore snapshots affect runtime permissions and readiness payloads.
4. Read owner domains:
   - `apps/reference/domains/feature_engineering/feature_engineering.py`
   - `apps/reference/domains/regime_detector/regime_detector.py`
   - Confirm whether they have a real restore/hydration path at boot.

IF REFUTED:
Do not re-add snapshot push wiring in `main.py`.

IF CONFIRMED OR PARTIAL:
Implement the smallest safe correction so startup cannot claim restored readiness where owner state is actually cold.

Preferred direction:
- Keep existing snapshot push wiring.
- Tighten readiness/restore truth so restore-based permissions cannot overstate owner continuity.
- Avoid introducing shared mutable SSOT caches.

---------------------------------------------------
ISSUE N-4 [HIGH / PARTIAL]: md_amr hydration contract is present but may still be metadata-only
---------------------------------------------------
Hypothesis:
`md_amr_rest_hydration` exists as a named contract and self-report surface, but startup may still not drive any real md_amr hydration path.

VERIFY:
1. Read `apps/reference/domains/decision_making/md_amr_handler.py`.
   - Confirm `describe_runtime_analytics_restore(symbol)` exists.
   - Confirm what `_rest_hydrated`, `_rest_last_bar_ts_ms`, and related restore fields actually mean.
   - Confirm whether startup logic ever feeds them.
2. Read `apps/reference/bootstrap/startup_hydration_planner.py`.
   - Confirm how `local_hydration_contract = "md_amr_rest_hydration"` is used.
3. Check whether md_amr receives actual startup hydration or only reports cold/missing restore state.

IF REFUTED:
Do not re-implement `describe_runtime_analytics_restore()`.

IF CONFIRMED OR PARTIAL:
Apply the smallest safe fix:

a) Keep the existing `describe_runtime_analytics_restore()` surface.
b) If md_amr has no real startup hydration input, make the contract explicitly truthful-as-cold.
c) Ensure md_amr is safely covered by the `bars_required` / sufficiency gate for its 15m / 96+ bar minimum before new-risk signals are allowed.
d) Preserve md_amr protect-only semantics.

---------------------------------------------------
ISSUE N-7 [MEDIUM]: Objective engine preconditions are fail-closed and may be too noisy at startup
---------------------------------------------------
Hypothesis:
Missing `_latest_exposure_summary` and related objective preconditions are blocked safely, but the current path may be too generic/noisy for a normal startup transient.

VERIFY:
1. Read `apps/reference/domains/decision_making/aurora_decision.py`, especially the objective-engine block.
2. Confirm whether missing objective preconditions are caught locally and converted into a strategy block.
3. Read:
   - `apps/reference/domains/decision_making/aurora_handler.py`
   - `apps/reference/domains/decision_making/decision_making.py`
   - `apps/reference/domains/execution_position/event_handlers.py`
   - Confirm how and when exposure summary is populated relative to the first Aurora decision cycle.

IF REFUTED:
Explain exactly why the old audit was wrong.

IF CONFIRMED OR PARTIAL:
Convert the startup-missing-precondition branch into a more explicit precondition block if needed.

Requirements:
- Trading must remain blocked until the precondition is met.
- Do not weaken safety.
- Prefer a specific reason code such as `OBJECTIVE_PRECONDITION_NOT_MET` over a generic exception-shaped fail-closed reason if the current code is too noisy.
- If logging level is changed, startup-normal absence should not be logged as an operational error.

---------------------------------------------------
ISSUE N-6 [LOW / HARDENING]: `scoring_version` validation outside typed config path
---------------------------------------------------
Hypothesis:
This is not a critical live runtime bug because `DecisionConfig.scoring_version` is already typed, but untyped callers may still reach `resolve_requested_quadratic_rollout()`.

VERIFY:
1. Read `apps/reference/config_models.py` and confirm the exact typing of `DecisionConfig.scoring_version`.
2. Read `apps/reference/contracts/quadratic_rollout.py`.
3. Search for callers of `resolve_requested_quadratic_rollout()` and identify whether any non-model / untyped path can reach it.

IF REFUTED:
Drop the issue from remediation and say it is already enforced at config-load time.

IF CONFIRMED AS HARDENING:
Add only a defensive assertion/validation for non-model callers.
Do not present it as a critical live runtime fix.

===========================================
TEST AND VALIDATION REQUIREMENTS
===========================================

Run targeted validation for every surviving issue:

1. Startup boot path
   - Verify restore report is built.
   - Verify restore snapshots are pushed to handlers.
   - Verify hydration plan is built.
   - Verify there is no hidden executor path being skipped.

2. Cold restart with no historical basis-bar hydration
   - Verify `bars_required` / readiness blocking behavior.
   - Verify no accidental new-risk opening before sufficiency is met.

3. md_amr startup with cold local hydration
   - Verify truthful restore status.
   - Verify blocked new-risk behavior until sufficiency is met.
   - Verify protect-only semantics remain intact.

4. Aurora objective engine startup before exposure summary arrives
   - Verify explicit precondition block behavior.
   - Verify logging is not escalated as an operational error if the condition is startup-normal.

5. Config-load negative validation for invalid `scoring_version`
   - Only if the hardening task remains in scope.

===========================================
OUTPUT FORMAT
===========================================

After verification and any fixes, produce a report in this exact structure:

## Issue N-2/N-3: [CONFIRMED|REFUTED|PARTIAL]
**Evidence:** file:line - exact evidence
**Fix applied:** description of what was changed, or "N/A - refuted"
**Disagreement:** specific reason with code evidence, if any

## Issue N-1: [CONFIRMED|REFUTED|PARTIAL]
**Evidence:** file:line - exact evidence
**Fix applied:** description of what was changed, or "N/A - refuted"
**Disagreement:** specific reason with code evidence, if any

## Issue N-4: [CONFIRMED|REFUTED|PARTIAL]
**Evidence:** file:line - exact evidence
**Fix applied:** description of what was changed, or "N/A - refuted"
**Disagreement:** specific reason with code evidence, if any

## Issue N-7: [CONFIRMED|REFUTED|PARTIAL]
**Evidence:** file:line - exact evidence
**Fix applied:** description of what was changed, or "N/A - refuted"
**Disagreement:** specific reason with code evidence, if any

## Issue N-6: [CONFIRMED|REFUTED|PARTIAL]
**Evidence:** file:line - exact evidence
**Fix applied:** description of what was changed, or "N/A - refuted"
**Disagreement:** specific reason with code evidence, if any

## Overall Assessment
Summary of:
- what stale claims were refuted
- what runtime gaps were actually confirmed
- what was fixed
- what remains deferred
- whether the code is safer but still not ready for any Quadratic config flip

===========================================
CONSTRAINTS
===========================================

- Read code first before making any changes.
- Base claims on live code under `apps/reference/`, not on old audit prose.
- Prefer wiring existing startup-capable mechanisms over adding new architecture.
- Do not modify YAML configs unless a fix explicitly requires it.
- Do not modify tests unless directly validating one of the surviving issues.
- Every fix must include a code comment referencing the surviving issue ID, for example `# FIX:N-2`.
- If you disagree with the old audit, say so clearly and do not patch around a refuted claim.
- Preserve current runtime invariants:
  - no Quadratic live flip
  - no MR or md_amr regression
  - no merging of manage-existing-risk with open-new-risk permissions
  - no planner-owned readiness truth

Treat the old audit as hypothesis only. The live code is the source of truth.
```

## Notes

- This rewrite is designed for current live code, not the original stale audit framing.
- The primary purpose is to force verify-first remediation and prevent false-positive churn.
- If a future code change invalidates one of the "known live-code truths" above, update this prompt before reuse.
