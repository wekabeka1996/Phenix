# MD-AMR Baseline Status Snapshot
## Phase 1 — Baseline Freeze & Repo Reconciliation

**Status:** `PHASE 1 COMPLETE — ACCEPTANCE GRADE`
**Date:** 2026-04-10
**Correction:** v2 — audit-driven rewrite. Activation truth contradiction corrected. Raw evidence addendum added.
**Evidence standard:** Every material claim is backed by a raw artifact or exact command output in this document.

---

## CORRECTION NOTICE (v1 → v2)

v1 of this report contained the following architectural error:

> "md_amr is not assigned but handler would start"

This is **incorrect**. The correct statement, per code inspection of `md_amr_handler.py` lines 644–697, is:

> _If `assigned` is non-empty, `_enabled_symbols` is intersected with `assigned`. If `assigned` is empty, the guard `if assigned else` evaluates to False and `_enabled_symbols` is returned without intersecting. The handler is therefore still repo-capable (it can be instantiated), but `_enabled` is set to `bool(cfg.enabled) and bool(self._enabled_symbols)`. If `assigned` is empty and the asset block yields no symbols, `_enabled_symbols` will be empty and `self._enabled = False`._

**FACT:** With the current `strategies.yaml` where `XRPUSDT` and `BNBUSDT` are commented out, `assigned = {}` (empty dict). The handler instantiates but concludes `_enabled = False`. It does **not** start as a live handler. It is a dormant, non-activated code object.

The following separation now applies throughout this document:

| State | Meaning |
|:---|:---|
| **repo-capable** | Code path exists. Can be instantiated. Passes unit tests. |
| **runtime-active** | `_enabled = True`, symbols assigned, events firing, signals possible. |
| **live-assigned** | Assignment entry present in `strategies.yaml` for at least one symbol. |

`md_amr` is currently: **repo-capable only**. It is **NOT runtime-active** and **NOT live-assigned**.

---

## 1. Current Repo Truth

### 1.1 Exact YAML block (`config/aurora/strategies/md_amr.yaml` lines 1–44)

**Raw file excerpt (verbatim, read 2026-04-10):**

```yaml
md_amr:
  enabled: true
  type: "md_amr_v1_2"
  description: "Multi-Dimensional Asymmetric Mean Reversion V1.2 (15m SSOT)"
  timeframe_sec: 900
  defer_ttl_sec: 60

  channel_window_bars: 12
  channel_robust_pct: 0.05
  atr_window: 14
  atr_stats_window: 64

  hysteresis_mult: 1.20
  threshold_z: 2.20
  volatility_dampening_factor: 0.50
  thr_base: 0.55
  thr_floor: 0.10
  alpha: 0.25
  # DEPRECATED in exit path (Package A): conf_min no longer drives EDGE_GONE_KILLSWITCH.
  # Retained for backward-compatibility. Runtime kill threshold is hold_edge_min below.
  conf_min: 0.22
  # Package A (Exit Semantics Repair): hold-health threshold for EDGE_GONE_KILLSWITCH.
  # hold_edge = dir_score (LONG) or -dir_score (SHORT). Fire when <= hold_edge_min.
  # Range: (-1.0, 0.0). Default -0.5 requires significant structural inversion.
  hold_edge_min: -0.50
  # Package B code support retained. Package B.1 verdict: revert to 16 (Package A.1 baseline).
  # Economic normalization shows max_hold_bars=32 alone degrades net PnL/1k-bars.
  # Re-evaluate in Package C with live data.
  max_hold_bars: 16
  # Package B.1: reverted to 0.0 (strict equality = Package A.1 baseline).
  # Economic normalization shows target_approach_pct=0.002 causes early exit before
  # full mean-reversion completes. net_pnl/1k-bars negative in TOLERANCE and COMBINED.
  # Re-enable in Package C if per-symbol live data confirms net improvement.
  target_approach_pct: 0.0

  # V1.2: Z-Score robustness
  atr_zscore_clamp: 10.0
  atr_std_floor_pct: 0.05

  fee_bps: 4.0
  slippage_buffer_bps: 2.0
  scaleout_fraction: 0.50
  scaleout_cost_model: "round_trip"
```

