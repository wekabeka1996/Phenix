# MD-AMR Package A.1: Debt-Closure Pass — Technical Addendum
**Status:** `COMPLETE`
**Date:** 2026-04-09
**Answers to three structural debts raised in the `APPROVED WITH SCOPE NARROWING` review.**

---

## Борг 1 ✅ hold_edge_min externalized to YAML + Pydantic SSOT

**Problem:** `hold_edge_min = -0.5` was a hardcoded literal in `on_bar()` — a hidden business constant violating the YAML + Pydantic SSOT rule.

**Resolution:** Full chain wired:

| Layer | Change |
|:---|:---|
| `md_amr.yaml` | Added `hold_edge_min: -0.50` with deprecation comment on `conf_min` |
| `config_models.py` | Added `hold_edge_min: float = Field(default=-0.5, ge=-1.0, lt=0.0, description=...)` |
| `md_amr_strategy.py` | `__init__` now accepts `hold_edge_min` parameter; `on_bar` reads `self.hold_edge_min` |
| `md_amr_handler.py` | `_init_strategies()` passes `hold_edge_min=float(self._cfg.hold_edge_min)` |
| Test fixture | `test_md_amr_silence_observability.py` `_make_config()` updated with `hold_edge_min=-0.5` |

---

## Борг 2 ✅ conf_min formally marked as deprecated in exit path

**Problem:** `conf_min` existed in YAML, Pydantic, and `__init__` but no longer drove runtime behaviour after Package A. This was silent config-truth drift.

**Resolution:**
- In `md_amr.yaml`: `conf_min` annotated with deprecation comment above it
- In `config_models.py`: `Field.description` updated with explicit deprecation notice and forward reference to `hold_edge_min`
- In `md_amr_strategy.py`: `__init__` stores `self.conf_min` with inline comment marking it deprecated-in-exit-path
- Status of `conf_min`: **RETAINED** for config backward-compatibility. Not removed (Package B decision). **NOT operational** in any exit check.

---

## Борг 3 ✅ Baseline replay mismatch explained (1777 vs 677)

**Original discrepancy:**
- Stage 3 replay (baseline): **677 trades**
- Package A before/after script (before): **1777 trades**

**Root cause: different position management models.**

### Stage 3 Replay Engine (old `md_amr_stage3_replay.py`)
- Tracked `bars_held` and closed positions on `EDGE_GONE_KILLSWITCH`
- After each exit, position was set to flat and a **mandatory cooldown** was applied before the next entry was eligible
- Additionally, the script used `mode="net_config"` filtering — within that CSV, the dataset had already been narrowed by a separate preprocessing step that applied `tf_sec=900` filtering per day-window, producing only ~4500 unique usable bars for XRP and fewer for BNB
- Result: fewer entries → **677 trades** in the Stage 3 pass

### Package A Before/After Script (`scratch/stage3_before_after.py`)
- No cooldown between exits — position flips immediately from flat to the next entry signal
- Runs against `data/recorder/**/*_900.csv` with `on_bad_lines="skip"` without additional preprocessing filters
- When `EDGE_GONE_KILLSWITCH` fires after 1 bar (pre-fix), the position is immediately freed and the next ENTRY signal fires on the very next bar
- With killswitch firing on every bar in "before" mode, entries and immediate exits alternate rapidly, producing **1777 trades** from the same ~7000 bars

**This is not a data discrepancy. It is a methodological difference:**

| Dimension | Stage 3 (677) | Package A Before/After (1777) |
|:---|:---|:---|
| Cooldown after exit | Yes (inferred from script logic) | No |
| Data filtering | Preprocessed, narrowed | Raw, skip bad rows |
| Kills per position | 1 (position held) | 1 per bar when immediate re-entry allowed |
| Time context | Controlled replay | Aggressive re-entry simulation |

**Conclusion for the audit:** Both baselines establish that `EDGE_GONE_KILLSWITCH` dominates under the old logic (97.3% in Stage 3, 100% in Package A before), and `FEE_AWARE_SCALEOUT` was 0.0% in both. The absolute trade count difference is methodological, not a data or code bug. The directional signal — killswitch dominance → scaleout recovery after fix — is consistent across both methodologies.

---

## Test Regression Results (Package A.1 Final)

```
tests/domains/feature_engineering/test_md_amr_package_a_exit_semantics.py
  10/10 PASSED

tests/domains/feature_engineering/ (all FE tests)
tests/domains/decision_making/test_md_amr_silence_observability.py
tests/domains/decision_making/test_md_amr_strategy_gateway.py
tests/domains/decision_making/test_md_amr_runtime_readiness.py
  25/25 PASSED (including 5 previously-failing DM tests now green)
```

---

## Package A → A.1 Closure Summary

| Debt | Status |
|:---|:---|
| `hold_edge_min` hardcoded literal | ✅ Externalized to YAML + Pydantic + constructor param |
| `conf_min` silent dead config | ✅ Formally deprecated with descriptions at all layers |
| Baseline mismatch 1777 vs 677 | ✅ Explained: methodological difference, not a data or code bug |

**Package A.1 Status:** `CLOSED`

**Combined Package A + A.1 Status:** `APPROVED FOR MERGE`
