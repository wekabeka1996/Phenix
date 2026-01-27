# Investigation Report: Market Order Cancellation Anomaly

## Problem Description
In backtests, `MARKET` orders placed by the system are being cancelled with the reason `CANCEL_STALE_REGIME` after exactly 5 minutes (one candle duration), resulting in a 0% fill rate. This occurs despite the expectation that MARKET orders should fill immediately (or at the next tick).

## Root Cause Analysis

### 1. The "Phantom" Pending Order
The core issue lies in **`ExecPosFSM._on_order_fill`** in `apps/reference/domains/execution_position/fsm.py`.
- When an order is placed and acknowledged (`ACK`), it is registered with `OrderTimeoutWatchdog` in `_on_order_ack`.
- When the order is filled (`ORDER_FILL`), `_on_order_fill` processes the event (updating exposure, injecting intent data, etc.) but **ACTUALLY FAILS to notify the Watchdog that the order is filled**.
- **Result**: The order remains in `Watchdog.acked_orders` (tracked as "Pending") even after it is physically filled.

### 2. The Trigger: Regime Change
- When the market moves to the next candle (5 minutes later), `RegimeDetector` processes the new market data.
- If a regime change is detected, it emits `EVT:REGIME_DETECTED`.
- `ExecPosFSM._on_regime_detected` handles this event.
- It calls `_cancel_pending_entries_for_symbol` with reason `CANCEL_STALE_REGIME` to clean up old orders that might be invalid in the new regime.

### 3. The Cancellation
- `_cancel_pending_entries_for_symbol` iterates over orders in `Watchdog`.
- It finds the (actually filled) order because it wasn't removed from the Watchdog.
- It sends a `cancel_order` command to the Broker.
- In the Backtest environment, the `MockBroker` might be in a state (or timing window) where this cancellation effectively overrides the fill status or causes the order to be reported as Canceled in the final metrics (depending on how `MockBroker` handles race conditions between Fill and Cancel in the same tick).
- Specifically, if `BacktestEngine` fills the order at T=5m, but the `RegimeDetector` also runs at T=5m and issues a Cancel, the logic assumes the order was caught in a race and cancelled.

## Recommendations
1.  **Fix `ExecPosFSM._on_order_fill`**: explicitly call `self.watchdog.on_order_fill(order_id)` to remove the order from the timeout tracker immediately upon receipt of the fill event.
2.  **Verify Watchdog State**: Ensure `_on_order_cancel` is also wired correctly (it appears to cover cancellations, but fills were missed).

## Impact
This fix ensures that filled orders are correctly recognized as "Terminal" by the Watchdog, preventing "Phantom Cancellations" triggered by subsequent regime changes or timeouts.
