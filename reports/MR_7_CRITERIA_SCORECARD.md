# MR 7-Criteria Scorecard

## Score table

| Criterion | Score (0-10) | Weight | Weighted contribution |
|---|---:|---:|---:|
| C1 Repository truth and diff proof | 8.0 | 0.20 | 1.60 |
| C2 Contract fidelity | 5.0 | 0.20 | 1.00 |
| C3 Mathematical correctness | 6.0 | 0.20 | 1.20 |
| C4 Architectural boundary integrity | 6.5 | 0.15 | 0.975 |
| C5 Safety and fallback semantics | 7.0 | 0.10 | 0.70 |
| C6 Test quality and evidence strength | 4.0 | 0.10 | 0.40 |
| C7 Docs / reports / code parity | 3.0 | 0.05 | 0.15 |

## Weighted total

Using the required formula:

```
total_score =
  0.20*C1 +
  0.20*C2 +
  0.20*C3 +
  0.15*C4 +
  0.10*C5 +
  0.10*C6 +
  0.05*C7
```

Substitution:

```
total_score =
  0.20*8.0 +
  0.20*5.0 +
  0.20*6.0 +
  0.15*6.5 +
  0.10*7.0 +
  0.10*4.0 +
  0.05*3.0
```

Result:

```
total_score = 6.025 / 10
```

Rounded overall score: **6.03 / 10**

Final overall implementation grade: **C**

## Criterion justifications

### C1 Repository truth and diff proof - 8.0 / 10

This scores relatively high because the implementation is clearly real: the target source files, YAML, passport, and test files all exist and contain the claimed V1/V2 additions. Earlier branch-status evidence also showed a meaningful subset of those changes in committed branch history relative to the merge-base. The deduction from a perfect score comes from uneven proof quality across surfaces: several later reports and the V2 behavioral test file were only working-tree artifacts at audit time, so not every narrative claim carries the same history-level confidence.

### C2 Contract fidelity - 5.0 / 10

This is only middling because the contract is implemented correctly for some surfaces and not for others. V2 mostly matches the simplified ratified contract. V1 exists, is strict, and is placed in the correct handler boundary. But V1's actual runtime input contract is incomplete: the handler expects nested `features.price_motion`, while the inspected FE -> CMD path does not provide it in that shape. That is a real fidelity gap against the intended bivariate design.

### C3 Mathematical correctness - 6.0 / 10

V2 math in code is correct. The funding normalization, clamp, and trigger geometry are coherent, and the crowd-fade interpretation is sound once the real inequalities are used. V1 heuristics are also internally coherent. The score is reduced because V1 mathematical intent depends on a price-reaction input that is not wired into the runtime path as expected, so actual deployed behavior would not fully match the intended math. In other words, the formulae are not the main problem; runtime data availability is.

### C4 Architectural boundary integrity - 6.5 / 10

The implementation mostly respects architecture. V1 is a handler overlay instead of a strategy-core rewrite. V2 uses handler-side preprocessing and strategy-side threshold consumption with per-symbol strategy instances. That is good boundary discipline. The score stays below strong because mutation-based threshold injection is still a mutable pattern, there is stale dead code in `_on_features_calculated()`, and the register docstring advertises data-caching behavior that is not actually wired. Those issues do not destroy the boundary, but they do weaken confidence.

### C5 Safety and fallback semantics - 7.0 / 10

Safety semantics are one of the stronger parts. V1 now fail-closes on missing or invalid TFI, on OBI when OBI confirmation is required, on warmup, and on zero-range bars. V2 degrades gracefully to static split thresholds when funding is missing or invalid. That is directionally correct. The deduction comes from practical behavior under current repository defaults: V1 can over-block because its price-motion branch is not properly wired, and V2 likely remains static under current feature-engineering defaults. Safe is not the same as rollout-ready.

### C6 Test quality and evidence strength - 4.0 / 10

Even though 66 targeted tests passed, the evidence is much weaker than the reports claim. The helper methods are tested; the runtime integration is not. Handler coverage is only 20%, strategy coverage only 49%, and several tests with ambitious names do not actually prove the behavior they claim. In particular, the V1 tests use nested `features.price_motion` that the real MR CMD path does not prove, and the V2 cleanup test simulates manual clearing instead of executing the real finally block.

### C7 Docs / reports / code parity - 3.0 / 10

This is the weakest criterion. Current code, YAML, passport, and reports do not tell one consistent story. `config_models.py` still contains inverted V2 prose. `REPORT_PACK_1`, `REPORT_PACK_3`, `REPORT_PACK_4`, and `REPORT_PACK_6` are stale or wrong relative to current code and tests. `REPORT_PACK_R4` says parity is complete, but it is not. The passport is closer to source truth than the older report packs, but overall parity remains poor.

## Overall score interpretation

**6.03 / 10** means the repository contains real and partly solid implementation work, but not enough evidence quality or contract fidelity to justify high trust. This is not a fabricated implementation, and it is not total failure. It is a moderate-quality, safety-biased, partially integrated layer that still needs concrete runtime and evidence repairs before enablement.

## Final assessment

### As dormant code

Acceptable. The strategy is currently unassigned and both vectors are disabled by YAML.

### As enablement-ready implementation

Not acceptable yet. The most important missing step is to align V1 runtime payload shape with the handler's expected data contract and then prove it with end-to-end tests.
