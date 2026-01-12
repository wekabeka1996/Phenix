# MR-RESTORE-002 — Local Probe Report

**Generated**: 2026-01-09 02:46:06 (local)

## Evidence

- Emitted `EVT:MARKET_TICK_FORWARDED` ticks into `MeanReversionHandler` (MiniFSM).
- Collected durable diagnostic JSONL artifact.

## Summary (machine)

```json
{
  "symbol": "DOGEUSDT",
  "ticks_emitted": 25,
  "diag_jsonl_path": "/home/wekabeka/Музыка/Phenix/reports/mr_restore_002_probe.jsonl",
  "diag_lines": 20
}
```

## First 20 diagnostic lines (JSONL)

```jsonl
{"ts_ms": 1700000000000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 1}
{"ts_ms": 1700000030000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 2}
{"ts_ms": 1700000060000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 3}
{"ts_ms": 1700000090000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 4}
{"ts_ms": 1700000120000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 5}
{"ts_ms": 1767926766340, "kind": "mr_bar_closed", "symbol": "DOGEUSDT", "tf_sec": 180, "bar_end_ts_ms": 1700000099999, "mr_bars_closed_total": 1}
{"ts_ms": 1700000150000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 6}
{"ts_ms": 1700000180000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 7}
{"ts_ms": 1700000210000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 8}
{"ts_ms": 1700000240000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 9}
{"ts_ms": 1700000270000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 10}
{"ts_ms": 1700000300000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 11}
{"ts_ms": 1767926766340, "kind": "mr_bar_closed", "symbol": "DOGEUSDT", "tf_sec": 180, "bar_end_ts_ms": 1700000279999, "mr_bars_closed_total": 2}
{"ts_ms": 1700000330000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 12}
{"ts_ms": 1700000360000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 13}
{"ts_ms": 1700000390000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 14}
{"ts_ms": 1700000420000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 15}
{"ts_ms": 1700000450000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 16}
{"ts_ms": 1700000480000, "kind": "mr_tick_seen", "symbol": "DOGEUSDT", "mr_ticks_seen_total": 17}
{"ts_ms": 1767926766341, "kind": "mr_bar_closed", "symbol": "DOGEUSDT", "tf_sec": 180, "bar_end_ts_ms": 1700000459999, "mr_bars_closed_total": 3}
```