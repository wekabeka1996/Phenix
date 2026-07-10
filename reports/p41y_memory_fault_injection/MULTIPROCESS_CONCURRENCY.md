# Multiprocess Concurrency

The harness uses `multiprocessing.get_context("spawn")`; it does not use threads as a substitute.

- Two writers run as independent Python processes.
- `api_agent_01` writes `ETHUSDT`; `cli_agent_01` writes `XRPUSDT`.
- Each process writes 30 publications with distinct idempotency keys.
- Final evidence sequences are exactly `1..N`, event IDs are unique, and all 60 publications are present.
- A process killed while holding the lock leaves a stale lock file. After the configured stale interval, a new writer removes it and proceeds.
- A live Windows lock that exceeds the age threshold is no longer unlinked: `PermissionError` is treated as active contention and retried.

Reliability repetition: the complete 14-test fault suite passed three additional consecutive runs.
