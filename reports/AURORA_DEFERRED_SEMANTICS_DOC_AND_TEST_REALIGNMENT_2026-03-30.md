# AURORA_DEFERRED_SEMANTICS_DOC_AND_TEST_REALIGNMENT

**Date**: 2026-03-30  
**Package**: AURORA_DEFERRED_SEMANTICS_DOC_AND_TEST_REALIGNMENT  
**Scope**: aurora deferred semantics docs/tests/comments, plus minimal topic-local defect fix proven during realignment  
**Status**: DONE WITH RESERVATIONS

---

## 1. Executive Verdict

### DONE WITH RESERVATIONS

**Are docs/tests now aligned with proven aurora deferred semantics?**  
Yes. Active repo docs, comments, schema wording, and the stale aurora tests found in scope now state the same current truth:

- normal live aurora no-trade outcomes -> `EVT:STRATEGY_DECISION_BLOCKED`
- aurora kernel `EVT:INTENT_DEFERRED` -> narrow anomaly/fail-closed path after the quadratic path is reached

**Was any runtime logic change required?**  
Yes, one minimal runtime fix was required and justified by new evidence. While realigning stale tests, a real defect surfaced: actual aurora kernel raw defer reasons such as `PILLAR_WARMUP` were not accepted by [`decision_truth_artifacts.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/decision_truth_artifacts.py):31-78, causing the canonical deferred emit path to fail with `ValueError`. The package fixed only that canonicalization seam.

**What remains open as a design choice rather than a bug?**  
Whether aurora should keep this anomaly-only deferred semantic long-term or later collapse it into another policy class is still an architecture choice. Under current proven truth, it remains a valid but rare fail-closed class.

---

## 2. FACTS

1. The aurora kernel producer emits raw defer reasons such as `PILLAR_WARMUP` and `MISSING_REGIME_THRESHOLD:<regime>` in [`quadratic_scoring_kernel.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py):195, [quadratic_scoring_kernel.py](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py):299.
2. The aurora deferred branch canonicalizes and emits `EVT:INTENT_DEFERRED` in [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):579, [aurora_decision.py](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):629.
3. Before this package, `canonicalize_intent_deferred_reason()` did not accept the real aurora raw reasons above; a stale test run failed with `ValueError: Unsupported INTENT_DEFERRED reason: PILLAR_WARMUP`.
4. The canonicalization seam is now covered explicitly in [`test_decision_truth_artifacts.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_decision_truth_artifacts.py):101.
5. The stale tests that previously encoded blocked semantics for aurora kernel anomalies were:
   - [`test_pillar_to_decision_e2e.py`](c:/Users/user/Music/Phenix/tests/integration/test_pillar_to_decision_e2e.py):99
   - [`test_aurora_quadratic_logging.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_quadratic_logging.py):83
   - [`test_aurora_runtime_readiness_contract.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_runtime_readiness_contract.py):758
6. Current semantic policy is now stated directly in:
   - [`README.md`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/README.md):120
   - [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):10
   - [`quadratic_scoring_kernel.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py):24
   - [`aurora_math_passport.md`](c:/Users/user/Music/Phenix/config/docs/aurora_math_passport.md):254
   - [`intent_deferred_v1.json`](c:/Users/user/Music/Phenix/schemas/intent_deferred_v1.json):5
7. The prior activation report is now annotated with a superseded note in [`CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION_2026-03-30.md`](c:/Users/user/Music/Phenix/reports/CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION_2026-03-30.md):3.

---

## 3. INFERENCES

1. The repo drift was not purely documentary. A stale test exposed a real runtime defect in canonical deferred-reason handling.
2. After the fix, current repo truth is internally coherent:
   - aurora kernel anomaly defer stays `INTENT_DEFERRED`
   - normal live no-trade aurora policy outcomes stay `STRATEGY_DECISION_BLOCKED`
