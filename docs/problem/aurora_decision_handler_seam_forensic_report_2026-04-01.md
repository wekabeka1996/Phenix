# Aurora Decision/Handler Seam Forensic Report

Date: 2026-04-01
Status: completed, evidence-based, post-fix
Scope:
- apps/reference/domains/decision_making/aurora_decision.py
- apps/reference/domains/decision_making/aurora_handler.py
- apps/reference/domains/decision_making/aurora_config_loader.py
- apps/reference/domains/decision_making/aurora_scoring_helpers.py
- apps/reference/domains/decision_making/entry_plan.py
- apps/reference/domains/decision_making/trade_intent_reject_wal.py
- apps/reference/domains/decision_making/decision_truth_artifacts.py
- apps/reference/domains/decision_making/execution_gate.py
- apps/reference/dictionaries/verb_registry_v1.yaml
- apps/reference/domains/decision_making/schemas/str_decision_blocked_v1.json
- schemas/trade_intent_rejected_v1.json
- config/aurora/strategies/aurora.yaml
- tests/domains/decision_making/test_aurora_handler.py
- tests/domains/decision_making/test_aurora_volatility_logic.py
- tests/domains/decision_making/test_decision_truth_artifacts.py

## 1. Executive Summary

- Question 1, silent-drop around volatility_entry_logic missing regime multiplier or DEFAULT:
  - Normal production boot path did not prove this branch reachable.
  - The strict loader path builds AuroraConfig through Pydantic and requires DEFAULT in VolatilityEntryConfig.
  - Live Aurora volatility-entry configs currently include DEFAULT.
  - The branch was still an observability hole for legacy or mock config bypasses because it only logged and returned.
  - Minimal hardening was applied so this branch now emits EVT:STRATEGY_DECISION_BLOCKED with reason_code VOLATILITY_ENTRY_MULTIPLIER_MISSING.

- Question 2, canonical side drift after policy overrides:
  - This was a real runtime defect, not only a code smell.
  - effective_side could be changed after the kernel result, but downstream entry plan, objective, projected notional, and execution gate still consumed result.side.
  - A targeted runtime harness proved the split: entry_plan_side=buy, gate_side=buy, emit_side=SELL, result_side=buy.
  - The seam was fixed by deriving a canonical_side from effective_side and feeding that to all downstream consumers while preserving result.side as raw kernel diagnostics.

- Question 3, true contract of _emit_strategy_blocked:
  - The current runtime helper is blocked-truth only.
  - It writes strategy blocked truth through write_strategy_decision_blocked and emits EVT:STRATEGY_DECISION_BLOCKED.
  - It does not write trade-intent reject WAL.
  - The stale expectation was in tests/domains/decision_making/test_aurora_handler.py, not in the runtime helper.

## 2. Protocol And Artifact Notes

Facts:
- Copilot_Master_Roadmap.md exists and is the declared SSOT for repo navigation.
- docs/problem already existed on disk before this report was written.
- docs/ai/AGENT_REPORT_SCHEMA.md was not present on disk when checked.
- docs/ai/DONE_CRITERIA.md was not present on disk when checked.

Inference:
- The forensic report had to be written against runtime truth and inspected code/tests rather than a local report-schema document, because the referenced docs/ai protocol files were missing.

Unknowns:
- I did not determine whether those docs/ai files were intentionally removed, relocated, or simply absent in this workspace snapshot.

## 3. Facts

- _emit_strategy_blocked in apps/reference/domains/decision_making/aurora_handler.py:511-532 calls write_strategy_decision_blocked and emits EVT:STRATEGY_DECISION_BLOCKED. It does not call write_trade_intent_rejected.
- The blocked truth helper write_strategy_decision_blocked is implemented in apps/reference/domains/decision_making/decision_truth_artifacts.py and mirrors STRATEGY_DECISION_BLOCKED into WAL.
- trade_intent_reject_wal.py explicitly writes TRADE_INTENT_REJECTED payloads to WAL only and does not emit EVT:TRADE_INTENT_REJECTED on the FSM bus.
- The verb registry separates STRATEGY_DECISION_BLOCKED and TRADE_INTENT_REJECTED as distinct verbs and schemas in apps/reference/dictionaries/verb_registry_v1.yaml:365-410.
- The strategy blocked schema fixes stage to STRATEGY in apps/reference/domains/decision_making/schemas/str_decision_blocked_v1.json.
- The trade-intent rejected schema allows stages RISK, STRATEGY, DECISION, EXECUTION in schemas/trade_intent_rejected_v1.json.
- Aurora README states that EVT:STRATEGY_DECISION_BLOCKED is the dominant live no-trade class for ordinary Aurora denials in apps/reference/domains/decision_making/README.md:123.
- In aurora_decision.py the raw kernel side is stored at apps/reference/domains/decision_making/aurora_decision.py:559.
- effective_side is initialized from result.side at apps/reference/domains/decision_making/aurora_decision.py:700.
- effective_side can be changed by policy after the kernel, including:
  - inception rescue at apps/reference/domains/decision_making/aurora_decision.py:753-755
  - exit manager override at apps/reference/domains/decision_making/aurora_decision.py:844
  - holding-period suppression at apps/reference/domains/decision_making/aurora_decision.py:866
