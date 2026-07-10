# J6-S4 — Lock and Execution Hazards

## Lock Contention Hazards
The concurrent write lock in `CollectiveMemoryStore` uses OS file locks (`os.O_CREAT | os.O_EXCL`). If a process crashes while holding the lock, the lock file `.coordination.lock` could be left orphaned. 
- **Mitigation**: Stale-lock checks clear locks older than 5 seconds (`lock_stale_seconds` in coordination config).

## Race Conditions in Lease Renewals
Under high execution frequencies, lease expiration check and lease write could drift.
- **Mitigation**: Lease expirations are written to the durable evidence log. Sequence validation enforces strict monotonic execution.