3. The fix is additive-safe because it only broadens accepted canonical raw reasons for already-existing aurora defer producers; it does not change the producer conditions or blocked-policy gates.

---

## 4. ASSUMPTIONS

1. The fresh live-runtime truth established in the earlier 2026-03-30 investigation remains the authoritative behavioral baseline for aurora.
2. No other in-scope active docs outside the files updated here materially contradict current aurora deferred semantics.

---

## 5. UNKNOWNS

1. Whether live production will eventually hit the anomaly-only aurora deferred path remains unproven in fresh runtime.
2. Whether future architecture should preserve or retire anomaly-only aurora defer is still open.

---

## 6. Semantic Policy Note

**`EVT:INTENT_DEFERRED` on aurora**  
On the aurora quadratic path, `INTENT_DEFERRED` is a reachable but narrow anomaly/fail-closed class. It is used only after the kernel path is reached and the kernel cannot safely continue because inputs or threshold state are invalid or unavailable.

**`EVT:STRATEGY_DECISION_BLOCKED` on aurora**  
`STRATEGY_DECISION_BLOCKED` is the normal dominant live no-trade class for ordinary policy or readiness denials such as cold-start bars gating and regime allowlist denial. It is not interchangeable with aurora kernel anomaly defer.

---

## 7. Drift Inventory

