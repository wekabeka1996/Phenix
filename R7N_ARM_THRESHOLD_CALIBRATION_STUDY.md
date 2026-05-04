# R7N Peak-Giveback Arm Threshold Calibration Study

## Problem Framing
R7M established that the current fixed `edge_arm_usd=25.0` threshold is too high for the observed runtime sizing and hold profile. R7N evaluates whether alternate arming families would have been reached in the same runtime slice, using existing runtime evidence only and no config or logic changes.

## FACTS
- Filled non-flat lifecycles in the evidence set: `7`.
- Conservative counterfactual scan rule: a candidate arm must occur before the first `peak_giveback_suppressed_close_in_progress` marker for that lifecycle, or before the actual close if no suppression marker appears. This avoids crediting a threshold that only appears after Sidecar is already out of the game.
- Observed current-edge maxima by lifecycle: BTCUSDT reached `2.99 USDT` on one lifecycle; the other positive maxima were `1.08 USDT`, `0.87 USDT`, and `0.68 USDT`. ETHUSDT stayed at `0` and XRPUSDT stayed negative.
- No candidate in the scan produced a 50% giveback trigger before close suppression or actual close.
- Best ROI-like excursion in the slice was about `2.34%` of margin on the BTCUSDT 2.99-USDT lifecycle; the BTCUSDT 0.87-USDT lifecycle reached about `0.68%` of margin.

## UNKNOWNS
- Only seven filled lifecycles are available; this is enough to rank families, but not enough to set a live threshold with confidence.
- The runtime evidence does not prove what would happen under a broader regime regime mix, a longer hold profile, or a different position-sizing mix.
- No counterfactual run was executed in live code; the trigger analysis is reconstructed from observed snapshot rows.

## ASSUMPTIONS
- Open quantity and entry price are derived from the final cumulative `PositionTracking` state in `EVT:TRADE_EXECUTED` rows.
- `max_edge_pct_notional` is computed as `max_edge_usd / notional_usdt * 100`, matching the percent-style economics already used by the runtime artifacts.
- `ROI-like` means edge relative to estimated margin, using the configured leverage target per symbol as a proxy for margin normalization.
- Hybrid models are evaluated as simple counterfactual families only; no live config implication is intended.

## Lifecycle Distribution
| rid | symbol | notional USDT | qty | entry price | hold s | max edge USDT | max edge % notional | max unrealized PnL % | realized net PnL | close reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| aurora_ETHUSDT_1777761604540 | ETHUSDT | 3716.0811 | 1.601 | 2321.1 | 51.078 | 0 | 0 | 0 | -0.74321622 | POSITION_CLOSED_DETECTED |
| aurora_ETHUSDT_1777765204919 | ETHUSDT | 3712.50684 | 1.602 | 2317.42 | 45.174 | 0 | 0 | 0 | -0.742501 | POSITION_CLOSED_DETECTED |
| aurora_BTCUSDT_1777767904005 | BTCUSDT | 4476.5406 | 0.057 | 78535.8 | 27.706 | 2.99 | 0.0668 | 0.07 | -0.89530812 | POSITION_CLOSED_DETECTED |
| aurora_BNBUSDT_1777770303223 | BNBUSDT | 3989.373 | 6.46 | 617.55 | 11.533 | 1.08 | 0.0271 | 0.03 | -0.7978746 | POSITION_CLOSED_DETECTED |
| aurora_BNBUSDT_1777770905993 | BNBUSDT | 3985.6262 | 6.46 | 616.97 | 45.336 | 0.68 | 0.0171 | 0.03 | -0.79712524 | POSITION_CLOSED_DETECTED |
| aurora_BTCUSDT_1777781104422 | BTCUSDT | 4455.7299 | 0.057 | 78170.7 | 32.371 | 0.87 | 0.0195 | 0.04 | -0.89114596 | POSITION_CLOSED_DETECTED |
| aurora_XRPUSDT_1777781405671 | XRPUSDT | 7387.82968 | 5347.3 | 1.3816 | 12.768 | -1.34 | -0.0181 | -0.02 | -1.47756593 | POSITION_CLOSED_DETECTED |

## Fixed USD Analysis
- Fixed arms of `1` and `2 USDT` would only have armed the BTCUSDT `1777767904005` lifecycle before suppression; `3 USDT` and above did not arm any lifecycle in the conservative scan.
- `25 USDT` is still out of reach, consistent with R7M.
- Even the lower fixed arms did not produce a 50% giveback trigger before suppression or close.