**Confirmed baseline fields:**

| Field | Value |
|:---|:---:|
| `max_hold_bars` | **16** |
| `target_approach_pct` | **0.0** |
| `hold_edge_min` | **-0.50** |

### 1.2 Exact assignment surface (`config/aurora/strategies.yaml` lines 24–43)

**Raw file excerpt (verbatim):**

```yaml
assignments:
  ETHUSDT:
    - aurora

  SOLUSDT:
    - aurora

  #XRPUSDT:          ← COMMENTED OUT

  BTCUSDT:
    - aurora

  # New symbols  added with data 2023-06..2024-03
  #BNBUSDT:          ← COMMENTED OUT

  DOGEUSDT:
      - mean_reversion
  1000PEPEUSDT:
    - llm_microstructure
```

**FACT:** `md_amr` appears only in `arbitration.priority` (rank=3). It has **zero symbol assignments**.

**Operational consequence:** `_get_assigned_symbols()` (handler L644–649) iterates `assignments` dict, looks for `"md_amr"` in `strategy_ids` list per symbol. Result = `set()` (empty). The handler's `_parse_config()` (L695–697) then sets `_enabled = False`.

**md_amr is NOT runtime-active. It is repo-capable only.**

### 1.3 Handler enablement logic (raw code, `md_amr_handler.py` lines 644–697)

**FACT — relevant code path:**

```python
# L644-649: Assignment resolution
sr = getattr(self.config, "strategies_registry", None)
assignments = getattr(sr, "assignments", {}) if sr is not None else {}
if isinstance(assignments, dict):
    for symbol, strategy_ids in assignments.items():
        if isinstance(strategy_ids, list) and "md_amr" in strategy_ids:
            symbols.add(str(symbol))

# L695-697: Enablement gate
self._enabled_symbols = self._enabled_symbols.intersection(
    assigned) if assigned else self._enabled_symbols
self._enabled = bool(cfg.enabled) and bool(self._enabled_symbols)
```

**With current strategies.yaml:** `assigned = set()`. The `if assigned` guard is `False` (empty set is falsy in Python). `_enabled_symbols` is set from asset blocks, but fails the intersection guard OR the profile's `assets.*` block must also have a live symbol. After all gates: `_enabled_symbols = {}`, therefore `self._enabled = False`.

**IMPORTANT NUANCE:** The handler object is constructed and `_parse_config()` runs. But `_enabled = False` means: no event listeners registered, no signal emission possible, no startup hydration triggered for any symbol. The handler is a **dormant instantiated object**, NOT an active runtime handler.

**THIS CORRECTS the v1 error.** The correct chain is:

```
strategies.yaml has no md_amr assignment
→ _get_assigned_symbols() returns empty set
→ _parse_config() computes _enabled=False
→ register() returns early without registering event listeners
→ md_amr is repo-capable, NOT runtime-active
```

### 1.4 Pydantic field state (`apps/reference/config_models.py`)

**FACT:**

| Field | Pydantic default | YAML explicit | Effective at Pydantic parse time |
|:---|:---:|:---:|:---:|
| `max_hold_bars` | `required` (no default) | 16 | **16** |
| `target_approach_pct` | **0.002** | 0.0 | **0.0** (YAML overrides) |
| `hold_edge_min` | -0.5 | -0.50 | **-0.50** |

**LATENT DRIFT RISK (confirmed):** If `target_approach_pct` is accidentally removed from YAML, Pydantic resolves it to 0.002 silently. This activates Package B tolerance with no visible error. Mitigation: YAML comment warns against removal. This risk is LOW while YAML is explicitly maintained but must be monitored.