- Before the fix, downstream consumers used result.side in the same method for:
  - entry_plan computation
  - active threshold selection
  - objective signal_direction
  - projected order notional
  - execution gate side
- _emit_signal resolves emitted side from effective_side first and only falls back to result.side in apps/reference/domains/decision_making/aurora_decision.py:1250.
- The volatility-entry branch inside _emit_signal previously did logger.error plus bare return when the active regime was absent and DEFAULT was also absent.
- VolatilityEntryConfig requires DEFAULT through Pydantic validation in apps/reference/config_models.py:4467.
- AuroraInstrumentConfig exposes volatility_entry_logic as VolatilityEntryConfig in apps/reference/config_models.py:4598.
- The main config loader constructs AuroraConfig via Pydantic in apps/reference/config_loader.py:1148.
- AuroraHandler switches to strict config behavior when self.config is an AuroraConfig instance in apps/reference/domains/decision_making/aurora_config_loader.py:74.
- AuroraBuiltinPlugin creates AuroraHandler from the typed config in apps/reference/domains/strategies/plugins/aurora_builtin.py:174.
- Live Aurora volatility-entry config examples currently include DEFAULT, for example in config/aurora/strategies/aurora.yaml:533, 652, 778, and 891.

## 4. Inferences

- The normal runtime boot path is strict and type-checked, so the missing-DEFAULT path was not proven reachable through ConfigLoader plus AuroraBuiltinPlugin.
- The bare log-and-return branch was still defect-worthy because fail-closed without a canonical artifact is an observability gap whenever the handler is instantiated with legacy, mock, or bypassed config objects.
- _emit_strategy_blocked already matched the blocked-truth contract implied by runtime code, schema, registry, and README; the mismatch was in stale test expectations.
- The side split was more severe than a naming inconsistency because emit-time payload side and pre-emit downstream logic could diverge on a live path.

## 5. Assumptions

- I treated ConfigLoader plus AuroraBuiltinPlugin as the authoritative Aurora boot path for normal runtime.
- I treated SimpleNamespace and partial-mock AuroraHandler tests as valid compatibility surfaces that must still fail closed observably.
- I did not assume hidden side canonicalization outside the inspected aurora_decision.py path.

## 6. Unknowns

- I did not prove whether some other non-plugin runtime path constructs AuroraHandler with an untyped config in production.
- I did not prove whether last_signal_side should remain raw kernel side or should also be rewritten to canonical post-policy side; no runtime defect was proven there in this audit.
- I did not audit every downstream consumer of emitted STRATEGY_SIGNAL_PRODUCED payloads beyond the seam under investigation.

## 7. Question 1 — Silent-Drop / Observability Hole

### Evidence

- The pre-fix volatility-entry branch inside _emit_signal performed:
  - regime lookup
  - multipliers.get(regime, multipliers.get("DEFAULT"))
  - logger.error plus return when both were missing
- That branch lived inside apps/reference/domains/decision_making/aurora_decision.py and produced no blocked artifact, no reject artifact, and no signal.
- VolatilityEntryConfig enforces DEFAULT in apps/reference/config_models.py:4467.
- ConfigLoader builds AuroraConfig via Pydantic in apps/reference/config_loader.py:1148.
- AuroraHandler uses strict typed-config behavior when it receives AuroraConfig in apps/reference/domains/decision_making/aurora_config_loader.py:74.
- AuroraBuiltinPlugin feeds the typed config into AuroraHandler in apps/reference/domains/strategies/plugins/aurora_builtin.py:174.
- Live enabled volatility-entry configs currently include DEFAULT. Spot checks showed DEFAULT in config/aurora/strategies/aurora.yaml:533, 652, 778, and 891.
- A direct runtime probe through the real loader/plugin path returned:

```text
{'config_type': 'AuroraConfig', 'handler_strict': True, 'enabled_vol_cfg_count': 7, 'missing_default': [], 'sample_vel_cfg_type': 'VolatilityEntryConfig'}
```

- A focused compatibility test in tests/domains/decision_making/test_aurora_volatility_logic.py:250 proves that a legacy/mock config without DEFAULT now emits EVT:STRATEGY_DECISION_BLOCKED with reason_code VOLATILITY_ENTRY_MULTIPLIER_MISSING.

### Cause

- The volatility-entry helper trusted that config validation had already ensured DEFAULT and kept only a log-and-return safeguard.

### Mechanism

- On a bypassed or mock config object, missing active-regime mapping and missing DEFAULT caused the method to return before any canonical blocked artifact was emitted.

### Effect

- The decision path failed closed but left a forensic hole: no trade, no signal, and no structured blocked artifact for that bar.

### Operational Risk

- Normal production risk: unproven, because the strict loader path did not reproduce the condition.
- Compatibility and test harness risk: real, because legacy/mock configs can still instantiate AuroraHandler directly.
- Observability risk: real before the fix, because the branch had no structured artifact.

### Verdict

- Production reachability through the normal boot path: not proven.
- Silent-drop semantics on bypassed configs: proven.
- Final classification: hardening fix justified and applied.

### Applied Fix

- The branch now emits _emit_strategy_blocked with reason_code VOLATILITY_ENTRY_MULTIPLIER_MISSING in apps/reference/domains/decision_making/aurora_decision.py:1322.

## 8. Question 2 — Canonical Side Drift After Policy Overrides

### Evidence

- Raw kernel side is stored at apps/reference/domains/decision_making/aurora_decision.py:559.
- effective_side begins as result.side at apps/reference/domains/decision_making/aurora_decision.py:700.
- effective_side can be changed by exit manager at apps/reference/domains/decision_making/aurora_decision.py:844.
- effective_side can be changed by holding-period suppression at apps/reference/domains/decision_making/aurora_decision.py:866.
- _emit_signal emits effective_side first in apps/reference/domains/decision_making/aurora_decision.py:1250.
- Before the fix, downstream consumers still used result.side in pre-emit logic.
- A focused runtime harness forced an exit-manager override and captured the pre-fix split:

```text
{'entry_plan_side': 'buy', 'gate_side': 'buy', 'emit_side': 'SELL', 'result_side': 'buy'}
```

- The fix now introduces canonical_side at apps/reference/domains/decision_making/aurora_decision.py:954 and routes it through:
  - entry_plan compute in apps/reference/domains/decision_making/aurora_decision.py:987-988
  - objective signal_direction in apps/reference/domains/decision_making/aurora_decision.py:1083
  - projected notional in apps/reference/domains/decision_making/aurora_decision.py:1097
  - execution gate in apps/reference/domains/decision_making/aurora_decision.py:1175
  - emit path in apps/reference/domains/decision_making/aurora_decision.py:1209 and 1221
- The regression test in tests/domains/decision_making/test_aurora_handler.py:475 now proves canonical propagation on an exit override.

### Cause

- The method kept both a raw kernel side and a mutable post-policy side, but only the emit boundary consumed the post-policy side consistently.

### Mechanism

- A later policy override changed effective_side while upstream calculations and gates still used result.side.

### Effect

- Entry planning, objective classification, projected exposure math, and execution gate evaluation could all assess a different direction from the one eventually emitted to downstream consumers.

### Operational Risk

- Real runtime defect.
- Severity medium to high because it can distort trade geometry, gate verdicts, and payload truth on a live actionable bar.

### Verdict

- Proven runtime defect.
- Minimal localized fix was required and applied.

### Applied Fix

- canonical_side is now derived once from effective_side and used for all post-policy downstream consumers while result.side remains raw kernel diagnostics.

## 9. Question 3 — Real Contract Of _emit_strategy_blocked

### Evidence

- Runtime helper implementation in apps/reference/domains/decision_making/aurora_handler.py:511-532:
  - builds payload through write_strategy_decision_blocked
  - appends blocked timestamps for objective windows
  - emits EVT:STRATEGY_DECISION_BLOCKED
