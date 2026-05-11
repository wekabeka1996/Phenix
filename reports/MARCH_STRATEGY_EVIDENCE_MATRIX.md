# MARCH STRATEGY EVIDENCE MATRIX

## Scope

- Research surface: MARCH / SIDE B / DEGRADED PARTIAL-UNIVERSE.
- Primary anchor artifact: `reports/backtests/20260312_132130/` with `resolved_config.json`, `manifest.json`, `result.json`, plus `reports/backtests/backtest_20260312_132130.json`.
- Validation rerun: baseline `20260314_041537` reproduced the same March loss surface on the current repo state.
- Limitation: `logs/backtests/order_log_20260312_132130.jsonl` is not present in the workspace, so entry-phase / why-chain evidence is unavailable. This matrix is therefore bounded to bundle-level trade data and existing forensic reports.

## Frozen March Surface

- Launcher: `scripts/diagnostics/run_single_backtest.py`.
- Runtime path: `apps/reference.main.run_backtest_simulation()`.
- Active side B assignment registry: Aurora-only.
- Configured symbols in the March anchor bundle: `1000PEPEUSDT`, `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`.
- Realized March trade surface in `result.json`: `ETHUSDT` and `BNBUSDT` only.
- ETH current per-symbol control surface available in config: `allowed_regimes`, `signal_threshold`, `volatility_entry_logic.regime_multipliers`, `holding_period`, `reentry_cooldown_sec`, `exit.regime_tpsl`.
- No current config-only surface exists for a green-bounce / entry-phase exhaustion gate.

## Evidence Matrix

| Slice | Closed trades | Net PnL USDT | Pattern type | Evidence status | Implementation classification |
| --- | ---: | ---: | --- | --- | --- |
| ETHUSDT / TREND_DOWN / LONG / SL | 30 in anchor, 31 in baseline rerun | Dominant repeated loss cluster | Repeated root-cause candidate | Strong | Config-only only at coarse regime-block level; fine filter needs code |
| ETHUSDT / TREND_DOWN / LONG / TP | 38 in anchor and baseline rerun | Positive offset, but insufficient to overcome SL mass | Offset, not root cause | Strong | Keep out of v1 decision except as opportunity-cost note |
| ETHUSDT / TREND_DOWN / SHORT | 5 trades in anchor and baseline rerun | Material negative despite small count | Repeated but low-n secondary loss cluster | Medium | Not separately controllable via current config surface |
| ETHUSDT / MEAN_REVERSION / LONG | 9 trades in anchor and baseline rerun | Positive net contributor | Positive keep-cluster | Strong | Leave unchanged in v1 |
| BNBUSDT / MEAN_REVERSION / LONG | 7 trades in anchor and baseline rerun | Small negative contributor | Minor residual noise | Medium | Leave unchanged in v1 |

## March Anchor Facts

- March anchor `20260312_132130` closed-trade surface:
  - `ETHUSDT`: 83 trades, about `-346 USDT`.
  - `BNBUSDT`: 7 trades, about `-19 USDT`.
  - `ETHUSDT / TREND_DOWN / LONG`: 69 trades, about `-212.5 USDT`.
  - `ETHUSDT / TREND_DOWN / SHORT`: 5 trades, about `-176.0 USDT`.
  - `ETHUSDT / MEAN_REVERSION / LONG`: 9 trades, about `+42.1 USDT`.
- Current baseline rerun `20260314_041537` confirms the same structure from current repo truth:
  - Closed trades in `result.json`: 90.
  - ETH TREND_DOWN combined net: `-387.42 USDT`.
  - ETH MEAN_REVERSION combined net: `+42.11 USDT`.
  - BNB MEAN_REVERSION combined net: `-18.95 USDT`.

## Candidate Rule Shortlist

| Rule ID | Rule | Evidence basis | Surface | Decision |
| --- | --- | --- | --- | --- |
| R1 | Block `ETHUSDT` in `TREND_DOWN` entirely | Dominant repeated March loss cluster; no positive evidence that this regime slice is net beneficial on the degraded March surface | Config-only | Selected for v1 |
| R2 | Block only `ETHUSDT / TREND_DOWN / LONG` via exhaustion / green-bounce gate | Older clean-run forensics support it, but current March anchor lacks order-log fields and runtime has no config-only hook | Minimal additive code | Deferred |
| R3 | Retune ETH TREND_DOWN TP/SL geometry | March evidence shows wrong-side participation as well as payoff issues; not the smallest causal fix | Config-only | Rejected for v1 |
| R4 | Retune or block BNB MEAN_REVERSION | Small sample, small absolute drag, not the root cause | Config-only | Rejected for v1 |
| R5 | Change ETH MEAN_REVERSION handling | Positive March slice | Config-only | Rejected |

## Selection

Selected minimal candidate v1: `R1`.

Why this one:

1. It directly targets the only large repeated March loss engine present in both the required anchor bundle and the current baseline rerun.
2. It is expressible with an existing config knob: `strategies.aurora.assets.ETHUSDT.allowed_regimes`.
3. It preserves the only clearly positive ETH slice on the degraded March surface: `MEAN_REVERSION`.
4. It avoids inventing a finer runtime control surface that current bundle evidence cannot validate honestly.

## Boundaries

- This is a backtest research candidate only, not a production recommendation.
- This result is valid only for the March degraded partial-universe surface currently reproducible from the repo.
- The candidate does not claim Jan-Feb retention or Q2 robustness.