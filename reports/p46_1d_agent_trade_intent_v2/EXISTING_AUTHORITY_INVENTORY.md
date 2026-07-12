# Existing Authority Inventory

## FACTS

| Surface | File / symbol | Current owner | Input -> output | Reachable | Money impact | Reuse |
|---|---|---|---|---|---|---|
| HTTP V1 | `shadow_telemetry/main.py`, `/intents/llm/v1` | shadow API | caller order including qty -> IPC | yes | yes | transport only |
| TCP IPC | `JsonlTcpQueueClient` / `JsonlTcpServer` | shadow telemetry | JSONL command -> main callback | yes | routing | reuse |
| Main bridge | `LLMIntentIngressBridge._on_command` | main process | IPC payload -> FSM events/commands | yes | yes | reuse/add V2 branch |
| V1 mapper | `register_llm_command_mapper` | shadow telemetry | V1 qty -> `CMD:EXTERNAL_OPEN_REQUEST_V1` | yes | yes | V2 must bypass caller sizing |
| Execution ingress | `IntentRouter.on_external_open_request` | execution_position | external command -> `CMD:OPEN` guard chain | yes | yes | reuse unchanged |
| FSM lifecycle | `ExecPosFSM` / execution_position FSM | execution_position | guarded command -> lifecycle | yes | yes | sole owner |
| Sizing | `PositionQueries.calculate_position_size` | decision_making | portfolio equity + price + instrument YAML -> qty | yes for strategy flow | yes | narrow adapter |
| Pure sizing | `sizing_margin_first.py` | shared decision primitives | explicit inputs -> notional/qty | yes through PositionQueries | yes | reused indirectly |
| Instrument truth | `config/aurora/instruments.yaml` + Pydantic | config SSOT | step/min/leverage/margin pct | yes | yes | reuse |
| Account truth | `DecisionMaking.latest_portfolio` | decision_making | portfolio events -> snapshot | yes in DM | yes | not exposed to bridge |
| Market price | `DecisionMaking.symbol_states` | decision_making | feature events -> current price | yes in DM | yes | not exposed to bridge |
| Session/participant/lease | no reusable Aurora main provider found | unknown | required authority -> validation | no | yes | blocker |

## INFERENCES

- V1 transport is process-safe but its model-owned `order.qty` violates V2 authority.

## ASSUMPTIONS

- External open ingress remains the canonical guarded execution boundary.

## UNKNOWNS

- Runtime freshness guarantees for portfolio and feature price at a future V2 adapter call remain unspecified.

