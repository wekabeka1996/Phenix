# Compatibility Handshake

S1 validates correlation, runtime identity, environment, schema, and runtime generation when a complete handler exists.

Production cannot truthfully return all S2 readiness flags as true:

```yaml
session_authority_available: false  # store exists, authoritative session state is not published
context_reader_available: false
lifecycle_reader_available: false
account_snapshot_reader_available: false
market_snapshot_reader_available: conditional
pure_exposure_preview_available: conditional
dry_run_available: false
```

Therefore the existing typed unavailable response is retained. TCP reachability is not reported as authority health.
