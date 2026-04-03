# Deep Forensic Research Of Critical Decision Making Contract Problems

Date: 2026-04-01
Scope:
- apps/reference/domains/decision_making/decision_making.py
- apps/reference/domains/decision_making/intent_emitter.py
- apps/reference/domains/decision_making/strategy_gateway.py
- apps/reference/domains/decision_making/intent_builder.py
- apps/reference/telemetry/alerts.py
- apps/reference/config_models.py
- apps/reference/config_loader.py
- regime-flip related tests in tests/decision_making and tests/domains/decision_making

## 1. Executive Summary

- Regime-flip close runtime truth is no longer the old direct fallback seam around patched proposal calls. The live chain is structural regime event handling in apps/reference/domains/decision_making/event_handlers.py:490, facade delegation in apps/reference/domains/decision_making/decision_making.py:583, fail-closed ownership resolution in apps/reference/domains/decision_making/intent_emitter.py:312, canonical close emission in apps/reference/domains/decision_making/flip_orchestration.py:131, and only then downstream proposal/emission through apps/reference/domains/decision_making/intent_builder.py:108.
- The old regime-flip tests in tests/domains/decision_making/test_regime_flip_close.py:133 are drifted because they patch the wrong seam and run with no registry. They expect a close where current runtime intentionally blocks with REGIME_FLIP_STRATEGY_UNRESOLVABLE.
- The current P0 suite in tests/decision_making/test_regime_flip_close_path_p0.py:88 matches the live contract and passes in isolation. It confirms registry-aware strategy resolution and fail-closed ambiguous ownership.
- There is still a live call into _propose_trade_intent for regime-flip closes, but it is now downstream of canonical close emission at apps/reference/domains/decision_making/flip_orchestration.py:180, not the old direct fallback contract. The only direct fallback left is a degraded guard in apps/reference/domains/decision_making/intent_emitter.py:456 when the close emitter is not injected.
- AlertManager mismatch is real, but narrower than a blanket production-is-broken claim. Main startup uses apps/reference/config_loader.py:100 through apps/reference/main.py:311 and succeeds, while helper/base-model assembly through apps/reference/config_models.py:5913 produces a different class identity that fails the strict check in apps/reference/telemetry/alerts.py:70.
- In DecisionMaking, that mismatch is suppressed by best-effort init in apps/reference/domains/decision_making/decision_making.py:109 and degrades to warning-path at apps/reference/domains/decision_making/decision_making.py:112, leaving alert_manager unset instead of crashing the domain.
- Problem A is a proven runtime-vs-legacy-test contract drift. Problem B is a proven class-identity mismatch on a valid typed-config path, but its production blast radius is path-dependent because the default loader path uses the wrapper class that AlertManager expects.

## 2. Facts

