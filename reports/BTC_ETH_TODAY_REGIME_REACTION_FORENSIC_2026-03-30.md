# BTC / ETH Today Regime-Reaction Forensic

Date in scope: 2026-03-30 only

## Scope

- Symbols: BTCUSDT, ETHUSDT
- Runtime evidence first
- No code changes
- Goal: separate regime identification quality from Aurora reaction quality, then isolate the main choke point and only then extract narrow manual calibration candidates

## Files Used

- logs/domain_regime_detector.log
- logs/domain_feature_engineering.log and rotated siblings
- logs/domain_decision_making.log and rotated siblings
- logs/aurora_core.log and rotated siblings
- logs/order_log_v1.jsonl
- logs/aurora_trades.log
- logs/aurora_events.jsonl
- logs/trade_lifecycle.jsonl
- config/aurora/strategies/aurora.yaml
- config/aurora/domains.yaml
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/quadratic_scoring_kernel.py
- apps/reference/domains/decision_making/safety_gates.py
- apps/reference/domains/decision_making/flip_orchestration.py

## Method Notes

- Text logs were evaluated by their local log timestamps on 2026-03-30.
- JSONL timestamps were normalized to local day using UTC+03:00 because that matches the visible text-log clock for the same events.
- Price context was taken from the nearest feature-engineering price around each regime transition, with 15-minute lookback and 15-minute lookforward deltas.
- Runtime truth outranked docs. Docs were used only to confirm active config consumers.

## FACTS

- BTCUSDT had 15 regime transitions today. ETHUSDT had 11.
- BTCUSDT had one low-confidence TREND_DOWN segment and three separate TREND_UP segments. ETHUSDT had two TREND_UP segments and no TREND_DOWN segment today.
- In TREND_UP, Aurora generated SELL or neutral only. It generated no BUY trace for BTCUSDT or ETHUSDT.
- BTCUSDT TREND_UP trace counts: 25 SELL, 25 neutral, 0 BUY.
- ETHUSDT TREND_UP trace counts: 23 SELL, 27 neutral, 0 BUY.
- BTCUSDT accepted 6 wrong-side TREND_UP SELL intents and 2 of them became real fills.
- ETHUSDT accepted 1 wrong-side TREND_UP SELL intent and it became a real fill.
- Wrong-side SELL attempts in TREND_UP were partially blocked by NRR-026, NRR-027, NRR-029, and NRR-030, but guards did not stop all of them.
- After shorts were already live, repeated same-side SELLs were later blocked by anti-pyramiding: 42 times for BTCUSDT and 40 times for ETHUSDT.

## INFERENCES

- Today’s dominant defect is not that the regime label failed to reach Aurora. The regime did reach Aurora.
- Today’s dominant defect is not downstream order propagation alone. Downstream filters rejected some accepted intents, but real wrong-side fills still occurred.
- The dominant defect is contrarian side generation from score inside directional uptrends, with guard families acting as partial containment rather than as the root signal source.
- BTC regime detection was only partially correct because its sole TREND_DOWN label was low-confidence and reversed sharply upward afterward.
- ETH regime detection was broadly correct on its TREND_UP segments.

## ASSUMPTIONS

- Local-day normalization of JSONL events to UTC+03:00 is correct because it aligns with text-log timestamps for the same RIDs and orders.
- Price structure judgment is limited to the available feature-engineering price series and not an external market tape.

## UNKNOWNS

- No external market tape or chart was imported, so regime correctness is judged from in-repo price context only.
- trade_lifecycle ORPHANED_TTL does not prove economic exit quality or realized PnL.
- This audit does not prove whether a code change is needed to fix side-generation logic. It only proves what happened today and which manual config levers are live.

## Active Calibration Boundary

- Aurora consumes per-symbol regime thresholds first and only falls back to global values if no symbol override exists.
- BTCUSDT and ETHUSDT both have per-symbol regime_thresholds, so global decision.regime_threshold_multipliers are not the live control surface for these two symbols.
- BTCUSDT has signal_threshold disabled at the symbol level, so it falls back to global decision.signal_threshold = 0.162.
- ETHUSDT has symbol-level signal_threshold enabled with value = 0.0221.
- The live guard surfaces today are:
  - domains.decision_making.directional_sanity.min_regime_confidence
  - domains.decision_making.directional_sanity.hard_veto_consecutive_bars
  - domains.decision_making.price_motion_sanity.flash_threshold_norm
  - domains.decision_making.price_motion_sanity.bleed_threshold_norm

