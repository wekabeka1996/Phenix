# Selective Port Matrix

## FACTS

| Path/module | Source -> target | Category | Reason / intended owner | Package |
|---|---|---|---|---|
| React chat, approvals, attachments, provider gateway, subagents | Cockpit -> Cockpit | `KEEP_FROM_MAIN_COCKPIT` | core operator/orchestration UX | P46-2B |
| 14-file Agent Feed/Dry Run package | primary snapshot -> Cockpit | `PRESERVE_PRIMARY_SNAPSHOT` | bounded read-only projection | preserved now; review P46-2B |
| `CanonicalMemoryStore` implementation | Phenix -> Phenix | `KEEP_IN_PHENIX_ONLY` | single trading-memory writer | none |
| memory/context DTOs and source refs | Phenix -> Cockpit client | `ADAPT_CONTRACT_ONLY` | display bounded context without dual writer | P46-2C |
| TradingSession/participant/lease client | Phenix API -> Cockpit | `ADAPT_CONTRACT_ONLY` | Phenix remains authority | P46-2D |
| AgentTradeIntentV2 client | Phenix API -> Cockpit | `ADAPT_CONTRACT_ONLY` | no qty/notional/leverage | P46-2E |
| lifecycle/reconciliation views | Phenix API -> Cockpit | `ADAPT_CONTRACT_ONLY` | venue truth remains Phenix | P46-2F |
| Cockpit `SessionStore` | Cockpit -> Cockpit | `KEEP_FROM_MAIN_COCKPIT` | operator chat presentation only | P46-2B boundary tests |
| Cockpit `MemoryStore` | Cockpit -> Cockpit | `REQUIRES_MANUAL_REVIEW` | retain non-trading memory only; name/authority collision | P46-2C |
| Cockpit SQLite runtime store | Cockpit -> Cockpit | `KEEP_FROM_MAIN_COCKPIT` | UI/runtime cache, never venue truth | P46-2B |
| `TradingAgentStore` and V1 decision flow | Cockpit | `DELETE_OR_ISOLATE_DUPLICATE` | accepts model `qty`, V1 authority conflict | P46-2E |
| token usage receipts | provider/Cockpit/Phenix | `ADAPT_CONTRACT_ONLY` | receipt attribution and display | P46-2G |
| context compression | Phenix contract -> Cockpit | `ADAPT_CONTRACT_ONLY` | request source-bound compact context | P46-2C |
| CLI participant protocol | Phenix -> CLI client | `KEEP_IN_PHENIX_ONLY` | restricted participant boundary | later CLI package |
| local Agent Feed packet cache | Cockpit -> Cockpit | `KEEP_FROM_MAIN_COCKPIT` | cache/projection only | P46-2B |

## INFERENCES

The existing React Cockpit is retained; integration should be contract-by-contract and remove V1 execution authority before enabling V2 actions.

## ASSUMPTIONS

Read-only Agent Feed contracts remain compatible enough to review additively.

## UNKNOWNS

Whether the preserved V0 read projection is retained unchanged or versioned alongside V2 is a P46-2B decision.
