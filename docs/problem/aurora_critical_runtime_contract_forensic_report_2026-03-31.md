# Aurora Critical Runtime Contract Forensic Report

Date: 2026-03-31
Status: completed, evidence-based, runtime-probed, report-only
Scope:
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/exit_manager.py
- apps/reference/domains/decision_making/shields/danger_zone.py
- apps/reference/domains/decision_making/shields/context_shield.py
- apps/reference/domains/decision_making/shields/memory_shield.py
- apps/reference/domains/execution_position/fsm_manage.py
- apps/reference/config_loader.py
- apps/reference/config_models.py
- config/aurora/strategies/aurora.yaml
- config/aurora/system.yaml
- tests/config/test_btcusdt_aurora_runtime_fields.py
- tests/integration/test_s2_danger_zone_reason_e2e.py
- tests/integration/test_regime_detector_event_flow.py
- tests/test_context_shield.py
- tests/domains/test_dm_bar_ttl_preemit.py
- tests/runtime/test_task24_regime_detector_correctness.py
- tests/test_memory_shield.py
- tests/unit/decision_making/test_memory_shield_logic.py

## 1. Executive Summary

- P0 trailing-stop mismatch is a proven live runtime defect in the Aurora decision path. The decision-path ExitManager is hydrated from a compatibility probe over `config.instruments`, while live per-symbol trailing values used by the strategy live under `strategies.aurora.assets.<SYMBOL>.trailing_stop`.
- A real runtime probe on loaded repo config proved the split for `SOLUSDT`: strategy config trailing was enabled and `ManageFlowFSM._get_trailing_stop_params("SOLUSDT")` returned `(True, 0.046, 0.018, 5)`, while `handler.exit_manager._trailing_enabled` was `False`.
- A second behavioral probe proved impact, not just config drift: the live Aurora handler returned no exit on a trailing-breach snapshot, while an ExitManager built from the `SOLUSDT` trailing config returned `EXIT_TRAILING`.
- Danger-zone handling is a proven control-plane contract defect. `DangerZoneShield` emits free-form human-readable reason strings, and `aurora_decision.py` derives `danger_zone_active` by substring parsing those strings. A wording-only mutation changed behavior from forced close to no close.
- TTL semantics are locally coherent but end-to-end fragmented. `ContextShield` stale handling and `ttl_ms=0` disable semantics are explicit and tested, but system freshness surfaces and regime-detector payload contracts are not pinned by a single integration contract.
- Validation blind spots are concrete. Passing targeted tests coexist with a real runtime defect, and the regime-detector integration suite is globally skipped because fixtures lag the `tf_sec` contract.
- MemoryShield is runtime-wired and functioning in RAM. A live Aurora handler carried `_memory_shield`, and state count increased after signal emission. Persistence remains disabled by SSOT via `storage_path: null`.
- No production code was changed in this task. The deliverable is this forensic report artifact.

## 2. Investigation Method

- Runtime truth was treated as authoritative over comments, older tests, or implied architecture.
- Evidence came from code inspection, loaded-config runtime probes, focused pytest runs, and targeted artifact/log searches.
- Missing proof was not upgraded into fact. Items without direct runtime evidence remain either inference or unknown.
- Scope stayed bounded to the Aurora decision/runtime seam requested by the investigation priorities:
  - trailing-stop contract/runtime mismatch
  - danger-zone string coupling
  - TTL semantics drift
  - validation/test blind spots
  - MemoryShield runtime completeness

## 3. Facts

