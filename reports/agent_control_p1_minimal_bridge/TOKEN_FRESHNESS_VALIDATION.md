# Token and freshness validation

The exporter serializes compact UTF-8 JSON and estimates tokens as `ceil(bytes / 4)`. Metadata is stabilized iteratively so its own digit widths are included. Default and maximum budget is 4,400 tokens. Requests below 1,500 are rejected by query validation because the fixed typed envelope cannot be honestly guaranteed below that cap.

If needed, reduction proceeds in a declared order: warning tail, position tail, additional feature cards, additional symbol cards, packet diagnostics, and raw-ref tail. Every reduction sets `truncated=true` and records an `omitted_sections` label. The endpoint fails with 503 if the cap still cannot be met.

Observed offline generation for BTCUSDT and ETHUSDT was 7,943 compact bytes and 1,986 estimated tokens, with no truncation. The sanitized sample is 4,420 compact bytes and 1,105 estimated tokens.

Each card carries independent freshness. Missing snapshots remain visible via `missing_fields`, `snapshot_missing`, an advisory readiness warning, and a missing feature-card freshness state. Packet-level counts and oldest source age are reported; stale data is not silently upgraded.
