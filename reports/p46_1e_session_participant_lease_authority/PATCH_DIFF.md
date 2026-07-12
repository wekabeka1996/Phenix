# Patch Diff

## FACTS

- Config: strict `AgentAuthorityPolicyConfig` plus explicit YAML policy.
- Runtime: canonical authority contracts/store/provider, V2 rejection/idempotency handling, main composition injection.
- Tests: authority lifecycle, roles, lease conflict/expiry/version, V2 positive/negative command boundary, strict config fixtures.
- Reports: ten package files plus one coordination report.

Exact committed paths and stats are available from the P46-1E commits; no Cockpit, FSM, adapter, provider, or exchange source was changed.

## INFERENCES

- The patch is additive except for narrow V2/main composition wiring.

## ASSUMPTIONS

- Existing V1 compatibility remains temporarily required.

## UNKNOWNS

- None affecting the reported command-boundary proof.
