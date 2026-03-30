# CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION

> Superseded note (2026-03-30, follow-up package `AURORA_DEFERRED_SEMANTICS_DOC_AND_TEST_REALIGNMENT`):
> this report correctly established that the aurora deferred producer path is reachable and live-absent in the fresh window, but a later stale-test realignment uncovered a narrower runtime defect in canonicalization of real aurora kernel raw defer reasons such as `PILLAR_WARMUP`. See `AURORA_DEFERRED_SEMANTICS_DOC_AND_TEST_REALIGNMENT_2026-03-30.md` for the corrected final repo truth.

**Date**: 2026-03-30  
**Package**: CLARIFY_INTENT_DEFERRED_KERNEL_DEFER_ACTIVATION  
**Scope**: `EVT:INTENT_DEFERRED` on aurora/quadratic kernel path only  
**Status**: DONE WITH RESERVATIONS

---

## 1. Executive Verdict

### DONE WITH RESERVATIONS

**Is `INTENT_DEFERRED` alive, intentionally inactive, dead, or broken?**

`INTENT_DEFERRED` on the aurora kernel path is **reachable and not broken**, but **not live-proven in the fresh 2026-03-30 runtime window**.  
The exact current classification is:

- **Runtime evidence verdict**: `REACHABLE_NOT_OBSERVED`
- **Operational truth**: aurora kernel defer is currently an **anomaly/fail-closed path**, not a dominant live policy path

**Is there live runtime proof?**

- **Fresh live WAL proof (2026-03-30)**: **NO**
- **Fresh live shadow proof (2026-03-30)**: **NO**
- **Controlled runtime-like proof**: **YES**

**Exact current truth**

`INTENT_DEFERRED` did not disappear because the emit path is broken. It is runtime-absent because the real aurora/quadratic producer only sets `deferred=True` under narrow fail-closed anomaly conditions, while the actual non-tradable states observed on 2026-03-30 were emitted as `STRATEGY_DECISION_BLOCKED` instead.

This means:

1. `INTENT_DEFERRED` is **not dead code**.
2. `INTENT_DEFERRED` is **not proven live** in the fresh post-hardening window.
3. The current aurora runtime is dominated by **blocked** outcomes (`REGIME_NOT_ALLOWLISTED`, `BARS_REQUIRED_COLD_START`), not kernel defer outcomes.

---

## 2. FACTS

### Code Facts

1. The real aurora kernel producer is [`quadratic_scoring_kernel.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py):189, :196, :201, :293.
   It sets `result.deferred = True` only for:
   - `PILLAR_WARMUP`
   - `LINEAR_SCORE_INVALID`
   - `LINEAR_SCORE_NAN_INF`
   - `MISSING_REGIME_THRESHOLD:<regime>`

2. The aurora transform path from `result.deferred` to canonical event is live in [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):566, :590, :620.
   Mechanism:
   - detect `if result.deferred`
   - canonicalize reason
   - `write_intent_deferred(...)`
   - `emit_fn("EVT:INTENT_DEFERRED", retry_payload)`

3. The retry consumer path is bound in [`main.py`](c:/Users/user/Music/Phenix/apps/reference/main.py):729, :756, :765.
   `EVT:INTENT_DEFERRED` is forwarded to `RetryScheduler.register_deferred(...)`.

4. The aurora regime-threshold lookup does not intentionally disable defer.
   [`aurora_scoring_helpers.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py):248 returns per-symbol thresholds or global fallback.

5. Global aurora config defines regime thresholds for all major runtime regimes in [`aurora.yaml`](c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml):234.

6. Per-symbol aurora configs for live symbols also define `allowed_regimes`, and several exclude `UNCERTAIN`:
   - [`aurora.yaml`](c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml):517
   - [`aurora.yaml`](c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml):629
   - [`aurora.yaml`](c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml):761

7. Live aurora policy gates emit `BLOCKED`, not `DEFERRED`, for dominant observed states:
   - cold-start bars gate in [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):262, :269
   - strict regime allowlist gate in [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):686-706
   - regime kill-switch in [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):794

