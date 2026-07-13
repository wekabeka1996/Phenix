# Validation

## FACTS
- Focused read-model/config: 11 passed.
- Authority/V2/FSM/S1/S2 regression group: 70 passed.
- Routes/bridge/config/registry group: 87 passed, 1 unrelated legacy Windows subprocess import-path failure in `agent_intent_dry_run.py`.
- The new strict read-model config initially exposed five old main-bridge fixtures that rebuilt `domains.yaml`; fixtures now copy the explicit policy and all those tests pass.
- Cross-repository real HTTP proof: passed.
- `git diff --check`, secret scan, and excluded-path scan: passed.

## INFERENCES
- No regression attributable to P46-2C remains in validated surfaces.

## ASSUMPTIONS
- The legacy script import issue is environment/path related and outside changed code.

## UNKNOWNS
- Full repository suite was not run; broad affected subsets were run.
