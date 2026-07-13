# Dry-Run Contract

## FACTS
- Proposal supports explicit OPEN intent only and rejects unknown/recursive money, raw exchange, and credential fields.
- Pure mapper preserves session, participant, side, rationale, confidence, horizon, context ACK, evidence, lease, and proposal identity.
- Mapper output contains no quantity, notional, leverage, or margin field.
- Result is frozen, versioned, immutable per proposal ID, and always `execution_state=DRY_RUN_ONLY`.
