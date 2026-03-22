# AURORA_DECISION_GEOMETRY_REPAIR_PACK — REPORT

Date: 2026-03-21
Branch: Phenix_v2
Scope: contract-safe Aurora decision-geometry repair with additive-only config/model/runtime changes

## Executive Verdict

Winner: decoupled linear admission plus quadratic sizing, with an admission-only shield floor of 0.75 and hard-veto preservation.

Why this wins from evidence instead of taste:
- It reduces structural neutral starvation materially more than baseline quadratic and more than the representative in-band soft-power candidate `p = 1.5` on ETHUSDT and SOLUSDT.
- It does not create a BTC over-admission regression on the first BTC-compatible recorder day checked in this package.
- It preserves quadratic sizing semantics while separating admission math from sizing math.
- It preserves fail-closed shield veto semantics: if total shield multiplier is exactly `0.0`, admission remains vetoed.

Package verdict:
- Structural starvation dropped at the admission boundary for ETHUSDT and SOLUSDT.
- No evidence in this package shows `NRR-027` started masking new garbage. The offline `NRR-027` proxy rate stayed flat-to-lower on the side-bearing population in the main forensic window.
- Full live `EVT:STRATEGY_SIGNAL_PRODUCED` equivalence is NOT proven by this package. Evidence here is bounded to recorder/regime/shield replay plus allowlist and an offline directional-sanity proxy.

## 1. Runtime Choke Confirmed

Confirmed live choke before this repair:
- Raw Aurora linear score enters `QuadraticScoringKernel`.
- Admission side resolution used the post-transform, post-shield score.
- The transform was quadratic: `sign(S) * |S|^2`.
- Threshold comparison used that compressed score after shield attenuation.
- This compresses mid-range signals before thresholding and then attenuates them again with the shield cascade.

Baseline formula:
- `S_raw = clamp(score_multiplier * pillar_sum, -1, 1)`
- `decision_score_baseline = sign(S_raw) * |S_raw|^2 * shield_total`
- Side resolution compares `decision_score_baseline` against threshold and hysteresis bands.

Observed choke effect from prior forensics and reproduced bounded replay:
- ETHUSDT and SOLUSDT were dominated by neutral returns at the kernel boundary.
- BTCUSDT could survive on some windows because its threshold surface is materially different, not because the quadratic geometry is healthy.

## 2. Candidate Comparison

Required candidates compared:

1. Baseline quadratic
- `D_quad = sign(S_raw) * |S_raw|^2 * shield_total`
- `Q_quad = D_quad`

2. Soft-power candidate, representative in-band `p = 1.5`
- `D_soft = sign(S_raw) * |S_raw|^1.5 * shield_total`
- `Q_soft = sign(S_raw) * |S_raw|^2 * shield_total`

3. Decoupled winner candidate
- `shield_admission = 0`, if `shield_total == 0`
- `shield_admission = max(shield_total, admission_shield_floor)`, otherwise
- `D_decoupled = S_raw * shield_admission`
- `Q_decoupled = sign(S_raw) * |S_raw|^2 * shield_total`
- This package sets `admission_shield_floor = 0.75`

Why candidate 3 wins:
- It gives the largest starvation reduction on ETHUSDT and SOLUSDT in both replay windows used here.
- It keeps sizing quadratic instead of flattening the entire downstream exposure semantics.
- It leaves hard-veto shield behavior untouched.
- It improved or held the offline `NRR-027` proxy rate rather than inflating it.

Why candidate 2 lost:
- It improved over baseline, but less than the decoupled design in both ETHUSDT and SOLUSDT windows used here.
- It still compresses the admission boundary enough to leave materially more neutral bars than the winning design.

## 3. Implementation

### 3.1 YAML + Pydantic contract

Added explicit geometry SSOT instead of hidden math constants.

YAML change in `config/aurora/strategies/aurora.yaml`:
- `decision_geometry.admission_mode: linear`
- `decision_geometry.sizing_mode: quadratic`
- `decision_geometry.admission_shield_floor: 0.75`

Pydantic change in `apps/reference/config_models.py`:
- Added `DecisionGeometryConfig`
- Added `DecisionConfig.decision_geometry`
- Validation rules:
  - `soft_power` requires explicit exponent in `(1, 2)`
  - non-soft modes reject explicit power

### 3.2 Runtime loader

`apps/reference/domains/decision_making/aurora_config_loader.py` now hydrates:
- `decision_admission_mode`
- `decision_admission_power`
- `decision_sizing_mode`
- `decision_sizing_power`
- `decision_admission_shield_floor`

### 3.3 Kernel repair

