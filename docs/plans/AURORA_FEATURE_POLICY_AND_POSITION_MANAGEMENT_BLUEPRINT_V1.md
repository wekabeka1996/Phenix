# AURORA_FEATURE_POLICY_AND_POSITION_MANAGEMENT_BLUEPRINT_V1

## Status
- Scope: design only
- Runtime/code/YAML activation: not applied in this package
- Basis: current forensic evidence from `order_log_v1.jsonl`, `trade_lifecycle.jsonl`, `execution_lifecycle_stats_v1.jsonl`, `data/recorder`, and current `Aurora` / `decision_making` code

## Goal
Design a feature-driven entry and position-management policy for `Aurora` that:
- reduces avoidable losing entries
- reduces giveback on positions that were already in profit
- reuses existing gate foundations where they are already conceptually correct
- avoids duplicating `NRR-026...030` or current shield/exit substrates when those already solve part of the problem

## Runtime Evidence This Blueprint Explains

## FACTS
- `BTCUSDT` short was a bad fresh short:
  - raw detector regime had already drifted to `MEAN_REVERSION`
  - emitted entry regime was only `hysteresis_carried`
  - confidence was almost at the floor
  - `abs(motion_sigma)` was extreme
  - the position never achieved retained positive excursion
- `DOGEUSDT` short was a late short:
  - raw regime was still `TREND_DOWN`
  - pre-entry move was already stretched
  - fill came materially late after the signal
  - score margin over threshold was thin
  - position later achieved large positive excursion, then gave it all back and closed at `SL`
- `ETHUSDT` short was directionally more correct:
  - raw regime and emitted regime matched
  - confidence was strong
  - post-entry path continued in short direction
  - position still finished net negative after fees because realized move was too small

## INFERENCES
- Not all current losses are caused by the same failure mode.
- There are at least three distinct failure classes:
  - regime-state misclassification / carry contamination
  - late-entry into already stretched impulse
  - weak monetization / fee-unaware exit geometry
- Therefore a single scalar threshold change is not enough.

## Existing Foundations

### What already exists
- `NRR-026`
  - `INSUFFICIENT_TREND_CONFIRMATION`
  - denies when trend is unknown or confidence is below minimum
  - code seam: `apps/reference/domains/decision_making/gates/safety_gates.py`
- `NRR-027`
  - `DIRECTIONAL_SANITY_BLOCKED`
  - denies countertrend long-in-downtrend / short-in-uptrend after sufficient run length
- `NRR-028`
  - `PRICE_MOTION_INSUFFICIENT`
  - fail-closed when price-motion features are missing and required
- `NRR-029`
  - `PRICE_MOTION_FLASH_BLOCKED`
  - blocks opening against fast motion
- `NRR-030`
  - `PRICE_MOTION_BLEED_BLOCKED`
  - blocks opening against sustained motion
- `Aurora` vol-adjusted gates
  - `anti_flat_sigma`
  - `anti_fomo_sigma`
  - current config uses `motion_window_sec=300`
- `DangerZoneShield`
  - entry-side hard block when shield fires
  - current `exit_manager` can tighten stops when `danger_zone_active=true` and the position is already profitable
- `execution_position` sidecar substrate
  - already has fee-aware arm / percent-notional arm / peak-giveback telemetry
  - currently not recommended as a wholesale close-authority replacement, but it contains useful lifecycle components
- `execution_lifecycle_stats_v1.jsonl`
  - already tracks MFE, MAE, first positive PnL timestamp, peak giveback

### Where the current foundations are insufficient
- `NRR-026` is too coarse.
  - It knows "confidence/trend not sufficient".
  - It does not know "trend label is carried while raw detector already disagrees".
- `NRR-027` is not the right tool for current bad shorts.
  - It blocks countertrend trades.
  - It does not block aligned-but-late shorts.
- `NRR-029/030` are sign-based against-motion gates.
  - They block opening against a move.
  - They do not block opening with the move when the move is already exhausted or stretched.
- `anti_fomo_sigma` is conceptually relevant but currently too loose for the observed slice.
  - Current config is `10.0`.
  - Observed bad shorts were already dangerous around `4.25` to `5.24`.
- `DangerZone` and current exit logic do not solve giveback harvesting.
  - `ETH` shows fee-unaware monetization.
  - `DOGE` shows large MFE followed by catastrophic giveback.

## Duplication Map

