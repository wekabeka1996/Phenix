# AUDIT: Execution Manager Duplication (Execution Orchestration)

## Executive Summary (Top 5 Duplication Risks)
1. **No explicit `execution_manager` module found**: orchestration responsibilities are spread across `execution_position`, `decision_making`, `services/order_guardian`, and `orchestrator`.
2. **Safety-critical validation duplicated** (`stopPrice`, order type lists, unknown-order idempotency), creating drift risk under hotfixes.
3. **Quantity/precision logic is fragmented** (DM sizing, OpenFlow guards, adapter quantization, qty_normalizer), with conflicting policies (fail-closed vs silent bump-up).
4. **Bracket orchestration is implemented in multiple paths** (`PLACE_ORDER`, deferred recovery, bracket-health), causing inconsistent dedup and conflict handling.
5. **State-flow orchestration split across domains** (`supersede` in ExecPosFSM vs `flip orchestration` in DecisionMaking), increasing race and ownership ambiguity.

## Method
- Mandatory pattern search executed via `rg` over `apps/reference`:
  - `"stopPrice" "triggerPrice" "TAKE_PROFIT" "STOP_MARKET"`
  - `"newClientOrderId" "clientOrderId" "EP-4015"`
  - `"quantize" "tick_size" "step_size"`
  - `"IDEMPOTENT_CANCEL" "Unknown order" "-2011" "-2013"`
  - `"supersede" "queued" "cancel timeout"`
  - `"Bracket" "pending_brackets" "reconcile"`

## Duplicate Map
| Concern | Location A | Location B | Same logic? | Divergence | Risk | Recommendation (SSOT owner) |
|---|---|---|---|---|---|---|
| stopPrice validation | `apps/reference/domains/execution_position/stopprice_validation.py:13-73` | `apps/reference/adapters/binance_adapter.py:55-88` | Partial | Two independent validators and error formatting contracts | Drift in fail-closed behavior | SSOT: `execution_position.stopprice_validation`; adapter should import shared validator |
| Conditional order type classification | `apps/reference/domains/execution_position/stopprice_validation.py:13-20` | `apps/reference/domains/execution_position/utils.py:111-112` | Yes | Separate lists can diverge on new order types | Wrong routing/guard decisions | SSOT: `stopprice_validation.CONDITIONAL_ORDER_TYPES` |
| clientOrderId length/format guard | `apps/reference/domains/execution_position/utils.py:165-223` | `apps/reference/adapters/binance_adapter.py:41-52` | Partial | Generation truncates/sanitizes; adapter separately rejects | Late runtime rejects despite upstream generation | SSOT: ID policy module in `execution_position.utils`; adapter enforces only as final assert |
| Quantity rounding formula | `apps/reference/domains/execution_position/qty_normalizer.py:140-143` | `apps/reference/domains/decision_making/sizing_margin_first.py:20-26` | Yes | Different wrappers and policy semantics around min checks | Behavior drift between sizing and execution | SSOT: `qty_normalizer.normalize_qty` |
| Quantity constraints policy | `apps/reference/domains/execution_position/qty_normalizer.py:145-191` | `apps/reference/adapters/binance_adapter.py:927-963` | No | `qty_normalizer` fail-closed; adapter silently bumps minQty/minNotional | Non-deterministic sizing + hidden policy override | SSOT: execution domain fail-closed; adapter should not silently mutate qty |
| Precision lookup and guard | `apps/reference/domains/execution_position/fsm_open.py:184-222` | `apps/reference/domains/decision_making/decision_making.py:4577-4607` | Partial | Both load `tick_size/step_size`; separate error contracts | Inconsistent symbol precision behavior | SSOT: shared `instrument_precision` helper |
| Bracket placement execution | `apps/reference/domains/execution_position/fsm.py:4974-5183` | `apps/reference/domains/execution_position/fsm.py:2908-3075` | Partial | Deferred path has guardrail; `PLACE_ORDER` path has different post-check semantics | Race/partial-protection blind spots | SSOT: single bracket placement coordinator invoked by all paths |
| Pending bracket consume/clear | `apps/reference/domains/execution_position/fsm.py:1093-1131` | `apps/reference/domains/execution_position/fsm.py:2235-2258` | Yes | Two consume implementations, different call contexts | Future drift/regressions in recovery | SSOT: one helper for all consume operations |
| Unknown-order / idempotent-cancel semantics | `apps/reference/domains/execution_position/idempotent_cancel.py:143-149,269-274` | `apps/reference/services/order_guardian.py:1117-1133` and `apps/reference/domains/inflight_reconcile/reconciler.py:173-186` | Partial | Three implementations of `-2011/-2013` meaning | Inconsistent cancel success accounting | SSOT: shared idempotent cancel policy helper |
| Timeout orchestration | `apps/reference/domains/execution_position/watchdog.py:474-494` | `apps/reference/domains/execution_position/fsm.py:4306-4495` and `apps/reference/orchestrator/orchestrator_fsm.py:286-311` | Partial | Each layer mutates timeout/error state independently | Double handling, unclear ownership | SSOT: ExecPosFSM timeout policy; orchestrator should observe only |
| Sequential open/close orchestration | `apps/reference/domains/execution_position/fsm.py:287-294,3082-3144` | `apps/reference/domains/decision_making/decision_making.py:4255-4414` | No | Supersede queue and flip orchestration overlap conceptually | Cross-domain race + duplicated queueing semantics | SSOT: execution_position owns order-state sequencing; DM emits intents only |
| Bracket existence/reconcile checks | `apps/reference/domains/execution_position/fsm.py:5348-5385` | `apps/reference/services/order_guardian.py:601-635,691-760` | Partial | Health-check scans exchange directly; guardian checks metadata conditions | Conflicting source of truth for "brackets exist" | SSOT: `services/order_guardian` for bracket existence and cleanup |