- Structural regime updates are forwarded into regime-flip handling from apps/reference/domains/decision_making/event_handlers.py:490.
- DecisionMaking does not own the flip logic locally; it delegates _handle_regime_flip to the emitter in apps/reference/domains/decision_making/decision_making.py:583.
- The emitter resolves strategy ownership in apps/reference/domains/decision_making/intent_emitter.py:312 and returns fail-closed no_registry at apps/reference/domains/decision_making/intent_emitter.py:350 when ownership cannot be resolved.
- The facade injects both the reduce-only close emitter and registry owner lookup into IntentEmitter at apps/reference/domains/decision_making/decision_making.py:220, apps/reference/domains/decision_making/decision_making.py:222, and apps/reference/domains/decision_making/decision_making.py:224.
- The canonical reduce-only close emitter lives in apps/reference/domains/decision_making/flip_orchestration.py:131 and calls back into proposal flow at apps/reference/domains/decision_making/flip_orchestration.py:180.
- Downstream trade-intent emission and arbitration happen in apps/reference/domains/decision_making/intent_builder.py:108, with arbitration pre-check at apps/reference/domains/decision_making/intent_builder.py:299, boundary emit at apps/reference/domains/decision_making/intent_builder.py:357, and final arbitration commit at apps/reference/domains/decision_making/intent_builder.py:366.
- A targeted grep for handle_regime_flip, REGIME_FLIP, and regime_flip returned no matches in apps/reference/domains/decision_making/strategy_gateway.py.
- The same targeted grep returned no matches in apps/reference/domains/decision_making/intent_builder.py, which means builder is downstream emission machinery, not the origin or owner-resolution site.
- DecisionMaking exposes registry owners via apps/reference/domains/decision_making/decision_making.py:614. When the registry is absent or a symbol has no assignment, this function returns an empty list.
- Because apps/reference/domains/decision_making/intent_emitter.py:340 only treats owner-list lengths 1 and greater than 1 specially, both registry missing and symbol unassigned collapse into the same final reject reason string at apps/reference/domains/decision_making/intent_emitter.py:350.
- The legacy suite in tests/domains/decision_making/test_regime_flip_close.py:133 patches dm._propose_trade_intent directly at tests/domains/decision_making/test_regime_flip_close.py:165 and runs with strategies_registry set to None at tests/domains/decision_making/test_regime_flip_close.py:129.
- The current P0 suite in tests/decision_making/test_regime_flip_close_path_p0.py:88 injects emit_reduce_only_close_fn and registry_lookup_fn at tests/decision_making/test_regime_flip_close_path_p0.py:71 and tests/decision_making/test_regime_flip_close_path_p0.py:72.
- The partially stale layering test in tests/domains/decision_making/test_regime_layering_contract.py:26 constructs IntentEmitter directly with propose_trade_intent injected at tests/domains/decision_making/test_regime_layering_contract.py:20, but without registry lookup or close emitter injection.
- AlertManager imports AuroraConfig from apps/reference/config_loader.py:100 inside apps/reference/telemetry/alerts.py:70 and rejects non-wrapper instances at apps/reference/telemetry/alerts.py:73.
- DecisionMaking initializes AlertManager best-effort at apps/reference/domains/decision_making/decision_making.py:109 and suppresses any init failure at apps/reference/domains/decision_making/decision_making.py:112.
- The default startup path loads config via apps/reference/main.py:311 and apps/reference/main.py:312, constructs AlertManager in main at apps/reference/main.py:413, and passes the same config into DecisionMaking via apps/reference/bootstrap/domain_builder.py:114.
- The helper path in apps/reference/config_models.py:5913 returns the base model by model_construct at apps/reference/config_models.py:5937, not the wrapper subclass.

## 3. Inferences

- Strategy ownership for regime-flip closes is now intentionally outside the old facade-local test seam. The authoritative seam is IntentEmitter with injected registry and close-emitter collaborators, not patched dm._propose_trade_intent.
- Current P0 coverage is stronger than the legacy suite, but still narrow. It covers single-owner and multi-owner resolution, yet it does not explicitly pin the no-registry and symbol-unassigned collapse that surfaced in tests/domains/decision_making/test_regime_layering_contract.py:26.
- The legacy failures are not random breakage. They are the expected result of moving from silent aurora-ish fallback assumptions to registry-aware fail-closed ownership.
- The AlertManager issue is both a real defect and a fragmentation symptom. The defect is that a valid typed config object from the base-model helper path is rejected; the fragmentation symptom is that two public AuroraConfig identities remain live and consumers do not agree on which one is canonical.
- The production startup path is less exposed than the test/helper path, because main uses the wrapper class from apps/reference/config_loader.py:100, which passes the strict AlertManager check.

## 4. Assumptions

- I treated the startup path in apps/reference/main.py:311 and apps/reference/bootstrap/domain_builder.py:114 as the authoritative default runtime path for Aurora core startup.
- I treated tests that construct config through apps/reference/config_models.py:5913 as valid typed-config consumers, because the helper is public and widely used in the repository.
- I did not assume any undocumented runtime behavior outside the inspected modules and tests.

## 5. Unknowns

- I did not prove whether any non-main worker or service entrypoint outside the inspected scope passes a base-model AuroraConfig into DecisionMaking in live runtime.
- I did not find a dedicated DecisionMaking-level test that asserts the AlertManager mismatch directly; the evidence there comes from the runtime probe and the captured warning in failing legacy tests.
- I did not exhaustively audit external documentation files for regime-flip contract drift; within the inspected runtime modules, comments and docstrings align with the current code.