- `config/aurora/strategies/aurora.yaml` defines live per-symbol `trailing_stop` blocks under `aurora.assets.<SYMBOL>.trailing_stop`.
- `config/aurora/strategies/aurora.yaml` defines `SOLUSDT.trailing_stop.enabled: true`, `activation_pct: 0.046`, `trail_pct: 0.018`, and `min_update_interval_sec: 5`.
- `apps/reference/domains/execution_position/fsm_manage.py` reads trailing-stop params from per-symbol Aurora instrument config through `ManageFlowFSM._get_trailing_stop_params()` and returns a fail-closed disabled tuple only when no per-symbol config exists.
- `tests/config/test_btcusdt_aurora_runtime_fields.py` proves `ManageFlowFSM._get_trailing_stop_params(symbol)` consumes mutated per-symbol trailing config.
- `apps/reference/domains/decision_making/aurora_config_loader.py` builds the decision-path `ExitManager` by probing `self.config.instruments` for a trailing-stop config and falling back to disabled when that probe finds nothing usable.
- The same `aurora_config_loader.py` block labels this as a compatibility probe for older config objects.
- A live runtime probe against the loaded repo config returned:

```text
strategies.aurora.assets.SOLUSDT.trailing_stop.enabled = True
ManageFlowFSM._get_trailing_stop_params("SOLUSDT") = (True, 0.046, 0.018, 5)
handler.exit_manager._trailing_enabled = False
```

- A live behavioral probe on the same `SOLUSDT` position snapshot returned:

```text
current_handler_exit_manager -> (False, None, None)
sol_configured_exit_manager -> (True, "EXIT_TRAILING:price=104.8<trail=105.07(...)", None)
```

- `apps/reference/domains/decision_making/shields/danger_zone.py` emits veto reasons as free-form strings such as `DANGER_ZONE:vol=...`, `DANGER_ZONE:spread=...`, and `DANGER_ZONE:motion=...`.
- `apps/reference/domains/decision_making/aurora_decision.py` computes `danger_zone_active = any("DANGER_ZONE" in str(r) for r in shield_reasons)` and passes that boolean into `self.exit_manager.check_exit(...)`.
- A mutation-style runtime probe returned:

```text
original reason  -> danger_zone_active=True  -> EXIT_DANGER_ZONE:ForceClose
mutated reason   -> danger_zone_active=False -> no forced close
```

- `tests/integration/test_s2_danger_zone_reason_e2e.py` verifies exact reason-string prefixes and propagation of `DANGER_ZONE:*` reasons through `ShieldCascade`.
- `apps/reference/domains/decision_making/shields/context_shield.py` applies stale-regime logic only when `ttl_ms > 0` and both timestamps are present and positive.
- `config/aurora/system.yaml` carries system freshness settings including `tick_ttl_ms`, `bar_ttl_ms`, and `bar_event_age_mode`.
- `tests/integration/test_regime_detector_event_flow.py` is globally skipped because `RegimeDetector` now requires `tf_sec` in payload and the fixtures do not provide the updated event contract.
- Focused TTL-oriented test execution passed for `tests/test_context_shield.py`, `tests/domains/test_dm_bar_ttl_preemit.py`, and `tests/runtime/test_task24_regime_detector_correctness.py`.
- `apps/reference/domains/decision_making/aurora_scoring_helpers.py` wires `MemoryShield` into the scoring helper mixin.
- `apps/reference/domains/decision_making/shields/memory_shield.py` declares a pure-read `evaluate()` contract and an explicit write path through `record_visit()`.
- `config/aurora/strategies/aurora.yaml` sets `memory_shield.storage_path: null`, which means in-memory only and no persistence.
- A live Aurora handler probe proved `_memory_shield` exists and state count increased from `0` to `1` after signal emission.
- Focused MemoryShield test execution passed for `tests/test_memory_shield.py` and `tests/unit/decision_making/test_memory_shield_logic.py`.
- Targeted observability searches found effective config artifacts and general telemetry, but did not surface explicit searchable runtime markers for `EXIT_TRAILING`, `EXIT_DANGER_ZONE`, or `danger_zone_active` in the seam under investigation.

## 4. Inferences