## Regime Timeline And Segment Reaction: BTCUSDT

| Start | End | Regime | Conf | Model | Px | 15m Before % | 15m After % | Trace B/S/N | Wrong-Side Traces | Accepted Wrong-Side | Wrong-Side Fills | Reject Families |
|---|---|---|---:|---|---:|---:|---:|---|---:|---:|---:|---|
| 00:20 | 02:00 | MEAN_REVERSION | 0.4919 | mean_reversion_v2 | 66515.05 | -0.1084 | 0.1662 | 0/5/15 | 0 | 0 | 0 | - |
| 02:00 | 02:50 | HIGH_VOLATILITY | 0.8500 | volatility_v2 | 65803.55 | 0.2402 | 0.3926 | 0/3/7 | 0 | 0 | 0 | NRR-027 x1 |
| 02:50 | 03:05 | UNCERTAIN | 0.1500 | uncertain_cutoff_gate | 65993.45 | 0.0924 | -0.3077 | 0/0/3 | 0 | 0 | 0 | - |
| 03:05 | 03:30 | TREND_DOWN | 0.2379 | sma_trend_v1 | 65828.85 | -0.2494 | 1.7318 | 0/1/4 | 0 | 0 | 0 | - |
| 03:30 | 04:20 | HIGH_VOLATILITY | 0.8500 | volatility_v2 | 66540.75 | 1.0917 | -0.3469 | 0/4/6 | 0 | 0 | 0 | NRR-027 x1, NRR-026 x2 |
| 04:20 | 04:40 | MEAN_REVERSION | 0.2474 | mean_reversion_v2 | 66489.35 | 0.1473 | 0.3073 | 0/2/2 | 0 | 0 | 0 | NRR-026 x2 |
| 04:40 | 07:10 | UNCERTAIN | 0.1500 | sma_trend_v1 | 66594.05 | 0.2243 | 0.0215 | 0/0/30 | 0 | 0 | 0 | - |
| 07:10 | 09:45 | TREND_UP | 0.2895 | sma_trend_v1 | 67383.65 | 0.2734 | -0.0336 | 0/14/17 | 14 | 5 | 1 | NRR-026 x3, NRR-027 x3, NRR-029 x1, NRR-030 x1 |
| 09:45 | 11:10 | LOW_VOLATILITY | 0.3110 | volatility_v2 | 67333.65 | 0.0670 | -0.1323 | 0/7/10 | 0 | 0 | 0 | - |
| 11:10 | 12:40 | TREND_UP | 0.8500 | sma_trend_v1 | 67760.05 | 0.4615 | -0.0393 | 0/9/9 | 9 | 1 | 1 | NRR-027 x1, NRR-029 x1 |
| 12:40 | 12:50 | TREND_UP | 0.8489 | volatility_v2(raw LOW_VOL) | 67510.85 | 0.0213 | -0.0140 | 0/2/0 | 2 | 0 | 0 | - |
| 12:50 | 15:20 | LOW_VOLATILITY | 0.4283 | volatility_v2 | 67533.55 | 0.1255 | -0.1461 | 0/14/16 | 0 | 0 | 0 | - |
| 15:20 | 15:35 | UNCERTAIN | 0.1500 | uncertain_cutoff_gate | 67865.85 | 0.1643 | 0.0403 | 0/0/3 | 0 | 0 | 0 | - |
| 15:35 | 17:00 | LOW_VOLATILITY | 0.2299 | volatility_v2 | 67887.95 | 0.0326 | -0.0852 | 0/9/8 | 0 | 0 | 0 | - |
| 17:00 | open | UNCERTAIN | 0.1500 | sma_trend_v1 | 67490.05 | -0.2712 | 0.2370 | 0/0/14 | 0 | 0 | 0 | - |

### BTCUSDT Regime Identification Verdict

PARTIALLY_CORRECT.

Why:

- TREND_UP transitions at 07:10 and 11:10 had clear positive price context before transition.
- The 03:05 TREND_DOWN label was weak evidence: confidence was only 0.2379 and price rose 1.7318% over the next 15 minutes.
- Non-directional regimes were plausible but not independently proven beyond in-repo price behavior.