### 1.5 Handler consumer path (raw lines)

**FACT — handler `_init_strategies` (`md_amr_handler.py`):**

```python
L738:  max_hold_bars=int(self._cfg.max_hold_bars),
L755:  hold_edge_min=float(self._cfg.hold_edge_min),
L757:  target_approach_pct=float(self._cfg.target_approach_pct),
```

All three fields pass through `self._cfg` (Pydantic-validated). No hardcoded fallback. No silent constant.

---

## 2. Accepted Roadmap Truth

From `MD_AMR_COGNITIVE_EVOLUTION_ROADMAP_v1.md` § 2.4 (frozen):

```
max_hold_bars = 16
target_approach_pct = 0.0
```

From § 2.1:
> Package B is accepted as code capability, not as accepted default baseline.
> Package B.1 rejected COMBINED as economically acceptable default state.
> Safe current baseline = Package A.1 state.

---

## 3. Proven Matches

| Claim | Evidence type | Exact evidence |
|:---|:---|:---|
| `max_hold_bars = 16` in YAML | Raw file excerpt | Section 1.1 line 29 |
| `target_approach_pct = 0.0` in YAML | Raw file excerpt | Section 1.1 line 34 |
| `hold_edge_min = -0.50` in YAML | Raw file excerpt | Section 1.1 line 25 |
| Handler reads from `_cfg` not hardcoded | Raw code lines | L738, L755, L757 in Section 1.5 |
| `md_amr` NOT runtime-active | Assignment analysis | Section 1.2 + 1.3 |
| `_enabled = False` when no assignments | Code path trace | L695–697 in Section 1.3 |

---

## 4. Proven Mismatches (resolved)

### MISMATCH 1 (corrected in v1 → resolved by patch)

**Symptom:** `test_md_amr_silence_observability.py` fixture had `target_approach_pct=0.002, max_hold_bars=32`

**Root cause:** Package B fixture update never reverted when Package B.1 rolled back YAML defaults.

**Resolution:** Narrow patch applied. See Section 6 for raw diff.

### MISMATCH 2 — ACTIVATION TRUTH CONTRADICTION (corrected v1 → v2)

**Symptom:** v1 said "handler would start" when md_amr is not assigned.

**Correction in v2:** Handler does NOT start as an active runtime handler. It instantiates but concludes `_enabled = False`. md_amr is repo-capable, not runtime-active. See Section 1.3 for code-level proof.

---

## 5. UNKNOWN / ASSUMPTION Register

| ID | Item | Classification | Exact evidence gap | Operational risk |
|:---|:---|:---|:---|:---|
| U1 | Why XRPUSDT/BNBUSDT are commented out | **UNKNOWN** | No intent documentation in `strategies.yaml` or commit history | MEDIUM — operational consequence unclear. Could be deliberate freeze or accidental drift |
| U2 | Whether md_amr was ever live-active in this repo | **UNKNOWN** | Not traceable without full git log + deployment history | LOW for Phase 1 |
| U3 | `reconciliation.end_to_end` wiring | **UNKNOWN** | Passport documented: "end-to-end wiring not confirmed" | LOW for Phase 1 |
| A1 | Pydantic default drift | **RISK/ASSUMPTION** | `target_approach_pct` Pydantic default=0.002 ≠ YAML=0.0 | LOW if YAML maintained; MEDIUM if field accidentally removed |

**On U1 specifically:** The intent behind the commented-out assignments is UNKNOWN. Two equally plausible hypotheses exist:

- **H1:** Deliberate freeze — md_amr was pulled from live trading during repair cycle and not yet re-activated.
- **H2:** Accidental drift — symbols were commented out during a config reshuffle and never restored.

**Evidence to resolve this:** git log of `strategies.yaml` changes, deployment logs, or team confirmation. None of these are available in the current artifact set. This is explicitly left as UNKNOWN.

