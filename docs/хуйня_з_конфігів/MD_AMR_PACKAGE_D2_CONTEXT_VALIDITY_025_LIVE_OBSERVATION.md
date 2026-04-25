# MD_AMR Package D.2 — Context Validity 0.25 Live Advisory Observation

**Date**: 2026-04-16
**Package**: D.2 (Observation-only — no code changes, no promotion)
**Frozen Baseline**: Package A.1 (`max_hold_bars=16`, `target_approach_pct=0.0`)
**Prior Governance**: C.1–C.4 = `ACCEPTED_ADVISORY_ONLY`, `NO PROMOTION YET`
**Prior Evidence**: D.1 identified CV 0.25 as the single candidate qualifying for further study

---

## 1. Observation Window

| Attribute | Value |
|-----------|-------|
| Log range analyzed | 2026-04-15 14:15 UTC — 2026-04-16 18:45 UTC (~28.5 hours) |
| Aurora core log files scanned | 29 (aurora_core.log + .1 through .28) |
| Shadow journal scanned | shadow_critical_event_journal_v1.jsonl (57,478 total events) |
| Trade lifecycle scanned | trade_lifecycle.jsonl (139,688 total events) |
| Domain decision log scanned | domain_decision_making.log + .1 + .30 |
| Active md_amr symbols | XRPUSDT only (BNBUSDT disabled since 2026-04-15 per-regime calibration) |
| Runtime restarts observed | 2 (at ~09:45 UTC and ~16:28 UTC on 2026-04-16) |

**FACT**: BNBUSDT was disabled in md_amr config on 2026-04-15. Only XRPUSDT was active during the observation window.

**FACT**: Two runtime restarts occurred during the window. Both show `CLEAN_START_UPGRADE` from `COLD → RESTORED` via canonical zero-positions.

---

## 2. Artifact Inventory

### Primary Sources

| Artifact | Path | Size | Relevance |
|----------|------|------|-----------|
| Aurora core logs | `logs/aurora_core.log` + `.1` through `.28` | ~290 MB total | MD_AMR_SIGNAL traces with full overlay component fields |
| Shadow journal | `logs/shadow_critical_event_journal_v1.jsonl` | 66 MB | md_amr trade intent events (20 events) |
| Trade lifecycle | `logs/trade_lifecycle.jsonl` | 229 MB | md_amr lifecycle events (35 events) |
| Decision making log | `logs/domain_decision_making.log` + `.1` + `.30` | ~15 MB | Handler registration, regime gates |
| 21h runtime path | `reports/runtime_21h_md_amr_path_raw.log` | 25 MB | Earlier 21h path trace (no overlay fields) |

### MD_AMR Events Found

| Event Type | Count | Contains CV Trace? |
|------------|-------|-------------------|
| MD_AMR_SIGNAL (full trace) | 2 | YES — but CV = null |
| MD_AMR_SIGNAL_READY (NOOP) | 3 | NO — summary only |
| MD_AMR_SIGNAL_EMITTED | 2 | NO — summary only |
| MD_AMR_REGIME_GATE_BLOCKED | 18 | NO |
| MD_AMR_INIT / ENABLED / REGISTERED | 6 | NO |
| MD_AMR_CLEAN_START_UPGRADE | 2 | NO |
| MD_AMR_HYDRATION | 2 | NO |
| MD_AMR seed_startup_bars | 2 | NO |
| MD_AMR_C1_ANCHOR_SET | **0** | N/A — **never fired** |
| Shadow journal (all REJECTED) | 20 | NO — rejection events only |
| Trade lifecycle (md_amr) | 35 | NO — pipeline events only |

---

## 3. Per-Trade Context Validity Extraction

### Signal 1: FEE_AWARE_SCALEOUT (2026-04-15 23:30:03 UTC)

| Field | Value |
|-------|-------|
| Symbol | XRPUSDT |
| Intent | PARTIAL_CLOSE |
| Reason | FEE_AWARE_SCALEOUT |
| elapsed_hold_frac | 0.25 (bar 4 of 16) |
| entry_price | **null** |
| entry_target_price | **null** |
| progress_pct | **null** |
| hold_quality | **null** |
| context_validity | **null** |
| context_validity_state | **UNKNOWN** |
| context_validity_missing | `["hold_quality", "progress_deficit"]` |
| context_penalty_reason | MISSING_CONTEXT |
| regime_validity_component | 0.0 (regime=TREND_UP, not allowlisted) |
| volatility_validity_component | 0.946 |
| structure_validity_component | 0.319 |
| progress_alignment_component | **null** |
| Outcome | ARBITRATION_BLOCKED (intent rejected at signal gateway) |

### Signal 2: ZOMBIE_POSITION_TIMEOUT (2026-04-16 14:15:06 UTC)