## Regime Timeline And Segment Reaction: ETHUSDT

| Start | End | Regime | Conf | Model | Px | 15m Before % | 15m After % | Trace B/S/N | Wrong-Side Traces | Accepted Wrong-Side | Wrong-Side Fills | Reject Families |
|---|---|---|---:|---|---:|---:|---:|---|---:|---:|---:|---|
| 00:20 | 02:00 | MEAN_REVERSION | 0.4931 | mean_reversion_v2 | 2000.985 | -0.0759 | 0.2086 | 0/11/9 | 0 | 0 | 0 | NRR-026 x5 |
| 02:00 | 02:50 | HIGH_VOLATILITY | 0.8500 | volatility_v2 | 1971.905 | 0.3131 | 0.6697 | 0/3/7 | 0 | 0 | 0 | NRR-027 x1, NRR-026 x1 |
| 02:50 | 03:30 | UNCERTAIN | 0.1500 | uncertain_cutoff_gate | 1981.355 | -0.0076 | -0.0876 | 0/3/5 | 0 | 0 | 0 | - |
| 03:30 | 04:25 | HIGH_VOLATILITY | 0.8500 | volatility_v2 | 2006.655 | 1.2182 | -0.4458 | 0/8/3 | 0 | 0 | 0 | NRR-027 x2 |
| 04:25 | 06:20 | UNCERTAIN | 0.1500 | sma_trend_v1 | 2002.335 | 0.1250 | 0.3548 | 0/7/16 | 0 | 0 | 0 | - |
| 06:20 | 09:00 | TREND_UP | 0.3049 | sma_trend_v1 | 2032.645 | 0.2505 | 0.1655 | 0/13/19 | 13 | 1 | 1 | NRR-026 x3, NRR-027 x3, NRR-029 x2 |
| 09:00 | 11:00 | LOW_VOLATILITY | 0.3187 | volatility_v2 | 2046.825 | -0.1371 | -0.1131 | 0/11/13 | 0 | 0 | 0 | - |
| 11:00 | 12:30 | TREND_UP | 0.8500 | sma_trend_v1 | 2058.685 | 0.7660 | 0.1858 | 0/10/8 | 10 | 0 | 0 | - |
| 12:30 | 12:40 | LOW_VOLATILITY | 0.3705 | volatility_v2 | 2055.535 | -0.1389 | -0.0404 | 0/0/2 | 0 | 0 | 0 | - |
| 12:40 | 17:10 | LOW_VOLATILITY | 0.4262 | volatility_v2 | 2056.505 | 0.0246 | -0.1019 | 0/22/32 | 0 | 0 | 0 | NRR-026 x1, NRR-027 x4, NRR-029 x1, NRR-030 x2 |
| 17:10 | open | UNCERTAIN | 0.1500 | sma_trend_v1 | 2064.955 | -0.0358 | -0.3189 | 0/5/7 | 0 | 0 | 0 | - |

### ETHUSDT Regime Identification Verdict

CORRECT.

Why:

- TREND_UP at 06:20 and 11:00 both had positive 15-minute context before and after transition.
- No contradictory TREND_DOWN episode had to be defended today.
- Non-directional LOW_VOL/HIGH_VOL transitions were consistent with flatter or noisier local price structure and do not conflict with the directional verdict.

## Direct Reaction Facts

### BTCUSDT

- In TREND_UP, Aurora still generated SELL 25 times and BUY 0 times.
- In TREND_DOWN, Aurora generated BUY 0 times and SELL 1 time.
- Processing signal count today: SELL 68, BUY 0.
- Trade intent proposed count today: SELL 10, BUY 0.
- Representative live trace: at 08:40 Aurora emitted score = -0.134531 with side = sell and thresholds only 0.01620 / 0.01620.
- Representative live trace: at 11:30 Aurora emitted score = -0.142962 with side = sell and thresholds only 0.01620 / 0.01620.

### ETHUSDT

- In TREND_UP, Aurora still generated SELL 23 times and BUY 0 times.
- ETHUSDT had no TREND_DOWN segment today.
- Processing signal count today: SELL 72, BUY 0.
- Trade intent proposed count today: SELL 5, BUY 0.
- Representative live trace: at 07:35 Aurora emitted score = -0.151109 with side = sell and thresholds only 0.02210 / 0.02210.

