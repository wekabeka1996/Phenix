# CURRENT_EVENT_GATE_REPLAY_INTERPRETATION

## Scope

This report analyzes the current runtime decision stream from `logs/order_log_v1.jsonl`
against local 300s mean-reversion bars.

The goal is to identify:

- which proposed trades were blocked by gates/policies;
- which blocked trades would likely have made money in retrospective replay;
- where the system appears to interpret the market too strictly or incorrectly;
- why the runtime can remain unprofitable or under-active despite visible market
  opportunity.

## Data Used

- Rejected intents: 60.
- Accepted strategy intents: 1.
- Rejected rows with entry/target/stop geometry: 21.
- Market replay source: `logs/mean_reversion/bars_300s.jsonl`.
- Bracket replay horizon: 12 future 300s bars.
- Net replay cost layer: 10 bps per trade.

## Main Finding

The current gate stack is probably overblocking some low-volatility Aurora
signals, especially NRR-062 rows where the low-vol cost floor blocks weak
direction confidence.

For the 21 rejected NRR-062 rows with full geometry:

- 13 hit TP;
- 3 hit SL;
- 5 timed out;
- win rate: 76.2%;
- average net replay: +15.71 bps;
- median net replay: +44.00 bps.

This is not enough sample to promote the segment, but it is enough to say the
gate may be suppressing a real short-horizon low-vol opportunity.

## Important Caveat

This positive NRR-062 result is not the exact segment
`LOW_VOL + FLAT_LOW + SHORT + pct_b 0.75-0.85`.

Current exact sample count for that segment:

- 0 rejected rows.

The current profitable NRR-062 cohort mostly appears when MR is
`NEUTRAL / LOW_VOLATILITY`, not when MR is `FLAT_LOW`.

Rows where MR was `FLAT_LOW` were worse:

- FLAT_LOW directional 3-bar rejected rows: n=9, positive_rate=22.2%,
  average=-23.73 bps.
- NRR-062 bracket rows with MR `FLAT_LOW`: n=2, win_rate=50%,
  average=-22.53 bps.

So the system may not be missing edge in the overbought/oversold FLAT_LOW slice.
It may be missing edge in low-vol micro-continuation or neutral low-vol drift
where the raw Aurora score is small but directionally useful.

## Gate-Level Read

Directional 3-bar replay by reject reason:

- NRR-062: n=21, positive_rate=61.9%, average=+8.36 bps.
- NRR-027: n=17, positive_rate=47.1%, average=-3.28 bps.
- NRR-029: n=10, positive_rate=60.0%, average=-0.61 bps.
- NRR-026: n=9, positive_rate=55.6%, average=-0.51 bps.
- NRR-028: n=3, positive_rate=33.3%, average=+10.07 bps.

Interpretation:

- NRR-062 is the most suspicious overblock in this window.
- NRR-027 appears broadly protective.
- NRR-026/029 are mixed and need more context before relaxing.
- NRR-028 sample is too small and unstable.

## Symbol-Level Read

Directional 3-bar replay after rejected intents:

- DOGEUSDT: n=28, positive_rate=57.1%, average=+7.34 bps.
- XRPUSDT: n=12, positive_rate=75.0%, average=+1.95 bps.
- BNBUSDT: n=10, positive_rate=50.0%, average=+3.55 bps.
- ETHUSDT: n=9, positive_rate=33.3%, average=-8.72 bps.
- BTCUSDT: n=1, average=-46.57 bps.

Interpretation:

- DOGE/XRP/BNB contain the missed-opportunity cluster.
- ETH rejects look mostly justified in this window.
- Symbol-specific NRR-062 calibration is more promising than a global relaxation.

## Current Accepted Runtime Intent

The current order log contains one accepted strategy intent:

- `aurora_BNBUSDT_1780882503185`
- side: BUY;
- regime: TREND_UP;
- confidence: 0.2639;
- order placed at GTX after spread guard adjustment;
- partially filled;
- timed out and cancelled;
- later residual close attribution shows a small realized loss.

This is a different failure mode than gate overblocking. It points at execution
quality: partial fill, long fill TTL, deferred protection, and timeout handling
can turn an accepted signal into poor realized economics.

## Why The System Can Still Be Losing

The current evidence points to two separate bottlenecks:

1. Gate selectivity is not calibrated to realized short-horizon outcomes.
   NRR-062 blocks many weak low-vol signals, but several of those weak signals
   would have reached TP in the immediate 300s-bar replay.

2. Accepted trades can suffer execution decay.
   The accepted BNB trade was not a clean instant entry. It partially filled,
   timed out, and required cleanup. That means even if signal selection improves,
   execution freshness and partial-fill protection can still destroy edge.

## What The Market Interpretation Seems To Miss

The system treats weak direction confidence as mostly non-actionable in
low-volatility regimes. In this current window, that is too blunt.

The missing distinction is:

- weak score in noisy/choppy FLAT_LOW overextension: often dangerous;
- weak score in neutral LOW_VOL with supportive short-horizon price motion:
  sometimes profitable as a small scalp.

This means the problem is not "allow all weak confidence" and not "block all weak
confidence". The missing policy is a low-vol micro-opportunity classifier that
separates continuation drift from exhausted mean-reversion extremes.

## Recommended Next Experiment

Do not re-enable the old NRR-062 override.

Instead, test a bounded shadow policy:

- only `LOW_VOLATILITY`;
- only symbols with positive recent replay: DOGEUSDT, XRPUSDT, BNBUSDT;
- require MR regime `LOW_VOLATILITY`, not `FLAT_LOW`;
- exclude MR `SHORT` when Aurora wants BUY and exclude MR `LONG` when Aurora
  wants SELL;
- require price-motion alignment with side over 60s or 300s;
- require fill freshness under 60 seconds;
- reduce size by at least 70% until sample size is meaningful;
- keep full NRR-062 telemetry and compare against the blocked baseline.

Promotion should require positive net expectancy after fees, slippage, stale-fill
penalty, and partial-fill protection cost.

## Files

- Rows: `current_event_gate_replay_rows.csv`
- Summary: `current_event_gate_replay_summary.json`
- Mechanical report: `CURRENT_EVENT_GATE_REPLAY_REPORT.md`
