# Partial Write Recovery

Before reading the evidence ledger under the session lock, P41Y inspects a non-newline final tail:

1. If it is a complete valid `ArenaEvidenceEvent`, a missing newline is appended.
2. If it is invalid or incomplete, the exact tail and error are written to quarantine.
3. The ledger is truncated only to the prior newline boundary.
4. The next accepted append receives the expected monotonic sequence.

The test injects `{"event_id":"partial-tail"` with no newline, then appends a valid event. The valid event remains readable, state catches up to the last sequence, and quarantine evidence exists.

This is not deletion of accepted evidence: only bytes that cannot validate as an arena event are removed from the authoritative ledger after quarantine.