## Suspicious Episode Classification

### BTCUSDT

| Time | Regime | Side | Category | Reason |
|---|---|---|---|---|
| 07:10 | TREND_UP | SELL | REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED | NRR-026 regime_confidence 0.2895 < 0.42 |
| 07:25 | TREND_UP | SELL | REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED | NRR-026 regime_confidence 0.3529 < 0.42 |
| 07:30 | TREND_UP | SELL | REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED | NRR-026 regime_confidence 0.3708 < 0.42 |
| 07:50 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |
| 07:55 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |
| 08:00 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |
| 08:20 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-030 bleed up blocks short |
| 08:40 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |
| 08:55 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |
| 09:10 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |
| 09:15 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |
| 09:20 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-029 flash up blocks short |
| 09:40 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |
| 11:15 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |
| 11:20 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-029 flash up blocks short |
| 11:30 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |

Category counts:

- REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED: 3
- REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD: 7
- REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED: 6
- REGIME_WRONG_REACTION_IRRELEVANT: 0 proven at order layer

### ETHUSDT

| Time | Regime | Side | Category | Reason |
|---|---|---|---|---|
| 06:20 | TREND_UP | SELL | REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED | NRR-026 regime_confidence 0.3049 < 0.42 |
| 06:25 | TREND_UP | SELL | REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED | NRR-026 regime_confidence 0.3407 < 0.42 |
| 06:35 | TREND_UP | SELL | REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED | NRR-026 regime_confidence 0.4174 < 0.42 |
| 06:50 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-029 flash up blocks short |
| 07:10 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |
| 07:15 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-029 flash up blocks short |
| 07:20 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |
| 07:35 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED | DecisionMaking ORDER_INTENT accepted |
| 07:50 | TREND_UP | SELL | REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD | NRR-027 uptrend blocks short |

Category counts:

- REGIME_CORRECT_BUT_LOW_CONFIDENCE_FAIL_CLOSED: 3
- REGIME_CORRECT_BUT_WRONG_SIDE_BLOCKED_BY_GUARD: 5
- REGIME_CORRECT_BUT_WRONG_SIDE_ACCEPTED: 1

## Guard-Family Audit

### Overall reject-family counts

| Symbol | NRR-026 low confidence | NRR-027 uptrend/downtrend directional sanity | NRR-029 flash motion | NRR-030 bleed motion | Downtrend blocks long |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 7 | 6 | 2 | 1 | 0 |
| ETHUSDT | 10 | 10 | 3 | 2 | 0 |

### Per-regime reject-family breakdown

#### BTCUSDT

- HIGH_VOLATILITY: NRR-027 x2, NRR-026 x2
- MEAN_REVERSION: NRR-026 x2
- TREND_UP: NRR-026 x3, NRR-027 x4, NRR-029 x2, NRR-030 x1

#### ETHUSDT

- MEAN_REVERSION: NRR-026 x5
- HIGH_VOLATILITY: NRR-027 x3, NRR-026 x1
- TREND_UP: NRR-026 x3, NRR-027 x3, NRR-029 x2
- LOW_VOLATILITY: NRR-026 x1, NRR-027 x4, NRR-029 x1, NRR-030 x2

### Guard-family verdict

- The guard stack is carrying part of the system today.
- The strongest proven live choke families are NRR-026 and NRR-027.
- NRR-029 and NRR-030 are live secondary brakes, not the primary brake.
- The leak is real because wrong-side SELLs in TREND_UP still reached ORDER_INTENT and sometimes FILLED.

## Order-Layer Propagation Audit

### Accepted wrong-side decisions that reached ORDER_INTENT

| Symbol | Time | RID | Regime | Side | Order Placed | Filled | Lifecycle Status |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 08:40 | aurora_BTCUSDT_1774849204443 | TREND_UP | SELL | yes | no | ORPHANED_TTL |
| BTCUSDT | 08:55 | aurora_BTCUSDT_1774850105153 | TREND_UP | SELL | no | no | REJECTED |
| BTCUSDT | 09:10 | aurora_BTCUSDT_1774851000801 | TREND_UP | SELL | yes | no | CANCELLED |
| BTCUSDT | 09:15 | aurora_BTCUSDT_1774851301557 | TREND_UP | SELL | yes | no | ORPHANED_TTL / REJECTED |
| BTCUSDT | 09:40 | aurora_BTCUSDT_1774852802488 | TREND_UP | SELL | yes | yes | ORPHANED_TTL |
| BTCUSDT | 11:30 | aurora_BTCUSDT_1774859404713 | TREND_UP | SELL | yes | yes | ORPHANED_TTL |
| ETHUSDT | 07:35 | aurora_ETHUSDT_1774845300573 | TREND_UP | SELL | yes | yes | ORPHANED_TTL |

