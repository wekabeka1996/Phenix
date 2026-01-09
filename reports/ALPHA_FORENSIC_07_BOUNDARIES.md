# TASK-ALPHA-FORENSIC-06: Tests & Stability

## Current State
*   **Missing Tests:** `tests/test_alpha_models.py` mentioned in docs DEOS NOT EXIST.
*   **Existing Tests:** `tests/test_ensemble.py` acts as the only coverage anchor, likely testing the aggregation logic but maybe mocking the models.
*   **Risk:** The individual logic of `Momentum`, `Volatility`, `MeanReversion` appears minimally tested (or tests were deleted).

## "Freeze" Plan (Minimum Verification)
To safely freeze this component, we need to enforce input-output determinism.

**Must-Have Test Cases:**
1.  **Warmup Resilience:** Pass empty features -> Expect empty list (no crash).
2.  **Deterministic Logic:** Pass fixed `features = {'rsi_14': 75.0, ...}` -> Expect `score > 0` (Momentum) or `score < 0` (Mean Reversion) strictly matches formula.
3.  **Bounds Checker:** Pass extreme features -> Expect `score` clamped at -1.0 / 1.0.
4.  **Ensemble Integration:** Register 3 models -> Call `calculate_all` -> Verify 3 results.

---

# TASK-ALPHA-ARCH-DECISION-07: Domain Boundaries

## Verdict: Sub-Domain of Decision Making using "Smart Component" pattern.

**Current Architecture:**
*   `DecisionMaking` "owns" the registry.
*   The execution happens synchronously within the `DecisionMaking.on_features` loop.
*   Data flow is strictly internal (except for the emitted event for observability).

**Decision:**
Do **NOT** promote to a standalone specific Domain (like RiskManagement).
Why?
1.  **Complexity:** It doesn't have its own lifecycle or persistence state (stateless calculation).
2.  **Coupling:** It requires the exact same identical feature set as DecisionMaking.
3.  **Latency:** Adding IPC overhead for signal generation is unnecessary for this scale.

**Migration Plan (Refactoring):**
1.  **Renaming:** Consider moving to `apps/reference/domains/decision_making/signals/` or `.../alpha/` to reflect ownership.
2.  **Wiring:** Use strict wiring in `DecisionMaking.__init__` (as is).
3.  **Contracts:** The `AlphaScore` is a good DTO pattern. Keep it.

**Conclusion:**
Treat `alpha_search` as the **"Signal Calculation Library"** for the Decision Engine. It is healthy, safe (fail-closed), and functionally relevant as an observability tool, even if currently "Shadow Mode".