## 6. Problem A — Regime-Flip Close Contract Drift

### Canonical runtime chain

- Structural regime event persists state and forwards to flip handling in apps/reference/domains/decision_making/event_handlers.py:490.
- DecisionMaking delegates to the emitter in apps/reference/domains/decision_making/decision_making.py:583.
- IntentEmitter performs structural gating and ownership resolution in apps/reference/domains/decision_making/intent_emitter.py:312 and apps/reference/domains/decision_making/intent_emitter.py:354.
- Resolved cases call the injected close path through apps/reference/domains/decision_making/decision_making.py:599 into apps/reference/domains/decision_making/flip_orchestration.py:131.
- FlipOrchestrator emits a reduce-only proposal by calling _propose_trade_intent at apps/reference/domains/decision_making/flip_orchestration.py:180.
- DecisionMaking routes that proposal into apps/reference/domains/decision_making/intent_builder.py:108, where arbitration is checked and EVT:TRADE_INTENT_PROPOSED is emitted.

### Does any live runtime path still go through _propose_trade_intent

- Yes, but only as the downstream leg of the canonical close chain after quantity and strategy ownership are already resolved in apps/reference/domains/decision_making/flip_orchestration.py:180.
- A direct fallback remains in apps/reference/domains/decision_making/intent_emitter.py:456, but that path is explicitly degraded and should not fire in production because the facade injects emit_reduce_only_close_fn at apps/reference/domains/decision_making/decision_making.py:222.

### Ownership outcomes

- Registry present with exactly one owner: resolve_strategy_id_for_close returns that owner from apps/reference/domains/decision_making/intent_emitter.py:342 and the close is emitted.
- Registry missing: resolve_strategy_id_for_close returns fail-closed no_registry at apps/reference/domains/decision_making/intent_emitter.py:350, and the emitter rejects instead of closing.
- Symbol unassigned: apps/reference/domains/decision_making/decision_making.py:614 returns an empty owner list, which also falls through to the same no_registry reject at apps/reference/domains/decision_making/intent_emitter.py:350.
- Ambiguous or invalid ownership: multi-owner resolution fails closed in apps/reference/domains/decision_making/intent_emitter.py:344, and lookup exceptions fail closed at apps/reference/domains/decision_making/intent_emitter.py:347.

### Legacy test drift map

- Aligned: tests/decision_making/test_regime_flip_close_path_p0.py is aligned and authoritative. It passed 4 of 4 in isolation and exercises single-owner aurora, single-owner md_amr, ambiguous multi-owner fail-closed, and reduce_only LIMIT TTL handling.
- Legacy expectation: test_regime_flip_short_in_trend_up_emits_reduce_only_close in tests/domains/decision_making/test_regime_flip_close.py:133 expects a close even though the test sets no registry and patches dm._propose_trade_intent at tests/domains/decision_making/test_regime_flip_close.py:165. It no longer matches runtime truth. Recommendation: split or update to assert fail-closed rejection when no registry is present.
- Legacy expectation: test_regime_flip_long_in_trend_down_emits_reduce_only_close in tests/domains/decision_making/test_regime_flip_close.py:181 uses the same stale seam and should be updated the same way.
- Legacy expectation: test_regime_flip_uncertain_closes_any_position in tests/domains/decision_making/test_regime_flip_close.py:227 also assumes the pre-registry contract and should be updated or split.
- Legacy expectation: test_structural_trend_up_closes_short_position in tests/domains/decision_making/test_regime_layering_contract.py:26 constructs IntentEmitter without registry_lookup_fn or emit_reduce_only_close_fn, then expects a close through direct proposal injection. That is not the canonical runtime seam anymore. Recommendation: split into a degraded-path test or inject the real collaborators.
- Ambiguous: the passing no position, no portfolio, and non-conflicting regime tests in tests/domains/decision_making/test_regime_flip_close.py still use the old seam, but their assertions are negative enough that they survive the contract shift. They should be retained only if renamed to reflect that they are coarse no-op checks, not authoritative ownership tests.
- Aligned: the non-structural gating test in tests/domains/decision_making/test_regime_layering_contract.py is aligned because apps/reference/contracts/runtime_regime_layers.py:55 and apps/reference/domains/decision_making/intent_emitter.py:364 explicitly restrict enforcement to structural regime payloads.