### Fresh Runtime Facts

8. Fresh 2026-03-30 aurora logs contain **483** `KERNEL_DIAG ... deferred=False` lines across `logs/aurora_core.log*`.

9. Fresh 2026-03-30 aurora logs contain **0** matches for:
   - `deferred=True`
   - `Kernel deferred`
   - `PILLAR_WARMUP`
   - `LINEAR_SCORE_INVALID`
   - `LINEAR_SCORE_NAN_INF`
   - `MISSING_REGIME_THRESHOLD`

10. Fresh live canonical artifact search shows:
   - `ops/wal/2026-03-30.jsonl`: **0** `INTENT_DEFERRED`
   - `logs/shadow_critical_event_journal_v1.jsonl`: **0** `INTENT_DEFERRED`

11. Fresh live blocked truth is abundant:
   - `ops/wal/2026-03-30.jsonl`: **101** `REGIME_NOT_ALLOWLISTED`
   - `ops/wal/2026-03-30.jsonl`: **480** `BARS_REQUIRED_COLD_START`

12. Fresh shadow also shows `STRATEGY_DECISION_BLOCKED` rows for those same classes, while `INTENT_DEFERRED` remains absent.

### Controlled Evidence Facts

13. Controlled runtime-like proof exists in [`test_aurora_timer_integration_contract_v1.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py):269.
   The test `test_kernel_deferred_emits_intent_deferred_not_strategy_blocked` passed on 2026-03-30.

14. `ops/wal/2026-03-29.jsonl` contains exactly **3** `INTENT_DEFERRED` rows, and all three map to test-like / controlled evidence, not fresh live 2026-03-30 production behavior:
   - `rid-kernel-defer` matches [`test_aurora_timer_integration_contract_v1.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py):311
   - `rid-1` + `stratX` matches [`test_degraded_context_gate_config_wiring_strategy_gateway_v1.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_degraded_context_gate_config_wiring_strategy_gateway_v1.py):53
   - `flip:BTCUSDT:SELL:r1` matches [`test_retry_scheduler_integration_v1.py`](c:/Users/user/Music/Phenix/tests/integration/test_retry_scheduler_integration_v1.py):54

15. Shadow capture is configured to record deferred truth in [`shadow_journal.py`](c:/Users/user/Music/Phenix/apps/reference/telemetry/shadow_journal.py):14-20 and validated in [`test_decision_truth_artifacts.py`](c:/Users/user/Music/Phenix/tests/domains/decision_making/test_decision_truth_artifacts.py):149.

---

## 3. INFERENCES

1. The aurora kernel defer path is **reachable in code** and **emits correctly** when `result.deferred=True`.

2. The absence of fresh `INTENT_DEFERRED` is **not an emit bug**, because:
   - canonical transform code exists,
   - retry consumer exists,
   - controlled test proves end-to-end emission,
   - shadow capture is configured.

3. The fresh runtime absence is explained by **producer non-activation**, not consumer loss.

4. Under current aurora runtime policy, ordinary “cannot trade now” situations are being expressed as `BLOCKED`, especially:
   - regime disallow (`REGIME_NOT_ALLOWLISTED`)
   - cold-start readiness (`BARS_REQUIRED_COLD_START`)

5. Therefore `INTENT_DEFERRED` is not the dominant semantic for aurora runtime policy denials. It is effectively reserved for fail-closed anomaly conditions in the kernel/input contract.

---

## 4. ASSUMPTIONS

1. The 2026-03-30 logs and WAL/shadow files reflect the relevant post-hardening live window the user asked to inspect.

2. The three `INTENT_DEFERRED` rows in `ops/wal/2026-03-29.jsonl` are controlled/test-like because their identifiers and payload shapes map directly to test fixtures.

3. No hidden out-of-band sink writes `INTENT_DEFERRED` outside WAL/shadow for this aurora path.

---

## 5. UNKNOWNS

1. Whether a real production anomaly will eventually trigger aurora kernel defer without controlled reproduction remains unproven.

2. Whether the business still wants a dedicated aurora kernel defer semantic for `PILLAR_WARMUP`-class failures, or would prefer to document that all such cases should remain `BLOCKED`, is not yet formally decided.

---

## 6. Reachability Map

### Producer of `deferred=True`

Authoritative producer:
- [`quadratic_scoring_kernel.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/quadratic_scoring_kernel.py):189, :196, :201, :293

