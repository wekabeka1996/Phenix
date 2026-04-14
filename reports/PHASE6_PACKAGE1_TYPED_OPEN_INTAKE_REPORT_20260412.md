# Phase 6 Package 1 Report — Typed Open Intake On `TRADE_INTENT_PROPOSED -> CMD:OPEN`

## 1. Executive Summary

Phase 6 Package 1 is implemented for the bounded seam:
`EVT:TRADE_INTENT_PROPOSED -> execution_position.intent_router -> CMD:OPEN`.

The open-intake route no longer depends on ad hoc dict reshaping inside
[`intent_router.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py).
Execution-side normalization now flows through the seam-local typed adapter in
[`trade_intent_open_intake.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py).

Ownership after this package is explicit:
- upstream bus schema still owns `EVT:TRADE_INTENT_PROPOSED` contract validation
- typed open intake now owns execution-side bridge normalization
- downstream [`CmdOpenPayload`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py) still owns final `CMD:OPEN` contract validation

Files changed:
- [`trade_intent_open_intake.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py)
- [`intent_router.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py)
- [`test_trade_intent_open_intake.py`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py)

## 2. FACTS

- Global JSON-schema validation is already active on the runtime bus in [`fsm_core.py`](C:/Users/user/Music/Phenix/vfoundation/core/fsm_core.py) and startup wiring in [`main.py`](C:/Users/user/Music/Phenix/apps/reference/main.py).
- Before this package, the open route inside [`intent_router.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py) manually extracted `symbol`, `side`, `order_type`, `price`, `tif`, `stop_price`, `target_price`, `valid_for_ms`, `price_ref`, `strategy`, and regime fields from a raw dict.
- The new seam-local intake contract constant is `trade_intent_open_intake_v1` at [`trade_intent_open_intake.py:17`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py#L17).
- The typed intake error surface is defined at [`trade_intent_open_intake.py:20`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py#L20).
- The typed intake model is defined at [`trade_intent_open_intake.py:81`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py#L81).
- The live parse/normalize entrypoint is [`trade_intent_open_intake.py:156`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py#L156).
- The router now emits typed-intake rejection diagnostics via [`intent_router.py:55`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#L55).
- The live open route now calls `parse_trade_intent_open_intake(...)` at [`intent_router.py:165`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py#L165).
- The downstream `CMD:OPEN` path still reaches `CmdOpenPayload.model_validate(...)` in [`fsm_open.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#L411).

## 3. INFERENCES

- This package closes the first Phase 6 foundation-to-runtime gap on the chosen seam without widening into whole-domain migration.
- The seam is now runtime-governed by a typed execution-side intake layer instead of raw router-local extraction.
- This is not a cutover. Upstream schema validation and downstream `CmdOpenPayload` remain in place, so the new adapter is a bridge owner, not a replacement owner.

## 4. ASSUMPTIONS

- The correct seam remains the normal open-intent route only; reduce-only close routing stays intentionally outside this package.
- Existing bus schema validation remains the correct owner of full `EVT:TRADE_INTENT_PROPOSED` shape, so the new typed intake only validates the execution-relevant subset.

## 5. UNKNOWNS

- Whether a future Phase 6 package will collapse `CMD:OPEN` JSON schema and `CmdOpenPayload` into one stronger contract surface.
- Whether the next bounded seam should be `DEC:OPEN -> executor` or a downstream fill/terminal seam.

## 6. Current Seam Before

Exact path before:
- `DecisionMaking` emitted `EVT:TRADE_INTENT_PROPOSED`
- `ExecPosFSM._on_trade_intent_proposed()` delegated to [`IntentRouter.on_trade_intent_proposed()`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py)
- `IntentRouter` manually reshaped the raw proposal dict into a `CMD:OPEN` payload
- `ExecPosFSM.handle()` routed the resulting command into `OpenFlowFSM`

Ad hoc dict shaping points before:
- `symbol = pld.get("instrument") or pld.get("symbol")`
- `order_info = pld.get("order", {})`
- manual `order_type`, `price`, `tif` checks
- manual `stop_price` / `target_price` extraction
- manual `metadata` assembly for strategy / TCA / risk context

That meant the bridge normalization logic lived in monolith-adjacent router glue instead of a typed seam owner.

## 7. New Typed Intake Design

Model / adapter:
- [`TradeIntentOpenOrder`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py)
- [`TradeIntentOpenIntake`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py)
- [`parse_trade_intent_open_intake(...)`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py#L156)

Ownership boundary:
- bus schema validates the full event
- typed intake normalizes only the open-intake subset
- `CmdOpenPayload` still validates the final command

Why bounded:
- no close-path rewrite
- no fill-path rewrite
- no `FSMv2` / `MetaFSM2` activation
- no change to upstream event schema ownership

## 8. Before vs After Runtime Path

Before:
1. `EVT:TRADE_INTENT_PROPOSED`
2. raw dict extraction in `IntentRouter`
3. raw dict `CMD:OPEN`
4. `CmdOpenPayload` validation in `OpenFlowFSM`

After:
1. `EVT:TRADE_INTENT_PROPOSED`
2. typed parse and normalization via [`parse_trade_intent_open_intake(...)`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py#L156)
3. typed `to_cmd_open_payload()` output
4. `CmdOpenPayload` validation in [`fsm_open.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py#L411)

Function-by-function:
- listener: [`fsm.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm.py)
- router entry: [`intent_router.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/intent_router.py)
- typed seam owner: [`trade_intent_open_intake.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/trade_intent_open_intake.py)
- final open command contract: [`fsm_open.py`](C:/Users/user/Music/Phenix/apps/reference/domains/execution_position/fsm_open.py)

## 9. Diagnostics Added

Exact surfaces:
- success payload metadata now includes:
  - `execution_intake_contract=trade_intent_open_intake_v1`
  - `execution_intake_path=EVT:TRADE_INTENT_PROPOSED->CMD:OPEN`
- typed intake rejection emits `EVT:TRADE_INTENT_REJECTED` with:
  - `details.execution_intake_contract`
  - `details.execution_intake_stage=typed_open_intake`
- router logs explicit typed-intake success/reject messages

What they prove:
- the new typed intake was the normalization owner on the open route
- rejection happened at the typed intake boundary, not later by silent router failure

## 10. Tests Added

- [`test_trade_intent_open_intake.py:115`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L115)
  Proves a valid proposal passes through typed intake and produces the expected `CMD:OPEN` payload.
- [`test_trade_intent_open_intake.py:133`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L133)
  Proves invalid open intents fail closed at typed intake.
- [`test_trade_intent_open_intake.py:146`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L146)
  Proves reduce-only / close routing is unchanged and does not use typed open intake.
- [`test_trade_intent_open_intake.py:168`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L168)
  Proves the live `ExecPosFSM._on_trade_intent_proposed()` path does not bypass typed intake.
- [`test_trade_intent_open_intake.py:189`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L189)
  Proves downstream `CmdOpenPayload` validation still runs after the new intake layer.
- [`test_trade_intent_open_intake.py:214`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L214)
  Proves existing `EVT:TRADE_INTENT_PROPOSED` schema validation remains compatible.
- [`test_trade_intent_open_intake.py:232`](C:/Users/user/Music/Phenix/tests/domains/execution_position/test_trade_intent_open_intake.py#L232)
  Proves rejection diagnostics are operator-visible.

## 11. Validation Evidence

Pytest command 1:
```text
pytest tests/domains/execution_position/test_trade_intent_open_intake.py tests/domains/execution_position/test_failclosed_validation.py tests/domains/execution_position/test_intent_boundary_audit.py tests/domains/execution_position/test_external_open_request.py tests/domains/execution_position/test_reject_contract_and_lifecycle_fix.py -q
```

Result:
```text
44 passed in 28.74s
```

Pytest command 2:
```text
pytest tests/bootstrap/test_schema_registry_activation.py tests/integration/test_ep01_4_tif_plumbing.py tests/integration/test_order_policy_01.py tests/domains/execution_position/test_regime_confidence_runtime_proof.py -q
```

Result:
```text
40 passed, 1 skipped in 4.47s
```

Historical legacy snapshot artifacts retained for traceability only:
- [`summary.json`](C:/Users/user/Music/Phenix/reports/runtime_phase6_package1_open_intake_proof_20260412/summary.json)
- [`success_cmd_open.json`](C:/Users/user/Music/Phenix/reports/runtime_phase6_package1_open_intake_proof_20260412/success_cmd_open.json)
- [`reject_event.json`](C:/Users/user/Music/Phenix/reports/runtime_phase6_package1_open_intake_proof_20260412/reject_event.json)

Evidence status after proof hardening:
- these files have no reproducible generation path in the repository and are not runtime-grade proof
- they are preserved as historical snapshots only
- reproducible harness-grade evidence now lives in `reports/runtime_phase6_package1_open_intake_harness_proof_20260414/`
- final evidence taxonomy and validation moved to `reports/PHASE6_PACKAGE1_PROOF_HARDENING_REPORT_20260414.md`

## 12. Residual Risks

- `CMD:OPEN` still has both bus JSON schema validation and downstream `CmdOpenPayload` validation. That duplication remains intentional in this package, but it is still duplicated contract enforcement.
- Reduce-only close routing still uses the preexisting path. That is deliberate, but it means Phase 6 Package 1 only closes the open seam.
- This package does not activate `FSMv2`, `MetaFSM2`, or protocol migration helpers on runtime.

## 13. Phase 6 Package 1 Readiness Note

This package unlocks the next bounded Phase 6 step because the first live decision-to-execution handoff is now typed on the execution side and no longer governed by raw router dict glue.

Still out of scope after this package:
- whole-domain `execution_position` migration
- terminal fill / close seam migration
- protocol migration helper activation
- `FSMv2` / `MetaFSM2` runtime cutover
- any Phase 7 cutover work