- decision_truth_artifacts.py defines write_strategy_decision_blocked as the truth helper for strategy-level blocked paths.
- trade_intent_reject_wal.py is the WAL helper for TRADE_INTENT_REJECTED and is separate by design.
- verb registry keeps STRATEGY_DECISION_BLOCKED and TRADE_INTENT_REJECTED as separate schema surfaces in apps/reference/dictionaries/verb_registry_v1.yaml:365-410.
- README says ordinary Aurora no-trade outcomes surface as STRATEGY_DECISION_BLOCKED in apps/reference/domains/decision_making/README.md:123.
- The authoritative contract test already existed and passed in tests/domains/decision_making/test_decision_truth_artifacts.py:119.
- The stale expectation was captured by the older handler test that expected reject WAL behavior.
- Direct pytest evidence during the investigation:
  - old stale handler test failed
  - blocked-truth contract test passed

### Cause

- Test drift: an older handler regression encoded reject-WAL expectations that no longer matched the live blocked-truth design.

### Mechanism

- The stale test patched write_trade_intent_rejected and expected _emit_strategy_blocked to log its failure, but runtime helper never called that function.

### Effect

- The suite could report a false regression even though runtime code, schema, registry, and contract tests were aligned.

### Operational Risk

- Runtime risk low.
- Maintenance and remediation risk high, because a naive response to the stale test could incorrectly reintroduce reject-WAL emission into the blocked helper.

### Verdict

- _emit_strategy_blocked runtime contract is defined and complete for blocked truth.
- The stale component was tests/domains/decision_making/test_aurora_handler.py.

### Applied Fix

- tests/domains/decision_making/test_aurora_handler.py:375 now asserts blocked-truth behavior and explicitly asserts that write_trade_intent_rejected is not called.

## 10. Minimal Changes Applied

### Runtime

- apps/reference/domains/decision_making/aurora_decision.py
  - added canonical_side after policy overrides
  - routed entry plan, objective signal_direction, projected notional, execution gate, emit path, and side-bias update through canonical_side
  - replaced bare missing-default volatility log-and-return with blocked-artifact emission

### Tests

- tests/domains/decision_making/test_aurora_handler.py
  - replaced stale reject-WAL expectation with blocked-truth contract assertion
  - added canonical-side propagation regression for exit-manager override
- tests/domains/decision_making/test_aurora_volatility_logic.py
  - added compatibility regression that proves missing DEFAULT on legacy/mock config emits structured blocked telemetry

## 11. Validation Evidence

### Static validation

- get_errors on the modified files returned no diagnostics.

### Runtime/config proof

- Real loader/plugin runtime probe confirmed:
  - config_type=AuroraConfig
  - handler_strict=True
  - enabled_vol_cfg_count=7
  - missing_default=[]

### Targeted pytest

Command executed:

```text
C:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/decision_making/test_aurora_handler.py tests/domains/decision_making/test_aurora_volatility_logic.py tests/domains/decision_making/test_decision_truth_artifacts.py -q
```

Result:

```text
28 passed, 3 skipped in 0.49s
```

### Additional direct investigation outputs

- Pre-fix stale blocked-helper expectation failed in isolation.
- Blocked-truth contract test in tests/domains/decision_making/test_decision_truth_artifacts.py passed in isolation.
- Side-drift runtime harness reproduced an actual mismatch before the fix.

## 12. Final Verdict

### FACTS

- Normal Aurora boot path is strict and typed.
- Live volatility-entry configs inspected in this audit contain DEFAULT.
- _emit_strategy_blocked is a blocked-truth helper, not a reject-WAL helper.
- Post-policy side overrides can diverge from raw kernel side.
- Before the fix, downstream consumers used raw result.side while emit used effective_side.

### INFERENCES

- The missing-DEFAULT branch was not proven reachable in the normal live boot path.
- The branch was still worth fixing because compatibility surfaces could hit it and lose observability.
- The stale handler test represented historical seam drift rather than a missing runtime feature.

### ASSUMPTIONS

- ConfigLoader plus AuroraBuiltinPlugin remains the authoritative runtime seam for Aurora startup.
- Partial mock AuroraHandler tests are compatibility surfaces worth keeping fail-closed and observable.

### UNKNOWNS

- Whether any uninspected runtime entrypoint still constructs AuroraHandler from untyped config in production.
- Whether last_signal_side should eventually be canonicalized as well.

### Disposition By Question

- Silent-drop / observability hole:
  - production reachability not proven
  - compatibility-surface observability hole proven
  - hardening fix applied
- Canonical side drift:
  - proven runtime defect
  - minimal fix applied
- _emit_strategy_blocked contract:
  - runtime contract proven as blocked truth only
  - stale test corrected