- The Aurora decision path and the execution-position path do not share a single authoritative trailing-stop contract at runtime.
- The trailing-stop defect is not merely stale config decoration. It directly changes exit behavior on a live trailing-breach scenario.
- Danger-zone protection is currently stringly typed. Human-readable wording is doubling as a machine-control contract.
- TTL semantics are individually defined in local components, but end-to-end freshness truth is fragmented across shield logic, system config, detector payload requirements, and tests.
- The current test mix overweights producer/local semantics and underweights consumer-boundary runtime truth.
- Existing observability around this seam is insufficient to make trailing-stop or danger-zone runtime failures easy to detect from artifacts alone.
- MemoryShield is not the source of the critical defect cluster investigated here. Its live runtime contract appears locally coherent within the inspected scope.

## 5. Assumptions

- I treated the loaded repo config and the live Aurora handler construction path used in the runtime probes as a valid representation of the current decision runtime.
- I treated the existing Aurora strategy YAML under `config/aurora/strategies/aurora.yaml` as the strategy SSOT within the inspected scope.
- I treated the targeted tests named in scope as representative of the current intended guardrails for these seams.

## 6. Unknowns

- I did not prove whether any alternate non-inspected bootstrap path hydrates the Aurora decision `ExitManager` differently from the path probed here.
- I did not prove whether downstream execution or external exchange-side stop management compensates for the missing trailing decision signal in production runtime.
- I did not prove whether any artifact pipeline outside the searched scope records `danger_zone_active` or trailing-stop decisions under different field names.
- I did not attempt a full repo-wide TTL taxonomy beyond the inspected decision, detector, config, and targeted test surfaces.

## 7. Problem P0 - Trailing Stop Contract / Runtime Mismatch

### Evidence

- Live trailing policy values are present under `config/aurora/strategies/aurora.yaml` in the per-symbol `aurora.assets.<SYMBOL>.trailing_stop` blocks.
- `ManageFlowFSM._get_trailing_stop_params()` consumes that per-symbol strategy config and, for `SOLUSDT`, returned `(True, 0.046, 0.018, 5)` in a live probe.
- `tests/config/test_btcusdt_aurora_runtime_fields.py` proves the execution-position path honors mutated per-symbol trailing config.
- `aurora_config_loader.py` does not hydrate decision-path trailing from `strategies.aurora.assets.<SYMBOL>.trailing_stop`. Instead, it performs a compatibility probe over `self.config.instruments` and disables trailing when that probe yields nothing active.
- The live decision-path handler built from repo config had `handler.exit_manager._trailing_enabled = False` while `SOLUSDT` trailing remained enabled in strategy config.
- A behavior probe on the same position snapshot showed the decision-path `ExitManager` missed an exit that a symbol-configured `ExitManager` correctly classified as `EXIT_TRAILING`.

### Code/Contract Conflict

- Inside `aurora_config_loader.py`, the compatibility block comments describe `config.instruments` as the precision SSOT for that probe.
- Within the inspected runtime and tests, the active per-symbol trailing values actually used by execution-position live under `strategies.aurora.assets.<SYMBOL>.trailing_stop`.
- That means the inspected runtime truth and the nearby comment/concept framing are in conflict for trailing-stop behavior.

### Root Cause

- Trailing-stop policy is declared on the strategy per-symbol surface, but the Aurora decision-path consumer reads a different namespace through a compatibility probe.

### Mechanism

- The loader constructs `ExitManager` before reading the live per-symbol trailing-stop settings that the execution-position path later consumes.
- When `config.instruments` does not expose an active trailing config, the decision path silently disables trailing even though the strategy YAML enables it per symbol.

### Effect

- Aurora open-position decision logic can fail to emit trailing exits that are explicitly configured in strategy SSOT.
- Execution-position and decision-making can disagree about whether trailing is enabled for the same symbol and the same runtime.

### Operational Severity

- Runtime severity: high.
- Test severity: high.
- Observability severity: medium-high, because missing trailing activation is not obvious from the usual artifacts inspected here.

### Precise Recommended Next Action

