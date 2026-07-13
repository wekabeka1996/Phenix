# HTTP API

## FACTS
- `GET|HEAD /read-model/v1/health`.
- `GET /read-model/v1/sessions/{session_id}`.
- Focused GET suffixes: `participants`, `leases`, `context`, `lifecycle`.
- Unknown session is 404; unavailable authority is 503; invalid/missing auth is 401/403.
- POST on the aggregate route returns 405. No PUT/PATCH/DELETE route exists in this namespace.

## INFERENCES
- The API is additive and does not create an execution ingress.

## ASSUMPTIONS
- Clients negotiate supported schema versions out of band through health/config.

## UNKNOWNS
- Rate limiting for GET is inherited from host/deployment and not added here.
