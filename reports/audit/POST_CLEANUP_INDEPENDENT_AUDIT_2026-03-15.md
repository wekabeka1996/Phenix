# Post-Cleanup Independent Audit

**Date:** 2026-03-15  
**Auditor stance:** trust repo state only; do not trust prior reports.

## Operator Summary

**Safe to believe**
- `config/aurora/` is the default Aurora core runtime root in production bootstrap: `apps/reference/main.py:315`.
- `config/aurora_baseline/` and `config/mean_reversion/` are no longer active config roots; archived snapshots live under `archive/config_snapshots/`.
- WhyCode canonicalization is real: `vfoundation/core/why_codes.py` is canonical, and `apps/reference/domains/decision_making/why_codes.py:1-22` is only a compatibility re-export shim.
- All six audited domains now have root `README.md`, `domain_dict.json`, and structural/guardrail tests; targeted audit slices passed (`128 passed`, `13 passed`).
- `apps/reference/domains/market_data/market_ws_client.py` is deleted, EP production code imports `NormalizedRejectReasons` via `apps/reference/shared/types.py:1-32`, and forbidden veto-config `.get()` access in MR strategy was replaced with typed runtime config objects.

**Not safe to believe yet**
- That config SSOT is singular and fully documented honestly.
- That contract SSOT is complete or fully enforced.
- That "authoritative" domain docs can be trusted without code cross-check.
- That FE<->DM ownership is actually clean rather than wrapped behind a bridge.
- That test hygiene / purge work is complete.

## 1. Executive Verdict

**MIXED / PARTIAL**

The cleanup program produced real structural gains, but the repo is not yet in a fully controlled, architecturally honest state. The strongest improvements are real: dead config trees were moved out of the active namespace, WhyCode was consolidated, `market_ws_client.py` was deleted, EP production boundary imports were cleaned, domain-level guardrails were added, and the forbidden `.get()` config fallback in MR strategy was actually fixed.

The overclaim is in the SSOT and documentation layer. Config truth is not singular enough to justify the wording in `config/README.md`. Contract truth is not singular enough to justify "registry is canonical" without a caveat, because runtime vocabulary still outruns registry coverage and side truth layers still exist. Several files presented as authoritative are stale on exactly the boundary changes the cleanup claimed to settle. The project is cleaner than a chaotic baseline in narrow, evidence-backed ways, but not clean enough to stop auditing with grep/tests/code.

## 2. Claimed vs Verified Matrix

