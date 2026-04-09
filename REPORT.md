# EXECUTION_POSITION_AUXILIARY_BRACKET_REGISTRATION_PATH_AUDIT_AND_HARDENING_PACKAGE_05

## 1. Scope

- Target: auxiliary and internal bracket registration only.
- In scope:
  - DEC:PLACE_ORDER path in execution_position.
  - Live legacy bracket-role detection around auxiliary/internal child orders.
  - Synchronization across _symbol_brackets, OrderIndex, ManageFlowFSM, and OrderGuardian for the audited auxiliary path.
- Explicitly out of scope:
  - strategy math,
  - restart logic,
  - sidecar policy,
  - broad execution flow redesign.
- Protocol note:
  - FACT: the repo instruction attachment referenced docs/ai report protocol files.
  - FACT: docs/ai/AGENT_REPORT_SCHEMA.md and docs/ai/DONE_CRITERIA.md were not present in the current workspace.
  - INFERENCE: this report follows the requested FACT / INFERENCE / UNKNOWN discipline directly and fails closed on missing schema docs.

## 2. Evidence Summary

- FACT: fsm.py routes decision.verb == PLACE_ORDER into CloseExecutor.execute_place_order().
- FACT: BracketManager primary and deferred paths already used the explicit registration surface:
  - _set_symbol_bracket_order,
  - OrderIndex.register_bracket_child,
  - OrderGuardian.register_bracket or register_brackets,
  - ManageFlowFSM.set_bracket_ids.
- FACT: before this package, CloseExecutor.execute_place_order() only:
  - upserted generic open-order state into OrderIndex,
  - attached exchange order ids,
  - used brittle substring checks on _sl and _tp,
  - partially updated _symbol_brackets,
  - partially synced ManageFlowFSM.
- FACT: before this package, CloseExecutor.execute_place_order() did not explicitly register auxiliary bracket children through OrderIndex.register_bracket_child.
- FACT: before this package, CloseExecutor.execute_place_order() did not explicitly register auxiliary bracket metadata through OrderGuardian.register_bracket.
- FACT: before this package, ManageFlowFSM._on_bracket_placed() still depended on substring logic _sl and _tp.
- FACT: before this package, emergency stop activation emitted a legacy client id of the form rid_emergency_sl.
- FACT: the legacy emitter was live.

## 3. Defect Matrix

| Surface | Primary / deferred good path | Auxiliary path before package | Auxiliary path after package |
|---|---|---|---|
| Role detection | Canonical prefix registry | Brittle substring _sl / _tp | Canonical classify_client_order_id |
| _symbol_brackets | Explicit role write | Partial substring-based write | Explicit canonical role write |
| OrderIndex | register_bracket_child | generic upsert_from_open only | register_bracket_child for auxiliary SL/TP |
| OrderGuardian | explicit bracket registration | missing | explicit register_bracket |
| ManageFlowFSM sync | set_bracket_ids with bracket context | partial two-id sync only | set_bracket_ids with preserved paired-side context and algo ids |
| Emergency auxiliary emit | canonical prefixes elsewhere | legacy rid_emergency_sl | canonical generate_client_order_id SL |
| Placement ack hook | canonical role aware | substring dependent | canonical TP / TP1 / TP2 / SL / BH* aware |

## 4. Implemented Changes

### FACT

- apps/reference/domains/execution_position/close_executor.py now classifies auxiliary client ids through classify_client_order_id.
- apps/reference/domains/execution_position/close_executor.py now maps TP, TP1, TP2, and BHTP into canonical TP auxiliary registration and maps SL and BHSL into canonical SL auxiliary registration.
- apps/reference/domains/execution_position/close_executor.py now explicitly registers auxiliary bracket children through OrderIndex.register_bracket_child.
- apps/reference/domains/execution_position/close_executor.py now explicitly registers auxiliary bracket metadata through OrderGuardian.register_bracket.
- apps/reference/domains/execution_position/close_executor.py now updates ManageFlowFSM only when the lifecycle state is non-FLAT.
- apps/reference/domains/execution_position/close_executor.py now preserves the opposite-side algo-client-id when that side is already tracked in _symbol_brackets.
- apps/reference/domains/execution_position/close_executor.py now logs a fail-closed warning when a reduce-only or stop/take-profit auxiliary order is accepted with a noncanonical client id, instead of silently treating it as a bracket.
- apps/reference/domains/execution_position/fsm_manage.py now uses classify_client_order_id inside _on_bracket_placed().
- apps/reference/domains/execution_position/fsm_manage.py now recognizes TP1 and TP2 explicitly in placement acknowledgements.
- apps/reference/domains/execution_position/fsm_manage.py now emits emergency stop auxiliary orders with generate_client_order_id("SL", ...), removing the live legacy rid_emergency_sl form.
- tests/domains/execution_position/test_auxiliary_bracket_registration_hardening.py was added with focused regression coverage for the audited surfaces.

### INFERENCE

- INFERENCE: the audited auxiliary PLACE_ORDER path now uses the same canonical contract surface as the primary and deferred bracket placement paths, without adding a second registration contract.
- INFERENCE: the runtime dependency on legacy substring detection for auxiliary bracket registration has been removed from the audited path.

## 5. Validation Evidence

### FACT

- Static diagnostics after edits:
  - close_executor.py: no errors.
  - fsm_manage.py: no errors.
  - test_auxiliary_bracket_registration_hardening.py: no errors.
- Focused pytest command executed:

```text
c:/Users/user/Music/Phenix/.venv/Scripts/python.exe -m pytest tests/domains/execution_position/test_auxiliary_bracket_registration_hardening.py tests/domains/execution_position/test_bracket_algo_client_id_correlation.py tests/domains/execution_position/test_bracket_child_orderindex_canonical.py tests/domains/execution_position/test_fsm_manage_bracket_fixes.py -q
```

- Result:

```text
78 passed in 0.79s
```

- New focused proofs added:
  - auxiliary SL PLACE_ORDER uses canonical registration contract,
  - auxiliary TP1 PLACE_ORDER no longer depends on legacy substring matching,
  - noncanonical reduce-only PLACE_ORDER does not mutate bracket truth,
  - emergency stop emit uses canonical SL prefix,
  - _on_bracket_placed handles TP1 and TP2 via canonical prefix classification.

## 6. Files Changed

- apps/reference/domains/execution_position/close_executor.py
- apps/reference/domains/execution_position/fsm_manage.py
- tests/domains/execution_position/test_auxiliary_bracket_registration_hardening.py

## 7. Residual Risks And Boundaries

- FACT: recovery health-check bracket placement remains a separate path and was not modified here.
- FACT: that path was left untouched because the user explicitly excluded restart logic changes from this package.
- FACT: noncanonical auxiliary client ids are now warned and reference-registered only; they are not silently coerced into bracket truth.
- INFERENCE: this is the correct fail-closed posture for unknown auxiliary ids.
- UNKNOWN: whether any nonaudited future auxiliary emitter might reintroduce a noncanonical client id outside the exercised surfaces.

## 8. Final Verdict

- FACT: a real defect was proven in the auxiliary DEC:PLACE_ORDER bracket registration path.
- FACT: the defect was narrow and localized to canonical registration and legacy role-detection seams.
- FACT: the package hardened that seam without changing strategy math, restart logic, or sidecar policy.
- FACT: focused validation passed with 78 passing tests across the new regression file and adjacent canonical bracket suites.
- FINAL: PASS for the requested auxiliary bracket registration hardening scope.
