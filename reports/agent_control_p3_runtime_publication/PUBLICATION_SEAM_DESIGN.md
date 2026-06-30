# Publication seam design

Aurora now has an internal, fixed-name atomic publication seam at `ops/agent_bridge/runtime/`. It is not a Cockpit contract: Cockpit still uses only `GET /agent-feed/v0/packet`.

The main-process publisher subscribes to `EVT:FEATURES_CALCULATED` and `EVT:REGIME_DETECTED`, reads allowlisted execution diagnostics, and writes three schema-tagged files:

- `market_snapshot_v0.json` (`agent-market-runtime/v0`);
- `execution_readiness_v0.json` (`agent-execution-readiness-publication/v0`);
- `publication_index_v0.json` (`agent-bridge-publication-index/v0`).

Writes use a same-directory unique temp file, compact JSON, flush + fsync, `os.replace`, Windows contention retry, and best-effort parent-directory fsync. Each file is capped at 256 KiB and validated on read. The reader never trusts a path from the index; filenames are fixed.

Reducer priority is now: valid atomic publication, safe in-process runtime object, bounded disk fallback, explicit missing. Each card reports `runtime_publication`, `runtime_object`, `bounded_disk_fallback`, `mixed`, or `missing`.

Because the active Aurora main processes predated this code and no safe no-order restart mode exists, P3 used a publication-only relay over the already main-owned `alpha_input_v1_live.jsonl`. The relay reads only the last 2 MiB / 1,000 lines and publishes the same schemas. Direct main-process wiring will activate on a future operator-controlled restart. No restart or WAL deletion occurred in P3.