### Reuse, do not duplicate
- Reuse `NRR-026` as the base "trend integrity floor".
- Reuse `NRR-029/030` as the base "against-motion veto".
- Reuse `anti_fomo` as the base "same-direction stretch" seam.
- Reuse `execution_lifecycle_stats` for runtime truth and calibration.
- Reuse sidecar fee-aware / peak-giveback substrate for hold-management mechanics, but not sidecar close policy as-is.

### New logic is still required
- A new gate for `regime-state integrity`, not just confidence.
- A new gate for `aligned-but-late stretched entries`.
- A new hold policy for `profit harvest / giveback control`.
- Explicit lifecycle separation between:
  - immediately wrong trades
  - initially right trades that start decaying
  - still-correct trades that should keep running

## Proposed Policy Family

## Policy 1: Regime State Integrity Gate
- Purpose:
  - block entries where the emitted regime says `TREND_*`, but the raw detector already disagrees
- Why:
  - this is exactly what happened on `BTCUSDT`
- Proposed inputs:
  - `raw_regime`
  - `pre_cutoff_regime`
  - `emitted_confidence_kind`
  - `carried_previous_stable`
  - `regime_confidence`
  - `resolved_min_regime_confidence`
- Proposed logic:
  - for trend-follow entries, deny when:
    - `raw_regime != emitted_regime`
    - and `emitted_confidence_kind == hysteresis_carried`
  - stricter deny when:
    - carried regime also has very low confidence margin above the active minimum
- Design placement:
  - conceptually this is an extension of `NRR-026`
  - recommended family label:
    - `NRR-026A` or `trend_state_integrity`
- Why this is not duplication:
  - `NRR-026` checks trend/confidence sufficiency
  - this extension checks regime-label integrity

## Policy 2: Same-Direction Stretch Gate
- Purpose:
  - block fresh entries that are aligned with the current move but already too stretched
- Why:
  - this is the main missing guard for `DOGEUSDT`
  - it also would have blocked the extreme `BTCUSDT` case
- Proposed inputs:
  - signed `pm_norm_60s`
  - signed `pm_norm_300s`
  - absolute `motion_norm_sigma`
  - `score_margin_abs`
  - `regime`
  - `side`
- Proposed logic:
  - do not use only absolute sigma
  - use signed price-motion context plus margin quality
  - deny a short when:
    - `pm_norm_300s` is already strongly negative
    - and `score_margin_abs` is too small
    - and the regime is already trend-following short
  - deny a long symmetrically for strongly positive stretched impulses
- Suggested semantics:
  - `stretch_hard_block`:
    - stretched move + thin margin
  - `stretch_soft_attenuation`:
    - stretched move + still healthy margin
- Design placement:
  - build on `anti_fomo`, not beside it
- Why this is not duplication:
  - `NRR-029/030` block entries against motion
  - this gate blocks entries that are with motion but too late

## Policy 3: Stale Entry Guard
- Purpose:
  - stop opening entries that were valid at signal time but invalid by fill time
- Why:
  - `DOGEUSDT` signal-to-fill delay was too large
- Proposed inputs:
  - `signal_ts_ms`
  - `entry_fill_ts_ms`
  - `signal_close_price`
  - `fill_price`
  - current bar price-motion
- Proposed logic:
  - expire pending entry if fill latency exceeds per-regime budget
  - expire if price drift from signal close exceeds trade-direction drift budget
- Important note:
  - this is execution-aware entry protection
  - it belongs to `Aurora` entry policy but must be enforced by the order lifecycle

## Policy 4: Immediate Invalidity Exit
- Purpose:
  - cut trades that are wrong immediately and never achieve positive excursion
- Why:
  - `BTCUSDT` never became right
- Proposed inputs:
  - `first_positive_pnl_ts_ms`
  - `mfe_usdt`
  - `trend_dir`
  - `regime_state_integrity`
  - microstructure conflict score during first 1-2 bars
- Proposed logic:
  - if trade has no positive excursion inside the first decision window
  - and microstructure/regime deteriorates against the position
  - tighten aggressively or close early
- Design placement:
  - new hold-management state
  - not a sidecar close recommender clone

## Policy 5: Fee-Aware Break-Even Arm
- Purpose:
  - once trade has enough edge to cover round-trip costs, it should not finish net negative for a tiny favorable move
- Why:
  - `ETHUSDT` was directionally right but net negative after fees
- Proposed inputs:
  - observed fees or configured fee model
  - current unrealized edge
  - position notional
  - peak edge
- Proposed logic:
  - arm only after unrealized edge exceeds:
    - fee multiple floor
    - or percent-notional floor
  - once armed, move SL to fee-covered break-even zone
