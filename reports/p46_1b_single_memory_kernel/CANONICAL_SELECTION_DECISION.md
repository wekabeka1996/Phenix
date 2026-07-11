# Canonical Selection Decision

## FACTS

Selected API: `deepseek_terminal_agent.sessions.collective_memory.CanonicalMemoryStore`.

Selected laws:

- one authoritative append-only JSONL ledger per session;
- strict monotonic sequence and globally unique record ID within that session;
- mandatory configured agent identity and explicit timestamp/instruction version;
- event, command, and source references survive read, restart, summary, and carryover;
- malformed or inconsistent ledger data fails closed;
- storage root and `CoordinationConfig` are constructor requirements;
- no `SessionStore`, legacy lifecycle, environment override, exchange client, or fallback path is instantiated.

## INFERENCES

- P41Y is the strongest source design, but copying its 1,651-line mixed coordination/execution store would exceed this task and reintroduce dashboard/FSM coupling. The selected focused port preserves its immutable-ledger and strict-recovery principles.

## ASSUMPTIONS

- Command dispatch remains outside this kernel and under registered FSM authority.

## UNKNOWNS

- The later runtime owner must choose the exact cutover transaction for active legacy sessions.

