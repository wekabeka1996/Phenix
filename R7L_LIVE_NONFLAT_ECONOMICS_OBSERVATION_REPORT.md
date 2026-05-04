# R7L Live Non-Flat Economics Observation Report

## Problem Framing

This package validates whether, after R7K enabled `position_tracking.enable_market_tick_subscription`, live non-flat position economics now flow end-to-end into Sidecar peak-giveback snapshots.

The scope is runtime proof only. No code, config, thresholds, or routing changes were made.

## Observation Window

Primary runtime window used for this report:

- 2026-05-03 00:01:30.703 +03:00 to 2026-05-03 10:56:19.586 +03:00

The evidence set also includes downstream order-log events that extend to 2026-05-03 10:55:01.991 +03:00.

## FACTS

- `PositionTracking` logs `Market tick subscription enabled for real-time unrealized PnL` in [C:/Users/user/Music/Phenix/logs/aurora_core.log.11](C:/Users/user/Music/Phenix/logs/aurora_core.log.11), and that line is the live startup proof that R7K took effect.
- The core logs contain repeated `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED` warnings across the full day slice, with 27 such warnings in [C:/Users/user/Music/Phenix/logs/aurora_core.log](C:/Users/user/Music/Phenix/logs/aurora_core.log) and 52 in [C:/Users/user/Music/Phenix/logs/aurora_core.log.1](C:/Users/user/Music/Phenix/logs/aurora_core.log.1).
- The critical journal shows active `position_tracking` export traffic: 6,959 `EVT:PORTFOLIO_STATE_UPDATED` entries and 7,311 `EVT:EXPOSURE_SUMMARY_UPDATED` entries.
- `trade_lifecycle.jsonl` contains 55,749 `position_policy_sidecar` rows.
- Of those, 746 rows are non-flat position rows with non-empty position quantity.
- 7 distinct lifecycles filled and later closed.
- 3 lifecycles never filled and timed out or canceled.
- The filled lifecycles span 4 symbols: `ETHUSDT`, `BTCUSDT`, `BNBUSDT`, and `XRPUSDT`.
- No `POSITION_POLICY_SIDECAR_CLOSE_REQUEST` rows were found.
- No Sidecar recommendation row was found.
- No malformed payload evidence was found in the current slice.

## INFERENCES

- Because the filled lifecycles export non-null `mark_price`, `unrealized_pnl_usdt`, `unrealized_pnl_pct`, `current_edge_usd`, and `positions_last_ts_ms`, live symbol economics are flowing into Sidecar instead of stopping at the portfolio carrier.
- Because `peak_edge_usd` stayed at 0.0 and no `is_armed` or `threshold_crossed` row appeared, peak-giveback never armed and never reached trigger in this slice.
- Because the 7 filled lifecycles later produced EP-owned close orders and `POSITION_CLOSED` events, the eventual exits were downstream closes, not Sidecar-triggered close requests.
- Because the market-tick warning density stays roughly stable across adjacent core-log segments, there is no evidence in this slice that enabling the subscription created a new loop storm.

## ASSUMPTIONS

- The first economics-bearing non-flat sidecar row per rid is the correct proof row for mark cache and portfolio-carrier validation.
- `ORDER_TIMEOUT` followed by `ORDER_CANCELLED` is treated as a timed-out, never-filled lifecycle.
- `portfolio_fresh=true` on the economics-bearing rows is sufficient proof that the portfolio carrier was fresh for the Sidecar evaluation.

## UNKNOWNS

- No direct live `on_market_tick` handler log line was found in the current artifacts.
- A strict pre-R7K baseline for loop-warn rate is not available in this artifact set.
- There is no peak-giveback trigger proof because no threshold-met or recommendation row exists in the slice.

## Non-Flat Lifecycle Proof

The slice contains 7 real non-flat lifecycles that later closed and 3 order attempts that never filled:

- `ETHUSDT` short `0.015` opened at 2026-05-03 01:40:16.199 +03:00 and closed at 2026-05-03 01:41:07.261 +03:00.
- `ETHUSDT` short `0.009` opened at 2026-05-03 02:40:26.912 +03:00 and closed at 2026-05-03 02:41:12.074 +03:00.
- `BTCUSDT` long `0.0025` opened at 2026-05-03 03:25:07.247 +03:00 and closed at 2026-05-03 03:25:34.932 +03:00.
- `BNBUSDT` short `6.46` opened at 2026-05-03 04:06:14.662 +03:00 and closed at 2026-05-03 04:06:26.182 +03:00.
- `BNBUSDT` short `0.02` opened at 2026-05-03 04:15:12.664 +03:00 and closed at 2026-05-03 04:15:57.986 +03:00.
- `BTCUSDT` short `0.0131` opened at 2026-05-03 07:05:13.680 +03:00 and closed at 2026-05-03 07:05:46.023 +03:00.
- `XRPUSDT` short `5347.3` opened at 2026-05-03 07:10:44.505 +03:00 and closed at 2026-05-03 07:10:57.250 +03:00.

