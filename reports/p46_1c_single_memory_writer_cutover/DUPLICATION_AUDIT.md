# Duplication Audit

## FACTS

| Remaining occurrence | Explanation | Classification |
|---|---|---|
| `agent_memory_lifecycle.py` | historical P39D JSON reader; no write API | `READ_ONLY_COMPATIBILITY` |
| `agent_trading_memory.py` | legacy Pydantic decode/summary model used only by compatibility reader/tests | `READ_ONLY_COMPATIBILITY` |
| `SessionStore` JSONL | chat sessions, turns, arena route events | distinct chat/event store |
| `MemoryAtomStore` JSONL | lexical retrieval atoms | distinct retrieval index |
| compressor spine JSONL | derived chat context compression | derived read context; not canonical agent memory |
| lifecycle trace/audit JSONL | operational evidence and duplicate-command audit | audit ledger, not private/collective memory |
| artifact, attachment, approval, patch, report stores | bounded operator/workbench records | distinct domain stores |

Static results:

- `AgentMemoryLifecycle(` in runtime source: zero.
- imports of legacy lifecycle outside its own compatibility module: zero.
- canonical constructions: exactly two consumers, both inject `CanonicalMemoryStore` into `CanonicalMemoryRuntime`.
- canonical store contains no exchange, provider, FSM dispatch, sizing, environment gate, or legacy write fallback.
- P42N markers were not introduced.

## INFERENCES

- More than one JSONL file exists, but only one API owns authoritative agent memory records; conflating audit/chat/retrieval persistence with that authority would be inaccurate.

## ASSUMPTIONS

- Runtime discovery covers tracked Python entrypoints under `src/`.

## UNKNOWNS

- Untracked external automation cannot be proven absent from static repository search.

