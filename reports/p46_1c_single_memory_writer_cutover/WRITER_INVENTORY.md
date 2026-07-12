# Writer Inventory

## FACTS

| File / surface | Class or function | Operation | Runtime reachability | Storage source | Classification |
|---|---|---|---|---|---|
| `sessions/collective_memory.py` | `CanonicalMemoryStore.append/read/recover/summarize/carryover` | append/read/recover/summarize | dashboard and lifecycle harness via runtime adapter | validated YAML + config-root resolver | `CANONICAL_WRITER` |
| `sessions/canonical_memory_runtime.py` | `CanonicalMemoryRuntime` | typed append/read/finalize | active dashboard and harness | injected canonical store | `CANONICAL_WRITER` adapter; no second persistence |
| `dashboard/app.py` | agent-memory and rationale routes | append/read/summarize | active FastAPI routes | settings canonical root | `CANONICAL_WRITER` consumer |
| `sessions/agent_order_lifecycle_harness.py` | `_finalize_trace_and_reflect` | append decision | reachable diagnostic harness | explicit absolute root + config | `CANONICAL_WRITER` consumer |
| `sessions/agent_memory_lifecycle.py` | `LegacyAgentMemoryReader` | read only | no active construction | explicit absolute root | `READ_ONLY_COMPATIBILITY` |
| `sessions/store.py` | `SessionStore` | chat session/turn/event writes | active dashboard/chat | sessions config | separate chat identity/event store |
| `sessions/memory_atoms.py` | `MemoryAtomStore` | retrieval index append | active workbench memory search | memory path config | separate retrieval index |
| `sessions/compressor.py` | `ContextCompressor` | session-spine append | active only when compression invoked | workbench root | derived chat-context summary, not trading-memory truth |
| `sessions/decision_ledger.py` | `DecisionLedger` | workflow decision update | dashboard workbench | workbench root | separate workflow store |
| artifact/attachment/approval/report stores | respective stores | domain writes | active routes | existing workbench roots | non-memory domain stores |
| `sessions/agent_action_audit.py` and lifecycle trace JSONL | audit functions | append audit evidence | event/harness paths | existing audit paths | audit evidence, not agent-memory writer |

## INFERENCES

- Class presence alone does not establish authority; construction and call paths identify the two canonical consumers and zero legacy writer consumers.

## ASSUMPTIONS

- External untracked code does not instantiate deleted legacy write methods.

## UNKNOWNS

- Third-party callers outside this repository were not observable.

