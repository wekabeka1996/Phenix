# VALIDATION_MATRIX_REGIME_LIFECYCLE_BTC_FOLLOW

Date: 2026-03-30

## Scope

This document defines a validation matrix for the proposed additive logic only:

- local regime lifecycle metadata
- BTC leader influence context

This is intentionally a replay, backtest, and shadow-test plan. It is not an implementation plan.

## Validation Objectives

1. Prove the new logic is additive and does not mutate raw structural regime truth.
2. Prove lifecycle and leader context are deterministic under replay.
3. Prove missing anchor or lifecycle evidence fails closed.
4. Prove no uncontrolled double counting against existing macro_resid and anchor_shock_veto surfaces.
5. Prove any trading impact is attributable, observable, and reversible.

## Core Invariants

These invariants must hold before any PnL discussion matters.

- Raw EVT:REGIME_DETECTED sequence must remain unchanged when the new logic is enabled in observe-only mode.
- Structural regime label, confidence, warmup, changed, and structural_regime_ref must not be rewritten by lifecycle or leader logic.
- map_to_flat_regime behavior for MR must remain unchanged.
- Existing macro_resid computation must remain unchanged unless explicitly and separately re-approved.
- Existing anchor_shock_veto semantics must remain unchanged in observe-only mode.
- Missing or stale lifecycle or leader context must produce no silent trading effect.

## Required Trace Points

Before active gating is allowed, the following traces should exist in replay and shadow output:

- local_regime_lifecycle snapshot per symbol
- leader_influence snapshot per symbol
- separate reason codes for lifecycle-driven blocks and leader-driven blocks
- explicit overlap counters when a decision is simultaneously affected by:
  - low regime confidence
  - anchor_shock_veto
  - leader influence
  - lifecycle inception hold
- counterfactual decision output in observe-only mode

## Matrix

| ID | Layer | Hypothesis | Dataset or slice | Required evidence | Pass condition |
| --- | --- | --- | --- | --- | --- |
| C1 | Contract parity | Raw structural regime output is unchanged by additive context in observe-only mode | Same replay inputs, baseline versus observe-only build | Exact diff of EVT:REGIME_DETECTED payload sequence | No diff in regime, confidence, changed, warmup, structural_regime_ref, ts ordering |
| C2 | Disable-path parity | With new modules disabled, downstream decisions match baseline exactly | Same replay inputs, baseline versus feature-disabled build | Exact diff of CMD:PROCESS_STRATEGY, trade intents, and strategy blocked reasons | No diff except additive observability artifacts that are explicitly disabled |
| C3 | Fail-closed missing context | Missing leader data or invalid lifecycle data causes no trading effect | Replays with anchor stream removed, delayed, or made stale | reason codes plus no-effect decision comparison | leader and lifecycle ready=false, no silent threshold changes, no synthetic fallback values |
| C4 | MR invariance | MR raw flat mapping is untouched | MR-focused replay set | Diff of flat regime mapping and trade eligibility | No diff in map_to_flat_regime output when leader/lifecycle are observe-only |
| R1 | Lifecycle determinism | stable_since_ts_ms and bars_in_state are deterministic | Deterministic replay repeated multiple times | Snapshot diffs of lifecycle event stream | Exact match across reruns |
| R2 | Leader determinism | leader state and confidence are deterministic under identical replay ordering | Deterministic replay repeated multiple times | Snapshot diffs of leader context stream | Exact match across reruns |
| R3 | Out-of-order robustness | Reordered or late anchor updates do not create silent regime-side corruption | Replays with synthetic anchor lateness and reordering | Trace counters for dropped, reordered, stale leader events | Context fails closed or degrades explicitly without mutating raw regime |
| R4 | Double-count containment | Combined leader plus existing anchor logic does not create uncontrolled overlap | BTC shock and alt lag slices | Overlap report for macro_resid, anchor_shock_veto, leader block, lifecycle block | Overlap is explicit, bounded, and attributable; no hidden score inflation |
| R5 | Fresh-regime timing benefit | Fresh regime plus adverse BTC leader context improves entry timing more than it reduces signal quality | Regime-flip slices with strong BTC impulse | Trade count, MAE, MFE, expectancy, entry-delay distribution | Improvement or acceptable tradeoff against a predeclared governance budget |
| R6 | Neutral-period non-regression | New logic does not degrade neutral periods | Low-vol and non-BTC-driven slices | Trade count, fill rate, expectancy, blocked-rate deltas | Deltas remain within predeclared tolerance |
| R7 | Warmup integrity | Leader logic does not introduce unexpected warmup deadlocks | Startup backfill and live-like warmup slices | warmup.full_ready timing, anchor readiness diagnostics, regime readiness diagnostics | No new deadlock pattern; all blocked states have explicit reasons |
| R8 | Execution invariance | Existing EP global exposure adaptation behavior remains unchanged | Strategy replay with execution traces | Diff of exposure-guard regime adaptation events | No diff unless EP integration is intentionally enabled in a separate experiment |
| S1 | Shadow observe-only | Observe-only mode produces usable counterfactual signals without touching live execution | Live shadow stream | Counterfactual block logs, overlap counters, lifecycle and leader telemetry | Full telemetry present, zero execution-side behavior changes |
| S2 | Shadow attribution | Every counterfactual block or threshold change is explainable | Live shadow stream during BTC-led impulses | Per-decision forensic record | Each event has a single dominant reason and explicit overlap annotations |
| S3 | Rollback safety | New context can be disabled instantly with behavior returning to baseline | Shadow and staged rollout | Feature-toggle rollback evidence | Toggle-off returns system to baseline behavior without stale residual state |

