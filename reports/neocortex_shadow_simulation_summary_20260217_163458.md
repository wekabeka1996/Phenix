# Neocortex Shadow Simulation Summary

- Generated at: `2026-02-17T16:34:58.899153Z`
- Time mode: `sequence_time`
- Intents loaded: `73832`
- Trades simulated: `21816`

## Parameters

- horizon_ticks: `120`
- fee_bps_roundtrip: `4.0`
- slippage_bps_entry: `1.0`
- slippage_bps_exit: `1.0`

## Overall

- winrate: `6.58%`
- net_return_sum: `-129672.12 bps`
- expectancy: `-5.94 bps/trade`
- max_drawdown: `-129677.76 bps`
- avg_pnl_quote_1unit: `-0.000832`

## By Symbol

| Symbol | Trades | Winrate | Net bps | Expectancy bps | Max DD bps |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | 0 | 0.00% | 0.00 | 0.00 | 0.00 |
| DOGEUSDT | 0 | 0.00% | 0.00 | 0.00 | 0.00 |
| ETHUSDT | 0 | 0.00% | 0.00 | 0.00 | 0.00 |
| SOLUSDT | 0 | 0.00% | 0.00 | 0.00 | 0.00 |
| XRPUSDT | 21816 | 6.58% | -129672.12 | -5.94 | -129677.76 |

## Notes

- If feature logs do not contain reliable timestamps, mode is `sequence_time` and alignment is based on per-symbol intent order, not wall-clock.
- This is shadow analytics and does not replace realized exchange PnL accounting.
