# Coherence Repair

## FACTS

- Fee buffer moved from an active hidden helper default to required instrument SSOT.
- Proof margin projection now solves `target / (equity × (1-fee) × leverage)`.
- Symbol preflight evaluates step-rounded quantity against exchange minimum and Phenix clip floor.
- V2 sizing rejects stale/missing account and market timestamps.
- `config_version` and `sizing_decision_id` survive registered external-command and internal `CMD:OPEN` validation.
- ExposureManager attaches deterministic exposure decision/config lineage before reserve/dispatch.
- Existing `SoftClipEngine`, ExposureGuard calculations, risk limits, and operator cap are unchanged.

## INFERENCES

- Same account snapshot, market snapshot, config, and intent now produce deterministic sizing and exposure outcomes.

## ASSUMPTIONS

- An exposure ID reconstructed from its specified deterministic key is equivalent in identity, though not equivalent to direct runtime capture.

## UNKNOWNS

- The external bus observer capture timing remains a diagnostic limitation.