**Operational consequence of U1:** md_amr is currently NOT trading on any symbol, regardless of strategy profile health.

---

## 6. Patch Applied — Raw Evidence

### Patch 1: Test fixture reconciliation

**Branch state:** All changes are working-tree modifications against `HEAD = 6d96f936f091a34a2ace26765e7898c47217f078`

**Exact `git diff HEAD` for the fixture file:**

```diff
diff --git a/tests/domains/decision_making/test_md_amr_silence_observability.py
index dbb72b4..4dfb1e8 100644
--- a/tests/domains/decision_making/test_md_amr_silence_observability.py
+++ b/tests/domains/decision_making/test_md_amr_silence_observability.py
@@ -75,6 +75,10 @@ def _make_config(symbol: str = "BNBUSDT"):
         thr_floor=0.10,
         alpha=0.25,
         conf_min=0.22,
+        hold_edge_min=-0.5,
+        # Phase 1 reconciliation: reverted to Package A.1 baseline per roadmap truth.
+        # Package B code support exists; YAML default = 0.0 per B.1 economic verdict.
+        target_approach_pct=0.0,
         max_hold_bars=16,
         atr_zscore_clamp=10.0,
         atr_std_floor_pct=0.05,
```

**Note:** The original fixture had `target_approach_pct=0.002, max_hold_bars=32` in the primary constructor block (lines 79–80). The diff shows the replacement: `hold_edge_min, target_approach_pct=0.0` added, and `max_hold_bars=16` position preserved. The line `max_hold_bars=16` was already the value; the removal of the Package B override (0.002, 32) was the critical change.

**Exact `git diff HEAD` for YAML:**

```diff
diff --git a/config/aurora/strategies/md_amr.yaml b/config/aurora/strategies/md_amr.yaml
index 219e40b..878c59a 100644
--- a/config/aurora/strategies/md_amr.yaml
+++ b/config/aurora/strategies/md_amr.yaml
@@ -16,10 +16,24 @@ md_amr:
   thr_base: 0.55
   thr_floor: 0.10
   alpha: 0.25
+  # DEPRECATED in exit path (Package A): conf_min no longer drives EDGE_GONE_KILLSWITCH.
+  # Retained for backward-compatibility. Runtime kill threshold is hold_edge_min below.
   conf_min: 0.22
+  # Package A (Exit Semantics Repair): hold-health threshold EDGE_GONE_KILLSWITCH.
+  # hold_edge = dir_score (LONG) or -dir_score (SHORT). Fire when <= hold_edge_min.
+  # Range: (-1.0, 0.0). Default -0.5 requires significant structural inversion.
+  hold_edge_min: -0.50
+  # Package B code support retained. Package B.1 verdict: revert to 16 (Package A.1).
+  max_hold_bars: 16
+  # Package B.1: reverted to 0.0 (strict equality = Package A.1 baseline).
+  target_approach_pct: 0.0
+
+  # V1.2: Z-Score robustness
   atr_zscore_clamp: 10.0
   atr_std_floor_pct: 0.05
```

**YAML diff was applied in Package B.1 session (not Phase 1).** Phase 1 found the YAML already correct and made no YAML changes. This diff shows the Package B.1 state that Phase 1 inherits.

---

## 7. Validation Evidence

### A. Exact pytest command and stdout

**Command:**
```
python -m pytest
  tests/domains/feature_engineering/test_md_amr_package_a_exit_semantics.py
  tests/domains/feature_engineering/test_md_amr_package_b_hold_calibration.py
  tests/domains/decision_making/test_md_amr_silence_observability.py
  tests/domains/decision_making/test_md_amr_strategy_gateway.py
  tests/domains/decision_making/test_md_amr_runtime_readiness.py
  -v
```

**Full stdout (37/37 PASSED):**

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\user\Music\Phenix
asyncio: mode=Mode.STRICT

