# AUDIT REPORT: Signal Normalization Mode Config-to-Runtime Mismatch

## A) Executive Summary
- **Verdict**: **CONFIRMED (CODE BUG).** There is a definitive mismatch between the strategy config and the `AuroraScoringKernel` execution.
- **Root Cause**: While `aurora.yaml` correctly specifies `normalize_signals_mode: signed_v2`, the `AuroraScoringKernel.compute` method was hardcoded to use `normalize_mode="net_zero"`. Because `"net_zero"` is not an expected transformation in `scoring_direction_strength_v1.py`, it falls back to a passthrough (equivalent to `"off"`).
- **Severity**: **HIGH** for Linear/v2 scoring. This disables normalization (stretching and clamping), halving the intended weight of `[0, 1]` bounded features (like `macro_sync` or `ema_bias` if neutral is 0.5) and leaving `0.0` neutral features completely unbounded.
- **Phase 9 Caveat**: In the current production/config state (`scoring_version: "quadratic"`), the system routes to `QuadraticScoringKernel`, which bypasses `compute_direction_strength_score` entirely by using `pillar_sum` calculated upstream. The bug only critically corrupted behavior when `scoring_version` was `v1`/`v2` or when quadratic scoring triggered the linear kernel as a fallback.
- **Remediation**: The repository HEAD currently has an unstaged fix that removes the hardcode and passes `normalize_signals_mode` from the config loader into both `AuroraScoringKernel` and `QuadraticScoringKernel`. This fix is correct and must be committed.

## B) Evidence Trace (Config → Runtime)
1. **YAML Configuration**:
   - File: `config/aurora/strategies/aurora.yaml` (Lines ~76-77)
   - Value: `aurora.decision.signals.normalize_signals_mode: signed_v2`
2. **Pydantic Model Parsing**:
   - File: `apps/reference/config_models.py` (Line 221)
   - The config is parsed into `SignalsConfig` where `normalize_signals_mode` is defined as `Literal["off", "legacy_v1", "signed_v2"]`.
3. **Config Loading**:
   - File: `apps/reference/domains/decision_making/aurora_config_loader.py` (Line 165)
   - Loaded into memory as: `self.normalize_signals_mode = str(getattr(signals, "normalize_signals_mode", "signed_v2"))`
4. **Call Chain & The Break (Before Unstaged Fix)**:
   - `apps/reference/domains/decision_making/aurora_decision.py`: The `compute()` method of the selected kernel was called, but `normalize_mode` **was not passed in the kwargs**.
   - `apps/reference/domains/decision_making/aurora_scoring_kernel.py`: Because it was not passed, the `compute` method executed its internal logic:
     ```python
     # Line 183 in older commits
     normalize_mode="net_zero",
     ```
   - `apps/reference/domains/decision_making/scoring_direction_strength_v1.py` (Line 144):
     ```python
     if normalize_mode == "signed_v2":
         features_eval = _apply_signed_v2_transforms(...)
     else:
         features_eval = features
     ```
   - `"net_zero"` caused the logic to fall into the `else` block, completely bypassing `_apply_signed_v2_transforms`.

## C) Mismatch Proof/Disproof
The mismatch is **proven**. 
**Decision Point**: The hardcoded `"net_zero"` existed within `AuroraScoringKernel.compute` parameter passing into `compute_direction_strength_score`. It was not an override by `trading_mode`, nor a fallback for a missing config; it was an explicit hardcoded string that bypassed the configuration completely.

**Minimal Reproduction Snippet**:
```python
# Even if config holds "signed_v2", the scoring call does this:
cfg_mode = "signed_v2" # Ignored

# In AuroraScoringKernel.compute:
ds_score = compute_direction_strength_score(
    features=v2_features,
    weights=signal_weights,
    neutrals=feature_neutrals,
    normalize_mode="net_zero", # <--- FATAL OVERRIDE
    ...
)
```

