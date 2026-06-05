> Note: The authoritative domain documentation is `execution_position/README.md`.
> This atlas is a package-local summary synced to the accepted Phase 8 skeleton.

# Execution Position Atlas

## Overview

`execution_position` is the deterministic execution layer that transforms trade
intents into live exchange actions while preserving lifecycle truth, fail-closed
guardrails, and observability.

## File map

- Root anchors:
  - `fsm.py`
  - `contracts.py`
  - `reasons.py`
  - `utils.py`
- Flows:
  - `flows/open/fsm_open.py`
  - `flows/manage/fsm_manage.py`
  - `flows/close/fsm_close.py`
- Guards:
  - `guards/exposure_guard.py`
  - `guards/exposure_manager.py`
- Guardian:
  - `guardian/order_guardian.py`
- State:
  - `state/order_index.py`
  - `state/order_ledger.py`
- Sidecar:
  - `sidecar/position_policy_sidecar.py`
  - `sidecar/position_policy_mediator.py`
- Telemetry:
  - `telemetry/metrics_collector.py`
  - `telemetry/drift_monitor.py`
- Orchestration:
  - `orchestration/event_handlers.py`
  - `orchestration/fill_ingress_coordinator.py`
- Support:
  - `support/stopprice_validation.py`
  - `support/utils_event_bus.py`

## Import compatibility

Phase 8 left flat-path compatibility stubs in place as temporary migration
shims. They preserve old imports while the semantic subpackage layout becomes
the documented physical structure. Those stubs are still present and are not
documented as removed.
