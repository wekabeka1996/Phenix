# R7K Mark Tick Smoke Matrix

| Check | Method | Result | Evidence | Notes |
| --- | --- | --- | --- | --- |
| Config flag loaded | ConfigLoader on active Aurora config | PASS | `position_tracking.enable_market_tick_subscription` loaded as `true`. | Confirms the canonical YAML is active. |
| Listener registered | Real `PositionTracking` instance with fake FSM | PASS | `fsm.listen_calls` included `EVT:MARKET_TICK_RECEIVED -> on_market_tick`. | This is the key routing proof. |
| Tick received | Direct call to `on_market_tick` with a synthetic `Message` | PASS | The handler accepted the tick for `BTCUSDT`. | No exception and no loop feedback from the handler. |
| Mark cache updated | Inspect `_mark_prices` after the tick | PASS | Cached mark price became `110.0` with a fresh timestamp. | Confirms `update_mark_price` executed. |
| Fresh snapshot economics | Seed a non-zero position and call `_get_positions_snapshot()` | PASS | Snapshot returned non-null `markPrice`, `unrealizedPnl`, and `unrealizedPnlPct`. | This proves the fresh-mark branch. |
| Live restart smoke | Restart app with temp WAL | PARTIAL | Startup reached PositionTracking balance and account handling. | The live slice stayed flat, so no real open-position snapshot was available. |
| Sidecar close safety | Exact log search for `POSITION_POLICY_SIDECAR_CLOSE_REQUEST` | PASS | No matches found in current core logs. | Enabling the subscription did not itself trigger a close request. |
| Malformed payload safety | Current log search for malformed or JSON errors | PASS | No relevant matches found in the smoke window. | No malformed Sidecar or portfolio payload was observed. |
| Loop storm check | Current log search for `LOOP_DETECTED` market tick warnings | WARN | Existing `LOOP_DETECTED: EVT:MARKET_TICK_RECEIVED` warnings are still present in the log history. | Pre-existing entropy warnings remain a residual risk, but the direct harness did not create a new loop. |

## Interpretation

The enablement is functionally proven. The only incomplete piece is a live non-flat account snapshot from the restarted app slice; the direct harness already proves the portfolio economics branch once a fresh tick and an open position are present.