### Authoritative SSOT verdict

- Canonical contract is the runtime code in apps/reference/domains/decision_making/event_handlers.py:490, apps/reference/domains/decision_making/decision_making.py:220, apps/reference/domains/decision_making/intent_emitter.py:312, apps/reference/domains/decision_making/flip_orchestration.py:131, and apps/reference/domains/decision_making/intent_builder.py:108.
- The suite that actually confirms this contract is tests/decision_making/test_regime_flip_close_path_p0.py:88.
- Within the inspected runtime modules, comments and docstrings align with the current contract. I did not find a code-vs-comment contradiction in the runtime files themselves.
- There is still a regression-gap risk because the current P0 suite does not explicitly pin the no-registry and symbol-unassigned fail-closed cases.

### Root cause

- Legacy tests were written against a pre-migration seam where regime-flip closes effectively expected direct proposal behavior without explicit registry ownership resolution.

### Mechanism

- Runtime now resolves strategy ownership before close emission and blocks if ownership is missing or ambiguous. Legacy tests omit registry injection and patch dm._propose_trade_intent directly, so they never satisfy the new precondition.

### Effect

- Legacy suites now fail even though current runtime and current P0 tests agree. This creates false confidence pressure to reintroduce unsafe fallback behavior.

### Operational severity

- Runtime severity is medium, because the live code is already fail-closed and current P0 passes.
- Test and remediation severity is high, because blindly fixing the failures by restoring fallback would emit closes under the wrong strategy or without ownership proof.

### Precise recommended next action

- Keep runtime unchanged.
- Update or split the failing legacy tests so no-registry and no-injection cases assert fail-closed rejection, and canonical close tests inject registry_lookup_fn plus emit_reduce_only_close_fn the same way as tests/decision_making/test_regime_flip_close_path_p0.py:71.

## 7. Problem B — AlertManager Type Mismatch

### Actual init chain

- Default startup loads config through apps/reference/main.py:311 and apps/reference/main.py:312, which uses the wrapper class from apps/reference/config_loader.py:100.
- Main then constructs AlertManager directly at apps/reference/main.py:413.
- DecisionMaking also tries to construct AlertManager best-effort at apps/reference/domains/decision_making/decision_making.py:109 and suppresses failure at apps/reference/domains/decision_making/decision_making.py:112.
- A second typed-config path exists via apps/reference/config_models.py:5913, which returns the base model by apps/reference/config_models.py:5937. Many DecisionMaking tests use that helper directly, including tests/domains/decision_making/test_regime_flip_close.py:143.

### Exact mismatch point

- apps/reference/telemetry/alerts.py:70 imports AuroraConfig from config_loader, not from config_models.
- apps/reference/telemetry/alerts.py:73 rejects any config object that is not an instance of that wrapper subclass.
- A runtime probe proved the class split:

```text
loader_type apps.reference.config_loader.AuroraConfig True True
model_type apps.reference.config_models.AuroraConfig False True
loader_alert_manager_ok AlertManager
model_alert_manager_error TypeError AlertManager requires AuroraConfig, got <class 'apps.reference.config_models.AuroraConfig'>
```

### Root cause

- Two public AuroraConfig identities coexist: a wrapper subclass in apps/reference/config_loader.py:100 and the base model in apps/reference/config_models.py:5455. AlertManager enforces subclass identity rather than a shared base type.

### Mechanism

- create_aurora_config returns the base model. AlertManager rejects it. DecisionMaking catches that TypeError and continues with self.alert_manager left as None.

### Effect

- DecisionMaking survives, but alert-dependent monitoring degrades silently. The risk-gate alert path in apps/reference/domains/decision_making/intent_emitter.py:268 short-circuits whenever alert_manager is missing.

### Classification

- This is a true runtime defect on the base-model typed-config path.
- It is not merely noisy, because functionality is disabled.
- It is also a broader typed-config fragmentation symptom, because the problem only exists because config identity is split.

