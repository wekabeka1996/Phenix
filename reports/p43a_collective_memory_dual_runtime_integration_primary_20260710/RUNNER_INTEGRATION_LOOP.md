# J6-S4 — Runner Integration Loop

## Timing Logic
The agent turn loop evaluates actions sequentially:
1. Emit heartbeats to the collective store.
2. Renew symbol leases for configured symbols.
3. Fetch the current collective state version.
4. Construct context envelope containing own portfolio, open positions, and peer publications.

## Dispatch-In-Doubt Guard
To prevent duplicate actions during network timeouts or slow FSM responses:
- If a command is found with `dispatch_state == "dispatch_started"`, subsequent trading actions on that symbol are strictly blocked until the FSM confirms or rejects the state.