## Dataset Requirements

Replay and backtest slices should include at least these categories:

- BTC crash or impulse periods with visible alt follow-through
- BTC impulse periods with weak alt follow-through or delayed catch-up
- local regime flips not obviously driven by BTC
- quiet low-vol periods where new leader logic should be mostly inert
- startup and warmup periods where anchor readiness is incomplete

Negative controls are mandatory:

- BTCUSDT itself when BTCUSDT is the configured anchor_symbol
- symbols whose local structure is stable while BTC is noisy
- replays where anchor input is intentionally stale or missing

## Metrics To Track

Trading metrics:

- entry count
- reduce-only count
- blocked-intent count by reason
- fill rate
- expectancy
- MAE and MFE
- drawdown
- average holding time

Context metrics:

- lifecycle_phase distribution
- bars_in_state distribution
- leader influence state distribution
- leader context stale rate
- lifecycle ready=false rate
- overlap count with anchor_shock_veto
- overlap count with low regime confidence gate

Warmup and data-quality metrics:

- feature warmup.full_ready latency
- regime warmup.full_ready latency
- anchor staleness rate
- out-of-order anchor event counters
- leader context missing-data rate

## Decision Rules For Promotion

Promotion from observe-only to active gating should require all of the following:

1. Contract parity invariants C1 through C4 pass.
2. Determinism checks R1 and R2 pass exactly.
3. Double-count containment R4 shows explicit and acceptable overlap rather than hidden score compounding.
4. Neutral-period non-regression R6 stays within governance tolerance.
5. Shadow attribution S1 through S3 proves that counterfactual decisions are explainable and reversible.

## Rollout Recommendation

Recommended rollout ladder:

1. Replay only, observe-only.
2. Backtest comparison on curated BTC-led slices.
3. Shadow live observe-only with full overlap telemetry.
4. Aurora-only active gating behind a separate toggle.
5. Later optional expansion to MD-AMR and only then any MR or EP discussion.

## ASSUMPTIONS

- Replay infrastructure can provide deterministic event order for both local symbol and anchor symbol streams.
- Counterfactual decision capture is available or can be added without changing live execution behavior.

## UNKNOWNS

- The acceptable governance budget for neutral-period non-regression is not yet defined in repo evidence inspected for this audit.
- Production live-stream anchor ordering behavior was not directly validated in this document and needs shadow confirmation.

## Bottom Line

The correct validation order is invariants first, overlap audit second, and PnL only after both are clean. The new logic should not be judged by outcome metrics until it first proves that it preserves raw structural regime truth, behaves deterministically, fails closed on missing context, and does not silently double count the BTC-anchor information already present in macro_resid and anchor_shock_veto.