`apps/reference/domains/decision_making/quadratic_scoring_kernel.py` now computes two scores instead of one coupled score:
- `decision_score`
- `sizing_score`

Key invariants:
- `result.score` is preserved as the admission score alias for backward-compatible admission semantics.
- If total shield multiplier is `0.0`, the admission floor does not override it.
- Shield cascade order is unchanged.

### 3.4 Decision-path wiring

`apps/reference/domains/decision_making/aurora_decision.py` now:
- passes geometry config into the kernel
- logs and traces `raw_score`, `decision_score`, `sizing_score`, `admission_shield_multiplier`, `admission_mode`, `sizing_mode`
- emits those fields in the signal scoring payload
- uses `sizing_score` for `quantize_exposure(...)`

## 4. Observability Added

New observability surfaced in decision trace / kernel diagnostics / emitted scoring payload:
- `raw_score`
- `decision_score`
- `sizing_score`
- `shield_multiplier_total`
- `admission_shield_multiplier`
- `admission_mode`
- `sizing_mode`
- `admission_result`

Operational effect:
- Neutral starvation can now be separated from sizing compression.
- Shield attenuation at admission can be distinguished from shield attenuation at sizing.
- Hard-veto vs shield-floor behavior is observable instead of implicit.

## 5. Validation

### 5.1 Targeted tests

Executed:
- `pytest tests/domains/decision_making/test_aurora_decision_geometry.py tests/domains/decision_making/test_aurora_quadratic_logging.py`

Result:
- `7 passed`

What those tests prove:
- baseline quadratic remains coupled when selected
- linear admission plus quadratic sizing decouples the scores as intended
- hard veto is preserved even with admission shield floor
- Pydantic rejects invalid geometry contracts
- nearby decision-trace logging behavior still passes

### 5.2 Replay method

Validation tool added:
- `tools/forensics/validate_aurora_decision_geometry.py`

Method actually used:
- recorder bars
- `RegimeDetector`
- live shield cascade construction
- live threshold surfaces from current config
- post-admission allowlist check
- offline `NRR-027` directional-sanity proxy from current domain config

Method NOT claimed:
- full live replay through objective engine, execution gate, quantizer, gateway, and order-log truth

### 5.3 Main forensic window: 2026-03-20

From `reports/aurora_decision_geometry_validation_2026-03-20.md`:

ETHUSDT:
- Baseline quadratic: `eligible=63`, `neutral_ratio=80.95%`, `side_ratio=19.05%`, `allowed_side=12`, `NRR-027 proxy rate=25.00%`
- Soft-power `p=1.5`: `eligible=63`, `neutral_ratio=28.57%`, `side_ratio=71.43%`, `allowed_side=37`, `NRR-027 proxy rate=13.33%`
- Decoupled winner: `eligible=63`, `neutral_ratio=0.00%`, `side_ratio=100.00%`, `allowed_side=46`, `NRR-027 proxy rate=9.52%`

SOLUSDT:
- Baseline quadratic: `eligible=116`, `neutral_ratio=52.59%`, `side_ratio=47.41%`, `allowed_side=49`, `NRR-027 proxy rate=10.91%`
- Soft-power `p=1.5`: `eligible=116`, `neutral_ratio=25.00%`, `side_ratio=75.00%`, `allowed_side=77`, `NRR-027 proxy rate=8.05%`
- Decoupled winner: `eligible=116`, `neutral_ratio=0.00%`, `side_ratio=100.00%`, `allowed_side=97`, `NRR-027 proxy rate=7.76%`

BTCUSDT:
- Recorder file for this window was schema-compatible but had `eligible=0` in this replay path.
- Therefore this window was usable for ETHUSDT and SOLUSDT starvation evidence, but not for BTC regression proof.

Interpretation bounded to evidence:
- Starvation dropped sharply for ETHUSDT and SOLUSDT.
- The winning candidate outperformed both baseline and soft-power on the same window.
- The offline `NRR-027` proxy rate did not increase on the side-bearing population; it fell.

### 5.4 BTC-compatible window: 2026-03-13

From `reports/aurora_decision_geometry_validation_2026-03-13.md`:

BTCUSDT:
- Baseline quadratic: `eligible=132`, `neutral_ratio=100.00%`, `side_ratio=0.00%`
- Soft-power `p=1.5`: `eligible=132`, `neutral_ratio=100.00%`, `side_ratio=0.00%`
- Decoupled winner: `eligible=132`, `neutral_ratio=100.00%`, `side_ratio=0.00%`

ETHUSDT:
- Baseline quadratic: `neutral_ratio=100.00%`, `side_ratio=0.00%`
- Soft-power `p=1.5`: `neutral_ratio=68.94%`, `side_ratio=31.06%`
- Decoupled winner: `neutral_ratio=59.09%`, `side_ratio=40.91%`