| Field | Value |
|-------|-------|
| Symbol | XRPUSDT |
| Intent | FULL_CLOSE |
| Reason | ZOMBIE_POSITION_TIMEOUT |
| elapsed_hold_frac | 1.0 (bar 16 of 16, max hold reached) |
| entry_price | **null** |
| entry_target_price | **null** |
| progress_pct | **null** |
| hold_quality | **null** |
| context_validity | **null** |
| context_validity_state | **UNKNOWN** |
| context_validity_missing | `["hold_quality", "progress_deficit"]` |
| context_penalty_reason | MISSING_CONTEXT |
| regime_validity_component | 0.0 (regime=UNCERTAIN, conf=0.15, not allowlisted) |
| volatility_validity_component | 1.0 |
| structure_validity_component | 0.561 |
| progress_alignment_component | **null** |
| Outcome | NO_POSITION_FOR_CLOSE (position already closed before signal reached gateway) |

### Root Cause: Why Context Validity Is Always Null

**FACT**: `MD_AMR_C1_ANCHOR_SET` was never logged during the entire observation window. Zero entry anchors were set.

**FACT**: Entry anchors (`entry_price`, `entry_target_price`) are set ONLY when the handler processes an ENTRY intent (md_amr_handler.py:2029–2036). No ENTRY signal was generated during this window.

**FACT**: Both observed trades appear to be holdover positions from before the current runtime boot. The handler did `CLEAN_START_UPGRADE` from `COLD → RESTORED`, which restores execution state but does NOT restore entry anchors (they are in-memory only at `self._entry_anchor`).

**INFERENCE**: The C.1→C.3→C.4 dependency chain is broken in live:
```
entry_anchor (C.1) → progress_pct → hold_quality (C.3) → context_validity (C.4)
```
If `entry_anchor` is null (lost on restart or never set), the entire chain produces null, and `context_validity` falls back to `UNKNOWN` with `MISSING_CONTEXT`.

**FACT**: The C.4 code path (`_compute_context_validity_overlay`) correctly produces null when its input dependencies are missing — this is the designed graceful degradation, not a bug.

---

## 4. Live Distribution Summary

### Context Validity Composite

| Metric | Value |
|--------|-------|
| Observations with non-null CV | **0** |
| Observations with null CV | **2** (100%) |
| VALID count | 0 |
| WEAKENING count | 0 |
| INVALID count | 0 |
| UNKNOWN count | 2 (100%) |

**FACT**: There is no live context_validity distribution to analyze. Every observation is null/UNKNOWN.

### Component Scores (Partially Observable)

Three of four CV components computed normally:

| Component | Signal 1 | Signal 2 | Notes |
|-----------|----------|----------|-------|
| regime_validity | 0.0 | 0.0 | Both regimes not allowlisted (TREND_UP, UNCERTAIN) |
| volatility_validity | 0.946 | 1.0 | Normal computation — low volatility |
| structure_validity | 0.319 | 0.561 | Normal computation — moderate directional coherence |
| progress_alignment | null | null | Depends on hold_quality → depends on entry_anchor → null |

**INFERENCE**: 3 of 4 components compute normally. The chain breaks at `progress_alignment` because it requires `hold_quality` and `progress_deficit`, which require `entry_anchor`.

**INFERENCE**: If entry anchors were available, regime_validity would still be 0.0 (regime not allowlisted in both cases), making the weighted composite:
- Signal 1: `0.35×0.0 + 0.20×0.946 + 0.20×0.319 + 0.25×?` = `0.253 + 0.25×progress_alignment`
- Signal 2: `0.35×0.0 + 0.20×1.0 + 0.20×0.561 + 0.25×?` = `0.312 + 0.25×progress_alignment`

Even with `progress_alignment = 0`, these would be 0.253 and 0.312 — straddling the 0.25 threshold.

---

## 5. 0.25 Counterfactual Analysis

### Can the 0.25 Threshold Be Evaluated?

**NO.** The counterfactual analysis cannot be performed.

| Requirement | Status | Reason |
|-------------|--------|--------|
| Non-null CV scores on live trades | NOT MET | 0 of 2 signals have CV score |
| Sufficient trade count | NOT MET | Only 2 signal events, 0 completed live-entry-to-exit cycles |
| Both symbols observed | NOT MET | BNBUSDT disabled; only XRPUSDT |
| Trades crossing below 0.25 | INDETERMINATE | Cannot evaluate — CV is null |
| Trades recovering after crossing 0.25 | INDETERMINATE | Cannot evaluate |
| Losing trades potentially helped | INDETERMINATE | Cannot evaluate |

### Partial Component-Based Estimate

Using the 3 observable components and assuming `progress_alignment = 0`:

