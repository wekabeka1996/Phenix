# Filter parity diagnostics

| Symbol | Tick | Step | Min qty | Min notional | Overall |
|---|---|---|---|---|---|
| BTCUSDT | match | configured 0.001 vs exchange 0.0001 | configured 0.001 vs exchange 0.0001 | configured 100 vs exchange 50 | `minor_mismatch` |
| ETHUSDT | match | match | match | match | `match` |

BTC values are stricter and grid-compatible, so the difference is not material. No configured value was mutated.

Severity precedence is stale → configured missing → exchange missing → material → minor → match. Material means an incompatible grid or a configured minimum below the exchange requirement.