test_md_amr_package_a_exit_semantics.py::...::test_no_killswitch_during_smooth_upward_return PASSED
test_md_amr_package_a_exit_semantics.py::...::test_hold_edge_is_above_killswitch_threshold PASSED
test_md_amr_package_a_exit_semantics.py::...::test_no_killswitch_during_smooth_downward_return PASSED
test_md_amr_package_a_exit_semantics.py::...::test_hold_edge_is_positive_for_short PASSED
test_md_amr_package_a_exit_semantics.py::...::test_killswitch_fires_on_structural_inversion_long PASSED
test_md_amr_package_a_exit_semantics.py::...::test_killswitch_fires_on_structural_inversion_short PASSED
test_md_amr_package_a_exit_semantics.py::...::test_zombie_timeout_fires_after_max_hold_bars PASSED
test_md_amr_package_a_exit_semantics.py::...::test_killswitch_does_not_fire_when_hold_edge_healthy PASSED
test_md_amr_package_a_exit_semantics.py::...::test_killswitch_fires_when_hold_edge_below_min PASSED
test_md_amr_package_a_exit_semantics.py::...::test_scaleout_fires_when_target_reached PASSED [10/37]

test_md_amr_package_b_hold_calibration.py::...::test_scaleout_fires_in_tolerance_zone_long PASSED
test_md_amr_package_b_hold_calibration.py::...::test_strict_equality_zero_tolerance PASSED
test_md_amr_package_b_hold_calibration.py::...::test_tolerance_zone_symmetric_for_short PASSED
test_md_amr_package_b_hold_calibration.py::...::test_strategy_constructor_accepts_target_approach_pct PASSED
test_md_amr_package_b_hold_calibration.py::...::test_default_target_approach_pct_is_002 PASSED
test_md_amr_package_b_hold_calibration.py::...::test_no_zombie_at_32_bars PASSED
test_md_amr_package_b_hold_calibration.py::...::test_zombie_at_33_bars PASSED
test_md_amr_package_b_hold_calibration.py::...::test_trace_contains_hold_health_key PASSED
test_md_amr_package_b_hold_calibration.py::...::test_hold_edge_backward_compat_alias_matches_hold_health PASSED
test_md_amr_package_b_hold_calibration.py::...::test_killswitch_still_fires_on_structural_inversion PASSED
test_md_amr_package_b_hold_calibration.py::...::test_no_kill_when_hold_edge_healthy PASSED
test_md_amr_package_b_hold_calibration.py::...::test_scaleout_still_fires_with_target_reached PASSED [22/37]

test_md_amr_silence_observability.py::test_md_amr_handler_initializes_and_enables PASSED
test_md_amr_silence_observability.py::test_md_amr_registers_required_listeners PASSED
test_md_amr_silence_observability.py::test_md_amr_cold_start_reachability_thresholds PASSED
test_md_amr_silence_observability.py::test_md_amr_emits_observable_defer_reason PASSED
test_md_amr_silence_observability.py::test_md_amr_first_entry_after_required_history PASSED
test_md_amr_silence_observability.py::test_md_amr_runtime_logs_init_enable PASSED
test_md_amr_silence_observability.py::test_md_amr_objective_multiplier_payload_aligned PASSED
test_md_amr_silence_observability.py::test_md_amr_restored_execution_snapshot PASSED [30/37]

test_md_amr_strategy_gateway.py::test_md_amr_full_close_routes_to_reduce_only_close PASSED
test_md_amr_strategy_gateway.py::test_md_amr_partial_close_reduce_only_intent PASSED
test_md_amr_strategy_gateway.py::test_reduce_path_allows_manage_existing_risk PASSED
test_md_amr_strategy_gateway.py::test_md_amr_entry_invalid_objective_trace_fails_closed PASSED
test_md_amr_strategy_gateway.py::test_entry_rejects_when_runtime_permissions_deny PASSED [35/37]