| Area | Claimed | Verified | Verdict | Evidence |
|------|---------|----------|---------|----------|
| Config SSOT | `config/aurora/` is the only active runtime SSOT | Core Aurora boot does load `config/aurora`, and old active trees are gone; but `config/README.md:10,28-30` still claims live overlays, `ConfigLoader` still has hidden `tests/config/aurora` fallback (`apps/reference/config_loader.py:121-142`), and `main.py:892-893` also loads `config/alpha_search.yaml` | Partial / overclaimed | `apps/reference/main.py:315,892-893`; `config/README.md:7-10,28-30`; `tests/infrastructure/test_config_safety.py:277-343` |
| Contract SSOT | `verb_registry_v1.yaml` is canonical and active contracts are covered | Registry exists and guardrails pass, but direct audit run of `pytest -q tests/vfoundation/test_verb_registry_warn_only.py -s` reported `coverage=83.951%`, `runtime_not_in_registry=13`, `registry_not_in_runtime=20`; side domain dictionaries still exist | Partial / overclaimed | `apps/reference/dictionaries/verb_registry_v1.yaml`; `tests/contracts/test_contract_ssot_guardrails.py`; `tests/contracts/test_contract_registry_audit.py`; `vfoundation/dictionaries/domains/domain_execution_position.yaml:34-58` |
| WhyCode consolidation | Canonical WhyCode is `vfoundation/core/why_codes.py`; local fork neutralized | Verified | Verified | `vfoundation/core/why_codes.py:1-37`; `apps/reference/domains/decision_making/why_codes.py:1-22`; `tests/contracts/test_contract_ssot_guardrails.py` |
| DM audit | README/domain_dict/tests authoritative and current | Files exist and guardrails pass, but DM docs are stale on `EVT:EXPOSURE_SUMMARY_UPDATED` ownership/source | Partial | `apps/reference/domains/decision_making/README.md:87-98`; `apps/reference/domains/decision_making/domain_dict.json:9`; `apps/reference/domains/decision_making/docs/EVENTS.md:10-18` |
| EP audit | README/domain_dict/tests authoritative and current | Structural reality improved and guardrails pass, but EP docs still misstate exposure event consumer/ownership | Partial | `apps/reference/domains/execution_position/docs/ATLAS.md:70-75`; `tests/domains/execution_position/test_ep_contract_boundary_guardrails.py` |
| EP boundary cleanup | Ownership/co-emitter disputes resolved; NRR routed through shared facade | Production import boundary is cleaner and guardrail passes; docs lag behind registry truth | Mostly verified with doc caveat | `apps/reference/domains/execution_position/leverage_service.py:1-13`; `apps/reference/shared/types.py:1-32`; `git grep -n "apps.reference.domains.decision_making" -- apps/reference/domains/execution_position` returned no production hits; registry lines `370-388` |
| RM audit | README/domain_dict/tests current | Mostly verified | Mostly verified | `apps/reference/domains/risk_management/README.md`; `apps/reference/domains/risk_management/domain_dict.json`; `tests/domains/risk_management/test_rm_domain_structural_guardrails.py` |
| RD audit | README/domain_dict/tests current | Structure is improved and README is comparatively honest about debt; code still carries silent defaulting via `getattr(..., 10000)` | Mostly verified with explicit debt | `apps/reference/domains/regime_detector/README.md`; `apps/reference/domains/regime_detector/regime_detector.py:305-310`; `tests/domains/regime_detector/test_rd_domain_structural_guardrails.py` |
| FE audit | README/domain_dict/tests current | Root README is materially better, but active FE docs still point to nonexistent `config/aurora/features.yaml` | Partial | `apps/reference/domains/feature_engineering/README.md`; `apps/reference/domains/feature_engineering/docs/ARCHITECTURE.md:23`; `apps/reference/domains/feature_engineering/docs/QUALITY_AND_DEBT.md:13`; `tests/domains/feature_engineering/test_fe_domain_structural_guardrails.py` |
| FE<->DM stabilization | Direct DM imports of FE strategy internals removed via `strategy_bridge.py` | Direct imports were centralized behind a bridge, but strategy code still physically lives in FE and DM still depends on it through the bridge | Partial / stabilized, not solved | `apps/reference/domains/decision_making/strategy_bridge.py:27-50`; `tests/domains/decision_making/test_fe_dm_boundary_guardrails.py` |
| MD audit | README/domain_dict/tests current | Market-data cleanup is real; deleted module is gone and exports are clean, but runtime defaults/hardcoded placeholders remain | Mostly verified with debt | `apps/reference/domains/market_data/__init__.py:11-27`; `apps/reference/bootstrap/domain_builder.py:100-103`; `apps/reference/domains/market_data/bar_aggregator.py:17,80-84`; `apps/reference/domains/market_data/websocket_aggregator.py:69,185-258,335` |
| Legacy purge wave #1 | Dead module/imports/no-ops/`__pycache__` cleaned | `market_ws_client.py` is deleted and guardrail passes, but stale docs/reports still reference deleted artifacts and root junk remains tracked | Mostly verified with leftovers | `apps/reference/domains/market_data/market_ws_client.py` absent; `tests/test_legacy_purge_wave1_guardrails.py`; `docs/PROJECT_ATLAS.md:493-517,823,845-846,995-996`; `ASYNC_AUDIT_REPORT.md:171-172` |
| Test suite reclassification | Test suite classified; dead tests removed conservatively | Report exists and many dead tests were removed, but report content is already stale/internally inconsistent and broad skip/xfail debt remains | Partial / overclaimed | `reports/tests/TEST_SUITE_RECLASSIFICATION_2026-03-15.md:11-15,37-48,81-86,128-130`; `git grep -n "@pytest.mark.xfail\\|xfail(" -- tests` |
| Forbidden config pattern fix | MR strategy no longer uses silent `.get()` fallbacks; typed runtime config introduced | Verified | Verified | `apps/reference/domains/feature_engineering/mean_reversion_strategy.py:41-60`; `apps/reference/domains/decision_making/mean_reversion_handler.py:134-148,537-541`; `tests/config/test_task53_no_silent_fallbacks_scan.py`; `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py` |
| Legacy purge wave #2 | Dead tests + empty dirs deleted conservatively | Several dead tests are deleted, but tracked root junk and stale debug/test-like artifacts still remain | Partial | `git status -sb`; `git ls-files =0.110.0 shadow_test.py tmp_all_config_usages.txt tmp_audit_config.py tmp_config_usages.txt tmp_config_usages2.txt tmp_drift_report.txt` |
| Test hygiene normalization | Stale `xfail` removed; generated artifacts untracked/gitignored | `tests/units/test_binance_adapter_session.py` no longer has xfail and passed in audit run, but the broader suite still contains 5 xfail files and the reclassification report still says this file is xfail/flaky | Partial | `reports/cleanup/TEST_HYGIENE_NORMALIZATION_2026-03-15.md:11-27,60-63`; `reports/tests/TEST_SUITE_RECLASSIFICATION_2026-03-15.md:85`; `tests/units/test_binance_adapter_session.py:1-46` |

