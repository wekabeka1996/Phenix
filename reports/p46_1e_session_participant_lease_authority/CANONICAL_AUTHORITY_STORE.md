# Canonical Authority Store

## FACTS

- `TradingSessionAuthorityStore` is the only new authority owner and requires explicit policy plus clock.
- Operations: create/read/activate/pause/close session; register/read participant; acquire/renew/release lease; resolve owner; validate execution authority.
- Same-record creation/acquisition is idempotent; conflicts fail closed.
- Lease acquisition requires an enabled main participant, session membership, session symbol, exact configured TTL, explicit ID, and explicit version.
- Expiry uses the injected clock with no grace period.
- Decisions retain session, participant, agent, symbol, lease/version, intent, config, timestamp, and rejection.

## INFERENCES

- One process-local lock is adequate for current scope but not distributed proof.

## ASSUMPTIONS

- Authority state is intentionally distinct from CanonicalMemoryStore evidence.

## UNKNOWNS

- Durable authority persistence/recovery remains a later package.
