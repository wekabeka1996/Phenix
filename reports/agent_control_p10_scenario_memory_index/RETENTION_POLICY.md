# Retention policy

- Keep every full raw ledger row in P10.
- Index only the latest valid revision per review id.
- Keep unresolved reviews query-visible.
- Exclude invalid/lint-failing rows but report their count and line-safe error class.
- Perform no silent deletion or in-place compaction.
- Recommend additive archival when the ledger reaches 3 MiB or 10,000 rows.
- Require a separate report, hash continuity and rollback path before future rotation.

Current state: 2 raw rows, 2 valid, 0 invalid, 5,429 bytes; archival not recommended.
