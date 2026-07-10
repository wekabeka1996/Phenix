# Common Runtime Interface

```text
TradingAgentRuntime
  start_session(session_id) -> RuntimeHealth
  submit_turn(TradingTurnContext) -> TradingResponse
  cancel_turn(turn_id) -> bool
  health() -> RuntimeHealth
  shutdown() -> None
```

`OpenAICompatibleTradingAgentRuntime` and `RestrictedCLITradingAgentRuntime` implement this same boundary. The boundary returns only `TradingResponse` or explicit failure responses with `REQUEST_REVIEW`, `error_code`, and provider/CLI state. It never returns arbitrary model text and never calls FSM/exchange code.

Runtime states distinguish `READY`, provider/process blocks, timeout, cancellation, crash, and clean shutdown. Runtime construction is explicit by `build_trading_agent_runtime`; missing provider configuration raises instead of selecting a fallback.