Producer conditions:
- `features["pillar_sum"] is None` -> `PILLAR_WARMUP`
- `pillar_sum` not parseable -> `LINEAR_SCORE_INVALID`
- `pillar_sum` is `NaN` or `Inf` -> `LINEAR_SCORE_NAN_INF`
- regime threshold factor missing -> `MISSING_REGIME_THRESHOLD:<regime>`

### Transform into `EVT:INTENT_DEFERRED`

Transform path:
- [`aurora_decision.py`](c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py):566-620

Mechanism:
- detect `result.deferred`
- canonicalize reason
- write canonical WAL row
- emit `EVT:INTENT_DEFERRED`

### Consumer expectation

Consumer path:
- [`main.py`](c:/Users/user/Music/Phenix/apps/reference/main.py):756-765

Mechanism:
- FSM listener catches `EVT:INTENT_DEFERRED`
- forwards payload to `RetryScheduler.register_deferred(...)`

### Branches that replace or preempt defer

Pre-kernel replacements:
- bars-required gate -> `STRATEGY_DECISION_BLOCKED`
- regime liveness guard -> `STRATEGY_DECISION_BLOCKED`
- liquidity gate -> `STRATEGY_DECISION_BLOCKED`

Post-kernel replacements:
- strict regime allowlist -> `STRATEGY_DECISION_BLOCKED`
- regime kill-switch -> `STRATEGY_DECISION_BLOCKED`

Important distinction:
- I found **no evidence** that `result.deferred=True` is later swallowed and rewritten to another class.
- I did find strong evidence that **most live non-tradable states never become `result.deferred` in the first place**.

---

## 7. Runtime Evidence Matrix

| Check | Result |
|---|---|
| Live WAL proof on 2026-03-30 | **NO** |
| Live shadow proof on 2026-03-30 | **NO** |
| Live log proof of deferred computation on 2026-03-30 | **NO** |
| Controlled runtime-like proof | **YES** |
| Final evidence verdict | **`REACHABLE_NOT_OBSERVED`** |

### Why the 2026-03-29 WAL rows do not count as fresh live proof

They are controlled/test-like artifacts:

1. `rid-kernel-defer` is directly referenced by a targeted contract test.
2. `stratX` + `rid-1` matches the degraded-context wiring test.
3. `flip:BTCUSDT:SELL:r1` matches retry-scheduler integration test data.

These rows prove **reachability**, not fresh production activation.

---

## 8. Root Cause

### Root Cause A: producer is anomaly-only

- **Cause**: the real `QuadraticScoringKernel` only emits `deferred=True` for fail-closed anomaly conditions.
- **Mechanism**: missing/invalid `pillar_sum`, non-finite score, or missing regime-threshold factor are the only real deferred triggers.
- **Effect**: when market data and config are healthy, aurora kernel returns `deferred=False`.
- **Operational risk**: operators may expect `INTENT_DEFERRED` to be a normal “not yet tradable” state, but in aurora it currently behaves more like an anomaly-only truth class.

### Root Cause B: live non-tradable states are classified as `BLOCKED`

- **Cause**: live aurora policy gates use explicit blocked semantics.
- **Mechanism**:
  - cold-start bars gate blocks before quadratic path
  - strict regime allowlist blocks after scoring
  - some symbols explicitly exclude `UNCERTAIN`
- **Effect**: fresh runtime emits `STRATEGY_DECISION_BLOCKED` instead of `INTENT_DEFERRED`.
- **Operational risk**: deferred truth can look “dead” even though the real issue is semantic displacement by blocked truth.

### Root Cause C: test/doc semantics are not fully aligned