- Design placement:
  - reuse sidecar `shadow_fee_aware_arm` substrate
  - make it execution-position owned hold logic
- Why this is not duplication:
  - current sidecar shadow already models this concept
  - the gap is live authority and integration contour, not missing idea

## Policy 6: Peak-Giveback Harvest
- Purpose:
  - protect trades that were already profitable from round-tripping into full losses
- Why:
  - `DOGEUSDT` had large MFE and still died at `SL`
- Proposed inputs:
  - `peak_edge_usd`
  - `current_edge_usd`
  - `peak_giveback_pct`
  - regime and microstructure adverse pressure
- Proposed logic:
  - after peak edge is armed, apply one of:
    - tighten stop
    - promote to fee-covered stop
    - force soft close only when giveback and adverse state co-occur
- Design placement:
  - reuse `peak_giveback` lifecycle substrate
  - do not enable legacy sidecar recommendation logic wholesale

## Policy 7: Hold-Suppression Override
- Purpose:
  - stop `holding_period` from preserving positions that have already entered a decaying-profit or invalid state
- Why:
  - current hold policy can suppress soft exits/flips while the trade is no longer healthy
- Proposed logic:
  - `holding_period` stays active only when:
    - trade has not armed fee-aware edge
    - and no giveback state is active
    - and no immediate invalidity state is active
- This prevents hold policy from overriding stronger lifecycle evidence

## Proposed Architecture

### Entry policy state machine
- `ENTRY_OK`
- `ENTRY_CONFLICTED_REGIME`
- `ENTRY_STRETCHED`
- `ENTRY_STALE`
- `ENTRY_COUNTERTREND`
- `ENTRY_DATA_GAP`

### Hold policy state machine
- `HOLD_WRONG_EARLY`
- `HOLD_RIGHT_UNDERWATER_FEES`
- `HOLD_RIGHT_AND_ARMED`
- `HOLD_GIVEBACK_DECAY`
- `HOLD_CONTINUE`

### Why state machine, not one score
- The failures are semantically different.
- One weighted score would hide whether the policy is blocking because the trade is:
  - mislabeled
  - late
  - stale
  - fee-fragile
  - giving back already-earned edge

## Observability Contract Required Before Confident Activation
- retain authoritative `signal_close_price`
- retain `entry_fill_latency_ms`
- retain `entry_vs_signal_close_bps`
- retain signed `pm_norm_60s` and `pm_norm_300s` in accepted-order truth
- retain explicit `score_margin_abs`
- retain explicit `anti_fomo_triggered` / `danger_zone_motion_threshold`
- retain authoritative `TA_FEATURES_CALCULATED` linkage if TA is expected to influence the policy

## Why TA Should Not Be a First-Class Gate Yet

## FACTS
- Current inspected retained surfaces do not give authoritative TA event truth for the audited losing entries.

## INFERENCES
- TA may be useful later.
- But it is not currently a safe first-class policy dependency because its retained forensic surface is incomplete.

## Recommendation
- Phase 1 policy should be built on:
  - core feature stack
  - regime truth
  - price-motion truth
  - lifecycle economics
- TA should be added only after authoritative retention is proven.

## Recommended Implementation Order

### Package 1: Observability hardening
- add missing retained fields
- no behavior change

### Package 2: Entry policy
- regime-state integrity gate
- same-direction stretch gate
- stale-entry guard

### Package 3: Hold policy
- immediate invalidity exit
- fee-aware break-even arm
- peak-giveback harvest
- hold-suppression override

### Package 4: Counterfactual replay matrix
- replay existing runtime slices
- compare:
  - baseline
  - entry-only new policy
  - hold-only new policy
  - combined policy

## Minimal Viable Version
- If only one small slice can be shipped first, ship:
  - regime-state integrity gate
  - same-direction stretch gate
  - fee-aware break-even arm
- This is the highest expected loss-reduction per unit of complexity.

## Explicit Non-Recommendations
- do not globally disable confidence gates
- do not replace all existing gates with one new feature score
- do not promote `sidecar_only` close logic wholesale
- do not make TA a hard live dependency before retained truth exists
- do not treat all losing trades as "should have been opposite-side BUY"

## Final Verdict
- Existing `Aurora` features already contain enough information to prevent part of the observed losses.
- The missing piece is not raw feature availability.
- The missing piece is policy structure:
  - a better entry-state integrity layer
  - and a better profit-harvest / giveback layer
- Recommended direction:
  - extend existing foundations instead of inventing a parallel policy stack from zero

