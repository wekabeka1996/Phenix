# Security

## FACTS
- Routes reuse existing shadow telemetry authorization dependency.
- Config requires explicit host, port, auth mode, runtime ID, environment, schema, freshness limits, and item bound.
- Unknown config fields fail Pydantic validation.
- No credentials, raw prompts, hidden reasoning, raw exchange payloads, or unrestricted memory dumps are projected.
- Secret scan found no matching credential material.

## INFERENCES
- Loopback is the safe default; non-loopback bearer/TLS operation remains deployment-controlled.

## ASSUMPTIONS
- Bearer values enter process environment through existing secret management.

## UNKNOWNS
- External TLS termination and credential rotation are outside repository proof.