## 3. What Is Genuinely Better Now

- Aurora core boot is anchored on `config/aurora/` in production code, not on a scatter of legacy config directories (`apps/reference/main.py:315`).
- Old active config roots were actually removed from `config/` and archived outside the active namespace, matching the narrow part of the SSOT claim.
- WhyCode consolidation is real. The DM-local file is explicitly a shim, and new imports are supposed to target `vfoundation/core/why_codes.py`.
- The six audited domains now have visible top-level ownership artifacts (`README.md`, `domain_dict.json`) and working structural/guardrail tests. That materially improves discoverability and regression detection.
- EP production code no longer imports DM directly, and `NormalizedRejectReasons` is routed through `apps/reference/shared/types.py` as claimed.
- `market_ws_client.py` is really gone, and `apps/reference/domains/market_data/__init__.py` only exports the surviving surface.
- The forbidden config fallback fix is real. Typed veto-config dataclasses exist in FE strategy code, conversion happens in DM runtime wiring, and the dedicated scan passed.
- The audit slices that should have failed if the cleanup were purely cosmetic did not fail: the structural/config/contract/boundary slice passed `128/128`; the targeted config/shared-types/session slice passed `13/13`.

## 4. Overclaims / Weak Spots / Misleading Parts

- `config/README.md` is not truthful as written. It says `config/overlays/` are applied at load time and that all runtime-impacting changes go through `config/aurora/` or `config/overlays/`, but safety tests explicitly assert the legacy overlay hook is removed.
- `config/README.md` also overstates singularity. `main.py` loads `config/alpha_search.yaml` in addition to Aurora core config, and alpha-search scenario config lives under `config/alpha_search/`.
- Contract SSOT is overclaimed. A canonical registry file exists, but a direct audit run still found 13 runtime tokens missing from the registry and 20 registry-only tokens. That is not "SSOT complete"; it is "SSOT under construction."
- `owner: unknown` remains in the canonical registry for non-deprecated entries such as `EVT:CANCELLED` and `EVT:POSITION_CLOSED` (`apps/reference/dictionaries/verb_registry_v1.yaml:101-105,320-324`).
- `vfoundation/core/payloads.py` is still a parallel contract-truth layer for payload models, including tokens that the registry audit still treats as unresolved (`CMD:CANCEL`, `ERR:REJECT`, `EVT:FILL`).
- Domain docs marketed as authoritative are not authoritative enough. DM README, DM `docs/EVENTS.md`, and EP `docs/ATLAS.md` still disagree with the registry/domain_dict on the `EXPOSURE_SUMMARY_UPDATED` boundary.
- FE<->DM cleanup is only a facade stabilization. `strategy_bridge.py` reduces import scatter, but it does not resolve conceptual ownership; DM still depends on FE-hosted strategy internals.
- Test-suite reporting overclaims freshness. The same repo contains one report saying `test_binance_adapter_session.py` is still xfail/flaky and another saying the xfail was removed. Repo reality matches the latter, not the former.

