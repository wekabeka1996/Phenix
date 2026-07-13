# Phenix Runtime Mechanism Inventory

## FACTS

| Mechanism | Canonical files/symbols | Proven surface | Future ownership | Strategy |
|---|---|---|---|---|
| Canonical memory | `sessions/collective_memory.py::CanonicalMemoryStore`, `canonical_memory_runtime.py` | append, recover, summary, carryover tests | Phenix | `EXPOSE_AS_PHENIX_API` |
| Memory models/config | `collective_memory_models.py`, `collective_memory_config.yaml` | typed records, checkpoint/source references | Phenix | `KEEP_PHENIX_ONLY` |
| Trading turn context | `trading_agent_runtime.py::TradingTurnContext.compact_payload` | bounded deterministic payload tests | Phenix | `EXPOSE_AS_PHENIX_API` |
| Provider token receipt | `trading_agent_runtime.py::TokenUsage`, `_token_usage_from_response` | prompt/completion/total extraction tests | provider adapter, displayed by Cockpit | `ADAPT_TO_COCKPIT` |
| Summary/carryover | `CanonicalMemoryStore.summary/carryover` | deterministic read model | Phenix | `EXPOSE_AS_PHENIX_API` |
| Checkpoint/replay | collective-memory models/store and recovery tests | durable recovery/source references | Phenix | `KEEP_PHENIX_ONLY` |
| Instruction version | instruction manifest/runtime plus turn context | preflight/ACK tests | Phenix authority; Cockpit display | `EXPOSE_AS_PHENIX_API` |
| Idempotency/restart | canonical memory plus V2/bridge/FSM tests | duplicate suppression and replay | Phenix | `KEEP_PHENIX_ONLY` |
| Provider timeout/retry | `trading_agent_runtime.py` API/CLI runtimes | timeout, retry, cancellation tests | Cockpit provider gateway or Phenix restricted client by participant type | `ADAPT_TO_COCKPIT` |
| Restricted CLI protocol | `trading_agent_runtime.py` CLI transport | allowlist and process failure tests | CLI participant client | `REIMPLEMENT_FROM_CONTRACT` |
| Session/participant/lease | `trading_session_authority.py::TradingSessionAuthorityStore` | typed authority tests | Phenix | `EXPOSE_AS_PHENIX_API` |
| V2 intent/sizing | `agent_trade_intent_v2.py`, `PositionQueriesSizingAdapterV2` | no caller quantity, authority/sizing boundary tests | Phenix | `EXPOSE_AS_PHENIX_API` |
| Registered FSM command | `CMD:EXTERNAL_OPEN_REQUEST_V1` registry/schema/handler | canonical lifecycle proof | Phenix | `KEEP_PHENIX_ONLY` |

## INFERENCES

Porting Python storage implementations into Cockpit would duplicate authority. Cockpit needs contracts and projections, not a second canonical writer.

## ASSUMPTIONS

Future APIs will preserve source references, context/config versions, and participant identity.

## UNKNOWNS

The exact API package/version for bounded context and lifecycle projections is not yet selected.