### Propagation verdict

- Wrong-side accepted intents count: BTCUSDT 6, ETHUSDT 1.
- Wrong-side actual trades count: BTCUSDT 2, ETHUSDT 1.
- Downstream gating rejected or cancelled some accepted wrong-side intents, but not enough to make downstream gating the primary choke.
- Same-side pyramiding then stopped repeated additions after the short state already existed: BTCUSDT 42, ETHUSDT 40.

## Main Failure Location

### Detector vs Reaction Separation

- Regime detection is not the dominant failure today.
- BTCUSDT detector quality is mixed, but even where TREND_UP looked directionally plausible, Aurora still generated SELL.
- ETHUSDT detector quality is broadly acceptable, yet Aurora still generated SELL through TREND_UP.
- Therefore the main defect is not “detector wrong, reaction irrelevant.”

### Dominant choke / failure point

- Primary failure: side generation from score.
- Secondary containment: directional sanity and price-motion veto family.
- Tertiary containment: downstream execution rejects/cancels and later anti-pyramiding.

Cause:

- The scoring kernel chooses side from the sign and magnitude of score.
- In live TREND_UP windows, the score stayed strongly negative for both symbols.

Mechanism:

- BTC example: score about -0.1345 to -0.1430 while threshold was only 0.0162.
- ETH example: score about -0.1511 while threshold was only 0.0221.
- Those margins are far beyond the threshold, so small threshold nudges are unlikely to change side generation.

Effect:

- Countertrend short generation persisted in uptrend regimes.
- Guard families blocked some of those shorts but leaked others.
- Real wrong-side fills occurred.

Operational risk:

- High. Wrong-side directional trades were not just theoretical decisions; they became live fills.

## Manual Recalibration Candidate Extraction

### Evidence-supported candidates only

1. domains.decision_making.directional_sanity.min_regime_confidence

- Why candidate: it already fail-closed early TREND_UP wrong-side SELLs for both symbols.
- Symptom addressed: early low-confidence trend labels still producing contrarian side attempts.
- Evidence: BTC TREND_UP NRR-026 x3; ETH TREND_UP NRR-026 x3.
- Expected effect: fewer early-transition wrong-side attempts reach deeper guard stack.
- Operational risk: valid early trend entries will be delayed or blocked.
- Changes: wrong-side blocking only.

2. domains.decision_making.directional_sanity.hard_veto_consecutive_bars

- Why candidate: NRR-027 is already a live and effective family but still leaked accepted wrong-side trades after some intervals.
- Symptom addressed: confirmed uptrend still allowing countertrend shorts before directional veto hardens.
- Evidence: BTC TREND_UP NRR-027 x4 with 6 accepted wrong-side intents still leaking; ETH TREND_UP NRR-027 x3 with 1 accepted wrong-side fill.
- Expected effect: earlier hard countertrend veto in confirmed directional regimes.
- Operational risk: more overblocking in choppy one-bar reversals and some loss of optionality in high-volatility pullback entries.
- Changes: wrong-side blocking only.

3. domains.decision_making.price_motion_sanity.flash_threshold_norm and bleed_threshold_norm

- Why candidate: NRR-029 and NRR-030 are already live and specifically block shorting into upward motion.
- Symptom addressed: late-stage up-impulse shorts that escape directional sanity.
- Evidence: BTC TREND_UP NRR-029 x2 and NRR-030 x1; ETH TREND_UP NRR-029 x2.
- Expected effect: stronger anti-FOMO protection against shorting into continuing upward motion.
- Operational risk: broader suppression across more regimes and more sensitivity to noisy motion bursts.
- Changes: wrong-side blocking only.

### Not justified today

- Global decision.regime_threshold_multipliers for BTCUSDT and ETHUSDT.

