# Authority Conflicts

## FACTS

| Severity | Surface | Evidence | Required disposition |
|---|---|---|---|
| `P0_EXECUTION_AUTHORITY_CONFLICT` | Cockpit V1 trading service | `trading.ts` accepts `qty`; prompts require qty; `PhenixApiClient` posts `/intents/llm/v1` | isolate/replace with V2 client before actions |
| `P0_EXECUTION_AUTHORITY_CONFLICT` | manual close/amend controls | Cockpit endpoints and service accept quantity-bearing lifecycle requests | route through approved V2/canonical lifecycle contracts only |
| `P1_MEMORY_OR_TOKEN_SSOT_CONFLICT` | Cockpit `MemoryStore` vs Phenix canonical memory | both can persist memory-like state | scope Cockpit store to non-trading/operator memory; no dual write |
| `P1_MEMORY_OR_TOKEN_SSOT_CONFLICT` | local token/cost ledger | Cockpit aggregates provider usage/cost; Phenix has provider receipts/context identity | define immutable receipt and attribution contract |
| `P1_MEMORY_OR_TOKEN_SSOT_CONFLICT` | local sessions/global IDs | Cockpit creates chat sessions and uses `GLOBAL_SESSION_ID`; Phenix owns TradingSession | separate UI chat ID from execution session ID |
| `P2_INTEGRATION_DEBT` | hardcoded runtime paths/defaults | stores default to CWD `.agent_workspace/runtime_store`; some routes use fallback IDs | explicit non-authoritative runtime config |
| `P2_INTEGRATION_DEBT` | preserved feed defaults | default symbols and `max_tokens` exist in client/server | source from session/config contracts before production use |
| `P3_STALE_OR_DEAD_SURFACE` | bundled `trading_bot/` | separate exchange/risk implementation inside Cockpit repo | do not port into canonical path; isolate/archive after review |

The preserved Agent Feed and Dry Run actions are explicitly disabled and use GET-only upstream clients. They are not an execution bypass.

## INFERENCES

V1 transport proves process-safe ingress existed, but its model-sizing semantics conflict with V2 and must not be relabeled as compliant.

## ASSUMPTIONS

No hidden production caller activates disabled feed actions.

## UNKNOWNS

Runtime reachability of every historical `trading_bot/` script was not tested.
