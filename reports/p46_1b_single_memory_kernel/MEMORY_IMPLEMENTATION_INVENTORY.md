# Memory Implementation Inventory

## FACTS

| Implementation | Source | Persistence | Identity / semantics | Recovery and carryover | Decision |
|---|---|---|---|---|---|
| `SessionStore` in `sessions/store.py` | current/base history | session JSON plus turn/event JSONL | chat `session_id`; mutable session/turn projections | restart load, snapshot/export | retain as chat/session presentation store; not trading memory writer |
| `AgentTradingSessionMemory` + `AgentMemoryLifecycle` | P38D/P39D (`9474c4c9`, `b0c93c64`) | one mutable JSON document per agent plus summary/Markdown | session/agent/number; append in memory then overwrite document | load-or-create and carryover Markdown | migration input; runtime writer must be retired later |
| `MemoryAtomStore` | pre-P39 current | append-versioned JSONL | atom/source session; no mandatory agent identity | latest-version replay, lexical retrieval | retrieval index only; not canonical evidence |
| `DecisionLedger` | pre-P39 current | one mutable JSON file per decision | decision id; no mandatory agent identity | directory reload | domain workflow store; not canonical memory |
| Aurora `scenario_memory.py` | sync baseline `167671af` | agent-bridge scenario read model | scenario/session context | bridge-local reconstruction | read bridge only; no Cockpit writer authority |
| P41X `CollectiveMemoryStore` | `74fb1079` / equivalent P43A `3f2e853b` | append-only evidence JSONL plus rebuildable state/checkpoints/private ledgers | complete session/agent/event/command identity | replay/checkpoint/carryover | selected design source, reduced to focused kernel |
| P41Y hardened store | `f5cac010` | P41X layout plus partial-write/reconciliation hardening | complete identity and source references | crash/replay/reconciliation | selected hardening source, reduced to focused kernel |
| P43A projections | `ec81a448`, `c1aeb599` | derived collective-state view | presentation fields | broad fallback in source candidate | projection input only; never writer |
| P46 `CanonicalMemoryStore` | this branch | one append-only `records.jsonl` per session | mandatory session/agent/number/time/instruction/event/command refs | strict reopen/replay; deterministic summary/carryover | canonical new writer API |

## INFERENCES

- Existing stores are not interchangeable: chat turns, retrieval atoms, workflow decisions, and authoritative trading memory have different contracts.
- Dual-writing P39D mutable documents and P46 JSONL would create conflicting recovery truth.

## ASSUMPTIONS

- Legacy stores may remain temporarily for reads until explicit migration ownership is assigned.

## UNKNOWNS

- Historical artifact volume and malformed-record rate have not been measured in this task.

