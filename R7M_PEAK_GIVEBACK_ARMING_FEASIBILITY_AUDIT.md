# R7M Peak-Giveback Arming Feasibility Audit

## Problem Framing
R7L proved that live non-flat economics now flow into Sidecar after R7K enabled market-tick subscription. R7M asks a narrower question: whether the live `edge_arm_usd=25.0` arm is feasible under the current filled-position distribution, hold durations, symbols, and leverage targets, without changing config or logic.

## Observation Window
- Reused the post-R7K / R7L runtime slice: `2026-05-03 00:01:30.703 +03:00` to `2026-05-03 10:56:19.586 +03:00`.
- The seven filled lifecycles in this slice opened between `2026-05-03 01:40:16.183 +03:00` and `2026-05-03 07:10:44.482 +03:00`, and closed between `2026-05-03 01:41:07.261 +03:00` and `2026-05-03 07:11:17.250 +03:00`.

## FACTS
- Filled lifecycles in scope: `7`.
- Non-flat Sidecar rows with `fill_correlation` for these seven lifecycles: `19131`.
- Rows with non-null `mark_price` / `unrealized_pnl_usdt` / `unrealized_pnl_pct` / `current_edge_usd`: `734` / `734` / `734` / `734`.
- `POSITION_POLICY_SIDECAR_CLOSE_REQUEST` rows: `0`. `POSITION_POLICY_SIDECAR_RECOMMENDATION` rows: `0`.
- `POSITION_CLOSED` close reason counts: `POSITION_CLOSED_DETECTED=7`.
- `peak_giveback_state` distribution across the seven lifecycles: `peak_giveback_not_ready=19124`, `peak_giveback_suppressed_close_in_progress=7`.
- No lifecycle hit `is_armed=true` or `threshold_crossed=true` in the live slice.

## INFERENCES
- Sidecar economics are reconstructable end-to-end: first economics-bearing rows show fresh portfolio snapshots, and later rows carry the live `mark_price`, `unrealized_pnl_usdt`, `unrealized_pnl_pct`, and `current_edge_usd` values.
- The trigger path is cleanly absent, not broken: the data show economics, but the economics never reached the arm threshold, so there was no recommendation or close request to emit.
- The fixed USD arm is not normalized across symbols. A 25 USDT arm equals roughly `0.34%` to `0.67%` of notional in this slice, while the best observed favorable excursion was only `2.99 USDT` (`0.07%` of notional) on BTCUSDT.
- Under the current hold durations, the best observed edge is about `12.0%` of the arm threshold, so the live 25 USDT arm is effectively out of reach in this runtime slice.
- A percent-of-notional / ROI-based arm would be more contractually aligned in principle, but this package does not validate a live change; it only shows that the current fixed-dollar arm is too high for the observed runtime profile.

## ASSUMPTIONS
- Canonical open quantity comes from the final cumulative `PositionTracking` quantity in `EVT:TRADE_EXECUTED`, not from a single partial fill row.
- The open timestamp is the first `EVT:TRADE_EXECUTED` timestamp for the lifecycle; the close timestamp is the `POSITION_CLOSED` timestamp in `order_log_v1.jsonl` / realized close row.
- `mark fresh` means the first economics-bearing Sidecar snapshot had `portfolio_fresh=true` and a recent `positions_last_ts_ms`.
- `current_edge_usd` threshold reach is counted by observed live Sidecar rows, not by extrapolation or simulation.

## UNKNOWNS
- No broader control sample exists in this package for a larger market regime, longer hold duration, or larger-size experiment.
- No config-only threshold experiment was run here, so we cannot prove what the live arming distribution would look like under a different arm value.
- The best observed BTCUSDT excursion of `2.99 USDT` is still below the arm threshold, but this slice is still only seven filled lifecycles, so the distribution is directional rather than exhaustive.

