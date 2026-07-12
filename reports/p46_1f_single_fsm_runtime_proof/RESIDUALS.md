# Residuals

## FACTS

- Legacy V1/EZE code remains source-compatible but inactive under production YAML.
- Terminal dual-agent runner contains historical `fsm_ref` instrumentation and is not constructed by Aurora main.
- Idempotency stores are process-local and do not prove restart deduplication.
- V2 context ACK remains explicitly deferred from P46-1E.
- Recording adapter was not called because the accepted DEC ran in shadow mode.

## INFERENCES

- Next package should add durable ingress idempotency before exchange runtime proof.

## ASSUMPTIONS

- Legacy execution routes remain disabled through rollout.

## UNKNOWNS

- Non-shadow recording-adapter submission behavior remains unproven.
