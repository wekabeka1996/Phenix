# Package 1 Plan

## Baseline
- `tools/migrations/dm_split/baseline_pytest.txt`

## Import-Rewrite
- `tests/runtime/test_no_runtime_config_fallbacks.py`

## Contract / Metadata Update
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `tests/ops/test_verb_registry_contracts.py`
- `apps/reference/domains/decision_making/domain_dict.json`

## Public Surface Narrowing
- `apps/reference/domains/decision_making/__init__.py`
- `apps/reference/domains/decision_making/decision_making.py`

## Delete
- `apps/reference/domains/decision_making/deferred_scheduler.py`
- `tests/domains/decision_making/test_deferred_intent_scheduler_timebase_v1.py`

## Documentation Add / Update
- `docs/contracts/REJECT_TRUTH_SPLIT.md`
- `apps/reference/domains/decision_making/docs/API_DEPENDENCIES.md`
- `apps/reference/domains/decision_making/docs/DOMAIN_DOCUMENTATION_DECISION_MAKING.md`

## Guardrail Test Add
- `tests/domains/decision_making/test_reject_truth_inventory.py`

## Reporting
- `tools/migrations/dm_split/artifacts/PACKAGE_1_REPORT.md`
- `tools/migrations/dm_split/artifacts/PACKAGE_1_REPORT.json`
- `tools/migrations/dm_split/artifacts/PACKAGE_1_REPORT_BLOCKED_1_3_2026-04-24.md`
- `tools/migrations/dm_split/artifacts/PACKAGE_1_REPORT_BLOCKED_1_3_2026-04-24.json`
