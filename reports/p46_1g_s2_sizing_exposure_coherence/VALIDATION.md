# Validation

## FACTS

| Command | Result |
|---|---|
| S2+S1 focused tests with RuntimeWarning as error | `23 passed` |
| Expanded sizing/V2/authority/config tests | `93 passed` |
| P46-1F/FSM/recovery/startup/shutdown/registry tests | `100 passed, 14 skipped` |
| `python -m pytest tools/deepseek-terminal-agent/tests -q --tb=short` | `578 passed, 13 skipped`, 3 dev warnings |
| Python compile for proof/V2/authority modules | passed |
| Canonical Testnet proof | exit `0`; one submit, canonical cancel, final flat |
| Independent venue query | `CANCELED`, position `0`, open orders `0` |
| Secret/signature scan | no credential value or unredacted signature persisted in package outputs |
| `git diff --check` | passed before reports; repeated at closure |

## INFERENCES

- Unit/integration proof and real venue proof are separately identified.

## ASSUMPTIONS

- Development-only RBAC/signing warnings do not affect the isolated Testnet path.

## UNKNOWNS

- Skipped tests supply no evidence.