## D) Blast Radius
Since `_apply_signed_v2_transforms` was bypassed, features were evaluated in their raw forms:
1. **[0, 1] Features (neutral=0.5)**: The transform `2*x - 0.5` ensures that when `neutral` (0.5) is subtracted downstream, the span is `[-1, 1]`. Without the transform, the feature remains in `[0, 1]`. Downstream subtraction of `0.5` means the effective signal range becomes `[-0.5, 0.5]`. 
   - *Impact*: Their weight contribution is exactly **halved**.
2. **Signed Features (neutral=0.0)**: The transform strictly clamps values to `[-1, 1]`. Without it, a rogue raw feature could pass `5.0` or `-10.0` into the directional score.
   - *Impact*: Unbounded features will completely drown out all other weighted signals, dominating the score and bypassing intended max exposure limits.
3. **Mis-Calibrated Config Knobs**:
   - `signal_threshold` and `neutral_threshold` are optimized against the `[-1, 1]` expected scale. Since half the features were compressed to `[-0.5, 0.5]`, the actual scores were likely significantly lower than expected, resulting in far fewer entries (false negatives).
4. **Environment**: This mismatch affects live, testnet, and backtests identically whenever `scoring_version` is `"v1"` or `"v2"`.

## E) WAL Forensic Plan + Findings
*(Directory `ops/wal` was not present on disk, so a live extraction could not be executed. Below is the exact procedure to confirm historical impact)*

**Forensic Procedure**:
1. Filter WAL events for `stage="STRATEGY"` or `EVT:STRATEGY_SIGNAL_PRODUCED`.
2. Select a single symbol (e.g., `BTCUSDT`) and pull 10 decisions containing the `features` dictionary in the payload.
3. Run an offline script calculating the score twice:
   - **Score A (Historical):** `compute_direction_strength_score(normalize_mode="net_zero")`
   - **Score B (Corrected):** `compute_direction_strength_score(normalize_mode="signed_v2")`
4. Compare `Score A` to the `score` logged in the WAL to prove `net_zero` was the active behavior.
5. Tabulate the difference to find decisions that would have flipped the FSM state.

**Example Expected Output**:
| decision_id/time | WAL_action | score_net_zero | score_signed_v2 | delta | would_flip?(y/n) |
|------------------|------------|----------------|-----------------|-------|------------------|
| 1700000000000    | NEUTRAL    | 0.003          | 0.008           | +0.005| Y (Exceeds Thr)  |

## F) Verdict + Next Actions
- **Was there a real bug?**: Yes.
- **Is it config mismatch, code bug, or both?**: Code bug (hardcoded variable ignoring config).
- **Severity**: **HIGH**. It compromises the mathematical integrity of the linear scoring model.

**Recommended Fix (Commit the Unstaged Changes)**:
1. `apps/reference/domains/decision_making/aurora_decision.py`: Pass `normalize_mode=self.normalize_signals_mode` to `self.scoring_kernel_cls.compute`.
2. `apps/reference/domains/decision_making/aurora_scoring_kernel.py`: Accept `normalize_mode: str = "signed_v2"` in `compute()` and pass it to `compute_direction_strength_score`.
3. `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`: Add `normalize_mode: str = "signed_v2"` to `compute()` signature to maintain duck-typing compatibility with `aurora_decision.py`, even if it does not strictly apply to `pillar_sum`.

**Validation Plan**:
- Run a minimal `v2` scoring backtest before and after committing the changes.
- Assert that `EVT:STRATEGY_SIGNAL_PRODUCED` payloads now show `score` values with properly expanded magnitudes.

## G) Update JOURNAL.md / TODO.md Instructions
**Update `JOURNAL.md`**:
- "Discovered and patched a critical bug in `AuroraScoringKernel` where `normalize_mode` was hardcoded to `"net_zero"`, effectively disabling the `signed_v2` normalization logic and causing features to bypass centering/clamping. Unstaged fix restores intended config mapping."

**Update `TODO.md`**:
- [ ] Commit the unstaged fixes in `aurora_decision.py` and `aurora_scoring_kernel.py`.
- [ ] Re-run phase parameter optimization for any model relying on `v2` linear scoring, as previous Optuna runs were fitted against non-normalized (compressed) feature space.
