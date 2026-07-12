# Residuals

## FACTS

- Store state is single-process and non-durable by explicit scope.
- Production starts with no hidden/bootstrap session, participant, or lease; requests fail `SESSION_NOT_FOUND` until an explicit runtime owner creates them.
- Context ACK authority is unavailable and explicitly deferred in config.
- V1 compatibility still accepts caller quantity and can emit the existing command without V2 lease checks.
- P46-1D's implicit sizing fee buffer remains outside this package.

## INFERENCES

- Next runtime package should provide explicit session lifecycle provisioning and then disable/deprecate V1 for Trading Floor agents.

## ASSUMPTIONS

- Durable/multiprocess authority is not required before that controlled runtime package.

## UNKNOWNS

- Exact durability backend and operator lifecycle surface are undecided.
