# Token and Context Compression Map

## FACTS

| Surface | Input/output | Accounting | Persistence/restart | Owner/conflict |
|---|---|---|---|---|
| Cockpit provider adapters | provider response | actual provider usage where exposed; DeepSeek maps prompt/completion/cache/reasoning | stored in runtime records where caller persists it | valid receipt source |
| `TradingAgentStore.trading_model_usage` | model call receipt | input/output/total/reasoning/cache plus estimated USD cost | local SQLite survives restart | duplicate presentation ledger, not billing SSOT |
| `PhenixTradingAgentService` | scout/decision calls | aggregates provider usage; attributes rows by call/profile/symbol/context | local Cockpit SQLite | no shared parent/subagent budget proof |
| Cockpit `ContextBuilder` | messages, attachments, accepted memory | truncates history to 50; artifact context pack | runtime storage | clipping/assembly, not trading-memory authority |
| Cockpit `SubAgentOrchestrator` | prompt/context and subagent outputs | output-length summaries; no proven parent-child token budget ledger | runtime events/results | attribution gap |
| preserved Agent Feed | Phenix read packet | `estimated_tokens`, `max_tokens_requested`, bytes, truncation metadata | local packet cache SQLite | estimate only, read projection |
| Phenix `TradingTurnContext.compact_payload` | source-bound trading context | deterministic character-bound clipping | reconstructed from canonical state | authoritative execution context projection |
| Phenix `TokenUsage` | provider response | prompt/completion/total actual fields when available | response/evidence record | provider receipt |
| Phenix canonical summary/carryover | append-only ledger | deterministic bounded read models with source IDs | ledger/recovery survives restart | authoritative trading memory |

### Required answers

1. Provider-reported tokens are extracted by provider adapters and Phenix `_token_usage_from_response`; Cockpit trading calls persist usage in `trading_model_usage`.
2. Estimated tokens are used in the preserved Agent Feed packet and other context sizing surfaces; they are not actual billing truth.
3. No single shared session budget across main and subagents is proven.
4. Subagent tokens are not proven to be attributed to a parent-call budget.
5. Cockpit `ContextBuilder` clips chat history; Phenix `compact_payload` bounds trading-turn context.
6. Phenix `CanonicalMemoryStore` owns semantic summary/carryover for trading truth; Cockpit also creates UI/runtime summaries that must remain non-authoritative.
7. Phenix carryover preserves source references; Cockpit generic summaries do not uniformly prove this.
8. Cockpit SQLite/session artifacts and Phenix canonical ledger survive restart independently; they are not unified.
9. Cockpit `trading_model_usage`, Agent Feed estimates, and Phenix provider receipts overlap but have different semantics.
10. Provider receipts are actual-usage SSOT; Phenix owns trading memory/context version; Cockpit owns display and attribution views.

## INFERENCES

Unification should use immutable provider receipts plus Phenix context references, not make local estimates authoritative.

## ASSUMPTIONS

Provider APIs may omit some usage fields; absence must remain explicit.

## UNKNOWNS

Cross-provider cost normalization and exact parent/subagent budget policy remain undecided.
