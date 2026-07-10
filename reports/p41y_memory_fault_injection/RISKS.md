# Risks

- Tests use local NTFS semantics; network-share locking and atomicity are unproven.
- `os._exit` models process death, not machine power loss or filesystem cache loss.
- Disk failure is injected at explicit storage stages; physical disk-full and I/O controller failures are unproven.
- Stale-lock cleanup depends on Windows denying unlink for a live open file; other filesystems may differ.
- Reconciliation truth is only as reliable as its source references and provider.
- `not_submitted` permits an explicit retry; operators must still pass normal lease/FSM checks.
- Structured semantic facts do not evaluate arbitrary prose, hidden implications, or model reasoning quality.
- Under more extreme budgets, active context may explicitly omit old facts; checkpoint retrieval remains the authoritative fallback.
- No external Binance testnet execution evidence was produced.
