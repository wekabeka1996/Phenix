# Post-Cleanup Discrepancies

Only hard mismatches, false claims, unresolved contradictions, broken guardrails, stale docs, or leftover dead code/tests are listed here.

| Discrepancy | Evidence | Impact |
|-------------|----------|--------|
| `config/README.md` still claims runtime overlays are applied at load time | `config/README.md:10,30` vs `tests/infrastructure/test_config_safety.py:277-343` | README lies about active runtime behavior |
| `config/README.md` says `config/aurora/` is the only canonical runtime config directory, but `main.py` also loads alpha-search config | `config/README.md:28-30`; `apps/reference/main.py:892-893` | "Single runtime config truth" claim is too broad |
| `ConfigLoader` still has hidden test-config fallback | `apps/reference/config_loader.py:126-142` | Ambient filesystem can change config root selection |
| Tooling config maps still reference removed `config/aurora/aurora_instruments.yaml` | `tools/config_default_path_map.yaml:107-206`; `tools/docs_gen/config_default_path_map.yaml` same pattern | Hidden stale config truth in docs/tooling |
| FE active docs still reference nonexistent `config/aurora/features.yaml` | `apps/reference/domains/feature_engineering/docs/ARCHITECTURE.md:23`; `.../QUALITY_AND_DEBT.md:13` | Active docs are stale on config ownership |
| DM README still says `EVT:EXPOSURE_SUMMARY_UPDATED` comes from risk_management | `apps/reference/domains/decision_making/README.md:92` vs `apps/reference/domains/decision_making/domain_dict.json:9` and `apps/reference/dictionaries/verb_registry_v1.yaml:132-137` | "Authoritative" DM docs contradict repo truth |
| DM events doc and EP ATLAS still disagree with registry/domain_dict on exposure boundary | `apps/reference/domains/decision_making/docs/EVENTS.md:14`; `apps/reference/domains/execution_position/docs/ATLAS.md:73` | Boundary cleanup not fully reflected in docs |
| Contract registry coverage is still incomplete | Direct audit run of `pytest -q tests/vfoundation/test_verb_registry_warn_only.py -s`: `coverage=83.951%`, `runtime_not_in_registry=13`, `registry_not_in_runtime=20` | Contract SSOT is not fully real yet |
| Canonical registry still contains non-deprecated `owner: unknown` entries | `apps/reference/dictionaries/verb_registry_v1.yaml:101-105`, `320-324` | Ownership truth remains unresolved |
| Side contract dictionary remains stale | `vfoundation/dictionaries/domains/domain_execution_position.yaml:34-58` | Hidden parallel contract truth persists |
| Test-suite reclassification report still says `test_binance_adapter_session.py` is xfail/flaky | `reports/tests/TEST_SUITE_RECLASSIFICATION_2026-03-15.md:85` vs `reports/cleanup/TEST_HYGIENE_NORMALIZATION_2026-03-15.md:11-27` and `tests/units/test_binance_adapter_session.py:1-46` | Report layer contradicts repo reality |
| Stale generated docs still reference deleted events/modules | `docs/PROJECT_ATLAS.md:493-517,823,845-846,995-996`; `ASYNC_AUDIT_REPORT.md:171-172` | Cleanup left false active references behind |
| Tracked root junk remains | `git ls-files =0.110.0 shadow_test.py tmp_all_config_usages.txt tmp_audit_config.py tmp_config_usages.txt tmp_config_usages2.txt tmp_drift_report.txt` | Repo still carries obvious cleanup residue |