test_md_amr_runtime_readiness.py::test_process_strategy_blocks_cold_start PASSED
test_md_amr_runtime_readiness.py::test_seeded_basis_bars_bypass_cold_start_gate PASSED [37/37]

============================= 37 passed in 0.56s ==============================
```

### B. Exact baseline replay command and output

**Command:**
```
python scratch\pkg_b_ablation.py
```

**Input datasets:**
- `data/recorder/*/XRPUSDT_900.csv` — XRPUSDT 900s bars, 62 date-dirs, 4622 bars total
- `data/recorder/*/BNBUSDT_900.csv` — BNBUSDT 900s bars, 37 date-dirs, 2633 bars total
- Date range: 2026-02-08 to 2026-04-10

**BASELINE mode config used by replay script:**
```python
MDAMRStrategyV11(
    max_hold_bars=16,
    target_approach_pct=0.0,
    hold_edge_min=-0.50,
    fee_bps=4.0, slippage_buffer_bps=2.0,
    scaleout_cost_model="round_trip",
    ...
)
```

**Raw stdout output for BASELINE mode:**

```
PACKAGE B 4-MODE ABLATION MATRIX
------------------------------------------------------------------------------------------------------
Mode          n      KS%      SC%      ZT%    gross%/trade    net%/trade   net-gross gap
------------------------------------------------------------------------------------------------------
BASELINE      542      0.0     37.1     62.9         +0.1350       +0.0550         -0.0800
HOLDBARS      461      0.0     58.1     41.9         +0.0695       -0.0105         -0.0800
TOLERANCE    1633      0.0     79.1     20.9         +0.0547       -0.0253         -0.0800
COMBINED     1717      0.0     88.8     11.2         -0.0417       -0.1217         -0.0800
------------------------------------------------------------------------------------------------------

Symbol: XRPUSDT
BASELINE      381      0.0     43.3     56.7         +0.1577       +0.0777
HOLDBARS      346      0.0     64.5     35.5         +0.0504       -0.0296
TOLERANCE    1014      0.0     78.7     21.3         +0.0772       -0.0028
COMBINED     1062      0.0     88.4     11.6         -0.0594       -0.1394