- Make the Aurora decision-path `ExitManager` hydrate trailing policy from the same per-symbol strategy surface used by `ManageFlowFSM`.
- Add a dedicated Aurora handler seam test that asserts loaded repo config yields identical trailing enablement/values for decision-making and execution-position consumers.
- Keep the compatibility probe only as an explicitly degraded legacy path if it is still required, and make that degradation visible in tests and artifacts.

## 8. Problem P1 - Danger-Zone String Coupling

### Evidence

- `DangerZoneShield` encodes the veto reason as a human-readable string.
- `aurora_decision.py` does not consume a structured reason code or typed flag. It infers `danger_zone_active` by checking whether any shield reason string contains the literal token `DANGER_ZONE`.
- The live mutation probe proved the coupling:

```text
original reason  -> danger_zone_active=True  -> EXIT_DANGER_ZONE:ForceClose
mutated reason   -> danger_zone_active=False -> no forced close
```

- `tests/integration/test_s2_danger_zone_reason_e2e.py` asserts exact `DANGER_ZONE:*` prefix format and reason propagation, which reinforces the current string contract rather than replacing it with a structured one.

### Root Cause

- A machine-actionable risk-control decision is encoded in free-form reason text instead of a structured field, reason code, or typed verdict.

### Mechanism

- The producer emits text.
- The consumer parses a substring from that text to determine whether forced-close logic should activate.
- Any wording change, localization change, or refactor that preserves semantics but changes the string token can disable the behavior.

### Effect

- Danger-zone forced-close behavior is brittle and coupled to presentation text.
- Tests can stay green while preserving the wrong kind of contract: exact string shape instead of semantic truth.

### Operational Severity

- Runtime severity: high.
- Refactor severity: high.
- Test severity: high, because current E2E coverage normalizes the brittle coupling.

### Precise Recommended Next Action

- Introduce a structured shield outcome for danger-zone semantics, for example a reason code, typed veto class, or explicit `danger_zone_active` field produced by the shield layer.
- Keep the human-readable reason string for diagnostics, but stop using it as the only machine contract.
- Add a semantic mutation regression test that proves behavior survives wording changes.

## 9. Problem P1 - TTL Semantics Drift

### Evidence

- `ContextShield` has explicit stale-regime behavior and explicit `ttl_ms > 0` gating.
- `config/aurora/strategies/aurora.yaml` sets `context_shield.ttl_ms: 14400000` and stale multipliers.
- `config/aurora/system.yaml` defines system freshness surfaces such as `tick_ttl_ms`, `bar_ttl_ms`, and `bar_event_age_mode`.
- `tests/test_context_shield.py`, `tests/domains/test_dm_bar_ttl_preemit.py`, and `tests/runtime/test_task24_regime_detector_correctness.py` passed in focused execution.
- `tests/integration/test_regime_detector_event_flow.py` is skipped because the detector now requires `tf_sec` in payload and the fixtures are stale.

### Root Cause

- Freshness/TTL rules are distributed across multiple components and payload contracts without a single end-to-end runtime contract test that pins their interaction.

### Mechanism

- Local components can be internally correct while still drifting from one another at integration boundaries.
- Event payload requirements changed (`tf_sec`) without the integration suite keeping pace.

### Effect

- The repo can report green on local TTL semantics while end-to-end freshness behavior remains partially unverified.
- Contract drift shows up as skipped integration coverage instead of immediate test failure on the canonical runtime path.

### Operational Severity

- Runtime severity: medium, because a specific bad live outcome was not proven here.
- Validation severity: high, because integration trust is materially weakened.

### Precise Recommended Next Action

- Define one explicit end-to-end freshness contract covering detector payload requirements, bar age semantics, and shield stale behavior.
- Update the skipped regime-detector fixtures to include the required `tf_sec` contract instead of leaving the suite globally skipped.
- Keep local TTL tests, but add at least one canonical integration test that crosses detector -> handler -> decision boundary.

## 10. Problem P1 - Validation And Test Blind Spots

### Evidence