| Signal | Estimated CV Floor (no PA) | Would Cross 0.25? |
|--------|---------------------------|-------------------|
| Signal 1 (SCALEOUT, bar 4) | 0.253 | BORDERLINE — barely above |
| Signal 2 (TIMEOUT, bar 16) | 0.312 | NO — above 0.25 |

**ASSUMPTION**: `progress_alignment_component ≥ 0` in general. If so, these estimates are lower bounds.

**INFERENCE**: Even in the (hypothetical) best-available-data case, Signal 1 would be borderline at 0.25. But this is inference from 2 data points with one missing component — statistically meaningless.

---

## 6. Slow Reversion Risk Review

### Can Slow Reversion Risk Be Assessed?

**NO.**

| Requirement | Status | Reason |
|-------------|--------|--------|
| Observed slow profitable reversions | 0 | No completed entry-to-exit cycle observed |
| CV scores on slow holds | null | No non-null CV available |
| Trades reaching bars 13+ with profit | 1 (Signal 2 at bar 16) | But position already closed; outcome unknown |

Signal 2 reached `elapsed_hold_frac = 1.0` (bar 16, max hold) — this is exactly the profile of a slow reversion. But:
- Its realized P&L is unknown (the close was rejected as NO_POSITION_FOR_CLOSE)
- Its CV was null
- We cannot determine whether it was profitable or not

**INFERENCE**: The slow-reversion safety question from D.1 cannot be validated or falsified with this data.

---

## 7. Replay vs Live Comparison

| Dimension | Replay (D.1) | Live (D.2) | Status |
|-----------|-------------|-----------|--------|
| Trades with CV composite | 333 | 0 | **BLOCKING DIVERGENCE** |
| CV score distribution | Mean 0.309, range 0.12–0.45 | All null | NOT COMPARABLE |
| CV state: VALID | 0% | 0% | Trivially same, different mechanism |
| CV state: WEAKENING | 93–100% | 0% | DIVERGENT |
| CV state: INVALID | 0–7% | 0% | DIVERGENT |
| CV state: UNKNOWN | 0% | 100% | **BLOCKING DIVERGENCE** |
| Entry anchors populated | 100% | 0% | **ROOT CAUSE** |
| Regime not allowlisted | ~variable | 100% (18 REGIME_GATE_BLOCKED) | Expected — TREND_UP/UNCERTAIN regime |
| Volatility component | variable | 0.95–1.0 | Component computes normally |
| Structure component | variable | 0.32–0.56 | Component computes normally |

### Root Cause of Divergence

**FACT**: In replay, the simulation engine calls `_initial_trade_state` and `_update_trade_overlay` in a tight loop where entry anchors are always set at the simulated entry bar. There is no restart, no state loss, no cold-start path.

**FACT**: In live runtime, the handler starts with `CLEAN_START_UPGRADE` (COLD → RESTORED). Entry anchors are in-memory only (`self._entry_anchor: Dict`). They are NOT persisted to warm state, NOT restored from guardian, NOT reconstructed from any durable store.

**INFERENCE**: The replay→live gap is not a distributional difference (e.g., "scores are shifted") — it is a **structural absence**. The overlay chain is architecturally incapable of producing a composite CV score after any restart where a position was not entered fresh.

**FACT**: This is not a new discovery. It is the same class of problem as DEF-005 (OrderIndex lost on restart) documented in the TRACK_A execution forensic. Entry anchors are another in-memory-only state that does not survive restart.

---

## 8. What Is Proven

1. **Context validity composite is null in all live observations.** (FACT: 0/2 signals have non-null CV)

2. **The root cause is entry anchor non-persistence.** (FACT: `self._entry_anchor` is in-memory only; `MD_AMR_C1_ANCHOR_SET` never fires after restart because no ENTRY signal occurs)

3. **Three of four CV components compute normally in live.** (FACT: regime_validity, volatility_validity, structure_validity all produce valid floats)

4. **The dependency chain C.1 → C.3 → C.4 breaks at the anchor root.** (FACT: without `entry_price`/`entry_target_price`, `progress_pct` → `hold_quality` → `progress_alignment` → `context_validity` all cascade to null)

5. **The observation window is too sparse for distributional analysis.** (FACT: 2 signal events, 0 completed entry-to-exit cycles, 1 symbol active)

6. **BNBUSDT cannot be observed.** (FACT: disabled in config since 2026-04-15)

---

## 9. What Remains Unproven

1. **Whether live CV distributions resemble replay.** (UNKNOWN — no live CV to compare)

2. **Whether CV 0.25 would endanger live slow reversions.** (UNKNOWN — no live CV scores, no completed slow reversions observed)

3. **Whether CV 0.25 is operationally stable in live.** (UNKNOWN — CV never produced a score in live)

4. **Whether the component scores (regime, volatility, structure) behave similarly to replay when the full composite is available.** (UNKNOWN — partial observation only)

