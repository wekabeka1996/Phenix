# Current Runtime Chain

## Real Aurora Path

1. `AgentTradeDecisionToSignalMapper.map_decision()` maps a validated decision to `EVT:STRATEGY_SIGNAL_PRODUCED` in `apps/reference/domains/agent_bridge/deepseek_to_fsm_adapter.py:20`.
2. DecisionMaking registers that event at `apps/reference/domains/decision_making/core/facade.py:362` and the gateway emits `EVT:TRADE_INTENT_PROPOSED` after gates (`strategy_gateway.py:1519`).
3. ExecPosFSM listens for the trade intent at `apps/reference/domains/execution_position/fsm.py:574`.
4. The intent router maps normal intents to `CMD:OPEN` (`flows/open/intent_router.py:101`).
5. Open execution calls the configured adapter's `place_market_entry` or `place_limit_entry` (`flows/open/open_executor.py:428`, `:1060`).
6. Adapter initialization constructs `BinanceAdapter` only after explicit mode and credential checks (`adapters/adapter_init.py:52`, `:170`).

## Shadow/Harness Path

`agent_order_lifecycle_harness.py:122` constructs `ExchangeACL(shadow_mode=True)` yet labels its result `submitted_testnet`/`exchange_ack` at lines 139/143. This harness is useful contract evidence, not venue proof.

P41X does not alter either path. Agent tools record commands and expose an explicit FSM callback boundary; they never import an exchange adapter.