## 5. Missed Defects

- Hidden test-config fallback still exists in production loader code: `apps/reference/config_loader.py:126-142` will switch to `tests/config/aurora` if a full required set appears there.
- Tooling/docs config maps still point at dead config files such as `config/aurora/aurora_instruments.yaml` (`tools/config_default_path_map.yaml:107-206`; same issue in `tools/docs_gen/config_default_path_map.yaml`).
- FE active docs still point at nonexistent `config/aurora/features.yaml` (`apps/reference/domains/feature_engineering/docs/ARCHITECTURE.md:23`, `.../QUALITY_AND_DEBT.md:13`).
- Side contract dictionaries under `vfoundation/dictionaries/domains/` still advertise old exports like `POSITION_OPENED`, `POSITION_CLOSED`, `INSUFFICIENT_BALANCE`, `MIN_NOTIONAL_NOT_MET`, creating a stale parallel truth layer.
- Generated or large "authority-looking" docs still reference deleted artifacts/events: `docs/PROJECT_ATLAS.md` still references deleted `EVT:MARKET_TICK_FORWARDED` tests; `ASYNC_AUDIT_REPORT.md` still references deleted `market_ws_client.py`.
- Root-level tracked junk remains in the repo: `=0.110.0`, `shadow_test.py`, `tmp_all_config_usages.txt`, `tmp_audit_config.py`, `tmp_config_usages.txt`, `tmp_config_usages2.txt`, `tmp_drift_report.txt`.
- Runtime-default drift survived cleanup: `domain_builder.py` defaults bar timeframes to `[60, 300]`, while `bar_aggregator.py` defaults to `[180, 300]`.
- Regime detector still silently defaults `bar_ttl_ms` via `getattr(..., 10000)`, which is exactly the kind of quiet runtime fallback this cleanup program claimed to be eliminating elsewhere.

## 6. Residual Architectural Debt

**P1. Contract truth is still split.**  
Registry, payload map, warn-only reports, and side domain dictionaries do not collapse to one enforced contract source. This is the main blocker before a large Pydantic migration.

**P1. Documentation authority is still unearned.**  
Multiple files present themselves as canonical or authoritative while being wrong on active boundaries and config paths. That makes the docs layer unsafe as an operator source.

**P2. FE/DM ownership is still unresolved.**  
`strategy_bridge.py` centralizes the leak, but the conceptual leak remains. This will keep resurfacing in migrations, schema moves, and domain ownership decisions.

**P2. Config truth is still duplicated in code and tooling.**  
The production boot path is straightforward, but the loader still contains test fallback logic and tooling maps still point at removed files.

**P3. Runtime code still carries silent defaults and placeholders.**  
Examples: RD `bar_ttl_ms` fallback, MD timeframe default mismatch, hardcoded `"absorption": "0.0"` payload filler.

**P3. Repo hygiene is still incomplete.**  
Tracked junk files and stale generated docs undermine claims of a fully controlled workspace.

## 7. Dangerous Illusions

- **"There is one config truth now."** False as written. There is one primary Aurora core runtime root, but not one repo-wide runtime config truth, and the README still documents a removed overlay mechanism.
- **"The contract registry is canonical now."** Only partially true. The file is canonical by intent, but runtime vocabulary still escapes it, and parallel truth layers still exist.
- **"The FE/DM leak was fixed."** It was centralized, not eliminated.
- **"Authoritative README means trustworthy boundary map."** False. DM and EP docs are still wrong on a boundary that the cleanup claimed to settle.
- **"Test hygiene is normalized because the guardrail slice is green."** False. Green targeted slices coexist with stale reports, 5 xfail files, many skip-marker files, and test-like modules with no textual assertions.
- **"Legacy purge is complete because the main dead module is deleted."** False. Stale references and tracked junk remain in active repo surfaces.

## 8. Test Integrity Verdict

Current test integrity is **moderate for structural guardrails, weak-to-moderate for broader repo truth claims**.