### Operational severity

- Low for the default main startup path, because wrapper config succeeds.
- Medium for DecisionMaking and any helper-driven runtime or test harness that uses the base-model path.
- High for observability confidence, because direct AlertManager tests in tests/telemetry/test_alert_manager_eviction.py pass while DecisionMaking-level alert initialization can still degrade.

### Precise recommended next action

- Add explicit tests for DecisionMaking construction with both loader wrapper config and base-model config before changing code.
- Then make AlertManager accept the shared base model from apps/reference/config_models.py:5455 while keeping dict rejection fail-closed.

## 8. Blast Radius Matrix

- Problem A
  - Directly affected modules: apps/reference/domains/decision_making/event_handlers.py:490, apps/reference/domains/decision_making/decision_making.py:220, apps/reference/domains/decision_making/intent_emitter.py:312, apps/reference/domains/decision_making/flip_orchestration.py:131, apps/reference/domains/decision_making/intent_builder.py:108.
  - Indirectly affected modules: tests/domains/decision_making/test_regime_flip_close.py:133, tests/domains/decision_making/test_regime_layering_contract.py:26, tests/decision_making/test_regime_flip_close_path_p0.py:88.
  - Runtime risk: medium-low because live behavior is fail-closed.
  - Test risk: high.
  - Observability risk: medium because no-registry and symbol-unassigned collapse to the same reject label.
  - Refactor risk: high if fallback is reintroduced blindly.
- Problem B
  - Directly affected modules: apps/reference/domains/decision_making/decision_making.py:109, apps/reference/telemetry/alerts.py:70, apps/reference/config_loader.py:100, apps/reference/config_models.py:5913.
  - Indirectly affected modules: apps/reference/main.py:413, apps/reference/domains/risk_management/risk_management.py, apps/reference/domains/position_tracking/position_tracking.py.
  - Runtime risk: medium on helper/base-model paths and low on main startup.
  - Test risk: medium because current telemetry tests do not cover DecisionMaking init.
  - Observability risk: high because alert_manager silently disappears.
  - Refactor risk: medium-high if the type gate is loosened carelessly and accidentally accepts dict-like objects.

## 9. Remediation Options

### Option A: minimal surgical fix

- Regime-flip: rewrite only the failing legacy tests so that no-registry and no-injection cases assert fail-closed rejection, and canonical-close tests use the same injected collaborators as tests/decision_making/test_regime_flip_close_path_p0.py:71.
- AlertManager: change the type gate in apps/reference/telemetry/alerts.py:70 and apps/reference/telemetry/alerts.py:73 to accept the shared base model from apps/reference/config_models.py:5455 as well as the wrapper subclass.
- Risk: low-to-medium.
- Validation burden: legacy regime-flip suite, P0 suite, explicit DecisionMaking init tests for loader and base-model configs, direct AlertManager tests.
- Additive-only status: yes for regime-flip tests; mostly additive for AlertManager because it widens accepted typed models without adding silent defaults.

### Option B: contract/test realignment

- Regime-flip: create a small canonical test harness around IntentEmitter that always provides registry_lookup_fn and emit_reduce_only_close_fn; keep separate degraded-path tests for missing injection if that path still matters.
- AlertManager: add dedicated DecisionMaking observability tests before any code change, so the mismatch is pinned as a contract rather than rediscovered through unrelated suite failures.
- Risk: low runtime risk, medium maintenance cost.
- Validation burden: same as Option A plus a few new focused tests.
- Additive-only status: yes.

### Option C: broader cleanup if required

- Collapse the duplicated AuroraConfig public surface so consumers stop importing different class identities, and deprecate or replace apps/reference/config_models.py:5913 if helper-driven model_construct paths are no longer intended.
- Consolidate regime-flip close coverage so only one authoritative contract suite exists and alternative degraded paths are explicitly named as such.
- Risk: high, because shared config APIs and many tests/helpers will move together.
- Validation burden: significantly higher across config loading, startup, and domain construction.
- Additive-only status: no.

## 10. Validation Evidence