- Focused pytest execution for the first cluster returned `11 passed, 3 skipped` across:
  - `tests/integration/test_s2_danger_zone_reason_e2e.py`
  - `tests/config/test_btcusdt_aurora_runtime_fields.py`
  - `tests/integration/test_regime_detector_event_flow.py`
- The skip reason is not cosmetic. The regime-detector integration file is fully marked skipped because fixtures lag the `tf_sec` event contract.
- `tests/config/test_btcusdt_aurora_runtime_fields.py` proves config loading and execution-position wiring for trailing-stop, but it does not assert that the live Aurora decision-path `ExitManager` receives the same trailing config.
- `tests/integration/test_s2_danger_zone_reason_e2e.py` proves exact reason-string format and propagation, but it does not protect against semantic coupling to those exact strings.
- Focused TTL tests passed (`36 passed`) and focused MemoryShield tests passed (`30 passed`), yet those green results coexisted with the proven trailing-stop runtime defect.
- Targeted artifact searches did not surface explicit searchable markers for `EXIT_TRAILING`, `EXIT_DANGER_ZONE`, or `danger_zone_active` in the investigated seam.

### Root Cause

- The current validation strategy is stronger on producer-local correctness and weaker on cross-component consumer truth.

### Mechanism

- Tests pin local config readers, local reason formatting, and local shield logic.
- The live consumer seams where those values are supposed to take effect remain under-tested.
- Integration drift is partly hidden behind skipped suites and partly hidden behind missing artifact truth markers.

### Effect

- Green targeted tests do not guarantee the actual Aurora runtime contract is correct.
- Teams can receive false confidence from passing suites while critical runtime behavior remains wrong.

### Operational Severity

- Confidence severity: high.
- Refactor safety severity: high.
- Runtime detection severity: medium-high.

### Precise Recommended Next Action

- Add seam tests that assert consumer hydration, not only producer configuration.
- Replace skipped integration coverage with updated fixtures tied to the current event contract.
- Add decision-truth or structured telemetry markers for critical exit-path outcomes so runtime defects become searchable.

## 11. Problem P2 - MemoryShield Runtime Completeness

### Evidence

- `aurora_scoring_helpers.py` wires `MemoryShield` into the live Aurora scoring helper stack.
- `memory_shield.py` explicitly documents `evaluate()` as pure read and `record_visit()` as the mutation path.
- A live Aurora handler probe showed `_memory_shield` exists and the tracked state count increased from `0` to `1` after signal emission.
- `config/aurora/strategies/aurora.yaml` sets `storage_path: null`, which explicitly disables persistence.
- Focused test execution for `tests/test_memory_shield.py` and `tests/unit/decision_making/test_memory_shield_logic.py` passed.

### Root Cause Assessment

- No critical runtime defect was proven here.
- The inspected behavior is consistent with the declared contract: MemoryShield is live, records visits in memory, and does not persist across restarts unless configured to do so.

### Effect

- MemoryShield contributes live state familiarity attenuation during process lifetime.
- Cross-restart persistence is absent by current SSOT, not by accidental runtime breakage.

### Operational Severity

- Runtime severity: low.
- Configuration clarity severity: low.

### Precise Recommended Next Action

- Keep the current classification as working-in-memory by design.
- Only treat persistence as missing functionality if there is an explicit requirement to survive process restarts.
- If persistence is later enabled, add restart-level validation to prove no cross-run leakage or stale-state corruption.

## 12. Observability And Artifact Gaps

- In the inspected searches, I found evidence of effective configs and generic runtime telemetry, but not straightforward searchable markers for the critical behaviors under audit.
- Specifically, I did not find explicit searchable traces for:
  - decision-path trailing enabled/disabled state at the point of exit evaluation
  - computed `danger_zone_active` on the exit path
  - canonical `EXIT_TRAILING` and `EXIT_DANGER_ZONE` artifacts in the investigated seam
- This means the repo currently depends too heavily on code reading and custom runtime probes to prove or disprove these defects.