SOLUSDT:
- Baseline quadratic: `neutral_ratio=99.26%`, `side_ratio=0.74%`
- Soft-power `p=1.5`: `neutral_ratio=66.18%`, `side_ratio=33.82%`
- Decoupled winner: `neutral_ratio=56.62%`, `side_ratio=43.38%`

Interpretation bounded to evidence:
- BTC did not begin emitting side-bearing garbage in the first BTC-compatible recorder window inspected here.
- ETHUSDT and SOLUSDT again improved more under the decoupled design than under soft-power.
- This is sufficient for a non-regression statement at the admission boundary, not for a full production-signal claim.

### 5.5 Signal-produced count statement

Proven in this package:
- pre-signal side-bearing count
- pre-signal allowlist-surviving count
- offline `NRR-027` proxy distribution

Not proven in this package:
- exact live `EVT:STRATEGY_SIGNAL_PRODUCED` count under the repaired geometry

Reason:
- the replay harness used here does not faithfully execute the entire post-kernel live Aurora pipeline.
- claiming exact signal-produced counts from this evidence would violate fail-closed reporting.

## 6. Answer To The User’s Core Questions

Did starvation really drop?
- Yes, at the admission boundary, materially.
- ETHUSDT on 2026-03-20 improved from `80.95%` neutral to `0.00%` neutral.
- SOLUSDT on 2026-03-20 improved from `52.59%` neutral to `0.00%` neutral.
- ETHUSDT and SOLUSDT also improved on the BTC-compatible 2026-03-13 window.

Did `NRR-027` start masking garbage?
- No evidence of that in this package.
- On the main forensic window, the offline proxy rate went down under the winner:
  - ETHUSDT: `25.00% -> 9.52%`
  - SOLUSDT: `10.91% -> 7.76%`
- On the BTC-compatible window, the proxy remained `0` because no candidate produced side-bearing BTC admissions there.
- This is still a bounded offline proxy statement, not full live order-log proof.

## 7. FACTS

- The live admission path was using quadratic post-shield score for side resolution before this package.
- The implemented repair is additive-only and config-gated through YAML + Pydantic.
- The winning runtime configuration is explicit, not hidden in code.
- Hard-veto shield semantics are preserved.
- `quantize_exposure(...)` now uses `sizing_score`, not the admission score alias.
- The new validation tool and targeted tests ran successfully.

## 8. INFERENCES

- The dominant defect was admission-boundary geometry, not primary gateway notional sizing.
- The admission-only shield floor is materially responsible for reviving side-bearing ETHUSDT and SOLUSDT decisions when shield attenuation would otherwise over-compress them.
- Keeping sizing quadratic is safer than flattening both admission and sizing together.

## 9. ASSUMPTIONS

- Recorder bars plus live regime/shield construction are sufficient to compare candidate decision geometries at the admission boundary.
- The current directional-sanity domain config is close enough to use for an offline `NRR-027` proxy.

## 10. UNKNOWNS

- Exact live `EVT:STRATEGY_SIGNAL_PRODUCED` counts after this repair.
- Exact post-gateway reject redistribution after the repair.
- Whether later post-kernel gates will now become the dominant blocker family on ETHUSDT and SOLUSDT in production.

## 11. Risks

- ETHUSDT and SOLUSDT now reach later gates more often; downstream blockers may rise even though starvation falls.
- The admission shield floor is an explicit business constant and may require later calibration by regime if operational logs show over-admission in other windows.
- BTC evidence is non-regression at the admission boundary only; it is not a full production profitability or trade-quality proof.

## 12. Changed Files

- `apps/reference/config_models.py`
- `config/aurora/strategies/aurora.yaml`
- `apps/reference/domains/decision_making/aurora_config_loader.py`
- `apps/reference/domains/decision_making/quadratic_scoring_kernel.py`
- `apps/reference/domains/decision_making/aurora_decision.py`
- `tests/domains/decision_making/test_aurora_decision_geometry.py`
- `tools/forensics/validate_aurora_decision_geometry.py`
- `reports/aurora_decision_geometry_validation_2026-03-20.md`
- `reports/aurora_decision_geometry_validation_2026-03-13.md`

## 13. Next Package

AURORA_POST_ADMISSION_GATE_DISTRIBUTION_PACK
- Use the repaired geometry in a bounded live-style replay to measure exact blocker redistribution after the kernel, especially `REGIME_NOT_ALLOWLISTED`, execution-gate rejects, quantizer rejects, and real `NRR-027` order-log counts.
