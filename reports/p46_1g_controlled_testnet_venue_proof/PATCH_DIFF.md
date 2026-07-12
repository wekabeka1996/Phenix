# Patch Diff

## FACTS

- Added strict proof-only YAML/Pydantic configuration.
- Added read-only credential/endpoint gate that cannot instantiate the adapter or call the network.
- Added tests for endpoint, caps, cleanup, unknown fields, missing credentials, and live-credential contamination.
- Added blocked evidence reports; no adapter/FSM/execution source changed.

## INFERENCES

- The patch prepares a safe rerun without pretending to implement venue proof.

## ASSUMPTIONS

- Future runner work remains bounded to the canonical path.

## UNKNOWNS

- No implementation beyond preflight is validated.
