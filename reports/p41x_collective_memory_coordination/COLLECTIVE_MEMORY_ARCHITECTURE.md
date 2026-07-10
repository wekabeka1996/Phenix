# Collective Memory Architecture

## Storage Layout

```text
.agent_memory/sessions/<session>/coordination/
  arena_evidence.jsonl
  collective_state.json
  checkpoints/<checkpoint>.json
  private/<agent>/private_reflections.jsonl
  private/<agent>/checkpoints/<checkpoint>.json
```

- `arena_evidence.jsonl` is authoritative, append-only evidence.
- `collective_state.json` is an atomic, rebuildable read model with optimistic version equal to the latest sequence.
- Private records are agent-scoped; peer read/write attempts fail.
- Shared publications carry bounded summaries and source references, never private reasoning blobs.
- Portfolio, feature trust, instruction version, heartbeat, lease, cursor, and pending-command state are versioned in the collective snapshot.

Writes acquire one session lock, append evidence, derive state, then atomically replace the read model. If a crash occurs after append, the next read replays missing events.