- **Cause**: older tests still encode blocked semantics for `PILLAR_WARMUP`.
- **Mechanism**: for example [`test_pillar_to_decision_e2e.py`](c:/Users/user/Music/Phenix/tests/integration/test_pillar_to_decision_e2e.py):128-138 still expects `STRATEGY_DECISION_BLOCKED` with `AURORA_KERNEL_DEFERRED`.
- **Effect**: the repo still contains mixed assumptions about whether aurora kernel warmup should be `DEFERRED` or `BLOCKED`.
- **Operational risk**: future maintainers may “fix” the wrong layer because the semantic contract is still described in two incompatible ways.

---

## 9. Proven vs Unproven

### Proven in live runtime

- `INTENT_DEFERRED` is **absent** from fresh 2026-03-30 WAL and shadow.
- `STRATEGY_DECISION_BLOCKED` is **live-dominant** for current aurora no-trade states.
- fresh aurora logs show `deferred=False` repeatedly and no deferred-computation markers.

### Proven in code/tests only

- aurora kernel defer producer exists.
- aurora deferred emit path exists and writes canonical WAL/event artifacts.
- retry consumer exists.
- a controlled contract test proves `result.deferred=True` becomes `EVT:INTENT_DEFERRED`.

### Still unproven

- a fresh real live aurora case where the actual production kernel naturally reaches `deferred=True`.

### Anomalies / contradictions

- Current code emits canonical `INTENT_DEFERRED` when `result.deferred=True`, but older tests still expect blocked truth for `PILLAR_WARMUP`.
- Canonical deferred reason taxonomy includes `REGIME_BLOCKED`, but the real `QuadraticScoringKernel` does not natively emit that reason; in fresh live runtime, regime-related no-trade states are emitted as `BLOCKED`.

---

## 10. Validation Evidence

### Artifact search results

- `logs/aurora_core.log*`: **483** `KERNEL_DIAG ... deferred=False`
- `logs/aurora_core.log*`: **0** `deferred=True`
- `logs/aurora_core.log*`: **0** `Kernel deferred`
- `ops/wal/2026-03-30.jsonl`: **0** `INTENT_DEFERRED`
- `logs/shadow_critical_event_journal_v1.jsonl`: **0** `INTENT_DEFERRED`
- `ops/wal/2026-03-30.jsonl`: **101** `REGIME_NOT_ALLOWLISTED`
- `ops/wal/2026-03-30.jsonl`: **480** `BARS_REQUIRED_COLD_START`

### Controlled runtime-like proof

Executed:

```bash
pytest tests/domains/decision_making/test_aurora_timer_integration_contract_v1.py::test_kernel_deferred_emits_intent_deferred_not_strategy_blocked -q
```

Result:

```text
1 passed in 2.69s
```

Interpretation:
- emit path is reachable
- canonical aurora defer plumbing is not broken
- runtime absence must be explained upstream at the producer/policy layer

---

## 11. Final Conclusion

`INTENT_DEFERRED` remains runtime-absent in the fresh post-hardening aurora window because the real quadratic kernel only defers on narrow fail-closed anomaly inputs, and none of those were observed in fresh runtime. The live system instead expressed current no-trade states through `STRATEGY_DECISION_BLOCKED`, especially regime allowlist and cold-start bars gates.

So the honest current truth is:

- **not broken emit**
- **not dead code**
- **not intentionally feature-flag-disabled**
- **reachable, anomaly-only, and not observed in fresh live runtime**

The correct artifact verdict is **`REACHABLE_NOT_OBSERVED`**.

---

## 12. Next-Step Recommendation

### Exactly one next package

**AURORA_DEFERRED_SEMANTICS_DOC_AND_TEST_REALIGNMENT**

Objective:
- document that aurora kernel defer is currently an anomaly/fail-closed path, not the primary “cannot trade now” path
- realign stale tests/docs that still expect `PILLAR_WARMUP`-class outcomes to appear as `BLOCKED`
- explicitly state whether aurora wants to keep anomaly-only `INTENT_DEFERRED` semantics or collapse those specific kernel anomalies into `BLOCKED`

This is the narrowest safe next package because the current evidence does **not** justify functional code changes.