## Percent-Of-Notional Analysis
- `0.02%` and `0.05%` of notional both behave like the BTCUSDT-only arming band in this slice; they arm the same BTCUSDT lifecycle(s) that the fixed `1` and `2 USDT` bands do, but they do so with proper scale normalization.
- `0.07%` and above did not arm any lifecycle.
- The notional-normalized view is the stronger structural fit: it preserves the same observed ordering while removing the need to carry an arbitrary fixed-dollar arm across symbols.

## ROI-Like Feasibility Analysis
- Margin-normalized arming is feasible only at very low levels in this slice.
- `0.5% of margin` arms the BTCUSDT `1777767904005` lifecycle and the BTCUSDT `1777781104422` lifecycle, but still produces no 50% giveback trigger before suppression or close.
- The BTCUSDT `1777781104422` lifecycle gets closest to a trigger under this family, with a `46.97%` drawdown from its post-arm peak, but it still stops short of the configured `50%` giveback trigger.
- `1.0% of margin` arms only the stronger BTCUSDT lifecycle; `2.0%` and `5.0%` arm nothing.

## Hybrid Threshold Analysis
- The two representative hybrid families collapse to the same practical conclusion on this slice: the only useful arming behavior comes from the BTCUSDT lifecycles, and neither hybrid produces a 50% giveback trigger.
- `max(1 USDT, 0.02% notional)` is effectively a BTCUSDT-only arm here.
- `min(2 USDT, 0.05% notional)` collapses to the `0.05%` notional band on this slice.

## Symbol-Specific Findings
- `ETHUSDT`: both lifecycles stayed at zero or negative edge before suppression; no candidate family rescues them.
- `BTCUSDT`: the only symbol that clearly reaches positive edge early enough to arm under permissive families; one lifecycle reached `2.39 USDT` before suppression and the other reached `0.87 USDT` before suppression.
- `BNBUSDT`: positive edge exists in the full runtime slice, but the favorable move arrives too late for a conservative pre-suppression arm on the first lifecycle and remains modest on the second.
- `XRPUSDT`: stayed negative; it is market-quiet or too-short-lived for any arm family in this slice.
- The fixed-dollar model is therefore structurally inferior to percent-of-notional or ROI-like normalization, but the evidence is still too small to justify a live change.

## Candidate Summary
| model | armed life. | trigger life. | helped | harmed | unknown | first arm example | peak after arm | max giveback after arm |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| fixed_usd_1 | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:16.582 +03:00 | 2.39 | 0 |
| fixed_usd_2 | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:18.185 +03:00 | 2.39 | 0 |
| fixed_usd_3 | 0 | 0 | 0 | 0 | 0 |   |  |  |
| fixed_usd_5 | 0 | 0 | 0 | 0 | 0 |   |  |  |
| fixed_usd_10 | 0 | 0 | 0 | 0 | 0 |   |  |  |
| fixed_usd_25 | 0 | 0 | 0 | 0 | 0 |   |  |  |
| pct_notional_0.02pct | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:16.582 +03:00 | 2.39 | 0 |
| pct_notional_0.05pct | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:18.185 +03:00 | 2.39 | 0 |
| pct_notional_0.07pct | 0 | 0 | 0 | 0 | 0 |   |  |  |
| pct_notional_0.10pct | 0 | 0 | 0 | 0 | 0 |   |  |  |
| pct_notional_0.15pct | 0 | 0 | 0 | 0 | 0 |   |  |  |
| pct_notional_0.25pct | 0 | 0 | 0 | 0 | 0 |   |  |  |
| roi_margin_0.5pct | 2 | 0 | 0 | 0 | 2 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:16.582 +03:00 | 2.39 | 46.97 |
| roi_margin_1.0pct | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:16.582 +03:00 | 2.39 | 0 |
| roi_margin_2.0pct | 0 | 0 | 0 | 0 | 0 |   |  |  |
| roi_margin_5.0pct | 0 | 0 | 0 | 0 | 0 |   |  |  |
| hybrid_max_1usd_0.02pct | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:16.582 +03:00 | 2.39 | 0 |
| hybrid_min_2usd_0.05pct | 1 | 0 | 0 | 0 | 1 | aurora_BTCUSDT_1777767904005 2026-05-03 03:25:18.185 +03:00 | 2.39 | 0 |

## Inferences
- No evaluated candidate family produces a useful giveback-cap trigger in this slice.
- The better next telemetry family is a shadow percent-of-notional arm, because it is scale-normalized, matches the observed ordering, and avoids hard-coding a dollar arm that remains too high for the current runtime profile.
- ROI-like shadow telemetry is also feasible, but it is a second-order refinement rather than the first thing to add.

## Recommendation
Add shadow percent-of-notional arm telemetry first. Keep live policy unchanged.

`ADD_SHADOW_PERCENT_NOTIONAL_ARM`
