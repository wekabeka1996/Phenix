# EXECUTION-VS-UPSTREAM-TRACE-01

## Window (derived)
- regime log: `logs/domain_regime_detector.log` (exists=True)
- start_ts_ms: `1768253034595` (2026-01-12 21:23:54)
- wal files: `8` (glob `ops/wal/*.jsonl`)

## Counts by symbol (all uptime window)
- CSV: `reports/execution_vs_upstream_trace_01_counts.csv`

| symbol | BAR 180s | BAR 300s | BAR 900s | CMD:PROCESS_STRATEGY | INTENT_PROPOSED | INTENT_REJECTED | CMD:OPEN | ORDER_PLACED | ORDER_REJECTED |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DOGEUSDT | 259 | 155 | 52 | 1 | 0 | 290 | 0 | 0 | 0 |
| XRPUSDT | 259 | 155 | 52 | 1 | 0 | 281 | 0 | 0 | 0 |
| BTCUSDT | 259 | 155 | 52 | 1 | 0 | 155 | 0 | 0 | 0 |
| ETHUSDT | 259 | 155 | 52 | 1 | 0 | 155 | 0 | 0 | 0 |
| SOLUSDT | 259 | 155 | 52 | 1 | 0 | 155 | 0 | 0 | 0 |

## BAR_CLOSED totals (WAL)
- tf_sec=180: count=1295, first_bar_close_ts=1768253039999 (2026-01-12 21:23:59)
- tf_sec=300: count=775, first_bar_close_ts=1768253099999 (2026-01-12 21:24:59)
- tf_sec=900: count=260, first_bar_close_ts=1768253399999 (2026-01-12 21:29:59)

## Basis timeframe + warmup mechanics (code/config)
- basis TF: `config/aurora/regime.yaml:1` (`basis_tf_sec: 300` → 5m)
- bar-only filter: `apps/reference/domains/regime_detector/regime_detector.py:208` (requires `tf_sec == basis_tf_sec`)
- SMA long warmup ("50 bars"): `config/aurora/regime.yaml:27` + `apps/reference/domains/regime_detector/regime_detector.py:301`
- ATR baseline warmup (100 bars): `config/aurora/regime.yaml:34` + `apps/reference/domains/regime_detector/regime_detector.py:354`
- full_ready is strict: `apps/reference/domains/regime_detector/regime_detector.py:458` (needs all ready flags and no data_drops)

## Warmup conclusion (explicit)
- now: regime warmup clocks on TF=`300s (5m)`; first observed 5m bar close in this uptime window = `2026-01-12 21:24:59`
- first observed 15m bar close (tf_sec=900) in this uptime window = `2026-01-12 21:29:59`

## BAR_CLOSED emission delay vs bar_close_ts (WAL)
This approximates how late `BAR_CLOSED` arrives vs the bar boundary (ms).
- tf_sec=180: n=1295, min=6ms, median=2407ms, p95=4733ms, max=54109ms
- tf_sec=300: n=775, min=5ms, median=2403ms, p95=4720ms, max=5374ms
- tf_sec=900: n=260, min=11ms, median=2407ms, p95=4774ms, max=4970ms

## Tick TTL (config)
- tick_ttl_ms (from `config/aurora/system.yaml`): `2000`
- compare: p95(BAR_CLOSED 300s delay)=4720ms vs tick_ttl_ms=2000ms
- implication: bar-boundary timestamps will often be treated as stale by strict TTL checks

## TRADE_INTENT_REJECTED top reasons (WAL)
- `NRR-046`: `775`
- `ARBITRATION_BLOCKED`: `261`

## Top gate reasons (DecisionMaking text logs)
- `warmup:regime_not_ready`: `294`
- `arbitration:strategy_not_assigned_to_symbol`: `196`


## Gate that blocks CMD:OPEN (file/line)
- warmup gate call site: `apps/reference/domains/decision_making/decision_making.py:925`
- warmup deny: `apps/reference/domains/decision_making/decision_making.py:2301` (checks warmup.full_ready) + `apps/reference/domains/decision_making/decision_making.py:2241` (logs WARMUP_NOT_READY:*)
- arbitration deny: `apps/reference/domains/decision_making/decision_making.py:475` (emits reason_code=ARBITRATION_BLOCKED; details include ARBITRATION_REJECT:*)
- tick-level features fail-closed: `apps/reference/domains/decision_making/decision_making.py:1810` → `apps/reference/domains/decision_making/decision_making.py:1833` (writes NRR-046)

## Execution wiring sanity (only relevant if CMD:OPEN > 0)
- bridge dispatch calls execution directly: `apps/reference/main.py:768`
- ExecPosFSM routes `msg.verb == "OPEN"`: `apps/reference/domains/execution_position/fsm.py:1365`

## Conclusion
- Root cause = Upstream gate: DecisionMaking never emitted CMD:OPEN
gj