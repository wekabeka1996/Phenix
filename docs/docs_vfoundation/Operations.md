# Operations (DR/Replay/Degradation)
- WAL location: `ops/wal/*.jsonl`
- Snapshots: `ops/snapshots/{domain}/...json`
- Replay API: `GET /replay/{rid}` (RBAC protected)
- Degradation modes: drop INQUIRY intents, reduce_only in execution_position
