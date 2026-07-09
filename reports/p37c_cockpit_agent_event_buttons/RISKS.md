# Risks

- FSM handoff is not implemented; testnet command requests are recorded as pending_fsm.
- Registry is YAML + Pydantic, but it is package-local rather than shared with Aurora FSM runtime.
- GET listing projects agent_arena.* records from the existing session event JSONL ledger.
- Payload shape is intentionally narrow by forbidden-key guards, but downstream FSM schema validation remains future work.
