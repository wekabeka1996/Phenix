# Observability and Forensics Result

## Inputs
- Time window: 2026-02-06 10:16:14–10:17:32 (UTC, per log timestamps)
- Evidence sources:
  - [logs/aurora_core.log.6](logs/aurora_core.log.6)
- Subsystem: execution_position / decision_making / backtest_engine (BTCUSDT)

## Timeline (UTC)
1) 10:16:14.103–10:16:14.105 — Entry fill for BTCUSDT SELL 0.345 @ 28938.3 with deferred brackets; equity_free_usdt recorded near 1388.31. [logs/aurora_core.log.6](logs/aurora_core.log.6#L31440-L31453)
2) 10:17:26.745–10:17:26.747 — New BTCUSDT BUY entry filled 0.273 @ 27640.5; equity_free_usdt 998.4908287 with margin ~377.29. [logs/aurora_core.log.6](logs/aurora_core.log.6#L39820-L39847)
3) 10:17:28.165–10:17:28.166 — Exit detected, BTCUSDT SELL 0.273 @ 24799.13918; equity_free_usdt drops to 220.09125884154344; position closed. [logs/aurora_core.log.6](logs/aurora_core.log.6#L39936-L39946)
4) 10:17:29.626–10:17:29.627 — BTCUSDT SELL entry 0.057 @ 26482.5 confirmed; equity_free_usdt 219.78935834154345 with margin ~75.48. [logs/aurora_core.log.6](logs/aurora_core.log.6#L40212-L40229)
5) 10:17:31.975–10:17:31.976 — Exit detected, BTCUSDT BUY 0.057 @ 26795.45802; equity_free_usdt drops to 201.33981475868754; position closed. [logs/aurora_core.log.6](logs/aurora_core.log.6#L40600-L40614)

## Evidence table
| Evidence | Source | Timestamp | Notes |
|---|---|---|---|
| Entry SELL 0.345 @ 28938.3, deferred brackets placed | [logs/aurora_core.log.6](logs/aurora_core.log.6#L31440-L31453) | 10:16:14.103–10:16:14.105 | Prior position and bracket placement (order id d0766d94-e901-4bcb-bfe5-9853a6ec72b0; SL 0a537ab5…, TP af98334f…). |
| BUY entry filled 0.273 @ 27640.5; equity_free_usdt 998.4908287 | [logs/aurora_core.log.6](logs/aurora_core.log.6#L39820-L39847) | 10:17:26.745–10:17:26.747 | Entry order 08e836c7-818f-4918-9713-5180318a1bf0; SL 1bf4e696…, TP 20298291…. |
| Exit SELL 0.273 @ 24799.13918; equity_free_usdt 220.09125884154344 | [logs/aurora_core.log.6](logs/aurora_core.log.6#L39936-L39946) | 10:17:28.165–10:17:28.166 | Exit detected, position closed; large adverse fill vs prior mark (~27583). |
| SELL entry 0.057 @ 26482.5; equity_free_usdt 219.78935834154345 | [logs/aurora_core.log.6](logs/aurora_core.log.6#L40212-L40229) | 10:17:29.626–10:17:29.627 | Entry order 60fcc470-e02a-4256-a322-c90aa87db369; SL 54943cb2…, TP a694e8e6…. |
| Exit BUY 0.057 @ 26795.45802; equity_free_usdt 201.33981475868754 | [logs/aurora_core.log.6](logs/aurora_core.log.6#L40600-L40614) | 10:17:31.975–10:17:31.976 | Exit detected, position closed; equity drop confirmed. |

## Root cause
- Primary cause: Large adverse price move in the backtest feed between 10:17:26 and 10:17:28 leading to an exit fill far below the long entry (27640.5 → 24799.13918), collapsing equity_free_usdt from 998.49 to 220.09. [logs/aurora_core.log.6](logs/aurora_core.log.6#L39820-L39946)
- Contributing factors: Subsequent short entry closed higher (26482.5 → 26795.45802), further reducing equity_free_usdt to 201.34. [logs/aurora_core.log.6](logs/aurora_core.log.6#L40212-L40614)

## Severity
- Severity: S2
- Justification: Rapid equity drawdown from 998.49 to 201.34 within ~6 seconds due to two consecutive adverse fills in backtest execution. [logs/aurora_core.log.6](logs/aurora_core.log.6#L39820-L40614)

## Corrective actions
1) Validate the backtest price series around 10:17:26–10:17:28 for BTCUSDT to confirm the abrupt drop (check data source continuity and gap handling).
2) Add an audit check for extreme single-bar price deltas that exceed configured slippage/volatility bounds and flag runs for review.

## Decision
- Status: ALLOWED
- Rationale: Evidence is sufficient to explain the equity drop via two adverse exit fills; no missing artifacts for this segment.