The never-filled lifecycles were:

- `XRPUSDT` order attempt at 2026-05-03 03:45:02.958 +03:00, timeout at 04:05:05.803 +03:00, cancel at 04:05:06.365 +03:00.
- `BNBUSDT` order attempt at 2026-05-03 07:35:03.787 +03:00, timeout at 07:55:05.535 +03:00, cancel at 07:55:06.181 +03:00.
- `BTCUSDT` order attempt at 2026-05-03 10:25:04.518 +03:00, timeout at 10:45:06.270 +03:00, cancel at 10:45:06.918 +03:00.

## Market Tick / Mark Cache Proof

- Startup proof exists: `Market tick subscription enabled for real-time unrealized PnL` in [logs/aurora_core.log.11](logs/aurora_core.log.11).
- Runtime event existence is visible through the core warnings: `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED`.
- Direct handler log evidence is absent, so the strongest proof is indirect: the economics-bearing sidecar rows show fresh `mark_price` and non-null symbol PnL after the subscription-enabled runtime is live.
- The largest observed `current_edge_usd` across the live non-flat rows is 2.99 USDT, which is far below the 25.0 USDT arm threshold.

## Portfolio Economics Proof

Across the non-flat Sidecar rows:

- non-flat rows: 746
- rows with `mark_price` non-null: 734
- rows with `unrealized_pnl_usdt` non-null: 734
- rows with `unrealized_pnl_pct` non-null: 734
- rows with `current_edge_usd` non-null: 734
- rows with `positions_last_ts_ms` present: 746
- rows with `portfolio_fresh=true`: 746

The 12 remaining non-flat rows are early post-fill grace rows where economics are still null. That is fail-closed behavior, not silent fallback.

## Sidecar Economics Proof

The first economics-bearing row for each filled lifecycle shows the full carrier chain:

- `position_snapshot.mark_price` is non-null.
- `position_snapshot.unrealized_pnl_usdt` is non-null.
- `position_snapshot.unrealized_pnl_pct` is non-null.
- `peak_giveback_snapshot.mark_price` is non-null.
- `peak_giveback_snapshot.current_edge_usd` is non-null.
- `portfolio_correlation.positions_last_ts_ms` is present.
- `freshness_snapshot.portfolio_fresh` is true.

That is the runtime proof that symbol economics are reconstructed and delivered into Sidecar.

The economics null-reason profile on non-flat rows is narrow:

- `giveback_pct: peak_edge_not_positive` appears 734 times.
- `mark_price`, `unrealized_pnl_usdt`, `unrealized_pnl_pct`, `current_edge_usd`, `giveback_pct`, and `threshold_crossed` are only null on the 12 early post-fill grace rows.

## Peak State Distribution

Overall Sidecar distribution:

- `peak_giveback_not_ready`: 55,730
- `peak_giveback_suppressed_close_in_progress`: 7
- startup `MODE_ACTIVE` markers: 12

Non-flat-row distribution:

- `peak_giveback_not_ready`: 739
- `peak_giveback_suppressed_close_in_progress`: 7

No armed state and no threshold-met state were observed.

## Trigger / Routing / Safety Analysis

- Sidecar emitted no close request and no recommendation.
- The downstream close path was EP-owned: `ORDER_PLACED` close orders were emitted by `ExecPosFSM`, followed by `POSITION_CLOSED` events in the order log.
- The 7 filled lifecycles closed cleanly through that downstream path.
- The 3 unfilled lifecycles timed out and were canceled before becoming non-flat.
- There is no evidence that Sidecar directly mutated brackets or took a direct exchange action.
- The shadow journal contains 140 suspected duplicates, all in `cross_origin_duplicate_exposure`, but none are peak-giveback close storms.

## Loop / Storm Analysis

- `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED` appears repeatedly in the core logs.
- The current segment has 27 such warnings over about 33 minutes.
- The immediately preceding segment has 52 warnings over about 58 minutes.
- That is a similar cadence, not a material step-up.
- No malformed payloads or JSON errors were observed in the current slice.
- The safest read is residual loop-warning debt, not a new loop storm caused by R7K.

## Final Verdict

Real non-flat economics do flow into Sidecar after R7K.

Peak-giveback is economically reconstructable from the live runtime slice.

No peak-giveback trigger occurred, and that absence is correct because the observed edges never armed or crossed threshold.

The market-tick listener is operational, but the runtime still carries a residual loop-warning burden.

Final verdict: `LIVE_ECONOMICS_FLOW_QUIET_BUT_OBSERVABLE`
