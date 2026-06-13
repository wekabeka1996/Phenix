# CURRENT_EVENT_GATE_REPLAY_REPORT

## Scope

Read-only replay of current `order_log_v1.jsonl` decisions joined to local 300s mean-reversion bars.
Directional replay uses future 300s closes. Bracket replay is only used when rejected rows carried entry/target/stop geometry.
Net bracket bps subtracts a fixed 10 bps fee+slippage layer.

## Counts

- Rows total: 64
- Accepted intents: 1
- Rejected intents: 60
- Bracket replay rows: 21
- Reject by NRR: {'NRR-027': 17, 'NRR-028': 3, 'NRR-062': 21, 'NRR-026': 9, 'NRR-029': 10}

## Directional Follow-Through

- 1 bars: n=60 positive_rate=0.533 avg_bps=-1.06 median_bps=0.78
- 3 bars: n=60 positive_rate=0.550 avg_bps=2.32 median_bps=4.10
- 6 bars: n=59 positive_rate=0.525 avg_bps=3.07 median_bps=1.26
- 12 bars: n=56 positive_rate=0.500 avg_bps=4.46 median_bps=1.32

## Bracket Replay By NRR

- NRR-062: n=21 win_rate=0.762 avg_net_bps=15.71 median_net_bps=44.00 outcomes={'TP': 13, 'TIMEOUT': 5, 'SL': 3}

## Top Profitable Blocked Bracket Replays

- 2026-06-08T12:20:02.230000+00:00 BNBUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_BNBUSDT_1780921202195
- 2026-06-08T12:30:03.451000+00:00 BNBUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_BNBUSDT_1780921803415
- 2026-06-08T14:35:02.993000+00:00 BNBUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_BNBUSDT_1780929302955
- 2026-06-08T04:05:04.200000+00:00 XRPUSDT SELL NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_XRPUSDT_1780891504172
- 2026-06-08T12:10:01.481000+00:00 BNBUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_BNBUSDT_1780920601433
- 2026-06-08T09:40:02.925000+00:00 XRPUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_XRPUSDT_1780911602878
- 2026-06-08T09:00:04.813000+00:00 DOGEUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_DOGEUSDT_1780909204769
- 2026-06-08T14:45:04.308000+00:00 BNBUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_BNBUSDT_1780929904269
- 2026-06-08T07:30:02.380000+00:00 XRPUSDT SELL NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_XRPUSDT_1780903802343
- 2026-06-08T15:00:05.315000+00:00 DOGEUSDT BUY NRR-062 net=44.00 outcome=TP regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_DOGEUSDT_1780930805279

## Top Losing Blocked Bracket Replays

- 2026-06-08T12:00:06.494000+00:00 BNBUSDT BUY NRR-062 net=-55.00 outcome=SL regime=LOW_VOLATILITY mr=SHORT/FLAT_LOW pct_b=0.9860721117864456 rid=aurora_BNBUSDT_1780920006443
- 2026-06-08T09:50:03.822000+00:00 DOGEUSDT BUY NRR-062 net=-55.00 outcome=SL regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_DOGEUSDT_1780912203770
- 2026-06-08T10:00:05.132000+00:00 XRPUSDT BUY NRR-062 net=-55.00 outcome=SL regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_XRPUSDT_1780912805079
- 2026-06-08T09:50:03.923000+00:00 XRPUSDT BUY NRR-062 net=-39.31 outcome=TIMEOUT regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_XRPUSDT_1780912203877
- 2026-06-08T09:20:01.080000+00:00 DOGEUSDT BUY NRR-062 net=-24.36 outcome=TIMEOUT regime=LOW_VOLATILITY mr=NEUTRAL/LOW_VOLATILITY pct_b=None rid=aurora_DOGEUSDT_1780910401036
