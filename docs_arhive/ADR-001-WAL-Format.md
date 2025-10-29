# ADR-001: WAL Format
- JSONL per day, append-only, hash-chain per record, daily Merkle-root file
- Pros: human-readable, easy to replay; Cons: larger than binary
