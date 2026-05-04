# R7K Mark Tick Subscription Enable Report

## Outcome

The canonical active Aurora config now sets `position_tracking.enable_market_tick_subscription` to `true` in [config/aurora/domains.yaml](config/aurora/domains.yaml).

The matching config contract test in [tests/config/test_position_tracking_contracts.py](tests/config/test_position_tracking_contracts.py) was updated to expect the enabled value, and the focused pytest slice passed.

## Validation

Focused validation succeeded with 36 passing tests across the config contract, PositionTracking economics export, and Sidecar consumption coverage.

## Runtime Proof

A bounded in-process smoke used the real `PositionTracking` class with the live-loaded config and a fake FSM. That smoke proved all of the following:

| Check | Result | Evidence |
| --- | --- | --- |
| Listener registration | PASS | `EVT:MARKET_TICK_RECEIVED` was registered alongside the other PositionTracking listeners. |
| Market tick receipt | PASS | `on_market_tick` processed a synthetic tick payload for `BTCUSDT`. |
| Mark cache update | PASS | The cached mark price became non-empty and stored `110.0`. |
| Fresh snapshot economics | PASS | With a fresh tick and an open position in the internal state, `_get_positions_snapshot()` returned `markPrice = 110`, `unrealizedPnl = 10`, and `unrealizedPnlPct = 10`. |

A separate bounded app restart was also exercised with a clean temporary WAL directory. That restart reached PositionTracking balance and account handling without introducing any new Sidecar close action. The current core logs still contain pre-existing `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED` warnings, so the enablement was treated carefully rather than assumed clean from logs alone.

## Residual Gap

The live restart slice did not include a non-zero real position, so a real account-level portfolio snapshot with non-null `markPrice` was not observed directly in that slice. The code path is verified, but a live non-flat account would be the next runtime slice to watch if end-to-end portfolio economics need a direct live observation.