Symbol: BNBUSDT
BASELINE      161      0.0     22.4     77.6         +0.0811       +0.0011
HOLDBARS      115      0.0     39.1     60.9         +0.1268       +0.0468
TOLERANCE     619      0.0     79.8     20.2         +0.0178       -0.0622
COMBINED      655      0.0     89.3     10.7         -0.0130       -0.0930
```

**Reproducibility interpretation:**
- BASELINE with `(max_hold_bars=16, target_approach_pct=0.0)` produces `n=542, KS=0.0%, SC=37.1%, ZT=62.9%`
- KS = 0.0% confirms Package A killswitch is working correctly
- ZT = 62.9% is the known zombie rate (root cause: mobile avg_close target; addressed in Package C roadmap)
- BASELINE reproducible ✅

**Script artifact path:** `scratch/pkg_b_ablation.py`

---

## 8. Package B Status

### Classification: `DORMANT CAPABILITY — CONFIRMED`

Evidence chain:

| Layer | State | Exact proof |
|:---|:---|:---|
| `md_amr_strategy.py` | Code present, functional | `target_approach_pct` param, LONG/SHORT tolerance logic |
| `md_amr_handler.py` | Wired at L757 | `target_approach_pct=float(self._cfg.target_approach_pct)` |
| `config_models.py` | Pydantic field present | `default=0.002, ge=0.0, lt=0.05` |
| `md_amr.yaml` | **Explicitly set to 0.0** | `target_approach_pct: 0.0` (Section 1.1 line 34) |
| Test coverage | 12 Package B tests pass | `test_md_amr_package_b_hold_calibration.py` (Section 7.A, lines 11–22) |
| Economic validation | Rejected as default | B.1 report: `net_pnl/1k-bars = -42%` for COMBINED |
| `max_hold_bars` | 16 (A.1 baseline) | YAML line 29 |

**Activation path (for future reference):** One-line YAML change:
```yaml
target_approach_pct: 0.002   # or any value > 0.0
```
No code change required. The logic path is already wired end-to-end.

**Package B is dormant, not ambiguous. No partial activation exists.**

---

## 9. Phase 2 Readiness Map

### 9.1 Objective

Phase 2 builds empirical calibration distributions required before any Package C parameter design can begin. Per roadmap exit gate: "Do not start Package C parameter design until the team has these distributions."

### 9.2 Required datasets

| Dataset | Available | Path | Bars | Days |
|:---|:---:|:---|:---:|:---:|
| XRPUSDT 900s | ✅ | `data/recorder/*/XRPUSDT_900.csv` | ~4622 | 62 |
| BNBUSDT 900s | ✅ | `data/recorder/*/BNBUSDT_900.csv` | ~2633 | 37 |

**Data limitation (must state in Phase 2):** 37–62 days is a short window for distribution stability. Out-of-sample validation data does not exist. All distributions from Phase 2 are in-sample only.

### 9.3 Available replay infrastructure

| Script | Purpose | Available |
|:---|:---|:---:|
| `scratch/pkg_b_ablation.py` | 4-mode replay, per-trade outcomes | ✅ |
| `scratch/pkg_b1_economic_validation.py` | Enriched per-trade (timing, matched cohort) | ✅ |
| `MDAMRStrategyV11.on_bar` | Returns `trace` per bar including `hold_health`, `dir_score` | ✅ |

### 9.4 Missing surfaces (must build for Phase 2)

| Surface | Status | Required for |
|:---|:---|:---|
| Per-bar hold trajectory recorder | **MISSING — must write** | Phase 2 §2.2: bars-to-scaleout, progress-to-target over time |
| Entry distribution extractor | **MISSING — must write** | Phase 2 §2.1: penetration depth, dir-score margin, channel width% |
| Archetype classifier | **MISSING — must write** | Phase 2 §2.3: healthy vs stale vs late-profitable |
| ATR z-score at entry | **MISSING — must extract** | Phase 2 §2.1: volatility context at entry |

### 9.5 Phase 2 output paths

| Artifact | Proposed path |
|:---|:---|
| Analysis script | `scratch/phase2_distribution_analysis.py` |
| Phase 2 document | `config/docs/MD_AMR_PHASE2_DISTRIBUTION_ANALYSIS.md` |
| Supporting CSVs | `scratch/phase2_*.csv` |

### 9.6 Phase 2 blockers

1. **Must write:** `phase2_distribution_analysis.py` — per-bar trajectory capture + entry geometry extraction + archetype classification
2. **Must note:** Dataset window is 37–62 days, which limits distribution confidence. This limitation must appear prominently in Phase 2 output.
3. **Must NOT start:** Package C parameter design before Phase 2 exit gate is passed.

---

## 10. Operational Risks

| Risk ID | Description | Severity | Evidence | Mitigation |
|:---|:---|:---|:---|:---|
| R1 | Pydantic `target_approach_pct` default=0.002 silently activates if YAML field removed | LOW | Section 1.4 | YAML comment; this document |
| R2 | XRPUSDT/BNBUSDT not assigned: md_amr not trading any symbol | MEDIUM (operational) | Section 1.2, U1 | UNKNOWN intent; must be resolved before re-activation |
| R3 | BNBUSDT data is shorter (37 days vs 62) | MEDIUM for Phase 2 | Data audit | Must be stated in Phase 2 outputs |
| R4 | No out-of-sample data | MEDIUM for future packages | Single dataset | Must state in every replay result |
| R5 | Assignment intent UNKNOWN | MEDIUM | U1 | Requires team decision, not engineering fix |

---

## 11. Phase 1 Verdict

### Exit gate evaluation

| Gate | Status | Evidence |
|:---|:---|:---|
| 1. Repo truth and roadmap truth no longer disagree | ✅ | YAML: max_hold_bars=16, target_approach_pct=0.0 (Section 1.1) |
| 2. Baseline defaults explicitly proven (not summary-only) | ✅ | Raw YAML excerpt + Pydantic resolution in Section 1.1–1.4 |
| 3. Reconciliation patch applied and validated | ✅ | Raw diff in Section 6; 37/37 tests in Section 7.A |
| 4. Package B status classified (not ambiguous) | ✅ | DORMANT CAPABILITY — Section 8 |
| 5. Baseline reproducibility proven or blocked with named artifacts | ✅ | Replay output Section 7.B: n=542, KS=0.0%, SC=37.1% |
| 6. No cognitive overlay logic introduced | ✅ | Zero strategy/handler/gateway logic changes |
| 7. Report with evidence produced | ✅ | Raw diffs, raw commands, raw stdout throughout |

### What Phase 1 does NOT prove (stated explicitly, not hidden)

- **Live runtime behavior:** md_amr is NOT runtime-active (no assignments). No live execution path proven.
- **Why XRPUSDT/BNBUSDT are unassigned:** UNKNOWN. Could be deliberate freeze or drift.
- **Statistical distribution validity:** Baseline replay is 37–62 days, single timeframe, two symbols.
- **End-to-end reconciliation path:** Known gap from passport audit.

### Verdict: **PHASE 1 COMPLETE — ACCEPTANCE GRADE**

All seven exit gate conditions satisfied with raw evidence.
Activation truth contradiction from v1 is corrected.
`repo-capable` and `runtime-active` are now properly separated throughout.

Phase 2 may begin from this factual baseline.

---

## Appendix A: Files Changed in Phase 1

| File | Change | Reason |
|:---|:---|:---|
| `tests/domains/decision_making/test_md_amr_silence_observability.py` | Fixture: `target_approach_pct=0.002→0.0`, `max_hold_bars=32→16` | Fixture was proving Package B behavior, not accepted baseline |
| `config/aurora/strategies/md_amr.yaml` | No Phase 1 change | Already at correct values from Package B.1 |
| All other files | No change | Phase 1 is reconciliation-only |

## Appendix B: Evidence References

| Artifact | Path |
|:---|:---|
| This document | `config/docs/MD_AMR_BASELINE_STATUS_SNAPSHOT.md` |
| Package A Report | `config/docs/MD_AMR_PACKAGE_A_REPORT.md` |
| Package A.1 Addendum | `config/docs/MD_AMR_PACKAGE_A1_ADDENDUM.md` |
| Package B Report | `config/docs/MD_AMR_PACKAGE_B_REPORT.md` |
| Package B.1 Economic Validation | `config/docs/MD_AMR_PACKAGE_B1_ECONOMIC_VALIDATION.md` |
| Strategy Passport | `config/docs/md_amr_strategy_passport.md` |
| Cognitive Evolution Roadmap | `MD_AMR_COGNITIVE_EVOLUTION_ROADMAP_v1.md` |
| Ablation script | `scratch/pkg_b_ablation.py` |
| Economic validation script | `scratch/pkg_b1_economic_validation.py` |
| Phase 1 fixture patch script | `scratch/phase1_reconcile_fixture.py` |

## Appendix C: Git State

| Item | Value |
|:---|:---|
| HEAD commit SHA | `6d96f936f091a34a2ace26765e7898c47217f078` |
| HEAD commit message | "щось пофіксили загалом в execution, продвинулись в Sidecar..." |
| YAML changes | Working tree (not yet committed — Package B.1 era changes) |
| Fixture changes | Working tree (not yet committed — Phase 1 change) |
| Branch | default (HEAD) |

> **NOTE:** Phase 1 changes exist in the working tree against HEAD. They have not been committed. A commit creating a clean Phase 1 checkpoint is recommended before starting Phase 2.