- Direct audit runs passed:
  - structural/config/contract/boundary slice: `128 passed`
  - config-fallback/shared-types/session slice: `13 passed`
- This gives real confidence that several cleanup guardrails are not fake.
- But the suite is not fully normalized:
  - direct grep still finds **5 xfail-bearing files**
  - a coarse text scan found **72 files with skip markers**
  - a coarse scan over `*test*.py` excluding `conftest`/`__init__` still found **32 modules without textual `assert`/`pytest.raises`**, which is too much debug/helper/test-shape ambiguity for a "clean" classification story
  - the contract coverage audit that most directly tests SSOT completeness is still **warn-only**, not a failing gate

Conclusion: tests are useful evidence for narrow structural claims, but they are not yet strong enough to certify repo-wide architectural honesty.

## 9. Documentation Integrity Verdict

Documentation integrity is **low**.

- The docs layer is better organized than a legacy sprawl, but not trustworthy enough to serve as primary truth.
- The worst failures are not cosmetic; they are active architectural contradictions:
  - config overlay behavior documented as live even though tests enforce its removal
  - FE docs referencing nonexistent config files
  - DM and EP docs contradicting registry/domain_dict ownership on `EVT:EXPOSURE_SUMMARY_UPDATED`
  - generated atlas/report surfaces still referencing deleted events/modules

Operator rule: treat docs as search hints only, not as truth, until consistency tests exist and the stale files are corrected or demoted.

## 10. Confidence + Blind Spots

**Confidence level:** Medium-high on static architecture findings; medium on runtime-behavior conclusions.

**Directly verified**
- Git branch/state and dirty worktree condition
- Runtime config bootstrap paths in `main.py` and `ConfigLoader`
- Active config/docs/tooling references
- Contract registry, WhyCode sources, payload map, domain dictionaries
- Domain top-level READMEs/domain_dicts/tests for the six requested domains
- FE<->DM and EP boundary imports/usages
- Deletion of `market_ws_client.py` and surviving exports
- MR forbidden-config fix implementation
- Targeted pytest slices (`128 passed`, `13 passed`)
- Direct warn-only registry audit run (`coverage=83.951%`, missing runtime tokens=13)

**Blind spots / uncertain areas**
- No live exchange execution or websocket runtime was exercised
- No full-suite pytest run was performed
- No CI pipeline or packaging job was executed
- Non-target domains outside the requested six were only inspected when they affected a boundary or stale reference
- Co-emitter behavior was audited statically and by guardrails, not by full event-trace replay

**What would need runtime/live execution to verify further**
- Real emitted contract vocabulary under live or replayed runtime
- Whether co-emitter policies behave exactly as registry notes claim
- Whether the remaining skipped integration tests should be restored or deleted
- Whether alpha-search config surfaces create additional hidden SSOT drift under real runs

## 11. Recommended Next Steps

1. **Fix or demote false-authority docs before anything else.** Update `config/README.md`, DM README/EVENTS, EP ATLAS, FE ARCHITECTURE/QUALITY_AND_DEBT, and either regenerate or explicitly mark `docs/PROJECT_ATLAS.md` / stale reports as non-authoritative.
2. **Make contract SSOT real, not aspirational.** Eliminate the 13 missing runtime tokens, resolve non-deprecated `owner: unknown` entries, and either fold `vfoundation/core/payloads.py` + `vfoundation/dictionaries/domains/*.yaml` under registry governance or kill them.
3. **Remove the hidden `tests/config/aurora` fallback from production loader paths.** If tests need it, gate it behind an explicit test-only flag rather than ambient filesystem presence.
4. **Decide FE vs DM ownership before the next major migration.** Either move strategy code into DM or stop claiming that the leak is fixed; right now the bridge hides a still-unresolved domain boundary.
5. **Run a Wave #3 purge focused on leftovers, not headline wins.** Delete tracked root junk, stale debug/test-shape files, and stale generated docs/reports that still point at deleted artifacts.
6. **Add semantic consistency tests.** Assert README/domain_dict/registry agreement for event ownership, assert tooling config maps only point at existing files, and turn registry coverage from warn-only into a real gate.

