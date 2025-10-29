# Architecture
- FSM Core (hot/warm/cold paths), Meta-FSM
- Domain FSMs: risk_strategy, execution_position, audit_xai
- DR: WAL (append-only JSONL with hash-chain), Snapshots, Merkle-root, Replay
- Observability: JSON logs, standardized log line, tracing (rid/span), /debug
- Security: ed25519 signing for CMD/DEC, RBAC/ABAC, redaction
- Data-by-reference: signed URLs (stub)