## Recommended SSOT Ownership
- `execution_position.stopprice_validation`:
  - Owns conditional-order classification and stopPrice validation.
  - Consumers: `fsm.py`, `fsm_manage.py`, `binance_adapter.py`.
- `execution_position.qty_normalizer`:
  - Owns quantity rounding and min constraints.
  - Consumers: DM sizing path, OpenFlow guards, adapter pre-submit checks.
- `execution_position.idempotent_cancel`:
  - Owns `-2011/-2013` semantics and cancel result normalization.
  - Consumers: ExecPosFSM, OrderGuardian service, InFlightReconciler.
- `services/order_guardian`:
  - Owns bracket existence checks, reconcile, and orphan cleanup.
  - Consumers: ExecPosFSM deferred/health/startup paths via guardian API only.
- `execution_position` domain:
  - Owns sequencing (`supersede`, cancel/fill race handling, recovery orchestration).
  - `decision_making` should stay intent-only, no order-state queue semantics.

## Minimal Refactor Plan (No Code)
1. **Package 1: Shared StopPrice Contract**
   - Move adapter checks to shared validator import.
   - Tests: adapter + FSM use identical accept/reject matrix.
   - Rollback: revert adapter import path only.
2. **Package 2: Shared Quantity Policy**
   - Route DM/OpenFlow through `normalize_qty` contract.
   - Remove adapter silent bump-up path (or gate behind explicit config flag default false).
   - Tests: one golden dataset for DM/OpenFlow/adapter parity.
   - Rollback: restore previous adapter quantize behavior behind feature flag.
3. **Package 3: Bracket Placement Coordinator**
   - Single coordinator API for deferred/manage/health/startup.
   - Include slot-aware dedup key and uniform guardrail emit.
   - Tests: race, multi-TP, partial failure, restart replay.
   - Rollback: switch call sites back to legacy path toggled by config.
4. **Package 4: Unified Idempotent Cancel Semantics**
   - Shared helper for unknown-order classification.
   - Tests: `-2011`, `-2013`, text-matched unknowns, non-terminal errors.
   - Rollback: retain old local fallbacks if helper unavailable.
5. **Package 5: Sequencing Boundary Cleanup**
   - Move flip queue semantics out of DM into execution_position event contract.
   - Tests: flip/supersede race matrix.
   - Rollback: keep DM fallback queue path behind compatibility flag.

## Risks If Left As-Is
- High probability of future regression when one duplicate path is patched without others.
- Safety behavior can vary by entry path (deferred vs manage vs startup vs health).
- Conflicting quantity policies can produce backtest/live divergence.
- Race handling remains distributed across domains with unclear ownership and duplicate state machines.
- Operational triage cost increases because log evidence is split across multiple orchestration layers.

## Audit Verdict
- Duplication Risk Level: **HIGH**
- No direct `execution_manager` file exists in tree; risk is architectural distribution of execution-manager responsibilities across multiple modules.

