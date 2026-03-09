# Closed Positions Postmortem (20260309)

## Executive summary
- Closed lifecycles detected: **2**
- Net realized PnL (inferred where needed): **-143.3235**
- Dominant issue classes: bad timing=1, cancel pathology=1, execution issue=1, unclear=1

## Newly closed trades table
| lifecycle_id | symbol | strategy | side | entry_ts | exit_ts | exit_reason | realized_pnl | categories |
|---|---|---|---|---|---|---|---:|---|
| SOLUSDT:aurora_SOLUSDT_1773009904226 | SOLUSDT | aurora | buy | 2026-03-08T22:45:04.235000Z | 2026-03-08T23:05:06.516000Z | timeout_cancellation |  | cancel pathology; execution issue |
| ETHUSDT:aurora_ETHUSDT_1773008403767 | ETHUSDT | aurora | sell | 2026-03-08T22:20:03.772000Z | 2026-03-09T00:35:41.029000Z | position_disappeared_from_account_update | -143.3235 | bad timing; unclear |

## Top losses
- ETHUSDT:aurora_ETHUSDT_1773008403767 (ETHUSDT): realized_pnl=-143.32351000000065
- SOLUSDT:aurora_SOLUSDT_1773009904226 (SOLUSDT): realized_pnl=None

## Top mistakes repeated by the system
- bad timing: 1
- cancel pathology: 1
- execution issue: 1
- unclear: 1

## Strategy-level summary
- aurora: trades=2, pnl_sum=-143.3235, wins=0, losses=1

## Regime-level summary
- HIGH_VOLATILITY: trades=2, pnl_sum=-143.3235

## Which strategies were right/wrong?
- aurora: trades=2, pnl_sum=-143.3235, wins=0, losses=1

## Which regimes were profitable/unprofitable?
- HIGH_VOLATILITY: trades=2, pnl_sum=-143.3235

## Which exits were likely premature?
- ETHUSDT:aurora_ETHUSDT_1773008403767 drift_15m=0.31620154999995975

## Which TP/SL settings look structurally wrong?
- No structural TP/SL defect confirmed from this window.

## Which anomalies repeated across trades?
- bad timing: 1
- cancel pathology: 1
- execution issue: 1
- unclear: 1

## Recommendations for tuning
- Add explicit lifecycle close WAL verb with `exit_reason`, `close_fill_price`, and `realized_pnl_net` for every terminal close to remove ambiguity.
- Keep `fill_timeout` for passive SOL entries but add per-symbol timeout tuning; timeout cancellations are repeating and should be strategy/regime adaptive.
- For ETH short lifecycle `1773008403767`, direction was adverse at close; require stronger confirmation in HIGH_VOLATILITY before adding short exposure.

## Exact evidence files used
- reports/auto/trade_lifecycle_ledger.jsonl
- reports/auto/active_positions_snapshot_20260308_230504.json
- reports/auto/active_positions_snapshot_20260309_030810.json
- ops/wal/2026-03-09.jsonl
- logs/order_log_v1.jsonl
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/mean_reversion.yaml
- config/aurora/trading.yaml
- config/aurora/regime.yaml
