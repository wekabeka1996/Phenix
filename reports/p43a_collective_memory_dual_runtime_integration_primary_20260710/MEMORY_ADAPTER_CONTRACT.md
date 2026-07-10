# J6-S4 — Memory Adapter Contract

The memory adapter boundary isolates private information while sharing trade intentions and metrics.

## Private Folder Isolation
- Path: `coordination/private/<agent_id>/`
- Access Control: Only the owner agent can read/write private reflections and checkpoints. Injected via `actor_agent_id` context check.
- Leakage Prevention: Cockpit view API can only count reflections (`reflection_count`) without displaying content details.

## Peer Publication Stream
- Path: `coordination/events.jsonl`
- Broadcast Rule: Shared publications are published to the main stream and become visible to other agents on subsequent turns.
