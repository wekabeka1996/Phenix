# Contracts and Config

## FACTS

- `TradingSession`: session/status/times/universe/participants/config/instruction version.
- `Participant`: participant/agent/type/enabled/session identity.
- `SymbolLease`: lease/session/symbol/owner/times/version.
- YAML/Pydantic policy defines complete statuses and roles, sole execution role, TTL, renewal/expiry/conflict behavior, allowed universe, horizon, intent TTL, and downstream order policy.
- All policy fields are required and `extra="forbid"`; malformed, missing, or unknown fields fail validation.
- Rejections include `SESSION_NOT_FOUND`, `SESSION_NOT_ACTIVE`, `PARTICIPANT_NOT_FOUND`, `PARTICIPANT_DISABLED`, `PARTICIPANT_SESSION_MISMATCH`, `SUBAGENT_EXECUTION_FORBIDDEN`, `PARTICIPANT_ROLE_FORBIDDEN`, `SYMBOL_NOT_IN_SESSION_UNIVERSE`, `LEASE_NOT_FOUND`, `LEASE_OWNER_MISMATCH`, `LEASE_EXPIRED`, `LEASE_CONFLICT`, and `LEASE_VERSION_CONFLICT`.

## INFERENCES

- Explicit `defer_unavailable` prevents context freshness from being misrepresented as implemented authority.

## ASSUMPTIONS

- The configured six-symbol allowlist is policy availability, not a frozen active session universe.

## UNKNOWNS

- A future runtime package must define a durable session creation source.
