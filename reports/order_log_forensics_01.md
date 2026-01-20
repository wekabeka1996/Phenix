# ORDER LOG FORENSICS: Why `order_log_v1.jsonl` Is Not Created

**Date:** 2026-01-13
**Status:** Root Cause Identified

## Summary

The file `logs/order_log_v1.jsonl` is **never created** because:

1. **No orders are placed** → `order_logger.write()` never called.
2. **No trade intents proposed** → No `TRADE_INTENT_PROPOSED` events.
3. **All signals blocked** → 100% rejection rate (562/562).

## Chain Analysis

```
Strategy Signal → [BLOCKED] → No Trade Intent → No Order → No Log
```

## Block Reasons by Symbol

| Symbol | Block Reason | Root Cause |
|--------|--------------|------------|
| SOLUSDT | `WARMUP_NOT_READY:regime_not_ready` | Regime detector needs 50 bars (4.2h warmup) |
| ETHUSDT | `WARMUP_NOT_READY:regime_not_ready` | Same |
| BTCUSDT | `WARMUP_NOT_READY:regime_not_ready` | Same |
| DOGEUSDT | `ARBITRATION_REJECT:strategy_not_assigned_to_symbol` | DOGE assigned to MR, Aurora blocked |
| XRPUSDT | `ARBITRATION_REJECT:strategy_not_assigned_to_symbol` | XRP assigned to MR, Aurora blocked |

## Evidence from Logs

```
logs/domain_decision_making.log:
[SOLUSDT] STRATEGY_SIGNAL_GATEWAY: Processing BUY signal...
[SOLUSDT] WARMUP_NOT_READY:regime_not_ready context=strategy_signal_gateway:pre_emit
Risk gate alert: 100.0% intents blocked (562/562)
```

## Fix Options

1. **Wait for Warmup** - Let system run 4.2+ hours for regime buffers to fill.
2. **Reduce Warmup Period** - Change `regime.yaml:sma_long_period` from 50 to 20 (reduces warmup to ~1.7h).
3. **Disable Regime Gate** (Dangerous) - Skip regime warmup check (NOT recommended for production).

## Technical Details

- Logger code: `apps/reference/telemetry/order_logger.py:62`
- Write calls: 26 locations in `fsm.py`, `decision_making.py`, `exposure_guard.py`
- All writes are conditional on order creation events
- File is created on first write (line 55: `mkdir`)

## Resolution

This is **expected behavior** for a freshly started system. The file will appear once:
1. Regime warmup completes (~4.2 hours of uptime), AND
2. At least one trade intent passes all gates.
