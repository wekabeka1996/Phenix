# Runtime Path Inventory

## FACTS

| Surface | Owner / construction | Boundary | Identity / verb |
|---|---|---|---|
| HTTP V2 | `create_shadow_telemetry_app` | API process | `client_intent_id` |
| TCP client/server | `JsonlTcpQueueClient` / `LLMIntentIngressBridge` | loopback TCP | `request_id` |
| Authority | `TradingSessionAuthorityStore` | main process | session/participant/lease |
| Sizing | `PositionQueriesSizingAdapterV2` | main process | `sizing_decision_id` |
| Registry | `VerbSchemaRegistry` + `FSMCore` | main process | `CMD:EXTERNAL_OPEN_REQUEST_V1` |
| Command handler | `ExecPosFSM._on_external_open_request` | main process | one listener |
| FSM ingress | `IntentRouter` -> `ExecPosFSM.handle` | main process | `CMD:OPEN` |
| Venue boundary | recording adapter | external boundary | network disabled |

## INFERENCES

- `domain_builder.py` has conditional construction branches, not simultaneous FSM owners.

## ASSUMPTIONS

- Main composition continues using `build_live_domains` as the canonical construction owner.

## UNKNOWNS

- Live-process object IDs are ephemeral and not durable trace identifiers.