| File | Location | Old expectation | Conflict with proven truth | Action taken |
|---|---|---|---|---|
| [`tests/integration/test_pillar_to_decision_e2e.py`](c:/Users/user/Music/Phenix/tests/integration/test_pillar_to_decision_e2e.py) | :99-142 | Missing `pillar_sum` should emit `STRATEGY_DECISION_BLOCKED` with `AURORA_KERNEL_DEFERRED` | `PILLAR_WARMUP` is aurora kernel anomaly defer, not blocked policy truth | Updated test to expect canonical `EVT:INTENT_DEFERRED`, `reason_code=NRR-DATA-NOT-READY`, `raw_reason=PILLAR_WARMUP` |
| [`tests/domains/decision_making/test_aurora_quadratic_logging.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_quadratic_logging.py) | :83-141 | Deferred-path logging test asserted blocked emission | Conflicted with current taxonomy and actual emit branch | Updated test to capture emitted events and assert deferred, not blocked |
| [`tests/domains/decision_making/test_aurora_runtime_readiness_contract.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_runtime_readiness_contract.py) | :758-847 | Seeded-basis case still expected blocked semantics | Seeded basis bypasses cold-start blocked gate and reaches anomaly defer | Updated test to expect canonical deferred event; removed stale patch of nonexistent reject helper |
| [`apps/reference/domains/decision_making/README.md`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/README.md) | :120-126 | No explicit aurora blocked-vs-deferred semantic note | Future maintainers could infer defer is a normal no-trade class | Added explicit semantic note |
| [`apps/reference/domains/decision_making/aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) | :10-13, :568-571 | Deferred branch had no local semantic warning | Reader could misread deferred as generic no-trade outcome | Added module note and branch comment |
| [`apps/reference/domains/decision_making/quadratic_scoring_kernel.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py) | :24-28 | Kernel docstring did not say defer is anomaly-only on aurora | Encouraged semantic overreach | Added deferred-output note |
| [`config/docs/aurora_math_passport.md`](c:/Users/user/Music/Phenix/config/docs/aurora_math_passport.md) | :254-262 | Missing `pillar_sum` described as defer, but not bounded against blocked policy truth | Left room to misread defer as dominant live no-trade semantic | Clarified anomaly/fail-closed meaning and canonical reason |
| [`schemas/intent_deferred_v1.json`](c:/Users/user/Music/Phenix/schemas/intent_deferred_v1.json) | :5 | Schema description lacked aurora-specific semantic note | Contract wording lagged behind proven runtime meaning | Added concise aurora semantic note |
| [`reports/CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION_2026-03-30.md`](c:/Users/user/Music/Phenix/reports/CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION_2026-03-30.md) | :3-4 | Report said path was not broken without the later canonicalization finding | Now incomplete as active reference | Added superseded note pointing to this report |
| [`apps/reference/domains/decision_making/decision_truth_artifacts.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/decision_truth_artifacts.py) | :31-78 | Real aurora raw defer reasons were rejected | This was a bug, not doc drift | Added canonical mappings for aurora anomaly raw reasons |

---

## 8. Root Cause

### A. Semantic drift in tests/docs

- **Cause**: earlier repo expectations still modeled aurora kernel anomaly outcomes as blocked truth.
- **Mechanism**: tests and docs kept asserting `STRATEGY_DECISION_BLOCKED` or generic fail-closed wording for `PILLAR_WARMUP`.
- **Effect**: future refactors would be pushed toward the wrong taxonomy, and the actual deferred branch looked semantically suspect.
- **Operational risk**: maintainers could silently collapse aurora anomaly defer back into blocked truth.

### B. Narrow runtime defect in canonicalization

- **Cause**: `decision_truth_artifacts.canonicalize_intent_deferred_reason()` lagged behind real aurora kernel raw reasons.
- **Mechanism**: aurora producer emitted `PILLAR_WARMUP`, `LINEAR_SCORE_INVALID`, `LINEAR_SCORE_NAN_INF`, and `MISSING_REGIME_THRESHOLD:<regime>`, but canonicalization rejected them.
- **Effect**: the intended canonical deferred path raised `ValueError` instead of emitting `EVT:INTENT_DEFERRED` for those real anomaly reasons.
- **Operational risk**: a true aurora kernel anomaly would fail at emit time and leave maintainers with a false belief that deferred semantics were merely rare rather than partially broken.

---

## 9. Change Set

| File | Location | What changed | Why | Type |
|---|---|---|---|---|
| [`apps/reference/domains/decision_making/decision_truth_artifacts.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/decision_truth_artifacts.py) | :39-67 | Added aurora raw defer mappings and prefix handling for missing regime threshold | Fix real canonicalization defect exposed by stale-test realignment | Minimal runtime logic |
| [`tests/domains/decision_making/test_decision_truth_artifacts.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_decision_truth_artifacts.py) | :101-116 | Added unit test for aurora raw defer canonicalization | Lock bugfix in place | Test |
| [`tests/integration/test_pillar_to_decision_e2e.py`](c:/Users/user/Music/Phenix/tests/integration/test_pillar_to_decision_e2e.py) | :99-142 | Reframed missing-`pillar_sum` path as anomaly deferred | Remove stale blocked expectation | Test |
| [`tests/domains/decision_making/test_aurora_quadratic_logging.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_quadratic_logging.py) | :83-141 | Assert deferred emission and preserve decision-trace proof | Align logging contract with current semantics | Test |
| [`tests/domains/decision_making/test_aurora_runtime_readiness_contract.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_runtime_readiness_contract.py) | :758-847 | Updated seeded-basis case to expect anomaly deferred; removed stale reject patch | Align readiness contract with actual branch behavior | Test |
| [`apps/reference/domains/decision_making/README.md`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/README.md) | :120-126 | Added aurora semantic note | Make current truth discoverable | Docs |
| [`apps/reference/domains/decision_making/aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py) | :10-13, :568-571 | Added semantic note and branch comment | Prevent re-drift near emit branch | Comment/docstring |
| [`apps/reference/domains/decision_making/quadratic_scoring_kernel.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py) | :24-28 | Added deferred-output note | Bind producer semantics to current aurora policy | Comment/docstring |
| [`config/docs/aurora_math_passport.md`](c:/Users/user/Music/Phenix/config/docs/aurora_math_passport.md) | :254-262 | Clarified anomaly-only defer meaning | Align passport with proven runtime truth | Docs |
| [`schemas/intent_deferred_v1.json`](c:/Users/user/Music/Phenix/schemas/intent_deferred_v1.json) | :5 | Added aurora-specific schema description note | Align contract wording | Schema doc |
| [`reports/CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION_2026-03-30.md`](c:/Users/user/Music/Phenix/reports/CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION_2026-03-30.md) | :3-4 | Added superseded note | Preserve history without leaving active contradiction | Report |

---

## 10. Validation Evidence

### Tests Run

```text
pytest tests/domains/decision_making/test_decision_truth_artifacts.py::test_canonicalize_intent_deferred_reason_accepts_aurora_kernel_fail_closed_reasons tests/integration/test_pillar_to_decision_e2e.py::test_cmd_process_strategy_missing_pillar_sum_emits_anomaly_deferred tests/domains/decision_making/test_aurora_quadratic_logging.py::test_quadratic_decision_trace_logs_on_deferred_path tests/domains/decision_making/test_aurora_runtime_readiness_contract.py::test_aurora_seeded_basis_bars_bypass_cold_start_gate_into_anomaly_deferred tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py::test_kernel_deferred_emits_intent_deferred_not_strategy_blocked -q
```

Result: `5 passed in 1.40s`

### Before / After Evidence

- Before:
  - stale tests expected `STRATEGY_DECISION_BLOCKED` with `AURORA_KERNEL_DEFERRED`
  - real aurora raw reason `PILLAR_WARMUP` crashed canonical deferred emission
- After:
  - tests assert `EVT:INTENT_DEFERRED`
  - canonical payload preserves `reason_code=NRR-DATA-NOT-READY` plus `raw_reason=PILLAR_WARMUP`
  - controlled integration still proves aurora deferred does not collapse into blocked truth

### Proof runtime behavior was not broadly altered

The package did not change aurora producer conditions, blocked-policy gates, retry scheduling, or strategy routing. The only runtime behavior change was the narrow bugfix that allows already-produced aurora kernel anomaly reasons to complete the canonical deferred emit path instead of throwing `ValueError`.

---

## 11. Proven vs Unproven

### Proven Runtime Truth

- Fresh live aurora no-trade outcomes are dominated by `STRATEGY_DECISION_BLOCKED`.
- Aurora kernel deferred semantics are anomaly-only / fail-closed under current proven runtime interpretation.

### Repo Expectations Now Aligned

- Active docs and schema wording now state blocked-vs-deferred aurora semantics explicitly.
- Stale tests no longer enforce blocked semantics for aurora kernel anomaly defer.
- Canonicalization now accepts real aurora raw defer reasons.

### Still Open Design Questions

- Should aurora keep anomaly-only `INTENT_DEFERRED` long-term?
- Should future architecture preserve raw anomaly reasons exactly as-is or promote a tighter defer-specific taxonomy?

### Residual Ambiguities

- Fresh live proof of a real post-deploy aurora anomaly hitting `INTENT_DEFERRED` is still absent.
- Historical documents outside the active in-scope truth anchors may still mention older semantics, but no additional active contradiction was found in the files inspected for this package.

---

## 12. Next-Step Recommendation

**One exact next package:** `AURORA_DEFERRED_LIVE_OBSERVABILITY_PROOF_OR_DEPRECATION_DECISION`

Purpose:
- either capture real live evidence of aurora anomaly defer activating,
- or, if it remains absent over a broader operational window, make an explicit architecture decision to keep, tighten, or deprecate the anomaly-only deferred semantic.

---

## 13. Final Conclusion

The repository now reflects the current aurora truth more honestly than before. `INTENT_DEFERRED` is documented and tested as a reachable anomaly-only fail-closed class, while ordinary live aurora no-trade outcomes remain `STRATEGY_DECISION_BLOCKED`. The only runtime change was a narrow bugfix required to make the already-intended canonical deferred path actually accept real aurora kernel raw reasons.