## Non-Flat Lifecycle Proof
| rid | symbol | side | quantity | entry price | notional USDT | open | close | hold s | max current edge | close reason | realized PnL net |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | --- | ---: |
| aurora_ETHUSDT_1777761604540 | ETHUSDT | SHORT | 1.601 | 2321.1 | 3716.0811 | 2026-05-03 01:40:16.183 +03:00 | 2026-05-03 01:41:07.261 +03:00 | 51.078 | 0 | POSITION_CLOSED_DETECTED | -0.74321622 |
| aurora_ETHUSDT_1777765204919 | ETHUSDT | SHORT | 1.602 | 2317.42 | 3712.50684 | 2026-05-03 02:40:26.900 +03:00 | 2026-05-03 02:41:12.074 +03:00 | 45.174 | 0 | POSITION_CLOSED_DETECTED | -0.742501 |
| aurora_BTCUSDT_1777767904005 | BTCUSDT | LONG | 0.057 | 78535.8 | 4476.5406 | 2026-05-03 03:25:07.226 +03:00 | 2026-05-03 03:25:34.932 +03:00 | 27.706 | 2.99 | POSITION_CLOSED_DETECTED | -0.89530812 |
| aurora_BNBUSDT_1777770303223 | BNBUSDT | SHORT | 6.46 | 617.55 | 3989.373 | 2026-05-03 04:06:14.649 +03:00 | 2026-05-03 04:06:26.182 +03:00 | 11.533 | 1.08 | POSITION_CLOSED_DETECTED | -0.7978746 |
| aurora_BNBUSDT_1777770905993 | BNBUSDT | SHORT | 6.46 | 616.97 | 3985.6262 | 2026-05-03 04:15:12.650 +03:00 | 2026-05-03 04:15:57.986 +03:00 | 45.336 | 0.68 | POSITION_CLOSED_DETECTED | -0.79712524 |
| aurora_BTCUSDT_1777781104422 | BTCUSDT | SHORT | 0.057 | 78170.7 | 4455.7299 | 2026-05-03 07:05:13.652 +03:00 | 2026-05-03 07:05:46.023 +03:00 | 32.371 | 0.87 | POSITION_CLOSED_DETECTED | -0.89114596 |
| aurora_XRPUSDT_1777781405671 | XRPUSDT | SHORT | 5347.3 | 1.3816 | 7387.82968 | 2026-05-03 07:10:44.482 +03:00 | 2026-05-03 07:10:57.250 +03:00 | 12.768 | -1.34 | POSITION_CLOSED_DETECTED | -1.47756593 |

## Market Tick / Mark Cache Proof
- R7L already established that `EVT:MARKET_TICK_RECEIVED` is emitted and the `PositionTracking` handler path is active.
- In this slice, the Sidecar economics rows show that live marks became available after an initial null post-fill row, then remained fresh across the open lifecycle.
- The first non-null economics-bearing snapshot per lifecycle had `portfolio_fresh=true` and `positions_last_ts_ms` close to the evaluation timestamp; non-null economics rows total `734`.
- No malformed payload evidence or fill-corruption evidence was found in the live slice used for this audit.

## Portfolio Economics Proof
- `mark_price` observed rows: `734`. `unrealized_pnl_usdt` observed rows: `734`. `unrealized_pnl_pct` observed rows: `734`.
- `positions_last_ts_ms` was present on the first economics-bearing row for every filled lifecycle, and `portfolio_fresh=true` on those rows.
- The economics rows were sparse right after fill because the first snapshot often arrived before the portfolio symbol was populated; that is a transient observability timing effect, not a broken economics path.

## Sidecar Economics Proof
- Sidecar consumed `mark_price`, `unrealized_pnl_usdt`, `unrealized_pnl_pct`, and `current_edge_usd` for the filled lifecycles once the portfolio snapshot became present.
- `peak_edge_usd` remained `0.0` everywhere because arming never happened, which is expected for the pre-arm state machine.
- The best observed current edge was `2.99 USDT` on BTCUSDT; the other positive maxima were `1.08 USDT`, `0.87 USDT`, and `0.68 USDT`.

## Peak State Distribution
- `peak_giveback_not_ready`: `19124` rows.
- `peak_giveback_suppressed_close_in_progress`: `7` rows.
- `armed`: `0`. `threshold_met`: `0`.

## Trigger / Routing / Safety
- No Sidecar recommendation or Sidecar close request rows were emitted.
- All seven filled lifecycles exited through the downstream EP-owned close path with `POSITION_CLOSED_DETECTED`.
- No duplicate close storm, no direct exchange-sidecar action, and no bracket-mutation evidence was found in the slice for this package.

## Loop / Storm Analysis
- This package did not change runtime behavior, so it does not add new loop risk.
- The live slice shows normal economics progression and terminal suppression on close, not a fan-out storm or malformed event cascade.

## Threshold Distribution
- `current_edge_usd >= 1`: `2` lifecycles, `11` snapshot rows.
- `current_edge_usd >= 2`: `1` lifecycles, `4` snapshot rows.
- `current_edge_usd >= 5`: `0` lifecycles, `0` snapshot rows.
- `current_edge_usd >= 10`: `0` lifecycles, `0` snapshot rows.
- `current_edge_usd >= 25`: `0` lifecycles, `0` snapshot rows.

## Final Verdict
The live economics path is healthy, but the fixed `25 USDT` arm is not feasible under the current observed sizing and hold profile. No trigger was expected, and no trigger occurred.

`FIXED_25_USD_TOO_HIGH_FOR_CURRENT_SIZING`
