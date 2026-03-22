# AGENT_REPORT_V1

## Executive Summary
ETHUSDT and SOLUSDT are not being eliminated before Aurora scoring. They reach the live Quadratic kernel, produce non-deferred results, but the result side remains empty, which triggers the neutral early return in Aurora before _emit_signal. BTCUSDT sometimes passes because its effective sell threshold in TREND_DOWN is materially lower than ETH/SOL, so comparable negative scores cross threshold for BTC but not for ETH/SOL.

## Proven Facts
- Scope: this report is limited to Aurora pre-signal branch behavior for BTCUSDT, ETHUSDT, and SOLUSDT on the observed runtime/log set from 2026-03-20.
- Aurora command routing contains pre-decision gates in [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L706) through [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L793), including wrong-timeframe silent skip at [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L763).
- Aurora symbol enablement is checked before strategy processing via [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L838) and asset fallback at [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py#L860).
- The live Aurora path emits kernel diagnostics before any signal emission at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L498), [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L529), and only handles deferred outputs afterward at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L543).
- The decisive pre-signal neutral return is at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L751). If effective_side is empty, Aurora returns before reentry cooldown, vol gates, anchor veto, execution gate, and _emit_signal.
- Quadratic side selection returns neutral when score does not cross threshold in flat state at [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L353) through [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py#L385).
- ETHUSDT and SOLUSDT per-symbol signal threshold override is 0.09 at [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L514) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L516) and [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L633) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L635).
- ETHUSDT and SOLUSDT regime_thresholds do not define TREND_DOWN and therefore rely on DEFAULT=1.0 at [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L458) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L462) and [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L576) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L580).
- BTCUSDT has per-symbol regime_thresholds with TREND_DOWN=0.1 and UNCERTAIN=99.0 at [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L702) through [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L708), while BTC signal_threshold override is disabled at [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L758).
- Quadratic threshold math is base_threshold times regime factor, then hysteresis, per [config/docs/aurora_math_passport.md](config/docs/aurora_math_passport.md#L205) and [config/docs/aurora_math_passport.md](config/docs/aurora_math_passport.md#L206). Missing DEFAULT would fail-close the kernel, per [config/docs/aurora_math_passport.md](config/docs/aurora_math_passport.md#L165).
- Runtime log evidence from rotated logs shows:
  - ETHUSDT: SIGNALS=0, NONEMPTY_SIDE=0, NEUTRAL_SIDE=75.
  - SOLUSDT: SIGNALS=0, NONEMPTY_SIDE=0, NEUTRAL_SIDE=75.
  - BTCUSDT: SIGNALS=15, NONEMPTY_SIDE=17, NEUTRAL_SIDE=58.
- Runtime examples from logs:
  - ETHUSDT 22:15 aurora_core.log shows QUADRATIC_DECISION_TRACE score=-0.024893 side= deferred=False regime=MEAN_REVERSION and KERNEL_DIAG thr_buy=0.09450 thr_sell=0.09450.
  - SOLUSDT 21:10 aurora_core.log.1 shows QUADRATIC_DECISION_TRACE score=-0.039978 side= deferred=False regime=TREND_DOWN and KERNEL_DIAG thr_buy=0.0900 thr_sell=0.0900.
  - BTCUSDT 21:05 aurora_core.log.1 shows QUADRATIC_DECISION_TRACE score=-0.022421 side=sell deferred=False regime=TREND_DOWN, KERNEL_DIAG thr_buy=0.01620 thr_sell=0.01620, then SIGNAL: SELL.
- For ETH/SOL, targeted log search found no SIGNAL, no side=buy, no side=sell, no Kernel deferred, no REENTRY_COOLDOWN, no GATE_ANTI_FLAT_SIGMA, no GATE_ANTI_FOMO_SIGMA, and no ANCHOR SHOCK VETO in aurora_handler logs for the sampled rotated aurora_core set.

## Inferred Findings
- The dominant suppressor for ETHUSDT and SOLUSDT in the sampled runtime is not a routing skip and not a kernel deferral. It is the post-kernel neutral branch caused by score magnitude failing to cross sell threshold.
- The strongest differential mechanism versus BTCUSDT is threshold geometry, not downstream execution behavior:
  - BTC TREND_DOWN threshold resolves to 0.162 x 0.1 = 0.0162.
  - ETH TREND_DOWN resolves to 0.09 x DEFAULT 1.0 = 0.09.
  - SOL TREND_DOWN resolves to 0.09 x DEFAULT 1.0 = 0.09.
- Because observed ETH/SOL negative scores such as -0.0249, -0.0331, -0.03998 remain above -0.09, `_determine_side` returns neutral and Aurora exits via `if not effective_side`.
- BTC sometimes reaches SIGNAL because observed BTC scores around -0.022 to -0.025 are below -0.0162 in TREND_DOWN, producing side=sell and allowing signal emission.
- ETH/SOL silence therefore appears to be intended runtime selectivity under current thresholds, not evidence of missing evaluator invocation.

## Contradictions / Evidence Gaps
- Previous lower-bound evidence suggested ETH/SOL may disappear before Aurora evaluator logging. That is contradicted by current rotated aurora_core evidence showing repeated ETH/SOL QUADRATIC_DECISION_TRACE and KERNEL_DIAG lines.
- The report cannot prove project-wide or multi-day truth. It only proves the observed branch behavior in the inspected log window.
- There is still an observability gap: neutral returns have kernel trace logs but no explicit STRATEGY_DECISION_BLOCKED or neutral-reason event. That makes neutral suppression easy to miss operationally.
- I did not prove whether older or pruned logs contain rare ETH/SOL non-neutral signals outside the inspected rotated aurora_core set.

## Root Cause Candidates
1. Proven leading mechanism: post-kernel neutral early return at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L751).
Cause: effective_side is empty because `_determine_side` does not cross threshold.
Mechanism: ETH/SOL scores are non-deferred but remain inside neutral band.
Effect: Aurora returns before `_emit_signal`.
Risk: Observability gap and symbol starvation.

