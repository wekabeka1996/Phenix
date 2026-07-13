# Bootstrap Manifest

## FACTS

- `config/agent_authority_deepseek_testnet.yaml` is a prior agent policy, not a complete Trading Floor runtime bootstrap contract.
- `config/p42_dual_agent_mvp.yaml` describes two agents but not canonical memory ownership, snapshot publication, or lifecycle projection.
- `config/project_capsule.yaml` is project guidance, not runtime authority SSOT.
- Production creates an empty authority store and does not seed it through `create_session`, `register_participant`, or `acquire_lease`.

No YAML/Pydantic manifest was added because its memory-owner field cannot be truthfully selected before ownership migration is approved.

## INFERENCES

Adding a manifest now would encode an unresolved authority decision as configuration.

## ASSUMPTIONS

The eventual manifest must be additive, testnet-only, strict, and contain no sizing values.

## UNKNOWNS

Canonical runtime ID and deployment storage root for the main process.
