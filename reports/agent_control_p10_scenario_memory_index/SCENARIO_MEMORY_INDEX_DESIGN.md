# Scenario Memory index design

- Source: append-only `ActionReviewV1` JSONL.
- Identity: SHA-256 of exact ledger bytes.
- Selection: latest schema-valid, lint-valid revision per review id.
- Invalid rows: excluded, counted and reported.
- Content: counts, symbols/horizons, expected/realized matrix, latest reviews/lessons, calibration and retention.
- Persistence: bounded 128 KiB, fsync and atomic replace.
- Current index: 1 review, 1 completed, 0 unresolved, 2,224 bytes, validation `valid`.