2. Strong contributing factor: ETH/SOL threshold geometry is materially stricter than BTC in TREND_DOWN.
Cause: ETH/SOL use per-symbol signal_threshold 0.09 with no TREND_DOWN override, so DEFAULT 1.0 applies.
Mechanism: sell threshold remains 0.09 or 0.0945 while BTC TREND_DOWN sell threshold is 0.0162.
Effect: BTC crosses sell threshold with similar score magnitudes while ETH/SOL do not.
Risk: Runtime selectivity may be much harsher than intended for ETH/SOL/SOL-like symbols.

3. Contributing contract risk: per-strategy decision.regime_thresholds is declared but not used, per [config/docs/aurora_math_passport.md](config/docs/aurora_math_passport.md#L175).
Cause: config surface contains fields that look authoritative but are not in live math routing.
Mechanism: operator may tune the wrong config block and misattribute behavior.
Effect: slower diagnosis and false tuning assumptions.
Risk: Observability and configuration-governance risk, not the direct suppressor proven here.

4. Rejected candidate for sampled logs: reentry cooldown.
Why rejected: it only runs after effective_side is non-empty at [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L764), and no ETH/SOL non-empty sides were observed.

5. Rejected candidate for sampled logs: anti-flat / anti-FOMO gates.
Why rejected: vol gates only apply to entry proposals with non-empty side at [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py#L84) through [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py#L106), and no ETH/SOL non-empty sides were observed.

6. Rejected candidate for sampled logs: kernel deferred or readiness fail-close.
Why rejected: ETH/SOL runtime traces repeatedly show deferred=False and targeted search found no kernel-deferred lines in the inspected log set.

## Operational Risk
- Runtime
- Observability Gap

## Files / Areas Touched
- [reports/REPORT_AURORA_ETH_SOL_PRESIGNAL_BRANCH_FORENSIC.md](reports/REPORT_AURORA_ETH_SOL_PRESIGNAL_BRANCH_FORENSIC.md)

## Validation Performed
- Read Aurora routing and decision code in:
  - [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py)
  - [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py)
  - [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py)
  - [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py)
  - [apps/reference/domains/decision_making/aurora_holding_period.py](apps/reference/domains/decision_making/aurora_holding_period.py)
- Read Aurora config and passport in:
  - [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml)
  - [config/docs/aurora_math_passport.md](config/docs/aurora_math_passport.md)
- Queried rotated logs for BTCUSDT, ETHUSDT, SOLUSDT across logs/aurora_core.log*.
- Verified ETH/SOL repeated kernel traces with deferred=False and empty side.
- Verified BTC control-path cases with side=sell followed by SIGNAL and downstream TRADE_INTENT processing.

## Residual Risk
- This report proves the sampled branch mechanism, but not whether ETH/SOL are globally over-filtered across all days or only under this market regime mix.
- If ETH/SOL are intended to trade more frequently, the live issue may be strategy tuning rather than code defect. That intent is not provable from current evidence alone.
- Neutral-return observability remains weaker than blocked-return observability, so future silent starvation can recur without a first-class blocked event.

## What Remains Unproven
- Whether ETH/SOL ever produce valid non-neutral Aurora signals outside the inspected rotated aurora_core files.
- Whether the stricter ETH/SOL threshold geometry is deliberate production policy or stale tuning drift.
- Whether any earlier branch sometimes suppresses ETH/SOL on other days before kernel entry.

## Minimal Safe Verdict
The strongest justified conclusion is narrow: in the inspected runtime, ETHUSDT and SOLUSDT are not dying before Aurora evaluation. They reach Quadratic scoring, return non-deferred but neutral results, and are suppressed by the `if not effective_side` branch before `_emit_signal`. BTCUSDT sometimes passes because its effective TREND_DOWN threshold is much lower, allowing similar negative scores to produce `side=sell` and reach SIGNAL.

## Scope and Evidence
- Runtime evidence sources:
  - logs/aurora_core.log
  - logs/aurora_core.log.1
  - logs/aurora_core.log.2
  - logs/aurora_core.log.3
  - logs/aurora_core.log.4
  - logs/aurora_core.log.5
- Code evidence sources:
  - [apps/reference/domains/decision_making/aurora_handler.py](apps/reference/domains/decision_making/aurora_handler.py)
  - [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py)
  - [apps/reference/domains/decision_making/quadratic_scoring_kernel.py](apps/reference/domains/decision_making/quadratic_scoring_kernel.py)
  - [apps/reference/domains/decision_making/aurora_scoring_helpers.py](apps/reference/domains/decision_making/aurora_scoring_helpers.py)
- Config evidence sources:
  - [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml)
  - [config/docs/aurora_math_passport.md](config/docs/aurora_math_passport.md)

## Runtime Branch Inventory

| branch_id | Location | Condition | Effect before `_emit_signal` | Observable? | Silent? | ETH/SOL fit? |
| --- | --- | --- | --- | --- | --- | --- |
| B01 | aurora_handler.on_process_strategy | missing symbol | return | no | yes | unproven |
| B02 | aurora_handler.on_process_strategy | global disabled | reject | yes | no | not seen |
| B03 | aurora_handler.on_process_strategy | tf_sec missing/zero | reject | yes | no | not seen |
| B04 | aurora_handler.on_process_strategy | wrong timeframe | return | weak | yes | possible in general, not seen in sampled kernel traces |
| B05 | aurora_handler.on_process_strategy | missing bar_close_ts | reject | yes | no | not seen |
| B06 | aurora_decision._process_decision | symbol disabled | return | weak | yes | contradicted by kernel traces |
| B07 | aurora_decision._process_decision | missing instrument config | return | weak | yes | contradicted by per-symbol thresholds in runtime logs |
| B08 | aurora_decision._process_decision | regime liveness/readiness/cold-start | blocked/reject | yes | no | not seen in sampled ETH/SOL traces |
| B09 | aurora_decision._process_decision | missing price | return | weak | yes | not seen |
| B10 | aurora_decision._process_decision | liquidity gate fail | blocked | yes | no | not seen |
| B11 | aurora_decision._process_decision | kernel crash | blocked | yes | no | not seen |
| B12 | aurora_decision._process_decision | `result.deferred` | blocked | yes | no | not seen |
| B13 | aurora_decision._process_decision | strict regime allowlist | blocked | yes | no | not seen |
| B14 | aurora_decision._process_decision | regime kill-switch | blocked | yes | no | not seen |
| B15 | quadratic kernel + aurora_decision | side resolves empty | neutral return | kernel trace only | partially | yes, strongest fit |
| B16 | aurora_decision._process_decision | reentry cooldown | blocked | yes | no | excluded in sampled logs |
| B17 | aurora_scoring_helpers._apply_vol_adj_gates | anti-flat or anti-fomo | blocked | yes | no | excluded in sampled logs |
| B18 | aurora_decision._process_decision | anchor shock veto | blocked | yes | no | excluded in sampled logs |
| B19 | aurora_decision._process_decision | entry plan missing/failed | blocked | yes | no | excluded because empty side returns earlier |
| B20 | aurora_decision._process_decision | objective/execution gate | blocked | yes | no | excluded because empty side returns earlier |

## BTC Control Path
FACT
- BTCUSDT 21:05 in aurora_core.log.1 shows:
  - QUADRATIC_DECISION_TRACE score=-0.022421 side=sell deferred=False regime=TREND_DOWN.
  - KERNEL_DIAG thr_buy=0.01620 thr_sell=0.01620.
  - SIGNAL: SELL.
- This path proves BTC can traverse kernel, obtain non-empty side, bypass neutral return, and reach signal emission.

INFERENCE
- BTC control pass is explained by low TREND_DOWN threshold, not by a different routing path.

## ETH Path
FACT
- ETHUSDT repeatedly shows QUADRATIC_DECISION_TRACE with deferred=False and side empty.
- Example: 21:10 aurora_core.log.1 score=-0.033057 side= deferred=False regime=TREND_DOWN.
- Example: 22:15 aurora_core.log score=-0.024893 side= deferred=False regime=MEAN_REVERSION.
- Matching KERNEL_DIAG lines show thr_sell=0.0900 or 0.09450, both above observed score magnitude.
- No ETH SIGNAL lines were found in the inspected rotated aurora_core set.

INFERENCE
- ETH reaches the evaluator branch tree and is suppressed at neutral return because score does not cross sell threshold.

## SOL Path
FACT
- SOLUSDT repeatedly shows QUADRATIC_DECISION_TRACE with deferred=False and side empty.
- Example: 21:10 aurora_core.log.1 score=-0.039978 side= deferred=False regime=TREND_DOWN.
- Example: 22:35 aurora_core.log score=-0.028446 side= deferred=False regime=MEAN_REVERSION.
- Matching KERNEL_DIAG lines show thr_sell=0.0900.
- No SOL SIGNAL lines were found in the inspected rotated aurora_core set.

INFERENCE
- SOL reaches the evaluator branch tree and is suppressed at neutral return because score does not cross sell threshold.

## Differential Analysis
- BTC sometimes emits because threshold geometry is permissive in TREND_DOWN:
  - base 0.162 x TREND_DOWN factor 0.1 = 0.0162.
- ETH in TREND_DOWN behaves as:
  - base 0.09 x DEFAULT 1.0 = 0.09 because TREND_DOWN is absent from ETH regime_thresholds.
- SOL in TREND_DOWN behaves as:
  - base 0.09 x DEFAULT 1.0 = 0.09 because TREND_DOWN is absent from SOL regime_thresholds.
- Therefore BTC score magnitudes around -0.022 cross threshold while ETH/SOL score magnitudes around -0.025 to -0.040 remain neutral.
- Reentry cooldown, vol gates, anchor veto, entry plan, objective engine, and execution gate are downstream of non-empty side and do not explain the sampled ETH/SOL silence.

## Ranked Root Cause Candidates
1. Proven: post-kernel neutral early return due empty side.
2. Strong contributor: stricter ETH/SOL threshold geometry via signal_threshold 0.09 plus DEFAULT regime factor.
3. Contributing observability defect: no first-class neutral-return blocked event.
4. Lower-confidence governance issue: config/passport surface can mislead operators because some similarly named threshold fields are declared-but-not-used.

## Auditability Gaps
- Neutral returns are logged only through QUADRATIC_DECISION_TRACE and KERNEL_DIAG, not through STRATEGY_DECISION_BLOCKED.
- Operationally, this makes ETH/SOL appear to “go silent” even though kernel evaluation happened.
- The most localized observability fix would be an explicit neutral-return event or structured log immediately before [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L751), but no code change is made in this report.

## Proven vs Unproven
PROVEN
- ETH/SOL evaluator invocation in the inspected runtime.
- ETH/SOL non-deferred empty-side kernel results in the inspected runtime.
- BTC non-empty-side SELL results and SIGNAL emission in the inspected runtime.
- Neutral branch localization before `_emit_signal`.

UNPROVEN
- Whether ETH/SOL should be tuned to behave differently.
- Whether other time windows contain ETH/SOL side-bearing signals.
- Whether any upstream branch dominates on other days.

## Validation Evidence
- Runtime counts used in this report:
  - ETHUSDT SIGNALS=0 NONEMPTY_SIDE=0 NEUTRAL_SIDE=75.
  - SOLUSDT SIGNALS=0 NONEMPTY_SIDE=0 NEUTRAL_SIDE=75.
  - BTCUSDT SIGNALS=15 NONEMPTY_SIDE=17 NEUTRAL_SIDE=58.
- Control examples used in this report:
  - BTCUSDT 21:05 aurora_core.log.1 SIGNAL path.
  - ETHUSDT 21:10 aurora_core.log.1 neutral path.
  - SOLUSDT 21:10 aurora_core.log.1 neutral path.

## Final Verdict
The requested exact pre-signal localization is: ETHUSDT and SOLUSDT are primarily suppressed by the neutral-return branch in Aurora after Quadratic scoring, not by a pre-evaluator routing skip and not by a later execution gate. The concrete predicate is the absence of `effective_side` after `_determine_side`, which occurs because current ETH/SOL score magnitudes do not cross their effective sell threshold. BTC sometimes does cross because its TREND_DOWN threshold is far lower.