5. **Whether the anchor non-persistence is the *only* reason for CV nullness, or whether other live conditions also degrade CV.** (UNKNOWN — no positive examples to compare against)

---

## 10. Promotion-Study Readiness Assessment

### Assessment Against D.2 Requirements

| D.2 Requirement | Met? | Why |
|-----------------|------|-----|
| Live CV distribution comparison vs replay | **NO** | CV is structurally null in live |
| Advisory threshold 0.25 counterfactual | **NO** | Cannot evaluate null scores against threshold |
| Slow reversion risk under live conditions | **NO** | No completed slow-reversion trades observed |
| CV stability / jitter assessment | **NO** | No score variation to measure |
| Sufficient sample size | **NO** | 2 signals, 0 completed cycles, 1 symbol |

### Blocking Issue Identified

**The D.1 replay thesis assumed that context_validity would produce non-null composites in live.** This assumption is falsified.

The entry-anchor dependency chain means:
- Any position surviving a restart will have null CV for its remaining life
- Any position entered fresh (after restart, from a clean entry signal) would have CV — but this was not observed
- The frequency of restarts in the current system (2 in 28 hours) means a significant fraction of live holds will have null CV

**INFERENCE**: Even if entry-anchor persistence were fixed, the D.1 evidence base would need to be re-evaluated against a mixed-null dataset (some trades with CV, some without), which is a different statistical surface than the 100%-populated replay dataset.

### Pre-Requisites Before D.2 Can Be Re-Attempted

Before live observation of CV 0.25 is possible:

1. **Entry anchor persistence** must be implemented — either:
   - Persist `_entry_anchor` to warm state JSON alongside other handler state, OR
   - Reconstruct anchors from guardian/WAL on restart (entry price is available from order records), OR
   - Accept that CV is null for restart-holdover positions and only observe fresh-entry trades

2. **BNBUSDT must be re-enabled** or a second symbol activated — D.1 results were bi-symbol; single-symbol observation is insufficient

3. **A longer observation window** with at least 10+ complete entry-to-exit cycles is needed

---

## 11. Final Verdict

```
+=========================================================+
|                                                         |
|  EVIDENCE INSUFFICIENT —                                |
|  EXTENDED LIVE OBSERVATION REQUIRED                     |
|                                                         |
+=========================================================+
```

### Formal Disposition

The D.2 live observation package **cannot validate or invalidate the D.1 replay thesis** because:

1. **Context validity composite is architecturally null in the current live runtime.** The C.1 → C.3 → C.4 dependency chain breaks at the entry-anchor root, which is in-memory only and lost on restart.

2. **Zero non-null CV observations were collected.** No distributional comparison, no threshold counterfactual, no slow-reversion risk assessment is possible.

3. **The observation window is too sparse.** 2 signal events, 0 completed entry-to-exit cycles, 1 symbol active.

### D.1 Thesis Status

The D.1 finding that CV 0.25 qualifies for further promotion study is **neither confirmed nor refuted**. It remains valid within the bounded replay context where it was derived. It has not been tested against live conditions because the prerequisite instrumentation (anchor persistence) does not exist.

### Required Pre-Requisite Package Before D.2 Re-Attempt

**Package D.2-PRE: Entry Anchor Persistence**

Before D.2 can be re-attempted, the following must be implemented:

| Item | Description | Scope |
|------|-------------|-------|
| 1. Anchor persistence | Persist `_entry_anchor` to warm state or reconstruct from durable store on restart | Code change (md_amr_handler.py) |
| 2. Null-CV audit logging | Add INFO log when CV falls back to UNKNOWN/MISSING_CONTEXT with reason | Code change (md_amr_handler.py or strategy) |
| 3. Symbol enablement | Re-enable BNBUSDT or confirm alternative second symbol | Config change |
| 4. Observation window | Minimum 7 days or 10+ completed entry-to-exit cycles | Runtime |

Until D.2-PRE is complete, the promotion study is suspended — not because CV 0.25 is disproven, but because it cannot be observed.

### Governance Status (Unchanged)

| Package | Status |
|---------|--------|
| C.1–C.4 | ACCEPTED_ADVISORY_ONLY |
| CV 0.25 | Qualifies for further study (D.1 thesis intact, not yet live-validated) |
| Baseline | A.1 (unchanged) |
| Promotion | NO PROMOTION YET |

---

*Report generated: 2026-04-16*
*Observation window: 2026-04-15 14:15 UTC — 2026-04-16 18:45 UTC*
*Artifacts: `reports/md_amr_cv025_live_observation.csv`, `reports/md_amr_cv025_trade_counterfactuals.csv`, `reports/md_amr_cv025_live_vs_replay_comparison.csv`*
*Root cause: Entry anchor non-persistence (in-memory only, lost on restart)*