## 13. Validation Evidence

### Runtime probes

```text
Probe A: loaded repo config split
- strategies.aurora.assets.SOLUSDT.trailing_stop.enabled = True
- ManageFlowFSM._get_trailing_stop_params("SOLUSDT") = (True, 0.046, 0.018, 5)
- handler.exit_manager._trailing_enabled = False

Probe B: behavior on trailing-breach snapshot
- current_handler_exit_manager -> (False, None, None)
- sol_configured_exit_manager -> (True, "EXIT_TRAILING:price=104.8<trail=105.07(...)", None)

Probe C: danger-zone mutation
- original reason  -> danger_zone_active=True  -> EXIT_DANGER_ZONE:ForceClose
- mutated reason   -> danger_zone_active=False -> no forced close

Probe D: live MemoryShield write path
- _memory_shield present on AuroraHandler
- state_count: 0 -> 1 after signal emission
```

### Focused pytest results

```text
Run 1:
- tests/integration/test_s2_danger_zone_reason_e2e.py
- tests/config/test_btcusdt_aurora_runtime_fields.py
- tests/integration/test_regime_detector_event_flow.py
Result: 11 passed, 3 skipped
Skip cause: RegimeDetector now requires tf_sec in payload; fixtures are outdated.

Run 2:
- tests/test_context_shield.py
- tests/domains/test_dm_bar_ttl_preemit.py
- tests/runtime/test_task24_regime_detector_correctness.py
Result: 36 passed

Run 3:
- tests/test_memory_shield.py
- tests/unit/decision_making/test_memory_shield_logic.py
Result: 30 passed
```

## 14. Blast Radius Matrix

- Trailing-stop mismatch
  - Directly affected: Aurora decision-path exit behavior for open positions.
  - Indirectly affected: any tests or runbooks that assume strategy trailing config automatically reaches both decision-making and execution-position.
  - Primary risk: configured protective exits silently not honored by the decision path.

- Danger-zone string coupling
  - Directly affected: forced-close activation on danger-zone conditions.
  - Indirectly affected: refactors, wording changes, localization, schema cleanup, telemetry normalization.
  - Primary risk: semantic protection disabled by non-semantic text changes.

- TTL semantics drift
  - Directly affected: freshness gating between detector, bar age, and shield staleness.
  - Indirectly affected: integration fixtures and runtime confidence.
  - Primary risk: local correctness hiding integration drift.

- Validation and observability blind spots
  - Directly affected: engineering confidence and incident response speed.
  - Indirectly affected: future contract migrations.
  - Primary risk: green suites and shallow artifacts masking live defects.

- MemoryShield completeness
  - Directly affected: familiarity attenuation during process lifetime.
  - Indirectly affected: restart semantics only if persistence later becomes required.
  - Primary risk: low in current scope.

## 15. Recommended Remediation Order

1. Fix trailing-stop hydration so Aurora decision-making and execution-position read the same per-symbol SSOT.
2. Introduce structured danger-zone semantics and stop using free-form reason text as the only control signal.
3. Unskip and modernize the regime-detector integration suite around the current `tf_sec` event contract.
4. Add runtime-truth seam tests for trailing and danger-zone consumer behavior.
5. Add searchable structured artifacts or truth events for critical exit-path decisions.
6. Leave MemoryShield persistence unchanged unless the requirement changes.

## 16. Final Verdict

- Trailing-stop contract/runtime mismatch: proven live defect.
- Danger-zone string coupling: proven control-plane defect.
- TTL semantics drift: locally coherent, integrationally fragmented, and insufficiently pinned end-to-end.
- Validation/test blind spots: proven and active.
- MemoryShield runtime completeness: proven in-memory and consistent with current SSOT.

The most important conclusion is that passing targeted tests did not disprove the core runtime defect. The Aurora decision path currently diverges from strategy SSOT on trailing-stop behavior, and danger-zone forced-close semantics remain brittle because they depend on free-form reason text instead of a structured contract.
