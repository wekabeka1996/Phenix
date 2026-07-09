# Runtime Call Contract

## FACTS

Callable:

`run_instruction_preflight_for_agent(session_store, root_dir, agent_id, agent_number, session_id)`

Returns:

- `agent_id`
- `agent_number`
- `session_id`
- `manifest_version`
- `changed_files`
- `missing_files`
- `refresh_event_id`
- `ack_event_id`
- `ack`
- `status`
- `recommended_cadence_seconds`

Events:

- `INSTRUCTIONS_REFRESHED`
- `INSTRUCTIONS_ACKED`

Refresh events include the current manifest snapshot and changed/missing files.
ACK events include agent identity, session identity, manifest version, acknowledged timestamp, status, and manifest snapshot.

## INFERENCES

- The stored manifest snapshot lets the next cycle compare hashes without a separate database table.
- Appending ACK every cycle gives Agent 5 and the operator an attributable heartbeat without duplicating refresh events.

## ASSUMPTIONS

- Caller owns scheduling. Recommended MVP cadence is 300 seconds.
- Caller can invoke immediately when a filesystem watcher or polling layer suspects changed Markdown.

## UNKNOWNS

- No live scheduler wiring is proven.
- No operator dashboard view for ACK staleness exists in this package.
