# Security / RBAC / Signing
- ed25519 signatures for CMD/* and DEC/*
- KMS stub derives deterministic key from seed (dev-only)
- RBAC: admin tokens via `RBAC_ADMIN_TOKENS` env list
- Redaction: sensitive fields masked in logs/debug
