# Aurora exporter notes

The exporter lives at `apps/reference/domains/agent_bridge/`, beside existing domain modules, and is registered on `apps/reference/api/main.py`, the existing FastAPI read-model host. It does not use port 7102 or the 8443 consequential surface.

Runtime-owned snapshot and execution objects are preferred when available. Disk fallback uses `bounded_tail_jsonl`: seek from EOF, read at most 524,288 bytes, retain at most 200 lines, discard an initial partial line, and tolerate malformed JSON. It never iterates a large JSONL from byte zero in the packet request path.

Available bounded fallbacks are the shadow snapshot tree, `shadow_critical_event_journal_v1.jsonl`, decision ledger, and order log. If current snapshots or runtime execution state are unavailable, cards expose missing fields and diagnostics. The exporter does not invent price, feature, lifecycle, bracket, filter, mode, or secret status.

Freshness thresholds are explicit reducer policies: market 15 minutes, portfolio/execution 2 minutes, decisions 60 minutes, with five minutes of tolerated future clock skew. These are observability classifications, not trading gates.

The current offline runtime sample produced a two-symbol packet of 7,943 compact bytes / 1,986 estimated tokens before the later missing-feature freshness correction; it remained below the 4,400-token cap. Current packet generation is covered by tests and the sanitized sample.
