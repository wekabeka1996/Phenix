# Operator Summary: Mean Reversion Incident

**What actually broke?**
1. **Strategy Level**: The strategy mistakenly shorted into an extreme low-volatility breakout (0.8% Bollinger Band width) because the `min_bb_width` threshold is set too low (0.005) for DOGEUSDT. It mistook a momentum expansion for a mean-reverting deviation.
2. **Execution Level**: A critical split-brain synchronization failure occurred in the execution engine. Stop-loss brackets correctly triggered on Binance Testnet, but the local `ManageFlowFSM` never received or processed the WebSocket `ORDER_UPDATED` event.

**What was just a symptom?**
- The `TTL_EXPIRED_3600s` and `ORPHANED_TTL` status were purely symptoms. Because `ManageFlowFSM` kept the position open locally but the REST-polling `PositionTracker` saw it was closed, `DecisionMaking` allowed new trades. The new trade overwrote the internal FSM state, abandoning the first trade's tracking ID. The system's garbage collector then cleaned it up exactly one hour later.
- The `Same-side pyramiding not allowed` blocks were functioning correctly, but only worked when the system accurately believed a position was open.

**What to check first in the next phase?**
1. **Execution Lock (P0)**: Review `ExecPosFSM` dictionary handling. It must never silently overwrite an `OPENED` state when receiving a new intent.
2. **WebSocket Parsing (P0)**: Verify if the BinanceAdapter is silently dropping `STOP_MARKET` fills from the Testnet User Data Stream.
3. **Quant Filter (P1)**: Increase `min_bb_width` to >= `0.015` in `mean_reversion.yaml` to prevent fading tight squeeze breakouts.