### Targeted regime-flip code trace

- apps/reference/domains/decision_making/event_handlers.py:490
- apps/reference/domains/decision_making/decision_making.py:220
- apps/reference/domains/decision_making/intent_emitter.py:312
- apps/reference/domains/decision_making/intent_emitter.py:354
- apps/reference/domains/decision_making/flip_orchestration.py:131
- apps/reference/domains/decision_making/flip_orchestration.py:180
- apps/reference/domains/decision_making/intent_builder.py:108
- apps/reference/domains/decision_making/intent_builder.py:299
- apps/reference/domains/decision_making/intent_builder.py:357

### Targeted AlertManager/type-trace

- apps/reference/telemetry/alerts.py:70
- apps/reference/telemetry/alerts.py:73
- apps/reference/domains/decision_making/decision_making.py:109
- apps/reference/domains/decision_making/decision_making.py:112
- apps/reference/config_loader.py:100
- apps/reference/config_loader.py:1148
- apps/reference/config_models.py:5455
- apps/reference/config_models.py:5913
- apps/reference/config_models.py:5937

### Targeted grep/find results

- Search pattern handle_regime_flip|REGIME_FLIP|regime_flip in apps/reference/domains/decision_making/strategy_gateway.py returned no matches.
- Search pattern handle_regime_flip|REGIME_FLIP|regime_flip in apps/reference/domains/decision_making/intent_builder.py returned no matches.
- Search pattern AlertManager init failed|requires AuroraConfig|alert_manager is None in tests under tests/domains/decision_making returned no matches, so there is no dedicated DecisionMaking-level mismatch test in that scope.
- Search in apps/reference/telemetry/alerts.py:70 and apps/reference/telemetry/alerts.py:73 confirmed the config_loader.AuroraConfig identity gate.

### Scoped pytest results

- tests/domains/decision_making/test_regime_flip_close.py: 3 failed, 3 passed. The three failures were the close-emission expectations in a no-registry harness, and each failure log also captured AlertManager init failed with the config_models.AuroraConfig TypeError.
- tests/decision_making/test_regime_flip_close_path_p0.py: 4 passed.
- tests/domains/decision_making/test_regime_layering_contract.py: 1 failed, 1 passed. The failing test expected a close from an IntentEmitter built without registry_lookup_fn or emit_reduce_only_close_fn.
- tests/telemetry/test_alert_manager_eviction.py: 2 passed.

### Runtime probe command

```powershell
$code = @'
from apps.reference.config_loader import ConfigLoader, AuroraConfig as LoaderAuroraConfig
from apps.reference.config_models import AuroraConfig as ModelAuroraConfig, create_aurora_config
from apps.reference.telemetry.alerts import AlertManager
cfg_loader = ConfigLoader().load_config()
cfg_model = create_aurora_config(cfg_loader.model_dump())
print('loader_type', type(cfg_loader).__module__ + '.' + type(cfg_loader).__name__, isinstance(cfg_loader, LoaderAuroraConfig), isinstance(cfg_loader, ModelAuroraConfig))
print('model_type', type(cfg_model).__module__ + '.' + type(cfg_model).__name__, isinstance(cfg_model, LoaderAuroraConfig), isinstance(cfg_model, ModelAuroraConfig))
ok = AlertManager(cfg_loader)
print('loader_alert_manager_ok', type(ok).__name__)
try:
    AlertManager(cfg_model)
except Exception as exc:
    print('model_alert_manager_error', type(exc).__name__, str(exc))
'@
C:/Users/user/Music/Phenix/.venv/Scripts/python.exe -c $code
```

Output summary:

```text
loader_type apps.reference.config_loader.AuroraConfig True True
model_type apps.reference.config_models.AuroraConfig False True
loader_alert_manager_ok AlertManager
model_alert_manager_error TypeError AlertManager requires AuroraConfig, got <class 'apps.reference.config_models.AuroraConfig'>
```

## 11. Final Verdict

- Problem A — REGIME-FLIP CLOSE CONTRACT DRIFT: PROVEN.
- Problem B — ALERTMANAGER TYPE MISMATCH: PARTIALLY PROVEN.
