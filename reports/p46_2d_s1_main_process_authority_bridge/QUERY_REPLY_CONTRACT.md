# Query/Reply Contract

Requests use `p46.authority-query.v1`; replies use `p46.authority-query-response.v1`.

Registered semantic kinds:

- `QUERY:AUTHORITY_COMPATIBILITY_V1`
- `QUERY:READ_MODEL_SESSION_V1`
- `QUERY:PROPOSAL_DRY_RUN_V1`
- `QUERY:PROPOSAL_DRY_RUN_RESULT_V1`

Every request carries request/correlation/session identity, deadline, requested timestamp, caller runtime, expected environment, and bounded payload. Every reply carries matching identity, status, generation, source runtime/environment/versions, bounded payload, and typed error.

Statuses are `OK`, `REJECTED`, `UNAVAILABLE`, `STALE`, `CONFLICT`, and `TIMEOUT`. Pydantic uses `extra="forbid"`; YAML declares endpoint, schemas, exact kinds, timeout, payload bound, and idempotency bound.