Why not justified:

- These two symbols already use per-symbol regime_thresholds first, so global multipliers are not the live first-order control path for them.

- Threshold-first tuning.

Why not justified:

- The observed negative scores are roughly 6x to 9x larger than the active thresholds in the suspicious TREND_UP windows.
- That means small threshold tuning is unlikely to change behavior, while large threshold moves would be broad, non-narrow, and hard to defend from one-day evidence.

## Safe Manual Recalibration Proposal

### SAFE_CANDIDATE_1

- Exact field: domains.decision_making.directional_sanity.min_regime_confidence
- Current value: 0.42
- Suggested test value: 0.45 to 0.50
- Expected behavioral effect: trims low-confidence early TREND_UP contrarian shorts before they reach deeper guard logic.
- BTC control-path risk: can delay early valid BTC trend participation if confidence ramps slowly.
- ETH risk: can delay valid ETH trend participation near fresh transitions.
- Why safer than blind threshold reduction: it touches only already low-confidence episodes that are already being rejected today.

### SAFE_CANDIDATE_2

- Exact field: domains.decision_making.directional_sanity.hard_veto_consecutive_bars
- Current value: 2
- Suggested test value: 1
- Expected behavioral effect: converts directional sanity from delayed hard veto to earlier hard veto, especially for repeated TREND_UP short attempts.
- BTC control-path risk: may overblock some legitimate BTC pullback shorts in noisy trend regimes.
- ETH risk: may overblock some ETH high-volatility fades when trend signals flicker.
- Why safer than blind threshold reduction: it only strengthens a guard family that is already proven to be live and semantically aligned with the bad episodes.

### RISKIER_CANDIDATE_3

- Exact field: domains.decision_making.price_motion_sanity.flash_threshold_norm and/or bleed_threshold_norm
- Current value: flash 1.0, bleed 0.5
- Suggested test value or range: flash 0.85 to 0.90, bleed 0.40 to 0.45
- Expected behavioral effect: more wrong-side short attempts are blocked during upward impulse continuation.
- BTC control-path risk: more BTC entries may be suppressed in fast but tradable pullback windows.
- ETH risk: more ETH entries may be suppressed during noisy continuation and rebound phases.
- Why safer than blind threshold reduction: it only tightens live anti-FOMO brakes instead of re-centering the core score-emergence geometry.

## Final Decision

### BTCUSDT

- Regime identification verdict: PARTIALLY_CORRECT
- Reaction verdict: TOO_CONTRARIAN
- Root cause class: SIDE_GENERATION_PROBLEM

### ETHUSDT

- Regime identification verdict: CORRECT
- Reaction verdict: TOO_CONTRARIAN
- Root cause class: SIDE_GENERATION_PROBLEM

### Overall recommendation

CALIBRATE_DIRECTIONAL_GUARDS_FIRST

Why:

- The safest live levers today are guard-side, not score-side.
- Regime detection is not the dominant choke.
- Threshold-first tuning is not narrow enough for the score/threshold gap shown by today’s traces.

## Concise REPORT

- Files used: domain_regime_detector, domain_feature_engineering, domain_decision_making, aurora_core, order_log_v1, aurora_trades, aurora_events, trade_lifecycle, aurora.yaml, domains.yaml, and the active decision/safety code.
- Today-only symbol verdicts:
  - BTCUSDT: regime PARTIALLY_CORRECT, reaction TOO_CONTRARIAN, dominant failure SIDE_GENERATION_PROBLEM.
  - ETHUSDT: regime CORRECT, reaction TOO_CONTRARIAN, dominant failure SIDE_GENERATION_PROBLEM.
- Dominant choke families:
  - Early fail-closed: NRR-026.
  - Main directional guard: NRR-027.
  - Secondary anti-FOMO guard: NRR-029 / NRR-030.
  - Not primary choke: downstream execution-only rejects and later anti-pyramiding.
- Safe calibration candidates:
  - Raise min_regime_confidence slightly.
  - Harden hard_veto_consecutive_bars.
  - Tighten price-motion flash/bleed thresholds only as the riskier third step.
- What remains unproven:
  - Exact feature-level cause of the negative scores.
  - Whether a code-level side-generation correction is required beyond manual guard recalibration.
  - Actual economic PnL effect of each accepted wrong-side trade.
