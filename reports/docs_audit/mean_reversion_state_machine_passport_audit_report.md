# Audit Report: `config/docs/mean_reversion_state_machine_passport.md`

Дата: 2026-03-13
Статус: completed
Формат: code-trace re-audit against current YAML, typed contracts, runtime handler/state machine, registry assignment, and focused tests

## Scope

Переаудитовано:
- `config/aurora/strategies/mean_reversion.yaml`
- `config/aurora/strategies.yaml`
- `apps/reference/config_models.py`
- `apps/reference/domains/feature_engineering/mean_reversion_strategy.py`
- `apps/reference/domains/decision_making/mean_reversion_handler.py`
- `apps/reference/domains/strategies/plugins/mean_reversion.py`
- `tests/domains/decision_making/test_mean_reversion_handler_config_wiring.py`
- `tests/domains/decision_making/test_mean_reversion_runtime_readiness.py`
- `tests/integration/test_mean_reversion_handler_event_contract_v1.py`

## Confirmed

- Live activation for `mean_reversion` remains assignment-first through `strategies_registry.assignments`.
- Current live symbol for MR is `DOGEUSDT`.
- `MeanReversion1mStrategy.on_bar()` is the real state-machine core: bars, indicators, regime mapping, BB-width filtering, `%B` entry logic, confidence enrichment, and advisory TP/SL generation.
- Runtime decision trigger is bar-driven via `CMD:PROCESS_STRATEGY`, not a live tick-driven path.
- Handler applies config fail-closed checks, liquidity gate, objective integration, and emits `EVT:STRATEGY_SIGNAL_PRODUCED` only after these overlays pass.
- Boundary to execution is explicit: `ExecPosFSM` / `ManageFlowFSM` own order lifecycle and reconciliation, not the MR state machine.

## Corrected

- Old passport mixed stale `1m`/`3m` naming with current runtime. Live YAML now sets `timeframe_sec=300`, so active runtime is 5m.
- Old passport underplayed the split between state machine and execution FSM. Incident classes like `ORDER_UPDATED` desync and `TTL_EXPIRED_3600s` belong downstream in execution_position.
- Old passport did not clearly separate strategy-local math from handler-owned gates like liquidity and objective.

## Drift Ledger

- Naming drift persists in code/comments: class names and some docstrings still say `1m` or `3m`, while live TF SSOT is 300 seconds.
- `tests/integration/test_mean_reversion_handler_event_contract_v1.py` is skipped and still references an older tick-based path; it is not a current source of truth.
- Historical comments around legacy paths remain in handler/state files and can mislead documentation if copied literally.

## Final Verdict

`config/docs/mean_reversion_state_machine_passport.md` has been rewritten to match current runtime truth. The updated passport now documents:
- assignment-first activation
- bar-driven handler trigger path
- exact strategy gating order in `on_bar()`
- handler overlays that are not part of the pure state machine
- the explicit boundary between MR strategy logic and execution-position reconciliation
