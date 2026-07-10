# Agent Tool Contract

All tools have Pydantic input/output schemas, explicit permission, symbol scope, timeout, retry policy, idempotency behavior, audit fields, and failure classes in the runtime registry.

| Tool | Permission | Scope | Effect |
|---|---|---|---|
| GET_MARKET_CONTEXT | read | owned | Bounded market/regime publications |
| GET_FEATURES | read | owned | Feature-trust state |
| GET_PORTFOLIO_STATE | read | all | Shared portfolio state |
| GET_OWN_POSITIONS | read | owned | Positions filtered by ownership |
| GET_PEER_PUBLICATIONS | read | all | Cursor-based peer feed |
| READ_COLLECTIVE_MEMORY | read | all | Bounded shared snapshot |
| PUBLISH_OBSERVATION | publish | owned | Append shared observation |
| PUBLISH_RISK_WARNING | publish | owned | Append critical warning |
| WRITE_PRIVATE_REFLECTION | private_write | none | Own private memory only |
| ASK_SUBAGENT | publish | owned | Record registered review request |
| REQUEST_ORDER | command | owned | Record `pending_fsm`; sizing ref required |
| REQUEST_CANCEL | command | owned | Record `pending_fsm` |
| REQUEST_CLOSE | command | owned | Record `pending_fsm` |
| EMIT_SOS | publish | owned | Record critical SOS event |
| ACK_INSTRUCTIONS | ack | none | Persist instruction version ACK |

No tool accepts raw order objects, credentials, quantity/notional/leverage fields, or exchange clients. Extra input fields fail validation.
