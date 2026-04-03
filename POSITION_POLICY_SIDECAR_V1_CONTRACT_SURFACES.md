# POSITION_POLICY_SIDECAR_V1_CONTRACT_SURFACES

## Existing Contracts Reused

- `EVT:PORTFOLIO_STATE_UPDATED`
  - reused for open/flat truth confirmation and entry price snapshot
- `EVT:ORDER_FILL`
  - reused for entry/exit fill correlation and position-life updates
- `EVT:ORDER_STATE_CHANGED`
  - reused for order progression and terminal non-fill context
- `EVT:EXECUTION_CLOSE_RECONCILED`
  - reused as authoritative post-close stop-evaluating signal
- `EVT:REGIME_DETECTED`
  - reused as local structural regime context only
- `EVT:FEATURES_CALCULATED`
  - reused for local feature context only
- Current `CMD:CLOSE` / `DEC:CLOSE` semantics
  - reused only conceptually as the later safe close path for symbol-scoped reduce-only behavior

## Existing Contracts Not To Be Touched

- `ManageFlowFSM` lifecycle ownership
- bracket order identity and bracket-fill handling
- `_closing_position` as incumbent close-in-progress signal
- `CloseExecutor.execute_close()` symbol-scoped reduce-only semantics
- `OrderGuardian` reconcile/tidy ownership
- `ExitManager` current post-entry evaluator semantics
- `RegimeDetector` structural regime ownership
- existing macro/BTC/anchor feature contracts

## New Internal-Only Contract Proposed

### 1. Sidecar recommendation telemetry

Internal-only structured telemetry surfaces:

- `EVT:POSITION_POLICY_SIDECAR_EVALUATED`
- `EVT:POSITION_POLICY_SIDECAR_SCORES`
- `EVT:POSITION_POLICY_SIDECAR_SUPPRESSED`
- `EVT:POSITION_POLICY_SIDECAR_RECOMMENDED`

These are Phase-1 internal observability surfaces, not new execution contracts.

### 2. Internal recommendation payload

Suggested internal-only recommendation shape:

| Field | Meaning |
| --- | --- |
| `trace_id` | evaluation/request correlation id |
| `symbol` | current symbol |
| `sidecar_version` | sidecar policy version |
| `evaluation_mode` | `observe_only` in Phase 1 |
| `recommended_action` | `HOLD` or `SOFT_CLOSE_RECOMMENDED` |
| `target_mode` | `symbol_current_net_only` |
| `requested_qty` | `null` in Phase 1 |
| `reason_codes` | bounded reason list |
| `score_snapshot` | derived signals used |
| `feature_ref` | latest feature timestamp and clock |
| `regime_ref` | latest local regime context |
| `position_snapshot` | side, qty, entry price, age |

## New Public Contract Deferred

- public sidecar action command
- public sidecar close-request schema
- public sidecar exact-lifecycle targeting schema
- public TP-replacement or target-extension schema

These are explicitly deferred.

## Missing Future Contract Required For Later Phases

- executable lifecycle or `position_id` contract if exact-target close is ever required
- public or at least stable internal close-initiation attribution contract
- explicit EP-internal request contract for safe Phase-2 soft-close actioning
- future bracket/target mutation contract if TP extension or stop/target replacement is ever pursued
- stronger action-to-outcome correlation fields connecting sidecar request -> close path -> reconcile outcome

## Contract Guardrail Summary

- Phase 1 reuses existing read-side contracts and adds internal observability only.
- Phase 1 does not change public close semantics.
- Anything beyond recommendation-only needs new or strengthened contracts, not just new code paths.
